"""Resumen de lotes y meses en fletes.db."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import func, select, text

from app.database import SessionLocal
from app.models import Envio, ImportBatch


def main() -> None:
    db = SessionLocal()
    try:
        print("=== LOTES IMPORTADOS ===")
        for b in db.scalars(select(ImportBatch).order_by(ImportBatch.imported_at)).all():
            print(
                f"  {b.filename} | {b.imported_at.date()} | "
                f"+{b.rows_inserted} ins, skip {b.rows_skipped}"
            )

        print("\n=== DEPOSITO / ORIGEN (top) ===")
        rows = db.execute(
            select(Envio.deposito, Envio.origen_cd, func.count())
            .group_by(Envio.deposito, Envio.origen_cd)
            .order_by(func.count().desc())
            .limit(8)
        ).all()
        for dep, origen, cnt in rows:
            print(f"  dep={dep!r} origen={origen!r} -> {cnt}")

        print("\n=== MESES fecha_pedido_d ===")
        for mes, cnt in db.execute(
            text(
                "SELECT strftime('%Y-%m', fecha_pedido_d), COUNT(*) "
                "FROM envios WHERE fecha_pedido_d IS NOT NULL GROUP BY 1 ORDER BY 1"
            )
        ):
            print(f"  {mes}: {cnt}")

        print("\n=== MESES fecha_entrega_d ===")
        for mes, cnt in db.execute(
            text(
                "SELECT strftime('%Y-%m', fecha_entrega_d), COUNT(*) "
                "FROM envios WHERE fecha_entrega_d IS NOT NULL GROUP BY 1 ORDER BY 1"
            )
        ):
            print(f"  {mes}: {cnt}")

        for label, sql in (
            ("Mayo pedido", "fecha_pedido_d BETWEEN '2026-05-01' AND '2026-05-31'"),
            ("Mayo entrega", "fecha_entrega_d BETWEEN '2026-05-01' AND '2026-05-31'"),
            ("Abril pedido", "fecha_pedido_d BETWEEN '2026-04-01' AND '2026-04-30'"),
            ("Junio pedido", "fecha_pedido_d BETWEEN '2026-06-01' AND '2026-06-30'"),
        ):
            n = db.scalar(text(f"SELECT COUNT(*) FROM envios WHERE {sql}"))
            print(f"\n{label}: {n}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
