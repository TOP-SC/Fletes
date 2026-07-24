"""Parser de planillas cross (Retirado por … / Cross Salta|Jujuy|Tucumán)."""

from __future__ import annotations

import io
import json
import re
from datetime import date, datetime
from typing import Any

import pandas as pd

from app.services.money_utils import parse_money
from app.services.remito_utils import es_remito_oficial, normalizar_remito

_RE_FECHA = re.compile(
    r"^\d{1,4}[-/]\d{1,2}[-/]\d{1,4}(\s+\d{1,2}:\d{2}(:\d{2})?)?$"
)


def _es_hoja_cross_util(nombre: str) -> bool:
    """
    Pestañas operativas a importar.
    - «Retirado por …» (histórico)
    - «Cross Salta / Jujuy / Tucumán …» (Drive: col A = fecha retiro, B = remito)
    """
    n = (nombre or "").strip().lower()
    if "retirado" in n:
        return True
    if n.startswith("cross ") or n.startswith("cross_"):
        return True
    return False


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
    # Hojas «Cross Salta/Jujuy/Tucuman» → última milla ALFARO
    if n.startswith("CROSS") and any(
        x in n for x in ("SALTA", "JUJUY", "TUCUMAN", "TUCUMÁN")
    ):
        return "ALFARO"
    return None


def _detectar_header(df_raw: pd.DataFrame) -> int | None:
    for i in range(min(12, len(df_raw))):
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


def _parece_fecha(valor: str) -> bool:
    s = (valor or "").strip()
    if not s:
        return False
    if _RE_FECHA.match(s):
        return True
    # Excel serial / datetime ya stringifyado
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        return True
    return False


def _elegir_columna_remito(df: pd.DataFrame) -> str | None:
    """
    Elige la columna REMITO por nombre y valida con muestra de valores.
    Evita tomar «FECHA DE RETIRO» (col A en Cross Salta/Jujuy) por error.
    """
    candidatas: list[str] = []
    por_nombre = _col_por_alias(df, "REMITO", "NRO REMITO", "N° REMITO", "NUMERO REMITO")
    if por_nombre:
        candidatas.append(por_nombre)
    for c in df.columns:
        if c not in candidatas:
            candidatas.append(c)

    mejor: str | None = None
    mejor_score = -1
    for col in candidatas:
        score = 0
        muestras = 0
        for v in df[col].head(40).tolist():
            s = _celda_str(v)
            if not s:
                continue
            muestras += 1
            if _parece_fecha(s):
                score -= 3
                continue
            if es_remito_oficial(s):
                score += 5
            elif re.match(r"^R\d", s.upper().replace("-", "").replace(" ", "")):
                score += 2
        if muestras == 0:
            continue
        # Priorizar la que se llama REMITO si empata
        if por_nombre and col == por_nombre:
            score += 2
        if score > mejor_score:
            mejor_score = score
            mejor = col
    if mejor is None or mejor_score <= 0:
        return por_nombre  # fallback nombre aunque score flojo
    return mejor


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

    col_remito = _elegir_columna_remito(df)
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
    col_cli = _col_por_alias(
        df, "CODIGO DE CLIENTE", "CODIGO CLIENTE", "CÓDIGO CLIENTE", "COD CLIENTE"
    )
    col_imp = _col_por_alias(
        df,
        "IMPORTE",
        "COSTO",
        "PRECIO",
        "FACTURADO",
        "MONTO",
        "TOTAL",
        "LOGISTICA",
        "LOGÍSTICA",
    )

    proveedor = _proveedor_desde_hoja(sheet) or ""
    por_remito: dict[str, dict[str, Any]] = {}

    for _, row in df.iterrows():
        rem_raw = _celda_str(row.get(col_remito))
        if not rem_raw or _parece_fecha(rem_raw) or not es_remito_oficial(rem_raw):
            continue
        norm = normalizar_remito(rem_raw)
        if not norm:
            continue

        ent = _normalizar_entregado(_celda_str(row.get(col_ent)) if col_ent else "")
        obs = _celda_str(row.get(col_obs)) if col_obs else ""
        f_ret = _celda_str(row.get(col_f_ret)) if col_f_ret else ""
        f_ent = _celda_str(row.get(col_f_ent)) if col_f_ent else ""
        ped = _celda_str(row.get(col_pedido)) if col_pedido else ""
        cod_cli = _celda_str(row.get(col_cli)) if col_cli else ""
        importe = None
        if col_imp:
            importe = parse_money(row.get(col_imp))

        prev = por_remito.get(norm)
        if prev is None:
            por_remito[norm] = {
                "remito_norm": norm,
                "remito": rem_raw,
                "nro_pedido": ped,
                "cod_cliente": cod_cli or None,
                "importe_facturado": importe,
                "proveedor": proveedor,
                "hoja_origen": sheet,
                "fecha_retiro": f_ret,
                "fecha_entrega_coord": f_ent,
                "entregado": ent,
                "observacion": obs,
            }
            continue

        if ent == "NO":
            prev["entregado"] = "NO"
        elif ent == "SI" and prev["entregado"] == "pendiente":
            prev["entregado"] = "SI"
        if obs and obs not in (prev.get("observacion") or ""):
            prev["observacion"] = "; ".join(
                x for x in (prev.get("observacion"), obs) if x
            )
        if f_ent and (
            not prev.get("fecha_entrega_coord") or f_ent > prev["fecha_entrega_coord"]
        ):
            prev["fecha_entrega_coord"] = f_ent
        if f_ret and not prev.get("fecha_retiro"):
            prev["fecha_retiro"] = f_ret
        if ped and not prev.get("nro_pedido"):
            prev["nro_pedido"] = ped
        if cod_cli and not prev.get("cod_cliente"):
            prev["cod_cliente"] = cod_cli
        if importe is not None:
            prev["importe_facturado"] = (prev.get("importe_facturado") or 0) + importe

    return list(por_remito.values())


def parse_cross_workbook(
    content: bytes,
    filename: str = "planilla.xlsx",
    *,
    solo_retirado: bool = True,
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Devuelve filas agregadas por remito_norm y nombres de hojas procesadas.

    ``solo_retirado=True`` (default) incluye pestañas Retirado **y** Cross Provincia
    (Salta/Jujuy/Tucumán), donde el remito suele estar en columna B.
    """
    buf = io.BytesIO(content)
    xl = pd.ExcelFile(buf)
    hojas_ok: list[str] = []
    por_remito: dict[str, dict[str, Any]] = {}

    for sheet in xl.sheet_names:
        if solo_retirado and not _es_hoja_cross_util(sheet):
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
                elif (
                    row.get("entregado") == "SI"
                    and prev.get("entregado") == "pendiente"
                ):
                    prev["entregado"] = "SI"
                if row.get("cod_cliente") and not prev.get("cod_cliente"):
                    prev["cod_cliente"] = row["cod_cliente"]
                if row.get("importe_facturado") is not None:
                    prev["importe_facturado"] = row["importe_facturado"]
                if row.get("hoja_origen") and row["hoja_origen"] not in (
                    prev.get("hoja_origen") or ""
                ):
                    prev["hoja_origen"] = ", ".join(
                        sorted(
                            {prev.get("hoja_origen", ""), row["hoja_origen"]} - {""}
                        )
                    )

    return list(por_remito.values()), hojas_ok


def listar_hojas_workbook(content: bytes) -> list[str]:
    return pd.ExcelFile(io.BytesIO(content)).sheet_names
