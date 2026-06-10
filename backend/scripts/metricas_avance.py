"""Métricas para docs/AVANCE_PROYECTO.html."""
from __future__ import annotations

import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parents[2] / "data" / "fletes.db"


def main() -> None:
    if not DB.exists():
        print("NO_DB")
        return
    c = sqlite3.connect(DB)
    total = c.execute("SELECT COUNT(*) FROM envios").fetchone()[0]
    print(f"total={total}")
    queries = {
        "con_costo": "SELECT COUNT(*) FROM envios WHERE costo_tarifario IS NOT NULL AND costo_tarifario > 0",
        "prefactura": "SELECT COUNT(*) FROM envios WHERE prefactura_proveedor IS NOT NULL",
        "macheo_ok": "SELECT COUNT(*) FROM envios WHERE macheo_estado = 'ok'",
        "elegir_prov": "SELECT COUNT(*) FROM envios WHERE requiere_elegir_proveedor = 1",
        "amba": "SELECT COUNT(*) FROM envios WHERE excluir_planilla = 1",
        "interior": "SELECT COUNT(*) FROM envios WHERE excluir_planilla = 0 OR excluir_planilla IS NULL",
        "dep12": "SELECT COUNT(*) FROM envios WHERE deposito = 12",
        "sin_dep": "SELECT COUNT(*) FROM envios WHERE deposito IS NULL OR deposito = ''",
        "dep2": "SELECT COUNT(*) FROM envios WHERE deposito = 2",
    }
    for k, q in queries.items():
        print(f"{k}={c.execute(q).fetchone()[0]}")
    print("colores", c.execute("SELECT regla_color, COUNT(*) FROM envios GROUP BY regla_color ORDER BY 2 DESC").fetchall())
    try:
        print(f"tarifas={c.execute('SELECT COUNT(*) FROM tarifas').fetchone()[0]}")
    except sqlite3.OperationalError:
        pass
    for tbl in ("flete_solicitudes", "fletes_solicitud", "flete_solicitud"):
        try:
            fle = c.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
            match = c.execute(
                f"SELECT COUNT(*) FROM {tbl} WHERE envio_id IS NOT NULL"
            ).fetchone()[0]
            print(f"fleteros_tbl={tbl} total={fle} match={match}")
            break
        except sqlite3.OperationalError:
            continue
    c.close()


if __name__ == "__main__":
    main()
