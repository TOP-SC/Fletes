"""Reglas Mundo 1 — interior Clickpac / Limansky."""

from __future__ import annotations

import unicodedata
from typing import Any

from app.config import DEPOSITO_ORIGEN, settings
from app.models import Envio
from app.labels import (
    MOTIVO_ABONA_WAMARO,
    MOTIVO_CANAL_RED,
    MOTIVO_CONJUNTO_OK,
    MOTIVO_ENTREGA_CLIENTE,
    MOTIVO_PREFACTURA_OK,
    MOTIVO_SIN_PREFACTURA,
)
from app.proveedores import normalizar_proveedor
from app.transporte_reglas import (
    es_canal_clicpaq,
    es_entrega_en_cliente_cod,
    excluir_planilla_transporte,
)
from app.services.excel_parser import infer_medida, infer_tipo_producto
from app.services.medida_utils import medida_a_banda, medidas_equivalentes
from app.services.remito_utils import normalizar_remito
from app.services.money_utils import round_pesos

AMBA_KEYWORDS = (
    "CABA",
    "CAPITAL FEDERAL",
    "CIUDAD AUTONOMA",
    "AVELLANEDA",
    "LANUS",
    "LANÚS",
    "LOMAS",
    "MORON",
    "MORÓN",
    "QUILMES",
    "LA PLATA",
    "SAN ISIDRO",
    "TIGRE",
    "PILAR",
    "MERLO",
    "MORENO",
    "SAN MARTIN",
    "SAN MIGUEL",
    "ITUZAINGO",
    "HAEDO",
    "CASEROS",
)

CLICKPACK_HINTS = ("CLICK", "CLICKPAC", "CLICKPACK", "LIMANSKY")


def _norm(value: str | None) -> str:
    return (value or "").strip().upper()


def _norm_geo(value: str | None) -> str:
    """Mayúsculas sin tildes — comparar provincias/localidades de Tango."""
    v = _norm(value)
    return "".join(
        c for c in unicodedata.normalize("NFD", v) if unicodedata.category(c) != "Mn"
    )


_PROVINCIA_CANON: dict[str, str] = {
    "CAPITAL FEDERAL": "CABA",
    "CIUDAD AUTONOMA DE BUENOS AIRES": "CABA",
    "CIUDAD DE BUENOS AIRES": "CABA",
    "CABA": "CABA",
    "BUENOS AIRES": "BUENOS AIRES",
    "RIO NEGRO": "RIO NEGRO",
    "CORDOBA": "CORDOBA",
    "TUCUMAN": "TUCUMAN",
    "ENTRE RIOS": "ENTRE RIOS",
    "NEUQUEN": "NEUQUEN",
    "RIOJA": "LA RIOJA",
    "LA RIOJA": "LA RIOJA",
}


def normalizar_provincia_geo(provincia: str | None) -> str:
    p = _norm_geo(provincia)
    return _PROVINCIA_CANON.get(p, p)


def es_retiro_sucursal(
    transporte: str | None,
    transporte_cod: str | None = None,
) -> bool:
    """Excluir del maestro interior por tipo retiro/sucursal/correo (catálogo o heurística)."""
    if excluir_planilla_transporte(transporte_cod, transporte):
        return True
    t = _norm(transporte)
    if "RETIRO" in t or "RETIRA" in t:
        return True
    if "SUCURSAL" in t:
        return True
    return False


def _cp_numero_ba(cp: str | None) -> int | None:
    """Parte numérica del CPA Bxxxx (Buenos Aires)."""
    cp_s = _norm(cp)
    if not cp_s.startswith("B") or len(cp_s) < 4:
        return None
    digits = "".join(c for c in cp_s[1:] if c.isdigit())
    if not digits:
        return None
    try:
        return int(digits[:4])
    except ValueError:
        return None


def es_amba_gba(provincia: str | None, localidad: str | None, cp: str | None) -> bool:
    """
    CABA y GBA conurbano → tarifario fletes sucursales (no maestro interior).

    Prioridad: provincia (CABA) antes que localidad del cliente (ej. Boedo no está en Tango).
    Interior de Buenos Aires (Mercedes, MDP, etc.) **no** es AMBA.
    """
    prov = normalizar_provincia_geo(provincia)
    loc = _norm_geo(localidad)
    if prov == "CABA":
        return True
    if "BUENOS AIRES" not in prov:
        return False
    if any(k in loc for k in AMBA_KEYWORDS):
        return True
    cp_num = _cp_numero_ba(cp)
    if cp_num is not None:
        if cp_num >= 6000:
            return False
        if cp_num < 6000:
            return True
    return False


def es_entrega_en_cliente(
    transporte: str | None,
    transporte_cod: str | None = None,
) -> bool:
    return es_entrega_en_cliente_cod(transporte_cod, transporte)


