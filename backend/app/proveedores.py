"""Proveedores de tarifa interior — nombres canónicos y zonas de cobertura."""

from __future__ import annotations

# Orden de visualización en menú
PROVEEDORES_MENU = ("CLICPAQ", "FRANSOF", "ALFARO", "LBO")

# Alias históricos en BD / Excel → nombre canónico
PROVEEDOR_ALIASES: dict[str, str] = {
    "CLICKPAC": "CLICPAQ",
    "CLICKPACK": "CLICPAQ",
    "CLICKPAQ": "CLICPAQ",
    "CLICPAQ": "CLICPAQ",
    "FRANOV": "FRANSOF",
    "FRANSOF": "FRANSOF",
    "ALFARO": "ALFARO",
    "LBO": "LBO",
    "LBO CP": "LBO",
    "FLETES_SUC": "FLETES_SUC",
}

PROVEEDOR_LABELS: dict[str, str] = {
    "CLICPAQ": "CLICPAQ",
    "FRANSOF": "FRANSOF",
    "ALFARO": "ALFARO",
    "LBO": "LBO",
    "FLETES_SUC": "Fletes sucursales",
}


def normalizar_proveedor(nombre: str | None) -> str | None:
    if not nombre:
        return None
    key = str(nombre).strip().upper()
    return PROVEEDOR_ALIASES.get(key, key if key in PROVEEDORES_MENU else None)


def _norm_txt(value: str | None) -> str:
    return (value or "").strip().upper()


def es_zona_fransof(provincia: str | None, localidad: str | None) -> bool:
    """Localidades con cobertura FRANSOF (catálogo data/fransof_localidades.json)."""
    from app.services.fransof_localidades_service import localidad_en_cobertura_fransof

    return localidad_en_cobertura_fransof(provincia, localidad)


def es_rosario(provincia: str | None, localidad: str | None) -> bool:
    """Compatibilidad: antes solo Rosario; ahora toda la cobertura FRANSOF en Santa Fe."""
    return es_zona_fransof(provincia, localidad)


def es_cordoba(provincia: str | None) -> bool:
    return "CORDOBA" in _norm_txt(provincia) or "CÓRDOBA" in _norm_txt(provincia)


def es_zona_alfaro(provincia: str | None) -> bool:
    prov = _norm_txt(provincia)
    return any(p in prov for p in ("SALTA", "JUJUY", "TUCUMAN", "TUCUMÁN"))


def es_destino_crossdock(provincia: str | None, localidad: str | None) -> bool:
    """
    Zonas con última milla provincial (LBO / ALFARO / FRANSOF).
    Solo define tramos del crossdock 82; el transporte manda antes que la provincia.
    """
    return (
        es_cordoba(provincia)
        or es_zona_fransof(provincia, localidad)
        or es_zona_alfaro(provincia)
    )


def _caso_en_vista_por_zona(
    proveedor: str,
    provincia: str | None,
    localidad: str | None,
) -> bool:
    """Respaldo por provincia/localidad cuando no hay transporte definido."""
    p = normalizar_proveedor(proveedor)
    if not p:
        return False
    if p == "FRANSOF":
        return es_zona_fransof(provincia, localidad)
    if p == "ALFARO":
        return es_zona_alfaro(provincia)
    if p == "LBO":
        return es_cordoba(provincia)
    if p == "CLICPAQ":
        if es_zona_alfaro(provincia):
            return False
        if es_cordoba(provincia):
            return False
        return True
    return False


def caso_en_vista_proveedor(
    proveedor: str,
    provincia: str | None,
    localidad: str | None,
    *,
    transporte_cod: str | None = None,
    transporte_nombre: str | None = None,
    proveedor_asignado: str | None = None,
) -> bool:
    """
    ¿El caso va en la pestaña del proveedor?
    1) asignación  2) transporte Tango  3) zona (solo si transporte ambiguo).
    """
    p = normalizar_proveedor(proveedor)
    if not p:
        return False

    asig = normalizar_proveedor(proveedor_asignado)
    if asig:
        return p == asig

    from app.transporte_reglas import resolver_circuito_logistico

    circuito = resolver_circuito_logistico(
        transporte_cod,
        transporte_nombre,
        provincia=provincia,
        localidad=localidad,
    )
    if circuito["modo"] == "red_clicpaq":
        return p == "CLICPAQ"
    if circuito["modo"] == "fletes_suc":
        return p == "FLETES_SUC"
    if circuito["modo"] == "crossdock":
        sug = circuito["proveedor"]
        if sug:
            return p == sug
    if circuito["proveedor"] and circuito["modo"] != "ambiguo":
        return p == circuito["proveedor"]

    return _caso_en_vista_por_zona(p, provincia, localidad)


def proveedor_puede_destino(
    proveedor: str,
    provincia: str | None,
    localidad: str | None,
    *,
    transporte_cod: str | None = None,
    transporte_nombre: str | None = None,
    proveedor_asignado: str | None = None,
) -> bool:
    """Cobertura operativa: transporte Tango antes que provincia."""
    return caso_en_vista_proveedor(
        proveedor,
        provincia,
        localidad,
        transporte_cod=transporte_cod,
        transporte_nombre=transporte_nombre,
        proveedor_asignado=proveedor_asignado,
    )


def proveedores_para_selector(
    provincia: str | None,
    localidad: str | None,
    candidatos_tarifa: list[dict] | None = None,
    *,
    transporte_cod: str | None = None,
    transporte_nombre: str | None = None,
) -> list[tuple[str, float | None]]:
    """
    Opciones del desplegable: tarifario acotado por circuito del transporte.
    """
    from app.transporte_reglas import (
        acotar_candidatos_por_circuito,
        resolver_circuito_logistico,
    )

    if not candidatos_tarifa:
        return []

    circuito = resolver_circuito_logistico(
        transporte_cod,
        transporte_nombre,
        provincia=provincia,
        localidad=localidad,
    )
    sugerido = circuito["proveedor"]
    acotados = acotar_candidatos_por_circuito(circuito, candidatos_tarifa)

    items: list[tuple[str, float | None]] = []
    for c in acotados:
        nombre = normalizar_proveedor(c.get("proveedor"))
        if not nombre:
            continue
        precio = c.get("precio")
        try:
            pval = float(precio) if precio is not None else None
        except (TypeError, ValueError):
            pval = None
        items.append((nombre, pval))

    items.sort(
        key=lambda x: (
            0 if sugerido and x[0] == sugerido else 1,
            x[0],
        )
    )
    return items
