from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.dashboard_service import stats_dashboard_gerencial
from app.services.kpi_entregas_service import kpi_entregas_mes

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/gerencial")
def dashboard_gerencial(db: Session = Depends(get_db)) -> dict:
    """KPIs y agregados orientados a gestión (provincias, proveedores, cuellos de botella)."""
    return stats_dashboard_gerencial(db)


@router.get("/kpi-entregas")
def dashboard_kpi_entregas(
    db: Session = Depends(get_db),
    anio: int = Query(..., ge=2020, le=2100),
    mes: int = Query(..., ge=1, le=12),
    circuito: str = Query("adrian", description="adrian | interior | todos"),
) -> dict:
    """KPI entregas x mes (Excel Grateful FC): volumen y costo LOG por quincena y CD."""
    if circuito not in ("adrian", "interior", "todos"):
        circuito = "adrian"
    return kpi_entregas_mes(db, anio=anio, mes=mes, circuito=circuito)  # type: ignore[arg-type]
