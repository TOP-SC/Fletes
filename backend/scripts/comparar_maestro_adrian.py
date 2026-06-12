"""
Comparación maestro app vs Adrián (abril 2026) — casos reales cruzados por remito.

Uso:
  python scripts/comparar_maestro_adrian.py [export_app.xlsx] [carpeta_adrian]

Genera: data/comparacion_maestro_adrian_2026.xlsx
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import settings
from app.services.remito_utils import normalizar_remito

APP_XLSX_DEFAULT = Path(r"c:\Users\juan.billiot\Desktop\maestro_wamaro (2).xlsx")
CARPETA_ADR_DEFAULT = Path(r"C:\Users\juan.billiot\Desktop\4 ABR 2026")
OUT = ROOT.parent / "data" / "comparacion_maestro_adrian_2026.xlsx"

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


def _montos_cercanos(ref: float | None, app: float | None) -> bool | None:
    if ref is None and app is None:
        return None
    if ref is None or app is None:
        return False
    diff = abs(ref - app)
    if diff < 1.0:
        return True
    if ref and diff / abs(ref) <= TOL_LOG_PCT:
        return True
    return diff <= TOL_LOG_ABS


def _ref_monto_adrian(row) -> float | None:
    """Adrián suele cargar LOGISTICA; PRECIO NETO cuando hay prefactura."""
    pn = _num(row.get("PRECIO NETO"))
    log = _num(row.get("LOGISTICA"))
    if pn and pn > 0:
        return pn
    if log and log > 0:
        return log
    return None


def _ref_monto_app(row) -> float | None:
    log = _num(row.get("LOGISTICA"))
    if log and log > 0:
        return log
    pn = _num(row.get("PRECIO NETO"))
    if pn and pn > 0:
        return pn
    return None


def cargar_adrian(carpeta: Path) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in sorted(carpeta.glob("*.xlsx")):
        name = path.name.upper()
        if "WAMARO TORTUGUITAS" not in name and not name.startswith("WAMARO SA"):
            continue
        df = pd.read_excel(path, sheet_name=0)
        if "REMITOS" not in df.columns:
            continue
        df = df.dropna(subset=["REMITOS"], how="all").copy()
        df["_archivo"] = path.name
        df["_origen"] = "sa" if name.startswith("WAMARO SA") else "tortu"
        frames.append(df)
    if not frames:
        raise FileNotFoundError(f"Sin maestros WAMARO en {carpeta}")
    out = pd.concat(frames, ignore_index=True)
    out["REMITO_N"] = out["REMITOS"].map(_norm_remito)
    return out[out["REMITO_N"] != ""].drop_duplicates("REMITO_N", keep="first")


def cargar_app(app_xlsx: Path) -> pd.DataFrame:
    frames = []
    for sh in pd.ExcelFile(app_xlsx).sheet_names:
        df = pd.read_excel(app_xlsx, sheet_name=sh)
        if "REMITOS" in df.columns and not df.empty:
            df["_hoja"] = sh
            frames.append(df)
    if not frames:
        raise FileNotFoundError(app_xlsx)
    out = pd.concat(frames, ignore_index=True)
    out["REMITO_N"] = out["REMITOS"].map(_norm_remito)
    return out[out["REMITO_N"] != ""].drop_duplicates("REMITO_N", keep="first")


def main() -> None:
    app_xlsx = Path(sys.argv[1]) if len(sys.argv) > 1 else APP_XLSX_DEFAULT
    carpeta_adr = Path(sys.argv[2]) if len(sys.argv) > 2 else CARPETA_ADR_DEFAULT

    adr = cargar_adrian(carpeta_adr)
    app = cargar_app(app_xlsx)
    comunes = sorted(set(adr["REMITO_N"]) & set(app["REMITO_N"]))
    solo_adr = sorted(set(adr["REMITO_N"]) - set(app["REMITO_N"]))
    solo_app = sorted(set(app["REMITO_N"]) - set(adr["REMITO_N"]))

    ai = adr.set_index("REMITO_N")
    bi = app.set_index("REMITO_N")

    detalle: list[dict] = []
    ok_dest = ok_loc = ok_prov = ok_bul = ok_monto = ok_full = 0

    for rn in comunes:
        a, b = ai.loc[rn], bi.loc[rn]
        dest_ok = _norm_text(a.get("DESTINATARIO"))[:15] == _norm_text(b.get("DESTINATARIO"))[:15]
        loc_ok = _norm_text(a.get("LOCALIDAD"))[:10] == _norm_text(b.get("LOCALIDAD"))[:10]
        prov_ok = _norm_text(a.get("PROVINCIA"))[:8] == _norm_text(b.get("PROVINCIA"))[:8]
        ba, bb = _num(a.get("BULTOS")), _num(b.get("BULTOS"))
        bul_ok = ba is not None and bb is not None and ba == bb
        ref_a, ref_b = _ref_monto_adrian(a), _ref_monto_app(b)
        monto_ok = _montos_cercanos(ref_a, ref_b)
        if monto_ok is True:
            ok_monto += 1
        if dest_ok:
            ok_dest += 1
        if loc_ok:
            ok_loc += 1
        if prov_ok:
            ok_prov += 1
        if bul_ok:
            ok_bul += 1
        if dest_ok and loc_ok and bul_ok and monto_ok is True:
            ok_full += 1

        difs = []
        if not dest_ok:
            difs.append("DESTINATARIO")
        if not loc_ok:
            difs.append("LOCALIDAD")
        if not bul_ok:
            difs.append("BULTOS")
        if monto_ok is False:
            difs.append("MONTO")

        detalle.append(
            {
                "REMITO_N": rn,
                "REMITOS_ADR": a.get("REMITOS"),
                "REMITOS_APP": b.get("REMITOS"),
                "DEST_ADR": a.get("DESTINATARIO"),
                "DEST_APP": b.get("DESTINATARIO"),
                "LOCALIDAD_ADR": a.get("LOCALIDAD"),
                "LOCALIDAD_APP": b.get("LOCALIDAD"),
                "BULTOS_ADR": ba,
                "BULTOS_APP": bb,
                "MONTO_REF_ADR": ref_a,
                "LOG_APP": _num(b.get("LOGISTICA")),
                "PN_APP": _num(b.get("PRECIO NETO")),
                "TRANSPORTE_ADR": a.get("TRANSPORTE"),
                "TRANSPORTE_APP": b.get("TRANSPORTE"),
                "ARCHIVO_ADR": a.get("_archivo", ""),
                "campos_distintos": ", ".join(difs) if difs else "OK",
                "n_difs": len(difs),
                "confiable": "SI" if not difs else "REVISAR",
            }
        )

    n = max(1, len(comunes))
    pct = lambda x: round(100 * x / n, 1)

    resumen = pd.DataFrame(
        [
            {"metrica": "Casos Adrián (remitos únicos)", "valor": len(adr)},
            {"metrica": "Casos app export (remitos únicos)", "valor": len(app)},
            {"metrica": "Cruce real por remito", "valor": len(comunes)},
            {"metrica": "% cobertura del maestro Adrián", "valor": round(100 * len(comunes) / max(1, len(adr)), 1)},
            {"metrica": "Solo en Adrián (scope más acotado o filtros)", "valor": len(solo_adr)},
            {"metrica": "Solo en app (consulta más amplia)", "valor": len(solo_app)},
            {"metrica": "Destinatario OK (15 chars)", "valor": f"{ok_dest}/{len(comunes)} ({pct(ok_dest)}%)"},
            {"metrica": "Localidad OK", "valor": f"{ok_loc}/{len(comunes)} ({pct(ok_loc)}%)"},
            {"metrica": "Provincia OK", "valor": f"{ok_prov}/{len(comunes)} ({pct(ok_prov)}%)"},
            {"metrica": "Bultos exactos", "valor": f"{ok_bul}/{len(comunes)} ({pct(ok_bul)}%)"},
            {
                "metrica": "Monto OK (Adr PN/LOG vs App LOG/PN ±15% o $5000)",
                "valor": f"{ok_monto}/{len(comunes)} ({pct(ok_monto)}%)",
            },
            {"metrica": "Casos plenamente confiables (dest+loc+bultos+monto)", "valor": f"{ok_full}/{len(comunes)} ({pct(ok_full)}%)"},
            {"metrica": "App LOG>0 en export", "valor": int((app["LOGISTICA"].fillna(0) > 0).sum())},
            {"metrica": "Seguro app ($)", "valor": settings.seguro_fijo},
            {"metrica": "Archivo app", "valor": app_xlsx.name},
        ]
    )

    det = pd.DataFrame(detalle).sort_values(["n_difs", "REMITO_N"])
    confiables = det[det["confiable"] == "SI"]
    revisar = det[det["confiable"] == "REVISAR"]

    with pd.ExcelWriter(OUT, engine="openpyxl") as w:
        resumen.to_excel(w, sheet_name="resumen", index=False)
        confiables.to_excel(w, sheet_name="confiables", index=False)
        revisar.to_excel(w, sheet_name="revisar", index=False)
        det.to_excel(w, sheet_name="detalle_completo", index=False)
        pd.DataFrame({"REMITO_N": solo_adr[:800]}).to_excel(w, sheet_name="solo_adrian", index=False)
        pd.DataFrame({"REMITO_N": solo_app[:800]}).to_excel(w, sheet_name="solo_app_muestra", index=False)

    print("=== COMPARACION MAESTRO APP vs ADRIAN (casos cruzados) ===")
    print(resumen.to_string(index=False))
    print(f"\nExport: {OUT}")


if __name__ == "__main__":
    main()
