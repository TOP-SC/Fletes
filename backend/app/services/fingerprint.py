import hashlib
import json
from typing import Any


def build_fingerprint(row: dict[str, Any]) -> str:
    """Clave estable por renglón: no pisa registros ya importados."""
    parts = [
        str(row.get("remito") or "").strip().upper(),
        str(row.get("nro_pedido") or "").strip(),
        str(row.get("cod_articulo") or "").strip().upper(),
        str(row.get("fecha_entrega") or "").strip(),
        str(row.get("nro_factura") or "").strip(),
    ]
    payload = "|".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def row_to_json(row: dict[str, Any]) -> str:
    """Persiste solo campos de negocio (sin _excel_raw ni metadatos de parseo)."""
    slim = {k: v for k, v in row.items() if not str(k).startswith("_")}
    return json.dumps(slim, ensure_ascii=False, default=str)
