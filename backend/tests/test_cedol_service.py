"""Tests resolución CEDOL — capital vs interior."""

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import Tarifa, TarifarioVersion
from app.services.cedol_service import (
    lookup_tarifa_con_cedol,
    resolver_cedol_destino,
)
from app.services.tarifario_version_service import tarifas_activas


def _tarifas_clicpaq(db: Session) -> list[Tarifa]:
    return [
        t
        for t in tarifas_activas(db)
        if (t.proveedor or "").upper() in ("CLICPAQ", "CLICKPAC")
    ]


def test_salta_interior_no_es_capital():
    engine = create_engine("sqlite:///../data/fletes.db")
    with Session(engine) as db:
        tarifas = _tarifas_clicpaq(db)
        if not tarifas:
            return
        cedol = resolver_cedol_destino(
            "Salta",
            "Cafayate",
            tarifas=tarifas,
            proveedor="CLICPAQ",
        )
        assert cedol == "A1", f"esperado A1 interior, obtuvo {cedol}"


def test_salta_capital():
    engine = create_engine("sqlite:///../data/fletes.db")
    with Session(engine) as db:
        tarifas = _tarifas_clicpaq(db)
        if not tarifas:
            return
        cedol = resolver_cedol_destino(
            "Salta",
            "Salta Capital",
            tarifas=tarifas,
            proveedor="CLICPAQ",
        )
        assert cedol == "A0", f"esperado A0 capital, obtuvo {cedol}"


def test_chaco_resistencia_vs_interior():
    engine = create_engine("sqlite:///../data/fletes.db")
    with Session(engine) as db:
        tarifas = _tarifas_clicpaq(db)
        if not tarifas:
            return
        h0 = resolver_cedol_destino(
            "Chaco",
            "Resistencia",
            tarifas=tarifas,
            proveedor="CLICPAQ",
        )
        h1 = resolver_cedol_destino(
            "Chaco",
            "Presidencia Roque Saenz Pena",
            tarifas=tarifas,
            proveedor="CLICPAQ",
        )
        assert h0 == "H0", h0
        assert h1 == "H1", h1


def test_precio_a0_distinto_a1_salta():
    engine = create_engine("sqlite:///../data/fletes.db")
    with Session(engine) as db:
        tarifas = _tarifas_clicpaq(db)
        if not tarifas:
            return
        p0, c0 = lookup_tarifa_con_cedol(
            tarifas, "CLICPAQ", "Salta", "Salta Capital", "COLCHON", "130-150"
        )
        p1, c1 = lookup_tarifa_con_cedol(
            tarifas, "CLICPAQ", "Salta", "Cafayate", "COLCHON", "130-150"
        )
        assert c0 == "A0" and c1 == "A1"
        assert p0 is not None and p1 is not None
        assert p0 != p1, "capital e interior deben tener precios distintos"
