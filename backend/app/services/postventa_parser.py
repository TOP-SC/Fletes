import hashlib
import json
from typing import Any

import pandas as pd

from app.services.flex_excel import find_column, read_first_sheet
from app.services.remito_utils import normalizar_remito


def _str(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    return s or None


def parse_postventa_excel(content: bytes) -> list[dict[str, Any]]:
    df = read_first_sheet(content)
    col_remito = find_column(list(df.columns), "remito", "guia", "nro remito")
    col_motivo = find_column(list(df.columns), "motivo", "motivo clickpack", "observacion")
    col_tipo = find_column(list(df.columns), "tipo", "tipo gestion", "gestion")
    col_fecha = find_column(list(df.columns), "fecha")

    if not col_remito:
        raise ValueError(
            "La grilla de postventa debe tener columna remito "
            "(ver data/plantilla_postventa.xlsx)."
        )

    rows: list[dict[str, Any]] = []
    for _, series in df.iterrows():
        remito = _str(series.get(col_remito))
        if not remito:
            continue
        motivo = _str(series.get(col_motivo)) if col_motivo else ""
        tipo = _str(series.get(col_tipo)) if col_tipo else ""
        fecha = _str(series.get(col_fecha)) if col_fecha else ""
        norm = normalizar_remito(remito)
        fp_src = f"{norm}|{motivo or ''}|{tipo or ''}|{fecha or ''}"
        fingerprint = hashlib.sha256(fp_src.encode()).hexdigest()
        rows.append(
            {
                "fingerprint": fingerprint,
                "remito": remito,
                "remito_norm": norm,
                "motivo": motivo,
                "tipo_gestion": tipo,
                "fecha": fecha or None,
                "raw_json": json.dumps(
                    {str(k): series.get(k) for k in df.columns},
                    ensure_ascii=False,
                    default=str,
                ),
            }
        )
    return rows
