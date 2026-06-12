"""
Cruce maestro app vs Adrián (abril 2026) por REMITO normalizado.
Compara campo a campo en casos comunes.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import settings
from app.services.maestro_service import MAESTRO_COLUMNAS
from app.services.remito_utils import normalizar_remito

CARPETA_ADR = Path(r"C:\Users\juan.billiot\Desktop\4 ABR 2026")
APP_XLSX_DEFAULT = Path(r"c:\Users\juan.billiot\Desktop\maestro_wamaro.xlsx")
OUT = ROOT.parent / "data" / "comparacion_remito_abr_2026.xlsx"

CAMPOS_TEXTO = (
    "DESTINATARIO",
    "LOCALIDAD",
    "PROVINCIA",
    "ZONA DESTINO",
    "DESCRIPCION ZONA DESTINO",
    "ARTICULOS",
)
CAMPOS_MONTO = ("LOGISTICA", "SEGURO", "GESTION", "ADICIONAL", "PRECIO NETO", "VALOR DECLARADO")
TOL_LOG_PCT = 0.15
TOL_LOG_ABS = 5000.0


def _norm_remito(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    parts = re.split(r"\s*\+\s*", str(v).strip())
    norms = [normalizar_remito(p.strip()) for p in parts if p.strip()]
    return "|".join(sorted(n for n in norms if n))


def _norm_text(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return re.sub(r"\s+", " ", str(v).strip().upper())


def _num(v) -> float | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _montos_iguales(ref: float | None, app: float | None, *, es_seguro: bool = False) -> bool | None:
    if ref is None and app is None:
        return None
    if ref is None or app is None:
        return False
    if es_seguro and abs(ref - 30) < 1 and abs(app - settings.seguro_fijo) < 1:
        return True  # regla distinta pero esperada
    diff = abs(ref - app)
    if diff < 1.0:
        return True
    if ref and diff / abs(ref) <= TOL_LOG_PCT:
        return True
    return diff <= TOL_LOG_ABS


def cargar_adrian() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in sorted(CARPETA_ADR.glob("*.xlsx")):
        name = path.name.upper()
        if "WAMARO TORTUGUITAS" not in name and not name.startswith("WAMARO SA"):
            continue
        df = pd.read_excel(path, sheet_name=0)
        if "REMITOS" not in df.columns:
            continue
        df = df.dropna(subset=["REMITOS"], how="all").copy()
        df["_archivo"] = path.name
        frames.append(df)
    if not frames:
        raise FileNotFoundError("Sin LOG WAMARO abril")
    out = pd.concat(frames, ignore_index=True)
    out["REMITO_N"] = out["REMITOS"].map(_norm_remito)
    return out[out["REMITO_N"] != ""].drop_duplicates("REMITO_N", keep="first")


def cargar_app(app_xlsx: Path) -> pd.DataFrame:
    if not app_xlsx.exists():
        raise FileNotFoundError(app_xlsx)
    frames = []
    for sh in pd.ExcelFile(app_xlsx).sheet_names:
        df = pd.read_excel(app_xlsx, sheet_name=sh)
        if "REMITOS" in df.columns and not df.empty:
            frames.append(df)
    out = pd.concat(frames, ignore_index=True)
    out["REMITO_N"] = out["REMITOS"].map(_norm_remito)
    return out[out["REMITO_N"] != ""].drop_duplicates("REMITO_N", keep="first")


def main() -> None:
    app_xlsx = Path(sys.argv[1]) if len(sys.argv) > 1 else APP_XLSX_DEFAULT
    adr = cargar_adrian()
    app = cargar_app(app_xlsx)
    comunes = sorted(set(adr["REMITO_N"]) & set(app["REMITO_N"]))
    solo_adr = sorted(set(adr["REMITO_N"]) - set(app["REMITO_N"]))
    solo_app = sorted(set(app["REMITO_N"]) - set(adr["REMITO_N"]))

    adr_i = adr.set_index("REMITO_N")
    app_i = app.set_index("REMITO_N")

    resumen_campos: list[dict] = []
    filas_detalle: list[dict] = []

    for campo in CAMPOS_TEXTO:
        ok = 0
        dist = 0
        vac = 0
        for rn in comunes:
            rv = _norm_text(adr_i.loc[rn].get(campo) if campo in adr_i.columns else "")
            av = _norm_text(app_i.loc[rn].get(campo) if campo in app_i.columns else "")
            if not rv and not av:
                vac += 1
            elif rv[:20] == av[:20] or (rv and av and (rv in av or av in rv)):
                ok += 1
            else:
                dist += 1
        resumen_campos.append(
            {
                "campo": campo,
                "iguales": ok,
                "distintos": dist,
                "ambos_vacios": vac,
                "pct_igual": round(100 * ok / max(1, len(comunes) - vac), 1),
            }
        )

    for campo in CAMPOS_MONTO:
        ok = dist = na = 0
        for rn in comunes:
            rv = _num(adr_i.loc[rn].get(campo) if campo in adr_i.columns else None)
            av = _num(app_i.loc[rn].get(campo) if campo in app_i.columns else None)
            cmp = _montos_iguales(rv, av, es_seguro=(campo == "SEGURO"))
            if cmp is None:
                na += 1
            elif cmp:
                ok += 1
            else:
                dist += 1
        resumen_campos.append(
            {
                "campo": campo,
                "iguales": ok,
                "distintos": dist,
                "ambos_vacios": na,
                "pct_igual": round(100 * ok / max(1, len(comunes) - na), 1),
            }
        )

    for rn in comunes:
        a, b = adr_i.loc[rn], app_i.loc[rn]
        difs = []
        for campo in CAMPOS_TEXTO:
            rv = _norm_text(a.get(campo))
            av = _norm_text(b.get(campo))
            if rv and av and rv[:20] != av[:20] and rv not in av and av not in rv:
                difs.append(campo)
        for campo in CAMPOS_MONTO:
            rv = _num(a.get(campo))
            av = _num(b.get(campo))
            if not _montos_iguales(rv, av, es_seguro=(campo == "SEGURO")):
                if rv is not None or av is not None:
                    difs.append(campo)
        filas_detalle.append(
            {
                "REMITO_N": rn,
                "REMITOS_ADR": a.get("REMITOS"),
                "REMITOS_APP": b.get("REMITOS"),
                "ARCHIVO_ADR": a.get("_archivo", ""),
                "TRANSPORTE_APP": b.get("TRANSPORTE", ""),
                "TRANSPORTE_ADR": a.get("TRANSPORTE", ""),
                "LOG_ADR": _num(a.get("LOGISTICA")),
                "LOG_APP": _num(b.get("LOGISTICA")),
                "PN_ADR": _num(a.get("PRECIO NETO")),
                "PN_APP": _num(b.get("PRECIO NETO")),
                "campos_distintos": ", ".join(difs) if difs else "OK",
                "n_difs": len(difs),
            }
        )

    det = pd.DataFrame(filas_detalle).sort_values("n_difs")
    res_cam = pd.DataFrame(resumen_campos)
    ok_total = int((det["n_difs"] == 0).sum())
    pocas = int((det["n_difs"] <= 2).sum())

    resumen = pd.DataFrame(
        [
            {"metrica": "Casos Adrian (remito único)", "valor": len(adr)},
            {"metrica": "Casos app export (remito único)", "valor": len(app)},
            {"metrica": "Cruce por remito", "valor": len(comunes)},
            {"metrica": "% cobertura Adrian", "valor": round(100 * len(comunes) / len(adr), 1)},
            {"metrica": "Solo Adrian", "valor": len(solo_adr)},
            {"metrica": "Solo app", "valor": len(solo_app)},
            {"metrica": "Casos 100% iguales (todos campos)", "valor": ok_total},
            {"metrica": "Casos con <=2 diferencias", "valor": pocas},
            {"metrica": "Seguro app configurado", "valor": settings.seguro_fijo},
        ]
    )

    with pd.ExcelWriter(OUT, engine="openpyxl") as w:
        resumen.to_excel(w, sheet_name="resumen", index=False)
        res_cam.to_excel(w, sheet_name="por_campo", index=False)
        det.to_excel(w, sheet_name="detalle_cruce", index=False)
        pd.DataFrame({"REMITO_N": solo_adr[:500]}).to_excel(w, sheet_name="solo_adrian", index=False)
        pd.DataFrame({"REMITO_N": solo_app[:500]}).to_excel(w, sheet_name="solo_app_muestra", index=False)

    print("=== CRUCE POR REMITO (app vs Adrian abril) ===")
    print(resumen.to_string(index=False))
    print("\n--- Por campo (casos comunes) ---")
    print(res_cam.to_string(index=False))
    print(f"\nDetalle: {OUT}")


if __name__ == "__main__":
    main()
