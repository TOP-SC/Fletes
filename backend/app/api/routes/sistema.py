from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.reset_service import cierre_mensual, contar_registros
from app.services.fransof_localidades_service import (
    listar_localidades_fransof,
    resumen_cobertura_fransof,
)
from app.transporte_reglas import resumen_reglas_transporte

router = APIRouter(prefix="/sistema", tags=["sistema"])


@router.get("/conteo")
def conteo_datos(db: Session = Depends(get_db)) -> dict[str, int]:
    return contar_registros(db)


@router.get("/transporte-reglas")
def reglas_transporte() -> dict:
    return {"reglas": resumen_reglas_transporte()}


@router.get("/fransof-cobertura")
def cobertura_fransof() -> dict:
    return {
        **resumen_cobertura_fransof(),
        "localidades": listar_localidades_fransof(),
    }


@router.post("/cierre-mensual")
def ejecutar_cierre_mensual(
    incluir_tarifarios: bool = Query(
        False,
        description="Si true, también borra el tarifario cargado",
    ),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return cierre_mensual(db, incluir_tarifarios=incluir_tarifarios)
