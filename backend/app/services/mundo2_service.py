"""Mundo 2 — fletes sucursales CABA/GBA (sin depender de nuevos exports Tango)."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from typing import Any

from app.config import settings
from app.models import Envio, FleteDistancia, Tarifa
from app.services.zona_km import zona_etiqueta
from app.services.excel_parser import infer_medida, infer_tipo_producto
from app.services.money_utils import normalize_maestro_montos, round_pesos
from app.services.maestro_service import _origen_planilla
from app.services.fecha_utils import formato_fecha_grilla
from app.services.remito_maestro import (
    clave_agrupacion_caso,
    clave_agrupacion_interna,
    etiqueta_estado_remito,
    estado_remito_envio,
    grupo_pasa_filtro_remito,
    texto_remito_grilla,
)
from app.services.remito_utils import es_remito_transito
from app.services.rules_service import (
    es_amba_gba,
    es_retiro_sucursal,
    lookup_tarifa,
    recalcular_costos_linea,
)

PROVEEDOR_TARIFA_LOCAL = "FLETES_SUC"
ZONAS_KM = ("Zona1_10km", "Zona2_20km", "Zona3_40km", "Zona4_40+km")

FLETES_COLUMNAS = [
    "FECHA PEDIDO",
    "FECHA ENTREGA",
    "REMITOS",
    "ESTADO REMITO",
    "DESTINATARIO",
    "LOCALIDAD",
    "PROVINCIA",
    "TRANSPORTE",
    "FLETERO",
    "SUCURSAL",
    "KM",
    "ZONA KM",
    "BULTOS",
    "TARIFA REF",
    "total",
]


def es_envio_mundo2(envio: Envio) -> bool:
    """Pedidos de flete local: Amba/GBA o retiro en sucursal (excluidos del maestro interior)."""
    if envio.excluir_planilla:
        return True
    return es_amba_gba(envio.provincia, envio.localidad, envio.cp)


def _agrupar_por_caso(envios: list[Envio]) -> dict[str, list[Envio]]:
    grupos: dict[str, list[Envio]] = defaultdict(list)
    for e in envios:
        if not clave_agrupacion_caso(e) and es_remito_transito(e.remito):
            continue
        key = clave_agrupacion_caso(e) or clave_agrupacion_interna(e)
        grupos[key].append(e)
    return grupos


def _bultos_grupo(lineas: list[Envio]) -> int:
    total = int(sum(l.cantidad or 0 for l in lineas))
    if total > 0:
        return total
    return sum(1 for l in lineas if l.descripcion or l.cod_articulo)


def _tarifas_zona_local(
    tarifas: list[Tarifa],
    tipo: str,
    medida: str,
) -> dict[str, float]:
    out: dict[str, float] = {}
    tipos_fallback = [tipo]
    if tipo == "CONJUNTO_FLETE":
        tipos_fallback.extend(["CONJUNTO", "FLETE_EXPRESS", "COLCHON"])
    elif tipo not in ("FLETE_EXPRESS", "COLCHON"):
        tipos_fallback.extend(["FLETE_EXPRESS", "COLCHON", "MUEBLES"])
    for zona in ZONAS_KM:
        for t in tipos_fallback:
            precio = lookup_tarifa(
                tarifas,
                PROVEEDOR_TARIFA_LOCAL,
                "CABA/GBA",
                zona,
                t,
                medida,
            )
            if precio is not None:
                out[zona] = precio
                break
    return out


def _buscar_distancia_caso(
    base: Envio,
    key: str,
    distancias: dict[str, FleteDistancia] | None,
    dist_directa: FleteDistancia | None,
    db: Any = None,
) -> FleteDistancia | None:
    """Cache de km: remito, domicilio_fp y reuso (misma lógica en toda la app)."""
    if db is not None:
        from app.services.fletes_km_service import obtener_distancia_caso

        row = obtener_distancia_caso(
            db, base, distancias=distancias, caso_key=key, intentar_reuso_domicilio=True
        )
        if row:
            return row
    if dist_directa and (dist_directa.zona_km or dist_directa.distance_km is not None):
        return dist_directa
    if not distancias:
        return dist_directa
    from app.services.fletes_km_service import _claves_lookup_distancia, _fila_distancia_util

    for rk in _claves_lookup_distancia(base, key):
        row = distancias.get(rk)
        if _fila_distancia_util(row):
            return row
    return dist_directa


def _color_fila_fletes(
    *,
    retiro: bool,
    abona_wamaro: bool,
    tiene_tarifa: bool,
    zona_asignada: str | None,
    sucursal_cod: str | None = None,
    es_estimado: bool = False,
    motivo_extra: str | None = None,
) -> tuple[str, str]:
    if retiro:
        return "gris", "Retiro en sucursal — sin flete a domicilio"
    if not tiene_tarifa:
        return "amarillo", "Sin tarifa local (importá hoja fletes sucursales)"
    if not zona_asignada:
        if sucursal_cod:
            return (
                "amarillo",
                f"Sucursal {sucursal_cod} sugerida — calcular km o confirmar zona",
            )
        return "amarillo", "Pendiente asignar zona km (domicilio → sucursal)"
    if abona_wamaro:
        return "celeste", "Abona Wamaro — tarifa referencia sucursal"
    if es_estimado:
        base = motivo_extra or "Tarifa ref. por localidad (km estimado)"
        return "verde", base
    if motivo_extra:
        return "verde", motivo_extra
    return "verde", "Tarifa local de referencia calculada"


def _fila_fletes_desde_grupo(
    key: str,
    lineas: list[Envio],
    tarifas: list[Tarifa] | None = None,
    *,
    tarifario_ctx: Any = None,
    dist: FleteDistancia | None = None,
    db: Any = None,
    mapa_fletero: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    base = lineas[0]
    retiro = es_retiro_sucursal(base.transporte_nombre)
    bultos = _bultos_grupo(lineas)

    from app.services.pedido_cobro_service import interpretar_pedido, tipo_flete_caba_gba

    interp = interpretar_pedido(lineas)
    tipo, medida = tipo_flete_caba_gba(interp)

    tarifas_grupo = (
        tarifario_ctx.tarifas_para_grupo(lineas)
        if tarifario_ctx
        else (tarifas or [])
    )
    por_zona = _tarifas_zona_local(tarifas_grupo, tipo, medida)
    zona_km: str | None = None
    costo_ref: float | None = None
    km_txt = ""
    sucursal_cod = ""

    es_estimado = False
    motivo_extra: str | None = None

    if dist and (dist.zona_km or dist.distance_km is not None):
        zona_km = dist.zona_km
        costo_ref = por_zona.get(zona_km)
        sucursal_cod = dist.sucursal_cod or ""
        try:
            from app.services.fletes_matching_service import es_estimado_provider

            es_estimado = es_estimado_provider(dist.km_provider)
        except Exception:
            es_estimado = False
        if dist.distance_km:
            km_val = float(dist.distance_km)
            km_txt = (
                f"~{km_val:.0f} km (est.)"
                if es_estimado
                else f"{km_val:.1f} km"
            )
        else:
            km_txt = ""

    if not zona_km and db is not None and not retiro:
        try:
            from app.services.fletes_km_service import preview_flete_caso

            prev = preview_flete_caso(db, base)
            if prev.get("sucursal_cod"):
                sucursal_cod = str(prev["sucursal_cod"])
            if prev.get("zona_km"):
                zona_km = prev["zona_km"]
                if costo_ref is None:
                    costo_ref = por_zona.get(zona_km)
                es_estimado = bool(prev.get("estimado"))
                motivo_extra = prev.get("motivo")
                if prev.get("distance_km"):
                    km_val = float(prev["distance_km"])
                    km_txt = (
                        f"~{km_val:.0f} km (est.)"
                        if prev.get("estimado")
                        else f"{km_val:.1f} km"
                    )
        except Exception:
            pass
    elif len(por_zona) == 1:
        zona_km = next(iter(por_zona.keys()))
        costo_ref = next(iter(por_zona.values()))
    elif por_zona:
        costo_ref = min(por_zona.values())

    if zona_km and costo_ref is None and tarifas_grupo:
        if not por_zona:
            por_zona = _tarifas_zona_local(tarifas_grupo, tipo, medida)
        costo_ref = por_zona.get(zona_km)

    from app.services.alerta_ui import color_fila_fletes_local

    color_raw, motivo = _color_fila_fletes(
        retiro=retiro,
        abona_wamaro=bool(base.abona_wamaro),
        tiene_tarifa=bool(por_zona),
        zona_asignada=zona_km,
        sucursal_cod=sucursal_cod or None,
        es_estimado=es_estimado,
        motivo_extra=motivo_extra,
    )

    tarifa_txt = ""
    if por_zona:
        if zona_km and costo_ref is not None:
            tarifa_txt = f"{zona_km.replace('_', ' ')} — ${costo_ref:,.0f}".replace(",", ".")
        else:
            pmin = min(por_zona.values())
            pmax = max(por_zona.values())
            tarifa_txt = (
                f"Ref. ${pmin:,.0f}–${pmax:,.0f} (elegir zona km)".replace(",", ".")
            )

    color_ui, alertas_celdas = color_fila_fletes_local(
        retiro=retiro,
        tiene_tarifa=bool(por_zona),
        zona_asignada=zona_km,
        motivo=motivo,
    )
    if not alertas_celdas:
        color_ui = None
    elif zona_km and sucursal_cod and costo_ref is not None:
        alertas_celdas = [
            a for a in alertas_celdas if a.get("codigo") != "zona_km"
        ]
        if not alertas_celdas:
            color_ui = None

    fila: dict[str, Any] = {
        "_caso_id": key,
        "_origen_planilla": _origen_planilla(base.deposito, base.origen_cd),
        "_regla_color": color_ui,
        "_alerta_motivo": alertas_celdas[0]["motivo"] if alertas_celdas else None,
        "_alertas_celdas": alertas_celdas,
        "_regla_motivo": motivo,
        "_cantidad_renglones": len(lineas),
        "_por_zona_tarifa": por_zona,
        "_zona_km_asignada": zona_km,
        "_tipo_producto_flete": tipo,
        "_medida_flete": medida,
        "_pedido_cobro": interp.resumen(),
        "_pedido_advertencias": interp.advertencias,
        "FECHA": base.fecha_entrega or base.fecha_pedido,
        "FECHA PEDIDO": formato_fecha_grilla(base.fecha_pedido),
        "FECHA ENTREGA": formato_fecha_grilla(base.fecha_entrega),
        "REMITOS": texto_remito_grilla(base),
        "ESTADO REMITO": etiqueta_estado_remito(estado_remito_envio(base)),
        "_estado_remito": estado_remito_envio(base),
        "DESTINATARIO": base.razon_social,
        "LOCALIDAD": base.localidad,
        "PROVINCIA": base.provincia,
        "TRANSPORTE": base.transporte_nombre,
        "SUCURSAL": sucursal_cod,
        "KM": km_txt,
        "ZONA KM": zona_etiqueta(zona_km) if zona_km else ("—" if por_zona else ""),
        "BULTOS": bultos,
        "TARIFA REF": tarifa_txt,
        "total": costo_ref if zona_km and costo_ref else None,
        "LOGISTICA": costo_ref if zona_km else None,
        "SEGURO": settings.seguro_fijo if costo_ref and zona_km else None,
    }
    if zona_km and costo_ref:
        tmp = Envio()
        recalcular_costos_linea(tmp, costo_ref, aplicar_seguro=True)
        fila["total"] = tmp.costo_tarifario
        fila["SEGURO"] = settings.seguro_fijo
        fila["LOGISTICA"] = round_pesos((tmp.costo_tarifario or 0) - settings.seguro_fijo)

    if mapa_fletero:
        from app.services.remito_utils import normalizar_remito as _nr

        rn = _nr(base.remito) or clave_agrupacion_caso(base)
        info = mapa_fletero.get(rn or "")
        if info:
            fila["FLETERO"] = info.get("fletero_corto") or info.get("fletero") or ""
        else:
            fila["FLETERO"] = ""
    else:
        fila["FLETERO"] = ""

    return normalize_maestro_montos(fila)


def construir_fletes(
    envios: list[Envio],
    *,
    tarifas: list[Tarifa] | None = None,
    tarifario_ctx: Any = None,
    origen: str | None = None,
    sucursal_cod: str | None = None,
    distancias: dict[str, FleteDistancia] | None = None,
    db: Any = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    campo_fecha: str = "cualquiera",
    remito_estado: str = "todos",
    mapa_fletero: dict[str, dict[str, Any]] | None = None,
    fletero_corto: str | None = None,
) -> list[dict[str, Any]]:
    from app.services.casos_filtro_service import aplicar_filtros_lista_envios

    tarifas = tarifas or []
    candidatos = [e for e in envios if es_envio_mundo2(e)]
    candidatos = aplicar_filtros_lista_envios(
        candidatos,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        campo_fecha=campo_fecha,
    )
    filas: list[dict[str, Any]] = []

    for key, grupo in _agrupar_por_caso(candidatos).items():
        if not grupo_pasa_filtro_remito(grupo, remito_estado):
            continue
        if origen and _origen_planilla(grupo[0].deposito, grupo[0].origen_cd) != origen:
            continue
        rn = clave_agrupacion_caso(grupo[0]) or key
        dist = (distancias or {}).get(rn) if distancias else None
        dist = _buscar_distancia_caso(grupo[0], key, distancias, dist, db=db)
        fila = _fila_fletes_desde_grupo(
            key,
            grupo,
            tarifas,
            tarifario_ctx=tarifario_ctx,
            dist=dist,
            db=db,
            mapa_fletero=mapa_fletero,
        )
        if sucursal_cod and fila.get("SUCURSAL") != sucursal_cod.upper():
            continue
        if fletero_corto and fletero_corto.upper() != "TODOS":
            flet = (fila.get("FLETERO") or "").upper()
            if flet != fletero_corto.upper():
                continue
        filas.append(fila)

    filas.sort(
        key=lambda r: str(r.get("FECHA ENTREGA") or r.get("FECHA PEDIDO") or ""),
        reverse=True,
    )
    return filas


def stats_mundo2(
    envios: list[Envio],
    tarifas: list[Tarifa] | None = None,
    *,
    tarifario_ctx: Any = None,
    db: Any = None,
    distancias: dict[str, FleteDistancia] | None = None,
) -> dict[str, Any]:
    if db is not None and distancias is None:
        from app.services.fletes_km_service import preparar_contexto_km

        distancias = preparar_contexto_km(db, envios)
    filas = construir_fletes(
        envios,
        tarifas=tarifas,
        tarifario_ctx=tarifario_ctx,
        db=db,
        distancias=distancias,
    )
    por_color: dict[str, int] = defaultdict(int)
    for f in filas:
        por_color[f.get("_regla_color") or "sin_color"] += 1
    con_tarifa = sum(1 for f in filas if f.get("_por_zona_tarifa"))
    return {
        "casos_fletes": len(filas),
        "renglones_fletes": sum(1 for e in envios if es_envio_mundo2(e)),
        "con_km_calculado": sum(1 for f in filas if f.get("KM")),
        "con_tarifa_referencia": con_tarifa,
        "pendiente_zona_km": sum(
            1 for f in filas if f.get("_por_zona_tarifa") and not f.get("_zona_km_asignada")
        ),
        "por_color": dict(por_color),
    }
