from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Envio, LiquidacionLinea, PostventaRegistro, PrefacturaClickpac
from app.schemas import ImportResult, Mundo1Stats
from app.services.export_service import export_planilla_interior
from app.services.macheo_service import (
    aplicar_postventa_a_envios,
    ejecutar_conciliacion_liquidacion,
    ejecutar_macheo_clickpack,
)
from app.services.mundo1_import import (
    import_liquidacion,
    import_postventa,
    import_prefactura_clickpack,
)

router = APIRouter(prefix="/mundo1", tags=["mundo1"])


@router.get("/stats", response_model=Mundo1Stats)
def stats_mundo1(db: Session = Depends(get_db)) -> Mundo1Stats:
    interior = (
        db.scalar(
            select(func.count())
            .select_from(Envio)
            .where(Envio.excluir_planilla.is_(False))
        )
        or 0
    )
    sin_datos = (
        db.scalar(
            select(func.count())
            .select_from(Envio)
            .where(Envio.remito.is_(None), Envio.cod_articulo.is_(None))
        )
        or 0
    )
    con_tarifa = (
        db.scalar(
            select(func.count())
            .select_from(Envio)
            .where(Envio.costo_tarifario.isnot(None), Envio.costo_tarifario > 0)
        )
        or 0
    )
    color_rows = db.execute(
        select(Envio.regla_color, func.count())
        .group_by(Envio.regla_color)
    ).all()
    por_color = {
        (c or "sin_color"): n for c, n in color_rows
    }
    return Mundo1Stats(
        envios_interior=interior,
        prefacturas_clickpack=db.scalar(select(func.count()).select_from(PrefacturaClickpac)) or 0,
        postventa_registros=db.scalar(select(func.count()).select_from(PostventaRegistro)) or 0,
        liquidacion_lineas=db.scalar(select(func.count()).select_from(LiquidacionLinea)) or 0,
        macheo_matcheados=db.scalar(
            select(func.count()).select_from(Envio).where(Envio.macheo_estado == "matcheado")
        )
        or 0,
        macheo_conjuntos=db.scalar(
            select(func.count()).select_from(Envio).where(Envio.macheo_estado == "conjunto")
        )
        or 0,
        pendientes_sin_prefactura=db.scalar(
            select(func.count())
            .select_from(Envio)
            .where(
                Envio.excluir_planilla.is_(False),
                Envio.alerta_clickpack.is_(True),
                Envio.prefactura_proveedor.is_(None),
            )
        )
        or 0,
        con_diferencia=db.scalar(
            select(func.count())
            .select_from(Envio)
            .where(
                Envio.diferencia.isnot(None),
                ((Envio.diferencia > 0.01) | (Envio.diferencia < -0.01)),
            )
        )
        or 0,
        sin_datos_tango=sin_datos,
        con_tarifa=con_tarifa,
        por_color=por_color,
    )


@router.post("/import/clickpack", response_model=ImportResult)
async def importar_clickpack(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> ImportResult:
    batch = import_prefactura_clickpack(db, await file.read(), file.filename or "clickpack.xlsx")
    return ImportResult(
        batch_id=batch.id,
        filename=batch.filename,
        rows_in_file=batch.rows_in_file,
        rows_inserted=batch.rows_inserted,
        rows_skipped=batch.rows_skipped,
        message=f"Clickpack: {batch.rows_inserted} nuevas, {batch.rows_skipped} omitidas.",
    )


@router.post("/import/postventa", response_model=ImportResult)
async def importar_postventa(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> ImportResult:
    batch = import_postventa(db, await file.read(), file.filename or "postventa.xlsx")
    return ImportResult(
        batch_id=batch.id,
        filename=batch.filename,
        rows_in_file=batch.rows_in_file,
        rows_inserted=batch.rows_inserted,
        rows_skipped=batch.rows_skipped,
        message=f"Postventa: {batch.rows_inserted} nuevos, {batch.rows_skipped} omitidos.",
    )


@router.post("/import/liquidacion", response_model=ImportResult)
async def importar_liquidacion(
    file: UploadFile = File(...),
    periodo: str = Query(..., description="Ej: 2026-05-01_15"),
    db: Session = Depends(get_db),
) -> ImportResult:
    batch = import_liquidacion(db, await file.read(), file.filename or "liquidacion.xlsx", periodo)
    return ImportResult(
        batch_id=batch.id,
        filename=batch.filename,
        rows_in_file=batch.rows_in_file,
        rows_inserted=batch.rows_inserted,
        rows_skipped=batch.rows_skipped,
        message=f"Liquidación {periodo}: {batch.rows_inserted} líneas nuevas.",
    )


@router.post("/macheo/ejecutar")
def macheo_ejecutar(db: Session = Depends(get_db)) -> dict[str, int]:
    return ejecutar_macheo_clickpack(db)


@router.post("/postventa/aplicar")
def postventa_aplicar(db: Session = Depends(get_db)) -> dict[str, int]:
    return aplicar_postventa_a_envios(db)


@router.post("/liquidacion/conciliar")
def liquidacion_conciliar(db: Session = Depends(get_db)) -> dict[str, int]:
    return ejecutar_conciliacion_liquidacion(db)


@router.post("/pipeline/completo")
def pipeline_completo(db: Session = Depends(get_db)) -> dict[str, object]:
    """Macheo + postventa en un paso (después de imports)."""
    from app.services.import_service import reaplicar_todos_envios

    reglas = reaplicar_todos_envios(db)
    macheo = ejecutar_macheo_clickpack(db)
    postventa = aplicar_postventa_a_envios(db)
    macheo2 = ejecutar_macheo_clickpack(db)
    return {"reglas": reglas, "macheo": macheo, "postventa": postventa, "macheo_final": macheo2}


@router.get("/export/planilla")
def exportar_planilla(
    incluir_excluidos: bool = Query(False),
    db: Session = Depends(get_db),
) -> Response:
    data = export_planilla_interior(db, incluir_excluidos=incluir_excluidos)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=planilla_interior.xlsx"},
    )
