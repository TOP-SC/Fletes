"""

Cobro logístico según tarifarios.



Dos conceptos (ver ``costo_conceptos``):



  - **Costo proveedor** (``costo_tarifario`` en BD): lo que nos cobra el

    proveedor. Se calcula siempre que haya tarifa, también en AMBA/GBA.

  - **Cobro al cliente**: puede ser $0 en CABA/GBA aunque el costo proveedor > 0.

    Eso lo refleja el maestro en la columna total, no anulando el costo tarifario.



Reglas de armado:

  - Un NRO PEDIDO = un cobro (colchón / conjunto / diván).

  - Interior: CLICPAQ / crossdock / última milla.

  - AMBA/GBA: FLETES_SUC por zona km.

  - Seguro fijo: una vez por pedido en la línea de cobro.

"""



from __future__ import annotations



from collections import defaultdict

from dataclasses import dataclass, field

from typing import TYPE_CHECKING, Any



from app.config import settings

from app.models import Envio, Tarifa

from app.services.costo_conceptos import (

    PROVEEDOR_FLETE_LOCAL,

    cobro_al_cliente_es_cero,

    debe_calcular_costo_proveedor,

    es_amba_gba_envio,

    es_retiro_sin_flete_domicilio,

)

from app.services.pedido_cobro_service import (

    InterpretacionPedido,

    agrupar_lineas_por_pedido,

    interpretar_pedido,

    tipo_flete_caba_gba,

)

from app.services.rules_service import (

    costo_referencia_linea,

    lookup_tarifa,

    recalcular_costos_linea,

)

from app.services.zona_km import ZONAS_KM



if TYPE_CHECKING:

    from sqlalchemy.orm import Session



NOTAS_TRAMO = {

    "CLICPAQ": "CD → red (CLICPAQ)",

    "LBO": "Sucursal → cliente (Córdoba)",

    "FRANSOF": "Sucursal → cliente (Santa Fe / catálogo FRANSOF)",

    "ALFARO": "Sucursal → cliente (NOA)",

    PROVEEDOR_FLETE_LOCAL: "Flete sucursal CABA/GBA",

}



ULTIMA_MILLA = frozenset({"LBO", "FRANSOF", "ALFARO"})





@dataclass

class CobroPedidoResult:

    modo: str

    logistica: float

    tramos: list["TramoCobro"] = field(default_factory=list)

    tiene_tarifa: bool = False

    interpretacion: InterpretacionPedido | None = None

    cobro_cliente_cero: bool = False





@dataclass

class TramoCobro:

    proveedor: str

    monto: float

    nota: str = ""





@dataclass

class CobroGrupoResult:

    logistica: float

    seguro: float

    total: float

    gestion: float = 0.0

    modo: str = "sin_tarifa"

    tramos: dict[str, float] = field(default_factory=dict)

    lineas_sin_tarifa: int = 0

    pedidos: list[dict] = field(default_factory=list)

    cobro_cliente_cero: bool = False





def _lookup_precio(

    envio: Envio,

    tarifas: list[Tarifa],

    proveedor: str,

    interp: InterpretacionPedido,

) -> float | None:

    from app.services.proveedor_service import precio_tarifa_linea



    return precio_tarifa_linea(

        envio,

        tarifas,

        proveedor,

        tipo_producto=interp.tipo_cobro,

        medida_banda=interp.medida_banda,

    )





def _cobro_flete_local_con_zona(

    lineas_pedido: list[Envio],

    tarifas: list[Tarifa],

    zona_km: str,

) -> CobroPedidoResult:

    interp = interpretar_pedido(lineas_pedido)

    tipo, medida = tipo_flete_caba_gba(interp)

    precio = lookup_tarifa(

        tarifas,

        PROVEEDOR_FLETE_LOCAL,

        "CABA/GBA",

        zona_km,

        tipo,

        medida,

    )

    if precio is not None and precio > 0:

        return CobroPedidoResult(

            "flete_local",

            round(precio, 2),

            tramos=[

                TramoCobro(

                    PROVEEDOR_FLETE_LOCAL,

                    round(precio, 2),

                    NOTAS_TRAMO[PROVEEDOR_FLETE_LOCAL],

                )

            ],

            tiene_tarifa=True,

            interpretacion=interp,

            cobro_cliente_cero=cobro_al_cliente_es_cero(lineas_pedido[0]),

        )

    return CobroPedidoResult(

        "sin_tarifa",

        0.0,

        interpretacion=interp,

        cobro_cliente_cero=cobro_al_cliente_es_cero(lineas_pedido[0]),

    )





