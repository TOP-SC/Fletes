from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.cross_seguimiento_service import (
    actualizar_planillas_drive_a_inbox,
    ejecutar_macheo_cross,
    estado_planillas_cross,
    export_cross_control_xlsx,
    guardar_ultimo_resultado_cross,
    import_cross_workbook,
    importar_carpeta_cross,
    listar_inbox_cross,
    listar_registros_cross,
    resumen_cross,
)

router = APIRouter(prefix="/cross", tags=["cross"])


@router.get("/resumen")
def cross_resumen(db: Session = Depends(get_db)) -> dict:
    return resumen_cross(db)


@router.get("/inbox")
def cross_inbox() -> dict:
    """Lista .xlsx en data/cross_inbox del servidor."""
    return listar_inbox_cross()


@router.get("/estado-planillas")
def cross_estado_planillas() -> dict:
    """Estado verde/rojo/gris de las 5 planillas + último macheo."""
    return estado_planillas_cross()


@router.post("/import-carpeta")
def cross_import_carpeta(
    matchear: bool = Query(True),
    mover: bool = Query(True),
    db: Session = Depends(get_db),
) -> dict:
    """Importa todos los Excel depositados en data/cross_inbox."""
    return importar_carpeta_cross(
        db, ejecutar_macheo=matchear, mover_procesados=mover
    )


@router.post("/actualizar-desde-drive")
def cross_actualizar_desde_drive(
    importar: bool = Query(
        True,
        description="Tras bajar a inbox, importar y machear",
    ),
    matchear: bool = Query(True),
    db: Session = Depends(get_db),
) -> dict:
    """
    Copia las planillas Cross conocidas (Drive) a data/cross_inbox.
    Por defecto también importa y machea con el maestro.
    """
    return actualizar_planillas_drive_a_inbox(
        importar=importar, matchear=matchear, db=db
    )


@router.get("/registros")
def cross_registros(
    limit: int = Query(200, ge=1, le=2000),
    solo_maestro: bool = Query(False),
    db: Session = Depends(get_db),
) -> list[dict]:
    return listar_registros_cross(db, limit=limit, solo_maestro=solo_maestro)


@router.get("/export")
def cross_export(
    proveedor: str | None = Query(None),
    db: Session = Depends(get_db),
) -> Response:
    """Excel de control: cross + costo control / facturado / dif / suc / COD CLIENTE."""
    data = export_cross_control_xlsx(db, proveedor=proveedor)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="control_cross_alfaro.xlsx"'
        },
    )


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


@router.post("/matchear")
def cross_matchear(db: Session = Depends(get_db)) -> dict:
    from app.services.cross_seguimiento_service import leer_ultimo_resultado_cross

    m = ejecutar_macheo_cross(db)
    prev = leer_ultimo_resultado_cross() or {}
    guardar_ultimo_resultado_cross(
        {
            "accion": "Solo machear",
            "descargas": prev.get("descargas") or [],
            "importacion": prev.get("importacion"),
            "macheo": m,
            "message": (
                f"Macheo: {m.get('en_maestro', 0)} en maestro · "
                f"{m.get('sin_maestro', 0)} solo planilla"
            ),
        }
    )
    return m
