"""Construcción de filtros de fecha/remito desde query params."""

from __future__ import annotations

from app.services.casos_filtro_service import parse_fecha_query


def build_filtros_casos(
    *,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
    campo_fecha: str = "entrega",
    remito_estado: str = "todos",
) -> dict:
    desde = parse_fecha_query(fecha_desde)
    hasta = parse_fecha_query(fecha_hasta)
    campo = campo_fecha if campo_fecha in ("pedido", "entrega", "cualquiera") else "cualquiera"
    remito = remito_estado if remito_estado in (
        "todos",
        "con_remito",
        "sin_remito",
        "sin_fecha_entrega",
    ) else "todos"
    return {
        "fecha_desde": desde,
        "fecha_hasta": hasta,
        "campo_fecha": campo,
        "remito_estado": remito,
    }
