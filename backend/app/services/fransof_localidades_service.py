"""Cobertura FRANSOF por localidad (Santa Fe y excepciones del tarifario)."""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from typing import Any

from app.config import DATA_DIR

FRANSOF_JSON = DATA_DIR / "fransof_localidades.json"


def _sin_acentos(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalizar_localidad_nombre(value: str | None) -> str:
    t = _sin_acentos((value or "").strip().upper())
    t = re.sub(r"\([^)]*\)", " ", t)
    t = re.sub(r"[^A-Z0-9\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    t = t.replace("GDRO ", "GRANADERO ")
    t = t.replace("GDOR ", "GOBERNADOR ")
    return t


def normalizar_provincia_nombre(value: str | None) -> str:
    t = _sin_acentos((value or "").strip().upper())
    if t in ("SANTA FE", "SF"):
        return "SANTA FE"
    if "CORDOBA" in t:
        return "CORDOBA"
    if "ENTRE RIOS" in t or t == "ER":
        return "ENTRE RIOS"
    if "BUENOS AIRES" in t:
        return "BUENOS AIRES"
    return t


@lru_cache(maxsize=1)
def _catalogo() -> list[dict[str, Any]]:
    if not FRANSOF_JSON.exists():
        return []
    raw = json.loads(FRANSOF_JSON.read_text(encoding="utf-8"))
    items = raw.get("localidades") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        return []
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict) or not item.get("nombre"):
            continue
        nombre = normalizar_localidad_nombre(str(item["nombre"]))
        alias = [
            normalizar_localidad_nombre(str(a))
            for a in (item.get("alias") or [])
            if a
        ]
        out.append(
            {
                "nombre": nombre,
                "provincia": normalizar_provincia_nombre(item.get("provincia")),
                "zona": item.get("zona"),
                "alias": alias,
            }
        )
    return out


def _provincia_coincide(esperada: str, actual: str) -> bool:
    if not esperada:
        return True
    if not actual:
        return esperada == "SANTA FE"
    if esperada == actual:
        return True
    if esperada in actual or actual in esperada:
        return True
    return False


def _nombres_coinciden(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    if len(a) >= 4 and len(b) >= 4 and (a in b or b in a):
        return True
    return False


def localidad_en_cobertura_fransof(
    provincia: str | None,
    localidad: str | None,
) -> bool:
    """
    True si la localidad está en el catálogo FRANSOF y la provincia coincide.
    Reemplaza el criterio antiguo «solo Rosario».
    """
    loc = normalizar_localidad_nombre(localidad)
    if not loc:
        return False
    prov = normalizar_provincia_nombre(provincia)

    if "VILLA DEL ROSARIO" in loc or loc.endswith(" DEL ROSARIO"):
        return False
    if loc.startswith("VILLA ") and "ROSARIO" in loc and prov not in ("", "SANTA FE"):
        return False

    for item in _catalogo():
        nombres = [item["nombre"], *item.get("alias", [])]
        if not any(_nombres_coinciden(loc, n) for n in nombres):
            continue
        esp = item.get("provincia") or "SANTA FE"
        if _provincia_coincide(esp, prov):
            return True
        if not prov and esp == "SANTA FE":
            return True
    return False


def listar_localidades_fransof() -> list[dict[str, Any]]:
    return list(_catalogo())


def resumen_cobertura_fransof() -> dict[str, Any]:
    cat = _catalogo()
    por_prov: dict[str, int] = {}
    for item in cat:
        p = item.get("provincia") or "SANTA FE"
        por_prov[p] = por_prov.get(p, 0) + 1
    return {
        "total": len(cat),
        "por_provincia": por_prov,
        "fuente": FRANSOF_JSON.name,
    }
