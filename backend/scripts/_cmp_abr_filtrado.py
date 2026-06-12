"""Cruce Adrian abril vs export app filtrado a entregas abril 2026."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.comparar_por_remito_abr import (
    CAMPOS_MONTO,
    _montos_iguales,
    _norm_remito,
    _norm_text,
    _num,
    cargar_adrian,
)

APP = Path(r"c:\Users\juan.billiot\Desktop\maestro_wamaro (1).xlsx")


def main() -> None:
    adr = cargar_adrian()
    app = pd.read_excel(APP, sheet_name="Wamaro Tortuguitas")
    app["REMITO_N"] = app["REMITOS"].map(_norm_remito)
    col = "FECHA ENTREGA" if "FECHA ENTREGA" in app.columns else "FECHA"
    app["_f"] = pd.to_datetime(app[col], errors="coerce")
    app_abr = app[(app["_f"] >= "2026-04-01") & (app["_f"] <= "2026-04-30")]
    app_abr = app_abr[app_abr["REMITO_N"] != ""].drop_duplicates("REMITO_N", keep="first")

    comunes = sorted(set(adr["REMITO_N"]) & set(app_abr["REMITO_N"]))
    pct = round(100 * len(comunes) / max(1, len(adr)), 1)

    print("=== APP ABRIL 2026 (entrega) vs ADRIAN ===")
    print(f"Adrian remitos: {len(adr)}")
    print(f"App abril remitos: {len(app_abr)}")
    print(f"Cruce: {len(comunes)} ({pct}% de Adrian)")
    print(f"Solo Adrian: {len(set(adr['REMITO_N']) - set(app_abr['REMITO_N']))}")
    print(f"Solo app abril: {len(set(app_abr['REMITO_N']) - set(adr['REMITO_N']))}")

    adr_i = adr.set_index("REMITO_N")
    app_i = app_abr.set_index("REMITO_N")
    campos = ["DESTINATARIO", "LOCALIDAD", "LOGISTICA", "PRECIO NETO", "BULTOS", "TRANSPORTE"]
    for campo in campos:
        if campo not in app_i.columns:
            continue
        ok = 0
        for rn in comunes:
            rv = adr_i.loc[rn].get(campo) if campo in adr_i.columns else None
            av = app_i.loc[rn].get(campo)
            if campo in CAMPOS_MONTO or campo == "BULTOS":
                if _montos_iguales(_num(rv), _num(av)):
                    ok += 1
            else:
                rt, at = _norm_text(rv), _norm_text(av)
                if rt[:20] == at[:20] or (rt and rt in at) or (at and at in rt):
                    ok += 1
        n = len(comunes)
        print(f"  {campo}: {ok}/{n} ({round(100 * ok / max(1, n), 1)}%)")


if __name__ == "__main__":
    main()
