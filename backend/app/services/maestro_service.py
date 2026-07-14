"""Armado del maestro WAMARO (formato manual del cliente) desde datos Tango."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import DEPOSITO_ORIGEN, clave_planilla_origen, settings
from app.models import Envio, Tarifa
from app.proveedores import caso_en_vista_proveedor, normalizar_proveedor
from app.transporte_reglas import (
    descripcion_canal_transporte,
    normalizar_transporte_cod,
)
from app.services.proveedor_service import etiqueta_proveedor_maestro
from app.services.fecha_utils import formato_fecha_grilla
from app.services.remito_maestro import (
    clave_agrupacion_caso,
    clave_agrupacion_interna,
    etiqueta_estado_remito,
    estado_remito_envio,
    texto_remito_grupo,
)
from app.services.remito_utils import es_remito_transito
from app.services.money_utils import normalize_maestro_montos, parse_money, round_pesos
from app.services.proveedor_service import (
    costo_referencia_linea_proveedor,
    cuenta_proveedores_tarifario,
)
from app.services.cobro_logistica_service import (
    calcular_cobro_grupo,
    calcular_cobro_pedido,
    cobro_red_y_provincia,
)
from app.services.alerta_ui import color_fila_maestro
from app.services.rules_service import costo_referencia_linea, es_amba_gba
from app.services.zona_maestro import zona_destino_maestro, zona_origen_maestro

MAESTRO_COLUMNAS = [
    "FECHA",
    "ENVIO",
    "REMITOS",
    "DESTINATARIO",
    "LOCALIDAD",
    "PROVINCIA",
    "SERVICIO",
    "TRANSPORTE",
    "OBLEA TRANSPORTE",
    "BULTOS",
    "PESO",
    "VOLUMEN",
    "PESO FACTURADO",
    "LOGISTICA",
    "SEGURO",
    "GESTION",
    "ADICIONAL",
    "VALOR DECLARADO",
    "PRECIO NETO",
    "ARTICULOS",
    "ZONA ORIGEN",
    "DESCRIPCION ZONA ORIGEN",
    "ZONA DESTINO",
    "DESCRIPCION ZONA DESTINO",
    "obs",
    "costo",
    "total",
    "dif",
    "suc",
]

COLUMNAS_CONTROL_MAESTRO = {"obs", "costo", "total", "dif", "suc", "LOGISTICA", "SEGURO", "GESTION", "PRECIO NETO"}


def _origen_planilla(deposito: str | None, origen_cd: str | None) -> str:
    """Delega en ``clave_planilla_origen`` (dep 12 = Hurlingham, dep 14 = Tortuguitas)."""
    return clave_planilla_origen(deposito, origen_cd)


def _zona_destino(
    provincia: str | None,
    localidad: str | None,
    excluir: bool,
    cp: str | None = None,
) -> tuple[str, str]:
    """Compat: delega en códigos legacy del maestro manual."""
    return zona_destino_maestro(
        provincia,
        localidad,
        es_amba_gba=excluir or es_amba_gba(provincia, localidad, cp),
    )


def _valor_declarado(leyenda: str | None) -> float | None:
    if not leyenda:
        return None
    m = re.search(r"[\d.,]+", leyenda.replace(" ", ""))
    if m:
        return parse_money(m.group(0))
    return None


def _linea_costo_sin_seguro(envio: Envio) -> float:
    ref = costo_referencia_linea(envio)
    if ref is None:
        return 0.0
    if ref > settings.seguro_fijo:
        return round(ref - settings.seguro_fijo, 2)
    return round(ref, 2)


def _agrupar_por_caso(envios: list[Envio]) -> dict[str, list[Envio]]:
    grupos: dict[str, list[Envio]] = defaultdict(list)
    for e in envios:
        if not clave_agrupacion_caso(e) and es_remito_transito(e.remito):
            continue
        key = clave_agrupacion_caso(e) or clave_agrupacion_interna(e)
        grupos[key].append(e)
    return grupos


def _bultos_grupo(lineas: list[Envio]) -> int:
    from app.services.bultos_service import bultos_grupo

    return bultos_grupo(lineas)


def _fila_maestro_desde_grupo(
    key: str,
    lineas: list[Envio],
    *,
    proveedor_vista: str | None = None,
    tarifas: list[Tarifa] | None = None,
    tarifario_ctx: Any = None,
    db: Any = None,
) -> dict[str, Any]:
    lineas = ordenar_lineas_caso(lineas)
    base = lineas[0]
    excluir = any(l.excluir_planilla for l in lineas)

    vista = normalizar_proveedor(proveedor_vista) if proveedor_vista else None
    tarifas_grupo = (
        tarifario_ctx.tarifas_para_grupo(lineas)
        if tarifario_ctx
        else tarifas
    )
    from app.services.fecha_utils import fecha_referencia_tarifa

    cobro = calcular_cobro_grupo(
        lineas, tarifas_grupo, proveedor_vista=vista, db=db
    )
    cobro_full = (
        calcular_cobro_grupo(lineas, tarifas_grupo, db=db)
        if vista
        else cobro
    )
    cobro_red, cobro_prov = cobro_red_y_provincia(cobro_full.tramos)
    es_cross = cobro_full.modo == "crossdock" and bool(cobro_red or cobro_prov)

    costo_lineas = cobro.logistica
    seguro = cobro.seguro
    gestion = cobro.gestion
    total_lineas = cobro.total

    if es_cross:
        logistica_grilla = cobro_prov if cobro_prov else costo_lineas
        red_monto = cobro_red or 0.0
        um_monto = cobro_prov or 0.0
        total_lineas = round(red_monto + um_monto + seguro + gestion, 2)
        total_proveedor = total_lineas
    else:
        logistica_grilla = costo_lineas
        total_proveedor = round(costo_lineas + seguro + gestion, 2)

    precio_neto = base.prefactura_proveedor
    if es_cross and precio_neto is None and cobro_red:
        precio_neto_grilla = cobro_red
    else:
        precio_neto_grilla = precio_neto

    dif = None
    if es_cross:
        ref_red = precio_neto if precio_neto is not None else cobro_red
        if ref_red is not None and cobro_red:
            dif = round(ref_red - cobro_red, 2)
    elif precio_neto is not None and total_proveedor > 0:
        dif = round(precio_neto - total_proveedor, 2)
    elif base.diferencia is not None:
        dif = base.diferencia

    from app.services.bultos_service import articulos_grupo_texto

    articulos = articulos_grupo_texto(lineas)

    obs_parts = []
    for l in lineas:
        if l.observaciones:
            obs_parts.append(l.observaciones)
        if l.regla_motivo and l.regla_motivo not in obs_parts:
            obs_parts.append(l.regla_motivo)
        if l.tipo_gestion or l.sub_tipo_gestion:
            pv = f"Postventa: {l.tipo_gestion or ''} {l.sub_tipo_gestion or ''}".strip()
            if pv not in obs_parts:
                obs_parts.append(pv)
    if cobro.cobro_cliente_cero and "cobro al cliente" not in " ".join(obs_parts).lower():
        obs_parts.append("Cobro al cliente: $0 — costo proveedor en LOGISTICA/SEGURO")
    elif excluir and not any("amba" in o.lower() for o in obs_parts):
        obs_parts.append("logistica en entregas amba")
    for pc in cobro.pedidos:
        res = pc.get("resumen")
        if res and res not in obs_parts:
            obs_parts.append(f"Cobro pedido: {res}")
        for adv in pc.get("advertencias") or []:
            if adv not in obs_parts:
                obs_parts.append(adv)

    zona, desc_zona = _zona_destino(base.provincia, base.localidad, excluir, base.cp)
    zo, desc_zo = zona_origen_maestro(base.deposito, base.origen_cd)
    bultos = _bultos_grupo(lineas)
    origen_key = _origen_planilla(base.deposito, base.origen_cd)

    from app.services.cedol_service import info_cedol_grupo

    cedol_info = info_cedol_grupo(lineas, tarifas_grupo)

    color_ui, alerta_motivo, alertas_celdas = color_fila_maestro(
        lineas,
        lineas_sin_tarifa=cobro.lineas_sin_tarifa or 0,
        total_logistica=costo_lineas or 0.0,
    )

    fila = {
        "_caso_id": key,
        "_origen_planilla": origen_key,
        "_regla_color": color_ui,
        "_alerta_motivo": alerta_motivo,
        "_alertas_celdas": alertas_celdas,
        "_regla_motivo": base.regla_motivo,
        "_cantidad_renglones": len(lineas),
        "_proveedor_tarifa": base.proveedor_tarifa,
        "_requiere_elegir_proveedor": base.requiere_elegir_proveedor,
        "_proveedores_candidatos": base.proveedores_candidatos,
        "_cobro_modo": cobro_full.modo if es_cross else cobro.modo,
        "_cobro_tramos": cobro_full.tramos if es_cross else cobro.tramos,
        "_es_crossdock": es_cross,
        "_cobro_sin_tarifa": cobro.lineas_sin_tarifa,
        "_pedidos_cobro": cobro.pedidos,
        "_tarifario_fecha_ref": fecha_referencia_tarifa(base),
        "_tarifario_versiones": (
            tarifario_ctx.snapshot_versiones(fecha_referencia_tarifa(base))
            if tarifario_ctx
            else {}
        ),
        "_transporte_cod": base.transporte_cod,
        "_cedol_auto": cedol_info.get("cedol_auto"),
        "_cedol_manual": cedol_info.get("cedol_manual"),
        "NRO TRANSP": normalizar_transporte_cod(
            base.transporte_cod, base.transporte_nombre
        )
        or base.transporte_cod
        or "",
        "CANAL": descripcion_canal_transporte(
            base.transporte_cod, base.transporte_nombre
        ),
        "FECHA": base.fecha_entrega or base.fecha_pedido,
        "FECHA PEDIDO": formato_fecha_grilla(base.fecha_pedido),
        "FECHA ENTREGA": formato_fecha_grilla(base.fecha_entrega),
        "ESTADO PEDIDO": (base.estado_pedido or "").strip(),
        "ENVIO": base.nro_pedido,
        "REMITOS": texto_remito_grupo(lineas),
        "ESTADO REMITO": etiqueta_estado_remito(estado_remito_envio(base)),
        "_estado_remito": estado_remito_envio(base),
        "DESTINATARIO": base.razon_social,
        "LOCALIDAD": base.localidad,
        "PROVINCIA": base.provincia,
        "SERVICIO": "LOGISTICA ORIGEN ST",
        "TRANSPORTE": (base.transporte_nombre or "").upper(),
        "OBLEA TRANSPORTE": None,
        "PROVEEDOR": etiqueta_proveedor_maestro(base),
        "CEDOL": cedol_info.get("cedol_efectivo") or "",
        "BULTOS": bultos,
        "PESO": 1 if bultos else 0,
        "VOLUMEN": round(sum(l.m3 or 0 for l in lineas), 2),
        "PESO FACTURADO": None,
        "LOGISTICA": round_pesos(logistica_grilla) if logistica_grilla else 0.0,
        "COBRO RED": round_pesos(cobro_red) if cobro_red else None,
        "COBRO PROVINCIA": round_pesos(cobro_prov) if cobro_prov else None,
        "SEGURO": round_pesos(seguro) if (logistica_grilla or es_cross) else 0.0,
        "GESTION": round_pesos(gestion) if gestion else 0.0,
        "ADICIONAL": 0.0,
        "VALOR DECLARADO": round_pesos(_valor_declarado(base.leyenda_5)),
        "PRECIO NETO": round_pesos(precio_neto_grilla),
        "ARTICULOS": articulos,
        "ZONA ORIGEN": zo,
        "DESCRIPCION ZONA ORIGEN": desc_zo,
        "ZONA DESTINO": zona,
        "DESCRIPCION ZONA DESTINO": desc_zona,
        "obs": " | ".join(obs_parts) if obs_parts else None,
        "costo": round_pesos(logistica_grilla) if logistica_grilla else 0.0,
        "_total_proveedor": round_pesos(total_proveedor) if total_proveedor else 0.0,
        "total": round_pesos(total_lineas),
        "dif": round_pesos(dif),
        "suc": base.sucursal_cc,
    }
    return normalize_maestro_montos(fila)


def insertar_marcadores_cambio_tarifario(filas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Inserta filas rojas cuando cambia la versión de tarifario entre casos contiguos
    (lista ordenada por fecha descendente: arriba el más nuevo).
    """
    if len(filas) < 2:
        return filas

    out: list[dict[str, Any]] = []
    prev_snap: dict[str, int] = filas[0].get("_tarifario_versiones") or {}
    out.append(filas[0])

    for fila in filas[1:]:
        snap = fila.get("_tarifario_versiones") or {}
        if snap and prev_snap and snap != prev_snap:
            cambios = []
            for prov in sorted(set(snap) | set(prev_snap)):
                v_nuevo = prev_snap.get(prov)
                v_viejo = snap.get(prov)
                if v_nuevo != v_viejo:
                    cambios.append(f"{prov}: v{v_viejo} → v{v_nuevo}")
            corte = fila.get("_tarifario_fecha_ref") or fila.get("FECHA") or ""
            detalle = " · ".join(cambios) if cambios else "Cambio de versión"
            out.append(
                {
                    "_es_marcador_tarifario": True,
                    "_regla_color": "alerta",
                    "_caso_id": "",
                    "FECHA": corte,
                    "FECHA ENTREGA": formato_fecha_grilla(str(corte)) if corte else "",
                    "REMITOS": "── CAMBIO TARIFARIO ──",
                    "DESTINATARIO": detalle,
                    "PROVEEDOR": "Tarifario anterior ↓",
                    "obs": (
                        "Línea de corte: casos **arriba** usan tarifario más nuevo; "
                        f"**abajo** el anterior. {detalle}"
                    ),
                }
            )
        out.append(fila)
        if snap:
            prev_snap = snap

    return out


