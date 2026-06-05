"""Diagnóstico rápido de importación Tango."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text

from app.services.excel_parser import parse_exportacion_excel

DB = Path(__file__).resolve().parents[2] / "data" / "fletes.db"


def main() -> None:
    engine = create_engine(f"sqlite:///{DB}")
    with engine.connect() as c:
        print("=== Batches ===")
        for row in c.execute(
            text(
                "SELECT id, filename, rows_in_file, rows_inserted, rows_skipped FROM import_batches ORDER BY id"
            )
        ):
            print(row)

        print("\n=== Campos poblados (batch Exportacion2) ===")
        bid = c.execute(
            text("SELECT id FROM import_batches WHERE filename LIKE '%Exportacion2%' LIMIT 1")
        ).scalar()
        if bid:
            for col in [
                "remito",
                "nro_pedido",
                "cod_articulo",
                "descripcion",
                "provincia",
                "localidad",
                "deposito",
                "transporte_nombre",
                "fecha_entrega",
            ]:
                n = c.execute(
                    text(
                        f"SELECT COUNT(*) FROM envios WHERE import_batch_id=:b AND {col} IS NOT NULL"
                    ),
                    {"b": bid},
                ).scalar()
                print(f"  {col}: {n}")

    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
        print(f"\n=== Columnas en {path.name} ===")
        rows = parse_exportacion_excel(path.read_bytes())
        print(f"Filas parseadas: {len(rows)}")
        sample = rows[0] if rows else {}
        filled = {k: v for k, v in sample.items() if v is not None and str(v).strip()}
        print("Primera fila con datos:", filled)
        import pandas as pd

        df = pd.read_excel(path, sheet_name=0)
        print("\nColumnas Excel (primeras 30):")
        for col in list(df.columns)[:30]:
            print(f"  {repr(col)}")
        print(f"... total {len(df.columns)} columnas")


if __name__ == "__main__":
    main()
