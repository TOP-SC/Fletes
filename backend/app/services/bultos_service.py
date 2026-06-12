"""
Bultos logísticos del envío.

  - Colchón, sommier, base y diván: 1 bulto por unidad (cantidad Tango).
  - Patas sueltas (renglón accesorio): cantidad = patas; cada 6 = 1 bulto de patas.

En el total del grupo, las patas sueltas de todos los renglones se agrupan antes de ÷6.
"""

from __future__ import annotations

import math

from app.models import Envio
from app.services.pedido_cobro_service import clasificar_linea

PATAS_POR_BULTO = 6

_PATA_KEYWORDS = ("PATA", "PATAS", "PACK PAT")

_TIPOS_BULTO_UNIDAD = frozenset({"COLCHON", "SOMIER", "BASE", "DIVAN"})


def _texto_linea(envio: Envio) -> str:
    return f"{envio.descripcion or ''} {envio.cod_articulo or ''}".upper()


def _texto_articulo(descripcion: str | None, cod_articulo: str | None) -> str:
    return f"{descripcion or ''} {cod_articulo or ''}".upper()


def _tiene_keyword_patas_texto(texto: str) -> bool:
    return any(k in texto for k in _PATA_KEYWORDS)


def es_renglon_patas_sueltas(envio: Envio) -> bool:
    """Solo accesorios explícitos de patas (no sommier/colchón)."""
    renglon = clasificar_linea(envio)
    return renglon.tipo_linea == "ACCESORIO" and _tiene_keyword_patas_texto(_texto_linea(envio))


def _cantidad(envio: Envio) -> float:
    cant = float(envio.cantidad or 0)
    if cant <= 0:
        return 1.0
    return cant


def bultos_unidades_linea(envio: Envio) -> int:
    """Colchones, sommiers, bases y divanes: 1 bulto por unidad."""
    renglon = clasificar_linea(envio)
    if renglon.tipo_linea not in _TIPOS_BULTO_UNIDAD:
        return 0
    return max(1, int(math.ceil(_cantidad(envio))))


def patas_sueltas_en_linea(envio: Envio) -> float:
    if es_renglon_patas_sueltas(envio):
        return _cantidad(envio)
    return 0.0


def patas_en_linea(envio: Envio) -> float:
    return patas_sueltas_en_linea(envio)


def bultos_patas_linea(envio: Envio) -> int:
    patas = patas_sueltas_en_linea(envio)
    if patas <= 0:
        return 0
    return max(1, math.ceil(patas / PATAS_POR_BULTO))


def bultos_de_linea(envio: Envio) -> int:
    return bultos_unidades_linea(envio) + bultos_patas_linea(envio)


def etiqueta_bultos(cantidad: int) -> str:
    n = max(0, int(cantidad))
    if n <= 0:
        return ""
    return f"{n} bulto" if n == 1 else f"{n} bultos"


def etiqueta_bultos_patas(cantidad: int, *, patas: int | None = None) -> str:
    n = max(0, int(cantidad))
    if n <= 0:
        return ""
    unidad = "bulto de patas" if n == 1 else "bultos de patas"
    base = f"{n} {unidad}"
    if patas is not None and patas > 0:
        return f"{base} ({int(patas)} patas)"
    return base


def etiqueta_bultos_detalle(
    *,
    tipo_linea: str | None,
    descripcion: str | None,
    cod_articulo: str | None,
    cantidad: float | None,
    bultos: int | None,
) -> str:
    """Etiqueta para grilla de detalle; no confunde sommier con patas sueltas."""
    if bultos is None or int(bultos) <= 0:
        return ""
    n = int(bultos)
    texto = _texto_articulo(descripcion, cod_articulo)
    es_patas = (tipo_linea or "").upper() == "ACCESORIO" and _tiene_keyword_patas_texto(texto)
    if es_patas:
        patas = int(cantidad or 0)
        bp = max(1, math.ceil(patas / PATAS_POR_BULTO)) if patas > 0 else n
        return etiqueta_bultos_patas(bp, patas=patas if patas > 0 else None)
    return etiqueta_bultos(n)


def etiqueta_cantidad_logistica(envio: Envio) -> str:
    if es_renglon_patas_sueltas(envio):
        cant = int(envio.cantidad or 0)
        return etiqueta_bultos_patas(bultos_patas_linea(envio), patas=cant or None)
    unidades = bultos_unidades_linea(envio)
    if unidades > 0:
        return etiqueta_bultos(unidades)
    cant = int(envio.cantidad or 0)
    if cant > 0:
        return f"cant. {cant}"
    return "cant. 1"


def etiqueta_articulo_linea(envio: Envio) -> str:
    desc = (envio.descripcion or envio.cod_articulo or "").strip()
    if not desc:
        return ""
    cant = int(envio.cantidad or 1)
    if es_renglon_patas_sueltas(envio):
        return f"{desc} — {etiqueta_cantidad_logistica(envio)}"
    renglon = clasificar_linea(envio)
    if renglon.tipo_linea in _TIPOS_BULTO_UNIDAD:
        return f"{desc} x{cant}"
    return f"{desc} x{cant}"


def articulos_grupo_texto(lineas: list[Envio]) -> str:
    partes = [
        etiqueta_articulo_linea(l)
        for l in lineas
        if l.descripcion or l.cod_articulo
    ]
    return " | ".join(p for p in partes if p)


def bultos_grupo(lineas: list[Envio]) -> int:
    if not lineas:
        return 0
    unidades = sum(bultos_unidades_linea(l) for l in lineas)
    total_patas = sum(patas_sueltas_en_linea(l) for l in lineas)
    bultos_patas = (
        max(1, math.ceil(total_patas / PATAS_POR_BULTO)) if total_patas > 0 else 0
    )
    return unidades + bultos_patas
