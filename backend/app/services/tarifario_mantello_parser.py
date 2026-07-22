"""
Parser del Excel unificado:
  TARIFARIOS INTERIOR y FLETES SUC 2026.xlsx

Hojas: clicpaq, fransof, alfaro, LBO CP, fletes sucursales
"""

from __future__ import annotations

import re
from io import BytesIO
from typing import Any

import pandas as pd

from app.services.money_utils import parse_money

# Columnas de producto en hojas matriz (clicpaq / alfaro)
MATRIZ_PRODUCTOS = [
    (3, "COLCHON", "80-100", "Colchon 1 PL"),
    (4, "COLCHON", "130-150", "Colchon 2 PL"),
    (5, "COLCHON", "160-200", "Colchon Queen/King"),
    (6, "CONJUNTO", "80-100", "Conjunto 1 PL"),
    (7, "CONJUNTO", "130-150", "Conjunto 2 PL"),
    (8, "CONJUNTO", "160-200", "Conjunto Queen/King"),
    (9, "MUEBLES", "GENERICO", "Divanes / Sillones"),
]

SHEET_PROVEEDOR = {
    "clicpaq": "CLICPAQ",
    "fransof": "FRANSOF",
    "alfaro": "ALFARO",
    "lbo cp": "LBO",
    "fletes sucursales": "FLETES_SUC",
}


def _cell_str(v: Any) -> str | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    return s if s and s.lower() != "nan" else None


