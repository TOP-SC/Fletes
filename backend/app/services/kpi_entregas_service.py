"""
KPI «entregas x mes» — réplica del Excel manual de Adrián (Grateful FC).

Propósito operativo
-------------------
Adrián controlaba mensualmente cuánto salía por la red LOG (Clicpaq / La Costa) y a qué
costo tarifario, separando por **centro de despacho físico** y por **quincena de entrega**.
Este informe automatiza ese Excel para que Logística y Dirección puedan:

  - Comparar el mismo mes del año anterior vs el año en curso (misma ventana de quincena).
  - Ver volumen (entregas) e importe (LOGISTICA tarifario) por mes de **pedido**.
  - Separar **Hurlingham (dep. 12)** — CD Clicpaq donde también despacha Limansky —
    de **Tortuguitas (dep. 14)** — centro de distribución principal.
  - Usar el mismo universo que el LOG diario WAMARO (canales 51/83) cuando circuito=adrian.

Reglas de corte (igual que la planilla manual)
----------------------------------------------
  - 4 bloques: 1°/2° quincena × Hurlingham / Tortuguitas.
  - Corte por **fecha de entrega** dentro de la quincena del mes de control.
  - Filas = mes calendario de **fecha de pedido**.
  - Importe oficial = facturas proveedor LOG (integración pendiente; ver config).
"""

from __future__ import annotations

from typing import Any, Literal

from sqlalchemy.orm import Session

from app.config import (
    DEPOSITO_CD_HURLINGHAM,
    DEPOSITO_CD_TORTUGUITAS,
    DEPOSITO_ORIGEN,
    KPI_ENTREGAS_FUENTE_FACTURAS_ACTIVA,
)
from app.models import Envio
from app.services.fecha_utils import periodo_mes_solo, rango_quincena
from app.services.envio_query_service import cargar_envios_filtrados
from app.services.maestro_service import (
    _agrupar_por_caso,
    _fila_maestro_desde_grupo,
    _origen_planilla,
)
from app.services.modo_adrian_service import es_circuito_log_wamaro_adrian

CircuitoKpi = Literal["adrian", "interior", "todos"]

MESES_CALENDARIO = [
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]

_ORIGEN_BLOQUE: dict[str, dict[str, str]] = {
    "sa": {
        "etiqueta": "Hurlingham",
        "deposito": DEPOSITO_CD_HURLINGHAM,
        "descripcion": DEPOSITO_ORIGEN[DEPOSITO_CD_HURLINGHAM],
    },
    "tortuguitas": {
        "etiqueta": "Tortuguitas",
        "deposito": DEPOSITO_CD_TORTUGUITAS,
        "descripcion": DEPOSITO_ORIGEN[DEPOSITO_CD_TORTUGUITAS],
    },
}

_BLOQUES_META: list[tuple[int, str, str]] = [
    (1, "sa", "hurl"),
    (1, "tortuguitas", "tortu"),
    (2, "sa", "hurl"),
    (2, "tortuguitas", "tortu"),
]

KPI_ENTREGAS_PROPOSITO: dict[str, Any] = {
    "titulo": "Entregas por mes — control LOG",
    "resumen": (
        "Réplica del Excel que Adrián armaba para Grateful FC: volumen y costo por quincena "
        "y por centro de despacho (Hurlingham vs Tortuguitas)."
    ),
    "fuente_importe": {
        "requerida": "facturas_proveedor_log",
        "descripcion": (
            "El Excel manual tomaba los importes de las facturas del proveedor (Clicpaq / red LOG), "
            "no las prefacturas diarias ni el tarifario calculado en Maestro."
        ),
        "integrada": KPI_ENTREGAS_FUENTE_FACTURAS_ACTIVA,
        "pendiente": "Definir origen de facturas (archivo, API o proceso contable) e importador.",
    },
    "para_que_sirve": [
        "Comparar año actual vs año anterior en la misma quincena de entrega.",
        "Separar volumen del CD Hurlingham (dep. 12: Clicpaq + Limansky) y Tortuguitas (dep. 14).",
        "Ver en qué mes de pedido se concentran las entregas de la red LOG.",
        "Reemplazar el armado manual del Excel cuando exista el dato de facturas.",
    ],
    "reglas": [
        "Corte por fecha de entrega dentro de la quincena del mes elegido.",
        "Filas de la tabla = mes calendario de fecha de pedido.",
        "Importe oficial = facturas proveedor (pendiente integración).",
        "Circuito «LOG WAMARO» = canales 51 y 83, igual que la planilla diaria de Adrián.",
    ],
    "depositos": [
        {
            "codigo": DEPOSITO_CD_HURLINGHAM,
            "bloque": "Hurlingham",
            "descripcion": DEPOSITO_ORIGEN[DEPOSITO_CD_HURLINGHAM],
        },
        {
            "codigo": DEPOSITO_CD_TORTUGUITAS,
            "bloque": "Tortuguitas",
            "descripcion": DEPOSITO_ORIGEN[DEPOSITO_CD_TORTUGUITAS],
        },
    ],
}


