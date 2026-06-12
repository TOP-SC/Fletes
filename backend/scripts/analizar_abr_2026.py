"""Resumen archivos referencia abril 2026 (maestro Adrián)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

CARPETA = Path(r"C:\Users\juan.billiot\Desktop\4 ABR 2026")
OUT = Path(__file__).resolve().parents[2] / "data" / "analisis_abr_2026.json"


def _listar() -> list[Path]:
    return sorted(CARPETA.glob("*")) if CARPETA.is_dir() else []


def main() -> None:
    resumen: dict = {"carpeta": str(CARPETA), "archivos": [], "totales": {}}
    wamaro_filas = 0
    clp_filas_h1 = 0
    obs_valores: dict[str, int] = {}

    for p in _listar():
        info = {"nombre": p.name, "bytes": p.stat().st_size}
        try:
            if p.name.startswith("CLP"):
                xl = pd.ExcelFile(p)
                h1 = pd.read_excel(p, sheet_name=0)
                info["hojas"] = xl.sheet_names
                info["filas_hoja1"] = len(h1)
                clp_filas_h1 += len(h1)
                info["columnas_hoja1"] = list(h1.columns)[:12]
            elif p.name.startswith("WAMARO"):
                df = pd.read_excel(p)
                info["filas"] = len(df)
                wamaro_filas += len(df)
                if "obs" in df.columns:
                    for v in df["obs"].dropna().astype(str):
                        k = v.strip()[:40]
                        if k:
                            obs_valores[k] = obs_valores.get(k, 0) + 1
            elif "amba" in p.name.lower() and p.suffix == ".xlsx":
                xl = pd.ExcelFile(p)
                info["hojas"] = xl.sheet_names
                for sh in xl.sheet_names[:2]:
                    info[f"filas_{sh}"] = len(pd.read_excel(p, sheet_name=sh))
        except Exception as exc:
            info["error"] = str(exc)
        resumen["archivos"].append(info)

    resumen["totales"] = {
        "archivos": len(resumen["archivos"]),
        "wamaro_filas": wamaro_filas,
        "clp_filas_hoja1": clp_filas_h1,
        "obs_top": dict(sorted(obs_valores.items(), key=lambda x: -x[1])[:15]),
    }
    OUT.write_text(json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(resumen["totales"], ensure_ascii=False, indent=2))
    print(f"Guardado: {OUT}")


if __name__ == "__main__":
    main()