def _grupo_coincide_busqueda(grupo: list[Envio], q: str) -> bool:
    needle = q.strip().upper()
    if not needle:
        return True
    for linea in grupo:
        for val in (
            linea.remito,
            linea.remito_norm,
            linea.nro_pedido,
            linea.razon_social,
            linea.localidad,
            linea.provincia,
            linea.proveedor_tarifa,
            linea.transporte_nombre,
            linea.cedol_codigo,
        ):
            if val and needle in str(val).upper():
                return True
    return False


def _grupo_tiene_alerta_maestro(grupo: list[Envio]) -> bool:
    from app.services.alerta_ui import alertas_maestro_grilla
    from app.services.costo_conceptos import debe_calcular_costo_proveedor

    lineas_sin_tarifa = sum(
        1
        for l in grupo
        if debe_calcular_costo_proveedor(l) and not (l.costo_tarifario or 0)
    )
    total_log = sum(l.costo_tarifario or 0 for l in grupo)
    return bool(
        alertas_maestro_grilla(
            grupo,
            lineas_sin_tarifa=lineas_sin_tarifa,
            total_logistica=total_log,
        )
    )


def _grupo_pasa_filtros_ui(
    grupo: list[Envio],
    *,
    solo_alerta: bool = False,
    solo_macheo: bool = False,
    solo_con_dif: bool = False,
) -> bool:
    base = grupo[0]
    if solo_macheo and not base.prefactura_proveedor:
        return False
    if solo_con_dif:
        diff = base.diferencia if base.diferencia is not None else 0.0
        if abs(diff) <= 0.01:
            return False
    if solo_alerta and not _grupo_tiene_alerta_maestro(grupo):
        return False
    return True