def _mes_nombre(mes: int) -> str:
    return MESES_CALENDARIO[mes - 1]


def _titulo_bloque(quincena: int, mes: int, anio: int, origen: str) -> str:
    etiqueta = _ORIGEN_BLOQUE[origen]["etiqueta"]
    return f"{quincena}° {_mes_nombre(mes)} {anio} {etiqueta}"


def _fecha_entrega(envio: Envio):
    if envio.fecha_entrega_d:
        return envio.fecha_entrega_d
    from app.services.fecha_utils import parse_fecha_tango

    return parse_fecha_tango(envio.fecha_entrega)


def _fecha_pedido(envio: Envio):
    if envio.fecha_pedido_d:
        return envio.fecha_pedido_d
    from app.services.fecha_utils import parse_fecha_tango

    return parse_fecha_tango(envio.fecha_pedido)


def _importe_caso(fila: dict[str, Any]) -> float:
    for key in ("LOGISTICA", "total", "_total_proveedor", "costo"):
        val = fila.get(key)
        if val is not None and float(val) > 0:
            return float(val)
    return 0.0


def _pasa_circuito(envio: Envio, circuito: CircuitoKpi) -> bool:
    if circuito == "adrian":
        return es_circuito_log_wamaro_adrian(envio)
    if circuito == "interior":
        return not bool(envio.excluir_planilla)
    return True


def _acumular_bloque(
    envios: list[Envio],
    *,
    quincena: int,
    mes_control: int,
    anio_col: int,
    origen: str,
    circuito: CircuitoKpi,
    tarifario_ctx: Any = None,
    db: Session | None = None,
) -> dict[str, Any]:
    d0, d1 = rango_quincena(anio_col, mes_control, quincena)
    por_mes_pedido: dict[str, dict[str, float]] = {
        m: {"entregas": 0, "importe": 0.0} for m in MESES_CALENDARIO
    }
    total_ent = 0
    total_imp = 0.0
    sin_tarifa = 0

    for key, lineas in _agrupar_por_caso(envios).items():
        base = lineas[0]
        if _origen_planilla(base.deposito, base.origen_cd) != origen:
            continue
        if not _pasa_circuito(base, circuito):
            continue
        fe = _fecha_entrega(base)
        if not fe or fe < d0 or fe > d1:
            continue
        fp = _fecha_pedido(base)
        fila = _fila_maestro_desde_grupo(
            key,
            lineas,
            tarifario_ctx=tarifario_ctx,
            db=db,
        )
        imp = _importe_caso(fila)
        total_ent += 1
        total_imp += imp
        if imp <= 0:
            sin_tarifa += 1
        if fp and 1 <= fp.month <= 12:
            bucket = por_mes_pedido[MESES_CALENDARIO[fp.month - 1]]
            bucket["entregas"] += 1
            bucket["importe"] += imp

    promedio = round(total_imp / total_ent, 4) if total_ent else 0.0
    filas = [
        {
            "mes": mes,
            "entregas": int(por_mes_pedido[mes]["entregas"]),
            "importe": round(por_mes_pedido[mes]["importe"], 2),
        }
        for mes in MESES_CALENDARIO
    ]
    return {
        "entregas": total_ent,
        "importe": round(total_imp, 2),
        "promedio": promedio,
        "sin_tarifa": sin_tarifa,
        "filas": filas,
        "ventana": {"desde": d0.isoformat(), "hasta": d1.isoformat()},
    }


