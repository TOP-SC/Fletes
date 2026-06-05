from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Tarifa
from app.schemas import TarifaIn, TarifaOut
from app.services.import_service import reaplicar_todos_envios
from app.services.tarifario_version_service import (
    activar_version,
    descartar_borrador,
    diff_version,
    escanear_carpeta_tarifarios,
    importar_archivo_como_borrador,
    listar_estado,
    listar_versiones,
    rollback_proveedor,
    tarifas_activas,
)
from app.services.tariff_service import create_tarifa, import_tarifarios_desde_carpeta

router = APIRouter(prefix="/tarifas", tags=["tarifas"])


@router.get("", response_model=list[TarifaOut])
def list_tarifas(
    db: Session = Depends(get_db),
    solo_activas: bool = Query(True, description="Solo tarifas de versiones activas"),
) -> list[Tarifa]:
    if solo_activas:
        return tarifas_activas(db)
    return list(db.scalars(select(Tarifa).order_by(Tarifa.id.desc())).all())


@router.get("/estado")
def estado_tarifarios(db: Session = Depends(get_db)) -> dict:
    return listar_estado(db)


@router.get("/para-fecha")
def tarifario_para_fecha(
    fecha: str = Query(..., description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
) -> dict:
    """Qué versiones de tarifario aplican en una fecha (consulta histórica)."""
    from app.services.tarifario_version_service import TarifarioContext

    ctx = TarifarioContext(db)
    return {
        "fecha": fecha[:10],
        "versiones": ctx.versiones_para_fecha(fecha),
        "filas_tarifa": len(ctx.tarifas_para_fecha(fecha)),
    }


@router.get("/versiones")
def versiones_tarifario(
    db: Session = Depends(get_db),
    proveedor: str | None = None,
    estado: str | None = None,
) -> list[dict]:
    return listar_versiones(db, proveedor=proveedor, estado=estado)


@router.get("/versiones/{version_id}/diff")
def preview_diff_version(version_id: int, db: Session = Depends(get_db)) -> dict:
    return diff_version(db, version_id)


@router.post("/versiones/{version_id}/activar")
def activar_version_tarifario(
    version_id: int,
    db: Session = Depends(get_db),
    recalcular: bool = Query(True),
    vigencia_desde: str | None = Query(
        None,
        description="Fecha de corte ISO (ej. 2026-05-16). Envíos anteriores usan tarifario previo.",
    ),
) -> dict:
    out = activar_version(db, version_id, vigencia_desde=vigencia_desde)
    if recalcular and "error" not in out and not out.get("omitido"):
        out["reaplicado"] = reaplicar_todos_envios(db)
    return out


@router.post("/versiones/{version_id}/descartar")
def descartar_version_borrador(version_id: int, db: Session = Depends(get_db)) -> dict:
    return descartar_borrador(db, version_id)


@router.post("/versiones/rollback/{proveedor}")
def rollback_tarifario_proveedor(proveedor: str, db: Session = Depends(get_db)) -> dict:
    out = rollback_proveedor(db, proveedor)
    if "error" not in out:
        out["reaplicado"] = reaplicar_todos_envios(db)
    return out


@router.post("", response_model=TarifaOut)
def alta_tarifa(payload: TarifaIn, db: Session = Depends(get_db)) -> Tarifa:
    return create_tarifa(db, payload)


@router.post("/import")
async def importar_tarifas(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    recalcular: bool = Query(False),
) -> dict[str, object]:
    content = await file.read()
    out = importar_archivo_como_borrador(db, content, file.filename or "upload.xlsx")
    if recalcular and out.get("activadas_auto"):
        out["reaplicado"] = reaplicar_todos_envios(db)
    return out


@router.post("/escanear-carpeta")
def escanear_tarifarios_carpeta(db: Session = Depends(get_db)) -> dict[str, object]:
    return escanear_carpeta_tarifarios(db)


@router.post("/import-carpeta")
def importar_tarifarios_carpeta(
    db: Session = Depends(get_db),
    recalcular: bool = Query(False),
) -> dict[str, object]:
    out = import_tarifarios_desde_carpeta(db)
    if recalcular and out.get("activadas_auto"):
        out["reaplicado"] = reaplicar_todos_envios(db)
    return out


@router.post("/recalcular-envios")
def recalcular_tarifas_en_envios(db: Session = Depends(get_db)) -> dict[str, object]:
    """Reaplica proveedor + cobro (simple y crossdock) con el tarifario actual."""
    return reaplicar_todos_envios(db)


@router.delete("/{tarifa_id}")
def eliminar_tarifa(tarifa_id: int, db: Session = Depends(get_db)) -> dict[str, str]:
    tarifa = db.get(Tarifa, tarifa_id)
    if tarifa:
        db.delete(tarifa)
        db.commit()
    return {"status": "ok"}
