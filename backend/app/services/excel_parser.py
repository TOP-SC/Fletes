"""Parseo flexible de Exportacion.xlsx (Tango) — soporta variantes de columnas."""

from __future__ import annotations

import re
from io import BytesIO
from typing import Any

import pandas as pd

from app.services.flex_excel import find_column, read_first_sheet
from app.services.money_utils import parse_quantity
from app.services.remito_maestro import COLUMNAS_REMITO_OFICIAL, COLUMNAS_REMITO_TRANSITO
from app.services.remito_resolver import resolver_remitos_fila

# Orden importa: columnas más específicas primero (evita que "TRANSPORTE" robe "NOMBRE TRANSPORTE")
FIELD_CANDIDATES: list[tuple[str, tuple[str, ...]]] = [
    ("remito", COLUMNAS_REMITO_OFICIAL),
    ("remito_transito", COLUMNAS_REMITO_TRANSITO),
    ("remito_original_transito", ("REMITO ORIGINAL",)),
    ("remito_final_transito", ("REMITO FINAL",)),
    (
        "nro_pedido",
        (
            "NRO PEDIDO",
            "NRO PEDIDO FABRICA",
            "NUMERO PEDIDO",
            "NRO DE PEDIDO",
            "N PEDIDO",
        ),
    ),
    ("nro_orden", ("NRO ORDEN", "NUMERO ORDEN", "NRO DE ORDEN")),
    ("nro_factura", ("NRO FACTURA", "NUMERO FACTURA", "FACTURA")),
    ("deposito", ("DEPÓSITO DI", "DEPOSITO DI", "DEPÓSITO", "DEPOSITO", "DEPSITO DI")),
    ("fecha_pedido", ("FECHA PEDIDO DI", "FECHA PEDIDO", "FECHA DEL PEDIDO")),
    (
        "fecha_entrega",
        (
            "FECHA ENTREGA DI",
            "FECHA ENTREGA",
            "FECHA DE ENTREGA",
            "FECHA ENTREGA ORIGINAL",
        ),
    ),
    ("razon_social", ("RAZON SOCIAL DI", "RAZON SOCIAL", "CLIENTE", "NOMBRE CLIENTE")),
    ("domicilio", ("DOMICILIO DI", "DOMICILIO", "DIRECCION", "DOMICILIO ENTREGA")),
    ("localidad", ("LOCALIDAD ENTREGA DI", "LOCALIDAD ENTREGA", "LOCALIDAD", "CIUDAD")),
    ("provincia", ("NOMBRE PROVINCIA DI", "PROVINCIA", "NOMBRE PROVINCIA")),
    ("cp", ("CP DI", "CP", "CODIGO POSTAL", "COD POSTAL")),
    ("cod_articulo", ("COD ARTICULO DI", "COD ARTICULO", "CODIGO ARTICULO", "ARTICULO")),
    ("descripcion", ("DESCRIPCION", "DESCRIPCIÓN", "DESC ARTICULO", "DESCRIPCION ARTICULO")),
    ("cantidad", (
        "CANT PEDIDA SC",
        "CANT PEDIDA",
        "CANTIDAD PEDIDA",
        "ULTIMA CANTIDAD REMITIDA LMK",
        "ULTIMA CANTIDAD REMITIDA",
        "CANTIDAD",
        "QTY",
    )),
    ("estado_pedido", ("ESTADO PEDIDO", "ESTADO DEL PEDIDO")),
    ("transporte_nombre", (
        "NOMBRE TRANSPORTE DI",
        "NOMBRE TRANSPORTE",
        "NOMBRE TRANSP",
        "TRANSPORTE ORIGINAL",
        "TRANSPORTE NOMBRE",
    )),
    ("transporte_cod", ("COD TRANSPORTE", "CODIGO TRANSPORTE", "TRANSPORTE")),
    ("clasificacion", ("CLASIFICACION", "CLASIFICACIÓN")),
    ("leyenda_5", ("LEYENDA_5_DI", "LEYENDA 5", "LEYENDA_5", "LEYENDA5")),
    ("vendedor", ("VENDEDOR", "NOMBRE VENDEDOR")),
    ("m3", ("M3", "M³", "VOLUMEN M3")),
    ("tipo_gestion", ("TIPOGESTION", "TIPO GESTION", "TIPO GESTIÓN", "TIPO_GESTION")),
    ("sub_tipo", ("SUBTIPO", "SUB TIPO", "SUB-TIPO", "SUB_TIPO")),
]

CAMPOS_CRITICOS = ("remito", "cod_articulo", "descripcion", "provincia", "localidad")


def _map_columns(columns: list[Any]) -> dict[str, str]:
    used: set[str] = set()
    mapping: dict[str, str] = {}
    for field, candidates in FIELD_CANDIDATES:
        col = find_column([c for c in columns if str(c) not in used], *candidates)
        if col:
            mapping[field] = col
            used.add(col)
    return mapping


def _cell_str(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    return text or None


def _parse_float(value: Any) -> float | None:
    return parse_quantity(value)


def _row_value(series: pd.Series, col_map: dict[str, str], field: str) -> Any:
    excel_col = col_map.get(field)
    if not excel_col:
        return None
    return series.get(excel_col)


def fila_es_valida(row: dict[str, Any]) -> bool:
    """Al menos remito o (artículo + destino) para aplicar reglas."""
    if row.get("remito"):
        return True
    if row.get("cod_articulo") and (row.get("provincia") or row.get("localidad")):
        return True
    return False


def parse_exportacion_excel(content: bytes) -> list[dict[str, Any]]:
    df = read_first_sheet(content)
    # Filas totalmente vacías y columnas sin datos reducen memoria en archivos grandes.
    df = df.dropna(how="all")
    df = df.dropna(axis=1, how="all")
    col_map = _map_columns(list(df.columns))
    rows: list[dict[str, Any]] = []
    fields = [f for f, _ in FIELD_CANDIDATES if f != "remito"]

    for record in df.to_dict(orient="records"):
        series = pd.Series(record)
        normalized = {
            field: (
                _parse_float(_row_value(series, col_map, field))
                if field in ("cantidad", "m3")
                else _cell_str(_row_value(series, col_map, field))
            )
            for field in fields
        }
        principal, entrega, transito = resolver_remitos_fila(series)
        if principal:
            normalized["remito"] = principal
        elif transito:
            normalized["remito"] = None
        if entrega:
            normalized["remito_entrega"] = entrega
        if transito:
            normalized["remito_transito"] = transito
        rows.append(normalized)
    return rows


def infer_medida(descripcion: str | None) -> str:
    if not descripcion:
        return ""
    match = re.search(r"(\d{2,3})\s*[xX×]\s*(\d{2,3})", descripcion)
    if match:
        return f"{match.group(1)}x{match.group(2)}"
    return ""


def infer_tipo_producto(descripcion: str | None, cod_articulo: str | None) -> str:
    text = f"{descripcion or ''} {cod_articulo or ''}".upper()
    if "DIVAN" in text or "DIVÁN" in text:
        return "MUEBLES"
    if "COL." in text or "COLCH" in text or text.startswith("CO"):
        return "COLCHON"
    if "SOM." in text or "SOMIER" in text:
        return "SOMIER"
    if "BASE" in text or "BRDI" in text:
        return "BASE"
    if "ALMOH" in text or "ALM." in text:
        return "ALMOHADA"
    return "OTRO"
