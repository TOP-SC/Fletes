"""Códigos de zona del maestro manual WAMARO (C0, B3, S0, …)."""

from __future__ import annotations

import unicodedata

from app.config import DEPOSITO_CD_HURLINGHAM, DEPOSITO_CD_TORTUGUITAS, DEPOSITO_ORIGEN

_CABA_PROVINCIAS = frozenset(
    {
        "CABA",
        "CAPITAL FEDERAL",
        "CIUDAD AUTONOMA DE BUENOS AIRES",
        "CIUDAD AUTÓNOMA DE BUENOS AIRES",
    }
)

# Capitales provinciales → código legacy (resto de la provincia = interior).
_CAPITALES: dict[str, tuple[str, str]] = {
    "SANTA FE": ("S0", "SANTA FE CAPITAL"),
    "CHACO": ("H0", "CHACO CAPITAL"),
    "MISIONES": ("N0", "MISIONES CAPITAL"),
    "SAN LUIS": ("D0", "SAN LUIS CAPITAL"),
}

_LOCALIDADES_ESPECIALES: dict[str, tuple[str, str]] = {
    "MAR DEL PLATA": ("B1", "COSTA ATLANTICA 1 (MDQ)"),
    "BARRIO RAWSON": ("J1", "SAN JUAN INTERIOR"),
}


def _norm(value: str | None) -> str:
    v = (value or "").strip().upper()
    return "".join(
        c for c in unicodedata.normalize("NFD", v) if unicodedata.category(c) != "Mn"
    )


def zona_origen_maestro(deposito: str | None, origen_cd: str | None) -> tuple[str, str]:
    dep = (deposito or "").strip()
    if dep == DEPOSITO_CD_HURLINGHAM:
        return ("C0", "CAPITAL FEDERAL")
    if dep == DEPOSITO_CD_TORTUGUITAS:
        return ("T0", "TORTUGUITAS")
    desc = origen_cd or DEPOSITO_ORIGEN.get(dep, "")
    if desc:
        return (dep or "", str(desc).upper())
    return (dep or "", "")


def zona_destino_maestro(
    provincia: str | None,
    localidad: str | None,
    *,
    es_amba_gba: bool = False,
) -> tuple[str, str]:
    """Zona destino: provincia primero; localidad solo para casos especiales (MDP, etc.)."""
    prov = _norm(provincia)
    loc = _norm(localidad)

    if es_amba_gba or prov in _CABA_PROVINCIAS:
        return ("B0", "GRAN BUENOS AIRES")

    for key, zona in _LOCALIDADES_ESPECIALES.items():
        if key in loc:
            return zona

    if "BUENOS AIRES" in prov:
        return ("B3", "INTERIOR BUENOS AIRES")

    if prov in _CAPITALES:
        cap_label = _CAPITALES[prov][1]
        if loc and (cap_label in loc or "CAPITAL" in loc):
            return _CAPITALES[prov]

    if prov == "SANTA FE":
        return ("S1", "SANTA FE INTERIOR")
    if prov == "MENDOZA":
        return ("M1", "MENDOZA INTERIOR")
    if prov == "RIO NEGRO":
        return ("R1", "RIO NEGRO INTERIOR")
    if prov == "SANTA CRUZ":
        return ("Z1", "SANTA CRUZ INTERIOR")
    if prov == "SAN JUAN":
        return ("J1", "SAN JUAN INTERIOR")
    if prov == "CHACO":
        return ("H1", "CHACO INTERIOR")
    if prov == "MISIONES":
        return ("N1", "MISIONES INTERIOR")
    if prov == "SAN LUIS":
        return ("D1", "SAN LUIS INTERIOR")

    if prov:
        cod = prov[:2].ljust(2, "0")
        return (cod, f"{prov} INTERIOR")
    return ("", "")
