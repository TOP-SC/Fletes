from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Envio, ImportBatch, Tarifa
from app.schemas import DashboardStats, EnvioOut, EnvioUpdate, ReaplicarReglasOut
from app.services.import_service import reaplicar_todos_envios
from app.services.remito_utils import normalizar_remito
from app.services.rules_service import (
    aplicar_reglas_envio,
    enrich_from_tarifario,
    recalcular_grupo,
)

router = APIRouter(prefix="/envios", tags=["envios"])


@router.get("/stats", response_model=DashboardStats)
def dashboard_stats(db: Session = Depends(get_db)) -> DashboardStats:
    total = db.scalar(select(func.count()).select_from(Envio)) or 0
    excluidos = (
        db.scalar(select(func.count()).select_from(Envio).where(Envio.excluir_planilla.is_(True)))
        or 0
    )
    alertas = (
        db.scalar(
            select(func.count()).select_from(Envio).where(Envio.alerta_clickpack.is_(True))
        )
        or 0
    )
    wamaro = (
        db.scalar(select(func.count()).select_from(Envio).where(Envio.abona_wamaro.is_(True))) or 0
    )
    ultimo = db.scalar(select(func.max(ImportBatch.imported_at)))
    batches = db.scalar(select(func.count()).select_from(ImportBatch)) or 0
    return DashboardStats(
        total_envios=total,
        excluidos=excluidos,
        alertas_clickpack=alertas,
        abona_wamaro=wamaro,
        ultimo_import=ultimo,
        import_batches=batches,
    )


@router.get("", response_model=list[EnvioOut])
def list_envios(
    db: Session = Depends(get_db),
    excluir: bool | None = Query(None),
    solo_alertas: bool = Query(False),
    solo_interior: bool = Query(False),
    macheo_estado: str | None = Query(None),
    limit: int = Query(500, le=5000),
    offset: int = Query(0, ge=0),
) -> list[Envio]:
    q = select(Envio).order_by(Envio.id.desc()).offset(offset).limit(limit)
    if excluir is not None:
        q = q.where(Envio.excluir_planilla.is_(excluir))
    if solo_interior:
        q = q.where(Envio.excluir_planilla.is_(False))
    if solo_alertas:
        q = q.where(Envio.alerta_clickpack.is_(True))
    if macheo_estado:
        q = q.where(Envio.macheo_estado == macheo_estado)
    return list(db.scalars(q).all())


@router.patch("/{envio_id}", response_model=EnvioOut)
def update_envio(
    envio_id: int,
    payload: EnvioUpdate,
    db: Session = Depends(get_db),
) -> Envio:
    envio = db.get(Envio, envio_id)
    if not envio:
        raise HTTPException(status_code=404, detail="Envío no encontrado")

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(envio, key, value)

    if envio.costo_total is not None and envio.prefactura_proveedor is not None:
        key = envio.remito_norm or normalizar_remito(envio.remito)
        grupo = list(
            db.scalars(
                select(Envio).where(
                    Envio.remito_norm == key,
                    Envio.excluir_planilla.is_(False),
                )
            ).all()
        )
        recalcular_grupo(grupo if len(grupo) > 1 else [envio])

    db.commit()
    db.refresh(envio)
    return envio


@router.post("/{envio_id}/recalcular-tarifa", response_model=EnvioOut)
def recalcular_tarifa_envio(
    envio_id: int,
    proveedor: str = Query("CLICKPAC"),
    db: Session = Depends(get_db),
) -> Envio:
    envio = db.get(Envio, envio_id)
    if not envio:
        raise HTTPException(status_code=404, detail="Envío no encontrado")
    from app.services.tarifario_version_service import TarifarioContext

    tarifas = TarifarioContext(db).tarifas_para_envio(envio)
    enrich_from_tarifario(envio, tarifas, proveedor)
    aplicar_reglas_envio(envio, preservar_postventa=True)
    db.commit()
    db.refresh(envio)
    return envio


@router.post("/reaplicar-reglas", response_model=ReaplicarReglasOut)
def reaplicar_reglas(db: Session = Depends(get_db)) -> dict:
    return reaplicar_todos_envios(db)
