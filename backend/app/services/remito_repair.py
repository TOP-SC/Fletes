"""Corrección de remito del CD (RAR / R) vs tránsito (X) en envíos ya importados."""

from __future__ import annotations

import json
from typing import Any

from app.models import Envio
from app.services.remito_resolver import clasificar_valor_remito, resolver_remitos_fila
from app.services.remito_utils import (
    es_remito_oficial,
    es_remito_transito,
    normalizar_remito,
)

import pandas as pd


def _pdo_desde_envio(envio: Envio) -> str | None:
    if not envio.raw_json:
        return None
    try:
        data = json.loads(envio.raw_json)
        raw = data.get("_excel_raw") if isinstance(data, dict) else {}
        if isinstance(raw, dict):
            pdo = raw.get("PDO")
            return str(pdo).strip() if pdo else None
    except json.JSONDecodeError:
        pass
    return None


def _valores_desde_objeto(obj: Any) -> list[str]:
    out: list[str] = []
    if isinstance(obj, dict):
        for v in obj.values():
            out.extend(_valores_desde_objeto(v))
    elif isinstance(obj, list):
        for v in obj:
            out.extend(_valores_desde_objeto(v))
    elif obj is not None:
        text = str(obj).strip()
        if text and text.lower() not in ("nan", "none"):
            out.append(text)
    return out


def resolver_remitos_desde_dict(data: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    """Busca remito del CD en _excel_raw o en el JSON guardado de la fila."""
    excel_raw = data.get("_excel_raw")
    if isinstance(excel_raw, dict) and excel_raw:
        series = pd.Series(excel_raw)
        return resolver_remitos_fila(series)

    entrega: str | None = data.get("remito_entrega")
    transito: str | None = data.get("remito_transito")
    principal: str | None = data.get("remito")

    if principal and es_remito_oficial(principal):
        return principal, entrega, transito

    candidatos_entrega: list[str] = []
    candidatos_transito: list[str] = []

    for val in _valores_desde_objeto(data):
        if len(val) < 6:
            continue
        kind = clasificar_valor_remito(val)
        if kind == "entrega":
            candidatos_entrega.append(val)
        elif kind == "transito":
            candidatos_transito.append(val)

    entrega = entrega or (candidatos_entrega[0] if candidatos_entrega else None)
    transito = transito or (candidatos_transito[0] if candidatos_transito else None)
    principal = entrega
    return principal, entrega, transito


def _aplicar_remito_cd(envio: Envio, data: dict, principal: str, entrega: str | None, transito: str | None) -> bool:
    if not es_remito_oficial(principal):
        return False
    cambio = envio.remito != principal
    envio.remito = principal
    envio.remito_norm = normalizar_remito(principal)
    data["remito"] = principal
    if entrega:
        data["remito_entrega"] = entrega
    if transito:
        data["remito_transito"] = transito
    envio.raw_json = json.dumps(data, ensure_ascii=False, default=str)
    return cambio or True


def corregir_remito_envio(envio: Envio) -> bool:
    """Reemplaza remito X o inválido por el remito del CD (RAR/R)."""
    actual = (envio.remito or "").strip()
    ped = (envio.nro_pedido or "").strip()
    if ped and actual == ped:
        actual = ""
        envio.remito = None
    if actual and es_remito_oficial(actual):
        return False

    if not envio.raw_json:
        if actual and (es_remito_transito(actual) or not es_remito_oficial(actual)):
            envio.remito = None
            envio.remito_norm = ""
            return True
        return False

    try:
        data = json.loads(envio.raw_json)
    except json.JSONDecodeError:
        return False

    if not isinstance(data, dict):
        return False

    principal, entrega, transito = resolver_remitos_desde_dict(data)
    if principal and es_remito_oficial(principal):
        return _aplicar_remito_cd(envio, data, principal, entrega, transito)

    if actual and (es_remito_transito(actual) or not es_remito_oficial(actual)):
        envio.remito = None
        envio.remito_norm = ""
        if transito:
            data["remito_transito"] = transito
            envio.raw_json = json.dumps(data, ensure_ascii=False, default=str)
        return True
    return False


def propagar_remitos_cd(envios: list[Envio]) -> int:
    """
    Mismo pedido (PDO) comparte un único remito del CD.
    Las líneas que solo traen X en REMITO DI heredan el RAR/R de otra línea del mismo PDO.
    """
    por_pdo: dict[str, str] = {}
    por_pedido: dict[str, str] = {}

    for envio in envios:
        r = (envio.remito or "").strip()
        if not es_remito_oficial(r):
            continue
        pdo = _pdo_desde_envio(envio)
        if pdo:
            por_pdo[pdo] = r
        ped = (envio.nro_pedido or "").strip()
        if ped:
            por_pedido[ped] = r

    cambios = 0
    for envio in envios:
        if es_remito_oficial(envio.remito):
            continue
        candidato: str | None = None
        pdo = _pdo_desde_envio(envio)
        if pdo and pdo in por_pdo:
            candidato = por_pdo[pdo]
        if not candidato:
            ped = (envio.nro_pedido or "").strip()
            if ped and ped in por_pedido:
                candidato = por_pedido[ped]
        if not candidato or not es_remito_oficial(candidato):
            continue
        if envio.raw_json:
            try:
                data = json.loads(envio.raw_json)
            except json.JSONDecodeError:
                data = {}
        else:
            data = {}
        _, entrega, transito = resolver_remitos_desde_dict(data)
        if _aplicar_remito_cd(envio, data, candidato, entrega or candidato, transito):
            cambios += 1
    return cambios


def remito_oficial_envio(envio: Envio) -> str | None:
    """Remito del CD para pantalla y agrupación; nunca devuelve X."""
    if es_remito_oficial(envio.remito):
        return str(envio.remito).strip()
    if envio.raw_json:
        try:
            data = json.loads(envio.raw_json)
            if isinstance(data, dict):
                principal, _, _ = resolver_remitos_desde_dict(data)
                if es_remito_oficial(principal):
                    return str(principal).strip()
        except json.JSONDecodeError:
            pass
    return None


def corregir_remito_fila(row: dict[str, Any]) -> bool:
    """Ajusta remito en dict de fila antes de crear Envio."""
    actual = (row.get("remito") or "").strip()
    if actual and es_remito_oficial(actual):
        return False
    principal, entrega, transito = resolver_remitos_desde_dict(row)
    if not principal or not es_remito_oficial(principal):
        if actual and es_remito_transito(actual):
            row["remito"] = None
            row["remito_transito"] = actual
        return False
    row["remito"] = principal
    if entrega:
        row["remito_entrega"] = entrega
    if transito:
        row["remito_transito"] = transito
    return True
