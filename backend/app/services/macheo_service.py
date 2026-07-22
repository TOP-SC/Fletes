"""Paso 3 — Macheo Clickpack ↔ planilla SommierCenter (Tango)."""

from collections import defaultdict
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Envio, PrefacturaClickpac, PostventaRegistro
from app.services.postventa_rules import aplicar_regla_postventa_a_envio
from app.services.remito_utils import normalizar_remito
from app.services.rules_service import aplicar_reglas_envio, costo_referencia_linea, recalcular_grupo
from app.transporte_reglas import (
    COD_CROSSDOCKING,
    COD_EXPRESO_CLICPAQ,
    normalizar_transporte_cod,
)


def _envio_indexable_macheo(envio: Envio) -> bool:
    """
    Envíos elegibles para cruce prefactura CLICPAQ.
    Incluye canal red (51/82/83) aunque ``excluir_planilla`` esté mal marcado
    (ej. Mar del Plata en Modo Adrián / LOG WAMARO).
    """
    if not envio.excluir_planilla:
        return True
    if envio.alerta_clickpack:
        return True
    cod = normalizar_transporte_cod(envio.transporte_cod, envio.transporte_nombre) or ""
    return cod in (COD_EXPRESO_CLICPAQ, COD_CROSSDOCKING, "83")


def _claves_remito(remito: str | None, remito_norm: str | None) -> set[str]:
    """Variantes de clave para tolerar ceros, guiones y cuerpos solo-dígitos."""
    keys: set[str] = set()
    if remito_norm:
        keys.add(remito_norm)
    norm = normalizar_remito(remito)
    if norm:
        keys.add(norm)
    digits = re.sub(r"\D", "", str(remito or ""))
    if digits:
        stripped = digits.lstrip("0") or digits
        keys.add(stripped)
        keys.add(digits)
        # Últimos 10–12 dígitos (cuerpo típico Tango R00…)
        if len(stripped) > 12:
            keys.add(stripped[-12:])
        if len(stripped) > 10:
            keys.add(stripped[-10:])
    return {k for k in keys if k}


def _index_envios(envios: list[Envio]) -> dict[str, list[Envio]]:
    idx: dict[str, list[Envio]] = defaultdict(list)
    for e in envios:
        if not _envio_indexable_macheo(e):
            continue
        for key in _claves_remito(e.remito, e.remito_norm):
            if e not in idx[key]:
                idx[key].append(e)
    return idx


def ejecutar_macheo_clickpack(db: Session) -> dict[str, int]:
    prefacturas = list(db.scalars(select(PrefacturaClickpac)).all())
    envios = list(db.scalars(select(Envio)).all())
    idx = _index_envios(envios)

    stats = {
        "prefacturas": len(prefacturas),
        "matcheados": 0,
        "conjuntos": 0,
        "sin_match_prefactura": 0,
        "sin_match_envio": 0,
    }
    matched_keys: set[str] = set()
    matched_envio_ids: set[int] = set()

    for pf in prefacturas:
        claves = _claves_remito(pf.remito, pf.remito_norm)
        grupo: list[Envio] = []
        seen: set[int] = set()
        for key in claves:
            for e in idx.get(key, []):
                if e.id not in seen:
                    grupo.append(e)
                    seen.add(e.id)
        if not grupo:
            pf.macheo_estado = "sin_match"
            stats["sin_match_prefactura"] += 1
            continue

        matched_keys |= claves
        estado = "matcheado" if len(grupo) == 1 else "conjunto"
        if estado == "conjunto":
            stats["conjuntos"] += 1
        else:
            stats["matcheados"] += 1

        pf.macheo_estado = estado
        for e in grupo:
            e.prefactura_clickpac_id = pf.id
            e.macheo_estado = estado
            e.prefactura_proveedor = pf.importe
            if pf.nro_envio:
                e.nro_envio_clp = pf.nro_envio
            if pf.fecha_reporte:
                e.fecha_presentacion_pf = pf.fecha_reporte
            matched_envio_ids.add(e.id)

        recalcular_grupo(grupo)
        for e in grupo:
            aplicar_reglas_envio(e, preservar_postventa=True)

    for key, grupo in idx.items():
        if key not in matched_keys:
            for e in grupo:
                if e.id in matched_envio_ids:
                    continue
                if e.alerta_clickpack and e.macheo_estado not in ("matcheado", "conjunto"):
                    e.macheo_estado = "pendiente_clickpack"
            stats["sin_match_envio"] += len(
                [e for e in grupo if e.id not in matched_envio_ids]
            )

    db.commit()
    return stats


def aplicar_postventa_a_envios(db: Session) -> dict[str, int]:
    registros = list(db.scalars(select(PostventaRegistro)).all())
    envios = list(db.scalars(select(Envio)).all())
    idx = _index_envios(envios)
    aplicados = 0
    for reg in registros:
        claves = _claves_remito(reg.remito, reg.remito_norm)
        grupo: list[Envio] = []
        seen: set[int] = set()
        for key in claves:
            for e in idx.get(key, []):
                if e.id not in seen:
                    grupo.append(e)
                    seen.add(e.id)
        for e in grupo:
            aplicar_regla_postventa_a_envio(e, reg)
            aplicados += 1
    db.commit()
    return {"registros": len(registros), "envios_actualizados": aplicados}


def ejecutar_conciliacion_liquidacion(db: Session) -> dict[str, int]:
    from app.models import LiquidacionLinea

    lineas = list(db.scalars(select(LiquidacionLinea)).all())
    envios = list(db.scalars(select(Envio)).all())
    idx = _index_envios(envios)
    ok = desvio = sin_match = 0

    for lin in lineas:
        claves = _claves_remito(lin.remito, lin.remito_norm)
        grupo: list[Envio] = []
        seen: set[int] = set()
        for key in claves:
            for e in idx.get(key, []):
                if e.id not in seen:
                    grupo.append(e)
                    seen.add(e.id)
        if not grupo:
            lin.macheo_estado = "sin_match"
            sin_match += 1
            continue
        control = sum(
            e.prefactura_proveedor or 0 for e in grupo
        ) / max(1, len({e.prefactura_clickpac_id for e in grupo if e.prefactura_clickpac_id}))
        ref = sum(costo_referencia_linea(e) or 0 for e in grupo)
        diff = round(lin.importe_liquidacion - (control or ref), 2)
        if abs(diff) <= 0.01:
            lin.macheo_estado = "ok"
            ok += 1
        else:
            lin.macheo_estado = "desvio"
            desvio += 1
            for e in grupo:
                e.regla_color = "rojo"
                e.regla_motivo = (
                    f"Liquidación quincenal: desvío ${diff} "
                    f"(liq ${lin.importe_liquidacion} vs control ${control or ref})"
                )
    db.commit()
    return {"lineas": len(lineas), "ok": ok, "desvios": desvio, "sin_match": sin_match}
