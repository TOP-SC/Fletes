from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import (
    Envio,
    FleteDistancia,
    FleteSolicitud,
    ImportBatch,
    LiquidacionLinea,
    PostventaRegistro,
    PrefacturaClickpac,
    Tarifa,
    TarifarioVersion,
)


def contar_registros(db: Session) -> dict[str, int]:
    return {
        "envios": db.scalar(select(func.count()).select_from(Envio)) or 0,
        "prefacturas_clickpack": db.scalar(select(func.count()).select_from(PrefacturaClickpac)) or 0,
        "postventa": db.scalar(select(func.count()).select_from(PostventaRegistro)) or 0,
        "liquidacion": db.scalar(select(func.count()).select_from(LiquidacionLinea)) or 0,
        "importaciones": db.scalar(select(func.count()).select_from(ImportBatch)) or 0,
        "flete_distancias": db.scalar(select(func.count()).select_from(FleteDistancia)) or 0,
        "flete_solicitudes": db.scalar(select(func.count()).select_from(FleteSolicitud)) or 0,
        "tarifas": db.scalar(select(func.count()).select_from(Tarifa)) or 0,
    }


def cierre_mensual(db: Session, *, incluir_tarifarios: bool = False) -> dict[str, object]:
    """
    Vacía TODA la base operativa (envíos Tango, CLP, postventa, km cache, solicitudes fleteros).
    No filtra por mes: borra el 100% de envios y datos ligados al período importado.
    Conserva tarifarios, transportes, sucursales y catálogo de fleteros (salvo incluir_tarifarios).
    """
    antes = contar_registros(db)

    db.execute(delete(Envio))
    db.execute(delete(PrefacturaClickpac))
    db.execute(delete(PostventaRegistro))
    db.execute(delete(LiquidacionLinea))
    db.execute(delete(ImportBatch))
    db.execute(delete(FleteDistancia))
    db.execute(delete(FleteSolicitud))

    tarifas_borradas = 0
    if incluir_tarifarios:
        tarifas_borradas = db.scalar(select(func.count()).select_from(Tarifa)) or 0
        db.execute(delete(Tarifa))
        db.execute(delete(TarifarioVersion))

    db.commit()
    despues = contar_registros(db)

    return {
        "ok": True,
        "mensaje": (
            "Cierre mensual realizado. Se borraron todos los envíos y datos operativos. "
            "Podés importar el Excel de Tango del mes nuevo."
        ),
        "eliminados": {
            "envios": antes["envios"],
            "prefacturas_clickpack": antes["prefacturas_clickpack"],
            "postventa": antes["postventa"],
            "liquidacion": antes["liquidacion"],
            "importaciones": antes["importaciones"],
            "flete_distancias": antes["flete_distancias"],
            "flete_solicitudes": antes["flete_solicitudes"],
            "tarifas": tarifas_borradas,
        },
        "restantes": despues,
    }
