"""Diagnóstico de un caso Fletes por remito."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal, init_db
from app.models import Envio
from app.services.fletes_km_service import preview_flete_caso
from app.services.mundo2_service import construir_fletes, es_envio_mundo2
from app.services.remito_maestro import clave_agrupacion_caso
from app.services.remito_utils import normalizar_remito
from sqlalchemy import select

init_db()
db = SessionLocal()

sufijo = sys.argv[1] if len(sys.argv) > 1 else "00720844"
e = db.scalars(
    select(Envio).where(Envio.remito.contains(sufijo)).limit(1)
).first()
if not e:
    print("no envio")
    sys.exit(1)

rn = e.remito_norm or normalizar_remito(e.remito)
ck = clave_agrupacion_caso(e)
dist = db.execute(
    "SELECT sucursal_cod, distance_km, zona_km, km_provider FROM flete_distancias WHERE remito_norm=?",
    (rn,),
).fetchone()
dist2 = None
if ck and ck != rn:
    dist2 = db.execute(
        "SELECT sucursal_cod, distance_km, zona_km FROM flete_distancias WHERE remito_norm=?",
        (ck,),
    ).fetchone()

print("remito", e.remito)
print("remito_norm", rn, "clave_caso", ck)
print("localidad", e.localidad, "| dom", (e.domicilio or "")[:60])
print("mundo2", es_envio_mundo2(e))
print("preview", preview_flete_caso(db, e))
print("dist por rn", dist)
print("dist por ck", dist2)

envios = list(db.scalars(select(Envio)).all())
filas = construir_fletes(envios, db=db, tarifas=[])
match = [f for f in filas if sufijo in str(f.get("REMITOS", ""))]
print("fila grilla", match[0] if match else "NO")
if match:
    f = match[0]
    print("  SUCURSAL", f.get("SUCURSAL"), "KM", f.get("KM"), "ZONA", f.get("ZONA KM"))
    print("  total", f.get("total"), "alertas", f.get("_alertas_celdas"))

db.close()
