from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.sucursales_service import (
    listar_sucursales,
    sincronizar_sucursales,
    sucursal_a_dict,
    sucursal_por_codigo,
)

router = APIRouter(prefix="/sucursales", tags=["sucursales"])


@router.get("")
def get_sucursales(
    db: Session = Depends(get_db),
    incluir_inactivas: bool = False,
) -> dict:
    items = listar_sucursales(db, solo_activas=not incluir_inactivas)
    return {
        "total": len(items),
        "items": [sucursal_a_dict(s) for s in items],
    }


@router.get("/{codigo}")
def get_sucursal(codigo: str, db: Session = Depends(get_db)) -> dict:
    s = sucursal_por_codigo(db, codigo)
    if not s:
        raise HTTPException(status_code=404, detail="Sucursal no encontrada")
    return sucursal_a_dict(s)


@router.post("/sincronizar")
def post_sincronizar_sucursales(db: Session = Depends(get_db)) -> dict:
    """Recarga data/sucursales.json → tabla sucursales."""
    return sincronizar_sucursales(db)
