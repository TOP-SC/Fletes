"""Export ARCA / costos de flete por provincia."""

from __future__ import annotations

from io import BytesIO
from typing import Any

import pandas as pd
from openpyxl.styles import Font, PatternFill
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Envio
from app.services.money_utils import EXCEL_NUM_FMT_PESOS, aplicar_formato_moneda_hoja
from app.services.rules_service import es_amba_gba

FILL_HEADER = PatternFill(start_color="E2E9F4", end_color="E2E9F4", fill_type="solid")
FONT_HEADER = Font(bold=True, color="2C3E50")


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
            # Separar CABA de GBA/AMBA según regla de negocio
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


def export_costos_por_provincia(db: Session) -> bytes:
    """
    Excel estilo presentación contable / ARCA:
    - Hoja Interior (provincias con costo tarifario)
    - Hoja CABA_AMBA (agrupado)
    """
    interior = _agregar_por_provincia(db, interior=True)
    amba = _agregar_por_provincia(db, interior=False)

    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
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
            # Total
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