def _grupos_maestro_ordenados(
    envios: list[Envio],
    *,
    origen: str | None = None,
    incluir_excluidos: bool = True,
    proveedor: str | None = None,
    solo_pendiente_proveedor: bool = False,
    tarifas: list[Tarifa] | None = None,
    tarifario_ctx: Any = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    campo_fecha: str = "cualquiera",
    remito_estado: str = "todos",
    q: str | None = None,
    solo_alerta: bool = False,
    solo_macheo: bool = False,
    solo_con_dif: bool = False,
) -> list[tuple[str, list[Envio]]]:
    from app.services.casos_filtro_service import aplicar_filtros_lista_envios
    from app.services.remito_maestro import grupo_pasa_filtro_remito

    if not incluir_excluidos:
        envios = [e for e in envios if not e.excluir_planilla]

    envios = aplicar_filtros_lista_envios(
        envios,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        campo_fecha=campo_fecha,
    )

    vista = normalizar_proveedor(proveedor) if proveedor else None
    candidatos: list[tuple[str, list[Envio], str]] = []

    for key, grupo in _agrupar_por_caso(envios).items():
        base = grupo[0]
        if not grupo_pasa_filtro_remito(grupo, remito_estado):
            continue
        if q and not _grupo_coincide_busqueda(grupo, q):
            continue
        if not _grupo_pasa_filtros_ui(
            grupo,
            solo_alerta=solo_alerta,
            solo_macheo=solo_macheo,
            solo_con_dif=solo_con_dif,
        ):
            continue
        if solo_pendiente_proveedor:
            if not any(l.requiere_elegir_proveedor for l in grupo):
                continue
            try:
                raw_cand = base.proveedores_candidatos
                cand = json.loads(raw_cand) if raw_cand else []
            except json.JSONDecodeError:
                cand = []
            from app.services.proveedor_service import es_crossdock_operativo

            t_chk = (
                tarifario_ctx.tarifas_para_grupo(grupo)
                if tarifario_ctx
                else tarifas
            )
            if es_crossdock_operativo(base, t_chk):
                continue
            if cuenta_proveedores_tarifario(
                cand if isinstance(cand, list) else []
            ) < 2:
                continue
        elif vista:
            if not caso_en_vista_proveedor(
                vista,
                base.provincia,
                base.localidad,
                transporte_cod=base.transporte_cod,
                transporte_nombre=base.transporte_nombre,
                proveedor_asignado=base.proveedor_tarifa,
            ):
                continue

        origen_key = _origen_planilla(base.deposito, base.origen_cd)
        if origen and origen_key != origen:
            continue

        fecha_ord = str(base.fecha_entrega or base.fecha_pedido or "")
        candidatos.append((key, grupo, fecha_ord))

    candidatos.sort(key=lambda x: x[2], reverse=True)
    return [(k, g) for k, g, _ in candidatos]


