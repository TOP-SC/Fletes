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


def _transito_desde_per_fabrica(envio: Envio) -> str:
    """Referencia PER del Excel (solo para combinar con R en maestro manual)."""
    if not envio.raw_json:
        return ""
    try:
        data = json.loads(envio.raw_json)
        raw = data.get("_excel_raw") if isinstance(data, dict) else {}
        if not isinstance(raw, dict):
            return ""
        for key in ("NRO PEDIDO FABRICA", "NRO PEDIDO FABRICA "):
            val = raw.get(key)
            if not val:
                continue
            m = _RE_PEDIDO_FABRICA.match(str(val).strip().upper())
            if m:
                return f"-0{m.group(1)}-{m.group(2)}"
    except json.JSONDecodeError:
        pass
    return ""


def _transito_desde_x(envio: Envio) -> str:
    """Remito X de tránsito (REMITO DI / ORIGINAL / FINAL), nunca pedido ni PER."""
    candidatos: list[str] = []
    if envio.raw_json:
        try:
            data = json.loads(envio.raw_json)
            transito = data.get("remito_transito")
            if transito and es_remito_transito(str(transito)):
                candidatos.append(str(transito).strip())
            raw = data.get("_excel_raw") if isinstance(data, dict) else {}
            if isinstance(raw, dict):
                for key, val in raw.items():
                    ku = str(key).upper()
                    if not val:
                        continue
                    if any(
                        p in ku
                        for p in ("REMITO DI", "REMITO ORIGINAL", "REMITO FINAL", "REMITO TRANSITO")
                    ) and es_remito_transito(str(val)):
                        candidatos.append(str(val).strip())
        except json.JSONDecodeError:
            pass
    if envio.remito and es_remito_transito(envio.remito):
        candidatos.append(str(envio.remito).strip())
    for text in candidatos:
        digits = "".join(c for c in text if c.isdigit())
        if len(digits) >= 11:
            return f"-0{digits[1:4]}-{digits[4:12]}"
    return ""


def remito_transito_visual(envio: Envio) -> str:
    """Tránsito para maestro manual: PER fábrica (-0117-…); si no, remito X."""
    t = _transito_desde_per_fabrica(envio)
    if t:
        return t
    return _transito_desde_x(envio)


def texto_remito_grilla(envio: Envio) -> str:
    """Texto REMITOS para una línea (compat)."""
    return texto_remito_grupo([envio])


def texto_remito_grupo(lineas: list[Envio]) -> str:
    """
    Columna REMITOS: solo remitos oficiales RAR / R-… (sin X ni PER de tránsito).
    Sin remito oficial → vacío.
    """
    oficiales: list[str] = []
    for envio in lineas:
        oficial = remito_oficial_envio(envio)
        if oficial:
            fmt = formato_remito_maestro(oficial) or oficial.strip()
            if fmt and fmt not in oficiales:
                oficiales.append(fmt)
    return " + ".join(oficiales)


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
            transito = data.get("remito_transito")
            if transito and es_remito_transito(str(transito)):
                return "solo_transito"
            raw = data.get("_excel_raw") if isinstance(data, dict) else {}
            if isinstance(raw, dict):
                for k, v in raw.items():
                    ku = str(k).upper()
                    if not v:
                        continue
                    if any(
                        p in ku
                        for p in ("REMITO DI", "REMITO ORIGINAL", "REMITO FINAL", "REMITO TRANSITO")
                    ) and es_remito_transito(str(v)):
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
