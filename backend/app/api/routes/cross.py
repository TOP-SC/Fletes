from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.cross_seguimiento_service import (
    actualizar_planillas_drive_a_inbox,
    ejecutar_macheo_cross,
    estado_planillas_cross,
    export_cross_control_xlsx,
    guardar_ultimo_resultado_cross,
    import_cross_workbook,
    importar_carpeta_cross,
    listar_inbox_cross,
    listar_registros_cross,
    resumen_cross,
)
from app.services.google_drive_auth import drive_auth_status

router = APIRouter(prefix="/cross", tags=["cross"])


@router.get("/resumen")
def cross_resumen(db: Session = Depends(get_db)) -> dict:
    return resumen_cross(db)


@router.get("/inbox")
def cross_inbox() -> dict:
    """Lista .xlsx en data/cross_inbox del servidor."""
    return listar_inbox_cross()


@router.get("/estado-planillas")
def cross_estado_planillas() -> dict:
    """Estado verde/rojo/gris de las 5 planillas + último macheo."""
    return estado_planillas_cross()


@router.get("/drive-auth")
def cross_drive_auth() -> dict:
    """Estado OAuth / service account para bajar planillas del grupo SommierCenter."""
    return drive_auth_status()


@router.post("/import-carpeta")
def cross_import_carpeta(
    matchear: bool = Query(True),
    mover: bool = Query(True),
    db: Session = Depends(get_db),
) -> dict:
    """Importa todos los Excel depositados en data/cross_inbox."""
    return importar_carpeta_cross(
        db, ejecutar_macheo=matchear, mover_procesados=mover
    )


@router.post("/actualizar-desde-drive")
def cross_actualizar_desde_drive(
    importar: bool = Query(
        True,
        description="Tras bajar a inbox, importar y machear",
    ),
    matchear: bool = Query(True),
    db: Session = Depends(get_db),
) -> dict:
    """
    Copia las planillas Cross conocidas (Drive) a data/cross_inbox.
    Por defecto también importa y machea con el maestro.
    """
    return actualizar_planillas_drive_a_inbox(
        importar=importar, matchear=matchear, db=db
    )


@router.get("/registros")
def cross_registros(
    limit: int = Query(200, ge=1, le=2000),
    solo_maestro: bool = Query(False),
    db: Session = Depends(get_db),
) -> list[dict]:
    return listar_registros_cross(db, limit=limit, solo_maestro=solo_maestro)


@router.get("/export")
def cross_export(
    proveedor: str | None = Query(None),
    db: Session = Depends(get_db),
) -> Response:
    """Excel de control: cross + costo control / facturado / dif / suc / COD CLIENTE."""
    data = export_cross_control_xlsx(db, proveedor=proveedor)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="control_cross_alfaro.xlsx"'
        },
    )


@router.post("/import")
async def cross_importar(
    file: UploadFile = File(...),
    matchear: bool = Query(True),
    db: Session = Depends(get_db),
) -> dict:
    content = await file.read()
    return import_cross_workbook(
        db,
        content,
        file.filename or "cross.xlsx",
        ejecutar_macheo=matchear,
    )


