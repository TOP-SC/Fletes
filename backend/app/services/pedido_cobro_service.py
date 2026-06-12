"""
Interpretación de pedidos Tango para cobro logístico.

Varios renglones con el mismo NRO PEDIDO = un envío.
No se factura cada renglón por separado: se detecta colchón solo, conjunto o diván/muebles.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from app.models import Envio
from app.services.excel_parser import infer_medida, infer_tipo_producto
from app.services.medida_utils import ancho_desde_medida, medida_a_banda

# Accesorios sin flete propio
_ACCESORIO_KEYWORDS = (
    "PATA",
    "PATAS",
    "PACK PAT",
    "ALMOH",
    "ALM.",
    "FUNDA",
    "ACOLCH",
    "PROTECTOR",
    "SABANA",
    "CUBRE",
)

_DIVAN_KEYWORDS = ("DIVAN", "DIVÁN", "DIVÁN", "BASE DIV", "BASE DIVAN")


@dataclass
class RenglonPedido:
    envio: Envio
    tipo_linea: str
    medida: str
    banda: str
    cantidad: float


@dataclass
class InterpretacionPedido:
    nro_pedido: str
    tipo_cobro: str
    medida_banda: str
    es_conjunto: bool
    linea_cobro: Envio
    renglones: list[RenglonPedido] = field(default_factory=list)
    somiers_esperados: int = 0
    somiers_detectados: float = 0.0
    advertencias: list[str] = field(default_factory=list)

    def resumen(self) -> str:
        conj = "conjunto" if self.es_conjunto else "colchón solo"
        if self.tipo_cobro == "MUEBLES":
            conj = "diván/muebles"
        return f"{self.tipo_cobro} {self.medida_banda} ({conj})"


def _norm_pedido(envio: Envio) -> str:
    p = (envio.nro_pedido or "").strip()
    if p:
        return p
    r = (envio.remito_norm or envio.remito or "").strip()
    return f"remito:{r}" if r else f"linea:{envio.id or 0}"


def clasificar_linea(envio: Envio) -> RenglonPedido:
    desc = f"{envio.descripcion or ''} {envio.cod_articulo or ''}".upper()
    cant = float(envio.cantidad or 1)
    medida = infer_medida(envio.descripcion)
    banda = medida_a_banda(medida) if medida else ""

    if any(k in desc for k in _ACCESORIO_KEYWORDS):
        return RenglonPedido(envio, "ACCESORIO", medida, banda, cant)

    if any(k in desc for k in _DIVAN_KEYWORDS):
        return RenglonPedido(envio, "DIVAN", medida, banda or "GENERICO", cant)

    tipo = infer_tipo_producto(envio.descripcion, envio.cod_articulo)
    if tipo == "COLCHON":
        return RenglonPedido(envio, "COLCHON", medida, banda, cant)
    if tipo in ("SOMIER", "BASE"):
        return RenglonPedido(envio, "SOMIER", medida, banda, cant)
    if tipo == "OTRO" and ("COLCH" in desc or "COL." in desc):
        return RenglonPedido(envio, "COLCHON", medida, banda, cant)

    return RenglonPedido(envio, tipo or "OTRO", medida, banda, cant)


def agrupar_lineas_por_pedido(lineas: list[Envio]) -> dict[str, list[Envio]]:
    grupos: dict[str, list[Envio]] = defaultdict(list)
    for e in lineas:
        grupos[_norm_pedido(e)].append(e)
    return dict(grupos)


def interpretar_pedido(lineas: list[Envio]) -> InterpretacionPedido:
    """Define tipo y medida de tarifario para cobrar el pedido una sola vez."""
    if not lineas:
        raise ValueError("pedido sin líneas")

    renglones = [clasificar_linea(e) for e in lineas]
    nro = _norm_pedido(lineas[0])

    colchones = [r for r in renglones if r.tipo_linea == "COLCHON"]
    somiers = [r for r in renglones if r.tipo_linea == "SOMIER"]
    divanes = [r for r in renglones if r.tipo_linea == "DIVAN"]
    accesorios = [r for r in renglones if r.tipo_linea == "ACCESORIO"]

    advertencias: list[str] = []

    if divanes and not colchones:
        ref = divanes[0]
        return InterpretacionPedido(
            nro_pedido=nro,
            tipo_cobro="MUEBLES",
            medida_banda=ref.banda or "GENERICO",
            es_conjunto=False,
            linea_cobro=ref.envio,
            renglones=renglones,
            advertencias=advertencias,
        )

    if colchones:
        ref = max(colchones, key=lambda r: ancho_desde_medida(r.medida) or 0)
        banda = ref.banda or "130-150"
        es_conjunto = len(somiers) > 0 or any(
            infer_tipo_producto(l.descripcion, l.cod_articulo) == "BASE" for l in lineas
        )

        somiers_detectados = sum(s.cantidad for s in somiers)
        somiers_esperados = 1
        if banda == "160-200" and es_conjunto:
            somiers_esperados = 2
        elif es_conjunto and ancho_desde_medida(ref.medida) == 80:
            somiers_esperados = 2
        elif es_conjunto and ancho_desde_medida(ref.medida) == 180:
            somiers_esperados = 2
        elif es_conjunto and ancho_desde_medida(ref.medida) == 200:
            somiers_esperados = 2

        if es_conjunto and somiers_detectados < somiers_esperados:
            advertencias.append(
                f"Conjunto {banda}: se detectaron {somiers_detectados:.0f} somier(es), "
                f"se esperaban {somiers_esperados}."
            )
        ancho_col = ancho_desde_medida(ref.medida)
        for s in somiers:
            ancho_s = ancho_desde_medida(s.medida)
            if ancho_col and ancho_s and abs(ancho_s - ancho_col) > 20:
                advertencias.append(
                    f"Somier {s.medida or '?'} no coincide con colchón {ref.medida or '?'} "
                    f"(revisar medidas del conjunto)."
                )
        if accesorios:
            advertencias.append(
                f"{len(accesorios)} renglón(es) accesorio (patas/almohadas) sin flete extra."
            )

        tipo_cobro = "CONJUNTO" if es_conjunto else "COLCHON"
        return InterpretacionPedido(
            nro_pedido=nro,
            tipo_cobro=tipo_cobro,
            medida_banda=banda,
            es_conjunto=es_conjunto,
            linea_cobro=ref.envio,
            renglones=renglones,
            somiers_esperados=somiers_esperados,
            somiers_detectados=somiers_detectados,
            advertencias=advertencias,
        )

    if somiers:
        ref = somiers[0]
        advertencias.append("Pedido sin colchón explícito; tarifa por somier/base.")
        return InterpretacionPedido(
            nro_pedido=nro,
            tipo_cobro="CONJUNTO",
            medida_banda=ref.banda or "130-150",
            es_conjunto=True,
            linea_cobro=ref.envio,
            renglones=renglones,
            advertencias=advertencias,
        )

    ref = renglones[0]
    advertencias.append("Tipo de producto no clasificado; se usa línea principal.")
    tipo = "MUEBLES" if ref.tipo_linea == "DIVAN" else "COLCHON"
    return InterpretacionPedido(
        nro_pedido=nro,
        tipo_cobro=tipo,
        medida_banda=ref.banda or "130-150",
        es_conjunto=False,
        linea_cobro=ref.envio,
        renglones=renglones,
        advertencias=advertencias,
    )


def tipo_flete_caba_gba(interp: InterpretacionPedido) -> tuple[str, str]:
    """
    Mapeo al tarifario hoja fletes sucursales (FLETES_SUC en BD).
    Tipos cargados: ``FLETE_EXPRESS`` (colchón), ``CONJUNTO_FLETE``, GENERICO (muebles).
    """
    if interp.tipo_cobro == "MUEBLES":
        return "FLETE_EXPRESS", "GENERICO"
    if interp.tipo_cobro == "CONJUNTO":
        return "CONJUNTO_FLETE", interp.medida_banda
    return "FLETE_EXPRESS", interp.medida_banda


def lineas_sin_cobro_individual(lineas: list[Envio]) -> set[int]:
    """Ids de envío que no llevan monto propio (accesorios u otros del mismo pedido)."""
    interp = interpretar_pedido(lineas)
    sin_cobro: set[int] = set()
    for r in interp.renglones:
        if r.tipo_linea == "ACCESORIO" and r.envio.id:
            sin_cobro.add(r.envio.id)
    cobro_id = interp.linea_cobro.id
    for r in interp.renglones:
        if r.envio.id and r.envio.id != cobro_id:
            sin_cobro.add(r.envio.id)
    return sin_cobro
