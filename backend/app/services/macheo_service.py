"""Paso 3 — Macheo Clickpack ↔ planilla SommierCenter (Tango)."""

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Envio, PrefacturaClickpac, PostventaRegistro
from app.services.postventa_rules import aplicar_regla_postventa_a_envio
from app.services.remito_utils import normalizar_remito
from app.services.rules_service import aplicar_reglas_envio, costo_referencia_linea, recalcular_grupo


def _index_envios(envios: list[Envio]) -> dict[str, list[Envio]]:
    idx: dict[str, list[Envio]] = defaultdict(list)
    for e in envios:
        if e.excluir_planilla:
            continue
        key = e.remito_norm or normalizar_remito(e.remito)
        if key:
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

    for pf in prefacturas:
        key = pf.remito_norm or ""
        grupo = idx.get(key, [])
        if not grupo:
            pf.macheo_estado = "sin_match"
            stats["sin_match_prefactura"] += 1
            continue

        matched_keys.add(key)
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

        recalcular_grupo(grupo)
        for e in grupo:
            aplicar_reglas_envio(e, preservar_postventa=True)

    for key, grupo in idx.items():
        if key not in matched_keys:
            for e in grupo:
                if e.alerta_clickpack and e.macheo_estado not in ("matcheado", "conjunto"):
                    e.macheo_estado = "pendiente_clickpack"
            stats["sin_match_envio"] += len(grupo)

    db.commit()
    return stats


def aplicar_postventa_a_envios(db: Session) -> dict[str, int]:
    registros = list(db.scalars(select(PostventaRegistro)).all())
    envios = list(db.scalars(select(Envio)).all())
    idx = _index_envios(envios)
    aplicados = 0
    for reg in registros:
        grupo = idx.get(reg.remito_norm or "", [])
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
        grupo = idx.get(lin.remito_norm or "", [])
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