def _aplicar_fuente_importe(
    bloques: list[dict[str, Any]],
    gran_imp: float,
    gran_ent: int,
    total_sin_tarifa: int,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    """Oculta importes oficiales hasta tener facturas; conserva referencia tarifaria aparte."""
    usar_facturas = KPI_ENTREGAS_FUENTE_FACTURAS_ACTIVA
    notas = [
        "Corte por fecha de entrega en la quincena; filas por mes de fecha de pedido.",
        f"Hurlingham = depósito {DEPOSITO_CD_HURLINGHAM} (CD Clicpaq; Limansky también despacha desde ahí). "
        f"Tortuguitas = depósito {DEPOSITO_CD_TORTUGUITAS}.",
    ]

    gran_total: dict[str, Any] = {
        "entregas": gran_ent,
        "importe": round(gran_imp, 2) if usar_facturas else None,
        "promedio": round(gran_imp / gran_ent, 4) if usar_facturas and gran_ent else None,
        "sin_tarifa": total_sin_tarifa if usar_facturas else None,
        "importe_referencia_tarifario": round(gran_imp, 2),
    }

    if not usar_facturas:
        notas.append(
            "Importes ocultos: el cierre mensual requiere facturas del proveedor (integración pendiente). "
            "El tarifario Maestro no reemplaza ese dato."
        )
        for bloque in bloques:
            for fila in bloque.get("filas") or []:
                fila["prev_importe_ref"] = fila.pop("prev_importe", 0)
                fila["ctrl_importe_ref"] = fila.pop("ctrl_importe", 0)
                fila["prev_importe"] = None
                fila["ctrl_importe"] = None
            tp = bloque.get("total_prev") or {}
            tc = bloque.get("total_ctrl") or {}
            tp["importe_ref"] = tp.get("importe")
            tc["importe_ref"] = tc.get("importe")
            tp["importe"] = None
            tc["importe"] = None
            tc["promedio"] = None
    elif total_sin_tarifa > 0:
        notas.append(
            f"{total_sin_tarifa} entrega(s) sin importe en facturas/tarifa "
            "(revisar datos del proveedor)."
        )

    return bloques, gran_total, notas


def _remitos_emitidos_mes(
    envios: list[Envio],
    *,
    anio: int,
    mes: int,
    circuito: CircuitoKpi,
) -> int:
    d0, d1 = periodo_mes_solo(anio, mes)
    n = 0
    for _, lineas in _agrupar_por_caso(envios).items():
        base = lineas[0]
        if not _pasa_circuito(base, circuito):
            continue
        fe = _fecha_entrega(base)
        if fe and d0 <= fe <= d1:
            n += 1
    return n


def kpi_entregas_mes(
    db: Session,
    *,
    anio: int,
    mes: int,
    circuito: CircuitoKpi = "adrian",
) -> dict[str, Any]:
    """Informe completo para un mes de control."""
    from app.services.tarifario_version_service import TarifarioContext

    envios = cargar_envios_filtrados(db)
    tarifario_ctx = TarifarioContext(db)
    anio_prev = anio - 1
    bloques: list[dict[str, Any]] = []
    total_sin_tarifa = 0

    for quincena, origen, codigo in _BLOQUES_META:
        meta_origen = _ORIGEN_BLOQUE[origen]
        prev = _acumular_bloque(
            envios,
            quincena=quincena,
            mes_control=mes,
            anio_col=anio_prev,
            origen=origen,
            circuito=circuito,
            tarifario_ctx=tarifario_ctx,
            db=db,
        )
        ctrl = _acumular_bloque(
            envios,
            quincena=quincena,
            mes_control=mes,
            anio_col=anio,
            origen=origen,
            circuito=circuito,
            tarifario_ctx=tarifario_ctx,
            db=db,
        )
        total_sin_tarifa += int(ctrl.get("sin_tarifa") or 0)
        filas_tabla: list[dict[str, Any]] = []
        for i, mes_nom in enumerate(MESES_CALENDARIO):
            filas_tabla.append(
                {
                    "mes": mes_nom,
                    "prev_entregas": prev["filas"][i]["entregas"],
                    "prev_importe": prev["filas"][i]["importe"],
                    "ctrl_entregas": ctrl["filas"][i]["entregas"],
                    "ctrl_importe": ctrl["filas"][i]["importe"],
                }
            )
        bloques.append(
            {
                "id": f"q{quincena}_{codigo}",
                "quincena": quincena,
                "origen": origen,
                "deposito": meta_origen["deposito"],
                "origen_descripcion": meta_origen["descripcion"],
                "titulo": _titulo_bloque(quincena, mes, anio, origen),
                "anio_prev": anio_prev,
                "anio_ctrl": anio,
                "filas": filas_tabla,
                "total_prev": {
                    "entregas": prev["entregas"],
                    "importe": prev["importe"],
                    "promedio": prev["promedio"],
                },
                "total_ctrl": {
                    "entregas": ctrl["entregas"],
                    "importe": ctrl["importe"],
                    "promedio": ctrl["promedio"],
                    "sin_tarifa": ctrl["sin_tarifa"],
                },
            }
        )

    gran_ent = sum(b["total_ctrl"]["entregas"] for b in bloques)
    gran_imp = sum(b["total_ctrl"]["importe"] for b in bloques)

    bloques, gran_total, notas = _aplicar_fuente_importe(
        bloques, gran_imp, gran_ent, total_sin_tarifa
    )

    fuente = KPI_ENTREGAS_PROPOSITO.get("fuente_importe") or {}
    estado = {
        "listo_para_cierre": KPI_ENTREGAS_FUENTE_FACTURAS_ACTIVA,
        "fuente_importe_requerida": fuente.get("requerida"),
        "fuente_importe_actual": "facturas" if KPI_ENTREGAS_FUENTE_FACTURAS_ACTIVA else "pendiente",
        "pendiente": fuente.get("pendiente"),
        "mensaje": (
            "Importes desde facturas del proveedor LOG."
            if KPI_ENTREGAS_FUENTE_FACTURAS_ACTIVA
            else (
                "Solo volumen (entregas) activo. El Excel de Adrián usaba facturas del proveedor, "
                "no prefacturas ni tarifario Maestro. Falta integrar esa fuente."
            )
        ),
    }

    return {
        "proposito": KPI_ENTREGAS_PROPOSITO,
        "estado": estado,
        "periodo": {"anio": anio, "mes": mes, "mes_nombre": _mes_nombre(mes)},
        "circuito": circuito,
        "bloques": bloques,
        "remitos_emitidos_mes": _remitos_emitidos_mes(
            envios, anio=anio, mes=mes, circuito=circuito
        ),
        "gran_total": gran_total,
        "notas": notas,
    }
