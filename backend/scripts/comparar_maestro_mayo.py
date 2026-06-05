"""
Compara maestros diarios (carpeta LOG mayo) vs maestro generado por la app.

Uso:
  python scripts/comparar_maestro_mayo.py
  python scripts/comparar_maestro_mayo.py --carpeta "S:/.../fletes envios log MAYO/..."
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import settings
from app.database import SessionLocal
from app.models import Envio, Tarifa
from app.services.maestro_service import construir_maestro
from app.services.remito_utils import normalizar_remito

DEFAULT_CARPETA = (
    r"S:\Administración\TOP\LOG -  Envios Fletes 200326"
    r"\fletes envios log MAYO\5 MAY 2026-20260604T191815Z-3-001\5 MAY 2026"
)


def _norm_envio(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    s = str(v).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s


def _norm_remito(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return normalizar_remito(str(v).strip()) or ""


def _num(v) -> float | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def cargar_excel_referencia(carpeta: Path) -> pd.DataFrame:
    """Todos los WAMARO TORTUGUITAS / WAMARO SA diarios."""
    filas: list[pd.DataFrame] = []
    patrones = ("WAMARO TORTUGUITAS", "WAMARO SA -")
    for path in sorted(carpeta.glob("*.xlsx")):
        if not any(p in path.name.upper() for p in ("WAMARO TORTUGUITAS", "WAMARO SA")):
            continue
        try:
            df = pd.read_excel(path, sheet_name="Envios")
        except Exception:
            try:
                df = pd.read_excel(path, sheet_name=0)
                if "ENVIO" not in [str(c).upper() for c in df.columns]:
                    df.columns = df.iloc[0]
                    df = df.iloc[1:].reset_index(drop=True)
            except Exception as exc:
                print(f"  omitido {path.name}: {exc}")
                continue
        df = df.dropna(how="all")
        if "ENVIO" not in df.columns:
            continue
        df["_archivo"] = path.name
        filas.append(df)
    if not filas:
        raise FileNotFoundError(f"No se encontraron maestros WAMARO en {carpeta}")
    out = pd.concat(filas, ignore_index=True)
    out["ENVIO_N"] = out["ENVIO"].map(_norm_envio)
    out["REMITO_N"] = out["REMITOS"].map(_norm_remito) if "REMITOS" in out.columns else ""
    out["CLAVE"] = out.apply(
        lambda r: r["REMITO_N"] or r["ENVIO_N"] or "",
        axis=1,
    )
    return out


def cargar_maestro_app(mes: int = 5, anio: int = 2026) -> pd.DataFrame:
    from datetime import date

    from sqlalchemy import select

    from app.services.casos_filtro_service import aplicar_filtros_lista_envios

    db = SessionLocal()
    try:
        envios = list(db.scalars(select(Envio)).all())
        tarifas = list(db.scalars(select(Tarifa)).all())
        desde = date(anio, mes, 1)
        if mes == 12:
            hasta = date(anio, 12, 31)
        else:
            hasta = date(anio, mes + 1, 1)
            from datetime import timedelta

            hasta = hasta - timedelta(days=1)
        envios_mes = aplicar_filtros_lista_envios(
            envios,
            fecha_desde=desde,
            fecha_hasta=hasta,
            campo_fecha="cualquiera",
        )
        filas = construir_maestro(envios_mes, tarifas=tarifas, incluir_excluidos=True)
        df = pd.DataFrame(filas)
        if df.empty:
            return df
        df["ENVIO_N"] = df["ENVIO"].map(_norm_envio) if "ENVIO" in df.columns else ""
        df["REMITO_N"] = df["REMITOS"].map(_norm_remito) if "REMITOS" in df.columns else ""
        df["CLAVE"] = df.apply(
            lambda r: r["REMITO_N"] or r["ENVIO_N"] or "",
            axis=1,
        )
        return df
    finally:
        db.close()


def comparar(ref: pd.DataFrame, app: pd.DataFrame) -> dict:
    ref_keys = set(ref["CLAVE"].dropna()) - {""}
    app_keys = set(app["CLAVE"].dropna()) - {""} if not app.empty else set()

    solo_ref = ref_keys - app_keys
    solo_app = app_keys - ref_keys
    comunes = ref_keys & app_keys

    ref_idx = ref.drop_duplicates("CLAVE", keep="first").set_index("CLAVE")
    app_idx = (
        app.drop_duplicates("CLAVE", keep="first").set_index("CLAVE")
        if not app.empty
        else pd.DataFrame()
    )

    dif_log = []
    dif_seg = []
    dif_dest = []
    match_log = 0
    tol_pct = 0.15
    tol_abs = 5000.0

    for clave in comunes:
        r = ref_idx.loc[clave]
        if clave not in app_idx.index:
            continue
        a = app_idx.loc[clave]
        rl = _num(r.get("LOGISTICA"))
        al = _num(a.get("LOGISTICA"))
        rs = _num(r.get("SEGURO"))
        as_ = _num(a.get("SEGURO"))
        if rl is not None and al is not None:
            diff = abs(rl - al)
            if diff <= tol_abs or (rl and diff / rl <= tol_pct):
                match_log += 1
            else:
                dif_log.append(
                    {
                        "CLAVE": clave,
                        "ENVIO_REF": r.get("ENVIO", ""),
                        "ENVIO_APP": a.get("ENVIO", ""),
                        "REF_LOG": rl,
                        "APP_LOG": al,
                        "DIFF": round(al - rl, 2),
                        "REF_ARCH": r.get("_archivo", ""),
                        "DEST_REF": r.get("DESTINATARIO", ""),
                        "DEST_APP": a.get("DESTINATARIO", ""),
                    }
                )
        if rs is not None and as_ is not None and abs(rs - as_) > 0.01:
            dif_seg.append(
                {
                    "CLAVE": clave,
                    "REF_SEG": rs,
                    "APP_SEG": as_,
                    "NOTA": "ref LOG usa 30; app usa 3000",
                }
            )
        rd = str(r.get("DESTINATARIO", "")).strip().upper()[:20]
        ad = str(a.get("DESTINATARIO", "")).strip().upper()[:20]
        if rd and ad and rd != ad:
            dif_dest.append({"CLAVE": clave, "REF": rd, "APP": ad})

    return {
        "ref_filas": len(ref),
        "ref_casos": len(ref_keys),
        "app_casos": len(app_keys),
        "comunes": len(comunes),
        "solo_referencia": len(solo_ref),
        "solo_app": len(solo_app),
        "match_logistica": match_log,
        "dif_logistica": dif_log,
        "dif_seguro": dif_seg,
        "dif_destinatario": dif_dest,
        "solo_ref_list": sorted(list(solo_ref)),
        "solo_app_list": sorted(list(solo_app)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--carpeta", default=DEFAULT_CARPETA)
    parser.add_argument("--mes", type=int, default=5)
    parser.add_argument("--anio", type=int, default=2026)
    parser.add_argument("--export", default=str(ROOT.parent / "data" / "comparacion_mayo.xlsx"))
    args = parser.parse_args()

    carpeta = Path(args.carpeta)
    print(f"Seguro configurado en app: ${settings.seguro_fijo:,.0f}")
    print(f"Cargando referencia: {carpeta}")
    ref = cargar_excel_referencia(carpeta)
    print(f"  Filas referencia: {len(ref)} | pedidos únicos: {ref['ENVIO_N'].nunique()}")
    print(f"  SEGURO referencia (moda): {ref['SEGURO'].mode().iloc[0] if 'SEGURO' in ref.columns else '?'}")

    print("Cargando maestro app (mayo 2026, filtros fecha)...")
    app = cargar_maestro_app(args.mes, args.anio)
    print(f"  Casos app: {len(app)}")

    stats = comparar(ref, app)
    print("\n=== RESUMEN COMPARACIÓN MAYO ===")
    print(f"Referencia (LOG):     {stats['ref_casos']} envíos únicos ({stats['ref_filas']} filas)")
    print(f"App (maestro):        {stats['app_casos']} casos")
    print(f"En ambos:             {stats['comunes']}")
    print(f"Solo en referencia:   {stats['solo_referencia']}")
    print(f"Solo en app:          {stats['solo_app']}")
    print(f"Logística similar:    {stats['match_logistica']} / {stats['comunes']} comunes")
    print(f"Diferencia logística: {len(stats['dif_logistica'])}")
    print(f"Diferencia seguro:    {len(stats['dif_seguro'])}")
    print(f"Destinatario distinto:{len(stats['dif_destinatario'])}")

    if stats["dif_seguro"]:
        print("\nNota seguro: referencia usa SEGURO columna; app ahora usa", settings.seguro_fijo)
        print("  Muestra:", stats["dif_seguro"][:5])

    if stats["dif_logistica"]:
        print("\nTop 10 diferencias LOGISTICA (|diff| mayor):")
        ddf = pd.DataFrame(stats["dif_logistica"])
        ddf["ABS"] = ddf["DIFF"].abs()
        print(ddf.sort_values("ABS", ascending=False).head(10).to_string(index=False))

    out = Path(args.export)
    out.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        ref.to_excel(w, sheet_name="referencia", index=False)
        if not app.empty:
            app.to_excel(w, sheet_name="app_maestro", index=False)
        pd.DataFrame(stats["dif_logistica"]).to_excel(w, sheet_name="dif_logistica", index=False)
        pd.DataFrame(stats["dif_seguro"]).to_excel(w, sheet_name="dif_seguro", index=False)
        pd.DataFrame({"CLAVE": stats["solo_ref_list"]}).to_excel(
            w, sheet_name="solo_referencia", index=False
        )
        pd.DataFrame({"CLAVE": stats["solo_app_list"]}).to_excel(
            w, sheet_name="solo_app", index=False
        )
    print(f"\nExportado: {out}")


if __name__ == "__main__":
    main()