def posible_clickpack(
    transporte: str | None,
    deposito: str | None = None,
    transporte_cod: str | None = None,
) -> bool:
    return es_canal_clicpaq(transporte_cod, transporte, deposito)


def abona_wamaro_desde_leyenda(leyenda: str | None) -> bool:
    return "ABONA WAMARO" in _norm(leyenda)


def asignar_origen_y_sucursal(envio: Envio) -> None:
    dep = (envio.deposito or "").strip()
    envio.origen_cd = DEPOSITO_ORIGEN.get(dep, f"Depósito {dep}" if dep else None)
    if not envio.sucursal_cc and envio.origen_cd:
        envio.sucursal_cc = envio.origen_cd


def costo_referencia_linea(envio: Envio) -> float | None:
    if envio.costo_total is not None:
        return envio.costo_total
    return envio.costo_tarifario


def recalcular_grupo(grupo: list[Envio]) -> None:
    """Diferencia a nivel remito (conjunto colchón + somier vs 1 línea Clickpack)."""
    if not grupo:
        return
    pref = grupo[0].prefactura_proveedor
    if pref is None:
        return
    total_ref = sum(costo_referencia_linea(e) or 0 for e in grupo)
    diff = round(pref - total_ref, 2)
    for e in grupo:
        e.diferencia = diff
        if abs(diff) > 0.01:
            e.regla_color = "rojo"
            e.regla_motivo = (
                f"Diferencia prefactura ${pref:.2f} vs costo control ${total_ref:.2f} "
                f"({'conjunto' if len(grupo) > 1 else 'único'})"
            )
        elif e.regla_postventa not in ("no_pagar_transporte", "costo_cero_pendiente"):
            if e.macheo_estado == "conjunto":
                e.regla_color = "verde"
                e.regla_motivo = MOTIVO_CONJUNTO_OK


def aplicar_reglas_envio(envio: Envio, *, preservar_postventa: bool = False) -> None:
    envio.remito_norm = normalizar_remito(envio.remito)
    asignar_origen_y_sucursal(envio)

    excluir = (
        es_retiro_sucursal(envio.transporte_nombre, envio.transporte_cod)
        or es_amba_gba(envio.provincia, envio.localidad, envio.cp)
    )
    alerta = posible_clickpack(
        envio.transporte_nombre, envio.deposito, envio.transporte_cod
    )
    wamaro = abona_wamaro_desde_leyenda(envio.leyenda_5)
    sospechosa = (
        es_entrega_en_cliente(envio.transporte_nombre, envio.transporte_cod)
        and not excluir
        and not alerta
    )

    envio.excluir_planilla = excluir
    envio.alerta_clickpack = alerta
    envio.abona_wamaro = wamaro
    envio.entrega_cliente_sospechosa = sospechosa

    if preservar_postventa and envio.regla_postventa:
        return

    if excluir:
        from app.services.costo_conceptos import motivo_exclusion_planilla

        envio.regla_color = "gris"
        envio.regla_motivo = motivo_exclusion_planilla(envio)
    elif sospechosa:
        envio.regla_color = "naranja"
        envio.regla_motivo = MOTIVO_ENTREGA_CLIENTE
    elif envio.macheo_estado == "pendiente_clickpack":
        envio.regla_color = "amarillo"
        envio.regla_motivo = MOTIVO_SIN_PREFACTURA
    elif alerta and envio.macheo_estado in (None, "pendiente_clickpack"):
        envio.regla_color = "amarillo"
        envio.regla_motivo = MOTIVO_CANAL_RED
    elif (
        envio.macheo_estado in ("matcheado", "conjunto")
        and envio.prefactura_proveedor is not None
    ):
        diff = envio.diferencia if envio.diferencia is not None else 0.0
        if abs(diff) <= 0.01:
            envio.regla_color = "verde"
            envio.regla_motivo = MOTIVO_PREFACTURA_OK
            if wamaro:
                envio.regla_motivo += " — Abona Wamaro"
        else:
            envio.regla_color = "rojo"
            if not envio.regla_motivo or "Diferencia prefactura" not in (envio.regla_motivo or ""):
                envio.regla_motivo = (
                    f"Diferencia prefactura ${envio.prefactura_proveedor:.2f} vs control"
                )
    elif wamaro:
        envio.regla_color = "celeste"
        envio.regla_motivo = MOTIVO_ABONA_WAMARO
    elif envio.macheo_estado == "matcheado":
        envio.regla_color = "verde"
        envio.regla_motivo = MOTIVO_PREFACTURA_OK


def recalcular_costos_linea(
    envio: Envio,
    precio_tarifa: float | None,
    *,
    prefactura: float | None = None,
    aplicar_seguro: bool = True,
    aplicar_gestion_retiro: bool = False,
) -> None:
    base = precio_tarifa or 0.0
    if aplicar_gestion_retiro:
        base *= 1 + settings.gestion_retiro_pct
    if aplicar_seguro and base > 0:
        base += settings.seguro_fijo
    if precio_tarifa is not None:
        envio.costo_tarifario = round_pesos(round(base, 2))
    if prefactura is not None:
        envio.prefactura_proveedor = prefactura


