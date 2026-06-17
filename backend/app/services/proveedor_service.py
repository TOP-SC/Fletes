"""Asignación de proveedor de tarifa por destino y tarifario."""

from __future__ import annotations

import json
from typing import Any

from app.models import Envio, Tarifa
from app.proveedores import (
    PROVEEDORES_MENU,
    es_cordoba,
    es_zona_fransof,
    es_zona_alfaro,
    normalizar_proveedor,
)
from app.transporte_reglas import (
    COD_CROSSDOCKING,
    acotar_candidatos_por_circuito,
    normalizar_transporte_cod,
    proveedor_sugerido_transporte,
    resolver_circuito_logistico,
)
from app.services.excel_parser import infer_medida, infer_tipo_producto
from app.services.medida_utils import medida_a_banda
from app.services.cobro_logistica_service import aplicar_cobro_linea
from app.services.costo_conceptos import (
    PROVEEDOR_FLETE_LOCAL,
    es_amba_gba_envio,
    es_retiro_sin_flete_domicilio,
)
from app.services.rules_service import (
    es_retiro_sucursal,
    lookup_tarifa_priorizado,
    recalcular_costos_linea,
)


def _candidato_dict(proveedor: str, precio: float) -> dict[str, Any]:
    return {"proveedor": proveedor, "precio": round(precio, 2)}


def candidatos_tarifa(
    envio: Envio,
    tarifas: list[Tarifa],
) -> list[dict[str, Any]]:
    """
    Proveedores con precio en tarifario para este destino/artículo.
    """
    medida = infer_medida(envio.descripcion)
    tipo = infer_tipo_producto(envio.descripcion, envio.cod_articulo)
    banda = medida_a_banda(medida) if medida else medida

    candidatos: list[dict[str, Any]] = []
    for prov in PROVEEDORES_MENU:
        precio = lookup_tarifa_priorizado(
            tarifas,
            prov,
            envio.provincia or "",
            envio.localidad or "",
            tipo,
            banda or medida or "",
            cp=envio.cp,
        )
        if precio is None and tipo in ("BASE", "SOMIER"):
            precio = lookup_tarifa_priorizado(
                tarifas,
                prov,
                envio.provincia or "",
                envio.localidad or "",
                "COLCHON",
                banda or "",
                cp=envio.cp,
            )
        if precio is not None and precio > 0:
            candidatos.append(_candidato_dict(prov, precio))

    por_nombre: dict[str, dict[str, Any]] = {}
    for c in candidatos:
        p = c["proveedor"]
        if p not in por_nombre or c["precio"] < por_nombre[p]["precio"]:
            por_nombre[p] = c
    return list(por_nombre.values())


def cuenta_proveedores_tarifario(candidatos: list[dict[str, Any]]) -> int:
    return len({c["proveedor"] for c in candidatos})


def requiere_elegir_proveedor(candidatos: list[dict[str, Any]]) -> bool:
    """Hay 2+ proveedores con tarifa y no aplicó asignación automática."""
    return cuenta_proveedores_tarifario(candidatos) >= 2


def es_planilla_interior(envio: Envio) -> bool:
    """Pedidos del maestro interior (no AMBA/GBA ni retiro en sucursal)."""
    from app.services.postventa_rules import postventa_bloquea_cobro

    if envio.excluir_planilla or postventa_bloquea_cobro(envio.regla_postventa):
        return False
    if es_retiro_sucursal(envio.transporte_nombre, envio.transporte_cod):
        return False
    return True


def es_crossdocking_envio(envio: Envio) -> bool:
    """
    Crossdock solo si Tango trae transporte 82 (o catálogo modo crossdock).
    La provincia define la última milla, no si es cross.
    """
    if not es_planilla_interior(envio):
        return False
    circuito = resolver_circuito_logistico(
        envio.transporte_cod,
        envio.transporte_nombre,
        provincia=envio.provincia,
        localidad=envio.localidad,
        cp=envio.cp,
    )
    return circuito["modo"] == "crossdock"


def es_crossdock_operativo(
    envio: Envio,
    tarifas: list[Tarifa] | None = None,
) -> bool:
    """
    Cross real en operación y en pantalla: CD → CLICPAQ → última milla (2 tramos).
    Destino interior con un solo tramo cotizado se trata como CLICPAQ simple.
    """
    if not es_crossdocking_envio(envio):
        return False
    return len(_tramos_crossdock(envio, tarifas)) >= 2


def _proveedor_ultima_milla_interior(envio: Envio) -> str | None:
    if es_cordoba(envio.provincia):
        return "LBO"
    if es_zona_fransof(envio.provincia, envio.localidad):
        return "FRANSOF"
    if es_zona_alfaro(envio.provincia):
        return "ALFARO"
    return None


