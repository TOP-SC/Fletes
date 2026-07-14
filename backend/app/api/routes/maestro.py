from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from typing import Any

from app.database import get_db
from app.models import Envio, Tarifa
from app.services.export_service import export_maestro_wamaro
from app.services.fecha_utils import periodo_mes_solo, resolver_periodo_vista
from app.services.envio_query_service import cargar_envios_filtrados
from app.schemas import MaestroPaginaOut
from app.services.maestro_service import (
    MAESTRO_COLUMNAS,
    construir_maestro_pagina,
    detalle_caso,
    obtener_lineas_caso,
)
from app.api.routes.casos_filtros import build_filtros_casos

router = APIRouter(prefix="/maestro", tags=["maestro"])


@router.get("")
def listar_maestro(
    response: Response,
    db: Session = Depends(get_db),
    origen: str | None = Query(None, description="tortuguitas | sa"),
    incluir_excluidos: bool = Query(True),
    proveedor: str | None = Query(None, description="CLICPAQ | FRANSOF | ALFARO | LBO"),
    vista_proveedor: str | None = Query(
        None,
        description="Alias de proveedor (misma función que proveedor)",
    ),
    solo_pendiente_proveedor: bool = Query(False),
    fecha_desde: str | None = Query(None),
    fecha_hasta: str | None = Query(None),
    campo_fecha: str = Query("entrega"),
    remito_estado: str = Query("todos"),
    mes_control_anio: int | None = Query(None, description="Año del mes a controlar"),
    mes_control_mes: int | None = Query(None, ge=1, le=12),
    page: int = Query(1, ge=1),
    page_size: int = Query(150, ge=1, le=500),
    q: str | None = Query(None, description="Buscar remito, pedido, destinatario, localidad"),
    solo_alerta: bool = Query(False),
    solo_macheo: bool = Query(False),
    solo_con_dif: bool = Query(False),
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
    vista = (proveedor or vista_proveedor or "").strip().upper() or None
    envios = cargar_envios_filtrados(
        db,
        fecha_desde=filtros.get("fecha_desde"),
        fecha_hasta=filtros.get("fecha_hasta"),
        campo_fecha=str(filtros.get("campo_fecha") or "cualquiera"),
    )
    from app.services.fletes_km_service import preparar_contexto_km
    from app.services.tarifario_version_service import TarifarioContext

    preparar_contexto_km(db, envios, enrich_limit=0, auto_calc_limit=0)
    tarifario_ctx = TarifarioContext(db)
    filas, total = construir_maestro_pagina(
        envios,
        origen=origen,
        incluir_excluidos=incluir_excluidos,
        proveedor=vista,
        solo_pendiente_proveedor=solo_pendiente_proveedor,
        tarifario_ctx=tarifario_ctx,
        db=db,
        page=page,
        page_size=page_size,
        q=q,
        solo_alerta=solo_alerta,
        solo_macheo=solo_macheo,
        solo_con_dif=solo_con_dif,
        **filtros,
    )
    total_pages = max(1, (total + page_size - 1) // page_size)
    if vista:
        response.headers["X-Maestro-Filtro-Zona"] = vista
        response.headers["X-Maestro-Count"] = str(total)
        response.headers["X-Maestro-Envios-Cargados"] = str(len(envios))
    return MaestroPaginaOut(
        filas=filas,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/periodo-control")
def periodo_control(
    anio: int = Query(...),
    mes: int = Query(..., ge=1, le=12),
) -> dict:
    """Rango del mes a controlar (para referencia al exportar Tango)."""
    desde, hasta = periodo_mes_solo(anio, mes)
    return {
        "anio": anio,
        "mes": mes,
        "fecha_desde": desde.isoformat(),
        "fecha_hasta": hasta.isoformat(),
        "nota": (
            "Exportá Tango filtrando por fecha de entrega (DIST y Limansky). "
            "La grilla controla el mes por entrega por defecto."
        ),
    }


@router.get("/columnas")
def columnas_maestro() -> dict:
    return {"columnas": MAESTRO_COLUMNAS, "control": list(MAESTRO_COLUMNAS[-5:])}


@router.get("/caso/{caso_id}")
def ver_caso(caso_id: str, db: Session = Depends(get_db)) -> dict:
    envios = list(db.scalars(select(Envio)).all())
    det = detalle_caso(envios, caso_id, db)
    if not det:
        raise HTTPException(status_code=404, detail="Caso no encontrado")
    return det


class PostventaCasoIn(BaseModel):
    accion: str  # aprobar_viaje | no_pagar


class CedolCasoIn(BaseModel):
    cedol: str | None = None
    restaurar_auto: bool = False


class CasoRenglonUpdateIn(BaseModel):
    """Campos editables de un renglón del caso."""

    id: int
    nro_pedido: str | None = None
    cod_articulo: str | None = None
    descripcion: str | None = None
    cantidad: float | None = None
    m3: float | None = None
    fecha_pedido: str | None = None
    fecha_entrega: str | None = None
    razon_social: str | None = None
    domicilio: str | None = None
    localidad: str | None = None
    provincia: str | None = None
    cp: str | None = None
    deposito: str | None = None
    origen_cd: str | None = None
    transporte_cod: str | None = None
    transporte_nombre: str | None = None
    clasificacion: str | None = None
    estado_pedido: str | None = None
    leyenda_5: str | None = None
    vendedor: str | None = None
    observaciones: str | None = None
    costo_total: float | None = None
    costo_tarifario: float | None = None
    diferencia: float | None = None
    sucursal_cc: str | None = None
    prefactura_proveedor: float | None = None
    tipo_gestion: str | None = None
    sub_tipo_gestion: str | None = None
    motivo_postventa: str | None = None
    regla_postventa: str | None = None
    macheo_estado: str | None = None
    proveedor_tarifa: str | None = None
    cedol_codigo: str | None = None
    regla_motivo: str | None = None
    regla_color: str | None = None
    excluir_planilla: bool | None = None
    alerta_clickpack: bool | None = None
    abona_wamaro: bool | None = None
    entrega_cliente_sospechosa: bool | None = None
    requiere_elegir_proveedor: bool | None = None
    cedol_manual: bool | None = None
    tango_completo: dict[str, Any] | None = None


class CasoUpdateIn(BaseModel):
    """Cabecera editables + renglones opcionales."""

    razon_social: str | None = None
    domicilio: str | None = None
    localidad: str | None = None
    provincia: str | None = None
    cp: str | None = None
    fecha_pedido: str | None = None
    fecha_entrega: str | None = None
    transporte_cod: str | None = None
    transporte_nombre: str | None = None
    estado_pedido: str | None = None
    clasificacion: str | None = None
    origen_cd: str | None = None
    deposito: str | None = None
    vendedor: str | None = None
    observaciones: str | None = None
    sucursal_cc: str | None = None
    leyenda_5: str | None = None
    proveedor_tarifa: str | None = None
    prefactura_proveedor: float | None = None
    remito: str | None = None
    renglones: list[CasoRenglonUpdateIn] | None = None
    recalcular: bool = True


@router.patch("/caso/{caso_id}")
def editar_caso(
    caso_id: str,
    body: CasoUpdateIn,
    db: Session = Depends(get_db),
) -> dict:
    """Edita cabecera y/o renglones del caso; opcionalmente recalcula tarifas/reglas."""
    from app.services.caso_edit_service import actualizar_caso

    data = body.model_dump(exclude_unset=True)
    recalcular = bool(data.pop("recalcular", True))
    renglones = data.pop("renglones", None)
    try:
        return actualizar_caso(
            db,
            caso_id,
            data,
            renglones=renglones,
            recalcular=recalcular,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/caso/{caso_id}/cedol")
def actualizar_cedol_caso(
    caso_id: str,
    body: CedolCasoIn,
    db: Session = Depends(get_db),
) -> dict:
    """Corrige CEDOL manual (CLICPAQ/ALFARO) y recalcula logística del caso."""
    envios = list(db.scalars(select(Envio)).all())
    found = obtener_lineas_caso(envios, caso_id)
    if not found:
        raise HTTPException(status_code=404, detail="Caso no encontrado")
    _, lineas = found
    from app.services.cedol_service import aplicar_cedol_caso

    try:
        return aplicar_cedol_caso(
            db,
            lineas,
            cedol=body.cedol,
            restaurar_auto=body.restaurar_auto,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/caso/{caso_id}/postventa")
def resolver_postventa_caso_api(
    caso_id: str,
    body: PostventaCasoIn,
    db: Session = Depends(get_db),
) -> dict:
    if body.accion not in ("aprobar_viaje", "no_pagar"):
        raise HTTPException(status_code=400, detail="accion debe ser aprobar_viaje o no_pagar")
    envios = list(db.scalars(select(Envio)).all())
    found = obtener_lineas_caso(envios, caso_id)
    if not found:
        raise HTTPException(status_code=404, detail="Caso no encontrado")
    _, lineas = found
    from app.services.postventa_rules import resolver_postventa_caso

    try:
        return resolver_postventa_caso(db, lineas, body.accion)  # type: ignore[arg-type]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/export")
def exportar_maestro(
    db: Session = Depends(get_db),
    incluir_excluidos: bool = Query(True),
) -> Response:
    """Export Excel maestro. Solo lectura — usa cache km existente (sin enrich masivo)."""
    envios = list(db.scalars(select(Envio)).all())
    try:
        data = export_maestro_wamaro(envios, incluir_excluidos=incluir_excluidos, db=db)
    except Exception as exc:
        from fastapi import HTTPException
        import logging

        logging.getLogger(__name__).exception("export maestro")
        raise HTTPException(status_code=500, detail=f"Error al exportar: {exc}") from exc
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=maestro_wamaro.xlsx"},
    )
