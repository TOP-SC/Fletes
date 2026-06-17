"""
Analiza planillas cross (Drive / docs/) para evaluar utilidad de macheo colaborativo.

Enfoca pestañas "Retirado por …" (Alfaro, Fransof, etc.) vs otras hojas del mismo libro.
Cruza remitos normalizados con envios en fletes.db (transporte 82 / proveedor cross).
"""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
DB = ROOT / "data" / "fletes.db"

sys.path.insert(0, str(ROOT / "backend"))
from app.services.remito_utils import normalizar_remito  # noqa: E402


def _es_hoja_retirado(nombre: str) -> bool:
    n = nombre.lower()
    return "retirado" in n


def _es_hoja_preparado(nombre: str) -> bool:
    return "preparado" in nombre.lower() and "retir" in nombre.lower()


def _leer_hoja_preparado(path: Path, sheet: str) -> tuple[pd.DataFrame | None, dict]:
    """Hojas 'Preparado para retirar' suelen no tener fila de encabezados."""
    meta: dict = {"sheet": sheet, "error": None, "tipo_hoja": "preparado"}
    try:
        raw = pd.read_excel(path, sheet_name=sheet, header=None, dtype=str)
    except Exception as exc:
        meta["error"] = str(exc)
        return None, meta
    if raw.empty:
        meta["error"] = "vacía"
        return None, meta
    # Columna A = remito (R00172-… / R00178…)
    col_a = raw.iloc[:, 0].dropna().astype(str).str.strip()
    col_a = col_a[col_a.str.match(r"^R\d", case=False, na=False)]
    if col_a.empty:
        meta["error"] = "sin remitos en columna A"
        return None, meta
    df = pd.DataFrame({"REMITO": col_a})
    meta["header_row"] = None
    meta["columns"] = ["REMITO", "(sin encabezado — col A remito, B fecha, C pedido…)"]
    meta["rows"] = len(col_a)
    return df, meta


def _detectar_header(df_raw: pd.DataFrame) -> int | None:
    for i in range(min(8, len(df_raw))):
        row = [str(x).strip().upper() for x in df_raw.iloc[i].tolist()]
        if "REMITO" in row:
            return i
    return None


def _leer_hoja(path: Path, sheet: str) -> tuple[pd.DataFrame | None, dict]:
    meta: dict = {"sheet": sheet, "error": None}
    if _es_hoja_preparado(sheet):
        return _leer_hoja_preparado(path, sheet)
    try:
        raw = pd.read_excel(path, sheet_name=sheet, header=None, dtype=str)
    except Exception as exc:
        meta["error"] = str(exc)
        return None, meta
    if raw.empty:
        meta["error"] = "vacía"
        return None, meta
    hdr = _detectar_header(raw)
    if hdr is None:
        meta["error"] = "sin columna REMITO en primeras 8 filas"
        return None, meta
    df = pd.read_excel(path, sheet_name=sheet, header=hdr, dtype=str)
    df.columns = [str(c).strip() for c in df.columns]
    meta["header_row"] = hdr + 1
    meta["columns"] = list(df.columns)
    meta["rows"] = len(df)
    return df, meta


def _col_remito(df: pd.DataFrame) -> str | None:
    for c in df.columns:
        if str(c).strip().upper() == "REMITO":
            return c
    for c in df.columns:
        if "REMITO" in str(c).upper():
            return c
    return None


def _col_pedido(df: pd.DataFrame) -> str | None:
    for c in df.columns:
        u = str(c).strip().upper()
        if u in ("PEDIDO", "NRO PEDIDO", "NRO_PEDIDO"):
            return c
    return None


def _cols_seguimiento(df: pd.DataFrame) -> list[str]:
    keys = (
        "ENTREGADO",
        "RETIRO",
        "FECHA DE ENTREGA",
        "FECHA ENTREGA",
        "OBS",
        "COORDINADA",
    )
    out = []
    for c in df.columns:
        u = str(c).upper()
        if any(k in u for k in keys):
            out.append(c)
    return out


def _remitos_hoja(df: pd.DataFrame) -> dict[str, str]:
    """remito_norm -> remito crudo (primero encontrado)."""
    col = _col_remito(df)
    if not col:
        return {}
    out: dict[str, str] = {}
    for v in df[col].dropna():
        raw = str(v).strip()
        if not raw or raw.lower() in ("nan", "none"):
            continue
        norm = normalizar_remito(raw)
        if norm and norm not in out:
            out[norm] = raw
    return out


def _cargar_envios_db() -> pd.DataFrame:
    con = sqlite3.connect(DB)
    q = """
    SELECT remito_norm, remito, nro_pedido, proveedor_tarifa, transporte_cod,
           transporte_nombre, localidad, provincia, estado_pedido
    FROM envios
    WHERE remito_norm IS NOT NULL AND remito_norm != ''
    """
    df = pd.read_sql(q, con)
    con.close()
    return df


def _index_envios_por_remito(envios: pd.DataFrame) -> dict[str, list[dict]]:
    idx: dict[str, list[dict]] = defaultdict(list)
    for row in envios.to_dict("records"):
        key = str(row.get("remito_norm") or "").strip()
        if key:
            idx[key].append(row)
    return idx


def _proveedor_desde_hoja(nombre_hoja: str) -> str | None:
    n = nombre_hoja.upper()
    if "FRANSOF" in n or "FRANOV" in n:
        return "FRANSOF"
    if "ALFARO" in n:
        return "ALFARO"
    if "LBO" in n:
        return "LBO"
    if "COMPLETA" in n:
        return "COMPLETA"
    return None


