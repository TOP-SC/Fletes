"""Compara maestro manual WAMARO SA (1 abr 2026) vs app."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import SessionLocal
from app.models import Envio
from app.services.envio_query_service import cargar_envios_filtrados
from app.services.fecha_utils import periodo_mes_solo
from app.services.maestro_service import MAESTRO_COLUMNAS, _zona_destino, construir_maestro
from app.services.remito_utils import normalizar_remito
from app.services.tarifario_version_service import TarifarioContext
from sqlalchemy import select

MANUAL = Path(r"c:\Users\juan.billiot\Desktop\4 ABR 2026\WAMARO SA - 01_04_2026.xlsx")
OUT = ROOT.parent / "data" / "comparacion_sa_abr_2026.xlsx"


def norm_remito(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    s = str(v).strip()
    parts = re.split(r"\s*\+\s*", s)
    norms = [normalizar_remito(p.strip()) for p in parts if p.strip()]
    return "|".join(sorted(n for n in norms if n))


def norm_envio(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    s = str(v).strip()
    return s[:-2] if s.endswith(".0") else s


def main() -> None:
    manual = pd.read_excel(MANUAL, sheet_name=0)
    manual = manual.dropna(subset=["ENVIO"]).copy()
    manual["ENVIO_N"] = manual["ENVIO"].map(norm_envio)
    manual["REMITO_N"] = manual["REMITOS"].map(norm_remito)

    db = SessionLocal()
    try:
        total = db.scalar(select(Envio.id).limit(1))
        n_env = db.query(Envio).count()
        desde, hasta = periodo_mes_solo(2026, 4)
        envios_abr = cargar_envios_filtrados(
            db, fecha_desde=desde, fecha_hasta=hasta, campo_fecha="cualquiera"
        )
        ctx = TarifarioContext(db)
        filas = construir_maestro(
            envios_abr, origen="sa", incluir_excluidos=True, tarifario_ctx=ctx, db=db
        )
        app_sa = pd.DataFrame([{c: f.get(c) for c in MAESTRO_COLUMNAS} for f in filas])
        if not app_sa.empty:
            app_sa["ENVIO_N"] = app_sa["ENVIO"].map(norm_envio)
            app_sa["REMITO_N"] = app_sa["REMITOS"].map(norm_remito)

        # cruce por remito (R) y por envio
        claves_m = set(manual["REMITO_N"]) | set(manual["ENVIO_N"])
        claves_m.discard("")
        if not app_sa.empty:
            claves_a = set(app_sa["REMITO_N"]) | set(app_sa["ENVIO_N"])
            claves_a.discard("")
            en_ambos_r = set(manual["REMITO_N"]) & set(app_sa["REMITO_N"])
            en_ambos_r.discard("")
            en_ambos_e = set(manual["ENVIO_N"]) & set(app_sa["ENVIO_N"])
            en_ambos_e.discard("")
        else:
            claves_a = set()
            en_ambos_r = set()
            en_ambos_e = set()

        # zonas manual vs heuristica
        zonas = []
        for _, r in manual.drop_duplicates(["LOCALIDAD", "PROVINCIA"]).iterrows():
            z, d = _zona_destino(r["PROVINCIA"], r["LOCALIDAD"], False)
            zonas.append(
                {
                    "LOCALIDAD": r["LOCALIDAD"],
                    "PROVINCIA": r["PROVINCIA"],
                    "ZONA_MANUAL": str(r["ZONA DESTINO"]).strip(),
                    "DESC_MANUAL": str(r["DESCRIPCION ZONA DESTINO"]).strip(),
                    "ZONA_APP": z,
                    "DESC_APP": d,
                }
            )
        df_zonas = pd.DataFrame(zonas)

        resumen = pd.DataFrame(
            [
                {"metrica": "Filas manual (sin total)", "valor": len(manual)},
                {"metrica": "Envios unicos manual", "valor": manual["ENVIO_N"].nunique()},
                {"metrica": "Filas app SA abril", "valor": len(app_sa)},
                {"metrica": "Envios en DB total", "valor": n_env},
                {"metrica": "Envios abril cargados", "valor": len(envios_abr)},
                {"metrica": "Cruce por ENVIO", "valor": len(en_ambos_e)},
                {"metrica": "Cruce por REMITO_N", "valor": len(en_ambos_r)},
                {"metrica": "Manual con remito X (-0117)", "valor": manual["REMITOS"].str.contains("-0117", na=False).sum()},
                {"metrica": "Manual filas combinadas X+R", "valor": manual["REMITOS"].str.contains(r" \+ ", regex=True).sum()},
            ]
        )

        with pd.ExcelWriter(OUT, engine="openpyxl") as w:
            resumen.to_excel(w, sheet_name="resumen", index=False)
            manual.to_excel(w, sheet_name="manual", index=False)
            if not app_sa.empty:
                app_sa.to_excel(w, sheet_name="app_sa_abril", index=False)
            df_zonas.to_excel(w, sheet_name="zonas", index=False)

        print(resumen.to_string(index=False))
        print(f"\nExportado: {OUT}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