def calcular_cobro_flete_local(

    lineas_pedido: list[Envio],

    tarifas: list[Tarifa],

    zona_km: str,

) -> CobroPedidoResult:

    """CABA/GBA — tarifario FLETES_SUC por zona km."""

    if not lineas_pedido:

        return CobroPedidoResult("sin_tarifa", 0.0)

    return _cobro_flete_local_con_zona(lineas_pedido, tarifas, zona_km)





def _flete_local_sin_zona_definida(

    lineas_pedido: list[Envio],

    tarifas: list[Tarifa],

) -> CobroPedidoResult:

    """Si no hay km guardados, prueba zonas hasta hallar tarifa (referencia mínima)."""

    for zona in ZONAS_KM:

        r = _cobro_flete_local_con_zona(lineas_pedido, tarifas, zona)

        if r.tiene_tarifa:

            r.modo = "flete_local_sin_zona_km"

            return r

    return _cobro_flete_local_con_zona(lineas_pedido, tarifas, ZONAS_KM[1])





def resolver_zona_km_pedido(

    lineas_pedido: list[Envio],

    db: "Session | None" = None,

) -> str | None:

    """Zona km persistida o estimada (preview) para el pedido AMBA/GBA."""

    if not lineas_pedido:

        return None

    base = lineas_pedido[0]

    rn = base.remito_norm

    if db and rn:

        from app.models import FleteDistancia



        dist = db.get(FleteDistancia, rn)

        if dist and dist.zona_km:

            return dist.zona_km

    if db:

        from app.services.fletes_km_service import preview_flete_caso



        prev = preview_flete_caso(db, base)

        if prev.get("zona_km"):

            return str(prev["zona_km"])

    return None





def calcular_cobro_pedido(

    lineas_pedido: list[Envio],

    tarifas: list[Tarifa],

    *,

    zona_km: str | None = None,

    db: "Session | None" = None,

) -> CobroPedidoResult:

    """Costo proveedor por NRO PEDIDO (no confundir con cobro al cliente)."""

    if not lineas_pedido:

        return CobroPedidoResult("sin_tarifa", 0.0)



    base = lineas_pedido[0]

    interp = interpretar_pedido(lineas_pedido)



    if not debe_calcular_costo_proveedor(base):

        return CobroPedidoResult(

            "sin_entrega_domicilio",

            0.0,

            interpretacion=interp,

            cobro_cliente_cero=cobro_al_cliente_es_cero(base),

        )



    if base.regla_postventa:

        ref = costo_referencia_linea(base) or 0.0

        log = ref - settings.seguro_fijo if ref > settings.seguro_fijo else ref

        return CobroPedidoResult(

            "postventa",

            round(log, 2),

            tiene_tarifa=log > 0,

            interpretacion=interp,

            cobro_cliente_cero=False,

        )



    if es_amba_gba_envio(base):

        zona = zona_km or resolver_zona_km_pedido(lineas_pedido, db)

        if zona:

            r = calcular_cobro_flete_local(lineas_pedido, tarifas, zona)

        else:

            r = _flete_local_sin_zona_definida(lineas_pedido, tarifas)

        r.cobro_cliente_cero = cobro_al_cliente_es_cero(base)

        return r



    envio = interp.linea_cobro



    from app.services.proveedor_service import (

        es_crossdock_operativo,

        _tramos_crossdock,

    )



    if es_crossdock_operativo(envio, tarifas):

        tramos: list[TramoCobro] = []

        total = 0.0

        for prov in _tramos_crossdock(envio, tarifas):

            p = _lookup_precio(envio, tarifas, prov, interp)

            if p is not None and p > 0:

                tramos.append(

                    TramoCobro(prov, round(p, 2), NOTAS_TRAMO.get(prov, prov))

                )

                total += p

        return CobroPedidoResult(

            "crossdock",

            round(total, 2),

            tramos=tramos,

            tiene_tarifa=total > 0,

            interpretacion=interp,

            cobro_cliente_cero=False,

        )



    prov = envio.proveedor_tarifa

    if prov:

        p = _lookup_precio(envio, tarifas, prov, interp)

        if p is not None and p > 0:

            return CobroPedidoResult(

                "simple",

                round(p, 2),

                tramos=[TramoCobro(prov, round(p, 2))],

                tiene_tarifa=True,

                interpretacion=interp,

                cobro_cliente_cero=False,

            )



    return CobroPedidoResult(

        "sin_tarifa",

        0.0,

        interpretacion=interp,

        cobro_cliente_cero=False,

    )