def analizar_archivo(path: Path, env_idx: dict[str, list[dict]]) -> dict:
    xl = pd.ExcelFile(path)
    libro = {
        "archivo": path.name,
        "hojas_total": len(xl.sheet_names),
        "hojas": xl.sheet_names,
        "pestanas_retirado": [],
        "otras_pestanas": [],
    }
    todos_remitos: dict[str, str] = {}

    for sheet in xl.sheet_names:
        df, meta = _leer_hoja(path, sheet)
        if df is None:
            entry = {
                **meta,
                "tipo": (
                    "retirado"
                    if _es_hoja_retirado(sheet)
                    else "preparado"
                    if _es_hoja_preparado(sheet)
                    else "otra"
                ),
            }
            if _es_hoja_retirado(sheet):
                libro["pestanas_retirado"].append(entry)
            else:
                libro["otras_pestanas"].append(entry)
            continue

        remitos = _remitos_hoja(df)
        todos_remitos.update(remitos)
        seg_cols = _cols_seguimiento(df)
        ped_col = _col_pedido(df)

        # muestra ENTREGADO OK si existe
        entregado_vals = {}
        for c in df.columns:
            if "ENTREGADO" in str(c).upper():
                vc = df[c].dropna().astype(str).str.strip()
                vc = vc[vc != ""]
                entregado_vals[c] = vc.value_counts().head(5).to_dict()

        matched = [k for k in remitos if k in env_idx]
        cross_82 = []
        prov_match = []
        prov_mismatch = []
        prov_esperado = _proveedor_desde_hoja(sheet)

        for k in matched:
            rows = env_idx[k]
            tc = {str(r.get("transporte_cod") or "") for r in rows}
            if "82" in tc:
                cross_82.append(k)
            if prov_esperado:
                pt = {str(r.get("proveedor_tarifa") or "").upper() for r in rows}
                if prov_esperado in pt:
                    prov_match.append(k)
                elif pt - {"", "NONE"}:
                    prov_mismatch.append(k)

        entry = {
            **meta,
            "tipo": (
                "retirado"
                if _es_hoja_retirado(sheet)
                else "preparado"
                if _es_hoja_preparado(sheet)
                else "otra"
            ),
            "proveedor_inferido": prov_esperado,
            "remitos_unicos": len(remitos),
            "remitos_con_pedido_col": bool(ped_col),
            "cols_seguimiento": seg_cols,
            "entregado_distrib": entregado_vals,
            "macheo_db": {
                "en_db": len(matched),
                "pct_db": round(100 * len(matched) / len(remitos), 1) if remitos else 0,
                "transporte_82": len(cross_82),
                "proveedor_coherente": len(prov_match) if prov_esperado else None,
                "proveedor_distinto": len(prov_mismatch) if prov_esperado else None,
            },
        }
        if _es_hoja_retirado(sheet):
            libro["pestanas_retirado"].append(entry)
        else:
            libro["otras_pestanas"].append(entry)

    all_norms = set(todos_remitos)
    matched_all = [k for k in all_norms if k in env_idx]
    libro["resumen_libro"] = {
        "remitos_unicos_todas_hojas": len(all_norms),
        "en_db": len(matched_all),
        "pct_en_db": round(100 * len(matched_all) / len(all_norms), 1) if all_norms else 0,
    }
    return libro


def main() -> None:
    if not DB.exists():
        print("No existe", DB)
        sys.exit(1)

    archivos = sorted(DOCS.glob("*.xlsx"))
    if not archivos:
        print("Sin xlsx en", DOCS)
        sys.exit(1)

    envios = _cargar_envios_db()
    env_idx = _index_envios_por_remito(envios)
    print(f"DB: {len(env_idx)} remitos_norm únicos en envios\n")

    informe = []
    for path in archivos:
        print("=" * 70)
        print(path.name)
        try:
            libro = analizar_archivo(path, env_idx)
            informe.append(libro)
        except Exception as exc:
            print("  ERROR:", exc)
            continue

        print(f"  Hojas ({libro['hojas_total']}): {libro['hojas']}")
        print(f"  Resumen libro: {libro['resumen_libro']}")

        for pest in libro["pestanas_retirado"]:
            print(f"\n  [RETIRADO] {pest['sheet']}")
            if pest.get("error"):
                print(f"    error: {pest['error']}")
                continue
            print(f"    cols seguimiento: {pest.get('cols_seguimiento')}")
            print(f"    remitos: {pest.get('remitos_unicos')} | macheo DB: {pest.get('macheo_db')}")
            if pest.get("entregado_distrib"):
                print(f"    entregado: {pest['entregado_distrib']}")

        for pest in libro["otras_pestanas"]:
            if pest.get("error") or not pest.get("remitos_unicos"):
                continue
            if pest.get("remitos_unicos", 0) < 5:
                continue
            print(f"\n  [otra] {pest['sheet']} — remitos {pest['remitos_unicos']} | {pest.get('macheo_db')}")

    out = DOCS / "analisis_macheo_cross.json"
    out.write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n" + "=" * 70)
    print("Informe JSON:", out)

    # Conclusión automática
    retirado_ok = []
    for lib in informe:
        for p in lib.get("pestanas_retirado", []):
            if p.get("error"):
                continue
            m = p.get("macheo_db") or {}
            if p.get("remitos_unicos", 0) >= 10 and m.get("en_db", 0) > 0:
                retirado_ok.append(
                    (lib["archivo"], p["sheet"], p["remitos_unicos"], m["en_db"], m["pct_db"])
                )
    print("\nPestañas Retirado con macheo útil (>=10 remitos y alguno en DB):")
    for row in retirado_ok:
        print(f"  {row[0]} | {row[1]} | remitos={row[2]} en_db={row[3]} ({row[4]}%)")


if __name__ == "__main__":
    main()
