"""Métricas ejecutivas para el dashboard gerencial."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Envio, FleteSolicitud, Fletero, Sucursal
from app.services.fletes_internos_service import resumen_fleteros
from app.services.proveedor_service import stats_por_proveedor
from app.services.rules_service import es_amba_gba
from app.services.zona_maestro import zona_destino_maestro, zona_origen_maestro


def _top_provincias(db: Session, *, limit: int = 8) -> list[dict[str, Any]]:
    """Remitos y costo tarifario por provincia (valorizado para control / ARCA)."""
    # 1 costo por remito (evita multiplicar renglones del mismo caso)
    por_remito = (
        select(
            Envio.provincia.label("provincia"),
            Envio.remito_norm.label("remito_norm"),
            func.max(func.coalesce(Envio.costo_tarifario, 0.0)).label("costo"),
        )
        .where(
            Envio.excluir_planilla.is_(False),
            Envio.remito_norm.isnot(None),
            Envio.remito_norm != "",
        )
        .group_by(Envio.provincia, Envio.remito_norm)
        .subquery()
    )
    rows = db.execute(
        select(
            por_remito.c.provincia,
            func.count().label("remitos"),
            func.sum(por_remito.c.costo).label("costo"),
        )
        .group_by(por_remito.c.provincia)
        .order_by(func.sum(por_remito.c.costo).desc())
        .limit(limit)
    ).all()
    out: list[dict[str, Any]] = []
    for prov, n, costo in rows:
        nombre = (prov or "Sin provincia").strip()
        out.append(
            {
                "provincia": nombre,
                "remitos": int(n or 0),
                "costo": round(float(costo or 0), 2),
            }
        )
    return out


def _problemas_operativos(db: Session) -> list[dict[str, Any]]:
    interior = Envio.excluir_planilla.is_(False)
    items: list[tuple[str, str, Any]] = [
        (
            "Sin tarifa",
            "Sin costo tarifario en envíos con remito",
            select(func.count(func.distinct(Envio.remito_norm))).where(
                interior,
                Envio.remito_norm.isnot(None),
                (Envio.costo_tarifario.is_(None)) | (Envio.costo_tarifario <= 0),
            ),
        ),
        (
            "Sin prefactura",
            "Canal Clickpack sin cruce con prefactura",
            select(func.count()).where(
                interior,
                Envio.alerta_clickpack.is_(True),
                Envio.prefactura_proveedor.is_(None),
            ),
        ),
        (
            "Diferencia $",
            "Tarifa vs prefactura con desvío",
            select(func.count()).where(
                Envio.diferencia.isnot(None),
                ((Envio.diferencia > 0.01) | (Envio.diferencia < -0.01)),
            ),
        ),
        (
            "Elegir proveedor",
            "Remitos con más de un proveedor posible",
            select(func.count(func.distinct(Envio.remito_norm))).where(
                interior,
                Envio.requiere_elegir_proveedor.is_(True),
            ),
        ),
        (
            "Sin datos Tango",
            "Filas sin remito ni artículo",
            select(func.count()).where(
                Envio.remito.is_(None),
                Envio.cod_articulo.is_(None),
            ),
        ),
        (
            "Alerta canal",
            "Crossdock / red sin resolver",
            select(func.count()).where(Envio.alerta_clickpack.is_(True)),
        ),
    ]
    out: list[dict[str, Any]] = []
    for label, hint, q in items:
        n = int(db.scalar(q) or 0)
        if n > 0:
            out.append({"label": label, "hint": hint, "valor": n})
    out.sort(key=lambda x: -x["valor"])
    return out


def _top_zonas(db: Session, *, limit: int = 12) -> list[dict[str, Any]]:
    """Ranking por código de zona maestro (B3, S1, M1, …) — remitos únicos interior."""
    rows = db.scalars(
        select(Envio).where(
            Envio.excluir_planilla.is_(False),
            Envio.remito_norm.isnot(None),
            Envio.remito_norm != "",
        )
    ).all()
    buckets: dict[str, tuple[str, set[str]]] = {}
    for e in rows:
        rn = e.remito_norm
        if not rn:
            continue
        es_amba = bool(e.excluir_planilla) or es_amba_gba(e.provincia, e.localidad, e.cp)
        cod, desc = zona_destino_maestro(e.provincia, e.localidad, es_amba_gba=es_amba)
        if not cod:
            cod = "?"
            desc = "Sin zona"
        if cod not in buckets:
            buckets[cod] = (desc, set())
        buckets[cod][1].add(rn)
    ranked = sorted(buckets.items(), key=lambda x: -len(x[1][1]))[:limit]
    return [
        {"codigo": cod, "zona": desc, "remitos": len(visitados)}
        for cod, (desc, visitados) in ranked
    ]


def _top_transportes(db: Session, *, limit: int = 8) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(Envio).where(
            Envio.excluir_planilla.is_(False),
            Envio.remito_norm.isnot(None),
            Envio.remito_norm != "",
        )
    ).all()
    buckets: dict[str, set[str]] = defaultdict(set)
    for e in rows:
        rn = e.remito_norm
        if not rn:
            continue
        nombre = (e.transporte_nombre or e.transporte_cod or "").strip()
        if not nombre:
            nombre = "Sin transporte"
        buckets[nombre].add(rn)
    ranked = sorted(buckets.items(), key=lambda x: -len(x[1]))[:limit]
    return [{"transporte": label, "remitos": len(visitados)} for label, visitados in ranked]


def _mix_proveedores(db: Session) -> list[dict[str, Any]]:
    envios = list(
        db.scalars(
            select(Envio).where(
                Envio.excluir_planilla.is_(False),
                Envio.remito_norm.isnot(None),
            )
        ).all()
    )
    raw = stats_por_proveedor(envios)
    labels_map = {
        "CLICPAQ": "Clicpaq",
        "FRANSOF": "Fransof",
        "ALFARO": "Alfaro",
        "LBO": "LBO",
        "PENDIENTE_ELEGIR": "A elegir",
    }
    out: list[dict[str, Any]] = []
    for key, n in raw.items():
        if n <= 0:
            continue
        out.append({"proveedor": labels_map.get(key, key), "casos": int(n)})
    out.sort(key=lambda x: -x["casos"])
    return out


def _top_fleteros(db: Session, *, mes: int, anio: int) -> list[dict[str, Any]]:
    res = resumen_fleteros(db, mes=mes, anio=anio)
    filas = res.get("fleteros") or []
    out: list[dict[str, Any]] = []
    for r in filas[:8]:
        out.append(
            {
                "codigo": r.get("nombre_corto") or "?",
                "entregas": int(r.get("entregas") or 0),
                "matcheadas": int(r.get("matcheadas") or 0),
                "pagar": float(r.get("total_pagar") or 0),
            }
        )
    return out


def _etiqueta_sucursal(db: Session, codigo: str | None) -> str:
    cod = (codigo or "").strip().upper()
    if not cod:
        return "Sin código"
    suc = db.get(Sucursal, cod)
    if suc and suc.nombre:
        nom = str(suc.nombre).strip()
        if nom.upper().startswith(cod):
            return nom
        return f"{cod} — {nom}"
    return cod


def _top_sucursales_locales(db: Session, *, limit: int = 8) -> list[dict[str, Any]]:
    """Sucursales retail (código AV, BE…) desde solicitudes de fletes Drive."""
    rows = db.execute(
        select(FleteSolicitud.local_compra, func.count(FleteSolicitud.id))
        .where(
            FleteSolicitud.estado != "Anulado",
            FleteSolicitud.local_compra.isnot(None),
            FleteSolicitud.local_compra != "",
        )
        .group_by(FleteSolicitud.local_compra)
        .order_by(func.count(FleteSolicitud.id).desc())
        .limit(limit)
    ).all()
    return [
        {
            "sucursal": _etiqueta_sucursal(db, str(c or "")),
            "codigo": str(c or "?"),
            "envios": int(n),
        }
        for c, n in rows
    ]


def _top_origenes_despacho(db: Session, *, limit: int = 8) -> list[dict[str, Any]]:
    """Origen logístico (CD / depósito) cuando no hay sucursales en solicitudes."""
    rows = db.scalars(
        select(Envio).where(
            Envio.excluir_planilla.is_(False),
            Envio.remito_norm.isnot(None),
            Envio.remito_norm != "",
        )
    ).all()
    buckets: dict[str, set[str]] = defaultdict(set)
    for e in rows:
        rn = e.remito_norm
        if not rn:
            continue
        _zona, desc = zona_origen_maestro(e.deposito, e.origen_cd)
        label = (e.sucursal_cc or desc or "").strip()
        if not label and e.deposito:
            label = f"Depósito {e.deposito}"
        if not label:
            label = "Sin origen"
        buckets[label].add(rn)
    ranked = sorted(buckets.items(), key=lambda x: -len(x[1]))[:limit]
    return [
        {"sucursal": label, "codigo": label, "envios": len(visitados)}
        for label, visitados in ranked
    ]


def _top_sucursales(db: Session, *, limit: int = 8) -> list[dict[str, Any]]:
    locales = _top_sucursales_locales(db, limit=limit)
    if locales:
        return locales
    return _top_origenes_despacho(db, limit=limit)


def _fleteros_solicitudes(db: Session) -> list[dict[str, Any]]:
    rows = db.execute(
        select(Fletero.nombre_corto, func.count(FleteSolicitud.id))
        .join(Fletero, FleteSolicitud.fletero_id == Fletero.id, isouter=True)
        .where(FleteSolicitud.estado != "Anulado")
        .group_by(Fletero.nombre_corto)
        .order_by(func.count(FleteSolicitud.id).desc())
        .limit(8)
    ).all()
    return [
        {"codigo": (c or "OTROS"), "solicitudes": int(n)}
        for c, n in rows
    ]


def stats_dashboard_gerencial(db: Session) -> dict[str, Any]:
    hoy = date.today()
    interior_remitos = int(
        db.scalar(
            select(func.count(func.distinct(Envio.remito_norm))).where(
                Envio.excluir_planilla.is_(False),
                Envio.remito_norm.isnot(None),
            )
        )
        or 0
    )
    con_tarifa_remitos = int(
        db.scalar(
            select(func.count(func.distinct(Envio.remito_norm))).where(
                Envio.excluir_planilla.is_(False),
                Envio.remito_norm.isnot(None),
                Envio.costo_tarifario.isnot(None),
                Envio.costo_tarifario > 0,
            )
        )
        or 0
    )
    costo_tarifado = float(
        db.scalar(
            select(func.sum(Envio.costo_tarifario)).where(
                Envio.excluir_planilla.is_(False),
                Envio.costo_tarifario.isnot(None),
                Envio.costo_tarifario > 0,
            )
        )
        or 0
    )
    diff_abs = float(
        db.scalar(
            select(func.sum(func.abs(Envio.diferencia))).where(
                Envio.diferencia.isnot(None),
                ((Envio.diferencia > 0.01) | (Envio.diferencia < -0.01)),
            )
        )
        or 0
    )
    macheo_ok = int(
        db.scalar(
            select(func.count()).where(Envio.macheo_estado == "matcheado")
        )
        or 0
    )
    pct_tarifa = round(100 * con_tarifa_remitos / interior_remitos, 1) if interior_remitos else 0.0

    fleteros_mes = _top_fleteros(db, mes=hoy.month, anio=hoy.year)
    fleteros_sol = _fleteros_solicitudes(db)
    top_sucursales = _top_sucursales(db)

    return {
        "periodo": {"mes": hoy.month, "anio": hoy.year},
        "kpis": {
            "costo_tarifado": round(costo_tarifado, 2),
            "remitos_interior": interior_remitos,
            "pct_tarifados": pct_tarifa,
            "remitos_con_tarifa": con_tarifa_remitos,
            "diferencias_abs": round(diff_abs, 2),
            "cruces_ok": macheo_ok,
            "problemas_activos": len(_problemas_operativos(db)),
        },
        "top_provincias": _top_provincias(db),
        "top_zonas": _top_zonas(db),
        "top_transportes": _top_transportes(db),
        "problemas": _problemas_operativos(db),
        "proveedores": _mix_proveedores(db),
        "fleteros_mes": fleteros_mes,
        "fleteros_solicitudes": fleteros_sol,
        "top_sucursales": top_sucursales,
    }
