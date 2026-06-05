from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ImportBatch
from app.schemas import ImportResult
from app.services.import_service import import_excel_file, revertir_import_batch

router = APIRouter(prefix="/import", tags=["importacion"])


@router.post("/tango", response_model=ImportResult)
async def importar_tango(
    file: UploadFile = File(...),
    proveedor_tarifa: str = "CLICPAQ",
    db: Session = Depends(get_db),
) -> ImportResult:
    content = await file.read()
    batch, rejected = import_excel_file(
        db,
        content,
        filename=file.filename or "exportacion.xlsx",
        proveedor_tarifa=proveedor_tarifa,
    )
    msg = (
        f"Importación OK: {batch.rows_inserted} nuevos, "
        f"{batch.rows_skipped} ya existían (no se pisaron)."
    )
    if rejected:
        msg += f" {rejected} filas rechazadas (sin remito ni artículo/destino)."
    return ImportResult(
        batch_id=batch.id,
        filename=batch.filename,
        rows_in_file=batch.rows_in_file,
        rows_inserted=batch.rows_inserted,
        rows_skipped=batch.rows_skipped,
        rows_rejected=rejected,
        message=msg,
    )


@router.delete("/batch/{batch_id}")
def revertir_lote(batch_id: int, db: Session = Depends(get_db)) -> dict[str, int]:
    """Quita un import erróneo para volver a cargar el Excel."""
    if not db.get(ImportBatch, batch_id):
        raise HTTPException(status_code=404, detail="Lote no encontrado")
    return revertir_import_batch(db, batch_id)
