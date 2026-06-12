"""Import, macheo y resumen de fletes internos (fleteros locales)."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.fleteros import nombre_corto_fletero, normalizar_nombre_fletero
from app.models import Envio, Fletero, FleteSolicitud, ImportBatch
from app.services.fecha_utils import parse_fecha_tango, periodo_mes_solo
from app.services.fletes_solicitud_parser import extraer_pedidos_articulos, leer_solicitudes_excel
from app.services.mundo2_service import construir_fletes, es_envio_mundo2
from app.services.remito_utils import normalizar_remito
from app.services.tarifario_version_service import TarifarioContext


def _norm_pedido(p: str | None) -> str:
    s = (p or "").strip()
    return s.lstrip("0") or s


def _pedido_variantes(p: str | None) -> list[str]:
    """Variantes del Nro Pedido Drive vs Tango (ej. 0805100206781 → 805100206781)."""
    if not p:
        return []
    s = str(p).strip()
    out: list[str] = []
    seen: set[str] = set()

    def add(x: str) -> None:
        if x and x not in seen:
            seen.add(x)
            out.append(x)

    add(s)
    add(_norm_pedido(s))
    if s.startswith("0"):
        add(s[1:])
    n = _norm_pedido(s)
    if len(n) >= 10:
        add(n[-10:])
    if len(n) >= 11:
        add(n[-11:])
    return out


def _codigo_cliente_excel(cliente: str | None) -> str | None:
    m = re.match(r"^([A-Z0-9]+)\s*-", (cliente or "").upper())
    return m.group(1) if m else None


def _nombre_cliente_excel(cliente: str | None) -> str:
    if not cliente:
        return ""
    parts = str(cliente).split("-", 1)
    return parts[-1].strip().upper() if len(parts) > 1 else str(cliente).strip().upper()


def _upsert_fletero(db: Session, nombre: str) -> Fletero:
    canon = normalizar_nombre_fletero(nombre)
    corto = nombre_corto_fletero(canon)
    row = db.scalar(select(Fletero).where(Fletero.nombre == canon))
    if row:
        if row.nombre_corto != corto:
            row.nombre_corto = corto
        return row
    row = Fletero(nombre=canon, nombre_corto=corto)
    db.add(row)
    db.flush()
    return row


def import_solicitudes_fletes(
    db: Session,
    content: bytes,
    filename: str,
    *,
    ejecutar_macheo: bool = False,
) -> dict[str, Any]:
    rows = leer_solicitudes_excel(content)
    batch = ImportBatch(
        filename=filename,
        source="fletes_solicitud",
        rows_in_file=len(rows),
    )
    db.add(batch)
    db.flush()

    insertados = 0
    actualizados = 0
    fleteros_vistos: set[str] = set()

    for row in rows:
        existente = db.scalar(
            select(FleteSolicitud).where(
                FleteSolicitud.id_flete_externo == row["id_flete_externo"]
            )
        )
        fletero = _upsert_fletero(db, row["fletero_nombre"])
        fleteros_vistos.add(fletero.nombre_corto)

        payload = {
            "fletero_id": fletero.id,
            "nro_pedido": row.get("nro_pedido"),
            "nro_pedido_norm": row.get("nro_pedido_norm"),
            "local_compra": row.get("local_compra"),
            "local_entrega": row.get("local_entrega"),
            "fecha_entrega": row.get("fecha_entrega"),
            "fecha_solicitado": row.get("fecha_solicitado"),
            "estado": row.get("estado"),
            "abona": row.get("abona"),
            "motivo": row.get("motivo"),
            "direccion": row.get("direccion"),
            "importe_wamaro": row.get("importe_wamaro"),
            "importe_cliente": row.get("importe_cliente"),
            "cliente": row.get("cliente"),
            "articulos_raw": row.get("articulos_raw"),
            "import_batch_id": batch.id,
            "raw_json": row.get("raw_json"),
            "match_estado": "pendiente",
        }
        if existente:
            for k, v in payload.items():
                setattr(existente, k, v)
            actualizados += 1
        else:
            db.add(FleteSolicitud(id_flete_externo=row["id_flete_externo"], **payload))
            insertados += 1

    batch.rows_inserted = insertados
    batch.rows_skipped = actualizados
    db.commit()

    match_stats = ejecutar_macheo_solicitudes(db) if ejecutar_macheo else None
    return {
        "batch_id": batch.id,
        "rows_in_file": len(rows),
        "insertados": insertados,
        "actualizados": actualizados,
        "fleteros": sorted(fleteros_vistos),
        "macheo": match_stats,
    }


def _indice_pedidos_fletes(envios_m2: list[Envio]) -> dict[str, Envio]:
    """Índice pedido → envío solo en ámbito Fletes (Mundo 2 / maestro Amba-GBA)."""
    idx: dict[str, Envio] = {}
    for e in envios_m2:
        if not e.nro_pedido:
            continue
        for v in _pedido_variantes(e.nro_pedido):
            if v not in idx:
                idx[v] = e
    return idx


def _pedidos_solicitud(sol: FleteSolicitud) -> list[str]:
    pedidos: list[str] = []
    seen: set[str] = set()
    for p in [sol.nro_pedido, *(extraer_pedidos_articulos(sol.articulos_raw))]:
        if p and p not in seen:
            seen.add(p)
            pedidos.append(p)
    return pedidos


def _match_por_pedido(sol: FleteSolicitud, idx: dict[str, Envio]) -> Envio | None:
    for p in _pedidos_solicitud(sol):
        for v in _pedido_variantes(p):
            env = idx.get(v)
            if env:
                return env
    return None


def _match_por_cliente_fecha(
    sol: FleteSolicitud,
    envios_m2: list[Envio],
) -> Envio | None:
    cod = _codigo_cliente_excel(sol.cliente)
    nombre = _nombre_cliente_excel(sol.cliente)
    fe = parse_fecha_tango(sol.fecha_entrega) or parse_fecha_tango(sol.fecha_solicitado)
    loc = (sol.local_entrega or "").strip().upper()
    candidatos: list[tuple[float, Envio]] = []

    for e in envios_m2:
        fe2 = parse_fecha_tango(e.fecha_entrega) or parse_fecha_tango(e.fecha_pedido)
        if fe and fe2 and abs((fe - fe2).days) > 7:
            continue
        score = 0.0
        suc = (e.sucursal_cc or e.origen_cd or "").strip().upper()
        if loc and suc and (suc == loc or suc.startswith(loc) or loc.startswith(suc[:2])):
            score += 2.0
        blob = f"{e.razon_social or ''} {e.raw_json or ''}".upper()
        if cod and cod in blob:
            score += 6.0
        if nombre:
            rs = (e.razon_social or "").upper()
            sim = SequenceMatcher(None, nombre[:40], rs[:40]).ratio()
            if sim >= 0.88:
                score += 5.0
            elif sim >= 0.72:
                score += 3.0
        if score >= 6.0:
            candidatos.append((score, e))

    if not candidatos:
        return None
    candidatos.sort(key=lambda x: -x[0])
    if len(candidatos) == 1:
        return candidatos[0][1]
    if candidatos[0][0] - candidatos[1][0] >= 2.0:
        return candidatos[0][1]
    return None


def _asignar_match(sol: FleteSolicitud, env: Envio, metodo: str) -> None:
    sol.remito_norm = env.remito_norm or normalizar_remito(env.remito)
    sol.match_estado = metodo


def ejecutar_macheo_solicitudes(db: Session) -> dict[str, int]:
    envios_m2 = [e for e in db.scalars(select(Envio)).all() if es_envio_mundo2(e)]
    idx = _indice_pedidos_fletes(envios_m2)
    solicitudes = list(
        db.scalars(
            select(FleteSolicitud).where(FleteSolicitud.estado != "Anulado")
        ).all()
    )
    stats: dict[str, int] = {
        "procesadas": 0,
        "matcheadas": 0,
        "matcheadas_pedido": 0,
        "matcheadas_cliente": 0,
        "sin_pedido": 0,
        "sin_envio": 0,
        "envios_fletes_maestro": len(envios_m2),
        "pedidos_indexados": len(idx),
    }
    for sol in solicitudes:
        stats["procesadas"] += 1
        if not _pedidos_solicitud(sol):
            stats["sin_pedido"] += 1
            sol.match_estado = "sin_pedido"
            sol.remito_norm = None
            continue
        env = _match_por_pedido(sol, idx)
        if env:
            _asignar_match(sol, env, "matcheado_pedido")
            stats["matcheadas"] += 1
            stats["matcheadas_pedido"] += 1
            continue
        env = _match_por_cliente_fecha(sol, envios_m2)
        if env:
            _asignar_match(sol, env, "matcheado_cliente")
            stats["matcheadas"] += 1
            stats["matcheadas_cliente"] += 1
            continue
        stats["sin_envio"] += 1
        sol.match_estado = "sin_envio_maestro"
        sol.remito_norm = None
    db.commit()
    return stats


def mapa_fletero_por_remito(db: Session) -> dict[str, dict[str, Any]]:
    """remito_norm → {nombre, nombre_corto, id_flete_externo}."""
    q = (
        select(FleteSolicitud, Fletero)
        .join(Fletero, FleteSolicitud.fletero_id == Fletero.id, isouter=True)
        .where(
            FleteSolicitud.remito_norm.isnot(None),
            FleteSolicitud.match_estado.in_(("matcheado", "matcheado_pedido", "matcheado_cliente")),
            FleteSolicitud.estado != "Anulado",
        )
    )
    out: dict[str, dict[str, Any]] = {}
    for sol, fl in db.execute(q).all():
        if not sol.remito_norm:
            continue
        out[sol.remito_norm] = {
            "fletero_id": fl.id if fl else None,
            "fletero": fl.nombre if fl else None,
            "fletero_corto": fl.nombre_corto if fl else None,
            "id_flete_externo": sol.id_flete_externo,
        }
    return out


def _filtra_solicitud_periodo(
    sol: FleteSolicitud,
    fecha_desde: date | None,
    fecha_hasta: date | None,
) -> bool:
    if not fecha_desde and not fecha_hasta:
        return True
    f = parse_fecha_tango(sol.fecha_entrega) or parse_fecha_tango(sol.fecha_solicitado)
    if not f:
        return True
    if fecha_desde and f < fecha_desde:
        return False
    if fecha_hasta and f > fecha_hasta:
        return False
    return True


def listar_solicitudes(db: Session) -> list[dict[str, Any]]:
    q = (
        select(FleteSolicitud, Fletero)
        .join(Fletero, FleteSolicitud.fletero_id == Fletero.id, isouter=True)
        .order_by(FleteSolicitud.fecha_entrega.desc(), FleteSolicitud.id.desc())
    )
    out: list[dict[str, Any]] = []
    for sol, fl in db.execute(q).all():
        out.append(
            {
                "id_flete": sol.id_flete_externo,
                "fletero": fl.nombre_corto if fl else "",
                "fletero_nombre": fl.nombre if fl else "",
                "cliente": sol.cliente,
                "nro_pedido": sol.nro_pedido,
                "local_entrega": sol.local_entrega,
                "fecha_entrega": sol.fecha_entrega,
                "estado": sol.estado,
                "match_estado": sol.match_estado,
                "remito_norm": sol.remito_norm,
            }
        )
    return out


def listar_fleteros(db: Session) -> list[dict[str, Any]]:
    rows = db.scalars(select(Fletero).where(Fletero.activo.is_(True)).order_by(Fletero.nombre_corto)).all()
    return [
        {"id": r.id, "nombre": r.nombre, "nombre_corto": r.nombre_corto}
        for r in rows
    ]


def resumen_fleteros(
    db: Session,
    *,
    mes: int | None = None,
    anio: int | None = None,
    fletero_corto: str | None = None,
) -> dict[str, Any]:
    fecha_desde: date | None = None
    fecha_hasta: date | None = None
    if mes and anio:
        fecha_desde, fecha_hasta = periodo_mes_solo(anio, mes)

    from app.services.envio_query_service import cargar_envios_filtrados

    if fecha_desde and fecha_hasta:
        envios = [
            e
            for e in cargar_envios_filtrados(
                db,
                fecha_desde=fecha_desde,
                fecha_hasta=fecha_hasta,
                campo_fecha="entrega",
            )
            if es_envio_mundo2(e)
        ]
    else:
        envios = [e for e in db.scalars(select(Envio)).all() if es_envio_mundo2(e)]
    from app.services.fletes_km_service import preparar_contexto_km

    tarifario_ctx = TarifarioContext(db)
    dist = preparar_contexto_km(db, envios, enrich_limit=0, auto_calc_limit=0)
    casos_fletes = {
        c.get("_caso_id") or c.get("REMITOS"): c
        for c in construir_fletes(
            envios, tarifario_ctx=tarifario_ctx, db=db, distancias=dist
        )
    }
    mapa_remito_caso: dict[str, dict] = {}
    for c in casos_fletes.values():
        rem = c.get("REMITOS")
        if rem:
            from app.services.remito_utils import normalizar_remito as nr

            rn = nr(str(rem).split()[0] if rem else "")
            if rn:
                mapa_remito_caso[rn] = c

    q = (
        select(FleteSolicitud, Fletero)
        .join(Fletero, FleteSolicitud.fletero_id == Fletero.id, isouter=True)
        .where(FleteSolicitud.estado != "Anulado")
    )
    if fletero_corto and fletero_corto.upper() != "TODOS":
        q = q.where(Fletero.nombre_corto == fletero_corto.upper())

    por_fletero: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "entregas": 0,
            "matcheadas": 0,
            "total_pagar": 0.0,
            "sin_tarifa": 0,
            "detalle_ids": [],
        }
    )
    total_entregas = 0
    total_pagar = 0.0

    for sol, fl in db.execute(q).all():
        if not _filtra_solicitud_periodo(sol, fecha_desde, fecha_hasta):
            continue
        corto = fl.nombre_corto if fl else "OTROS"
        bucket = por_fletero[corto]
        bucket["fletero"] = fl.nombre if fl else "OTROS"
        bucket["nombre_corto"] = corto
        bucket["entregas"] += 1
        bucket["detalle_ids"].append(sol.id_flete_externo)
        total_entregas += 1

        if sol.match_estado in ("matcheado", "matcheado_pedido", "matcheado_cliente") and sol.remito_norm:
            bucket["matcheadas"] += 1
            caso = mapa_remito_caso.get(sol.remito_norm)
            monto = None
            if caso:
                monto = caso.get("total") or caso.get("LOGISTICA")
            if monto:
                bucket["total_pagar"] += float(monto)
                total_pagar += float(monto)
            else:
                bucket["sin_tarifa"] += 1

    filas = sorted(por_fletero.values(), key=lambda x: -x["total_pagar"])
    return {
        "periodo": {"mes": mes, "anio": anio},
        "total_entregas": total_entregas,
        "total_pagar": round(total_pagar, 2),
        "fleteros": filas,
    }


def listar_detalle_internos(
    db: Session,
    *,
    fletero_corto: str | None = None,
    mes: int | None = None,
    anio: int | None = None,
) -> list[dict[str, Any]]:
    fecha_desde: date | None = None
    fecha_hasta: date | None = None
    if mes and anio:
        fecha_desde, fecha_hasta = periodo_mes_solo(anio, mes)

    mapa_f = mapa_fletero_por_remito(db)
    envios = [e for e in db.scalars(select(Envio)).all() if es_envio_mundo2(e)]
    from app.services.fletes_km_service import preparar_contexto_km

    tarifario_ctx = TarifarioContext(db)
    dist = preparar_contexto_km(db, envios, enrich_limit=3000, auto_calc_limit=0)
    casos = construir_fletes(
        envios, tarifario_ctx=tarifario_ctx, db=db, distancias=dist, mapa_fletero=mapa_f
    )

    q = (
        select(FleteSolicitud, Fletero)
        .join(Fletero, FleteSolicitud.fletero_id == Fletero.id, isouter=True)
        .where(FleteSolicitud.estado != "Anulado")
    )
    if fletero_corto and fletero_corto.upper() != "TODOS":
        q = q.where(Fletero.nombre_corto == fletero_corto.upper())

    sol_por_remito = {
        s.remito_norm: (s, fl)
        for s, fl in db.execute(q).all()
        if s.remito_norm and _filtra_solicitud_periodo(s, fecha_desde, fecha_hasta)
    }

    out: list[dict[str, Any]] = []
    for c in casos:
        rem = c.get("REMITOS") or ""
        rn = normalizar_remito(str(rem).split()[0] if rem else "")
        if not rn or rn not in sol_por_remito:
            continue
        sol, fl = sol_por_remito[rn]
        if fletero_corto and fletero_corto.upper() != "TODOS":
            if not fl or fl.nombre_corto != fletero_corto.upper():
                continue
        fila = dict(c)
        fila["FLETERO"] = fl.nombre_corto if fl else ""
        fila["ID FLETE DRIVE"] = sol.id_flete_externo
        fila["ESTADO DRIVE"] = sol.estado
        fila["NRO PEDIDO"] = sol.nro_pedido
        out.append(fila)
    return out
