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
    Zonas donde puede existir crossdock (CD → CLICPAQ → última milla provincial).
    Solo aplica si el transporte Tango es 82; destino crossdock no basta por sí solo.
    """
    return (
        es_cordoba(provincia)
        or es_zona_fransof(provincia, localidad)
        or es_zona_alfaro(provincia)
    )


def caso_en_vista_proveedor(
    proveedor: str,
    provincia: str | None,
    localidad: str | None,
) -> bool:
    """¿Este destino corresponde a la pestaña del proveedor (por zona, no por asignación)?"""
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
        # Interior CLICPAQ: no zonas exclusivas ALFARO ni LBO (Rosario sí, solapa con FRANSOF)
        if es_zona_alfaro(provincia):
            return False
        if es_cordoba(provincia):
            return False
        return True
    return False


def proveedor_puede_destino(proveedor: str, provincia: str | None, localidad: str | None) -> bool:
    """Cobertura geográfica base (antes de mirar filas del tarifario)."""
    return caso_en_vista_proveedor(proveedor, provincia, localidad)


def proveedores_para_selector(
    provincia: str | None,
    localidad: str | None,
    candidatos_tarifa: list[dict] | None = None,
    *,
    transporte_cod: str | None = None,
    transporte_nombre: str | None = None,
) -> list[tuple[str, float | None]]:
    """
    Opciones del desplegable = proveedores con tarifa para esa localidad.
    El transporte solo marca sugerencia (orden), no quita opciones del tarifario.
    """
    from app.transporte_reglas import proveedor_sugerido_transporte

    if not candidatos_tarifa:
        return []

    sugerido = proveedor_sugerido_transporte(
        transporte_cod, provincia, localidad, transporte_nombre=transporte_nombre
    )
    items: list[tuple[str, float | None]] = []
    for c in candidatos_tarifa:
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
