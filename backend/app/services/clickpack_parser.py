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


def parse_clickpack_prefactura(content: bytes) -> list[dict[str, Any]]:
    df = read_first_sheet(content)
    col_remito = find_column(
        list(df.columns),
        "remito",
        "nro remito",
        "numero remito",
        "guia",
        "n° remito",
    )
    col_importe = find_column(
        list(df.columns),
        "logistica",
        "logística",
        "precio neto",
        "p. fact",
        "importe",
        "total",
        "costo",
        "facturado",
        "importe total",
        "monto",
    )
    col_fecha = find_column(
        list(df.columns),
        "fecha reporte",
        "fecha presentacion",
        "fecha presentación",
        "fecha envio",
        "fecha",
    )
    col_envio = find_column(
        list(df.columns),
        "nro envio",
        "nº envio",
        "n° envio",
        "numero envio",
        "número envio",
        "nro. envio",
        "envio clp",
        "envio",
        "id envio",
    )
    col_prov = find_column(list(df.columns), "provincia")
    col_loc = find_column(list(df.columns), "localidad")
    col_cli = find_column(list(df.columns), "cliente", "razon social", "destinatario")

    if not col_remito or not col_importe:
        raise ValueError(
            "El Excel Clickpack debe tener columnas de remito e importe "
            "(ver plantilla en data/plantilla_clickpack.xlsx)."
        )

    rows: list[dict[str, Any]] = []
    for _, series in df.iterrows():
        remito = _str(series.get(col_remito))
        importe = _parse_importe(series.get(col_importe))
        if not remito or importe is None:
            continue
        fecha = _str(series.get(col_fecha)) if col_fecha else None
        nro_envio = _str(series.get(col_envio)) if col_envio else None
        # Evitar confundir columna remito con envío si find_column eligió mal
        if nro_envio and nro_envio == remito:
            nro_envio = None
        norm = normalizar_remito(remito)
        if not norm:
            # Prefacturas a veces traen solo dígitos / variantes no RAR
            digits = "".join(c for c in remito if c.isdigit())
            norm = digits.lstrip("0") or digits or ""
        fp_src = f"{norm}|{fecha or ''}|{importe:.2f}"
        fingerprint = hashlib.sha256(fp_src.encode()).hexdigest()
        row = {
            "fingerprint": fingerprint,
            "remito": remito,
            "remito_norm": norm or None,
            "nro_envio": nro_envio,
            "fecha_reporte": fecha,
            "importe": importe,
            "provincia": _str(series.get(col_prov)) if col_prov else None,
            "localidad": _str(series.get(col_loc)) if col_loc else None,
            "cliente": _str(series.get(col_cli)) if col_cli else None,
            "raw_json": json.dumps(
                {str(k): series.get(k) for k in df.columns},
                ensure_ascii=False,
                default=str,
            ),
        }
        rows.append(row)
    return rows
