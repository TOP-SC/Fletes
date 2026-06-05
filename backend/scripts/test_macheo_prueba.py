from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.database import SessionLocal, init_db
from app.services.mundo1_import import import_prefactura_clickpack
from app.services.macheo_service import ejecutar_macheo_clickpack
from sqlalchemy import text

init_db()
db = SessionLocal()
content = Path(__file__).resolve().parents[2] / "data" / "prefactura_clickpack_prueba.xlsx"
b = import_prefactura_clickpack(db, content.read_bytes(), content.name)
print("Import:", b.rows_inserted, "new", b.rows_skipped, "skip")
print("Macheo:", ejecutar_macheo_clickpack(db))
q = text(
    "SELECT DISTINCT remito, regla_color, macheo_estado, prefactura_proveedor "
    "FROM envios WHERE remito LIKE 'R001780031802%'"
)
for row in db.execute(q):
    print(row)
db.close()