def construir_maestro(
    envios: list[Envio],
    *,
    origen: str | None = None,
    incluir_excluidos: bool = True,
    proveedor: str | None = None,
    solo_pendiente_proveedor: bool = False,
    tarifas: list[Tarifa] | None = None,
    tarifario_ctx: Any = None,
    db: Any = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    campo_fecha: str = "cualquiera",
    remito_estado: str = "todos",
    q: str | None = None,
    solo_alerta: bool = False,
    solo_macheo: bool = False,
    solo_con_dif: bool = False,
    page: int | None = None,
    page_size: int | None = None,
) -> list[dict[str, Any]]:
    grupos = _grupos_maestro_ordenados(
        envios,
        origen=origen,
        incluir_excluidos=incluir_excluidos,
        proveedor=proveedor,
        solo_pendiente_proveedor=solo_pendiente_proveedor,
        tarifas=tarifas,
        tarifario_ctx=tarifario_ctx,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        campo_fecha=campo_fecha,
        remito_estado=remito_estado,
        q=q,
        solo_alerta=solo_alerta,
        solo_macheo=solo_macheo,
        solo_con_dif=solo_con_dif,
    )

    if page is not None and page_size is not None:
        start = max(0, (page - 1) * page_size)
        grupos = grupos[start : start + page_size]

    vista = normalizar_proveedor(proveedor) if proveedor else None
    filas = [
        _fila_maestro_desde_grupo(
            key,
            grupo,
            proveedor_vista=vista,
            tarifas=tarifas,
            tarifario_ctx=tarifario_ctx,
            db=db,
        )
        for key, grupo in grupos
    ]

    if tarifario_ctx and page is None:
        filas = insertar_marcadores_cambio_tarifario(filas)
    return filas


