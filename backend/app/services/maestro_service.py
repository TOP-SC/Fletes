"""Armado del maestro WAMARO (formato manual del cliente) desde datos Tango."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import DEPOSITO_ORIGEN, settings
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
    dep = (deposito or "").strip()
    if dep == "12" or (origen_cd and "LIMANSKY" in origen_cd.upper()):
        return "sa"
    if dep == "14" or (origen_cd and "TORTUGUITAS" in origen_cd.upper()):
        return "tortuguitas"
    if origen_cd and "LIMANSKY" in origen_cd.upper():
        return "sa"
    return "tortuguitas"


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
    """Suma cantidades Tango; si vinieron en 0 por columna mal mapeada, cuenta renglones."""
    total = int(sum(l.cantidad or 0 for l in lineas))
    if total > 0:
        return total
    return sum(1 for l in lineas if l.descripcion or l.cod_articulo)


def _fila_maestro_desde_grupo(
    key: str,
    lineas: list[Envio],
    *,
    proveedor_vista: str | None = None,
    tarifas: list[Tarifa] | None = None,
    tarifario_ctx: Any = None,
    db: Any = None,
) -> dict[str, Any]:
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
    costo_lineas = cobro.logistica
    seguro = cobro.seguro
    total_lineas = cobro.total
    gestion = cobro.gestion
    cobro_red, cobro_prov = cobro_red_y_provincia(cobro.tramos)

    total_proveedor = round(costo_lineas + seguro + gestion, 2)

    precio_neto = base.prefactura_proveedor
    if precio_neto is None and total_proveedor > 0:
        precio_neto = None

    dif = None
    if precio_neto is not None and total_proveedor > 0:
        dif = round(precio_neto - total_proveedor, 2)
    elif base.diferencia is not None:
        dif = base.diferencia

    articulos = " | ".join(
        f"{(l.descripcion or l.cod_articulo or '').strip()} x{int(l.cantidad or 1)}"
        for l in lineas
        if l.descripcion or l.cod_articulo
    )

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
        "_cobro_modo": cobro.modo,
        "_cobro_tramos": cobro.tramos,
        "_cobro_sin_tarifa": cobro.lineas_sin_tarifa,
        "_pedidos_cobro": cobro.pedidos,
        "_tarifario_fecha_ref": fecha_referencia_tarifa(base),
        "_tarifario_versiones": (
            tarifario_ctx.snapshot_versiones(fecha_referencia_tarifa(base))
            if tarifario_ctx
            else {}
        ),
        "_transporte_cod": base.transporte_cod,
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
        "BULTOS": bultos,
        "PESO": 1 if bultos else 0,
        "VOLUMEN": round(sum(l.m3 or 0 for l in lineas), 2),
        "PESO FACTURADO": None,
        "LOGISTICA": round_pesos(costo_lineas) if costo_lineas else 0.0,
        "COBRO RED": round_pesos(cobro_red) if cobro_red else None,
        "COBRO PROVINCIA": round_pesos(cobro_prov) if cobro_prov else None,
        "SEGURO": round_pesos(seguro) if costo_lineas else 0.0,
        "GESTION": round_pesos(gestion) if gestion else 0.0,
        "ADICIONAL": 0.0,
        "VALOR DECLARADO": round_pesos(_valor_declarado(base.leyenda_5)),
        "PRECIO NETO": round_pesos(precio_neto),
        "ARTICULOS": articulos,
        "ZONA ORIGEN": zo,
        "DESCRIPCION ZONA ORIGEN": desc_zo,
        "ZONA DESTINO": zona,
        "DESCRIPCION ZONA DESTINO": desc_zona,
        "obs": " | ".join(obs_parts) if obs_parts else None,
        "costo": round_pesos(costo_lineas) if costo_lineas else 0.0,
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
) -> list[dict[str, Any]]:
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

    filas = []
    for key, grupo in _agrupar_por_caso(envios).items():
        base = grupo[0]
        if not grupo_pasa_filtro_remito(grupo, remito_estado):
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

        fila = _fila_maestro_desde_grupo(
            key,
            grupo,
            proveedor_vista=vista,
            tarifas=tarifas,
            tarifario_ctx=tarifario_ctx,
            db=db,
        )
        if origen and fila["_origen_planilla"] != origen:
            continue
        filas.append(fila)

    filas.sort(key=lambda r: str(r.get("FECHA") or ""), reverse=True)
    if tarifario_ctx:
        filas = insertar_marcadores_cambio_tarifario(filas)
    return filas


def detalle_caso(
    envios: list[Envio],
    caso_id: str,
    db: Session | None = None,
) -> dict[str, Any] | None:
    grupos = _agrupar_por_caso(envios)
    lineas = grupos.get(caso_id)
    if not lineas:
        for key, g in grupos.items():
            if any((l.remito or "") == caso_id for l in g):
                lineas = g
                caso_id = key
                break
    if not lineas:
        return None

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
                "observaciones": l.observaciones,
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

        result["distancia_sucursal"] = info_distancia_sucursal_destino(db, lineas[0])
        from app.services.pedido_cobro_service import interpretar_pedido

        cobro_grupo = calcular_cobro_grupo(lineas, tarifas_db, db=db)
        result["cobro_pedidos"] = cobro_grupo.pedidos
        interp = interpretar_pedido(lineas)
        result["cobro_renglones"] = [
            {
                "tipo_linea": r.tipo_linea,
                "descripcion": r.envio.descripcion,
                "cantidad": r.cantidad,
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
    return result
