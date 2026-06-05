"""Catálogo de sucursales SommierCenter (dirección y coordenadas para fletes / km)."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config import DATA_DIR
from app.models import Sucursal

SUCURSALES_JSON = DATA_DIR / "sucursales.json"
COORDS_CSV = DATA_DIR / "input" / "coordenadas_sucursales.csv"
CODIGO_ALIASES = {"THC": "TH", "UG": "SV"}


def _infer_zona(localidad: str) -> str:
    loc = (localidad or "").upper()
    if "C.A.B.A" in loc or "CABA" in loc or "CAPITAL" in loc:
        return "CABA"
    if "GBA" in loc or "BUENOS AIRES" in loc:
        return "GBA"
    if "SALTA" in loc:
        return "INTERIOR"
    if "ROSARIO" in loc or "SANTA FE" in loc:
        return "INTERIOR"
    if "CORDOBA" in loc or "CÓRDOBA" in loc:
        return "INTERIOR"
    return "OTRO"


def _row_from_json(item: dict[str, Any]) -> dict[str, Any]:
    codigo = str(item.get("id") or "").strip().upper()
    localidad = str(item.get("localidad") or "").strip()
    lat = item.get("lat")
    lon = item.get("lon")
    return {
        "codigo": codigo,
        "nombre": str(item.get("nombre") or "").strip(),
        "direccion": str(item.get("direccion") or "").strip(),
        "localidad": localidad,
        "provincia": str(item.get("provincia") or "").strip() or None,
        "zona": _infer_zona(localidad),
        "lat": float(lat) if lat is not None else None,
        "lon": float(lon) if lon is not None else None,
        "activa": True,
    }


def _fusionar_coordenadas_en_json() -> None:
    """Completa lat/lon en sucursales.json desde mantello CSV."""
    if not SUCURSALES_JSON.exists() or not COORDS_CSV.exists():
        return
    raw = json.loads(SUCURSALES_JSON.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        return
    coords: dict[str, tuple[float, float]] = {}
    with COORDS_CSV.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            cod = str(row.get("Código") or row.get("Codigo") or "").strip().upper()
            cod = CODIGO_ALIASES.get(cod, cod)
            try:
                lat = float(row.get("Latitud") or "")
                lon = float(row.get("Longitud") or "")
            except (TypeError, ValueError):
                continue
            coords[cod] = (lat, lon)
    cambios = 0
    for item in raw:
        cod = str(item.get("id") or "").strip().upper()
        if cod in coords and (item.get("lat") is None or item.get("lon") is None):
            item["lat"], item["lon"] = coords[cod]
            cambios += 1
    if cambios:
        SUCURSALES_JSON.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def cargar_sucursales_json() -> list[dict[str, Any]]:
    _fusionar_coordenadas_en_json()
    if not SUCURSALES_JSON.exists():
        return []
    raw = json.loads(SUCURSALES_JSON.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        return []
    rows = [_row_from_json(x) for x in raw if x.get("id")]
    return [r for r in rows if r["codigo"]]


def sincronizar_sucursales(db: Session) -> dict[str, int]:
    """Upsert desde data/sucursales.json."""
    items = cargar_sucursales_json()
    insertados = 0
    actualizados = 0
    for data in items:
        codigo = data["codigo"]
        existente = db.get(Sucursal, codigo)
        if existente:
            for k, v in data.items():
                setattr(existente, k, v)
            actualizados += 1
        else:
            db.add(Sucursal(**data))
            insertados += 1
    db.commit()
    return {
        "total_archivo": len(items),
        "insertados": insertados,
        "actualizados": actualizados,
        "en_bd": db.query(Sucursal).count(),
    }


def listar_sucursales(db: Session, *, solo_activas: bool = True) -> list[Sucursal]:
    q = db.query(Sucursal).order_by(Sucursal.nombre)
    if solo_activas:
        q = q.filter(Sucursal.activa.is_(True))
    return list(q.all())


def sucursal_por_codigo(db: Session, codigo: str | None) -> Sucursal | None:
    if not codigo:
        return None
    return db.get(Sucursal, str(codigo).strip().upper())


def sucursal_a_dict(s: Sucursal) -> dict[str, Any]:
    return {
        "codigo": s.codigo,
        "nombre": s.nombre,
        "direccion": s.direccion,
        "localidad": s.localidad,
        "provincia": s.provincia,
        "zona": s.zona,
        "lat": s.lat,
        "lon": s.lon,
        "tiene_coordenadas": s.lat is not None and s.lon is not None,
        "activa": s.activa,
    }
