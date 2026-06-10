"""
Alertas operativas en grillas: fila roja + luces por columna afectada.
"""

from __future__ import annotations

from typing import Any, TypedDict

from app.models import Envio
from app.proveedores import normalizar_proveedor
from app.services.costo_conceptos import debe_calcular_costo_proveedor, es_amba_gba_envio
from app.services.remito_maestro import estado_remito_envio, remito_oficial_envio
from app.transporte_reglas import (
    COD_CROSSDOCKING,
    COD_ENTREGA_CLIENTE,
    COD_EXPRESO_CLICPAQ,
    normalizar_transporte_cod,
    resolver_circuito_logistico,
)


class AlertaGrilla(TypedDict):
    codigo: str
    columnas: list[str]
    motivo: str


def _requiere_remito_cd(envio: Envio) -> bool:
    """
    Remito oficial R/RAR del CD: obligatorio en red CLICPAQ (51, 82, 40 interior).
    No aplica en 40 AMBA/GBA (flete sucursal local) ni en retiros/excluidos.
    """
    if envio.excluir_planilla:
        return False
    cod = normalizar_transporte_cod(envio.transporte_cod, envio.transporte_nombre)
    if cod in (COD_EXPRESO_CLICPAQ, COD_CROSSDOCKING):
        return True
    if cod == COD_ENTREGA_CLIENTE:
        circuito = resolver_circuito_logistico(
            envio.transporte_cod,
            envio.transporte_nombre,
            provincia=envio.provincia,
            localidad=envio.localidad,
            cp=envio.cp,
        )
        return circuito["modo"] == "red_clicpaq"
    return False


def _falta_remito_operativo(envio: Envio) -> bool:
    if remito_oficial_envio(envio):
        return False
    if not (envio.fecha_entrega or envio.fecha_entrega_d):
        return False
    if not _requiere_remito_cd(envio):
        return False
    return estado_remito_envio(envio) in ("sin_remito", "solo_transito")


def _falta_prefactura_proveedor(envio: Envio) -> bool:
    if envio.prefactura_proveedor is not None or not envio.alerta_clickpack:
        return False
    cod = normalizar_transporte_cod(envio.transporte_cod, envio.transporte_nombre)
    return cod in (COD_EXPRESO_CLICPAQ, COD_CROSSDOCKING)


def _diferencia_prefactura(envio: Envio) -> bool:
    if envio.prefactura_proveedor is None:
        return False
    diff = envio.diferencia if envio.diferencia is not None else 0.0
    return abs(diff) > 0.01


def _falta_cotizar_provincia(
    lineas: list[Envio],
    *,
    lineas_sin_tarifa: int,
    total_logistica: float,
) -> bool:
    if total_logistica > 0:
        return False
    if any(l.regla_postventa == "revisar_manual" for l in lineas):
        return False
    if lineas_sin_tarifa > 0:
        return True
    if any(l.excluir_planilla for l in lineas):
        return False
    return any(debe_calcular_costo_proveedor(l) for l in lineas)


def _postventa_pendiente_amba(lineas: list[Envio], *, total_logistica: float) -> bool:
    if total_logistica > 0:
        return False
    if not any(l.regla_postventa == "revisar_manual" for l in lineas):
        return False
    return any(es_amba_gba_envio(l) for l in lineas)


def _inconsistencia_transporte_proveedor(envio: Envio) -> str | None:
    circuito = resolver_circuito_logistico(
        envio.transporte_cod,
        envio.transporte_nombre,
        provincia=envio.provincia,
        localidad=envio.localidad,
        cp=envio.cp,
    )
    asig = normalizar_proveedor(envio.proveedor_tarifa)
    modo = circuito["modo"]

    if modo == "red_clicpaq":
        if asig and asig != "CLICPAQ":
            return "Transporte 51/40 interior no coincide con proveedor"
        return None
    if modo == "fletes_suc":
        if asig and asig != "FLETES_SUC":
            return "Transporte 40 AMBA no coincide con proveedor local"
        return None
    if modo == "crossdock":
        esperado = normalizar_proveedor(circuito.get("proveedor"))
        if asig and esperado and asig != esperado:
            return "Transporte 82 no coincide con última milla"
        return None
    return None


