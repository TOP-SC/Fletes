"""Detecta envíos interior cross-zone con modo crossdock pero transporte != 82."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Envio
from app.proveedores import es_destino_crossdock
from app.services.proveedor_service import (
    es_crossdock_operativo,
    es_crossdocking_envio,
    es_planilla_interior,
)
from app.services.tarifario_version_service import TarifarioContext
from app.transporte_reglas import COD_CROSSDOCKING, normalizar_transporte_cod


def main() -> None:
    engine = create_engine(settings.database_url)
    with Session(engine) as db:
        envios = list(db.scalars(select(Envio)).all())
        ctx = TarifarioContext(db)

        cruzados: list[Envio] = []
        operativos: list[Envio] = []
        for e in envios:
            if not es_planilla_interior(e) or not es_destino_crossdock(e.provincia, e.localidad):
                continue
            cod = normalizar_transporte_cod(e.transporte_cod, e.transporte_nombre)
            if es_crossdocking_envio(e) and cod != COD_CROSSDOCKING:
                cruzados.append(e)
            if es_crossdock_operativo(e, ctx.tarifas_para_envio(e)):
                operativos.append(e)

        print(f"Envíos total: {len(envios)}")
        print(f"Cross operativo (2 tramos, transp 82): {len(operativos)}")
        print(f"Cross cruzados (modo cross sin ser 82): {len(cruzados)}")
        if operativos:
            ctr = Counter(
                normalizar_transporte_cod(e.transporte_cod, e.transporte_nombre)
                for e in operativos
            )
            print("Transportes en cross operativo:", dict(ctr))
        for e in cruzados[:15]:
            cod = normalizar_transporte_cod(e.transporte_cod, e.transporte_nombre)
            print(
                f"  rem={e.remito_norm} dep={e.deposito} transp={cod} "
                f"{e.transporte_nombre} → {e.localidad}/{e.provincia}"
            )


if __name__ == "__main__":
    main()
