"""Analiza carpeta 4 ABR 2026 completa vs app."""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.remito_utils import normalizar_remito

ABR = Path(r"C:\Users\juan.billiot\Desktop\4 ABR 2026")


def norm_remito(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    parts = re.split(r"\s*\+\s*", str(v).strip())
    return "|".join(sorted(normalizar_remito(p.strip()) for p in parts if p.strip()))


def find_col(cols, names):
    for c in cols:
        if str(c).upper().strip() in names:
            return c
    return None


def clasificar(nombre: str) -> str:
    nu = nombre.upper()
    if nu.startswith("WAMARO TORTUGUITAS"):
        return "LOG Tortuguitas"
    if nu.startswith("WAMARO SA"):
        return "LOG SA"
    if "CLP" in nu:
        return "Prefactura CLP"
    if "CENTRO DE COSTOS" in nu:
        return "Centro costos"
    if "VIAJES" in nu:
        return "Viajes amba"
    if "AMBA" in nu:
        return "Entregas amba (qmt)"
    return "Otro"


def main() -> None:
    by_tipo: dict[str, dict] = defaultdict(
        lambda: {"files": 0, "filas": 0, "remitos": set(), "claves": set()}
    )
    all_remitos: set[str] = set()
    all_claves: set[str] = set()

    for p in sorted(ABR.glob("*")):
        if p.suffix.lower() not in (".xlsx", ".xls"):
            continue
        try:
            xl = pd.ExcelFile(p)
            df = pd.read_excel(p, sheet_name=xl.sheet_names[0])
        except Exception as exc:
            print(f"ERROR {p.name}: {exc}")
            continue

        tipo = clasificar(p.name)
        rc = find_col(df.columns, {"REMITOS", "REMITO", "NRO REMITO", "REMITO ENTREGA"})
        ec = find_col(df.columns, {"ENVIO", "NRO PEDIDO", "NRO PEDIDO ", "PEDIDO", "ENTREGA"})

        rem: set[str] = set()
        clv: set[str] = set()
        if rc:
            for v in df[rc].dropna():
                rn = norm_remito(v)
                if rn:
                    rem.add(rn)
                    clv.add(f"R:{rn}")
        if ec:
            for v in df[ec].dropna():
                s = str(v).strip()
                if s.endswith(".0"):
                    s = s[:-2]
                if s:
                    clv.add(f"E:{s}")

        d = by_tipo[tipo]
        d["files"] += 1
        d["filas"] += len(df)
        d["remitos"] |= rem
        d["claves"] |= clv
        all_remitos |= rem
        all_claves |= clv

    print("=== CARPETA 4 ABR 2026 — POR TIPO ===")
    total_filas = 0
    for t, d in sorted(by_tipo.items()):
        total_filas += d["filas"]
        print(
            f"{t:22} | {d['files']:2} arch | {d['filas']:5} filas | "
            f"{len(d['remitos']):4} remitos | {len(d['claves']):5} claves"
        )

    print(f"\nTOTAL filas (suma archivos, hay solapamiento): {total_filas}")
    print(f"TOTAL remitos unicos (toda la carpeta): {len(all_remitos)}")
    print(f"TOTAL claves remito/envio (toda la carpeta): {len(all_claves)}")

    log_r = by_tipo["LOG Tortuguitas"]["remitos"] | by_tipo["LOG SA"]["remitos"]
    clp_r = by_tipo["Prefactura CLP"]["remitos"]
    amba_r = by_tipo["Entregas amba (qmt)"]["remitos"]

    print(f"\nLOG WAMARO remitos: {len(log_r)}")
    print(f"CLP remitos: {len(clp_r)}")
    print(f"Entregas amba remitos: {len(amba_r)}")
    print(f"LOG + CLP remitos (union): {len(log_r | clp_r)}")
    print(f"LOG inter CLP: {len(log_r & clp_r)}")
    print(f"Solo CLP (no en LOG): {len(clp_r - log_r)}")
    print(f"Solo LOG (no en CLP): {len(log_r - clp_r)}")

    # App DB
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session
    from app.models import Envio
    from app.services.remito_maestro import remito_oficial_envio

    db_path = ROOT.parent / "data" / "fletes.db"
    db = Session(create_engine(f"sqlite:///{db_path}"))
    envios = list(db.scalars(select(Envio)).all())
    app_rem: set[str] = set()
    app_ped: set[str] = set()
    for e in envios:
        o = remito_oficial_envio(e)
        if o:
            app_rem.add(normalizar_remito(o))
        if e.nro_pedido:
            app_ped.add(str(e.nro_pedido).strip())
    db.close()

    union_adrian = all_remitos
    print("\n=== VS APP (mismo Tango importado) ===")
    print(f"App remitos oficiales: {len(app_rem)}")
    print(f"App pedidos: {len(app_ped)}")
    print(f"App renglones Tango: {len(envios)}")
    print(f"Carpeta Adrian remitos en app: {len(union_adrian & app_rem)}")
    print(f"Solo carpeta Adrian (no en app): {len(union_adrian - app_rem)}")
    print(f"Solo app (no en carpeta Adrian): {len(app_rem - union_adrian)}")
    print(f"Cobertura app sobre carpeta: {100*len(union_adrian & app_rem)/max(1,len(union_adrian)):.1f}%")


if __name__ == "__main__":
    main()
