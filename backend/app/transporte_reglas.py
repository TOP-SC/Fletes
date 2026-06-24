"""
Reglas de transporte Tango (SommierCenter / Mantello).

Jerarquía operativa (siempre en este orden):
  1. Nº transporte Tango (+ catálogo data/transportes.json)
  2. Provincia / localidad solo para validar zona (cross 82, AMBA en 40)

  40 — Entrega en cliente → AMBA: FLETES_SUC; interior: CLICPAQ
  51 — Expreso CLICPAQ al interior → CLICPAQ (toda provincia)
  82 — Crossdocking → última milla FRANSOF / ALFARO / LBO según zona
"""

from __future__ import annotations

from typing import Any, TypedDict

from app.config import DEPOSITO_CD_HURLINGHAM
from app.proveedores import (
    es_cordoba,
    es_zona_alfaro,
    es_zona_fransof,
    normalizar_proveedor,
)
from app.services.transportes_service import (
    catalogo_transportes,
    lookup_transporte_catalogo,
    normalizar_transporte_codigo,
)

COD_ENTREGA_CLIENTE = "40"
COD_EXPRESO_CLICPAQ = "51"
COD_CROSSDOCKING = "82"

TRANSPORTE_CATALOG: dict[str, dict[str, str]] = {
    COD_ENTREGA_CLIENTE: {
        "label": "Entrega en cliente",
        "canal": "CLICPAQ",
        "modo": "directo",
    },
    COD_EXPRESO_CLICPAQ: {
        "label": "Expreso CLICPAQ",
        "canal": "CLICPAQ",
        "modo": "red",
    },
    COD_CROSSDOCKING: {
        "label": "Crossdocking",
        "canal": "CROSSDOCK",
        "modo": "crossdock",
    },
}


def _norm(value: str | None) -> str:
    return (value or "").strip().upper()


def normalizar_transporte_cod(
    transporte_cod: str | None,
    transporte_nombre: str | None = None,
) -> str | None:
    cod = normalizar_transporte_codigo(transporte_cod)
    if cod and lookup_transporte_catalogo(cod, transporte_nombre):
        return cod
    raw = str(transporte_cod or "").strip()
    if raw.isdigit():
        return normalizar_transporte_codigo(raw)
    if raw:
        digits = "".join(c for c in raw if c.isdigit())
        if digits and normalizar_transporte_codigo(digits) in {
            normalizar_transporte_codigo(k) for k in TRANSPORTE_CATALOG
        }:
            return normalizar_transporte_codigo(digits)
    nombre = _norm(transporte_nombre)
    if "ENTREGA EN CLIENTE" in nombre:
        return COD_ENTREGA_CLIENTE
    if any(x in nombre for x in ("CLICPAQ", "CLICKPAC", "CLICKPACK", "EXPRESO CLIC")):
        return COD_EXPRESO_CLICPAQ
    if "CROSSDOCK" in nombre or "CROSS DOCK" in nombre:
        return COD_CROSSDOCKING
    return cod if cod else (raw if raw.isdigit() else None)


def excluir_planilla_transporte(
    transporte_cod: str | None,
    transporte_nombre: str | None = None,
) -> bool:
    row = lookup_transporte_catalogo(transporte_cod, transporte_nombre)
    if row is not None:
        return bool(row.get("excluir_planilla"))
    t = _norm(transporte_nombre)
    if "RETIRO" in t or "RETIRA" in t:
        return True
    if "SUCURSAL" in t and "ENTREGA EN ESTA SUCURSAL" not in t:
        return True
    return False


def sin_flete_domicilio_transporte(
    transporte_cod: str | None,
    transporte_nombre: str | None = None,
) -> bool:
    row = lookup_transporte_catalogo(transporte_cod, transporte_nombre)
    if row is not None:
        return bool(row.get("sin_flete_domicilio"))
    t = _norm(transporte_nombre)
    if "RETIRA CLIENTE" in t:
        return True
    if t.startswith("RETIRA ") and "CON FLETE" not in t:
        return True
    return False


