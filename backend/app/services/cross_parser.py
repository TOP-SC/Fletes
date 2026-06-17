"""Parser de planillas cross (pestañas «Retirado por …»)."""

from __future__ import annotations

import io
import json
from datetime import date, datetime
from typing import Any

import pandas as pd

from app.services.remito_utils import es_remito_oficial, normalizar_remito


def _es_hoja_retirado(nombre: str) -> bool:
    return "retirado" in nombre.lower()


def _proveedor_desde_hoja(nombre: str) -> str | None:
    n = nombre.upper()
    if "FRANSOF" in n or "FRANOV" in n:
        return "FRANSOF"
    if "ALFARO" in n:
        return "ALFARO"
    if "LBO" in n:
        return "LBO"
    if "COMPLETA" in n:
        return "COMPLETA"
    return None


def _detectar_header(df_raw: pd.DataFrame) -> int | None:
    for i in range(min(8, len(df_raw))):
        row = [str(x).strip().upper() for x in df_raw.iloc[i].tolist()]
        if "REMITO" in row:
            return i
    return None


def _col_por_alias(df: pd.DataFrame, *aliases: str) -> str | None:
    upper_map = {str(c).strip().upper(): c for c in df.columns}
    for a in aliases:
        if a.upper() in upper_map:
            return upper_map[a.upper()]
    for c in df.columns:
        u = str(c).strip().upper()
        for a in aliases:
            if a.upper() in u:
                return c
    return None


def _celda_str(v: Any) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    if isinstance(v, (datetime, date)):
        return v.strftime("%Y-%m-%d")
    s = str(v).strip()
    return "" if s.lower() in ("nan", "none") else s


def _normalizar_entregado(v: str) -> str:
    s = (v or "").strip().upper()
    if not s or s in ("-", "—", "N/A", "NA", "PENDIENTE"):
        return "pendiente"
    if s in ("SI", "SÍ", "S", "OK", "OIK", "ENTREGADO"):
        return "SI"
    if s in ("NO", "N", "DEVUELTO", "DEVUELTO A DEPOSITO", "DEVUELTO A DEPÓSITO"):
        return "NO"
    return s


def _leer_hoja_retirado(path_or_buf: io.BytesIO | str, sheet: str) -> list[dict[str, Any]]:
    raw = pd.read_excel(path_or_buf, sheet_name=sheet, header=None, dtype=str)
    hdr = _detectar_header(raw)
    if hdr is None:
        return []
    df = pd.read_excel(path_or_buf, sheet_name=sheet, header=hdr, dtype=str)
    df.columns = [str(c).strip() for c in df.columns]

    col_remito = _col_por_alias(df, "REMITO")
    if not col_remito:
        return []

    col_pedido = _col_por_alias(df, "PEDIDO", "NRO PEDIDO")
    col_f_ret = _col_por_alias(
        df, "FECHA DE RETIRO", "FECHA RETIRO", "RETIRO FRANSOF"
    )
    col_f_ent = _col_por_alias(
        df,
        "FECHA DE ENTREGA COORDINADA",
        "FECHA ENTREGA COORDINADA",
        "FECHA DE ENTREGA",
    )
    col_ent = _col_por_alias(df, "ENTREGADO OK", "ENTREGADO", "Entregado")
    col_obs = _col_por_alias(df, "OBS", "OBSERVACION", "Observacion", "OBS.1")

    proveedor = _proveedor_desde_hoja(sheet) or ""
    por_remito: dict[str, dict[str, Any]] = {}

    for _, row in df.iterrows():
        rem_raw = _celda_str(row.get(col_remito))
        if not rem_raw or not es_remito_oficial(rem_raw):
            continue
        norm = normalizar_remito(rem_raw)
        if not norm:
            continue

        ent = _normalizar_entregado(_celda_str(row.get(col_ent)) if col_ent else "")
        obs = _celda_str(row.get(col_obs)) if col_obs else ""
        f_ret = _celda_str(row.get(col_f_ret)) if col_f_ret else ""
        f_ent = _celda_str(row.get(col_f_ent)) if col_f_ent else ""
        ped = _celda_str(row.get(col_pedido)) if col_pedido else ""

        prev = por_remito.get(norm)
        if prev is None:
            por_remito[norm] = {
                "remito_norm": norm,
                "remito": rem_raw,
                "nro_pedido": ped,
                "proveedor": proveedor,
                "hoja_origen": sheet,
                "fecha_retiro": f_ret,
                "fecha_entrega_coord": f_ent,
                "entregado": ent,
                "observacion": obs,
            }
            continue

        # Agregar filas del mismo remito (varios SKU)
        if ent == "NO":
            prev["entregado"] = "NO"
        elif ent == "SI" and prev["entregado"] == "pendiente":
            prev["entregado"] = "SI"
        if obs and obs not in (prev.get("observacion") or ""):
            prev["observacion"] = "; ".join(
                x for x in (prev.get("observacion"), obs) if x
            )
        if f_ent and (not prev.get("fecha_entrega_coord") or f_ent > prev["fecha_entrega_coord"]):
            prev["fecha_entrega_coord"] = f_ent
        if f_ret and not prev.get("fecha_retiro"):
            prev["fecha_retiro"] = f_ret
        if ped and not prev.get("nro_pedido"):
            prev["nro_pedido"] = ped

    return list(por_remito.values())


def parse_cross_workbook(
    content: bytes,
    filename: str = "planilla.xlsx",
    *,
    solo_retirado: bool = True,
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Devuelve filas agregadas por remito_norm y nombres de hojas procesadas.
    Por defecto solo pestañas cuyo nombre contiene «Retirado».
    """
    buf = io.BytesIO(content)
    xl = pd.ExcelFile(buf)
    hojas_ok: list[str] = []
    filas: list[dict[str, Any]] = []
    por_remito: dict[str, dict[str, Any]] = {}

    for sheet in xl.sheet_names:
        if solo_retirado and not _es_hoja_retirado(sheet):
            continue
        buf.seek(0)
        chunk = _leer_hoja_retirado(buf, sheet)
        if not chunk:
            continue
        hojas_ok.append(sheet)
        for row in chunk:
            norm = row["remito_norm"]
            row["archivo_origen"] = filename
            row["raw_json"] = json.dumps(row, ensure_ascii=False, default=str)
            prev = por_remito.get(norm)
            if prev is None:
                por_remito[norm] = row
            else:
                if row.get("entregado") == "NO":
                    prev["entregado"] = "NO"
                elif row.get("entregado") == "SI" and prev.get("entregado") == "pendiente":
                    prev["entregado"] = "SI"
                if row.get("hoja_origen") and row["hoja_origen"] not in (
                    prev.get("hoja_origen") or ""
                ):
                    prev["hoja_origen"] = ", ".join(
                        sorted({prev.get("hoja_origen", ""), row["hoja_origen"]} - {""})
                    )

    filas = list(por_remito.values())
    return filas, hojas_ok


def listar_hojas_workbook(content: bytes) -> list[str]:
    return pd.ExcelFile(io.BytesIO(content)).sheet_names
