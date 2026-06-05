"""Consultas eficientes sobre envios (filtro por fecha en SQL)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import and_, inspect, or_, select
from sqlalchemy.orm import Session

from app.database import engine
from app.models import Envio
from app.services.fecha_utils import filtrar_envios_por_fecha, parse_fecha_tango


def fechas_index_disponibles() -> bool:
    insp = inspect(engine)
    if "envios" not in insp.get_table_names():
        return False
    cols = {c["name"] for c in insp.get_columns("envios")}
    return "fecha_pedido_d" in cols and "fecha_entrega_d" in cols


def cargar_envios_filtrados(
    db: Session,
    *,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    campo_fecha: str = "cualquiera",
) -> list[Envio]:
    """
    Carga envíos acotados por rango de fechas.
    Usa columnas fecha_*_d indexadas cuando existen; si no, fallback en memoria.
    """
    if not fecha_desde and not fecha_hasta:
        return list(db.scalars(select(Envio)).all())

    if fechas_index_disponibles():
        q = select(Envio)
        if campo_fecha == "pedido":
            if fecha_desde:
                q = q.where(Envio.fecha_pedido_d >= fecha_desde)
            if fecha_hasta:
                q = q.where(Envio.fecha_pedido_d <= fecha_hasta)
        elif campo_fecha == "entrega":
            if fecha_desde:
                q = q.where(Envio.fecha_entrega_d >= fecha_desde)
            if fecha_hasta:
                q = q.where(Envio.fecha_entrega_d <= fecha_hasta)
        else:
            partes = []
            if fecha_desde and fecha_hasta:
                partes.append(
                    and_(
                        Envio.fecha_pedido_d.isnot(None),
                        Envio.fecha_pedido_d >= fecha_desde,
                        Envio.fecha_pedido_d <= fecha_hasta,
                    )
                )
                partes.append(
                    and_(
                        Envio.fecha_entrega_d.isnot(None),
                        Envio.fecha_entrega_d >= fecha_desde,
                        Envio.fecha_entrega_d <= fecha_hasta,
                    )
                )
            if partes:
                q = q.where(or_(*partes))
        return list(db.scalars(q).all())

    envios = list(db.scalars(select(Envio)).all())
    return filtrar_envios_por_fecha(
        envios,
        desde=fecha_desde,
        hasta=fecha_hasta,
        campo=campo_fecha,
    )


def backfill_fechas_envios(db: Session, *, limit: int = 8000) -> int:
    """Puebla fecha_pedido_d / fecha_entrega_d desde strings Tango."""
    if not fechas_index_disponibles():
        return 0
    pendientes = list(
        db.scalars(
            select(Envio).where(
                Envio.fecha_pedido_d.is_(None),
                Envio.fecha_pedido.isnot(None),
            ).limit(limit)
        ).all()
    )
    if not pendientes:
        pendientes = list(
            db.scalars(
                select(Envio).where(
                    Envio.fecha_entrega_d.is_(None),
                    Envio.fecha_entrega.isnot(None),
                ).limit(limit)
            ).all()
        )
    n = 0
    for e in pendientes:
        if e.fecha_pedido_d is None and e.fecha_pedido:
            e.fecha_pedido_d = parse_fecha_tango(e.fecha_pedido)
        if e.fecha_entrega_d is None and e.fecha_entrega:
            e.fecha_entrega_d = parse_fecha_tango(e.fecha_entrega)
        n += 1
    if n:
        db.commit()
    return n