def _kwargs_filtro_grupos(**kwargs: Any) -> dict[str, Any]:
    omit = {"db", "tarifario_ctx", "tarifas", "page", "page_size"}
    return {k: v for k, v in kwargs.items() if k not in omit}


def contar_grupos_maestro(envios: list[Envio], **kwargs: Any) -> int:
    return len(_grupos_maestro_ordenados(envios, **_kwargs_filtro_grupos(**kwargs)))


def construir_maestro_pagina(
    envios: list[Envio],
    *,
    page: int = 1,
    page_size: int = 150,
    **kwargs: Any,
) -> tuple[list[dict[str, Any]], int]:
    page = max(1, page)
    page_size = max(1, min(page_size, 500))
    filtros = _kwargs_filtro_grupos(**kwargs)
    total = contar_grupos_maestro(envios, **filtros)
    filas = construir_maestro(
        envios,
        page=page,
        page_size=page_size,
        **filtros,
        db=kwargs.get("db"),
        tarifario_ctx=kwargs.get("tarifario_ctx"),
        tarifas=kwargs.get("tarifas"),
    )
    return filas, total


def _prioridad_linea_caso(l: Envio) -> tuple[int, int, int, int]:
    """Preferir línea con proveedor, transporte y fecha (evita renglones Tango vacíos al frente)."""
    prov = normalizar_proveedor(l.proveedor_tarifa)
    return (
        0 if prov else 1,
        0 if (l.transporte_cod or l.transporte_nombre) else 1,
        0 if (l.fecha_entrega_d or l.fecha_entrega) else 1,
        l.id or 0,
    )


