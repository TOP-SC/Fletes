from io import BytesIO
from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from app.config import TARIFARIOS_DIR
from app.models import Tarifa
from app.schemas import TarifaIn
from app.services.flex_excel import find_column
from app.services.money_utils import parse_money
from app.services.tarifario_mantello_parser import is_tarifario_mantello, parse_tarifario_mantello

TARIFA_COLUMNS = {
    "proveedor",
    "provincia",
    "localidad",
    "tipo_producto",
    "medida",
    "precio",
    "cedol",
    "vigencia_desde",
    "vigencia_hasta",
    "notas",
}

PRECIO_ALIASES = ("precio", "tarifa", "importe", "valor", "costo")


def _resolve_precio_column(columns: list[str]) -> str | None:
    lower = {str(c).strip().lower(): c for c in columns}
    for alias in PRECIO_ALIASES:
        if alias in lower:
            return str(lower[alias])
    return find_column(columns, *PRECIO_ALIASES)


def create_tarifa(db: Session, data: TarifaIn, *, commit: bool = True) -> Tarifa:
    tarifa = Tarifa(**data.model_dump())
    db.add(tarifa)
    if commit:
        db.commit()
        db.refresh(tarifa)
    return tarifa


def _persist_tarifas_rows(db: Session, rows: list[dict], *, commit: bool = True) -> int:
    count = 0
    for row in rows:
        precio = parse_money(row.get("precio"))
        if precio is None or not row.get("proveedor"):
            continue
        data = TarifaIn(
            proveedor=str(row["proveedor"]).strip(),
            provincia=str(row.get("provincia") or "").strip(),
            localidad=str(row.get("localidad") or "").strip(),
            tipo_producto=str(row.get("tipo_producto") or "").strip(),
            medida=str(row.get("medida") or "").strip(),
            precio=precio,
            cedol=str(row["cedol"]).strip() if row.get("cedol") else None,
            vigencia_desde=str(row["vigencia_desde"]) if row.get("vigencia_desde") else None,
            vigencia_hasta=str(row["vigencia_hasta"]) if row.get("vigencia_hasta") else None,
            notas=str(row["notas"]) if row.get("notas") else None,
        )
        create_tarifa(db, data, commit=False)
        count += 1
    if commit and count:
        db.commit()
    return count


def import_tarifas_excel(db: Session, content: bytes, *, commit: bool = True) -> int:
    if is_tarifario_mantello(content):
        rows = parse_tarifario_mantello(content)
        return _persist_tarifas_rows(db, rows, commit=commit)

    df = pd.read_excel(BytesIO(content))
    df.columns = [str(c).strip().lower() for c in df.columns]
    col_precio = _resolve_precio_column(list(df.columns))
    count = 0

    for _, row in df.iterrows():
        payload = {k: row.get(k) for k in df.columns if k in TARIFA_COLUMNS}
        if col_precio and col_precio.lower() in df.columns:
            payload["precio"] = row.get(col_precio.lower())

        if not payload.get("proveedor") or pd.isna(payload.get("proveedor")):
            continue

        precio = parse_money(payload.get("precio"))
        if precio is None:
            continue

        data = TarifaIn(
            proveedor=str(payload["proveedor"]).strip(),
            provincia=str(payload.get("provincia") or "").strip(),
            localidad=str(payload.get("localidad") or "").strip(),
            tipo_producto=str(payload.get("tipo_producto") or "").strip(),
            medida=str(payload.get("medida") or "").strip(),
            precio=precio,
            cedol=str(payload["cedol"]).strip()
            if payload.get("cedol") and not pd.isna(payload.get("cedol"))
            else None,
            vigencia_desde=str(payload["vigencia_desde"])
            if payload.get("vigencia_desde") and not pd.isna(payload.get("vigencia_desde"))
            else None,
            vigencia_hasta=str(payload["vigencia_hasta"])
            if payload.get("vigencia_hasta") and not pd.isna(payload.get("vigencia_hasta"))
            else None,
            notas=str(payload["notas"])
            if payload.get("notas") and not pd.isna(payload.get("notas"))
            else None,
        )
        create_tarifa(db, data, commit=False)
        count += 1

    if commit and count:
        db.commit()
    return count


def import_tarifarios_desde_carpeta(db: Session, folder: Path | None = None) -> dict[str, object]:
    """Escanea carpeta y crea borradores (activa auto si el proveedor no tenía versión)."""
    from app.services.tarifario_version_service import escanear_carpeta_tarifarios

    return escanear_carpeta_tarifarios(db, folder)