@router.post("/import-varios")
async def cross_import_varios(
    files: list[UploadFile] = File(...),
    matchear: bool = Query(True),
    db: Session = Depends(get_db),
) -> dict:
    """
    Subí Cross 3/4 (u otras) bajadas del navegador.
    No requiere cambiar permisos Drive ni proyecto Google Cloud.
    """
    from app.config import CROSS_INBOX_DIR
    from app.services.cross_seguimiento_service import (
        guardar_ultimo_resultado_cross,
        leer_ultimo_resultado_cross,
    )

    CROSS_INBOX_DIR.mkdir(parents=True, exist_ok=True)
    guardados: list[dict] = []
    for up in files:
        raw = await up.read()
        name = (up.filename or "cross.xlsx").strip()
        if not name.lower().endswith(".xlsx"):
            name += ".xlsx"
        low = name.lower()
        if "cordoba" in low or "córdoba" in low or "cross_4" in low or "cross 4" in low:
            name = "cross_4.xlsx"
        elif (
            ("jujuy" in low or "tucuman" in low or "tucumán" in low)
            or "cross_3" in low
            or "cross 3" in low
            or ("salta" in low and "alfaro" in low)
        ):
            name = "cross_3.xlsx"
        dest = CROSS_INBOX_DIR / name
        dest.write_bytes(raw)
        guardados.append({"nombre": name, "bytes": len(raw)})

    out = importar_carpeta_cross(db, ejecutar_macheo=matchear, mover_procesados=True)
    prev = leer_ultimo_resultado_cross() or {}
    guardar_ultimo_resultado_cross(
        {
            "accion": "Upload Excel locales + machear",
            "descargas": prev.get("descargas") or [],
            "importacion": out,
            "macheo": out.get("macheo"),
            "message": (
                f"Subidos {len(guardados)} archivo(s). " + (out.get("message") or "")
            ),
            "archivos_subidos": guardados,
        }
    )
    out["archivos_subidos"] = guardados
    return out


@router.post("/depositar")
async def cross_depositar(
    archivo: str = Query(..., description="Nombre canónico ej. cross_3.xlsx"),
    file: UploadFile = File(...),
    matchear: bool = Query(True),
    db: Session = Depends(get_db),
) -> dict:
    """Deposita un Excel para una planilla concreta (la que está en rojo) e importa."""
    from app.config import CROSS_INBOX_DIR, CROSS_PLANILLAS_DRIVE
    from app.services.cross_seguimiento_service import (
        guardar_ultimo_resultado_cross,
        leer_ultimo_resultado_cross,
    )

    allowed = {str(c.get("filename")) for c in CROSS_PLANILLAS_DRIVE}
    name = (archivo or "").strip()
    if name not in allowed:
        raise HTTPException(400, f"Archivo no reconocido: {name}")
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Archivo vacío")
    CROSS_INBOX_DIR.mkdir(parents=True, exist_ok=True)
    (CROSS_INBOX_DIR / name).write_bytes(raw)

    # Marcar esa planilla como OK en el último resultado (depositado a mano)
    prev = leer_ultimo_resultado_cross() or {}
    descargas = list(prev.get("descargas") or [])
    label = next(
        (
            str(c.get("label"))
            for c in CROSS_PLANILLAS_DRIVE
            if str(c.get("filename")) == name
        ),
        name,
    )
    found = False
    for d in descargas:
        if d.get("archivo") == name or d.get("label") == label:
            d["ok"] = True
            d["archivo"] = name
            d["label"] = label
            d["bytes"] = len(raw)
            d["origen"] = "depositado_manual"
            d.pop("motivo", None)
            found = True
            break
    if not found:
        descargas.append(
            {
                "label": label,
                "ok": True,
                "archivo": name,
                "bytes": len(raw),
                "origen": "depositado_manual",
            }
        )

    out = importar_carpeta_cross(db, ejecutar_macheo=matchear, mover_procesados=True)
    guardar_ultimo_resultado_cross(
        {
            "accion": f"Depositar {label}",
            "descargas": descargas,
            "importacion": out,
            "macheo": out.get("macheo"),
            "message": f"Depositado {name}. " + (out.get("message") or ""),
        }
    )
    out["depositado"] = {"label": label, "archivo": name, "bytes": len(raw)}
    return out


@router.post("/matchear")
def cross_matchear(db: Session = Depends(get_db)) -> dict:
    from app.services.cross_seguimiento_service import leer_ultimo_resultado_cross

    m = ejecutar_macheo_cross(db)
    prev = leer_ultimo_resultado_cross() or {}
    guardar_ultimo_resultado_cross(
        {
            "accion": "Solo machear",
            "descargas": prev.get("descargas") or [],
            "importacion": prev.get("importacion"),
            "macheo": m,
            "message": (
                f"Macheo: {m.get('en_maestro', 0)} en maestro · "
                f"{m.get('sin_maestro', 0)} solo planilla"
            ),
        }
    )
    return m
