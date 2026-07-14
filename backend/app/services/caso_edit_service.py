"""Edición manual de casos del maestro (cabecera + renglones)."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.models import Envio
from app.services.fecha_utils import parse_fecha_tango
from app.services.maestro_service import obtener_lineas_caso
from app.services.remito_utils import normalizar_remito


# Campos de cabecera: se copian a todas las líneas del grupo.
CAMPOS_CASO_COMPARTIDOS: frozenset[str] = frozenset(
    {
        "razon_social",
        "domicilio",
        "localidad",
        "provincia",
        "cp",
        "fecha_pedido",
        "fecha_entrega",
        "transporte_cod",
        "transporte_nombre",
        "estado_pedido",
        "clasificacion",
        "origen_cd",
        "deposito",
        "vendedor",
        "observaciones",
        "sucursal_cc",
        "leyenda_5",
        "proveedor_tarifa",
        "prefactura_proveedor",
        "remito",
    }
)

# Campos editables por renglón (además de los compartidos si se envían por línea).
CAMPOS_RENGLON: frozenset[str] = frozenset(
    {
        "nro_pedido",
        "cod_articulo",
        "descripcion",
        "cantidad",
        "m3",
        "fecha_pedido",
        "fecha_entrega",
        "razon_social",
        "domicilio",
        "localidad",
        "provincia",
        "cp",
        "deposito",
        "origen_cd",
        "transporte_cod",
        "transporte_nombre",
        "clasificacion",
        "estado_pedido",
        "leyenda_5",
        "vendedor",
        "observaciones",
        "costo_total",
        "costo_tarifario",
        "diferencia",
        "sucursal_cc",
        "prefactura_proveedor",
        "tipo_gestion",
        "sub_tipo_gestion",
        "motivo_postventa",
        "regla_postventa",
        "macheo_estado",
        "proveedor_tarifa",
        "cedol_codigo",
        "regla_motivo",
        "regla_color",
        "excluir_planilla",
        "alerta_clickpack",
        "abona_wamaro",
        "entrega_cliente_sospechosa",
        "requiere_elegir_proveedor",
        "cedol_manual",
    }
)

_FLOAT_FIELDS = frozenset(
    {
        "cantidad",
        "m3",
        "costo_total",
        "costo_tarifario",
        "diferencia",
        "prefactura_proveedor",
    }
)
_BOOL_FIELDS = frozenset(
    {
        "excluir_planilla",
        "alerta_clickpack",
        "abona_wamaro",
        "entrega_cliente_sospechosa",
        "requiere_elegir_proveedor",
        "cedol_manual",
    }
)


def _fmt_fecha_display(d: date | None, original: str | None) -> str | None:
    if d is None:
        return (original or "").strip() or None
    return d.strftime("%d/%m/%Y")


def _coerce_campo(campo: str, valor: Any) -> Any:
    if campo in _BOOL_FIELDS:
        if isinstance(valor, bool):
            return valor
        if valor is None or valor == "":
            return False
        return str(valor).strip().lower() in ("1", "true", "si", "sí", "yes")
    if campo in _FLOAT_FIELDS:
        if valor is None or valor == "":
            return None
        return float(valor)
    if valor is None:
        return None
    if isinstance(valor, str):
        txt = valor.strip()
        return txt or None
    return valor


def _aplicar_fechas_payload(payload: dict[str, Any]) -> tuple[date | None | object, date | None | object]:
    """Devuelve fechas parseadas; usa sentinel object si el campo no viene."""
    miss = object()
    fe_pedido: date | None | object = miss
    fe_entrega: date | None | object = miss
    if "fecha_pedido" in payload:
        raw = payload.get("fecha_pedido")
        if raw is None or raw == "":
            payload["fecha_pedido"] = None
            fe_pedido = None
        else:
            fe_pedido = parse_fecha_tango(str(raw))
            if isinstance(fe_pedido, date):
                payload["fecha_pedido"] = _fmt_fecha_display(fe_pedido, str(raw))
    if "fecha_entrega" in payload:
        raw = payload.get("fecha_entrega")
        if raw is None or raw == "":
            payload["fecha_entrega"] = None
            fe_entrega = None
        else:
            fe_entrega = parse_fecha_tango(str(raw))
            if isinstance(fe_entrega, date):
                payload["fecha_entrega"] = _fmt_fecha_display(fe_entrega, str(raw))
    return fe_pedido, fe_entrega


def _set_attrs_envio(
    linea: Envio,
    payload: dict[str, Any],
    *,
    remito_norm: str | None = None,
    fe_pedido: Any = None,
    fe_entrega: Any = None,
    miss: object | None = None,
) -> None:
    _miss = miss if miss is not None else object()
    for campo, valor in payload.items():
        if campo == "remito":
            linea.remito = valor
            if remito_norm is not None:
                linea.remito_norm = remito_norm
            continue
        if campo == "tango_completo":
            continue
        setattr(linea, campo, valor)
    if fe_pedido is not _miss and "fecha_pedido" in payload:
        linea.fecha_pedido_d = fe_pedido  # type: ignore[assignment]
    if fe_entrega is not _miss and "fecha_entrega" in payload:
        linea.fecha_entrega_d = fe_entrega  # type: ignore[assignment]


def _aplicar_tango_completo(linea: Envio, tango: dict[str, Any] | None) -> None:
    if tango is None:
        return
    if not isinstance(tango, dict):
        raise ValueError("tango_completo debe ser un objeto JSON")
    linea.raw_json = json.dumps(tango, ensure_ascii=False, default=str)
    # Sincroniza claves que coinciden con columnas del modelo.
    for campo in CAMPOS_RENGLON | CAMPOS_CASO_COMPARTIDOS:
        if campo not in tango:
            continue
        if campo in ("excluir_planilla", "alerta_clickpack", "abona_wamaro"):
            continue
        try:
            setattr(linea, campo, _coerce_campo(campo, tango.get(campo)))
        except (TypeError, ValueError):
            continue
    if "remito" in tango:
        txt = str(tango.get("remito") or "").strip()
        linea.remito = txt or None
        if txt:
            linea.remito_norm = normalizar_remito(txt)


def actualizar_caso(
    db: Session,
    caso_id: str,
    cambios: dict[str, Any],
    *,
    renglones: list[dict[str, Any]] | None = None,
    recalcular: bool = True,
) -> dict[str, Any]:
    """
    Actualiza cabecera (todas las líneas) y/o campos por renglón.
    """
    envios = list(db.query(Envio).all())
    found = obtener_lineas_caso(envios, caso_id)
    if not found:
        raise ValueError("Caso no encontrado")
    key, lineas = found
    por_id = {int(e.id): e for e in lineas}

    miss = object()
    payload: dict[str, Any] = {}
    for k, v in cambios.items():
        if k in CAMPOS_CASO_COMPARTIDOS:
            payload[k] = _coerce_campo(k, v)

    campos_cabecera = sorted(payload.keys())
    remito_norm_nuevo: str | None = None
    fe_pedido: Any = miss
    fe_entrega: Any = miss

    if payload:
        fe_pedido, fe_entrega = _aplicar_fechas_payload(payload)
        if "remito" in payload:
            remito_txt = str(payload.get("remito") or "").strip()
            payload["remito"] = remito_txt or None
            remito_norm_nuevo = normalizar_remito(remito_txt) if remito_txt else None
        if "proveedor_tarifa" in payload:
            p = str(payload.get("proveedor_tarifa") or "").strip().upper()
            payload["proveedor_tarifa"] = p or None
            for linea in lineas:
                linea.requiere_elegir_proveedor = False
        for linea in lineas:
            _set_attrs_envio(
                linea,
                payload,
                remito_norm=remito_norm_nuevo,
                fe_pedido=fe_pedido,
                fe_entrega=fe_entrega,
                miss=miss,
            )

    renglones_ok: list[int] = []
    for item in renglones or []:
        rid = item.get("id")
        if rid is None:
            raise ValueError("Cada renglón requiere id")
        rid_i = int(rid)
        linea = por_id.get(rid_i)
        if linea is None:
            raise ValueError(f"Renglón {rid_i} no pertenece al caso")
        ren_payload: dict[str, Any] = {}
        for k, v in item.items():
            if k in CAMPOS_RENGLON and k != "id":
                ren_payload[k] = _coerce_campo(k, v)
        fe_p, fe_e = _aplicar_fechas_payload(ren_payload)
        if "proveedor_tarifa" in ren_payload:
            p = str(ren_payload.get("proveedor_tarifa") or "").strip().upper()
            ren_payload["proveedor_tarifa"] = p or None
            linea.requiere_elegir_proveedor = False
        if ren_payload:
            _set_attrs_envio(
                linea,
                ren_payload,
                fe_pedido=fe_p,
                fe_entrega=fe_e,
                miss=miss,
            )
        if "tango_completo" in item:
            _aplicar_tango_completo(linea, item.get("tango_completo"))
        if ren_payload or "tango_completo" in item:
            renglones_ok.append(rid_i)

    if not campos_cabecera and not renglones_ok:
        raise ValueError("No hay cambios para aplicar")

    db.flush()

    recalc_info: dict[str, Any] = {}
    if recalcular:
        from app.services.proveedor_service import precio_tarifa_linea
        from app.services.rules_service import (
            aplicar_reglas_envio,
            recalcular_costos_linea,
            recalcular_grupo,
        )
        from app.services.tarifario_version_service import TarifarioContext

        ctx = TarifarioContext(db)
        tarifas = ctx.tarifas_para_grupo(lineas)
        for linea in lineas:
            aplicar_reglas_envio(linea, preservar_postventa=True)
            prov = (linea.proveedor_tarifa or "").strip().upper() or None
            if prov:
                precio = precio_tarifa_linea(linea, tarifas, prov)
                recalcular_costos_linea(linea, precio)
        recalcular_grupo(lineas)
        recalc_info["recalculado"] = True

    db.commit()
    for linea in lineas:
        db.refresh(linea)

    nuevo_id = remito_norm_nuevo or key
    return {
        "caso_id": nuevo_id,
        "caso_id_anterior": key,
        "lineas_actualizadas": len(lineas) if campos_cabecera else len(renglones_ok),
        "campos": campos_cabecera,
        "renglones_actualizados": renglones_ok,
        **recalc_info,
    }