def _tramos_crossdock(
    envio: Envio,
    tarifas: list[Tarifa] | None = None,
) -> tuple[str, ...]:
    """
    Proveedores del envío crossdock.
    Si hay última milla provincial → (CLICPAQ, LBO|FRANSOF|ALFARO).
    Si solo CLICPAQ cotiza → (CLICPAQ,) un tramo.
    """
    p2 = _proveedor_ultima_milla_interior(envio)
    if not p2 and tarifas:
        cand = candidatos_tarifa(envio, tarifas)
        otros = [c["proveedor"] for c in cand if c["proveedor"] != "CLICPAQ"]
        if len(otros) == 1:
            p2 = otros[0]
    if p2 and p2 != "CLICPAQ":
        return ("CLICPAQ", p2)
    return ("CLICPAQ",)


def _asignar_proveedor_crossdock(envio: Envio, tarifas: list[Tarifa]) -> bool:
    tramos_prov = _tramos_crossdock(envio, tarifas)
    if len(tramos_prov) < 2:
        return False
    notas = {
        "CLICPAQ": "CD → sucursal (CLICPAQ)",
    }
    if len(tramos_prov) > 1:
        notas[tramos_prov[1]] = "Sucursal → cliente"

    candidatos: list[dict[str, Any]] = []
    for prov in tramos_prov:
        precio = precio_tarifa_linea(envio, tarifas, prov)
        if precio is not None and precio > 0:
            candidatos.append(
                {
                    "proveedor": prov,
                    "precio": round(precio, 2),
                    "nota": notas.get(prov, prov),
                    "modo": "crossdock",
                }
            )

    if not candidatos:
        return False

    ultima = tramos_prov[-1]
    envio.proveedor_tarifa = ultima
    envio.requiere_elegir_proveedor = False
    envio.proveedores_candidatos = json.dumps(
        {
            "modo": "crossdock",
            "tramos": candidatos,
            "total_tarifas": round(sum(c["precio"] for c in candidatos), 2),
            "nota_remito": (
                "Un solo remito del CD para todo el envío; la X es tránsito interno "
                "y el segundo transportista no genera otro remito."
            ),
        },
        ensure_ascii=False,
    )
    return True


def aplicar_tarifa_crossdock(envio: Envio, tarifas: list[Tarifa]) -> None:
    """Crossdock: CLICPAQ + última milla por renglón (seguro al persistir)."""
    if not es_crossdock_operativo(envio, tarifas):
        aplicar_tarifa_proveedor_asignado(envio, tarifas)
        return
    aplicar_cobro_linea(envio, tarifas)


def _elegir_automatico(candidatos: list[dict[str, Any]]) -> str | None:
    if cuenta_proveedores_tarifario(candidatos) == 1:
        return candidatos[0]["proveedor"]
    return None


def _circuito_envio(envio: Envio):
    return resolver_circuito_logistico(
        envio.transporte_cod,
        envio.transporte_nombre,
        provincia=envio.provincia,
        localidad=envio.localidad,
        cp=envio.cp,
    )


def _asignar_por_circuito_transporte(
    envio: Envio,
    tarifas: list[Tarifa],
    circuito,
) -> bool:
    """Asigna proveedor según circuito del transporte (prioridad sobre provincia)."""
    modo = circuito["modo"]
    todos = candidatos_tarifa(envio, tarifas)
    envio.proveedores_candidatos = (
        json.dumps(todos, ensure_ascii=False) if todos else None
    )

    if modo == "fletes_suc":
        envio.proveedor_tarifa = PROVEEDOR_FLETE_LOCAL
        envio.requiere_elegir_proveedor = False
        return True

    if modo == "red_clicpaq" and circuito["proveedor"]:
        envio.proveedor_tarifa = circuito["proveedor"]
        envio.requiere_elegir_proveedor = False
        return True

    if modo == "catalogo" and circuito["proveedor"]:
        envio.proveedor_tarifa = circuito["proveedor"]
        envio.requiere_elegir_proveedor = False
        return True

    return False


