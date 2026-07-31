"""Tests CEDOL Santa Fe (S0/S1) y cobro sommier/diván."""

from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.services.cedol_service import resolver_cedol_destino
from app.services.cobro_logistica_service import calcular_cobro_pedido
from app.services.pedido_cobro_service import interpretar_pedido
from app.services.postventa_rules import envio_postventa_valorizable
from app.services.tarifario_version_service import tarifas_activas
from app.services.zona_maestro import zona_destino_maestro


def _tarifas_clicpaq(db: Session) -> list:
    return [
        t
        for t in tarifas_activas(db)
        if (t.proveedor or "").upper() in ("CLICPAQ", "CLICKPAC")
    ]


def test_santa_fe_capital_e_interior_cedol():
    engine = create_engine("sqlite:///../data/fletes.db")
    with Session(engine) as db:
        tarifas = _tarifas_clicpaq(db)
        if not tarifas:
            return
        assert (
            resolver_cedol_destino(
                "Santa Fe", "Rafaela", tarifas=tarifas, proveedor="CLICPAQ"
            )
            == "S1"
        )
        assert (
            resolver_cedol_destino(
                "Santa Fe", "Rosario", tarifas=tarifas, proveedor="CLICPAQ"
            )
            == "S0"
        )
        assert (
            resolver_cedol_destino(
                "Santa Fe", "Santa Fe", tarifas=tarifas, proveedor="CLICPAQ"
            )
            == "S0"
        )
        assert (
            resolver_cedol_destino(
                "Santa Fe",
                "Santa Fe Capital",
                tarifas=tarifas,
                proveedor="CLICPAQ",
            )
            == "S0"
        )


def test_rosario_zona_maestro_s0():
    assert zona_destino_maestro("Santa Fe", "Rosario")[0] == "S0"
    assert zona_destino_maestro("Santa Fe", "Rafaela")[0] == "S1"


def test_interpretar_solo_sommier_es_cambio():
    lineas = [
        SimpleNamespace(
            id=1,
            nro_pedido="P1",
            remito="R0017800329577",
            remito_norm="17800329577",
            descripcion="SOMIER 80 X 200",
            cod_articulo="X",
            cantidad=2,
        )
    ]
    interp = interpretar_pedido(lineas)
    assert interp.tipo_cobro == "SOMIER_CAMBIO"


def test_interpretar_colchon_mas_divan():
    lineas = [
        SimpleNamespace(
            id=1,
            nro_pedido="P2",
            remito="R1",
            remito_norm="1",
            descripcion="COLCHON 1 PLAZA 80X190",
            cod_articulo="C",
            cantidad=1,
        ),
        SimpleNamespace(
            id=2,
            nro_pedido="P2",
            remito="R1",
            remito_norm="1",
            descripcion="DIVAN CAMA 1 PLAZA",
            cod_articulo="D",
            cantidad=1,
        ),
    ]
    interp = interpretar_pedido(lineas)
    assert any(r.tipo_linea == "DIVAN" for r in interp.renglones)
    assert interp.tipo_cobro in ("COLCHON", "CONJUNTO")


def test_envio_garantia_valorizable():
    envio = SimpleNamespace(
        regla_postventa=None,
        tipo_gestion="Reclamo por garantía",
        sub_tipo_gestion="Hundido",
        observaciones=None,
    )
    assert envio_postventa_valorizable(envio) is True


def test_cobro_somier_cambio_y_divan_si_hay_tarifas():
    engine = create_engine("sqlite:///../data/fletes.db")
    with Session(engine) as db:
        tarifas = _tarifas_clicpaq(db)
        if not tarifas:
            return
        somier = SimpleNamespace(
            id=1,
            nro_pedido="P3",
            remito="R0017800329577",
            remito_norm="17800329577",
            descripcion="SOMIER QUEEN 160 X 200",
            cod_articulo="S",
            cantidad=2,
            proveedor_tarifa="CLICPAQ",
            provincia="Santa Fe",
            localidad="Rafaela",
            cp=None,
            cedol_codigo=None,
            cedol_manual=False,
            regla_postventa="cruce_medidas_aprobado",
            transporte_cod="51",
            transporte_nombre="EXPRESO CLICPAQ",
            excluir_planilla=False,
        )
        r = calcular_cobro_pedido([somier], tarifas)
        assert r.modo == "somier_cambio" or r.logistica > 0

        col = SimpleNamespace(
            id=2,
            nro_pedido="P4",
            remito="R2",
            remito_norm="2",
            descripcion="COLCHON 1 PLAZA 80X190",
            cod_articulo="C",
            cantidad=1,
            proveedor_tarifa="CLICPAQ",
            provincia="Santa Fe",
            localidad="Rafaela",
            cp=None,
            cedol_codigo=None,
            cedol_manual=False,
            regla_postventa=None,
            transporte_cod="51",
            transporte_nombre="EXPRESO CLICPAQ",
            excluir_planilla=False,
        )
        div = SimpleNamespace(
            id=3,
            nro_pedido="P4",
            remito="R2",
            remito_norm="2",
            descripcion="BASE DIVAN 1 PLAZA",
            cod_articulo="D",
            cantidad=1,
            proveedor_tarifa="CLICPAQ",
            provincia="Santa Fe",
            localidad="Rafaela",
            cp=None,
            cedol_codigo=None,
            cedol_manual=False,
            regla_postventa=None,
            transporte_cod="51",
            transporte_nombre="EXPRESO CLICPAQ",
            excluir_planilla=False,
        )
        r2 = calcular_cobro_pedido([col, div], tarifas)
        assert r2.logistica > 0
        if r2.modo == "colchon_divan":
            assert len(r2.tramos) >= 2
