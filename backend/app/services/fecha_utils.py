"""Parseo y filtros de fechas Tango (pedido / entrega)."""

from __future__ import annotations

import calendar
import re
from datetime import date, datetime
from typing import Literal

from app.models import Envio

CampoFecha = Literal["pedido", "entrega", "cualquiera"]


def parse_fecha_tango(valor: str | None) -> date | None:
    """Acepta 5/5/2026, 5/5/2026 00:00:00, 2026-05-05."""
    if not valor:
        return None
    s = str(valor).strip()
    if not s or s.startswith("1/1/1900"):
        return None
    s = s.split(" ", 1)[0].strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return date(y, mo, d)
        except ValueError:
            return None
    return None


def formato_fecha_grilla(valor: str | None) -> str:
    d = parse_fecha_tango(valor)
    if not d:
        return ""
    return d.strftime("%d/%m/%Y")


def periodo_control_mes(anio: int, mes: int) -> tuple[date, date]:
    """
    Mes a controlar + mes anterior (cubre entregas pactadas fuera del mes del pedido).
    Ej. controlar mayo 2026 → 01/04/2026 al 31/05/2026.
    """
    ultimo = calendar.monthrange(anio, mes)[1]
    fin = date(anio, mes, ultimo)
    if mes == 1:
        inicio = date(anio - 1, 12, 1)
    else:
        inicio = date(anio, mes - 1, 1)
    return inicio, fin


def periodo_mes_solo(anio: int, mes: int) -> tuple[date, date]:
    ultimo = calendar.monthrange(anio, mes)[1]
    return date(anio, mes, 1), date(anio, mes, ultimo)


def resolver_periodo_vista(anio: int, mes: int) -> tuple[date, date]:
    """Rango del mes elegido (día 1 → último día)."""
    return periodo_mes_solo(anio, mes)


def _en_rango(d: date | None, desde: date | None, hasta: date | None) -> bool:
    if d is None:
        return False
    if desde and d < desde:
        return False
    if hasta and d > hasta:
        return False
    return True


def envio_coincide_fecha(
    envio: Envio,
    *,
    desde: date | None,
    hasta: date | None,
    campo: CampoFecha = "cualquiera",
) -> bool:
    if not desde and not hasta:
        return True
    fp = parse_fecha_tango(envio.fecha_pedido)
    fe = parse_fecha_tango(envio.fecha_entrega)
    if campo == "pedido":
        return _en_rango(fp, desde, hasta)
    if campo == "entrega":
        return _en_rango(fe, desde, hasta)
    return _en_rango(fp, desde, hasta) or _en_rango(fe, desde, hasta)


def fecha_referencia_tarifa(envio: Envio) -> str | None:
    """
    Fecha para elegir versión de tarifario: entrega primero, sino pedido.
    Retorna ISO YYYY-MM-DD o None.
    """
    fe = parse_fecha_tango(envio.fecha_entrega)
    if fe:
        return fe.isoformat()
    fp = parse_fecha_tango(envio.fecha_pedido)
    if fp:
        return fp.isoformat()
    return None


def filtrar_envios_por_fecha(
    envios: list[Envio],
    *,
    desde: date | None = None,
    hasta: date | None = None,
    campo: str = "cualquiera",
) -> list[Envio]:
    c: CampoFecha = campo if campo in ("pedido", "entrega", "cualquiera") else "cualquiera"
    if not desde and not hasta:
        return envios
    return [e for e in envios if envio_coincide_fecha(e, desde=desde, hasta=hasta, campo=c)]
