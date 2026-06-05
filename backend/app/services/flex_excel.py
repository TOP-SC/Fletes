"""Detección flexible de columnas en Excel de proveedores."""

from io import BytesIO
from typing import Any

import pandas as pd


def _norm_col(name: Any) -> str:
    return str(name).strip().lower().replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")


def find_column(columns: list[Any], *candidates: str) -> str | None:
    normalized = {_norm_col(c): str(c) for c in columns}
    for cand in candidates:
        key = _norm_col(cand)
        if key in normalized:
            return normalized[key]
        for ncol, original in normalized.items():
            if key in ncol:
                # Evitar que "RAR" matchee RAZON SOCIAL o "NRO REMITO" matchee NRO PEDIDO
                if key == "rar" and "razon" in ncol:
                    continue
                if key == "nro remito" and "pedido" in ncol:
                    continue
                if key == "remito" and ncol in ("nro pedido", "nro pedido fabrica"):
                    continue
                return original
    return None


def read_first_sheet(content: bytes) -> pd.DataFrame:
    return pd.read_excel(BytesIO(content), sheet_name=0, engine="openpyxl")
