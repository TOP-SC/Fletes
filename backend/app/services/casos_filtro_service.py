"""Filtros compartidos maestro / fletes / proveedores."""

from __future__ import annotations

from datetime import date

from app.models import Envio
from app.services.fecha_utils import filtrar_envios_por_fecha
from app.services.remito_maestro import grupo_pasa_filtro_remito


def aplicar_filtros_lista_envios(
    envios: list[Envio],
    *,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    campo_fecha: str = "cualquiera",
) -> list[Envio]:
    return filtrar_envios_por_fecha(
        envios,
        desde=fecha_desde,
        hasta=fecha_hasta,
        campo=campo_fecha,
    )


def parse_fecha_query(valor: str | None) -> date | None:
    if not valor:
        return None
    from app.services.fecha_utils import parse_fecha_tango

    s = str(valor).strip()
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        try:
            return date.fromisoformat(s)
        except ValueError:
            pass
    return parse_fecha_tango(valor)