def alerta_uso_transporte(
    transporte_cod: str | None,
    transporte_nombre: str | None = None,
) -> bool:
    row = lookup_transporte_catalogo(transporte_cod, transporte_nombre)
    return bool(row.get("alerta_uso")) if row else False


class CircuitoLogistico(TypedDict):
    codigo: str | None
    modo: str
    proveedor: str | None
    proveedores_permitidos: list[str]
    usa_zona: bool


def _ultima_milla_crossdock(
    provincia: str | None,
    localidad: str | None,
) -> str | None:
    """Solo para transporte 82: quién hace sucursal → cliente."""
    if es_zona_fransof(provincia, localidad):
        return "FRANSOF"
    if es_zona_alfaro(provincia):
        return "ALFARO"
    if es_cordoba(provincia):
        return "LBO"
    return None


def resolver_circuito_logistico(
    transporte_cod: str | None,
    transporte_nombre: str | None = None,
    *,
    provincia: str | None = None,
    localidad: str | None = None,
    cp: str | None = None,
) -> CircuitoLogistico:
    """
    Circuito logístico: transporte primero; zona solo si el transporte lo requiere.
    """
    cod = normalizar_transporte_cod(transporte_cod, transporte_nombre)
    row = lookup_transporte_catalogo(transporte_cod, transporte_nombre)

    if cod == COD_EXPRESO_CLICPAQ:
        return {
            "codigo": cod,
            "modo": "red_clicpaq",
            "proveedor": "CLICPAQ",
            "proveedores_permitidos": ["CLICPAQ"],
            "usa_zona": False,
        }

    if cod == COD_CROSSDOCKING:
        ultima = _ultima_milla_crossdock(provincia, localidad)
        permitidos = ["CLICPAQ"]
        if ultima:
            permitidos.append(ultima)
        return {
            "codigo": cod,
            "modo": "crossdock",
            "proveedor": ultima or "CLICPAQ",
            "proveedores_permitidos": permitidos,
            "usa_zona": True,
        }

    if cod == COD_ENTREGA_CLIENTE:
        from app.services.rules_service import es_amba_gba, normalizar_provincia_geo

        if es_amba_gba(normalizar_provincia_geo(provincia), localidad, cp):
            return {
                "codigo": cod,
                "modo": "fletes_suc",
                "proveedor": "FLETES_SUC",
                "proveedores_permitidos": ["FLETES_SUC"],
                "usa_zona": True,
            }
        return {
            "codigo": cod,
            "modo": "red_clicpaq",
            "proveedor": "CLICPAQ",
            "proveedores_permitidos": ["CLICPAQ"],
            "usa_zona": False,
        }

    if row and row.get("proveedor"):
        prov = normalizar_proveedor(str(row["proveedor"]))
        return {
            "codigo": cod,
            "modo": str(row.get("modo") or "catalogo"),
            "proveedor": prov,
            "proveedores_permitidos": [prov] if prov else [],
            "usa_zona": False,
        }

    if row and row.get("excluir_planilla"):
        return {
            "codigo": cod,
            "modo": "excluido",
            "proveedor": None,
            "proveedores_permitidos": [],
            "usa_zona": False,
        }

    return {
        "codigo": cod,
        "modo": "ambiguo",
        "proveedor": None,
        "proveedores_permitidos": [],
        "usa_zona": True,
    }