def asignar_proveedor_envio(
    envio: Envio,
    tarifas: list[Tarifa],
    *,
    forzar: str | None = None,
) -> None:
    """Calcula candidatos (tarifario) y proveedor_tarifa (costo proveedor, no cobro cliente)."""
    if es_retiro_sin_flete_domicilio(envio):
        envio.proveedor_tarifa = None
        envio.proveedores_candidatos = None
        envio.requiere_elegir_proveedor = False
        return

    if forzar:
        canon = normalizar_proveedor(forzar)
        if canon:
            envio.proveedor_tarifa = canon
            envio.requiere_elegir_proveedor = False
            cand = candidatos_tarifa(envio, tarifas)
            envio.proveedores_candidatos = json.dumps(cand, ensure_ascii=False)
            return

    circuito = _circuito_envio(envio)

    if circuito["modo"] == "excluido":
        envio.proveedor_tarifa = None
        envio.proveedores_candidatos = None
        envio.requiere_elegir_proveedor = False
        return

    if circuito["modo"] == "crossdock":
        if _asignar_proveedor_crossdock(envio, tarifas):
            return
        if _asignar_por_circuito_transporte(envio, tarifas, circuito):
            return

    if _asignar_por_circuito_transporte(envio, tarifas, circuito):
        return

    candidatos = acotar_candidatos_por_circuito(
        circuito, candidatos_tarifa(envio, tarifas)
    )
    envio.proveedores_candidatos = (
        json.dumps(candidatos, ensure_ascii=False) if candidatos else None
    )

    if circuito["proveedor"] and circuito["modo"] != "ambiguo":
        envio.proveedor_tarifa = circuito["proveedor"]
        envio.requiere_elegir_proveedor = False
        return

    elegido = _elegir_automatico(candidatos)
    if elegido:
        envio.proveedor_tarifa = elegido
        envio.requiere_elegir_proveedor = False
    else:
        envio.proveedor_tarifa = None
        envio.requiere_elegir_proveedor = requiere_elegir_proveedor(candidatos)


def aplicar_tarifa_proveedor_asignado(envio: Envio, tarifas: list[Tarifa]) -> None:
    from app.services.postventa_rules import postventa_bloquea_cobro

    if postventa_bloquea_cobro(envio.regla_postventa) or not envio.proveedor_tarifa:
        return
    if es_retiro_sin_flete_domicilio(envio):
        return
    if es_crossdock_operativo(envio, tarifas):
        aplicar_tarifa_crossdock(envio, tarifas)
        return
    medida = infer_medida(envio.descripcion)
    tipo = infer_tipo_producto(envio.descripcion, envio.cod_articulo)
    banda = medida_a_banda(medida) if medida else medida
    precio = lookup_tarifa_priorizado(
        tarifas,
        envio.proveedor_tarifa,
        envio.provincia or "",
        envio.localidad or "",
        tipo,
        banda or medida or "",
        cp=envio.cp,
    )
    if precio is None and tipo in ("BASE", "SOMIER"):
        precio = lookup_tarifa_priorizado(
            tarifas,
            envio.proveedor_tarifa,
            envio.provincia or "",
            envio.localidad or "",
            "COLCHON",
            banda or "",
            cp=envio.cp,
        )
    if precio is not None:
        aplicar_cobro_linea(envio, tarifas)


def procesar_proveedores_envios(
    envios: list[Envio],
    tarifas: list[Tarifa] | None = None,
    *,
    tarifario_ctx: Any = None,
) -> dict[str, int]:
    stats = {
        "procesados": 0,
        "asignados": 0,
        "pendientes_elegir": 0,
        "sin_tarifa": 0,
        "crossdock": 0,
    }
    for envio in envios:
        if es_retiro_sin_flete_domicilio(envio):
            envio.proveedor_tarifa = None
            envio.proveedores_candidatos = None
            envio.requiere_elegir_proveedor = False
            continue
        stats["procesados"] += 1
        t = (
            tarifario_ctx.tarifas_para_envio(envio)
            if tarifario_ctx
            else (tarifas or [])
        )
        asignar_proveedor_envio(envio, t)
        if envio.requiere_elegir_proveedor:
            stats["pendientes_elegir"] += 1
        elif envio.proveedor_tarifa:
            stats["asignados"] += 1
            if es_crossdock_operativo(envio, t):
                stats["crossdock"] += 1
        else:
            stats["sin_tarifa"] += 1
    return stats


def precio_tarifa_linea(
    envio: Envio,
    tarifas: list[Tarifa],
    proveedor: str,
    *,
    tipo_producto: str | None = None,
    medida_banda: str | None = None,
) -> float | None:
    from app.services.postventa_rules import postventa_bloquea_cobro

    canon = normalizar_proveedor(proveedor)
    if not canon or postventa_bloquea_cobro(envio.regla_postventa):
        return None
    if es_retiro_sin_flete_domicilio(envio):
        return None
    if es_amba_gba_envio(envio) and canon != PROVEEDOR_FLETE_LOCAL:
        return None
    medida = infer_medida(envio.descripcion)
    tipo = tipo_producto or infer_tipo_producto(envio.descripcion, envio.cod_articulo)
    banda = medida_banda or (medida_a_banda(medida) if medida else medida)
    cedol = envio.cedol_codigo if envio.cedol_manual and envio.cedol_codigo else None
    precio = lookup_tarifa_priorizado(
        tarifas,
        canon,
        envio.provincia or "",
        envio.localidad or "",
        tipo,
        banda or medida or "",
        cp=envio.cp,
        cedol=cedol,
    )
    if precio is None and tipo in ("BASE", "SOMIER"):
        precio = lookup_tarifa_priorizado(
            tarifas,
            canon,
            envio.provincia or "",
            envio.localidad or "",
            "COLCHON",
            banda or "",
            cp=envio.cp,
            cedol=cedol,
        )
    return precio


