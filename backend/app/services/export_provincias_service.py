"""Export ARCA / costos de flete por provincia (formato contable Marcela)."""

from __future__ import annotations

from io import BytesIO
from typing import Any

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Envio
from app.services.money_utils import EXCEL_NUM_FMT_PESOS, aplicar_formato_moneda_hoja
from app.services.rules_service import es_amba_gba

FILL_HEADER = PatternFill(start_color="E2E9F4", end_color="E2E9F4", fill_type="solid")
FONT_HEADER = Font(bold=True, color="2C3E50")
FILL_EMPRESA = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
FONT_EMPRESA = Font(bold=True, color="FFFFFF", size=14)

# Orden típico de columnas de provincia en listados contables TOP
_PROVINCIAS_COLS = [
    "CABA",
    "Buenos Aires",
    "Catamarca",
    "Chaco",
    "Chubut",
    "Córdoba",
    "Corrientes",
    "Entre Ríos",
    "Formosa",
    "Jujuy",
    "La Pampa",
    "La Rioja",
    "Mendoza",
    "Misiones",
    "Neuquén",
    "Río Negro",
    "Salta",
    "San Juan",
    "San Luis",
    "Santa Cruz",
    "Santa Fe",
    "Santiago del Estero",
    "Tierra del Fuego",
    "Tucumán",
    "AMBA / GBA",
]


def _nombre_provincia_contable(
    provincia: str | None,
    localidad: str | None,
    cp: str | None,
    *,
    excluir_planilla: bool,
) -> str:
    if excluir_planilla or es_amba_gba(provincia, localidad, cp):
        prov_u = (provincia or "").upper()
        loc_u = (localidad or "").upper()
        if "CABA" in prov_u or "CAPITAL" in prov_u or "CABA" in loc_u:
            return "CABA"
        return "AMBA / GBA"
    nombre = (provincia or "Sin provincia").strip()
    # Normalizar acentos comunes a rótulos del listado
    mapa = {
        "CORDOBA": "Córdoba",
        "ENTRE RIOS": "Entre Ríos",
        "NEUQUEN": "Neuquén",
        "RIO NEGRO": "Río Negro",
        "TUCUMAN": "Tucumán",
        "CIUDAD AUTONOMA DE BUENOS AIRES": "CABA",
        "CAPITAL FEDERAL": "CABA",
    }
    key = "".join(
        c
        for c in nombre.upper()
        if c.isalnum() or c.isspace()
    )
    # strip accents roughly
    import unicodedata

    key_n = "".join(
        c for c in unicodedata.normalize("NFD", key) if unicodedata.category(c) != "Mn"
    )
    for k, v in mapa.items():
        if k in key_n:
            return v
    return nombre.title() if nombre else "Sin provincia"


def _agregar_por_provincia(
    db: Session,
    *,
    interior: bool,
) -> list[dict[str, Any]]:
    """Interior: excluir_planilla=False. AMBA/CABA: excluir_planilla=True (retiro/AMBA)."""
    base = (
        select(
            Envio.provincia.label("provincia"),
            Envio.localidad.label("localidad"),
            Envio.cp.label("cp"),
            Envio.remito_norm.label("remito_norm"),
            func.max(func.coalesce(Envio.costo_tarifario, 0.0)).label("costo"),
        )
        .where(
            Envio.excluir_planilla.is_(not interior),
            Envio.remito_norm.isnot(None),
            Envio.remito_norm != "",
        )
        .group_by(Envio.provincia, Envio.localidad, Envio.cp, Envio.remito_norm)
    )
    rows = db.execute(base).all()
    acum: dict[str, dict[str, Any]] = {}
    for prov, loc, cp, _rem, costo in rows:
        nombre = (prov or "Sin provincia").strip()
        if not interior:
            if es_amba_gba(prov, loc, cp):
                prov_u = (prov or "").upper()
                loc_u = (loc or "").upper()
                if "CABA" in prov_u or "CAPITAL" in prov_u or "CABA" in loc_u:
                    nombre = "CABA"
                else:
                    nombre = "AMBA / GBA"
            else:
                continue
        bucket = acum.setdefault(
            nombre, {"provincia": nombre, "remitos": 0, "costo": 0.0}
        )
        bucket["remitos"] += 1
        bucket["costo"] += float(costo or 0)
    out = sorted(acum.values(), key=lambda x: x["costo"], reverse=True)
    for row in out:
        row["costo"] = round(float(row["costo"]), 2)
    return out


