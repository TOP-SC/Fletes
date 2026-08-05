"""Configuración protegida (super admin) — informes KPI ISO, etc."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app.api.deps_auth import require_super_admin
from app.database import get_db
from app.models import AppUser
from app.services.iso_kpi import compute_iso_kpis_from_db, render_iso_kpi_html

router = APIRouter(prefix="/settings", tags=["settings"])

# Permiso lógico documentado (RBAC binario: solo super admin = settings.kpi).
PERM_SETTINGS_KPI = "settings.kpi"


@router.get("/kpi-iso-report")
def kpi_iso_report(
    format: str = Query("html", pattern="^(html|json)$"),  # noqa: A002 — query name API
    db: Session = Depends(get_db),
    _user: AppUser = Depends(require_super_admin),
) -> Response:
    """
    Genera informe KPI ISO 9001 (tabla + tortas SVG).
    Requiere super administrador (permiso ``settings.kpi``).
    """
    payload = compute_iso_kpis_from_db(db)
    if format == "json":
        return JSONResponse(payload)

    html = render_iso_kpi_html(payload)
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"KPI_ISO9001_Fletes_{ts}.html"
    return Response(
        content=html.encode("utf-8"),
        media_type="text/html; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-KPI-Permission": PERM_SETTINGS_KPI,
        },
    )
