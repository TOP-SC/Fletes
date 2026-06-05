from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ImportBatch, LiquidacionLinea, PostventaRegistro, PrefacturaClickpac
from app.services.clickpack_parser import parse_clickpack_prefactura
from app.services.liquidacion_parser import parse_liquidacion_excel
from app.services.postventa_parser import parse_postventa_excel


def _import_rows(
    db: Session,
    filename: str,
    source: str,
    rows: list[dict],
    model,
    existing_fps: set[str],
) -> ImportBatch:
    batch = ImportBatch(
        filename=filename,
        source=source,
        rows_in_file=len(rows),
        rows_inserted=0,
        rows_skipped=0,
    )
    db.add(batch)
    db.flush()

    for row in rows:
        fp = row["fingerprint"]
        if fp in existing_fps:
            batch.rows_skipped += 1
            continue
        payload = {k: v for k, v in row.items() if k != "fingerprint"}
        obj = model(import_batch_id=batch.id, fingerprint=fp, **payload)
        db.add(obj)
        existing_fps.add(fp)
        batch.rows_inserted += 1

    db.commit()
    db.refresh(batch)
    return batch


def import_prefactura_clickpack(db: Session, content: bytes, filename: str) -> ImportBatch:
    rows = parse_clickpack_prefactura(content)
    existing = set(db.scalars(select(PrefacturaClickpac.fingerprint)).all())
    return _import_rows(db, filename, "clickpack", rows, PrefacturaClickpac, existing)


def import_postventa(db: Session, content: bytes, filename: str) -> ImportBatch:
    rows = parse_postventa_excel(content)
    existing = set(db.scalars(select(PostventaRegistro.fingerprint)).all())
    return _import_rows(db, filename, "postventa", rows, PostventaRegistro, existing)


def import_liquidacion(db: Session, content: bytes, filename: str, periodo: str) -> ImportBatch:
    rows = parse_liquidacion_excel(content, periodo)
    existing = set(db.scalars(select(LiquidacionLinea.fingerprint)).all())
    return _import_rows(db, filename, "liquidacion", rows, LiquidacionLinea, existing)
