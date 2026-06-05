from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal, init_db
from app.services.import_service import reaplicar_todos_envios
from app.services.macheo_service import ejecutar_macheo_clickpack
from sqlalchemy import text

init_db()
db = SessionLocal()
print("Macheo:", ejecutar_macheo_clickpack(db))
print("Reglas:", reaplicar_todos_envios(db))
q = text(
    "SELECT DISTINCT remito, regla_color, regla_motivo, prefactura_proveedor "
    "FROM envios WHERE remito LIKE :p"
)
for row in db.execute(q, {"p": "R001780031802%"}):
    print(row)
db.close()