def ordenar_lineas_caso(lineas: list[Envio]) -> list[Envio]:
    return sorted(lineas, key=_prioridad_linea_caso)


def obtener_lineas_caso(
    envios: list[Envio],
    caso_id: str,
) -> tuple[str, list[Envio]] | None:
    grupos = _agrupar_por_caso(envios)
    lineas = grupos.get(caso_id)
    key = caso_id
    if not lineas:
        for k, g in grupos.items():
            if any((l.remito or "") == caso_id for l in g):
                lineas = g
                key = k
                break
    if not lineas:
        return None
    return key, ordenar_lineas_caso(lineas)


def detalle_caso(
    envios: list[Envio],
    caso_id: str,
    db: Session | None = None,
) -> dict[str, Any] | None:
    found = obtener_lineas_caso(envios, caso_id)
    if not found:
        return None
    caso_id, lineas = found

    from app.services.bultos_service import bultos_de_linea, etiqueta_cantidad_logistica
    from app.services.pedido_cobro_service import clasificar_linea

    renglones = []
    for l in lineas:
        raw = {}
        if l.raw_json:
            try:
                raw = json.loads(l.raw_json)
            except json.JSONDecodeError:
                raw = {}
        renglones.append(
            {
                "id": l.id,
                "remito": l.remito,
                "nro_pedido": l.nro_pedido,
                "cod_articulo": l.cod_articulo,
                "descripcion": l.descripcion,
                "cantidad": l.cantidad,
                "tipo_linea": clasificar_linea(l).tipo_linea,
                "bultos": bultos_de_linea(l),
                "cantidad_display": etiqueta_cantidad_logistica(l),
                "fecha_pedido": l.fecha_pedido,
                "fecha_entrega": l.fecha_entrega,
                "domicilio": l.domicilio,
                "localidad": l.localidad,
                "provincia": l.provincia,
                "cp": l.cp,
                "transporte": l.transporte_nombre,
                "clasificacion": l.clasificacion,
                "estado_pedido": l.estado_pedido,
                "leyenda_5": l.leyenda_5,
                "vendedor": l.vendedor,
                "m3": l.m3,
                "tipo_gestion": l.tipo_gestion,
                "sub_tipo_gestion": l.sub_tipo_gestion,
                "regla_postventa": l.regla_postventa,
                "motivo_postventa": l.motivo_postventa,
                "costo_tarifario": l.costo_tarifario,
                "costo_total": l.costo_total,
                "diferencia": l.diferencia,
                "prefactura_proveedor": l.prefactura_proveedor,
                "proveedor_tarifa": l.proveedor_tarifa,
                "sucursal_cc": l.sucursal_cc,
                "origen_cd": l.origen_cd,
                "deposito": l.deposito,
                "razon_social": l.razon_social,
                "transporte_cod": l.transporte_cod,
                "observaciones": l.observaciones,
                "excluir_planilla": l.excluir_planilla,
                "alerta_clickpack": l.alerta_clickpack,
                "abona_wamaro": l.abona_wamaro,
                "entrega_cliente_sospechosa": l.entrega_cliente_sospechosa,
                "requiere_elegir_proveedor": l.requiere_elegir_proveedor,
                "cedol_manual": l.cedol_manual,
                "cedol_codigo": l.cedol_codigo,
                "regla_color": l.regla_color,
                "regla_motivo": l.regla_motivo,
                "tango_completo": raw,
            }
        )

    tarifario_ctx = None
    tarifas_db = None
    if db is not None:
        from app.services.tarifario_version_service import TarifarioContext

        tarifario_ctx = TarifarioContext(db)
        tarifas_db = tarifario_ctx.tarifas_para_grupo(lineas)
    result: dict[str, Any] = {
        "caso_id": caso_id,
        "maestro": _fila_maestro_desde_grupo(
            caso_id, lineas, tarifas=tarifas_db, db=db
        ),
        "renglones": renglones,
        "cantidad_renglones": len(renglones),
    }
    if db is not None:
        from app.services.cobro_logistica_service import calcular_cobro_linea
        from app.services.fletes_km_service import info_distancia_sucursal_destino

        result["distancia_sucursal"] = info_distancia_sucursal_destino(
            db, lineas[0], intentar_calculo=True
        )
        from app.services.pedido_cobro_service import interpretar_pedido

        cobro_grupo = calcular_cobro_grupo(lineas, tarifas_db, db=db)
        result["cobro_pedidos"] = cobro_grupo.pedidos
        interp = interpretar_pedido(lineas)
        result["cobro_renglones"] = [
            {
                "tipo_linea": r.tipo_linea,
                "descripcion": r.envio.descripcion,
                "cantidad": r.cantidad,
                "bultos": bultos_de_linea(r.envio),
                "cantidad_display": etiqueta_cantidad_logistica(r.envio),
            }
            for r in interp.renglones
        ]
        c = calcular_cobro_pedido(lineas, tarifas_db or [], db=db)
        result["cobro_unidad"] = {
            "modo": c.modo,
            "logistica": c.logistica,
            "resumen": interp.resumen(),
            "tramos": [
                {"proveedor": t.proveedor, "monto": t.monto, "nota": t.nota}
                for t in c.tramos
            ],
        }
        from app.services.cedol_service import info_cedol_grupo, listar_cedoles_tarifario

        cedol_info = info_cedol_grupo(lineas, tarifas_db)
        result["cedol"] = cedol_info
        if cedol_info.get("aplica") and cedol_info.get("proveedor"):
            result["cedol_opciones"] = listar_cedoles_tarifario(
                tarifas_db or [], cedol_info["proveedor"]
            )
        from app.services.cross_seguimiento_service import info_cross_caso

        cross_info = info_cross_caso(lineas, db)
        if cross_info:
            result["cross_seguimiento"] = cross_info
    return result
