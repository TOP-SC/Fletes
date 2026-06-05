"""Identificación de remito de entrega (RAR / R del CD) vs tránsito (X)."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

_RE_RAR = re.compile(r"^\s*RAR\s*[\d\-]+", re.IGNORECASE)
_RE_X_TRANSITO = re.compile(r"^\s*X\d", re.IGNORECASE)

# Valores de estado Tango que no son números de remito
_NO_ES_REMITO = frozenset(
    {
        "FACTURADO",
        "CUMPLIDO",
        "IGUALES",
        "OK",
        "CRONO",
        "PENDIENTE",
        "ANULADO",
        "PARCIAL",
    }
)

# Columnas Tango/Limansky: el remito legal suele estar acá (no en REMITO DI que trae la X).
_PREFIJOS_COLUMNA_ENTREGA = (
    "NRO REMITO LEGAL",
    "REMITO LEGAL",
    "REMITO FINAL",
    "REMITO ORIGINAL",
    "REMITO ENTREGA",
    "REMITO RAR",
)


def _prioridad_columna(nombre_col: str) -> int:
    cu = str(nombre_col).upper().strip()
    for i, pref in enumerate(_PREFIJOS_COLUMNA_ENTREGA):
        if pref in cu:
            return i
    if "REMITO" in cu and cu != "REMITO DI":
        return 20
    if cu == "REMITO DI":
        return 90
    return 200


def _columna_puede_tener_remito(nombre_col: str) -> bool:
    """Evita ESTADO REMITO TANGO FINAL y columnas que no traen el número."""
    cu = str(nombre_col).upper().strip()
    if "ESTADO" in cu:
        return False
    if "ORIGINAL/FINAL" in cu.replace(" ", ""):
        return False
    if "EXPORTADO" in cu or "INFORME" in cu:
        return False
    return any(
        p in cu
        for p in (
            "NRO REMITO",
            "REMITO LEGAL",
            "REMITO DI",
            "REMITO FINAL",
            "REMITO ORIGINAL",
            "REMITO RAR",
            "REMITO ENTREGA",
            " REMITO",
        )
    )


def clasificar_valor_remito(valor: str) -> str:
    """entrega | transito | otro"""
    t = str(valor).strip()
    if not t:
        return "otro"
    if t.upper() in _NO_ES_REMITO:
        return "otro"
    if _RE_RAR.match(t):
        return "entrega"
    if _RE_X_TRANSITO.match(t):
        return "transito"
    tu = t.upper()
    if tu.startswith("X") and re.search(r"\d{5,}", tu):
        return "transito"
    clean = re.sub(r"[\s\-\./]", "", tu)
    if re.match(r"^R\d{10,}", clean):
        return "entrega"
    return "otro"


def _cell_str(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    return text or None


def resolver_remitos_fila(series: pd.Series) -> tuple[str | None, str | None, str | None]:
    """
    Devuelve (remito_CD, remito_entrega, remito_transito_X).
    El remito del CD no se reemite en crossdock: es el mismo en todo el viaje.
    """
    candidatos_entrega: list[tuple[int, str]] = []
    transito: str | None = None

    for col in series.index:
        val = _cell_str(series.get(col))
        if not val or len(val) < 6:
            continue
        cn = str(col).upper()
        kind = clasificar_valor_remito(val)

        if kind == "entrega":
            candidatos_entrega.append((_prioridad_columna(col), val))
        elif kind == "transito":
            if not transito:
                transito = val
        elif _columna_puede_tener_remito(cn) and not es_remito_transito_val(val):
            candidatos_entrega.append((_prioridad_columna(col), val))

    candidatos_entrega.sort(key=lambda x: (x[0], x[1]))
    entrega = candidatos_entrega[0][1] if candidatos_entrega else None
    return entrega, entrega, transito


def es_remito_transito_val(valor: str) -> bool:
    return clasificar_valor_remito(valor) == "transito"
