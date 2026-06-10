"""Estadísticas transporte 51 vs otros."""
from __future__ import annotations

import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parents[2] / "data" / "fletes.db"


def main() -> None:
    c = sqlite3.connect(DB)
    print("=== TOP transportes (renglones) ===")
    for r in c.execute(
        "SELECT transporte_cod, transporte_nombre, COUNT(*) n "
        "FROM envios GROUP BY transporte_cod, transporte_nombre ORDER BY n DESC LIMIT 12"
    ):
        print(r)

    q51 = "transporte_cod='51'"
    n51 = c.execute(f"SELECT COUNT(*) FROM envios WHERE {q51}").fetchone()[0]
    n40 = c.execute("SELECT COUNT(*) FROM envios WHERE transporte_cod='40'").fetchone()[0]
    n82 = c.execute("SELECT COUNT(*) FROM envios WHERE transporte_cod='82'").fetchone()[0]
    print(f"\nrenglones cod51={n51} cod40={n40} cod82={n82}")

    ac51 = c.execute(
        f"SELECT COUNT(*) FROM envios WHERE {q51} AND alerta_clickpack=1"
    ).fetchone()[0]
    print(f"alerta_clickpack_51={ac51}")

    sin_pf_51 = c.execute(
        f"SELECT COUNT(*) FROM envios WHERE {q51} AND prefactura_proveedor IS NULL"
    ).fetchone()[0]
    print(f"sin_prefactura_51={sin_pf_51} (prefactura en DB total=0)")

    sin_rem_51 = c.execute(
        f"SELECT COUNT(*) FROM envios WHERE {q51} AND (remito IS NULL OR remito='')"
    ).fetchone()[0]
    print(f"sin_remito_campo_51={sin_rem_51}")

    print("\ncolores persistidos cod51:", c.execute(
        f"SELECT regla_color, COUNT(*) FROM envios WHERE {q51} GROUP BY regla_color"
    ).fetchall())
    print("colores persistidos cod40:", c.execute(
        "SELECT regla_color, COUNT(*) FROM envios WHERE transporte_cod='40' GROUP BY regla_color"
    ).fetchall())

    elegir = c.execute(
        f"SELECT COUNT(*) FROM envios WHERE {q51} AND requiere_elegir_proveedor=1"
    ).fetchone()[0]
    print(f"requiere_elegir_proveedor_51={elegir}")

    c.close()


if __name__ == "__main__":
    main()