def lookup_tarifa(
    tarifas: list[Any],
    proveedor: str,
    provincia: str,
    localidad: str,
    tipo_producto: str,
    medida: str,
) -> float | None:
    prov = normalizar_provincia_geo(provincia)
    loc = _norm_geo(localidad)
    tipo = _norm(tipo_producto)
    med_variants = medidas_equivalentes(medida) if medida else set()
    banda = medida_a_banda(medida) if medida else ""
    if banda:
        med_variants.add(banda)
    prov_key = normalizar_proveedor(proveedor) or _norm(proveedor)

    def _score_row(t: Any) -> int | None:
        tprov_canon = normalizar_proveedor(t.proveedor) or _norm(t.proveedor)
        if tprov_canon != prov_key:
            return None
        score = 0
        tprov = normalizar_provincia_geo(t.provincia)
        if tprov == prov or (tprov and prov and (tprov in prov or prov in tprov)):
            score += 2
        elif tprov in ("GENERAL", ""):
            score += 1
        else:
            return None

        tloc = _norm_geo(t.localidad)
        if tloc and loc:
            if tloc in loc or loc in tloc:
                score += 4
            elif tloc == "INTERIOR" and prov:
                score += 2
            elif "ROSARIO" in tloc and "ROSARIO" in loc:
                score += 3
            elif prov == "SANTA FE" and tprov == "SANTA FE":
                score += 2
            elif not loc:
                score += 1
            else:
                # Misma provincia, localidad distinta: match débil (ej. San Lorenzo → Santa Fe S0)
                if tprov == prov:
                    score += 1
                else:
                    return None

        ttipo = _norm(t.tipo_producto)
        if ttipo and tipo:
            if ttipo == tipo:
                score += 2
            elif ttipo == "GENERICO":
                score += 1
            elif tipo in ("BASE", "SOMIER") and ttipo == "COLCHON":
                score += 1
            elif ttipo != tipo:
                return None

        tmed = _norm(t.medida).replace(" ", "")
        if tmed and med_variants:
            if tmed in {m.upper().replace(" ", "") for m in med_variants}:
                score += 2
            elif tmed in ("GENERICO", ""):
                score += 1
            else:
                return None
        elif tmed and not med_variants:
            return None
        return score

    best_score = -1
    best_price: float | None = None
    for t in tarifas:
        score = _score_row(t)
        if score is not None and score > best_score:
            best_score = score
            best_price = t.precio
    return best_price


def lookup_tarifa_priorizado(
    tarifas: list[Any],
    proveedor: str,
    provincia: str,
    localidad: str,
    tipo_producto: str,
    medida: str,
) -> float | None:
    """
    Tarifario con jerarquía: provincia antes que localidad del cliente.
    La localidad (ej. Boedo) solo refina si hay fila exacta; si no, tarifa provincial.
    """
    prov = provincia or ""
    loc = (localidad or "").strip()
    intentos_loc: list[str] = ["", "INTERIOR"]
    if loc:
        intentos_loc.append(loc)
    prov_geo = normalizar_provincia_geo(prov)
    if prov_geo:
        intentos_loc.append(f"{prov_geo} INTERIOR")
        intentos_loc.append(prov_geo)

    vistos: set[str] = set()
    for loc_try in intentos_loc:
        key = _norm_geo(loc_try)
        if key in vistos:
            continue
        vistos.add(key)
        precio = lookup_tarifa(tarifas, proveedor, prov, loc_try, tipo_producto, medida)
        if precio is not None:
            return precio
    return None


def enrich_from_tarifario(
    envio: Envio, tarifas: list[Any], proveedor: str | None = None
) -> None:
    prov = normalizar_proveedor(proveedor or envio.proveedor_tarifa) or normalizar_proveedor(
        settings.proveedor_interior_default
    )
    medida = infer_medida(envio.descripcion)
    tipo = infer_tipo_producto(envio.descripcion, envio.cod_articulo)

    banda = medida_a_banda(medida) if medida else medida
    precio = lookup_tarifa_priorizado(
        tarifas,
        prov,
        envio.provincia or "",
        envio.localidad or "",
        tipo,
        banda or medida or "",
    )
    if precio is None and tipo in ("BASE", "SOMIER"):
        precio = lookup_tarifa_priorizado(
            tarifas,
            prov,
            envio.provincia or "",
            envio.localidad or "",
            "COLCHON",
            banda or "",
        )

    if precio is not None and envio.costo_total is None and not envio.regla_postventa:
        recalcular_costos_linea(envio, precio)