def acotar_candidatos_por_circuito(
    circuito: CircuitoLogistico,
    candidatos: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Filtra tarifario según circuito definido por transporte."""
    permitidos = {normalizar_proveedor(p) for p in circuito["proveedores_permitidos"]}
    permitidos.discard(None)
    if not permitidos:
        return candidatos
    return [
        c
        for c in candidatos
        if normalizar_proveedor(c.get("proveedor")) in permitidos
    ]


def descripcion_canal_transporte(
    transporte_cod: str | None,
    transporte_nombre: str | None = None,
) -> str:
    row = lookup_transporte_catalogo(transporte_cod, transporte_nombre)
    if row and row.get("descripcion"):
        return str(row["descripcion"])
    cod = normalizar_transporte_cod(transporte_cod, transporte_nombre)
    if cod and cod in TRANSPORTE_CATALOG:
        return TRANSPORTE_CATALOG[cod]["label"]
    if transporte_nombre:
        return str(transporte_nombre).strip()
    return ""


def proveedor_sugerido_transporte(
    transporte_cod: str | None,
    provincia: str | None,
    localidad: str | None,
    *,
    transporte_nombre: str | None = None,
    cp: str | None = None,
) -> str | None:
    """Proveedor operativo: transporte Tango primero; zona solo en cross/AMBA."""
    circuito = resolver_circuito_logistico(
        transporte_cod,
        transporte_nombre,
        provincia=provincia,
        localidad=localidad,
        cp=cp,
    )
    return circuito["proveedor"]


def proveedores_acotados_por_transporte(
    transporte_cod: str | None,
    provincia: str | None,
    localidad: str | None,
    *,
    transporte_nombre: str | None = None,
    cp: str | None = None,
) -> list[str] | None:
    """Proveedores válidos para el circuito del transporte."""
    circuito = resolver_circuito_logistico(
        transporte_cod,
        transporte_nombre,
        provincia=provincia,
        localidad=localidad,
        cp=cp,
    )
    if circuito["proveedores_permitidos"]:
        return list(circuito["proveedores_permitidos"])
    return None


def es_canal_clicpaq(
    transporte_cod: str | None,
    transporte_nombre: str | None = None,
    deposito: str | None = None,
) -> bool:
    """Canal con prefactura CLICPAQ (51/82; 40 en interior)."""
    row = lookup_transporte_catalogo(transporte_cod, transporte_nombre)
    if row is not None:
        return bool(row.get("es_canal_clicpaq"))
    cod = normalizar_transporte_cod(transporte_cod, transporte_nombre)
    if cod in (COD_ENTREGA_CLIENTE, COD_EXPRESO_CLICPAQ, COD_CROSSDOCKING):
        return True
    t = _norm(transporte_nombre)
    if any(h in t for h in ("CLICK", "CLICKPAC", "CLICKPACK", "CLICPAQ", "EXPRESO CLIC")):
        return True
    if deposito and str(deposito).strip() == DEPOSITO_CD_HURLINGHAM:
        return True
    return False


def es_entrega_en_cliente_cod(
    transporte_cod: str | None,
    transporte_nombre: str | None = None,
) -> bool:
    row = lookup_transporte_catalogo(transporte_cod, transporte_nombre)
    if row is not None:
        return row.get("tipo") == "domicilio" and normalizar_transporte_cod(
            transporte_cod, transporte_nombre
        ) == COD_ENTREGA_CLIENTE
    cod = normalizar_transporte_cod(transporte_cod, transporte_nombre)
    if cod == COD_ENTREGA_CLIENTE:
        return True
    return "ENTREGA EN CLIENTE" in _norm(transporte_nombre)


def resumen_reglas_transporte() -> list[dict[str, Any]]:
    cat = catalogo_transportes()
    if cat:
        return [
            {
                "codigo": cod,
                "descripcion": row.get("descripcion"),
                "tipo": row.get("tipo"),
                "zona": row.get("zona"),
                "proveedor": row.get("proveedor"),
                "excluir_planilla": row.get("excluir_planilla"),
                "sin_flete_domicilio": row.get("sin_flete_domicilio"),
                "notas": row.get("notas"),
            }
            for cod, row in sorted(cat.items(), key=lambda x: (len(x[0]), x[0]))
        ]
    return [
        {
            "codigo": COD_ENTREGA_CLIENTE,
            "descripcion": "Entrega en cliente",
            "sugerencia": "CLICPAQ",
            "nota": "Canal directo CLICPAQ",
        },
        {
            "codigo": COD_EXPRESO_CLICPAQ,
            "descripcion": "Expreso CLICPAQ",
            "sugerencia": "CLICPAQ",
            "nota": "Red CLICPAQ",
        },
        {
            "codigo": COD_CROSSDOCKING,
            "descripcion": "Crossdocking",
            "sugerencia": "Por destino",
            "nota": "Santa Fe (catálogo FRANSOF)→FRANSOF, NOA→ALFARO, Córdoba→LBO",
        },
    ]
