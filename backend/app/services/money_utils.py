"""Parseo de importes y cantidades (Excel Tango / tarifarios — formatos AR)."""

import re
from typing import Any

import pandas as pd

# Columnas / campos que son dinero (pesos), no cantidades físicas
CAMPOS_MONEDA = frozenset({
    "LOGISTICA", "SEGURO", "GESTION", "ADICIONAL", "VALOR DECLARADO", "PRECIO NETO",
    "costo", "total", "dif", "precio", "importe", "costo_tarifario", "costo_total",
    "prefactura_proveedor", "diferencia", "PESO FACTURADO",
})


def parse_money(value: Any) -> float | None:
    """
    Normaliza montos en pesos:
    - 240000.000000000 -> 240000
    - 240.000 (miles AR) -> 240000
    - 240.000,50 -> 240000.5
    - $ 39.036,00 -> 39036
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None

    if isinstance(value, (int, float)):
        return _normalize_money_float(float(value))

    text = str(value).strip()
    if not text or text.lower() in ("nan", "none", "-", ""):
        return None

    text = (
        text.replace("\u00a0", "")
        .replace("$", "")
        .replace("ARS", "")
        .replace(" ", "")
        .strip()
    )
    # Solo símbolos raros del Excel LBO
    text = re.sub(r"[^\d,.\-]", "", text)
    if not text or text in ("-", ".", ","):
        return None

    # Ruido Excel: 240000.000000 (4+ ceros decimales)
    if re.fullmatch(r"\d+\.0{4,}", text):
        return _normalize_money_float(float(text.split(".")[0]))

    has_comma = "," in text
    has_dot = "." in text

    if has_comma and has_dot:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif has_comma:
        parts = text.split(",")
        if len(parts) > 1 and all(len(p) == 3 for p in parts[1:]):
            text = "".join(parts)
        elif len(parts[-1]) == 3 and len(parts) > 1:
            text = "".join(parts)
        else:
            text = text.replace(",", ".")
    elif has_dot:
        parts = text.split(".")
        if len(parts) > 1 and all(len(p) == 3 for p in parts[1:]):
            text = "".join(parts)
        elif len(parts) == 2 and len(parts[1]) > 2 and set(parts[1]) <= {"0"}:
            text = parts[0]

    try:
        return _normalize_money_float(float(text))
    except ValueError:
        return None


def _normalize_money_float(v: float) -> float:
    if v == 0:
        return 0.0
    # Pesos: sin centavos si es entero (evita 240000.0000001)
    if abs(v - round(v)) < 0.01:
        return float(int(round(v)))
    return round(v, 2)


def parse_quantity(value: Any) -> float | None:
    """Cantidades físicas (bultos, m3) — no aplicar reglas de miles AR."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (int, float)):
        return round(float(value), 4)
    text = str(value).strip().replace(",", ".")
    try:
        return round(float(text), 4)
    except ValueError:
        return None


def round_pesos(value: float | None) -> float | None:
    """Redondeo para mostrar/guardar montos en maestro."""
    if value is None:
        return None
    return _normalize_money_float(float(value))


def normalize_maestro_montos(fila: dict[str, Any]) -> dict[str, Any]:
    """Aplica parse_money a columnas monetarias del maestro."""
    out = dict(fila)
    for key in out:
        if key in CAMPOS_MONEDA or key.lower() in CAMPOS_MONEDA:
            v = out[key]
            if v is None or (isinstance(v, float) and pd.isna(v)):
                out[key] = None
            else:
                out[key] = parse_money(v)
    # dif puede quedar None si no hay prefactura
    return out
