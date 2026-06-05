from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Envio, Tarifa
from app.services.fecha_utils import periodo_mes_solo, resolver_periodo_vista
from app.services.fletes_internos_service import (
    ejecutar_macheo_solicitudes,
    import_solicitudes_fletes,
    listar_detalle_internos,
    listar_fleteros,
    listar_solicitudes,
    mapa_fletero_por_remito,
    resumen_fleteros,
)
from app.services.envio_query_service import cargar_envios_filtrados
from app.services.fletes_km_service import calcular_pendientes, mapa_distancias
from app.services.mundo2_service import FLETES_COLUMNAS, construir_fletes, stats_mundo2
from app.api.routes.casos_filtros import build_filtros_casos

router = APIRouter(prefix="/fletes", tags=["fletes"])


def _envios_para_fletes(
    db: Session,
    *,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
    campo_fecha: str = "cualquiera",
    mes_control_anio: int | None = None,
    mes_control_mes: int | None = None,
):
    filtros = build_filtros_casos(
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        campo_fecha=campo_fecha,
        remito_estado="todos",
    )
    if mes_control_anio and mes_control_mes:
        d, h = resolver_periodo_vista(mes_control_anio, mes_control_mes)
        filtros["fecha_desde"] = d
        filtros["fecha_hasta"] = h
    return cargar_envios_filtrados(
        db,
        fecha_desde=filtros.get("fecha_desde"),
        fecha_hasta=filtros.get("fecha_hasta"),
        campo_fecha=str(filtros.get("campo_fecha") or "cualquiera"),
    )


@router.get("/stats")
def get_stats_fletes(
    db: Session = Depends(get_db),
    mes_control_anio: int | None = Query(None),
    mes_control_mes: int | None = Query(None, ge=1, le=12),
    campo_fecha: str = Query("cualquiera"),
) -> dict:
    envios = _envios_para_fletes(
        db,
        mes_control_anio=mes_control_anio,
        mes_control_mes=mes_control_mes,
        campo_fecha=campo_fecha,
    )
    from app.services.tarifario_version_service import TarifarioContext

    out = stats_mundo2(envios, tarifario_ctx=TarifarioContext(db), db=db)
    out["envios_cargados"] = len(envios)
    return out


@router.get("/casos")
def listar_casos_fletes(
    db: Session = Depends(get_db),
    origen: str | None = Query(None, description="tortuguitas | sa"),
    sucursal: str | None = Query(None, description="Código sucursal AV, BE…"),
    fecha_desde: str | None = Query(None),
    fecha_hasta: str | None = Query(None),
    campo_fecha: str = Query("cualquiera"),
    remito_estado: str = Query("todos"),
    fletero: str | None = Query(None, description="Código corto: BLAS, GAMA, ARMANDO…"),
    mes_control_anio: int | None = Query(None),
    mes_control_mes: int | None = Query(None, ge=1, le=12),
) -> list[dict]:
    filtros = build_filtros_casos(
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        campo_fecha=campo_fecha,
        remito_estado=remito_estado,
    )
    if mes_control_anio and mes_control_mes:
        d, h = resolver_periodo_vista(mes_control_anio, mes_control_mes)
        filtros["fecha_desde"] = d
        filtros["fecha_hasta"] = h
    envios = cargar_envios_filtrados(
        db,
        fecha_desde=filtros.get("fecha_desde"),
        fecha_hasta=filtros.get("fecha_hasta"),
        campo_fecha=str(filtros.get("campo_fecha") or "cualquiera"),
    )
    from app.services.tarifario_version_service import TarifarioContext

    tarifario_ctx = TarifarioContext(db)
    dist = mapa_distancias(db)
    mapa_f = mapa_fletero_por_remito(db)
    return construir_fletes(
        envios,
        tarifario_ctx=tarifario_ctx,
        origen=origen,
        sucursal_cod=sucursal,
        distancias=dist,
        db=db,
        mapa_fletero=mapa_f,
        fletero_corto=fletero,
        **filtros,
    )


@router.get("/columnas")
def columnas_fletes() -> dict:
    return {"columnas": FLETES_COLUMNAS}


@router.post("/calcular-km")
def post_calcular_km(
    db: Session = Depends(get_db),
    limit: int = Query(25, ge=1, le=80),
) -> dict:
    """Geocodifica y calcula km/zona (Nominatim/ORS). Procesa hasta `limit` casos nuevos."""
    envios = list(db.scalars(select(Envio)).all())
    return calcular_pendientes(db, envios, limit=limit)


@router.get("/fleteros")
def get_fleteros(db: Session = Depends(get_db)) -> list[dict]:
    return listar_fleteros(db)


@router.post("/internos/import")
async def importar_fletes_internos(
    file: UploadFile = File(...),
    matchear: bool = Query(False, description="Si true, ejecuta macheo al importar"),
    db: Session = Depends(get_db),
) -> dict:
    content = await file.read()
    return import_solicitudes_fletes(
        db,
        content,
        filename=file.filename or "fletes_solicitud.xlsx",
        ejecutar_macheo=matchear,
    )


@router.get("/internos/solicitudes")
def solicitudes_fletes_internos(db: Session = Depends(get_db)) -> list[dict]:
    return listar_solicitudes(db)


@router.post("/internos/matchear")
def matchear_fletes_internos(db: Session = Depends(get_db)) -> dict:
    return ejecutar_macheo_solicitudes(db)


@router.get("/internos/resumen")
def resumen_fletes_internos(
    db: Session = Depends(get_db),
    mes: int | None = Query(None, ge=1, le=12),
    anio: int | None = Query(None),
    fletero: str | None = Query(None),
) -> dict:
    return resumen_fleteros(db, mes=mes, anio=anio, fletero_corto=fletero)


@router.get("/internos/casos")
def casos_fletes_internos(
    db: Session = Depends(get_db),
    fletero: str | None = Query(None),
    mes: int | None = Query(None, ge=1, le=12),
    anio: int | None = Query(None),
) -> list[dict]:
    return listar_detalle_internos(db, fletero_corto=fletero, mes=mes, anio=anio)
