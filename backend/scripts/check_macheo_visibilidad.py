from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, select, text

from app.database import SessionLocal
from app.models import Envio
from app.services.maestro_service import construir_maestro, _origen_planilla

engine = create_engine(f"sqlite:///{Path(__file__).resolve().parents[2] / 'data' / 'fletes.db'}")
db = SessionLocal()
envios = list(db.scalars(select(Envio)).all())

print("=== Remitos prefactura prueba ===")
with engine.connect() as c:
    for r in c.execute(
        text(
            "SELECT remito, regla_color, macheo_estado, prefactura_proveedor, "
            "excluir_planilla, deposito, alerta_clickpack, abona_wamaro "
            "FROM envios WHERE remito LIKE 'R001780031802%'"
        )
    ):
        print(r)

print("\n=== Origen planilla para esos remitos ===")
for e in envios:
    if e.remito and e.remito.startswith("R001780031802"):
        print(e.remito, "deposito=", e.deposito, "origen=", _origen_planilla(e.deposito, e.origen_cd))

print("\n=== Maestro total / tortuguitas / sa ===")
for origen in [None, "tortuguitas", "sa"]:
    filas = construir_maestro(envios, origen=origen, incluir_excluidos=True)
    match = [f for f in filas if "17800318022" in str(f.get("REMITOS", "")) or "318022" in str(f.get("_caso_id", ""))]
    print(f"origen={origen}: {len(filas)} casos, match R318022: {len(match)}")
    if match:
        print(" ", match[0].get("REMITOS"), match[0].get("_regla_color"), match[0].get("PRECIO NETO"))

print("\n=== Colores en base ===")
with engine.connect() as c:
    for r in c.execute(text("SELECT regla_color, COUNT(*) FROM envios GROUP BY regla_color")):
        print(r)

db.close()
