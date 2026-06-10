"""Cálculo y persistencia de km / zona para la grilla Fletes."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models import Envio, FleteDistancia
from app.services.fletes_matching_service import (
    construir_flete_distancia,
    es_estimado_provider,
    fingerprint_domicilio,
    limpiar_fragmento,
    match_sucursal_envio,
    resolver_sucursal,
    texto_destino_envio,
)
from app.services.remito_utils import normalizar_remito

# Re-export para compatibilidad con imports existentes
_query_destino = texto_destino_envio
_limpiar_fragmento = limpiar_fragmento


def clave_persistencia_distancia(envio: Envio) -> str | None:
    """
    Clave para cache km: remito oficial, o pedido-/fp- si aún no hay remito.
    Casos sin remito (ESTADO REMITO = Sin remito) igual pueden geocodificarse.
    """
    rn = envio.remito_norm or normalizar_remito(envio.remito)
    if rn:
        return rn[:40]
    from app.services.remito_maestro import clave_agrupacion_interna

    interna = clave_agrupacion_interna(envio)
    if interna.startswith("pedido-"):
        return interna[:40]
    fp = fingerprint_domicilio(envio)
    if fp:
        return f"fp-{fp[:32]}"
    return None


def _es_distancia_real(row: FleteDistancia | None) -> bool:
    if not row or row.distance_km is None:
        return False
    prov = (row.km_provider or "").lower()
    return "preview" not in prov and "estimado_localidad" not in prov


def _fila_distancia_util(row: FleteDistancia | None) -> bool:
    """Fila usable para grilla/cobro (km o zona)."""
    if not row:
        return False
    return row.distance_km is not None or bool(row.zona_km)


def buscar_distancia_por_domicilio(db: Session, envio: Envio) -> FleteDistancia | None:
    """Reutiliza cálculo previo para el mismo domicilio (otro remito)."""
    fp = fingerprint_domicilio(envio)
    if not fp:
        return None
    from sqlalchemy import select

    return db.scalars(
        select(FleteDistancia)
        .where(FleteDistancia.domicilio_fp == fp)
        .where(FleteDistancia.distance_km.isnot(None))
        .order_by(FleteDistancia.updated_at.desc())
    ).first()


def _persistir_fila_distancia(
    db: Session,
    remito_norm: str,
    envio: Envio,
    payload: dict[str, Any],
    *,
    km_provider_extra: str = "",
) -> FleteDistancia:
    row = db.get(FleteDistancia, remito_norm)
    if not row:
        row = FleteDistancia(remito_norm=remito_norm)
        db.add(row)
    row.domicilio_fp = fingerprint_domicilio(envio)
    row.sucursal_cod = payload["sucursal_cod"]
    row.distance_km = payload["distance_km"]
    row.zona_km = payload["zona_km"]
    prov = str(payload.get("km_provider") or "")
    if km_provider_extra:
        prov = f"{prov}|{km_provider_extra}" if prov else km_provider_extra
    row.km_provider = prov[:80]
    row.destino_query = payload.get("destino_query")
    row.dest_lat = payload.get("dest_lat")
    row.dest_lon = payload.get("dest_lon")
    row.updated_at = datetime.utcnow()
    return row


def _copiar_distancia_desde_cache(
    db: Session,
    origen: FleteDistancia,
    envio: Envio,
) -> FleteDistancia:
    clave = clave_persistencia_distancia(envio)
    if not clave:
        raise ValueError("Sin clave de cache (remito, pedido o domicilio)")
    payload = {
        "sucursal_cod": origen.sucursal_cod,
        "distance_km": origen.distance_km,
        "zona_km": origen.zona_km,
        "km_provider": origen.km_provider,
        "destino_query": origen.destino_query or texto_destino_envio(envio),
        "dest_lat": origen.dest_lat,
        "dest_lon": origen.dest_lon,
    }
    row = _persistir_fila_distancia(
        db, clave, envio, payload, km_provider_extra="reuso_domicilio"
    )
    db.commit()
    db.refresh(row)
    return row


def calcular_o_reusar_distancia(
    db: Session,
    envio: Envio,
    *,
    sucursal_cod: str | None = None,
    forzar: bool = False,
) -> FleteDistancia | None:
    """
    1) Cache por remito · 2) Cache por domicilio · 3) Geocodificar y guardar.
    geocode_cache (kilometrizador) evita repetir Nominatim para la misma query.
    """
    clave = clave_persistencia_distancia(envio)
    if not clave:
        return None
    if not texto_destino_envio(envio):
        return None

    if not forzar:
        actual = db.get(FleteDistancia, clave)
        if _es_distancia_real(actual):
            return actual
        cached = buscar_distancia_por_domicilio(db, envio)
        if cached and cached.remito_norm != clave:
            return _copiar_distancia_desde_cache(db, cached, envio)

    return calcular_distancia_caso(db, envio, sucursal_cod=sucursal_cod, forzar=forzar)


def calcular_distancia_caso(
    db: Session,
    envio: Envio,
    *,
    sucursal_cod: str | None = None,
    forzar: bool = False,
) -> FleteDistancia:
    clave = clave_persistencia_distancia(envio)
    if not clave:
        raise ValueError("Sin remito ni pedido para cachear distancia")

    if not texto_destino_envio(envio):
        raise ValueError("Sin domicilio/localidad para geocodificar")

    if not forzar:
        actual = db.get(FleteDistancia, clave)
        if _es_distancia_real(actual):
            return actual

    payload = construir_flete_distancia(db, envio, sucursal_cod=sucursal_cod)
    if payload.get("error"):
        raise ValueError(str(payload["error"]))

    row = _persistir_fila_distancia(db, clave, envio, payload)
    db.commit()
    db.refresh(row)
    return row


def preview_flete_caso(
    db: Session,
    envio: Envio,
) -> dict[str, Any]:
    """Vista previa sin Nominatim: alias localidad, barrio CABA o depósito."""
    from app.models import Sucursal
    from app.services.fletes_matching_service import (
        ResultadoGeocode,
        _motivo_asignacion,
        km_estimado_sin_coordenadas,
    )
    from app.services.zona_km import km_a_zona

    alias_cod, alias_key = match_sucursal_envio(db, envio)
    res = resolver_sucursal(db, envio, dest=None)
    suc = res.sucursal
    if not suc and alias_cod:
        suc = db.get(Sucursal, alias_cod)
    cod = (suc.codigo if suc else None) or alias_cod
    metodo = res.metodo if res.metodo != "sin_sucursal" else (
        "solo_localidad" if alias_cod else "sin_sucursal"
    )
    out: dict[str, Any] = {
        "sucursal_cod": cod,
        "alias": alias_key or res.alias,
        "metodo": metodo,
    }
    if cod and metodo in ("solo_localidad", "deposito", "explicito"):
        misma = metodo == "solo_localidad"
        km = km_estimado_sin_coordenadas(misma_zona_logica=misma)
        _, zona = km_a_zona(km)
        out["zona_km"] = zona
        out["distance_km"] = km
        out["estimado"] = True
        out["motivo"] = _motivo_asignacion(
            res, ResultadoGeocode(None, "", "sin_geocode"), True
        )
    return out


def _persistir_preview_distancia(
    db: Session,
    envio: Envio,
    prev: dict[str, Any],
) -> FleteDistancia | None:
    """Guarda estimado local en cache (sin geocodificar)."""
    if not prev.get("sucursal_cod") or prev.get("distance_km") is None:
        return None
    clave = clave_persistencia_distancia(envio)
    if not clave:
        return None
    row = db.get(FleteDistancia, clave)
    if row and row.distance_km is not None:
        prov = (row.km_provider or "").lower()
        if "preview" not in prov and "estimado_localidad" not in prov:
            return row
    if not row:
        row = FleteDistancia(remito_norm=clave)
        db.add(row)
    row.domicilio_fp = fingerprint_domicilio(envio)
    row.sucursal_cod = str(prev["sucursal_cod"])
    row.distance_km = float(prev["distance_km"])
    row.zona_km = prev.get("zona_km")
    row.km_provider = "estimado_preview|solo_localidad"
    row.destino_query = (texto_destino_envio(envio) or "")[:500]
    row.updated_at = datetime.utcnow()
    return row


def _prioridad_geocode(envio: Envio) -> int:
    """Mayor = domicilio con calle/número (mejor candidato a geocodificar)."""
    from app.services.fletes_matching_service import es_destino_caba

    dom = limpiar_fragmento(envio.domicilio) or ""
    score = 0
    if dom:
        score += 10
    if re.search(r"\d{2,}", dom):
        score += 20
    if es_destino_caba(envio) and dom:
        score += 5
    return score


def enriquecer_previews_pendientes(
    db: Session,
    envios: list[Envio],
    *,
    limit: int | None = None,
) -> dict[str, Any]:
    """Preview rápido (alias/barrio) y persiste estimados sin Nominatim."""
    from app.services.mundo2_service import _agrupar_por_caso, es_envio_mundo2
    from app.services.rules_service import es_retiro_sucursal

    grupos = _agrupar_por_caso([e for e in envios if es_envio_mundo2(e)])
    enriquecidos = 0
    omitidos = 0
    sin_match = 0

    for _key, grupo in grupos.items():
        if limit is not None and enriquecidos >= limit:
            break
        base = grupo[0]
        if es_retiro_sucursal(base.transporte_nombre):
            omitidos += 1
            continue
        clave = clave_persistencia_distancia(base)
        if not clave:
            continue
        existente = db.get(FleteDistancia, clave)
        if existente and existente.distance_km is not None:
            if "preview" not in (existente.km_provider or ""):
                continue
        prev = preview_flete_caso(db, base)
        if not prev.get("sucursal_cod"):
            sin_match += 1
            continue
        if _persistir_preview_distancia(db, base, prev):
            enriquecidos += 1

    if enriquecidos:
        db.commit()

    return {
        "enriquecidos": enriquecidos,
        "omitidos_retiro": omitidos,
        "sin_match_sucursal": sin_match,
    }


def calcular_pendientes(
    db: Session,
    envios: list[Envio],
    *,
    limit: int = 500,
) -> dict[str, Any]:
    """Calcula km reales para casos sin registro o solo con preview estimado."""
    from app.services.mundo2_service import es_envio_mundo2, _agrupar_por_caso
    from app.services.rules_service import es_retiro_sucursal

    grupos = _agrupar_por_caso([e for e in envios if es_envio_mundo2(e)])
    ordenados = sorted(
        grupos.items(),
        key=lambda kv: -_prioridad_geocode(kv[1][0]),
    )
    hechos = 0
    estimados = 0
    errores: list[str] = []
    omitidos = 0
    saltados = 0
    reusados = 0

    for _key, grupo in ordenados:
        if hechos >= limit:
            break
        base = grupo[0]
        if es_retiro_sucursal(base.transporte_nombre):
            omitidos += 1
            continue
        clave = clave_persistencia_distancia(base)
        if not clave:
            continue
        existente = db.get(FleteDistancia, clave)
        if existente and existente.distance_km is not None:
            prov = (existente.km_provider or "").lower()
            if "preview" not in prov and "estimado_localidad" not in prov:
                saltados += 1
                continue
        try:
            row = calcular_o_reusar_distancia(db, base)
            if not row:
                continue
            hechos += 1
            if "reuso_domicilio" in (row.km_provider or ""):
                reusados += 1
            if es_estimado_provider(row.km_provider):
                estimados += 1
            if hechos % 20 == 0:
                db.commit()
        except Exception as e:
            errores.append(f"{clave}: {e}")

    db.commit()
    return {
        "calculados": hechos,
        "reusados_domicilio": reusados,
        "estimados_localidad": estimados,
        "omitidos_retiro": omitidos,
        "ya_calculados": saltados,
        "errores": errores[:15],
    }


def mapa_distancias(db: Session) -> dict[str, FleteDistancia]:
    """Índice por remito y por fingerprint de domicilio (reuso en grilla)."""
    rows = db.query(FleteDistancia).all()
    out: dict[str, FleteDistancia] = {}
    for r in rows:
        if r.remito_norm:
            out[r.remito_norm] = r
        if r.domicilio_fp and r.domicilio_fp not in out:
            out[r.domicilio_fp] = r
    return out


def _claves_lookup_distancia(envio: Envio, caso_key: str | None = None) -> list[str]:
    """Claves de búsqueda: remito, pedido, caso, domicilio_fp."""
    from app.services.mundo2_service import clave_agrupacion_caso
    from app.services.remito_maestro import clave_agrupacion_interna

    fp = fingerprint_domicilio(envio)
    claves = [
        clave_persistencia_distancia(envio),
        envio.remito_norm or normalizar_remito(envio.remito),
        clave_agrupacion_caso(envio),
        clave_agrupacion_interna(envio),
        caso_key,
        fp,
    ]
    vistos: set[str] = set()
    out: list[str] = []
    for k in claves:
        if k and k not in vistos:
            vistos.add(k)
            out.append(k)
    return out


def obtener_distancia_caso(
    db: Session,
    envio: Envio,
    *,
    distancias: dict[str, FleteDistancia] | None = None,
    caso_key: str | None = None,
    intentar_reuso_domicilio: bool = True,
    intentar_calculo: bool = False,
    forzar: bool = False,
) -> FleteDistancia | None:
    """
    Resolución unificada de km/zona/sucursal para toda la app.
    Orden: mapa cache → remito DB → reuso domicilio → geocodificar.
    """
    clave = clave_persistencia_distancia(envio)

    if not forzar:
        for lk in _claves_lookup_distancia(envio, caso_key):
            row = (distancias or {}).get(lk) if distancias else None
            if not row and clave and lk == clave:
                row = db.get(FleteDistancia, clave)
            if _fila_distancia_util(row):
                return row

        if intentar_reuso_domicilio and clave:
            actual = db.get(FleteDistancia, clave)
            if not _es_distancia_real(actual):
                cached = buscar_distancia_por_domicilio(db, envio)
                if cached and _fila_distancia_util(cached):
                    if cached.remito_norm != clave:
                        return _copiar_distancia_desde_cache(db, cached, envio)
                    return cached

    if intentar_calculo and texto_destino_envio(envio):
        try:
            return calcular_o_reusar_distancia(db, envio, forzar=forzar)
        except Exception:
            return None
    return None


def backfill_domicilio_fp(db: Session, envios: list[Envio]) -> int:
    """Rellena fingerprint en filas ya calculadas (habilita reuso general)."""
    from app.services.mundo2_service import _agrupar_por_caso, es_envio_mundo2

    actualizados = 0
    for grupo in _agrupar_por_caso([e for e in envios if es_envio_mundo2(e)]).values():
        base = grupo[0]
        clave = clave_persistencia_distancia(base)
        if not clave:
            continue
        row = db.get(FleteDistancia, clave)
        if not row or row.domicilio_fp:
            continue
        fp = fingerprint_domicilio(base)
        if fp:
            row.domicilio_fp = fp
            actualizados += 1
    if actualizados:
        db.commit()
    return actualizados


def reusar_domicilios_pendientes(
    db: Session,
    envios: list[Envio],
    *,
    limit: int | None = None,
) -> int:
    """Propaga km/zona de domicilios ya geocodificados a remitos pendientes."""
    from app.services.mundo2_service import _agrupar_por_caso, es_envio_mundo2
    from app.services.rules_service import es_retiro_sucursal

    grupos = _agrupar_por_caso([e for e in envios if es_envio_mundo2(e)])
    ordenados = sorted(
        grupos.items(),
        key=lambda kv: -_prioridad_geocode(kv[1][0]),
    )
    reusados = 0
    for _key, grupo in ordenados:
        if limit is not None and reusados >= limit:
            break
        base = grupo[0]
        if es_retiro_sucursal(base.transporte_nombre):
            continue
        clave = clave_persistencia_distancia(base)
        if not clave:
            continue
        actual = db.get(FleteDistancia, clave)
        if _es_distancia_real(actual):
            continue
        cached = buscar_distancia_por_domicilio(db, base)
        if not cached or not _fila_distancia_util(cached) or cached.remito_norm == clave:
            continue
        try:
            _copiar_distancia_desde_cache(db, cached, base)
            reusados += 1
        except Exception:
            continue
    return reusados


def preparar_contexto_km(
    db: Session,
    envios: list[Envio],
    *,
    enrich_limit: int | None = 3000,
    auto_calc_limit: int = 0,
) -> dict[str, FleteDistancia]:
    """
    Pipeline estándar antes de grilla/cobro/stats:
    preview persistido → backfill domicilio_fp → reuso domicilio → km reales (opcional).
    """
    enriquecer_previews_pendientes(db, envios, limit=enrich_limit)
    backfill_domicilio_fp(db, envios)
    reusar_domicilios_pendientes(db, envios)
    if auto_calc_limit > 0:
        calcular_pendientes(db, envios, limit=auto_calc_limit)
    return mapa_distancias(db)


def _codigo_sucursal_envio(envio: Envio) -> str | None:
    """Código AV/PI/… desde Tango (sucursal_cc u origen)."""
    raw = (envio.sucursal_cc or envio.origen_cd or "").strip().upper()
    if not raw:
        return None
    if len(raw) <= 4 and raw.replace(" ", "").isalpha():
        return raw.replace(" ", "")[:8]
    return None


def info_distancia_sucursal_destino(
    db: Session,
    envio: Envio,
    *,
    intentar_calculo: bool = False,
) -> dict[str, Any]:
    """Resumen legible: sucursal (fijada/sugerida) → destino y km."""
    from app.models import Sucursal
    from app.services.mundo2_service import es_envio_mundo2
    from app.services.rules_service import es_retiro_sucursal
    from app.services.zona_km import zona_etiqueta

    if not es_envio_mundo2(envio):
        return {"aplica": False}

    if es_retiro_sucursal(envio.transporte_nombre):
        return {
            "aplica": False,
            "motivo": "Retiro en sucursal — no aplica distancia a domicilio.",
        }

    destino = texto_destino_envio(envio)
    domicilio = limpiar_fragmento(envio.domicilio) or ""
    remito_norm = envio.remito_norm or normalizar_remito(envio.remito)
    sucursal_fijada = _codigo_sucursal_envio(envio)
    error_calculo = ""
    try:
        dist = obtener_distancia_caso(
            db,
            envio,
            intentar_reuso_domicilio=True,
            intentar_calculo=bool(intentar_calculo and domicilio),
        )
    except Exception as exc:
        dist = None
        error_calculo = str(exc)

    def _sucursal_datos(cod: str | None) -> tuple[str | None, str | None]:
        if not cod:
            return None, None
        suc = db.get(Sucursal, cod.strip().upper())
        if suc:
            return suc.codigo, suc.nombre
        return cod.strip().upper(), None

    sucursal_cod: str | None = None
    sucursal_nombre: str | None = None
    origen_sucursal = "sugerida"
    distance_km: float | None = None
    zona_km: str | None = None
    es_estimado = False
    motivo = ""
    pendiente_calculo = True
    desde_cache_domicilio = False
    km_provider = ""

    if dist and dist.distance_km is not None:
        sucursal_cod, sucursal_nombre = _sucursal_datos(dist.sucursal_cod)
        distance_km = float(dist.distance_km)
        zona_km = dist.zona_km
        km_provider = dist.km_provider or ""
        es_estimado = es_estimado_provider(km_provider)
        origen_sucursal = "calculada"
        pendiente_calculo = es_estimado
        desde_cache_domicilio = "reuso_domicilio" in km_provider.lower()
        if sucursal_fijada and dist.sucursal_cod == sucursal_fijada:
            origen_sucursal = "fijada"
    else:
        prev = preview_flete_caso(db, envio)
        if sucursal_fijada:
            sucursal_cod, sucursal_nombre = _sucursal_datos(sucursal_fijada)
            origen_sucursal = "fijada"
        elif prev.get("sucursal_cod"):
            sucursal_cod, sucursal_nombre = _sucursal_datos(str(prev["sucursal_cod"]))
            origen_sucursal = "sugerida"
        if prev.get("distance_km") is not None:
            distance_km = float(prev["distance_km"])
            zona_km = prev.get("zona_km")
            es_estimado = bool(prev.get("estimado"))
            motivo = str(prev.get("motivo") or "")
        elif intentar_calculo and domicilio and not error_calculo:
            from app.services.fletes_matching_service import construir_flete_distancia

            payload = construir_flete_distancia(db, envio)
            if not payload.get("error") and payload.get("distance_km") is not None:
                sucursal_cod, sucursal_nombre = _sucursal_datos(payload.get("sucursal_cod"))
                distance_km = float(payload["distance_km"])
                zona_km = payload.get("zona_km")
                es_estimado = es_estimado_provider(payload.get("km_provider"))
                origen_sucursal = "calculada"
                pendiente_calculo = es_estimado
                clave = clave_persistencia_distancia(envio)
                if clave:
                    try:
                        _persistir_fila_distancia(db, clave, envio, payload)
                        db.commit()
                    except Exception:
                        db.rollback()

    return {
        "aplica": True,
        "sucursal_cod": sucursal_cod,
        "sucursal_nombre": sucursal_nombre,
        "origen_sucursal": origen_sucursal,
        "domicilio": domicilio,
        "destino": destino,
        "distance_km": distance_km,
        "zona_km": zona_km,
        "zona_etiqueta": zona_etiqueta(zona_km),
        "es_estimado": es_estimado,
        "motivo": motivo,
        "pendiente_calculo": pendiente_calculo,
        "desde_cache_domicilio": desde_cache_domicilio,
        "km_provider": km_provider,
        "error_calculo": error_calculo,
    }
