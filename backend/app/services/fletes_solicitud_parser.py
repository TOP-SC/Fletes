"""Parser Excel «Fletes Solicitados sucursales» (Drive vendedores)."""

from __future__ import annotations

import io
import json
import re
from typing import Any

import pandas as pd

from app.fleteros import normalizar_nombre_fletero


def _cell_str(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    return s if s and s.lower() != "nan" else None


def _cell_float(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def extraer_pedidos_articulos(texto: str | None) -> list[str]:
    if not texto:
        return []
    found = re.findall(r"Nro Pedido:\s*(\d+)", str(texto))
    out: list[str] = []
    seen: set[str] = set()
    for p in found:
        key = p.strip()
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out


def _norm_pedido(p: str | None) -> str:
    s = (p or "").strip()
    return s.lstrip("0") or s


def leer_solicitudes_excel(content: bytes) -> list[dict[str, Any]]:
    """Hoja Resultados del export LOG / Drive."""
    bio = io.BytesIO(content)
    xl = pd.ExcelFile(bio)
    sheet = "Resultados" if "Resultados" in xl.sheet_names else xl.sheet_names[0]
    df = pd.read_excel(bio, sheet_name=sheet, header=0)
    df.columns = [str(c).strip() for c in df.columns]

    required = {"idFlete", "Fletero", "Articulos"}
    if not required.issubset(set(df.columns)):
        raise ValueError(
            f"Excel sin columnas esperadas (idFlete, Fletero, Articulos). "
            f"Encontradas: {list(df.columns)}"
        )

    rows: list[dict[str, Any]] = []
    for _, r in df.iterrows():
        ext_id = _cell_str(r.get("idFlete"))
        if not ext_id:
            continue
        pedidos = extraer_pedidos_articulos(_cell_str(r.get("Articulos")))
        fletero_raw = _cell_str(r.get("Fletero"))
        row = {
            "id_flete_externo": ext_id,
            "fletero_nombre": normalizar_nombre_fletero(fletero_raw),
            "cliente": _cell_str(r.get("Cliente")),
            "solicitado_por": _cell_str(r.get("SolicitadoPor")),
            "fecha_solicitado": _cell_str(r.get("FechaSolicitado")),
            "fecha_entrega": _cell_str(r.get("FechaEntrega")),
            "local_compra": _cell_str(r.get("LocalCompra")),
            "local_entrega": _cell_str(r.get("LocalEntrega")),
            "abona": _cell_str(r.get("Abona")),
            "motivo": _cell_str(r.get("Motivo")),
            "proveedor_excel": _cell_str(r.get("Proveedor")),
            "importe_wamaro": _cell_float(r.get("ImporteWamaro")),
            "importe_cliente": _cell_float(r.get("ImporteCliente")),
            "estado": _cell_str(r.get("EstadoFlete")),
            "direccion": _cell_str(r.get("Direccion")),
            "comentario": _cell_str(r.get("Comentario")),
            "articulos_raw": _cell_str(r.get("Articulos")),
            "pedidos": pedidos,
            "nro_pedido": pedidos[0] if pedidos else None,
            "nro_pedido_norm": _norm_pedido(pedidos[0]) if pedidos else None,
            "raw_json": json.dumps(
                {k: (None if pd.isna(v) else v) for k, v in r.items()},
                ensure_ascii=False,
                default=str,
            ),
        }
        rows.append(row)
    return rows