def aplicar_cobro_pedido(

    lineas_pedido: list[Envio],

    tarifas: list[Tarifa],

    *,

    zona_km: str | None = None,

    db: "Session | None" = None,

) -> CobroPedidoResult:

    """Persiste costo proveedor en la línea de cobro; accesorios del pedido en 0."""

    cobro = calcular_cobro_pedido(

        lineas_pedido, tarifas, zona_km=zona_km, db=db

    )

    interp = cobro.interpretacion or interpretar_pedido(lineas_pedido)

    if not interp:

        return cobro

    linea_id = interp.linea_cobro.id

    for e in lineas_pedido:

        if e.id != linea_id:

            e.costo_tarifario = 0.0

    if cobro.tiene_tarifa:

        recalcular_costos_linea(interp.linea_cobro, cobro.logistica)

    elif not cobro.tiene_tarifa:

        for e in lineas_pedido:

            if e.costo_tarifario and e.id != linea_id:

                continue

            if e.id == linea_id:

                e.costo_tarifario = None

    return cobro





def aplicar_cobro_todos_envios(

    envios: list[Envio],

    tarifas: list[Tarifa] | None = None,

    db: "Session | None" = None,

    *,
    tarifario_ctx: Any = None,

) -> dict[str, int]:

    """Reaplica costo proveedor agrupando por NRO PEDIDO (interior + AMBA/GBA)."""

    stats = {"pedidos": 0, "con_tarifa": 0, "sin_tarifa": 0, "amba": 0}

    por_pedido: dict[str, list[Envio]] = defaultdict(list)

    for e in envios:

        if not debe_calcular_costo_proveedor(e) or e.regla_postventa:

            continue

        key = (e.nro_pedido or "").strip() or f"__linea_{e.id}"

        por_pedido[key].append(e)



    for lineas in por_pedido.values():

        stats["pedidos"] += 1

        base = lineas[0]

        zona = None

        if es_amba_gba_envio(base):

            stats["amba"] += 1

            zona = resolver_zona_km_pedido(lineas, db)

        t = (
            tarifario_ctx.tarifas_para_envio(base)
            if tarifario_ctx
            else (tarifas or [])
        )
        r = aplicar_cobro_pedido(lineas, t, zona_km=zona, db=db)

        if r.tiene_tarifa:

            stats["con_tarifa"] += 1

        else:

            stats["sin_tarifa"] += 1

    return stats





# Compatibilidad con nombre anterior

def aplicar_cobro_envios_interior(

    envios: list[Envio],

    tarifas: list[Tarifa],

    db: "Session | None" = None,

) -> dict[str, int]:

    return aplicar_cobro_todos_envios(envios, tarifas, db=db)





