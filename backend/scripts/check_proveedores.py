from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text

e = create_engine(f"sqlite:///{Path(__file__).resolve().parents[2] / 'data' / 'fletes.db'}")
with e.connect() as c:
    n = c.execute(
        text("SELECT COUNT(*) FROM tarifas WHERE proveedor='FRANSOF'")
    ).scalar()
    print("tarifas FRANSOF", n)
    rows = c.execute(
        text(
            "SELECT proveedor_tarifa, requiere_elegir_proveedor, COUNT(DISTINCT remito_norm) "
            "FROM envios WHERE localidad LIKE '%Rosario%' AND excluir_planilla=0 "
            "GROUP BY proveedor_tarifa, requiere_elegir_proveedor"
        )
    ).fetchall()
    for r in rows:
        print(r)
