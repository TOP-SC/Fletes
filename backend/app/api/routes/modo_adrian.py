"""API Modo Adrián — LOG WAMARO diario (vista micro)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import MaestroPaginaOut
from app.services.envio_query_service import cargar_envios_filtrados
from app.services.fecha_utils import periodo_mes_solo, resolver_periodo_vista
from app.services.modo_adrian_service import (
    construir_log_adrian_pagina,
    construir_log_dia_adrian,
    export_log_dia_adrian_xlsx,
    listar_dias_modo_adrian,
    nombre_archivo_log_adrian,
    resumen_modo_adrian,
)

router = APIRouter(prefix="/modo-adrian", tags=["modo-adrian"])


def _periodo(
    fecha_desde: str | None,
    fecha_hasta: str | None,
    mes_control_anio: int | None,
    mes_control_mes: int | None,
) -> tuple[date | None, date | None]:
    if mes_control_anio and mes_control_mes:
        return resolver_periodo_vista(mes_control_anio, mes_control_mes)
    fd = date.fromisoformat(fecha_desde) if fecha_desde else None
    fh = date.fromisoformat(fecha_hasta) if fecha_hasta else None
    return fd, fh


@router.get("/resumen")
def get_resumen_modo_adrian(
    db: Session = Depends(get_db),
    fecha_desde: str | None = Query(None),
    fecha_hasta: str | None = Query(None),
    mes_control_anio: int | None = Query(None),
    mes_control_mes: int | None = Query(None, ge=1, le=12),
) -> dict:
    fd, fh = _periodo(fecha_desde, fecha_hasta, mes_control_anio, mes_control_mes)
    envios = cargar_envios_filtrados(
        db, fecha_desde=fd, fecha_hasta=fh, campo_fecha="entrega"
    )
    return resumen_modo_adrian(envios, fecha_desde=fd, fecha_hasta=fh)


@router.get("/dias")
def get_dias_modo_adrian(
    db: Session = Depends(get_db),
    planilla: str = Query("tortuguitas", description="tortuguitas | sa"),
    fecha_desde: str | None = Query(None),
    fecha_hasta: str | None = Query(None),
    mes_control_anio: int | None = Query(None),
    mes_control_mes: int | None = Query(None, ge=1, le=12),
) -> dict:
    if planilla not in ("tortuguitas", "sa"):
        raise HTTPException(status_code=400, detail="planilla debe ser tortuguitas o sa")
    fd, fh = _periodo(fecha_desde, fecha_hasta, mes_control_anio, mes_control_mes)
    envios = cargar_envios_filtrados(
        db, fecha_desde=fd, fecha_hasta=fh, campo_fecha="entrega"
    )
    dias = listar_dias_modo_adrian(
        envios, planilla=planilla, fecha_desde=fd, fecha_hasta=fh
    )
    return {"planilla": planilla, "dias": dias, "total_dias": len(dias)}


@router.get("/dia")
def get_log_dia_modo_adrian(
    db: Session = Depends(get_db),
    dia: str = Query(..., description="YYYY-MM-DD fecha de entrega"),
    planilla: str = Query("tortuguitas"),
    page: int = Query(1, ge=1),
    page_size: int = Query(150, ge=1, le=500),
) -> MaestroPaginaOut:
    if planilla not in ("tortuguitas", "sa"):
        raise HTTPException(status_code=400, detail="planilla debe ser tortuguitas o sa")
    try:
        fecha_dia = date.fromisoformat(dia)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="dia inválido (YYYY-MM-DD)") from exc

    fd, fh = periodo_mes_solo(fecha_dia.year, fecha_dia.month)
    envios = cargar_envios_filtrados(
        db, fecha_desde=fd, fecha_hasta=fh, campo_fecha="entrega"
    )
    from app.services.fletes_km_service import preparar_contexto_km
    from app.services.tarifario_version_service import TarifarioContext

    preparar_contexto_km(db, envios, enrich_limit=0, auto_calc_limit=0)
    ctx = TarifarioContext(db)
    filas, total = construir_log_dia_adrian(
        envios,
        dia=fecha_dia,
        planilla=planilla,
        db=db,
        tarifario_ctx=ctx,
        page=page,
        page_size=page_size,
    )
    total_pages = max(1, (total + page_size - 1) // page_size)
    return MaestroPaginaOut(
        filas=filas,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/casos", response_model=MaestroPaginaOut)
def get_log_mes_modo_adrian(
    db: Session = Depends(get_db),
    planilla: str = Query("tortuguitas"),
    mes_control_anio: int = Query(...),
    mes_control_mes: int = Query(..., ge=1, le=12),
    page: int = Query(1, ge=1),
    page_size: int = Query(150, ge=1, le=500),
) -> MaestroPaginaOut:
    if planilla not in ("tortuguitas", "sa"):
        raise HTTPException(status_code=400, detail="planilla debe ser tortuguitas o sa")
    fd, fh = resolver_periodo_vista(mes_control_anio, mes_control_mes)
    envios = cargar_envios_filtrados(
        db, fecha_desde=fd, fecha_hasta=fh, campo_fecha="entrega"
    )
    from app.services.fletes_km_service import preparar_contexto_km
    from app.services.tarifario_version_service import TarifarioContext

    preparar_contexto_km(db, envios, enrich_limit=0, auto_calc_limit=0)
    ctx = TarifarioContext(db)
    filas, total = construir_log_adrian_pagina(
        envios,
        planilla=planilla,
        fecha_desde=fd,
        fecha_hasta=fh,
        db=db,
        tarifario_ctx=ctx,
        page=page,
        page_size=page_size,
    )
    total_pages = max(1, (total + page_size - 1) // page_size)
    return MaestroPaginaOut(
        filas=filas,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/export-dia")
def export_log_dia_modo_adrian(
    db: Session = Depends(get_db),
    dia: str = Query(...),
    planilla: str = Query("tortuguitas"),
) -> Response:
    if planilla not in ("tortuguitas", "sa"):
        raise HTTPException(status_code=400, detail="planilla debe ser tortuguitas o sa")
    try:
        fecha_dia = date.fromisoformat(dia)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="dia inválido") from exc

    fd, fh = periodo_mes_solo(fecha_dia.year, fecha_dia.month)
    envios = cargar_envios_filtrados(
        db, fecha_desde=fd, fecha_hasta=fh, campo_fecha="entrega"
    )
    from app.services.fletes_km_service import preparar_contexto_km
    from app.services.tarifario_version_service import TarifarioContext

    preparar_contexto_km(db, envios, enrich_limit=0, auto_calc_limit=0)
    ctx = TarifarioContext(db)
    data = export_log_dia_adrian_xlsx(
        envios, dia=fecha_dia, planilla=planilla, db=db, tarifario_ctx=ctx
    )
    fname = nombre_archivo_log_adrian(fecha_dia, planilla)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
