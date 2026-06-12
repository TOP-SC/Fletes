"""Compara maestro exportado app vs LOG WAMARO abril 2026 (Adrián)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import settings
from app.services.remito_utils import normalizar_remito

CARPETA_ADR = Path(r"C:\Users\juan.billiot\Desktop\4 ABR 2026")
APP_XLSX_DEFAULT = Path(r"c:\Users\juan.billiot\Desktop\maestro_wamaro.xlsx")
OUT = ROOT.parent / "data" / "comparacion_abr_export_2026.xlsx"


def _norm_envio(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    s = str(v).strip()
    return s[:-2] if s.endswith(".0") else s


def _norm_remito(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    parts = re.split(r"\s*\+\s*", str(v).strip())
    norms = [normalizar_remito(p.strip()) for p in parts if p.strip()]
    return "|".join(sorted(n for n in norms if n))


def _num(v) -> float | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def cargar_adrian() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in sorted(CARPETA_ADR.glob("*.xlsx")):
        name = path.name.upper()
        if "WAMARO TORTUGUITAS" not in name and not name.startswith("WAMARO SA"):
            continue
        df = pd.read_excel(path, sheet_name=0)
        if "ENVIO" not in df.columns:
            continue
        df = df.dropna(subset=["ENVIO"]).copy()
        df["_origen"] = "tortu" if "TORTUGUITAS" in name else "sa"
        df["_archivo"] = path.name
        frames.append(df)
    if not frames:
        raise FileNotFoundError("Sin maestros WAMARO en carpeta abril")
    out = pd.concat(frames, ignore_index=True)
    out["ENVIO_N"] = out["ENVIO"].map(_norm_envio)
    out["REMITO_N"] = out["REMITOS"].map(_norm_remito)
    out["CLAVE"] = out.apply(lambda r: r["REMITO_N"] or r["ENVIO_N"], axis=1)
    return out


def cargar_app(app_xlsx: Path) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    xl = pd.ExcelFile(app_xlsx)
    for sh in xl.sheet_names:
        df = pd.read_excel(app_xlsx, sheet_name=sh)
        if df.empty or "ENVIO" not in df.columns:
            continue
        df = df.dropna(subset=["ENVIO"], how="all").copy()
        df["_hoja"] = sh
        df["_origen"] = "sa" if "sa" in sh.lower().replace("á", "a") else "tortu"
        frames.append(df)
    out = pd.concat(frames, ignore_index=True)
    out["ENVIO_N"] = out["ENVIO"].map(_norm_envio)
    out["REMITO_N"] = out["REMITOS"].map(_norm_remito)
    out["CLAVE"] = out.apply(lambda r: r["REMITO_N"] or r["ENVIO_N"], axis=1)
    return out


def comparar(ref: pd.DataFrame, app: pd.DataFrame) -> dict:
    ref_u = ref.drop_duplicates("CLAVE", keep="first")
    app_u = app.drop_duplicates("CLAVE", keep="first")
    ref_keys = set(ref_u["CLAVE"]) - {""}
    app_keys = set(app_u["CLAVE"]) - {""}
    comunes = ref_keys & app_keys
    solo_ref = ref_keys - app_keys
    solo_app = app_keys - ref_keys

    ref_idx = ref_u.set_index("CLAVE")
    app_idx = app_u.set_index("CLAVE")

    tol_pct, tol_abs = 0.15, 5000.0
    match_log = match_prov = match_transp = 0
    dif_log: list[dict] = []
    dif_prov: list[dict] = []

    for clave in comunes:
        r, a = ref_idx.loc[clave], app_idx.loc[clave]
        rp = str(r.get("PROVINCIA") or "").strip().upper()[:12]
        ap = str(a.get("PROVINCIA") or "").strip().upper()[:12]
        if rp and ap and rp[:6] == ap[:6]:
            match_prov += 1
        elif rp and ap:
            dif_prov.append({"CLAVE": clave, "REF": rp, "APP": ap})

        rt = str(r.get("TRANSPORTE") or r.get("OBLEA TRANSPORTE") or "")[:30]
        at = str(a.get("TRANSPORTE") or a.get("OBLEA TRANSPORTE") or "")[:30]
        if rt and at and rt.strip().upper()[:8] == at.strip().upper()[:8]:
            match_transp += 1

        rl, al = _num(r.get("LOGISTICA")), _num(a.get("LOGISTICA"))
        if rl is not None and al is not None:
            diff = abs(rl - al)
            if diff <= tol_abs or (rl and diff / abs(rl) <= tol_pct):
                match_log += 1
            else:
                dif_log.append(
                    {
                        "CLAVE": clave,
                        "REF_LOG": rl,
                        "APP_LOG": al,
                        "DIFF": round(al - rl, 2),
                        "REF_ARCH": r.get("_archivo", ""),
                    }
                )

    # Fechas app
    fechas_app = []
    if "FECHA" in app.columns:
        for v in app["FECHA"].dropna().astype(str).head(500):
            fechas_app.append(v[:10])

    return {
        "ref_filas": len(ref),
        "ref_casos": len(ref_keys),
        "app_filas": len(app),
        "app_casos": len(app_keys),
        "comunes": len(comunes),
        "solo_ref": len(solo_ref),
        "solo_app": len(solo_app),
        "pct_cobertura_ref": round(100 * len(comunes) / max(1, len(ref_keys)), 1),
        "match_provincia": match_prov,
        "match_transporte": match_transp,
        "match_logistica": match_log,
        "dif_log": dif_log,
        "dif_prov": dif_prov,
        "app_tortu": int((app["_origen"] == "tortu").sum()),
        "app_sa": int((app["_origen"] == "sa").sum()),
        "ref_tortu": int((ref["_origen"] == "tortu").sum()),
        "ref_sa": int((ref["_origen"] == "sa").sum()),
        "cruce_envio": len(set(ref["ENVIO_N"]) & set(app["ENVIO_N"]) - {""}),
        "seguro_app": settings.seguro_fijo,
    }


def main() -> None:
    app_xlsx = Path(sys.argv[1]) if len(sys.argv) > 1 else APP_XLSX_DEFAULT
    if not app_xlsx.exists():
        raise FileNotFoundError(app_xlsx)
    ref = cargar_adrian()
    app = cargar_app(app_xlsx)
    stats = comparar(ref, app)

    resumen = pd.DataFrame([{"metrica": k, "valor": v} for k, v in stats.items() if not isinstance(v, list)])
    dif_log = pd.DataFrame(stats["dif_log"][:200])
    dif_prov = pd.DataFrame(stats["dif_prov"][:100])

    with pd.ExcelWriter(OUT, engine="openpyxl") as w:
        resumen.to_excel(w, sheet_name="resumen", index=False)
        if not dif_log.empty:
            dif_log.to_excel(w, sheet_name="dif_logistica", index=False)
        if not dif_prov.empty:
            dif_prov.to_excel(w, sheet_name="dif_provincia", index=False)

    print("=== COMPARACION ABRIL: APP vs ADRIAN ===")
    print(f"Seguro app: ${stats['seguro_app']:,.0f}")
    print(f"Adrian: {stats['ref_filas']} filas | {stats['ref_casos']} casos (tortu {stats['ref_tortu']} / sa {stats['ref_sa']})")
    print(f"App export ({app_xlsx.name}): {stats['app_filas']} filas | {stats['app_casos']} casos (tortu {stats['app_tortu']} / sa {stats['app_sa']})")
    print(f"Cruce ENVIO (mismo nro): {stats['cruce_envio']}")
    print(f"Cruce CLAVE remito/envio: {stats['comunes']} ({stats['pct_cobertura_ref']}% de casos Adrian)")
    print(f"Solo en Adrian: {stats['solo_ref']} | Solo en app: {stats['solo_app']}")
    n = max(1, stats["comunes"])
    print(f"En comunes — provincia OK: {stats['match_provincia']}/{n}")
    print(f"En comunes — transporte OK: {stats['match_transporte']}/{n}")
    print(f"En comunes — LOGISTICA ±15% o $5000: {stats['match_logistica']}/{n}")
    print(f"\nExportado: {OUT}")


if __name__ == "__main__":
    main()
