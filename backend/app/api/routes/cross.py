from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.config import CROSS_PLANILLAS_DRIVE
from app.database import get_db
from app.schemas import CrossDriveLinkIn
from app.services.cross_seguimiento_service import (
    ejecutar_macheo_cross,
    import_cross_workbook,
    importar_cross_desde_url,
    intentar_sync_drive,
    listar_registros_cross,
    resumen_cross,
)

router = APIRouter(prefix="/cross", tags=["cross"])


@router.get("/resumen")
def cross_resumen(db: Session = Depends(get_db)) -> dict:
    return resumen_cross(db)


@router.get("/planillas-drive")
def cross_planillas_drive() -> list[dict]:
    """Planillas configuradas para sync automático (estado permiso se ve al sincronizar)."""
    return [
        {
            "label": p.get("label"),
            "sheet_id": p.get("sheet_id"),
            "activo": p.get("activo", True),
        }
        for p in CROSS_PLANILLAS_DRIVE
    ]


@router.get("/registros")
def cross_registros(
    limit: int = Query(200, ge=1, le=2000),
    solo_maestro: bool = Query(False),
    db: Session = Depends(get_db),
) -> list[dict]:
    return listar_registros_cross(db, limit=limit, solo_maestro=solo_maestro)


@router.post("/import")
async def cross_importar(
    file: UploadFile = File(...),
    matchear: bool = Query(True),
    db: Session = Depends(get_db),
) -> dict:
    content = await file.read()
    return import_cross_workbook(
        db,
        content,
        file.filename or "cross.xlsx",
        ejecutar_macheo=matchear,
    )


@router.post("/sync-drive")
def cross_sync_drive(
    matchear: bool = Query(True),
    db: Session = Depends(get_db),
) -> dict:
    return intentar_sync_drive(db, ejecutar_macheo=matchear)


@router.post("/import-drive-link")
def cross_import_drive_link(
    body: CrossDriveLinkIn,
    matchear: bool = Query(True),
    db: Session = Depends(get_db),
) -> dict:
    """Descarga planilla desde link compartido de Drive/Sheets e importa."""
    try:
        return importar_cross_desde_url(
            db,
            body.url,
            nombre=body.nombre,
            ejecutar_macheo=matchear,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/matchear")
def cross_matchear(db: Session = Depends(get_db)) -> dict:
    return ejecutar_macheo_cross(db)
