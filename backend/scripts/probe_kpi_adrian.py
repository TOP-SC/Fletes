"""Probe KPI entregas x mes vs Excel Adrian."""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Envio
from app.services.fecha_utils import parse_fecha_tango, rango_quincena, periodo_mes_solo
from app.services.maestro_service import _agrupar_por_caso, _fila_maestro_desde_grupo, _origen_planilla
from app.services.modo_adrian_service import es_circuito_log_wamaro_adrian

MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def kpi_entrega(anio: int, mes: int, q: int, origen: str, filtro: str, envios: list) -> None:
    d0, d1 = rango_quincena(anio, mes, q)
    _kpi_core(d0, d1, anio, mes, origen, filtro, envios, "entrega")


def kpi_mes_completo(anio: int, mes: int, origen: str, filtro: str, envios: list) -> None:
    d0, d1 = periodo_mes_solo(anio, mes)
    _kpi_core(d0, d1, anio, mes, origen, filtro, envios, "mes")


def _kpi_core(d0, d1, anio, mes, origen, filtro, envios, label):
    grupos = _agrupar_por_caso(envios)
    by_ped: dict[str, dict[str, float]] = defaultdict(lambda: {"n": 0, "imp": 0.0})
    total_n = 0
    for key, lines in grupos.items():
        base = lines[0]
        if _origen_planilla(base.deposito, base.origen_cd) != origen:
            continue
        if filtro == "adrian" and not es_circuito_log_wamaro_adrian(base):
            continue
        fe = base.fecha_entrega_d or parse_fecha_tango(base.fecha_entrega)
        if not fe or fe < d0 or fe > d1:
            continue
        fp = base.fecha_pedido_d or parse_fecha_tango(base.fecha_pedido)
        total_n += 1
        if fp:
            m = MESES[fp.month - 1]
            by_ped[m]["n"] += 1
    print(f"{filtro} {label} {MESES[mes-1]} {anio} {origen}: TOTAL {total_n}")
    for m in MESES:
        if by_ped[m]["n"]:
            print(f"  ped-{m}: {int(by_ped[m]['n'])}")


def kpi(anio: int, mes: int, q: int, origen: str, filtro: str, envios: list) -> None:
    kpi_entrega(anio, mes, q, origen, filtro, envios)


def rtos_mes(anio: int, mes: int, origen: str | None, envios: list) -> int:
    d0, d1 = periodo_mes_solo(anio, mes)
    grupos = _agrupar_por_caso(envios)
    n = 0
    for _, lines in grupos.items():
        base = lines[0]
        if origen and _origen_planilla(base.deposito, base.origen_cd) != origen:
            continue
        fe = base.fecha_entrega_d or parse_fecha_tango(base.fecha_entrega)
        if fe and d0 <= fe <= d1:
            n += 1
    return n


def main() -> None:
    db = SessionLocal()
    envios = list(db.scalars(select(Envio)).all())
    db.close()
    print(f"envios: {len(envios)}")
    for f in ("maestro", "adrian", "interior"):
        kpi(2026, 4, 1, "sa", f, envios)
        kpi(2026, 4, 1, "tortuguitas", f, envios)
    print("rtos abril 2026:", rtos_mes(2026, 4, None, envios))
    kpi(2026, 5, 1, "tortuguitas", "adrian", envios)
    kpi_mes_completo(2026, 5, "tortuguitas", "adrian", envios)


if __name__ == "__main__":
    main()
