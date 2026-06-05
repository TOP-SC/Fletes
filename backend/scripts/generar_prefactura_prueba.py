"""Genera prefactura Clickpack ficticia alineada a remitos pendientes en la base."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

OUT = ROOT / "data" / "prefactura_clickpack_prueba.xlsx"
DB = ROOT / "data" / "fletes.db"


def main() -> None:
    engine = create_engine(f"sqlite:///{DB}")
    rows: list[dict] = []
    with engine.connect() as c:
        remitos = c.execute(
            text(
                """
                SELECT remito, MAX(razon_social), MAX(localidad), MAX(provincia),
                       SUM(COALESCE(costo_tarifario, 0))
                FROM envios
                WHERE alerta_clickpack = 1 AND excluir_planilla = 0
                GROUP BY remito_norm
                HAVING SUM(COALESCE(costo_tarifario, 0)) > 0
                """
            )
        ).fetchall()

    for remito, cliente, loc, prov, total in remitos:
        rows.append(
            {
                "Fecha reporte": "02/06/2026",
                "Remito": remito,
                "Cliente": cliente,
                "Localidad": loc,
                "Provincia": prov,
                "Importe total": round(float(total), 2),
                "Observacion": "Prefactura ficticia de prueba",
            }
        )

    if not rows:
        print("No hay remitos Clickpack con tarifa en la base.")
        return

    df = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(OUT, index=False, sheet_name="Prefactura")
    print(f"OK: {OUT} ({len(df)} filas)")


if __name__ == "__main__":
    main()
