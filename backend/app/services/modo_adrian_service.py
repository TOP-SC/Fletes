"""
Modo Adrián — réplica operativa de las planillas manuales (carpeta 4 ABR 2026).

Adrián consultaba Tango y armaba un Excel por día con columnas fijas (29 cols).
Nosotros aplicamos **las mismas reglas de selección** sobre el Tango ya importado.

Reglas LOG WAMARO (inferidas de sus archivos vs nuestra base):
  - Remito oficial obligatorio.
  - Canal **51** (Expreso CLICPAQ) o **83** (La Costa) — como filtra en Tango.
  - **No** crossdock 82 ni flete local AMBA 40–50 (van por otros circuitos).
  - Sin retiro en sucursal / sin flete a domicilio.
  - Excluye pedidos **ANULADO / CERRADO / CANCELADO**.
  - **No** filtra por flag ``excluir_planilla`` (Adrián incluye MDP, costa, etc.).
  - Tortuguitas vs SA según depósito / CD (igual que export maestro).
  - Corte diario por **fecha de entrega** (columna FECHA ENTREGA DI en Tango).
  - Columna **TRANSPORTE** en estilo Adrián: CLICPAQ / LA COSTA (no «EXPRESO CLICPAQ»).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from io import BytesIO
from typing import Any

from app.models import Envio
from app.services.costo_conceptos import es_retiro_sin_flete_domicilio
from app.services.fecha_utils import parse_fecha_tango
from app.services.maestro_service import (
    MAESTRO_COLUMNAS,
    _agrupar_por_caso,
    _fila_maestro_desde_grupo,
    _origen_planilla,
)
from app.services.remito_maestro import clave_agrupacion_caso, estado_remito_envio
from app.transporte_reglas import (
    COD_EXPRESO_CLICPAQ,
    excluir_planilla_transporte,
    normalizar_transporte_cod,
)

# Canales que Adrián incluye en LOG WAMARO diario (consulta Tango)
_COD_LOG_ADRIAN = frozenset({COD_EXPRESO_CLICPAQ, "83"})

_ESTADOS_EXCLUIDOS = frozenset({"ANULADO", "CERRADO", "CANCELADO"})

# Referencia carpeta 4 ABR 2026
_REF_ABR_2026 = {
    "log_tortuguitas_remitos": 1084,
    "log_sa_remitos": 77,
    "archivos_log_tortu": 20,
    "nota": "Conteos dedup carpeta 4 ABR 2026.",
}


def _parse_fecha_tango_datetime(valor: str | None) -> datetime | None:
    """FECHA columna estilo Adrián (fecha + hora si viene en Tango)."""
    if not valor:
        return None
    s = str(valor).strip()
    if not s or s.startswith("1/1/1900"):
        return None
    for fmt in (
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(s.split(".")[0].strip(), fmt)
        except ValueError:
            continue
    d = parse_fecha_tango(s)
    if d:
        return datetime.combine(d, datetime.min.time())
    return None


def _transporte_log_adrian(lineas: list[Envio], cobro: Any | None = None) -> str:
    """
    Nombre operativo en columna TRANSPORTE (como cargaba Adrián).
    En Tango el canal 51 figura «EXPRESO CLICPAQ»; en su planilla escribe CLICPAQ,
    ORO NEGRO, etc. Con tarifario usamos el tramo dominante; sin tarifa, default CLICPAQ.
    """
    base = lineas[0]
    cod = normalizar_transporte_cod(base.transporte_cod, base.transporte_nombre) or ""
    if cod == "83":
        return "LA COSTA"
    if cod == COD_EXPRESO_CLICPAQ:
        if cobro and getattr(cobro, "tramos", None):
            tramos = cobro.tramos
            if isinstance(tramos, dict):
                # Última milla con monto > red CLICPAQ
                um = [
                    p
                    for p in tramos
                    if p not in ("CLICPAQ",) and (tramos.get(p) or 0) > 0
                ]
                if um:
                    return um[0]
            elif isinstance(tramos, list):
                for t in reversed(tramos):
                    prov = getattr(t, "proveedor", None) or (
                        t.get("proveedor") if isinstance(t, dict) else None
                    )
                    if prov and prov != "CLICPAQ":
                        return str(prov)
        return "CLICPAQ"
    return (base.transporte_nombre or "").upper() or "CLICPAQ"


def es_circuito_log_wamaro_adrian(envio: Envio) -> bool:
    """¿Entra al LOG WAMARO diario de Adrián? (mismo corte Tango canal 51/83)."""
    if not clave_agrupacion_caso(envio):
        return False
    if estado_remito_envio(envio) != "con_remito":
        return False
    if es_retiro_sin_flete_domicilio(envio):
        return False
    if excluir_planilla_transporte(envio.transporte_cod, envio.transporte_nombre):
        return False

    cod = normalizar_transporte_cod(envio.transporte_cod, envio.transporte_nombre) or ""
    if cod not in _COD_LOG_ADRIAN:
        return False

    estado = (envio.estado_pedido or "").upper().strip()
    if estado in _ESTADOS_EXCLUIDOS:
        return False

    return True


def _fecha_entrega_envio(envio: Envio) -> date | None:
    if envio.fecha_entrega_d:
        return envio.fecha_entrega_d
    return parse_fecha_tango(envio.fecha_entrega)


def _fecha_columna_adrian(lineas: list[Envio]) -> datetime | date | None:
    """Columna FECHA del Excel Adrián — tomamos fecha entrega Tango (con hora si hay)."""
    base = lineas[0]
    dt = _parse_fecha_tango_datetime(base.fecha_entrega)
    if dt:
        return dt
    d = _fecha_entrega_envio(base)
    if d:
        return datetime.combine(d, datetime.min.time())
    return _parse_fecha_tango_datetime(base.fecha_pedido)


def filtrar_envios_modo_adrian(
    envios: list[Envio],
    *,
    planilla: str | None = None,
) -> list[Envio]:
    base = [e for e in envios if es_circuito_log_wamaro_adrian(e)]
    if not planilla or planilla == "todos":
        return base
    key = "sa" if planilla in ("sa", "limansky") else "tortuguitas"
    return [
        e
        for e in base
        if _origen_planilla(e.deposito, e.origen_cd) == key
    ]


def _grupos_modo_adrian(
    envios: list[Envio],
    *,
    planilla: str | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    dia: date | None = None,
) -> list[tuple[str, list[Envio]]]:
    filtrados = filtrar_envios_modo_adrian(envios, planilla=planilla)
    grupos_raw = _agrupar_por_caso(filtrados)
    out: list[tuple[str, list[Envio]]] = []

    for key, grupo in grupos_raw.items():
        base = grupo[0]
        fe = _fecha_entrega_envio(base)
        if fe is None:
            continue
        if dia is not None and fe != dia:
            continue
        if fecha_desde and fe < fecha_desde:
            continue
        if fecha_hasta and fe > fecha_hasta:
            continue
        out.append((key, grupo))

    out.sort(key=lambda x: str(_fecha_entrega_envio(x[1][0]) or ""), reverse=True)
    return out


def _ajustar_alertas_log_adrian(fila: dict[str, Any]) -> dict[str, Any]:
    """
    Adrián carga LOGISTICA desde tarifario antes de la prefactura CLP.
    Si ya hay tarifa, no marcar rojo solo por PRECIO NETO vacío.
    """
    log = float(fila.get("LOGISTICA") or 0)
    if log <= 0:
        return fila
    alertas = list(fila.get("_alertas_celdas") or [])
    restantes = [a for a in alertas if a.get("codigo") != "prefactura"]
    if len(restantes) == len(alertas):
        return fila
    fila["_alertas_celdas"] = restantes
    if restantes:
        fila["_regla_color"] = "alerta"
        fila["_alerta_motivo"] = restantes[0].get("motivo")
    else:
        fila["_regla_color"] = None
        fila["_alerta_motivo"] = None
    return fila


def _fila_log_adrian_desde_grupo(
    key: str,
    lineas: list[Envio],
    *,
    tarifario_ctx: Any = None,
    db: Any = None,
) -> dict[str, Any]:
    from app.services.cobro_logistica_service import calcular_cobro_grupo

    tarifas = (
        tarifario_ctx.tarifas_para_grupo(lineas) if tarifario_ctx else None
    )
    cobro = calcular_cobro_grupo(lineas, tarifas, db=db)
    fila = _fila_maestro_desde_grupo(
        key, lineas, tarifario_ctx=tarifario_ctx, db=db
    )
    fila["FECHA"] = _fecha_columna_adrian(lineas)
    fila["SERVICIO"] = "LOGISTICA ORIGEN ST"
    fila["TRANSPORTE"] = _transporte_log_adrian(lineas, cobro)
    return _ajustar_alertas_log_adrian(fila)


def _stats_prefactura_grupos(
    grupos: list[tuple[str, list[Envio]]],
) -> dict[str, int]:
    con = sin = dif = 0
    for _, g in grupos:
        base = g[0]
        if base.prefactura_proveedor is not None:
            con += 1
            d = base.diferencia if base.diferencia is not None else 0.0
            if abs(d) > 0.01:
                dif += 1
        elif base.alerta_clickpack:
            sin += 1
    return {
        "con_prefactura_clp": con,
        "sin_prefactura_clp": sin,
        "con_diferencia_prefactura": dif,
    }


def resumen_modo_adrian(
    envios: list[Envio],
    *,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
) -> dict[str, Any]:
    tortu = _grupos_modo_adrian(
        envios, planilla="tortuguitas", fecha_desde=fecha_desde, fecha_hasta=fecha_hasta
    )
    sa = _grupos_modo_adrian(
        envios, planilla="sa", fecha_desde=fecha_desde, fecha_hasta=fecha_hasta
    )
    todos = _grupos_modo_adrian(
        envios, planilla="todos", fecha_desde=fecha_desde, fecha_hasta=fecha_hasta
    )

    dias_t: dict[str, int] = defaultdict(int)
    for _, g in tortu:
        fe = _fecha_entrega_envio(g[0])
        if fe:
            dias_t[fe.isoformat()] += 1

    dias_sa: dict[str, int] = defaultdict(int)
    for _, g in sa:
        fe = _fecha_entrega_envio(g[0])
        if fe:
            dias_sa[fe.isoformat()] += 1

    return {
        "casos_tortuguitas": len(tortu),
        "casos_sa": len(sa),
        "casos_total": len(todos),
        "dias_con_entregas_tortuguitas": len(dias_t),
        "dias_con_entregas_sa": len(dias_sa),
        "por_dia_tortuguitas": dict(sorted(dias_t.items())),
        "por_dia_sa": dict(sorted(dias_sa.items())),
        "prefactura_clp": _stats_prefactura_grupos(todos),
        "reglas": {
            "canales": sorted(_COD_LOG_ADRIAN),
            "corte": "fecha_entrega",
            "planillas": ["WAMARO TORTUGUITAS", "WAMARO SA"],
            "columnas": len(MAESTRO_COLUMNAS),
        },
        "referencia_adrian_abr_2026": _REF_ABR_2026,
    }


def listar_dias_modo_adrian(
    envios: list[Envio],
    *,
    planilla: str = "tortuguitas",
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
) -> list[dict[str, Any]]:
    grupos = _grupos_modo_adrian(
        envios,
        planilla=planilla,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
    )
    por_dia: dict[str, int] = defaultdict(int)
    for _, g in grupos:
        fe = _fecha_entrega_envio(g[0])
        if fe:
            por_dia[fe.isoformat()] += 1
    return [
        {"fecha": k, "casos": v, "planilla": planilla}
        for k, v in sorted(por_dia.items(), reverse=True)
    ]


def construir_log_adrian_pagina(
    envios: list[Envio],
    *,
    planilla: str = "tortuguitas",
    dia: date | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    db: Any = None,
    tarifario_ctx: Any = None,
    page: int | None = None,
    page_size: int | None = None,
) -> tuple[list[dict[str, Any]], int]:
    if dia is not None:
        keys_grupos = _grupos_modo_adrian(envios, planilla=planilla, dia=dia)
    else:
        keys_grupos = _grupos_modo_adrian(
            envios,
            planilla=planilla,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
        )
    total = len(keys_grupos)

    if page is not None and page_size is not None:
        start = max(0, (page - 1) * page_size)
        keys_grupos = keys_grupos[start : start + page_size]

    filas = [
        _fila_log_adrian_desde_grupo(
            key, grupo, tarifario_ctx=tarifario_ctx, db=db
        )
        for key, grupo in keys_grupos
    ]
    return filas, total


def construir_log_dia_adrian(
    envios: list[Envio],
    *,
    dia: date,
    planilla: str = "tortuguitas",
    db: Any = None,
    tarifario_ctx: Any = None,
    page: int | None = None,
    page_size: int | None = None,
) -> tuple[list[dict[str, Any]], int]:
    return construir_log_adrian_pagina(
        envios,
        planilla=planilla,
        dia=dia,
        db=db,
        tarifario_ctx=tarifario_ctx,
        page=page,
        page_size=page_size,
    )


def export_log_dia_adrian_xlsx(
    envios: list[Envio],
    *,
    dia: date,
    planilla: str = "tortuguitas",
    db: Any = None,
    tarifario_ctx: Any = None,
) -> bytes:
    from app.services.export_service import _sheet_from_filas, _write_sheet

    filas, _ = construir_log_dia_adrian(
        envios,
        dia=dia,
        planilla=planilla,
        db=db,
        tarifario_ctx=tarifario_ctx,
    )
    label = "Wamaro Sa" if planilla == "sa" else "Wamaro Tortuguitas"
    buf = BytesIO()
    import pandas as pd

    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        _write_sheet(writer, _sheet_from_filas(filas), label)
    buf.seek(0)
    return buf.getvalue()


def nombre_archivo_log_adrian(dia: date, planilla: str = "tortuguitas") -> str:
    pref = "WAMARO SA" if planilla == "sa" else "WAMARO TORTUGUITAS"
    return f"{pref} - {dia.day:02d}_{dia.month:02d}_{dia.year}.xlsx"
