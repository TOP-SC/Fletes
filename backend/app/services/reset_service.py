from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import (
    Envio,
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
        "tarifas": db.scalar(select(func.count()).select_from(Tarifa)) or 0,
    }


def cierre_mensual(db: Session, *, incluir_tarifarios: bool = False) -> dict[str, object]:
    """
    Vacía datos operativos del período (Tango, Clickpack, postventa, liquidación).
    Por defecto conserva el tarifario cargado.
    """
    antes = contar_registros(db)

    db.execute(delete(Envio))
    db.execute(delete(PrefacturaClickpac))
    db.execute(delete(PostventaRegistro))
    db.execute(delete(LiquidacionLinea))
    db.execute(delete(ImportBatch))

    tarifas_borradas = 0
    if incluir_tarifarios:
        tarifas_borradas = db.scalar(select(func.count()).select_from(Tarifa)) or 0
        db.execute(delete(Tarifa))
        db.execute(delete(TarifarioVersion))

    db.commit()
    despues = contar_registros(db)

    return {
        "ok": True,
        "mensaje": "Cierre mensual realizado. Podés importar el nuevo Excel de Tango.",
        "eliminados": {
            "envios": antes["envios"],
            "prefacturas_clickpack": antes["prefacturas_clickpack"],
            "postventa": antes["postventa"],
            "liquidacion": antes["liquidacion"],
            "importaciones": antes["importaciones"],
            "tarifas": tarifas_borradas,
        },
        "restantes": despues,
    }
