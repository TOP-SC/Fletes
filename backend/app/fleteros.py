"""Catálogo de fleteros locales (Mundo 2 — entregas sucursal → domicilio)."""

from __future__ import annotations

import re
import unicodedata


def _norm(value: str | None) -> str:
    if not value:
        return ""
    s = unicodedata.normalize("NFKD", str(value))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s.strip().upper())


# Alias cortos para filtros (BLAS, GAMA…)
ALIAS_CORTO: dict[str, str] = {
    "BLAS ANTONIO FERNANDEZ": "BLAS",
    "GAMA AGUSTIN JORGE EDUARDO": "GAMA",
    "ARMANDO RIOS": "ARMANDO",
    "OTROS": "OTROS",
}


def normalizar_nombre_fletero(nombre: str | None) -> str:
    """Nombre canónico en mayúsculas sin acentos."""
    n = _norm(nombre)
    if not n or n in ("NAN", "NONE", "-"):
        return "OTROS"
    return n


def nombre_corto_fletero(nombre: str | None) -> str:
    canon = normalizar_nombre_fletero(nombre)
    if canon in ALIAS_CORTO:
        return ALIAS_CORTO[canon]
    # Primera palabra si es nombre compuesto conocido
    parts = canon.split()
    if len(parts) >= 2 and len(parts[0]) >= 3:
        return parts[0]
    return canon[:24] if canon else "OTROS"
