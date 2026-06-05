"""
Reglas de remito para maestro / fletes / importación.

Jerarquía (ej. export Limansky):
  - NRO REMITO LEGAL LIMANSKY / RAR …  → remito del CD al cliente (único, no se reemite)
  - R00178… / R-…                      → mismo rol, formato alternativo
  - REMITO ORIGINAL / FINAL / DI (X…)  → tránsito interno, nunca va en columna REMITOS
  - NRO PEDIDO                         → identificador de pedido (columna ENVIO), no es remito
"""

from __future__ import annotations

import json
import re

from app.models import Envio
from app.services.remito_repair import remito_oficial_envio
from app.services.remito_utils import es_remito_oficial, es_remito_transito, normalizar_remito

_RE_PEDIDO_FABRICA = re.compile(r"^PER(\d{3})(\d{8})$", re.IGNORECASE)

# Columnas Excel → remito oficial (orden estricto; sin REMITO ORIGINAL/FINAL)
COLUMNAS_REMITO_OFICIAL = (
    "NRO REMITO LEGAL LIMANSKY",
    "NRO REMITO LEGAL",
    "REMITO LEGAL",
    "REMITO RAR",
    "RAR",
    "REMITO ENTREGA",
    "NRO REMITO",
)

# Solo tránsito (X) — no mapear al campo remito del Envio
COLUMNAS_REMITO_TRANSITO = (
    "REMITO DI",
    "REMITO ORIGINAL",
    "REMITO FINAL",
    "REMITO TRANSITO",
    "REMITO DE TRASLADO",
)

def formato_remito_maestro(remito: str | None) -> str:
    """Formato visual RAR / R-… Solo si es remito oficial."""
    if not remito or not es_remito_oficial(remito):
        return ""
    text = str(remito).strip().upper()
    if text.startswith("RAR"):
        digits = "".join(c for c in text if c.isdigit())
        if len(digits) >= 12:
            return f"R-{digits[:4]}-{digits[4:12]}"
        if len(digits) >= 8:
            return f"RAR {digits}"
    digits = "".join(c for c in text if c.isdigit())
    if len(digits) >= 12:
        return f"R-{digits[-12:-8]}-{digits[-8:]}"
    if len(digits) >= 8:
        return f"R-{digits[:4]}-{digits[4:]}"
    return text


def remito_transito_visual(envio: Envio) -> str:
    """Formato manual Limansky: -0117-00117064 (desde PER o remito X)."""
    if envio.raw_json:
        try:
            data = json.loads(envio.raw_json)
            raw = data.get("_excel_raw") if isinstance(data, dict) else {}
            if isinstance(raw, dict):
                for val in raw.values():
                    if not val:
                        continue
                    text = str(val).strip().upper()
                    m = _RE_PEDIDO_FABRICA.match(text)
                    if m:
                        return f"-0{m.group(1)}-{m.group(2)}"
            transito = data.get("remito_transito") if isinstance(data, dict) else None
            if transito and es_remito_transito(str(transito)):
                digits = "".join(c for c in str(transito) if c.isdigit())
                if len(digits) >= 11:
                    return f"-0{digits[1:4]}-{digits[4:12]}"
        except json.JSONDecodeError:
            pass
    if envio.remito and es_remito_transito(envio.remito):
        digits = "".join(c for c in envio.remito if c.isdigit())
        if len(digits) >= 11:
            return f"-0{digits[1:4]}-{digits[4:12]}"
    return ""


def texto_remito_grilla(envio: Envio) -> str:
    """Texto REMITOS para una línea (compat)."""
    return texto_remito_grupo([envio])


def texto_remito_grupo(lineas: list[Envio]) -> str:
    """Columna REMITOS estilo manual: tránsito (-0117-…) + oficial (R-0114-…)."""
    transitos: list[str] = []
    oficiales: list[str] = []
    for envio in lineas:
        t = remito_transito_visual(envio)
        if t and t not in transitos:
            transitos.append(t)
        oficial = remito_oficial_envio(envio)
        if oficial:
            fmt = formato_remito_maestro(oficial) or oficial.strip()
            if fmt and fmt not in oficiales:
                oficiales.append(fmt)
    partes = transitos + oficiales
    return " + ".join(partes)


def clave_agrupacion_caso(envio: Envio) -> str | None:
    """Clave de caso = remito normalizado. None si no hay remito oficial."""
    oficial = remito_oficial_envio(envio)
    if not oficial:
        return None
    norm = normalizar_remito(oficial)
    return norm or None


def estado_remito_envio(envio: Envio) -> str:
    """
    con_remito | solo_transito | sin_fecha_entrega | sin_remito
    No se puede remitir a futuro sin fecha de entrega pactada.
    """
    from app.services.fecha_utils import parse_fecha_tango

    if remito_oficial_envio(envio):
        return "con_remito"
    fe = parse_fecha_tango(envio.fecha_entrega)
    if not fe:
        return "sin_fecha_entrega"
    import json

    if envio.raw_json:
        try:
            data = json.loads(envio.raw_json)
            raw = data.get("_excel_raw") if isinstance(data, dict) else {}
            if isinstance(raw, dict):
                for k, v in raw.items():
                    if "REMITO DI" in str(k).upper() and es_remito_transito(str(v)):
                        return "solo_transito"
        except json.JSONDecodeError:
            pass
    return "sin_remito"


def etiqueta_estado_remito(codigo: str) -> str:
    return {
        "con_remito": "Con remito",
        "solo_transito": "Sin remito",
        "sin_fecha_entrega": "Sin fecha entrega",
        "sin_remito": "Sin remito",
    }.get(codigo, codigo)


def grupo_pasa_filtro_remito(lineas: list[Envio], remito_estado: str) -> bool:
    if not remito_estado or remito_estado == "todos":
        return True
    estado = estado_remito_envio(lineas[0])
    if remito_estado == "sin_remito":
        return estado in ("sin_remito", "solo_transito")
    if remito_estado == "solo_transito":
        return estado == "solo_transito"
    return estado == remito_estado


def clave_agrupacion_interna(envio: Envio) -> str:
    """Fallback interno (no mostrar como REMITOS): pedido o id de línea."""
    ped = (envio.nro_pedido or "").strip()
    if ped:
        return f"pedido-{ped}"
    return f"linea-{envio.id or 0}"
