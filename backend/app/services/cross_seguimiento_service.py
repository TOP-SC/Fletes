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
                cod_cliente=row.get("cod_cliente"),
                importe_facturado=row.get("importe_facturado"),
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
    if row.get("cod_cliente"):
        existente.cod_cliente = row["cod_cliente"]
    if row.get("importe_facturado") is not None:
        existente.importe_facturado = row["importe_facturado"]
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
        "cod_cliente": reg.cod_cliente,
        "importe_facturado": reg.importe_facturado,
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

# Export anónimo (sin OAuth): Google exige «Cualquiera con el enlace → Lector».
_DRIVE_UA = (
    "Mozilla/5.0 (compatible; TOP-Fletes/1.0; +https://github.com/TOP-SC/Fletes) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_MIN_XLSX_BYTES = 3000


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


def _interpretar_respuesta_drive(r: httpx.Response) -> tuple[bool, str]:
    """True si parece un xlsx válido; si no, mensaje legible."""
    ct = (r.headers.get("content-type") or "").lower()
    body = r.content or b""
    if r.status_code == 401:
        return False, (
            "HTTP 401 — el servidor no puede leer el archivo. "
            "En Drive: Compartir → «Cualquiera con el enlace» → Lector "
            "(no alcanza compartir solo con mails @empresa)."
        )
    if r.status_code == 403:
        return False, "HTTP 403 — acceso denegado. Revisá permisos del archivo."
    if r.status_code == 404:
        return False, "HTTP 404 — ID de planilla incorrecto en config.py."
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}"
    if "html" in ct[:24] or body[:15].strip().lower().startswith(b"<!doctype"):
        return False, "Google devolvió HTML (login o permiso) en lugar del Excel."
    if len(body) < _MIN_XLSX_BYTES:
        return False, f"Archivo muy chico ({len(body)} bytes) — export vacío o pestaña gid incorrecta."
    if not body[:2] == b"PK":
        return False, "No es un .xlsx válido (falta firma ZIP/PK)."
    return True, "OK"


def descargar_bytes_drive(export_url: str, *, timeout: float = 180.0) -> tuple[bytes, str]:
    """GET anónimo a export de Drive/Sheets."""
    try:
        r = httpx.get(
            export_url,
            follow_redirects=True,
            timeout=timeout,
            headers={"User-Agent": _DRIVE_UA},
        )
    except httpx.TimeoutException as exc:
        raise ValueError(
            f"Timeout ({int(timeout)}s) — planilla muy pesada o red lenta. "
            "Probá de nuevo o importá el .xlsx manual."
        ) from exc
    ok, msg = _interpretar_respuesta_drive(r)
    if not ok:
        raise ValueError(msg)
    return r.content, msg


def probar_planilla_drive(cfg: dict[str, str | bool]) -> dict[str, Any]:
    """Solo verifica si el export anónimo funciona (sin importar)."""
    label = str(cfg.get("label") or cfg.get("sheet_id") or "?")
    if not cfg.get("activo", True):
        return {"label": label, "ok": False, "motivo": "desactivada en config"}
    sid = cfg.get("sheet_id")
    if not sid:
        return {"label": label, "ok": False, "motivo": "sin sheet_id"}
    gid = str(cfg.get("gid") or "0")
    meta = {"tipo": "sheet", "sheet_id": str(sid), "gid": gid}
    export_url = export_url_google(meta)
    try:
        r = httpx.get(
            export_url,
            follow_redirects=True,
            timeout=90.0,
            headers={"User-Agent": _DRIVE_UA},
        )
        ok, msg = _interpretar_respuesta_drive(r)
        return {
            "label": label,
            "ok": ok,
            "motivo": msg,
            "sheet_id": str(sid),
            "gid": gid,
            "bytes": len(r.content) if ok else 0,
            "http_status": r.status_code,
        }
    except httpx.TimeoutException:
        return {"label": label, "ok": False, "motivo": "Timeout — archivo grande o red lenta", "sheet_id": str(sid)}
    except Exception as exc:
        return {"label": label, "ok": False, "motivo": str(exc), "sheet_id": str(sid)}


def listar_estado_planillas_drive() -> list[dict[str, Any]]:
    return [probar_planilla_drive(cfg) for cfg in CROSS_PLANILLAS_DRIVE]