def alertas_maestro_grilla(
    lineas: list[Envio],
    *,
    lineas_sin_tarifa: int = 0,
    total_logistica: float = 0.0,
) -> list[AlertaGrilla]:
    if not lineas:
        return []
    base = lineas[0]
    out: list[AlertaGrilla] = []

    if any(_falta_remito_operativo(l) for l in lineas):
        out.append(
            {
                "codigo": "remito",
                "columnas": ["REMITOS"],
                "motivo": "Falta remito oficial (R/RAR)",
            }
        )

    if any(_falta_prefactura_proveedor(l) for l in lineas):
        out.append(
            {
                "codigo": "prefactura",
                "columnas": ["PRECIO NETO"],
                "motivo": "Falta prefactura del proveedor",
            }
        )

    if any(_diferencia_prefactura(l) for l in lineas):
        out.append(
            {
                "codigo": "dif_prefactura",
                "columnas": ["PRECIO NETO", "total"],
                "motivo": "Diferencia prefactura vs control",
            }
        )

    if _postventa_pendiente_amba(lineas, total_logistica=total_logistica):
        out.append(
            {
                "codigo": "postventa_amba",
                "columnas": ["LOGISTICA", "PROVEEDOR"],
                "motivo": "Postventa sin resolver — calcular km o aprobar viaje en detalle",
            }
        )

    if _falta_cotizar_provincia(
        lineas,
        lineas_sin_tarifa=lineas_sin_tarifa,
        total_logistica=total_logistica,
    ):
        out.append(
            {
                "codigo": "tarifa",
                "columnas": ["LOGISTICA", "PROVINCIA"],
                "motivo": "Falta cotizar destino en tarifario (provincia)",
            }
        )

    if base.requiere_elegir_proveedor:
        out.append(
            {
                "codigo": "proveedor",
                "columnas": ["PROVEEDOR"],
                "motivo": "Falta definir proveedor de tarifa",
            }
        )

    inc = _inconsistencia_transporte_proveedor(base)
    if inc:
        out.append(
            {
                "codigo": "transporte",
                "columnas": ["NRO TRANSP", "TRANSPORTE", "PROVEEDOR"],
                "motivo": inc,
            }
        )

    return out


def color_fila_maestro(
    lineas: list[Envio],
    *,
    lineas_sin_tarifa: int = 0,
    total_logistica: float = 0.0,
) -> tuple[str | None, str | None, list[AlertaGrilla]]:
    alertas = alertas_maestro_grilla(
        lineas,
        lineas_sin_tarifa=lineas_sin_tarifa,
        total_logistica=total_logistica,
    )
    if alertas:
        return "alerta", alertas[0]["motivo"], alertas
    return None, None, []


def alertas_fletes_grilla(
    *,
    retiro: bool,
    tiene_tarifa: bool,
    zona_asignada: str | None,
    motivo: str | None = None,
) -> list[AlertaGrilla]:
    if retiro:
        return []
    out: list[AlertaGrilla] = []
    if not tiene_tarifa:
        out.append(
            {
                "codigo": "tarifa_local",
                "columnas": ["TARIFA REF"],
                "motivo": motivo or "Sin tarifa local (fletes sucursales)",
            }
        )
    if tiene_tarifa and not zona_asignada:
        out.append(
            {
                "codigo": "zona_km",
                "columnas": ["ZONA KM", "KM", "SUCURSAL"],
                "motivo": motivo or "Pendiente asignar zona km",
            }
        )
    return out


def color_fila_fletes_local(
    *,
    retiro: bool,
    tiene_tarifa: bool,
    zona_asignada: str | None,
    motivo: str | None = None,
) -> tuple[str | None, list[AlertaGrilla]]:
    alertas = alertas_fletes_grilla(
        retiro=retiro,
        tiene_tarifa=tiene_tarifa,
        zona_asignada=zona_asignada,
        motivo=motivo,
    )
    if alertas:
        return "alerta", alertas
    return None, []


def columnas_con_luz(alertas: list[AlertaGrilla] | list[dict[str, Any]] | None) -> dict[str, str]:
    """columna → motivo (primera alerta que la marca)."""
    mapa: dict[str, str] = {}
    if not alertas:
        return mapa
    for a in alertas:
        motivo = str(a.get("motivo") or "")
        for col in a.get("columnas") or []:
            if col not in mapa:
                mapa[col] = motivo
    return mapa
