from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Transporte
from app.services.transportes_service import (
    listar_transportes,
    normalizar_transporte_codigo,
    sincronizar_transportes,
    transporte_a_dict,
)

router = APIRouter(prefix="/transportes", tags=["transportes"])


@router.get("")
def get_transportes(
    db: Session = Depends(get_db),
    incluir_inactivos: bool = False,
) -> dict:
    items = listar_transportes(db, solo_en_uso=not incluir_inactivos)
    return {
        "total": len(items),
        "items": [transporte_a_dict(t) for t in items],
    }


@router.get("/{codigo}")
def get_transporte(codigo: str, db: Session = Depends(get_db)) -> dict:
    key = normalizar_transporte_codigo(codigo) or codigo.strip().upper()
    t = db.get(Transporte, key)
    if not t:
        raise HTTPException(status_code=404, detail="Transporte no encontrado")
    return transporte_a_dict(t)


@router.post("/sincronizar")
def post_sincronizar_transportes(db: Session = Depends(get_db)) -> dict:
    """Recarga data/transportes.json → tabla transportes."""
    return sincronizar_transportes(db)
