"""Catálogo de transportes Tango (COD_GVA24) — códigos en uso habitual."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config import DATA_DIR
from app.models import Transporte

TRANSPORTES_JSON = DATA_DIR / "transportes.json"

_catalog_cache: dict[str, dict[str, Any]] = {}


def normalizar_transporte_codigo(codigo: str | None) -> str | None:
    if codigo is None:
        return None
    raw = str(codigo).strip().upper()
    if not raw:
        return None
    if raw.isdigit():
        return raw.lstrip("0") or "0"
    return raw


def _row_from_json(item: dict[str, Any]) -> dict[str, Any]:
    codigo = normalizar_transporte_codigo(item.get("codigo")) or ""
    return {
        "codigo": codigo,
        "descripcion": str(item.get("descripcion") or "").strip(),
        "en_uso": bool(item.get("en_uso", True)),
        "tipo": item.get("tipo"),
        "zona": item.get("zona"),
        "proveedor": item.get("proveedor"),
        "modo": item.get("modo"),
        "excluir_planilla": bool(item.get("excluir_planilla", False)),
        "sin_flete_domicilio": bool(item.get("sin_flete_domicilio", False)),
        "es_canal_clicpaq": bool(item.get("es_canal_clicpaq", False)),
        "alerta_uso": bool(item.get("alerta_uso", False)),
        "notas": item.get("notas"),
    }


def cargar_transportes_json() -> list[dict[str, Any]]:
    if not TRANSPORTES_JSON.exists():
        return []
    raw = json.loads(TRANSPORTES_JSON.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        return []
    rows = [_row_from_json(x) for x in raw if x.get("codigo")]
    return [r for r in rows if r["codigo"]]


def _rebuild_cache(items: list[dict[str, Any]]) -> None:
    global _catalog_cache
    _catalog_cache = {r["codigo"]: r for r in items}


def catalogo_transportes() -> dict[str, dict[str, Any]]:
    if not _catalog_cache:
        _rebuild_cache(cargar_transportes_json())
    return dict(_catalog_cache)


def lookup_transporte_catalogo(
    transporte_cod: str | None,
    transporte_nombre: str | None = None,
) -> dict[str, Any] | None:
    cat = catalogo_transportes()
    cod = normalizar_transporte_codigo(transporte_cod)
    if cod and cod in cat:
        return cat[cod]
    if transporte_cod and str(transporte_cod).strip().upper() in cat:
        return cat[str(transporte_cod).strip().upper()]
    nombre = (transporte_nombre or "").strip().upper()
    if not nombre:
        return None
    for row in cat.values():
        if row.get("descripcion", "").upper() == nombre:
            return row
    return None


def sincronizar_transportes(db: Session) -> dict[str, int]:
    """Upsert desde data/transportes.json."""
    items = cargar_transportes_json()
    _rebuild_cache(items)
    insertados = 0
    actualizados = 0
    for data in items:
        codigo = data["codigo"]
        existente = db.get(Transporte, codigo)
        if existente:
            for k, v in data.items():
                setattr(existente, k, v)
            actualizados += 1
        else:
            db.add(Transporte(**data))
            insertados += 1
    db.commit()
    return {
        "total_archivo": len(items),
        "insertados": insertados,
        "actualizados": actualizados,
        "en_bd": db.query(Transporte).count(),
    }


def listar_transportes(db: Session, *, solo_en_uso: bool = True) -> list[Transporte]:
    q = db.query(Transporte).order_by(Transporte.codigo)
    if solo_en_uso:
        q = q.filter(Transporte.en_uso.is_(True))
    return list(q.all())


def transporte_a_dict(t: Transporte) -> dict[str, Any]:
    return {
        "codigo": t.codigo,
        "descripcion": t.descripcion,
        "en_uso": t.en_uso,
        "tipo": t.tipo,
        "zona": t.zona,
        "proveedor": t.proveedor,
        "modo": t.modo,
        "excluir_planilla": t.excluir_planilla,
        "sin_flete_domicilio": t.sin_flete_domicilio,
        "es_canal_clicpaq": t.es_canal_clicpaq,
        "alerta_uso": t.alerta_uso,
        "notas": t.notas,
    }
