from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Envio, FleteSolicitud, Tarifa
from app.services.fecha_utils import periodo_mes_solo, resolver_periodo_vista
from app.services.fletes_internos_service import (
    ejecutar_macheo_solicitudes,
    import_solicitudes_fletes,
    listar_detalle_internos,
    listar_fleteros,
    listar_solicitudes,
    limpiar_solicitudes_fletes,
    mapa_fletero_por_remito,
    resumen_fleteros,
)
from app.services.envio_query_service import cargar_envios_filtrados
from app.services.fletes_km_service import (
    calcular_o_reusar_distancia,
    calcular_pendientes,
    enriquecer_previews_pendientes,
    info_distancia_sucursal_destino,
    preparar_contexto_km,
)
from app.schemas import MaestroPaginaOut
from app.services.mundo2_service import (
    FLETES_COLUMNAS,
    _agrupar_por_caso,
    construir_fletes_pagina,
    es_envio_mundo2,
    stats_mundo2_liviano,
)
from app.api.routes.casos_filtros import build_filtros_casos

router = APIRouter(prefix="/fletes", tags=["fletes"])


def _envios_para_fletes(
    db: Session,
    *,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
    campo_fecha: str = "entrega",
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
        campo_fecha=str(filtros.get("campo_fecha") or "entrega"),
    )


@router.get("/stats")
def get_stats_fletes(
    db: Session = Depends(get_db),
    mes_control_anio: int | None = Query(None),
    mes_control_mes: int | None = Query(None, ge=1, le=12),
    campo_fecha: str = Query("entrega"),
    fecha_desde: str | None = Query(None),
    fecha_hasta: str | None = Query(None),
) -> dict:
    envios = _envios_para_fletes(
        db,
        mes_control_anio=mes_control_anio,
        mes_control_mes=mes_control_mes,
        campo_fecha=campo_fecha,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
    )
    from app.services.tarifario_version_service import TarifarioContext

    dist = preparar_contexto_km(db, envios, enrich_limit=0, auto_calc_limit=0)
    mapa_f = mapa_fletero_por_remito(db)
    out = stats_mundo2_liviano(
        envios,
        distancias=dist,
        mapa_fletero=mapa_f,
    )
    out["envios_cargados"] = len(envios)
    n_sol = db.scalar(
        select(func.count(FleteSolicitud.id)).where(FleteSolicitud.estado != "Anulado")
    ) or 0
    n_match = db.scalar(
        select(func.count(FleteSolicitud.id)).where(
            FleteSolicitud.estado != "Anulado",
            FleteSolicitud.match_estado.in_(
                ("matcheado", "matcheado_pedido", "matcheado_cliente")
            ),
        )
    ) or 0
    out["fleteros_drive"] = {
        "solicitudes": int(n_sol),
        "matcheadas": int(n_match),
        "pendientes_cruce": max(0, int(n_sol) - int(n_match)),
    }
    if mes_control_mes and mes_control_anio:
        res_f = resumen_fleteros(
            db, mes=mes_control_mes, anio=mes_control_anio
        )
        out["fleteros_periodo"] = {
            "entregas": res_f.get("total_entregas", 0),
            "total_pagar": res_f.get("total_pagar", 0),
            "por_fletero": res_f.get("fleteros") or [],
        }
    return out


@router.get("/casos", response_model=MaestroPaginaOut)
def listar_casos_fletes(
    db: Session = Depends(get_db),
    origen: str | None = Query(None, description="tortuguitas | sa"),
    sucursal: str | None = Query(None, description="Código sucursal AV, BE…"),
    fecha_desde: str | None = Query(None),
    fecha_hasta: str | None = Query(None),
    campo_fecha: str = Query("entrega"),
    remito_estado: str = Query("todos"),
    fletero: str | None = Query(None, description="Código corto: BLAS, GAMA, ARMANDO…"),
    mes_control_anio: int | None = Query(None),
    mes_control_mes: int | None = Query(None, ge=1, le=12),
    q: str | None = Query(None, description="Buscar remito, destinatario, localidad"),
    solo_alerta: bool = Query(False),
    solo_pendiente_zona_km: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(150, ge=1, le=500),
) -> MaestroPaginaOut:
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
        campo_fecha=str(filtros.get("campo_fecha") or "entrega"),
    )
    from app.services.tarifario_version_service import TarifarioContext

    tarifario_ctx = TarifarioContext(db)
    dist = preparar_contexto_km(db, envios, enrich_limit=0, auto_calc_limit=30)
    mapa_f = mapa_fletero_por_remito(db)
    filas, total = construir_fletes_pagina(
        envios,
        page=page,
        page_size=page_size,
        tarifario_ctx=tarifario_ctx,
        origen=origen,
        sucursal_cod=sucursal,
        distancias=dist,
        db=db,
        mapa_fletero=mapa_f,
        fletero_corto=fletero,
        q=q,
        solo_alerta=solo_alerta,
        solo_pendiente_zona_km=solo_pendiente_zona_km,
        **filtros,
    )
    total_pages = max(1, (total + page_size - 1) // page_size)
    return MaestroPaginaOut(
        filas=filas,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/columnas")
def columnas_fletes() -> dict:
    return {"columnas": FLETES_COLUMNAS}


@router.post("/enriquecer-preview")
def post_enriquecer_preview(
    db: Session = Depends(get_db),
    limit: int | None = Query(None, ge=1, le=20000),
) -> dict:
    """Preview rápido: sucursal por localidad/barrio CABA + km estimado (sin geocodificar)."""
    envios = list(db.scalars(select(Envio)).all())
    return enriquecer_previews_pendientes(db, envios, limit=limit)


@router.post("/calcular-km")
def post_calcular_km(
    db: Session = Depends(get_db),
    limit: int = Query(500, ge=1, le=1000),
) -> dict:
    """Geocodifica y calcula km/zona reales (Nominatim/ORS). Hasta `limit` casos pendientes."""
    envios = list(db.scalars(select(Envio)).all())
    return calcular_pendientes(db, envios, limit=limit)


def _resolver_grupo_caso(envios: list[Envio], caso_id: str):
    grupos = _agrupar_por_caso(envios)
    grupo = grupos.get(caso_id)
    if grupo:
        return grupo
    for g in grupos.values():
        if any((e.remito or "") == caso_id for e in g):
            return g
    return None


@router.post("/caso/{caso_id}/calcular-km")
def post_calcular_km_caso(
    caso_id: str,
    db: Session = Depends(get_db),
    forzar: bool = Query(False, description="Recalcular aunque ya exista km real"),
) -> dict:
    """Geocodifica el domicilio del caso (detalle) y persiste sucursal/km/zona."""
    envios = list(db.scalars(select(Envio)).all())
    grupo = _resolver_grupo_caso(envios, caso_id)
    if not grupo:
        raise HTTPException(status_code=404, detail="Caso no encontrado")
    base = grupo[0]
    if not es_envio_mundo2(base):
        raise HTTPException(status_code=400, detail="No aplica fletes AMBA/GBA")
    try:
        row = calcular_o_reusar_distancia(db, base, forzar=forzar)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not row:
        raise HTTPException(
            status_code=400,
            detail="Sin domicilio/localidad para geocodificar",
        )
    info = info_distancia_sucursal_destino(db, base)
    return {
        "caso_id": caso_id,
        "distancia_sucursal": info,
        "remito_norm": row.remito_norm,
        "domicilio_fp": row.domicilio_fp,
    }


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


@router.delete("/internos/solicitudes")
def vaciar_solicitudes_fletes_internos(db: Session = Depends(get_db)) -> dict:
    return limpiar_solicitudes_fletes(db)


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