def _detalle_imputacion(db: Session) -> list[dict[str, Any]]:
    """Una fila por remito con monto imputado a la columna de provincia."""
    q = (
        select(
            Envio.remito,
            Envio.remito_norm,
            Envio.nro_pedido,
            Envio.fecha_entrega,
            Envio.razon_social,
            Envio.provincia,
            Envio.localidad,
            Envio.cp,
            Envio.excluir_planilla,
            func.max(func.coalesce(Envio.costo_tarifario, 0.0)).label("costo"),
        )
        .where(Envio.remito_norm.isnot(None), Envio.remito_norm != "")
        .group_by(
            Envio.remito,
            Envio.remito_norm,
            Envio.nro_pedido,
            Envio.fecha_entrega,
            Envio.razon_social,
            Envio.provincia,
            Envio.localidad,
            Envio.cp,
            Envio.excluir_planilla,
        )
    )
    rows = db.execute(q).all()
    out: list[dict[str, Any]] = []
    for rem, rem_n, pedido, fecha, cliente, prov, loc, cp, excl, costo in rows:
        monto = round(float(costo or 0), 2)
        if monto <= 0:
            continue
        col_prov = _nombre_provincia_contable(
            prov, loc, cp, excluir_planilla=bool(excl)
        )
        fila: dict[str, Any] = {
            "Fecha": fecha or "",
            "Remito": rem or rem_n or "",
            "Pedido": pedido or "",
            "Cliente": cliente or "",
            "Provincia": col_prov,
            "Total": monto,
        }
        for p in _PROVINCIAS_COLS:
            fila[p] = monto if p == col_prov else None
        # Si la provincia no está en el catálogo fijo, sumar a Total solo
        if col_prov not in _PROVINCIAS_COLS:
            fila[col_prov] = monto
        out.append(fila)
    return out


def export_costos_por_provincia(db: Session) -> bytes:
    """
    Excel estilo presentación contable / ARCA (Marcela):
    - Datos de la Empresa (portada)
    - Listado por Imputación Contable (filas = remitos, columnas = provincias)
    - Interior / CABA_AMBA (resúmenes)
    """
    interior = _agregar_por_provincia(db, interior=True)
    amba = _agregar_por_provincia(db, interior=False)
    detalle = _detalle_imputacion(db)

    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        # Portada
        ws0 = writer.book.create_sheet("Datos de la Empresa", 0)
        ws0["A1"] = "SOMMIER CENTER / TOP — Control de Fletes"
        ws0["A1"].font = FONT_EMPRESA
        ws0["A1"].fill = FILL_EMPRESA
        ws0.merge_cells("A1:F1")
        ws0["A3"] = "Listado de costos de flete por provincia"
        ws0["A4"] = "Uso: imputación contable / ARCA"
        ws0["A6"] = "Hojas:"
        ws0["A7"] = "1) Listado por Imputación Contable — detalle remito × provincia"
        ws0["A8"] = "2) Interior — resumen provincias interior"
        ws0["A9"] = "3) CABA_AMBA — resumen CABA / AMBA-GBA"
        ws0.column_dimensions["A"].width = 70

        # Listado estilo Marcela
        extra_prov = sorted(
            {
                k
                for row in detalle
                for k in row
                if k
                not in (
                    "Fecha",
                    "Remito",
                    "Pedido",
                    "Cliente",
                    "Provincia",
                    "Total",
                    *_PROVINCIAS_COLS,
                )
            }
        )
        cols_detalle = [
            "Fecha",
            "Remito",
            "Pedido",
            "Cliente",
            "Provincia",
            "Total",
            *_PROVINCIAS_COLS,
            *extra_prov,
        ]
        df_det = pd.DataFrame(detalle, columns=cols_detalle)
        if df_det.empty:
            df_det = pd.DataFrame(columns=cols_detalle)
        df_det.to_excel(writer, index=False, sheet_name="Listado por Imputación Contable")
        ws_det = writer.sheets["Listado por Imputación Contable"]
        for col in range(1, len(cols_detalle) + 1):
            cell = ws_det.cell(row=1, column=col)
            cell.font = FONT_HEADER
            cell.fill = FILL_HEADER
            cell.alignment = Alignment(wrap_text=True, horizontal="center")
        aplicar_formato_moneda_hoja(ws_det, cols_detalle)
        if not df_det.empty:
            total_row = len(df_det) + 2
            ws_det.cell(row=total_row, column=1, value="TOTAL")
            total_cell = ws_det.cell(
                row=total_row,
                column=6,
                value=round(float(df_det["Total"].sum()), 2),
            )
            total_cell.number_format = EXCEL_NUM_FMT_PESOS
            total_cell.font = Font(bold=True)

        for nombre, filas in (("Interior", interior), ("CABA_AMBA", amba)):
            df = pd.DataFrame(filas, columns=["provincia", "remitos", "costo"])
            if df.empty:
                df = pd.DataFrame(columns=["provincia", "remitos", "costo"])
            df.to_excel(writer, index=False, sheet_name=nombre)
            ws = writer.sheets[nombre]
            for col in range(1, 4):
                cell = ws.cell(row=1, column=col)
                cell.font = FONT_HEADER
                cell.fill = FILL_HEADER
            if not df.empty:
                total_row = len(df) + 2
                ws.cell(row=total_row, column=1, value="TOTAL")
                ws.cell(row=total_row, column=2, value=int(df["remitos"].sum()))
                total_cell = ws.cell(
                    row=total_row, column=3, value=round(float(df["costo"].sum()), 2)
                )
                total_cell.number_format = EXCEL_NUM_FMT_PESOS
                for col in range(1, 4):
                    ws.cell(row=total_row, column=col).font = Font(bold=True)
            aplicar_formato_moneda_hoja(ws, list(df.columns))
    buf.seek(0)
    return buf.getvalue()
