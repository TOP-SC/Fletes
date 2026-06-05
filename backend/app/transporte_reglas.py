"""
Reglas de transporte Tango (SommierCenter / Mantello).

Catálogo en data/transportes.json (códigos en uso habitual).
Códigos no catalogados siguen con heurística por nombre (compatibilidad).

  40 — Entrega en cliente → AMBA: FLETES_SUC; interior: CLICPAQ
  51 — Expreso CLICPAQ al interior
  82 — Crossdocking → FRANSOF / ALFARO / LBO según destino
"""

from __future__ import annotations

from typing import Any

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
) -> str | None:
    """Sugerencia operativa por nº transporte (no asigna si el tarifario tiene 2+ proveedores)."""
    row = lookup_transporte_catalogo(transporte_cod, transporte_nombre)
    if row and row.get("proveedor"):
        return normalizar_proveedor(str(row["proveedor"]))

    cod = normalizar_transporte_cod(transporte_cod, transporte_nombre)
    if cod in (COD_ENTREGA_CLIENTE, COD_EXPRESO_CLICPAQ):
        return "CLICPAQ"
    if cod == COD_CROSSDOCKING:
        if es_zona_fransof(provincia, localidad):
            return "FRANSOF"
        if es_zona_alfaro(provincia):
            return "ALFARO"
        if es_cordoba(provincia):
            return "LBO"
    return None


def proveedores_acotados_por_transporte(
    transporte_cod: str | None,
    provincia: str | None,
    localidad: str | None,
    *,
    transporte_nombre: str | None = None,
) -> list[str] | None:
    """Solo para etiquetas UI; no limita candidatos del tarifario."""
    sug = proveedor_sugerido_transporte(
        transporte_cod, provincia, localidad, transporte_nombre=transporte_nombre
    )
    return [sug] if sug else None


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
    if deposito and str(deposito).strip() == "12":
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