def _parse_matriz_provincia(
    df: pd.DataFrame,
    proveedor: str,
    *,
    start_row: int,
    end_row: int | None,
    vigencia: str | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    provincia_actual = ""

    lim = end_row if end_row is not None else len(df)
    for i in range(start_row, lim):
        r = df.iloc[i]
        prov = _cell_str(r.iloc[0])
        if prov and not prov.upper().startswith("TARIFARIO"):
            provincia_actual = prov

        localidad = _cell_str(r.iloc[1]) if len(r) > 1 else None
        cedol = _cell_str(r.iloc[2]) if len(r) > 2 else None

        if not cedol or not re.fullmatch(r"[A-Z]\d+", cedol.upper()):
            continue

        loc = localidad or "General"
        prov_final = provincia_actual or "GENERAL"

        for col_idx, tipo, medida, nota_prod in MATRIZ_PRODUCTOS:
            if col_idx >= len(r):
                continue
            precio = parse_money(r.iloc[col_idx])
            if precio is None or precio <= 0:
                continue
            rows.append(
                {
                    "proveedor": proveedor,
                    "provincia": prov_final,
                    "localidad": loc,
                    "tipo_producto": tipo,
                    "medida": medida,
                    "precio": precio,
                    "cedol": cedol,
                    "vigencia_desde": vigencia,
                    "notas": nota_prod,
                }
            )
    return rows


def _parse_clicpaq(df: pd.DataFrame) -> list[dict[str, Any]]:
    vigencia = None
    t0 = _cell_str(df.iloc[0, 0]) if len(df) else None
    if t0:
        m = re.search(r"(\d{2}/\d{2}/\d{4})", t0)
        if m:
            d, mo, y = m.group(1).split("/")
            vigencia = f"{y}-{mo}-{d}"

    return _parse_matriz_provincia(
        df, "CLICPAQ", start_row=3, end_row=None, vigencia=vigencia or "2026-04-01"
    )


def _parse_alfaro(df: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    # Bloque 1: filas 1+ (enero/febrero)
    rows.extend(
        _parse_matriz_provincia(
            df, "ALFARO", start_row=1, end_row=7, vigencia="2026-01-01"
        )
    )
    # Bloque 2: fila 8 = header, datos desde 9
    vig2 = _cell_str(df.iloc[8, 10]) if df.shape[1] > 10 else None
    if vig2 and hasattr(vig2, "strftime"):
        vig2 = vig2.strftime("%Y-%m-%d")
    rows.extend(
        _parse_matriz_provincia(
            df, "ALFARO", start_row=9, end_row=None, vigencia=vig2 or "2026-03-01"
        )
    )
    return rows


def _parse_fransof(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Localidad + tarifa vigente (última columna numérica del encabezado)."""
    rows: list[dict[str, Any]] = []
    header = df.iloc[0]
    price_col = None
    vigencia = None
    for idx in range(len(header) - 1, 1, -1):
        val = header.iloc[idx]
        if isinstance(val, pd.Timestamp):
            price_col = idx
            vigencia = val.strftime("%Y-%m-%d")
            break
        if parse_money(val) is not None:
            price_col = idx
            break

    if price_col is None:
        price_col = 8

    for i in range(1, len(df)):
        loc = _cell_str(df.iloc[i, 0])
        if not loc:
            continue
        precio = parse_money(df.iloc[i, price_col])
        if precio is None or precio <= 0:
            continue
        rows.append(
            {
                "proveedor": "FRANOV",
                "provincia": "Santa Fe",
                "localidad": loc,
                "tipo_producto": "GENERICO",
                "medida": "",
                "precio": precio,
                "cedol": None,
                "vigencia_desde": vigencia or "2026-04-01",
                "notas": "Tarifa por localidad (Franov Rosario)",
            }
        )
    return rows


def _parse_lbo(df: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    vigencia = None
    v0 = df.iloc[0, 0]
    if isinstance(v0, pd.Timestamp):
        vigencia = v0.strftime("%Y-%m-%d")

    for i in range(1, len(df)):
        servicio = _cell_str(df.iloc[i, 0])
        tarifa = parse_money(df.iloc[i, 1])
        if not servicio or tarifa is None:
            continue
        rows.append(
            {
                "proveedor": "LBO",
                "provincia": "Cordoba",
                "localidad": servicio,
                "tipo_producto": "SERVICIO",
                "medida": "",
                "precio": tarifa,
                "cedol": None,
                "vigencia_desde": vigencia or "2026-02-01",
                "notas": _cell_str(df.iloc[i, 2]) or "LBO Córdoba",
            }
        )
    return rows


def _parse_fletes_sucursales(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Tarifario CABA/GBA — para módulo Fletes (zonas y abona Wamaro/cliente)."""
    rows: list[dict[str, Any]] = []
    zona_actual = ""
    for i in range(6, len(df)):
        label = _cell_str(df.iloc[i, 0])
        if not label:
            continue
        # Filas de producto con precios en cols 4,6,8,10 (Abona Wamaro por zona)
        for z_col, zona in [(4, "Zona1_10km"), (6, "Zona2_20km"), (8, "Zona3_40km"), (10, "Zona4_40+km")]:
            if z_col >= df.shape[1]:
                continue
            raw = df.iloc[i, z_col]
            precio = parse_money(raw)
            if precio is None:
                s = _cell_str(raw)
                if s and "/km" not in s.lower():
                    precio = parse_money(s.replace("/km", ""))
            if precio is None or precio <= 0:
                continue
            tipo = "COLCHON"
            medida = "GENERICO"
            label_u = label.upper()
            if "1 PL" in label_u or "80-90-100" in label_u:
                medida = "80-100"
            elif "2 PL" in label_u or "130-140-150" in label_u:
                medida = "130-150"
            elif "QUEEN" in label_u or "KING" in label_u or "160-180-200" in label_u:
                medida = "160-200"
            if "CONJUNTO" in label_u:
                tipo = "CONJUNTO"
            elif "DIVAN" in label_u or "SILLON" in label_u or "MUEBLE" in label_u:
                tipo = "MUEBLES"
                medida = "GENERICO"
            rows.append(
                {
                    "proveedor": "FLETES_SUC",
                    "provincia": "CABA/GBA",
                    "localidad": zona,
                    "tipo_producto": tipo,
                    "medida": medida,
                    "precio": precio,
                    "cedol": None,
                    "vigencia_desde": "2025-10-21",
                    "notas": label[:120],
                }
            )
    return rows


def _parece_matriz_provincia(df: pd.DataFrame) -> bool:
    """
    Matriz tipo CLICPAQ (provincia | zona | CEDOL | 7 precios),
    aunque la hoja no se llame 'clicpaq' (ej. 'NUEVO' / Bedtime julio).
    """
    if df.shape[0] < 4 or df.shape[1] < 10:
        return False
    cedol_ok = 0
    for i in range(min(len(df), 25)):
        cedol = _cell_str(df.iloc[i, 2]) if df.shape[1] > 2 else None
        if cedol and re.fullmatch(r"[A-Z]\d+", cedol.upper()):
            precio = parse_money(df.iloc[i, 3]) if df.shape[1] > 3 else None
            if precio is not None and precio > 0:
                cedol_ok += 1
    if cedol_ok < 3:
        return False
    # Evitar hojas de trabajo (Hoja1) con layout distinto / sin título de matriz.
    blob = " ".join(
        str(x)
        for x in df.iloc[:4].astype(str).values.flatten().tolist()
        if str(x).lower() != "nan"
    ).upper()
    return (
        "TARIFARIO" in blob
        or "COLCHON" in blob
        or "COLCHÓN" in blob
        or "CONJUNTO" in blob
        or "PROVINCIA" in blob
    )


def _parse_sheet_rows(sheet: str, df: pd.DataFrame) -> tuple[str | None, list[dict[str, Any]]]:
    key = sheet.strip().lower()
    if key == "clicpaq":
        rows = _parse_clicpaq(df)
        return "CLICPAQ", rows
    if key == "alfaro":
        rows = _parse_alfaro(df)
        return "ALFARO", rows
    if key == "fransof":
        rows = _parse_fransof(df)
        return "FRANSOF", rows
    if key == "lbo cp":
        rows = _parse_lbo(df)
        return "LBO", rows
    if key == "fletes sucursales":
        rows = _parse_fletes_sucursales(df)
        return "FLETES_SUC", rows
    # Excel Bedtime / Wamaro: hoja renombrada (NUEVO, JULIO, etc.) con misma matriz.
    if _parece_matriz_provincia(df):
        rows = _parse_clicpaq(df)
        if rows:
            return "CLICPAQ", rows
    return None, []


def _vigencia_desde_filas(rows: list[dict[str, Any]]) -> str | None:
    fechas = [str(r["vigencia_desde"]) for r in rows if r.get("vigencia_desde")]
    return max(fechas) if fechas else None


def parse_tarifario_mantello_por_proveedor(content: bytes) -> list[dict[str, Any]]:
    """Un bloque por hoja Mantello (proveedor + filas + vigencia)."""
    xl = pd.ExcelFile(BytesIO(content))
    bloques: list[dict[str, Any]] = []
    for sheet in xl.sheet_names:
        df = pd.read_excel(xl, sheet_name=sheet, header=None)
        proveedor, rows = _parse_sheet_rows(sheet, df)
        if not proveedor or not rows:
            continue
        bloques.append(
            {
                "proveedor": proveedor,
                "hoja": sheet,
                "vigencia_desde": _vigencia_desde_filas(rows),
                "filas": rows,
            }
        )
    return bloques


def parse_tarifario_mantello(content: bytes) -> list[dict[str, Any]]:
    all_rows: list[dict[str, Any]] = []
    for bloque in parse_tarifario_mantello_por_proveedor(content):
        all_rows.extend(bloque["filas"])
    return all_rows


_HOJAS_MANTELLO = {"clicpaq", "fransof", "alfaro", "lbo cp", "fletes sucursales"}


def is_tarifario_mantello(content: bytes) -> bool:
    """True si hay hojas Mantello clásicas o una matriz provincial (Bedtime/Wamaro)."""
    try:
        xl = pd.ExcelFile(BytesIO(content))
        names = {s.strip().lower() for s in xl.sheet_names}
        if names & _HOJAS_MANTELLO:
            return True
        for sheet in xl.sheet_names:
            df = pd.read_excel(xl, sheet_name=sheet, header=None)
            if _parece_matriz_provincia(df):
                return True
        return False
    except Exception:
        return False
