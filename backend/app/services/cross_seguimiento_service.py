"""Import y macheo colaborativo de planillas cross (Retirado por …)."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import unquote

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import CROSS_PLANILLAS_DRIVE
from app.models import CrossSeguimiento, Envio, ImportBatch
from app.services.cross_parser import listar_hojas_workbook, parse_cross_workbook
from app.services.remito_utils import normalizar_remito


def _upsert_seguimiento(db: Session, row: dict[str, Any], batch_id: int) -> tuple[bool, bool]:
    """Returns (inserted, updated)."""
    norm = row["remito_norm"]
    existente = db.scalar(select(CrossSeguimiento).where(CrossSeguimiento.remito_norm == norm))
    if existente is None:
        db.add(
            CrossSeguimiento(
                remito_norm=norm,
                remito=row.get("remito"),
                nro_pedido=row.get("nro_pedido"),
                proveedor=row.get("proveedor"),
                hoja_origen=row.get("hoja_origen"),
                archivo_origen=row.get("archivo_origen"),
                import_batch_id=batch_id,
                fecha_retiro=row.get("fecha_retiro"),
                fecha_entrega_coord=row.get("fecha_entrega_coord"),
                entregado=row.get("entregado") or "pendiente",
                observacion=row.get("observacion"),
                match_estado="pendiente",
                raw_json=row.get("raw_json"),
            )
        )
        return True, False

    existente.remito = row.get("remito") or existente.remito
    existente.nro_pedido = row.get("nro_pedido") or existente.nro_pedido
    existente.proveedor = row.get("proveedor") or existente.proveedor
    existente.hoja_origen = row.get("hoja_origen") or existente.hoja_origen
    existente.archivo_origen = row.get("archivo_origen") or existente.archivo_origen
    existente.import_batch_id = batch_id
    if row.get("fecha_retiro"):
        existente.fecha_retiro = row["fecha_retiro"]
    if row.get("fecha_entrega_coord"):
        existente.fecha_entrega_coord = row["fecha_entrega_coord"]
    if row.get("entregado"):
        existente.entregado = row["entregado"]
    if row.get("observacion"):
        existente.observacion = row["observacion"]
    if row.get("raw_json"):
        existente.raw_json = row["raw_json"]
    return False, True


def import_cross_workbook(
    db: Session,
    content: bytes,
    filename: str,
    *,
    ejecutar_macheo: bool = True,
    solo_retirado: bool = True,
) -> dict[str, Any]:
    filas, hojas = parse_cross_workbook(content, filename, solo_retirado=solo_retirado)
    batch = ImportBatch(
        filename=filename,
        source="cross_seguimiento",
        rows_in_file=len(filas),
    )
    db.add(batch)
    db.flush()

    insertados = actualizados = 0
    for row in filas:
        ins, upd = _upsert_seguimiento(db, row, batch.id)
        insertados += int(ins)
        actualizados += int(upd)

    batch.rows_inserted = insertados
    batch.rows_skipped = actualizados
    db.commit()

    macheo: dict[str, int] | None = None
    if ejecutar_macheo and (insertados or actualizados):
        macheo = ejecutar_macheo_cross(db)

    return {
        "batch_id": batch.id,
        "filename": filename,
        "hojas_procesadas": hojas,
        "hojas_disponibles": listar_hojas_workbook(content),
        "filas_agregadas": len(filas),
        "insertados": insertados,
        "actualizados": actualizados,
        "macheo": macheo,
        "message": (
            f"Cross: {insertados} nuevos, {actualizados} actualizados "
            f"({len(hojas)} pestaña(s) Retirado)."
        ),
    }


def ejecutar_macheo_cross(db: Session) -> dict[str, int]:
    envios_norm = set(
        db.scalars(
            select(Envio.remito_norm).where(
                Envio.remito_norm.isnot(None),
                Envio.remito_norm != "",
            )
        ).all()
    )
    registros = list(db.scalars(select(CrossSeguimiento)).all())
    en_maestro = sin_maestro = 0
    for reg in registros:
        if reg.remito_norm in envios_norm:
            reg.match_estado = "en_maestro"
            en_maestro += 1
        else:
            reg.match_estado = "sin_maestro"
            sin_maestro += 1
    db.commit()
    return {
        "procesados": len(registros),
        "en_maestro": en_maestro,
        "sin_maestro": sin_maestro,
    }


def resumen_cross(db: Session) -> dict[str, Any]:
    total = db.scalar(select(func.count()).select_from(CrossSeguimiento)) or 0
    en_maestro = (
        db.scalar(
            select(func.count()).select_from(CrossSeguimiento).where(
                CrossSeguimiento.match_estado == "en_maestro"
            )
        )
        or 0
    )
    entregado_si = (
        db.scalar(
            select(func.count()).select_from(CrossSeguimiento).where(
                CrossSeguimiento.entregado == "SI"
            )
        )
        or 0
    )
    entregado_no = (
        db.scalar(
            select(func.count()).select_from(CrossSeguimiento).where(
                CrossSeguimiento.entregado == "NO"
            )
        )
        or 0
    )
    return {
        "total": total,
        "en_maestro": en_maestro,
        "sin_maestro": max(0, total - en_maestro),
        "entregado_si": entregado_si,
        "entregado_no": entregado_no,
        "pendiente_entrega": max(0, total - entregado_si - entregado_no),
    }


def info_cross_remito(db: Session, remito_norm: str) -> dict[str, Any] | None:
    if not remito_norm:
        return None
    reg = db.scalar(
        select(CrossSeguimiento).where(CrossSeguimiento.remito_norm == remito_norm)
    )
    if not reg:
        return None
    return _cross_a_dict(reg)


def info_cross_caso(lineas: list[Envio], db: Session) -> dict[str, Any] | None:
    for ln in lineas:
        norm = ln.remito_norm or normalizar_remito(ln.remito)
        if norm:
            info = info_cross_remito(db, norm)
            if info:
                return info
    return None


def _cross_a_dict(reg: CrossSeguimiento) -> dict[str, Any]:
    return {
        "remito_norm": reg.remito_norm,
        "remito": reg.remito,
        "nro_pedido": reg.nro_pedido,
        "proveedor": reg.proveedor,
        "hoja_origen": reg.hoja_origen,
        "archivo_origen": reg.archivo_origen,
        "fecha_retiro": reg.fecha_retiro,
        "fecha_entrega_coord": reg.fecha_entrega_coord,
        "entregado": reg.entregado,
        "observacion": reg.observacion,
        "match_estado": reg.match_estado,
        "actualizado": reg.updated_at.isoformat() if reg.updated_at else None,
    }


_SHEET_ID_RE = re.compile(r"docs\.google\.com/spreadsheets/d/([a-zA-Z0-9-_]+)")
_DRIVE_FILE_RE = re.compile(r"drive\.google\.com/file/d/([a-zA-Z0-9-_]+)")
_GID_RE = re.compile(r"gid=(\d+)")


def parse_google_drive_url(url: str) -> dict[str, str]:
    """Extrae sheet_id/gid o file_id de un link compartido de Google."""
    raw = unquote((url or "").strip())
    if not raw:
        raise ValueError("URL vacía")
    sheet = _SHEET_ID_RE.search(raw)
    if sheet:
        gid = "0"
        gid_match = _GID_RE.search(raw)
        if gid_match:
            gid = gid_match.group(1)
        return {"tipo": "sheet", "sheet_id": sheet.group(1), "gid": gid}
    drive = _DRIVE_FILE_RE.search(raw)
    if drive:
        return {"tipo": "file", "file_id": drive.group(1)}
    raise ValueError(
        "No reconozco el link. Pegá una URL de Google Sheets "
        "(docs.google.com/spreadsheets/…) o un .xlsx en Drive."
    )


def export_url_google(meta: dict[str, str]) -> str:
    if meta["tipo"] == "sheet":
        sid = meta["sheet_id"]
        gid = str(meta.get("gid") or "0")
        if gid and gid != "0":
            return f"https://docs.google.com/spreadsheets/d/{sid}/export?format=xlsx&gid={gid}"
        return f"https://docs.google.com/spreadsheets/d/{sid}/export?format=xlsx"
    return f"https://drive.google.com/uc?export=download&id={meta['file_id']}"


def descargar_planilla_drive(url: str) -> tuple[bytes, dict[str, str]]:
    """Descarga bytes de una planilla compartida (Sheets o archivo Drive)."""
    meta = parse_google_drive_url(url)
    export_url = export_url_google(meta)
    r = httpx.get(export_url, follow_redirects=True, timeout=120)
    ct = (r.headers.get("content-type") or "").lower()
    if r.status_code != 200 or "html" in ct[:20] or len(r.content) < 5000:
        raise ValueError(
            f"No se pudo descargar (HTTP {r.status_code}). "
            "Verificá que el archivo tenga permiso «Lector con link» / «Cualquier persona con el link»."
        )
    return r.content, meta


def importar_cross_desde_url(
    db: Session,
    url: str,
    *,
    nombre: str | None = None,
    ejecutar_macheo: bool = True,
) -> dict[str, Any]:
    """Descarga un Excel desde link de Drive/Sheets e importa pestañas Retirado."""
    content, meta = descargar_planilla_drive(url)
    if nombre and nombre.strip():
        fname = nombre.strip()
    elif meta["tipo"] == "sheet":
        fname = f"cross_{meta['sheet_id'][:10]}.xlsx"
    else:
        fname = f"cross_{meta['file_id'][:10]}.xlsx"
    if not fname.lower().endswith(".xlsx"):
        fname += ".xlsx"
    out = import_cross_workbook(
        db,
        content,
        fname,
        ejecutar_macheo=ejecutar_macheo,
    )
    out["url_origen"] = url.strip()
    out["tipo_drive"] = meta["tipo"]
    return out


def intentar_sync_drive(
    db: Session,
    *,
    ejecutar_macheo: bool = True,
) -> dict[str, Any]:
    """Descarga planillas públicas configuradas en CROSS_PLANILLAS_DRIVE."""
    resultados: list[dict[str, Any]] = []
    total_ins = total_upd = 0

    for cfg in CROSS_PLANILLAS_DRIVE:
        label = cfg.get("label") or cfg.get("sheet_id", "?")
        if not cfg.get("activo", True):
            resultados.append({"label": label, "ok": False, "motivo": "desactivada"})
            continue
        sid = cfg.get("sheet_id")
        if not sid:
            resultados.append({"label": label, "ok": False, "motivo": "sin sheet_id"})
            continue
        gid = str(cfg.get("gid") or "0")
        meta = {"tipo": "sheet", "sheet_id": str(sid), "gid": gid}
        export_url = export_url_google(meta)
        try:
            r = httpx.get(export_url, follow_redirects=True, timeout=120)
            ct = (r.headers.get("content-type") or "").lower()
            if r.status_code != 200 or "html" in ct[:20] or len(r.content) < 5000:
                resultados.append(
                    {
                        "label": label,
                        "ok": False,
                        "motivo": f"HTTP {r.status_code} — permiso o URL inválida",
                    }
                )
                continue
            fname = cfg.get("filename") or f"cross_{label}.xlsx"
            out = import_cross_workbook(
                db,
                r.content,
                fname,
                ejecutar_macheo=False,
            )
            total_ins += int(out.get("insertados") or 0)
            total_upd += int(out.get("actualizados") or 0)
            resultados.append({"label": label, "ok": True, **out})
        except Exception as exc:
            resultados.append({"label": label, "ok": False, "motivo": str(exc)})

    macheo = ejecutar_macheo_cross(db) if ejecutar_macheo and (total_ins or total_upd) else None
    return {
        "resultados": resultados,
        "insertados": total_ins,
        "actualizados": total_upd,
        "macheo": macheo,
        "message": (
            f"Drive: {sum(1 for x in resultados if x.get('ok'))}/{len(resultados)} planillas OK · "
            f"{total_ins} nuevos · {total_upd} actualizados"
        ),
    }


def listar_registros_cross(
    db: Session,
    *,
    limit: int = 200,
    solo_maestro: bool = False,
) -> list[dict[str, Any]]:
    q = select(CrossSeguimiento).order_by(CrossSeguimiento.updated_at.desc()).limit(limit)
    if solo_maestro:
        q = q.where(CrossSeguimiento.match_estado == "en_maestro")
    return [_cross_a_dict(r) for r in db.scalars(q).all()]
