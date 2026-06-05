from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Envio, Tarifa
from app.proveedores import PROVEEDORES_MENU, PROVEEDOR_LABELS, normalizar_proveedor
from app.services.import_service import reaplicar_todos_envios
from app.services.proveedor_service import elegir_proveedor_remito, stats_por_proveedor
from app.services.remito_utils import normalizar_remito

router = APIRouter(prefix="/proveedores", tags=["proveedores"])


class ElegirProveedorIn(BaseModel):
    remito_norm: str
    proveedor: str


@router.get("/lista")
def lista_proveedores() -> dict:
    return {
        "proveedores": [
            {"id": p, "nombre": PROVEEDOR_LABELS.get(p, p)} for p in PROVEEDORES_MENU
        ]
    }


@router.get("/stats")
def estadisticas_proveedores(db: Session = Depends(get_db)) -> dict:
    envios = list(db.scalars(select(Envio)).all())
    return stats_por_proveedor(envios)


@router.post("/asignar-todos")
def asignar_proveedores_todos(db: Session = Depends(get_db)) -> dict:
    """Recalcula proveedor + tarifas + reglas (mismo que reaplicar reglas)."""
    return reaplicar_todos_envios(db)


@router.post("/elegir")
def elegir_proveedor(payload: ElegirProveedorIn, db: Session = Depends(get_db)) -> dict:
    canon = normalizar_proveedor(payload.proveedor)
    if not canon:
        raise HTTPException(status_code=400, detail="Proveedor no válido")
    key = payload.remito_norm.strip() or normalizar_remito(payload.remito_norm)
    if not key:
        raise HTTPException(status_code=400, detail="Remito inválido")
    from app.services.tarifario_version_service import TarifarioContext

    tarifario_ctx = TarifarioContext(db)
    n = elegir_proveedor_remito(db, key, canon, tarifario_ctx=tarifario_ctx)
    if n == 0:
        raise HTTPException(status_code=404, detail="Caso no encontrado")
    reaplicar_todos_envios(db)
    return {"renglones_actualizados": n, "proveedor": canon}
