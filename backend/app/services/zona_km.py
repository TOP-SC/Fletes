"""Bandas de km alineadas al tarifario fletes sucursales."""

from __future__ import annotations

ZONAS_KM = ("Zona1_10km", "Zona2_20km", "Zona3_40km", "Zona4_40+km")


def km_a_zona(distance_km: float) -> tuple[int, str]:
    """Devuelve (número 1-4, clave tarifario)."""
    d = float(distance_km)
    if d <= 10:
        return 1, ZONAS_KM[0]
    if d <= 20:
        return 2, ZONAS_KM[1]
    if d <= 40:
        return 3, ZONAS_KM[2]
    return 4, ZONAS_KM[3]


def zona_etiqueta(zona_key: str | None) -> str:
    if not zona_key:
        return ""
    return zona_key.replace("_", " ").replace("+", "+")
