"""Cálculo y persistencia de km / zona para la grilla Fletes."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models import Envio, FleteDistancia
from app.services.fletes_matching_service import (
    construir_flete_distancia,
    es_estimado_provider,
    limpiar_fragmento,
    match_localidad_sucursal,
    resolver_sucursal,
    texto_destino_envio,
)
from app.services.remito_utils import normalizar_remito

# Re-export para compatibilidad con imports existentes
_query_destino = texto_destino_envio
_limpiar_fragmento = limpiar_fragmento


def calcular_distancia_caso(
    db: Session,
    envio: Envio,
    *,
    sucursal_cod: str | None = None,
) -> FleteDistancia:
    remito_norm = envio.remito_norm or normalizar_remito(envio.remito)
    if not remito_norm:
        raise ValueError("Remito inválido")

    if not texto_destino_envio(envio):
        raise ValueError("Sin domicilio/localidad para geocodificar")

    payload = construir_flete_distancia(db, envio, sucursal_cod=sucursal_cod)
    if payload.get("error"):
        raise ValueError(str(payload["error"]))

    row = db.get(FleteDistancia, remito_norm)
    if not row:
        row = FleteDistancia(remito_norm=remito_norm)
        db.add(row)
    row.sucursal_cod = payload["sucursal_cod"]
    row.distance_km = payload["distance_km"]
    row.zona_km = payload["zona_km"]
    row.km_provider = payload["km_provider"]
    row.destino_query = payload["destino_query"]
    row.dest_lat = payload["dest_lat"]
    row.dest_lon = payload["dest_lon"]
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return row


def preview_flete_caso(
    db: Session,
    envio: Envio,
) -> dict[str, Any]:
    """Vista previa sin persistir ni llamar a Nominatim (solo reglas locales)."""
    from app.services.fletes_matching_service import (
        _motivo_asignacion,
        km_estimado_sin_coordenadas,
    )
    from app.services.zona_km import km_a_zona

    from app.services.fletes_matching_service import texto_alias_sucursal

    texto = texto_alias_sucursal(envio) or texto_destino_envio(envio)
    alias_cod, alias_key = match_localidad_sucursal(db, texto, envio=envio)
    res = resolver_sucursal(db, envio, dest=None)
    suc = res.sucursal
    out: dict[str, Any] = {
        "sucursal_cod": (suc.codigo if suc else None) or alias_cod,
        "alias": alias_key,
        "metodo": res.metodo,
    }
    if suc and res.metodo in ("solo_localidad", "deposito"):
        misma = res.metodo == "solo_localidad"
        km = km_estimado_sin_coordenadas(misma_zona_logica=misma)
        _, zona = km_a_zona(km)
        out["zona_km"] = zona
        out["distance_km"] = km
        out["estimado"] = True
        from app.services.fletes_matching_service import ResultadoGeocode

        out["motivo"] = _motivo_asignacion(
            res, ResultadoGeocode(None, "", "sin_geocode"), True
        )
    return out


def calcular_pendientes(
    db: Session,
    envios: list[Envio],
    *,
    limit: int = 25,
) -> dict[str, Any]:
    """Calcula km para casos flete sin registro previo (rate limit Nominatim)."""
    from app.services.mundo2_service import es_envio_mundo2, _agrupar_por_caso
    from app.services.rules_service import es_retiro_sucursal

    grupos = _agrupar_por_caso([e for e in envios if es_envio_mundo2(e)])
    hechos = 0
    estimados = 0
    errores: list[str] = []
    omitidos = 0

    for _key, grupo in grupos.items():
        if hechos >= limit:
            break
        base = grupo[0]
        if es_retiro_sucursal(base.transporte_nombre):
            omitidos += 1
            continue
        rn = base.remito_norm or normalizar_remito(base.remito)
        if not rn or db.get(FleteDistancia, rn):
            continue
        try:
            row = calcular_distancia_caso(db, base)
            hechos += 1
            if es_estimado_provider(row.km_provider):
                estimados += 1
        except Exception as e:
            errores.append(f"{rn}: {e}")

    return {
        "calculados": hechos,
        "estimados_localidad": estimados,
        "omitidos_retiro": omitidos,
        "errores": errores[:10],
    }


def mapa_distancias(db: Session) -> dict[str, FleteDistancia]:
    rows = db.query(FleteDistancia).all()
    return {r.remito_norm: r for r in rows if r.remito_norm}


def _codigo_sucursal_envio(envio: Envio) -> str | None:
    """Código AV/PI/… desde Tango (sucursal_cc u origen)."""
    raw = (envio.sucursal_cc or envio.origen_cd or "").strip().upper()
    if not raw:
        return None
    if len(raw) <= 4 and raw.replace(" ", "").isalpha():
        return raw.replace(" ", "")[:8]
    return None


def info_distancia_sucursal_destino(db: Session, envio: Envio) -> dict[str, Any]:
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
    remito_norm = envio.remito_norm or normalizar_remito(envio.remito)
    sucursal_fijada = _codigo_sucursal_envio(envio)
    dist = db.get(FleteDistancia, remito_norm) if remito_norm else None

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

    if dist and dist.distance_km is not None:
        sucursal_cod, sucursal_nombre = _sucursal_datos(dist.sucursal_cod)
        distance_km = float(dist.distance_km)
        zona_km = dist.zona_km
        es_estimado = es_estimado_provider(dist.km_provider)
        origen_sucursal = "calculada"
        pendiente_calculo = False
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

    return {
        "aplica": True,
        "sucursal_cod": sucursal_cod,
        "sucursal_nombre": sucursal_nombre,
        "origen_sucursal": origen_sucursal,
        "destino": destino,
        "distance_km": distance_km,
        "zona_km": zona_km,
        "zona_etiqueta": zona_etiqueta(zona_km),
        "es_estimado": es_estimado,
        "motivo": motivo,
        "pendiente_calculo": pendiente_calculo,
    }
