from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Envio, Tarifa
from app.services.export_service import export_maestro_wamaro
from app.services.fecha_utils import periodo_mes_solo, resolver_periodo_vista
from app.services.envio_query_service import cargar_envios_filtrados
from app.services.maestro_service import MAESTRO_COLUMNAS, construir_maestro, detalle_caso
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
    vista = (proveedor or vista_proveedor or "").strip().upper() or None
    envios = cargar_envios_filtrados(
        db,
        fecha_desde=filtros.get("fecha_desde"),
        fecha_hasta=filtros.get("fecha_hasta"),
        campo_fecha=str(filtros.get("campo_fecha") or "cualquiera"),
    )
    from app.services.tarifario_version_service import TarifarioContext

    tarifario_ctx = TarifarioContext(db)
    filas = construir_maestro(
        envios,
        origen=origen,
        incluir_excluidos=incluir_excluidos,
        proveedor=vista,
        solo_pendiente_proveedor=solo_pendiente_proveedor,
        tarifario_ctx=tarifario_ctx,
        db=db,
        **filtros,
    )
    if vista:
        response.headers["X-Maestro-Filtro-Zona"] = vista
        response.headers["X-Maestro-Count"] = str(len(filas))
        response.headers["X-Maestro-Envios-Cargados"] = str(len(envios))
    return filas


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
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Caso no encontrado")
    return det


@router.get("/export")
def exportar_maestro(
    db: Session = Depends(get_db),
    incluir_excluidos: bool = Query(True),
) -> Response:
    envios = list(db.scalars(select(Envio)).all())
    data = export_maestro_wamaro(envios, incluir_excluidos=incluir_excluidos)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=maestro_wamaro.xlsx"},
    )