def calcular_cobro_grupo(

    lineas: list[Envio],

    tarifas: list[Tarifa] | None,

    *,

    proveedor_vista: str | None = None,

    db: "Session | None" = None,

) -> CobroGrupoResult:

    """Totales de caso/remito: costo proveedor; total al cliente puede ser 0 en AMBA."""

    if not lineas:

        return CobroGrupoResult(0.0, 0.0, 0.0)



    base = lineas[0]

    cliente_cero = any(cobro_al_cliente_es_cero(l) for l in lineas)



    vista = proveedor_vista

    if vista and tarifas:

        from app.services.proveedor_service import costo_referencia_linea_proveedor



        logistica = 0.0

        for pedido_lineas in agrupar_lineas_por_pedido(lineas).values():

            interp = interpretar_pedido(pedido_lineas)

            ref = costo_referencia_linea_proveedor(

                interp.linea_cobro, tarifas, vista

            )

            if ref and ref > settings.seguro_fijo:

                logistica += ref - settings.seguro_fijo

            elif ref:

                logistica += ref

        seguro = settings.seguro_fijo if logistica > 0 else 0.0

        gestion = 0.0

        if any(l.regla_postventa == "gestion_retiro_25" for l in lineas):

            gestion = round(logistica * settings.gestion_retiro_pct, 2)

        total_prov = round(logistica + seguro + gestion, 2)

        total_cli = 0.0 if cliente_cero else total_prov

        return CobroGrupoResult(

            round(logistica, 2),

            seguro,

            total_cli,

            gestion=gestion,

            modo="vista_proveedor",

            tramos={vista: round(logistica, 2)},

            cobro_cliente_cero=cliente_cero,

        )



    if not tarifas:

        logistica = 0.0

        for pedido_lineas in agrupar_lineas_por_pedido(lineas).values():

            interp = interpretar_pedido(pedido_lineas)

            ref = costo_referencia_linea(interp.linea_cobro) or 0.0

            if ref > settings.seguro_fijo:

                logistica += ref - settings.seguro_fijo

            elif ref:

                logistica += ref

        seguro = settings.seguro_fijo if logistica > 0 else 0.0

        total_prov = round(logistica + seguro, 2)

        total_cli = 0.0 if cliente_cero else total_prov

        return CobroGrupoResult(

            round(logistica, 2),

            seguro,

            total_cli,

            modo="persistido",

            cobro_cliente_cero=cliente_cero,

        )



    logistica = 0.0

    tramos_agg: dict[str, float] = {}

    sin_tarifa = 0

    modo = "sin_tarifa"

    pedidos_info: list[dict] = []



    for pedido_lineas in agrupar_lineas_por_pedido(lineas).values():

        cobro = calcular_cobro_pedido(pedido_lineas, tarifas, db=db)

        interp = cobro.interpretacion

        info: dict[str, Any] = {

            "nro_pedido": interp.nro_pedido if interp else "",

            "resumen": interp.resumen() if interp else "",

            "logistica": cobro.logistica,

            "modo": cobro.modo,

            "renglones": len(pedido_lineas),

            "advertencias": interp.advertencias if interp else [],

            "cobro_cliente_cero": cobro.cobro_cliente_cero,

        }

        pedidos_info.append(info)

        if not cobro.tiene_tarifa:

            sin_tarifa += 1

            continue

        if cobro.modo == "crossdock":

            modo = "crossdock"

        elif modo != "crossdock" and cobro.modo in ("simple", "flete_local", "flete_local_sin_zona_km"):

            modo = cobro.modo

        elif modo == "sin_tarifa":

            modo = cobro.modo

        logistica += cobro.logistica

        for t in cobro.tramos:

            tramos_agg[t.proveedor] = tramos_agg.get(t.proveedor, 0.0) + t.monto



    seguro = settings.seguro_fijo if logistica > 0 else 0.0

    gestion = 0.0

    if any(l.regla_postventa == "gestion_retiro_25" for l in lineas):

        gestion = round(logistica * settings.gestion_retiro_pct, 2)



    total_prov = round(logistica + seguro + gestion, 2)

    total_cli = 0.0 if cliente_cero else total_prov



    return CobroGrupoResult(

        round(logistica, 2),

        seguro,

        total_cli,

        gestion=gestion,

        modo=modo if logistica > 0 else "sin_tarifa",

        tramos={k: round(v, 2) for k, v in tramos_agg.items()},

        lineas_sin_tarifa=sin_tarifa,

        pedidos=pedidos_info,

        cobro_cliente_cero=cliente_cero,

    )





def calcular_cobro_linea(envio: Envio, tarifas: list[Tarifa]) -> CobroPedidoResult:

    return calcular_cobro_pedido([envio], tarifas)





def aplicar_cobro_linea(envio: Envio, tarifas: list[Tarifa]) -> CobroPedidoResult:

    return aplicar_cobro_pedido([envio], tarifas)





def cobro_red_y_provincia(tramos: dict[str, float]) -> tuple[float | None, float | None]:

    red = tramos.get("CLICPAQ")

    provincia = sum(tramos.get(p, 0.0) for p in ULTIMA_MILLA)

    return (

        round(red, 2) if red else None,

        round(provincia, 2) if provincia else None,

    )

