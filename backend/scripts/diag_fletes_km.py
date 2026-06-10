import sqlite3
from pathlib import Path

c = sqlite3.connect(Path(__file__).resolve().parents[2] / "data" / "fletes.db")
print("=== remitos 0117 ===")
for r in c.execute(
    "SELECT remito, remito_norm, localidad, domicilio FROM envios "
    "WHERE remito LIKE '%0117%' LIMIT 8"
):
    print(r)
    if r[1]:
        d = c.execute(
            "SELECT sucursal_cod, distance_km, zona_km FROM flete_distancias WHERE remito_norm=?",
            (r[1],),
        ).fetchone()
        print("  dist:", d)

n_dist = c.execute("SELECT COUNT(*) FROM flete_distancias").fetchone()[0]
print("total dist cache:", n_dist)

# amba sin dist
q = """
SELECT COUNT(*) FROM envios e
WHERE e.excluir_planilla=1 AND e.transporte_cod='40'
AND e.remito_norm IS NOT NULL AND e.remito_norm != ''
AND NOT EXISTS (SELECT 1 FROM flete_distancias f WHERE f.remito_norm=e.remito_norm)
"""
print("amba40 con remito sin dist:", c.execute(q).fetchone()[0])

c.close()
