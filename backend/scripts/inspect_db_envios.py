"""Inspección rápida de fletes.db — conteos y meses."""
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import create_engine, text

DB = Path(__file__).resolve().parents[2] / "data" / "fletes.db"


def main() -> None:
    print("DB:", DB, "exists:", DB.exists())
    if not DB.exists():
        sys.exit(1)
    e = create_engine(f"sqlite:///{DB}")
    with e.connect() as c:
        print("\nTablas SQLite:")
        tabs = c.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        ).fetchall()
        for (name,) in tabs:
            try:
                n = c.execute(text(f"SELECT COUNT(*) FROM {name}")).scalar()
                print(f"  {name}: {n}")
            except Exception:
                print(f"  {name}: ?")

        rows = c.execute(
            text(
                """
                SELECT strftime('%Y-%m', fecha_entrega_d) AS mes, COUNT(*) AS n
                FROM envios
                WHERE fecha_entrega_d IS NOT NULL
                GROUP BY mes
                ORDER BY mes
                """
            )
        ).fetchall()
        print("\nPor mes (fecha_entrega_d):")
        for mes, n in rows:
            print(f"  {mes}: {n}")

        rows_ped = c.execute(
            text(
                """
                SELECT strftime('%Y-%m', fecha_pedido_d) AS mes, COUNT(*) AS n
                FROM envios
                WHERE fecha_pedido_d IS NOT NULL
                GROUP BY mes
                ORDER BY mes
                """
            )
        ).fetchall()
        print("\nPor mes (fecha_pedido_d):")
        for mes, n in rows_ped:
            print(f"  {mes}: {n}")

        batches = c.execute(
            text(
                "SELECT id, filename, rows_inserted FROM import_batches ORDER BY id DESC LIMIT 10"
            )
        ).fetchall()
        print("\nÚltimos import_batches:")
        for b in batches:
            print(f"  {b}")


if __name__ == "__main__":
    main()