def descargar_planilla_drive(url: str) -> tuple[bytes, dict[str, str]]:
    """Descarga bytes de una planilla compartida (Sheets o archivo Drive)."""
    meta = parse_google_drive_url(url)
    export_url = export_url_google(meta)
    content, _msg = descargar_bytes_drive(export_url)
    return content, meta


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
            content, _msg = descargar_bytes_drive(export_url, timeout=180.0)
            fname = cfg.get("filename") or f"cross_{label}.xlsx"
            out = import_cross_workbook(
                db,
                content,
                fname,
                ejecutar_macheo=False,
            )
            total_ins += int(out.get("insertados") or 0)
            total_upd += int(out.get("actualizados") or 0)
            resultados.append({"label": label, "ok": True, **out})
        except Exception as exc:
            resultados.append({"label": label, "ok": False, "motivo": str(exc)})

    macheo = ejecutar_macheo_cross(db) if ejecutar_macheo else None
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


def export_cross_control_xlsx(
    db: Session,
    *,
    proveedor: str | None = None,
) -> bytes:
    """
    Planilla de control Alfaro/Fransof: cross + datos maestro
    (costo control, facturado, dif, suc, COD CLIENTE).
    """
    from io import BytesIO

    import pandas as pd
    from openpyxl.styles import Font, PatternFill

    from app.services.money_utils import EXCEL_NUM_FMT_PESOS, aplicar_formato_moneda_hoja
    from app.services.rules_service import resolver_sucursal_cc

    q = select(CrossSeguimiento).order_by(CrossSeguimiento.remito)
    if proveedor:
        q = q.where(CrossSeguimiento.proveedor == proveedor.upper())
    regs = list(db.scalars(q).all())

    # Índice maestro por remito_norm (una fila representativa)
    envios = list(
        db.scalars(
            select(Envio).where(
                Envio.remito_norm.isnot(None),
                Envio.remito_norm != "",
            )
        ).all()
    )
    by_norm: dict[str, list[Envio]] = {}
    for e in envios:
        by_norm.setdefault(e.remito_norm or "", []).append(e)

    filas: list[dict[str, Any]] = []
    for reg in regs:
        grupo = by_norm.get(reg.remito_norm or "", [])
        base = grupo[0] if grupo else None
        costo_control = None
        if grupo:
            # max por remito (mismo criterio que exports provincia)
            costo_control = max(float(e.costo_tarifario or 0) for e in grupo)
        prec_neto = None
        if grupo:
            for e in grupo:
                if e.prefactura_proveedor is not None:
                    prec_neto = float(e.prefactura_proveedor)
                    break
        facturado = reg.importe_facturado
        if facturado is None and prec_neto is not None:
            facturado = prec_neto
        control = round(costo_control, 2) if costo_control else None
        dif = None
        if facturado is not None and control is not None:
            dif = round(float(facturado) - float(control), 2)

        suc = ""
        cod_cli = reg.cod_cliente or ""
        if base:
            suc = resolver_sucursal_cc(base) or base.sucursal_cc or ""
            if not cod_cli:
                cod_cli = base.cod_cliente or ""

        filas.append(
            {
                "remito": reg.remito,
                "proveedor": reg.proveedor,
                "entregado": reg.entregado,
                "fecha_retiro": reg.fecha_retiro,
                "fecha_entrega_coord": reg.fecha_entrega_coord,
                "match_estado": reg.match_estado,
                "nro_pedido": reg.nro_pedido or (base.nro_pedido if base else None),
                "COD CLIENTE": cod_cli,
                "suc": suc,
                "destinatario": base.razon_social if base else None,
                "localidad": base.localidad if base else None,
                "provincia": base.provincia if base else None,
                "facturado": facturado,
                "control": control,
                "dif": dif,
                "observacion": reg.observacion,
                "archivo_origen": reg.archivo_origen,
                "hoja_origen": reg.hoja_origen,
            }
        )

    buf = BytesIO()
    df = pd.DataFrame(filas)
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Control cross")
        ws = writer.sheets["Control cross"]
        fill = PatternFill(start_color="D9E2F3", end_color="D9E2F3", fill_type="solid")
        font = Font(bold=True, color="1F4E79")
        for col in range(1, len(df.columns) + 1):
            cell = ws.cell(1, col)
            cell.fill = fill
            cell.font = font
        aplicar_formato_moneda_hoja(ws, list(df.columns))
        # Colorear entregado pendiente/NO
        for r_idx, row in enumerate(filas, start=2):
            ent = (row.get("entregado") or "").upper()
            cell = ws.cell(r_idx, list(df.columns).index("entregado") + 1)
            if ent == "NO":
                cell.fill = PatternFill(
                    start_color="FFCDD2", end_color="FFCDD2", fill_type="solid"
                )
            elif ent == "PENDIENTE":
                cell.fill = PatternFill(
                    start_color="FFF9C4", end_color="FFF9C4", fill_type="solid"
                )
    buf.seek(0)
    return buf.getvalue()
