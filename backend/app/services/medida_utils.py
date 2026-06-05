"""Convierte medidas de producto a bandas del tarifario (80-100, 130-150, etc.)."""

import re


def ancho_desde_medida(medida: str) -> int | None:
    if not medida:
        return None
    m = re.search(r"(\d{2,3})\s*[xX×]\s*(\d{2,3})", medida.replace(" ", ""))
    if not m:
        return None
    return int(m.group(1))


def medida_a_banda(medida: str) -> str:
    """Ej: 100x200 → 80-100, 140x190 → 130-150."""
    ancho = ancho_desde_medida(medida)
    if ancho is None:
        return medida or ""
    if ancho <= 100:
        return "80-100"
    if ancho <= 150:
        return "130-150"
    return "160-200"


def medidas_equivalentes(medida: str) -> set[str]:
    """Variantes para lookup (exacta + banda)."""
    out = {medida.strip(), medida.replace(" ", "").upper()}
    banda = medida_a_banda(medida)
    if banda:
        out.add(banda)
    return {x for x in out if x}