def costo_referencia_linea_proveedor(
    envio: Envio,
    tarifas: list[Tarifa],
    proveedor: str,
) -> float:
    from app.config import settings
    from app.services.rules_service import costo_referencia_linea

    precio = precio_tarifa_linea(envio, tarifas, proveedor)
    if precio is None or precio <= 0:
        return costo_referencia_linea(envio) or 0.0
    total = precio
    if total > 0:
        total += settings.seguro_fijo
    return round(total, 2)


def etiqueta_proveedor_maestro(envio: Envio) -> str:
    raw = envio.proveedores_candidatos
    if raw and es_crossdocking_envio(envio):
        try:
            data = json.loads(raw)
            if isinstance(data, dict) and data.get("modo") == "crossdock":
                tramos = data.get("tramos") or []
                nombres = [t.get("proveedor") for t in tramos if t.get("proveedor")]
                if len(nombres) >= 2:
                    return "Crossdock: " + " + ".join(nombres)
        except json.JSONDecodeError:
            pass
    if envio.proveedor_tarifa:
        return envio.proveedor_tarifa
    circuito = _circuito_envio(envio)
    if envio.requiere_elegir_proveedor:
        if circuito["proveedor"] and circuito["modo"] != "ambiguo":
            return circuito["proveedor"]
        return "?"
    return circuito["proveedor"] or ""


def elegir_proveedor_remito(
    db: Any,
    remito_norm: str,
    proveedor: str,
    tarifas: list[Tarifa] | None = None,
    *,
    tarifario_ctx: Any = None,
) -> int:
    from sqlalchemy import select

    canon = normalizar_proveedor(proveedor)
    if not canon:
        return 0
    lineas = list(
        db.scalars(select(Envio).where(Envio.remito_norm == remito_norm)).all()
    )
    if not lineas:
        return 0
    t_grupo = (
        tarifario_ctx.tarifas_para_grupo(lineas)
        if tarifario_ctx
        else (tarifas or [])
    )
    n = 0
    for envio in lineas:
        t = (
            tarifario_ctx.tarifas_para_envio(envio)
            if tarifario_ctx
            else t_grupo
        )
        asignar_proveedor_envio(envio, t, forzar=canon)
        n += 1
    from app.services.cobro_logistica_service import aplicar_cobro_pedido

    aplicar_cobro_pedido(lineas, t_grupo)
    return n


# Compatibilidad con imports previos
def candidatos_efectivos(
    envio: Envio,
    candidatos: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return candidatos


def cuenta_proveedores_elegibles(envio: Envio, candidatos: list[dict[str, Any]]) -> int:
    return cuenta_proveedores_tarifario(candidatos)


def stats_por_proveedor(envios: list[Envio]) -> dict[str, int]:
    from app.proveedores import PROVEEDORES_MENU, caso_en_vista_proveedor

    casos: dict[str, set[str]] = {p: set() for p in PROVEEDORES_MENU}
    pendientes: set[str] = set()
    vistos: set[str] = set()
    for e in envios:
        if e.excluir_planilla or not e.remito_norm:
            continue
        key = e.remito_norm
        if key in vistos:
            continue
        vistos.add(key)
        if e.requiere_elegir_proveedor and not es_crossdock_operativo(e):
            try:
                cand = json.loads(e.proveedores_candidatos or "[]")
            except json.JSONDecodeError:
                cand = []
            if cuenta_proveedores_tarifario(cand) >= 2:
                pendientes.add(key)
        for p in PROVEEDORES_MENU:
            if caso_en_vista_proveedor(
                p,
                e.provincia,
                e.localidad,
                transporte_cod=e.transporte_cod,
                transporte_nombre=e.transporte_nombre,
                proveedor_asignado=e.proveedor_tarifa,
            ):
                casos[p].add(key)
    out = {p: len(casos[p]) for p in PROVEEDORES_MENU}
    out["PENDIENTE_ELEGIR"] = len(pendientes)
    return out
