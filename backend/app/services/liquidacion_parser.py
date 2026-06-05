import hashlib
import json
from typing import Any

import pandas as pd

from app.services.flex_excel import find_column, read_first_sheet
from app.services.money_utils import parse_money
from app.services.remito_utils import normalizar_remito


def _parse_importe(value: Any) -> float | None:
    return parse_money(value)


def _str(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    return s or None


def parse_liquidacion_excel(content: bytes, periodo: str) -> list[dict[str, Any]]:
    df = read_first_sheet(content)
    col_remito = find_column(list(df.columns), "remito", "guia", "nro remito")
    col_importe = find_column(
        list(df.columns), "importe", "total", "liquidado", "monto", "importe liquidacion"
    )
    if not col_remito or not col_importe:
        raise ValueError(
            "La liquidación debe tener remito e importe (ver plantilla_liquidacion.xlsx)."
        )

    rows: list[dict[str, Any]] = []
    for _, series in df.iterrows():
        remito = _str(series.get(col_remito))
        importe = _parse_importe(series.get(col_importe))
        if not remito or importe is None:
            continue
        norm = normalizar_remito(remito)
        fp_src = f"{periodo}|{norm}|{importe:.2f}"
        fingerprint = hashlib.sha256(fp_src.encode()).hexdigest()
        rows.append(
            {
                "fingerprint": fingerprint,
                "periodo": periodo,
                "remito": remito,
                "remito_norm": norm,
                "importe_liquidacion": importe,
                "raw_json": json.dumps(
                    {str(k): series.get(k) for k in df.columns},
                    ensure_ascii=False,
                    default=str,
                ),
            }
        )
    return rows
