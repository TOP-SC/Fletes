"""Códigos de zona del maestro manual WAMARO (C0, B3, S0, K0, …)."""

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

# Capitales provinciales → código CEDOL / legacy CLP (resto de la provincia = interior).
# Valor: (código, etiqueta, aliases de localidad capital)
_CAPITALES: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "SANTA FE": ("S0", "SANTA FE CAPITAL", ("SANTA FE",)),
    "CHACO": ("H0", "CHACO CAPITAL", ("RESISTENCIA",)),
    "MISIONES": ("N0", "MISIONES CAPITAL", ("POSADAS",)),
    "SAN LUIS": ("D0", "SAN LUIS CAPITAL", ("SAN LUIS",)),
    "CATAMARCA": (
        "K0",
        "CATAMARCA CAPITAL",
        ("SAN FERNANDO DEL VALLE DE CATAMARCA", "CATAMARCA"),
    ),
    "CORDOBA": ("X0", "CORDOBA CAPITAL", ("CORDOBA",)),
    "MENDOZA": ("M0", "MENDOZA CAPITAL", ("MENDOZA",)),
    "SAN JUAN": ("J0", "SAN JUAN CAPITAL", ("SAN JUAN",)),
    "LA RIOJA": ("F0", "LA RIOJA CAPITAL", ("LA RIOJA",)),
    "SALTA": ("A0", "SALTA CAPITAL", ("SALTA",)),
    "JUJUY": ("Y0", "JUJUY CAPITAL", ("SAN SALVADOR DE JUJUY", "JUJUY")),
    "TUCUMAN": ("T1", "TUCUMAN CAPITAL", ("SAN MIGUEL DE TUCUMAN", "TUCUMAN")),
    "ENTRE RIOS": ("E0", "ENTRE RIOS CAPITAL", ("PARANA",)),
    "NEUQUEN": ("Q0", "NEUQUEN CAPITAL", ("NEUQUEN",)),
    "RIO NEGRO": ("R0", "RIO NEGRO CAPITAL", ("VIEDMA",)),
    "CHUBUT": ("U0", "CHUBUT CAPITAL", ("RAWSON",)),
    "SANTA CRUZ": ("Z0", "SANTA CRUZ CAPITAL", ("RIO GALLEGOS",)),
    "FORMOSA": ("P0", "FORMOSA CAPITAL", ("FORMOSA",)),
    "LA PAMPA": ("L0", "LA PAMPA CAPITAL", ("SANTA ROSA",)),
    "SANTIAGO DEL ESTERO": (
        "G0",
        "SANTIAGO DEL ESTERO CAPITAL",
        ("SANTIAGO DEL ESTERO",),
    ),
}

# Interior explícito (evita abreviar provincia a 2 letras tipo CATAMARCA→CA).
_INTERIORES: dict[str, tuple[str, str]] = {
    "SANTA FE": ("S1", "SANTA FE INTERIOR"),
    "MENDOZA": ("M1", "MENDOZA INTERIOR"),
    "RIO NEGRO": ("R1", "RIO NEGRO INTERIOR"),
    "SANTA CRUZ": ("Z1", "SANTA CRUZ INTERIOR"),
    "SAN JUAN": ("J1", "SAN JUAN INTERIOR"),
    "CHACO": ("H1", "CHACO INTERIOR"),
    "MISIONES": ("N1", "MISIONES INTERIOR"),
    "SAN LUIS": ("D1", "SAN LUIS INTERIOR"),
    "CATAMARCA": ("K1", "CATAMARCA INTERIOR"),
    "CORDOBA": ("X1", "CORDOBA INTERIOR"),
    "LA RIOJA": ("F1", "LA RIOJA INTERIOR"),
    "SALTA": ("A1", "SALTA INTERIOR"),
    "JUJUY": ("Y1", "JUJUY INTERIOR"),
    "TUCUMAN": ("T2", "TUCUMAN INTERIOR"),
    "ENTRE RIOS": ("E1", "ENTRE RIOS INTERIOR"),
    "NEUQUEN": ("Q1", "NEUQUEN INTERIOR"),
    "CHUBUT": ("U1", "CHUBUT INTERIOR"),
    "FORMOSA": ("P1", "FORMOSA INTERIOR"),
    "LA PAMPA": ("L1", "LA PAMPA INTERIOR"),
    "SANTIAGO DEL ESTERO": ("G1", "SANTIAGO DEL ESTERO INTERIOR"),
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
        cap_code, cap_label, aliases = _CAPITALES[prov]
        if loc and (
            "CAPITAL" in loc
            or loc == prov
            or any(a == loc or a in loc or loc in a for a in aliases)
        ):
            return (cap_code, cap_label)

    if prov in _INTERIORES:
        return _INTERIORES[prov]

    if prov:
        # Fallback: letra + 1 (interior), no las 2 primeras letras (CA ≠ Catamarca CLP).
        letra = prov[0]
        return (f"{letra}1", f"{prov} INTERIOR")
    return ("", "")
