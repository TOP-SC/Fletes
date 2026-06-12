from collections import defaultdict

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Envio, ImportBatch, Tarifa
from app.services.excel_parser import fila_es_valida, parse_exportacion_excel
from app.services.fingerprint import build_fingerprint, row_to_json
from app.services.postventa_rules import aplicar_postventa_desde_tango
from app.services.remito_repair import (
    corregir_remito_envio,
    corregir_remito_fila,
    propagar_remitos_cd,
)
from app.services.remito_utils import normalizar_remito
from app.labels import MOTIVO_FALTA_PREF, MOTIVO_TARIFA_SIN_PREF
from app.services.cobro_logistica_service import aplicar_cobro_todos_envios
from app.services.costo_conceptos import es_retiro_sin_flete_domicilio
from app.services.fecha_utils import parse_fecha_tango
from app.services.proveedor_service import procesar_proveedores_envios
from app.services.rules_service import (
    aplicar_reglas_envio,
    recalcular_grupo,
)


def limpiar_campos_tarifarios_envios(envios: list[Envio]) -> int:
    """
    Borra proveedor y costos calculados antes de reaplicar (evita datos viejos
    p. ej. CLICPAQ en envíos AMBA/GBA).
    """
    n = 0
    for envio in envios:
        envio.proveedor_tarifa = None
        envio.proveedores_candidatos = None
        envio.requiere_elegir_proveedor = False
        envio.costo_tarifario = None
        envio.costo_total = None
        envio.diferencia = None
        n += 1
    return n


def reaplicar_todos_envios(db: Session) -> dict:
    """Limpia tarifas calculadas, reglas, proveedor, costo proveedor y macheo."""
    envios = list(db.scalars(select(Envio)).all())
    from app.services.tarifario_version_service import TarifarioContext

    tarifario_ctx = TarifarioContext(db)

    limpiados = limpiar_campos_tarifarios_envios(envios)

    remitos_corregidos = 0
    for envio in envios:
        if corregir_remito_envio(envio):
            remitos_corregidos += 1
        envio.remito_norm = normalizar_remito(envio.remito)
    remitos_corregidos += propagar_remitos_cd(envios)
    for envio in envios:
        envio.remito_norm = normalizar_remito(envio.remito)
        aplicar_reglas_envio(envio, preservar_postventa=bool(envio.regla_postventa))
        if not envio.regla_postventa:
            aplicar_postventa_desde_tango(envio)

    prov_stats = procesar_proveedores_envios(envios, tarifario_ctx=tarifario_ctx)
    cobro_stats = aplicar_cobro_todos_envios(
        envios, db=db, tarifario_ctx=tarifario_ctx
    )

    for envio in envios:
        _finalizar_color_interior(envio)

    idx: dict[str, list[Envio]] = defaultdict(list)
    for e in envios:
        if not e.excluir_planilla and e.remito_norm:
            idx[e.remito_norm].append(e)
    for grupo in idx.values():
        if grupo[0].prefactura_proveedor is not None:
            recalcular_grupo(grupo)

    db.commit()
    return {
        "procesados": len(envios),
        "limpiados": limpiados,
        "remitos_corregidos": remitos_corregidos,
        "proveedores": prov_stats,
        "cobro_pedidos": cobro_stats,
    }


def reaplicar_envios_post_import(db: Session, batch_id: int) -> dict:
    """
    Reaplica reglas/cobro solo al lote nuevo y pedidos/remitos relacionados
    (mucho más rápido que reaplicar_todos_envios con 3 meses de Tango).
    """
    nuevos = list(
        db.scalars(select(Envio).where(Envio.import_batch_id == batch_id)).all()
    )
    if not nuevos:
        return {"procesados": 0, "batch_id": batch_id}

    pedidos = {e.nro_pedido for e in nuevos if e.nro_pedido}
    remitos = {e.remito_norm for e in nuevos if e.remito_norm}
    ids: set[int] = {e.id for e in nuevos}

    if pedidos:
        for e in db.scalars(select(Envio).where(Envio.nro_pedido.in_(pedidos))).all():
            ids.add(e.id)
    if remitos:
        for e in db.scalars(select(Envio).where(Envio.remito_norm.in_(remitos))).all():
            ids.add(e.id)

    envios = list(db.scalars(select(Envio).where(Envio.id.in_(ids))).all())
    from app.services.tarifario_version_service import TarifarioContext

    tarifario_ctx = TarifarioContext(db)
    limpiados = limpiar_campos_tarifarios_envios(envios)
    remitos_corregidos = 0
    for envio in envios:
        if corregir_remito_envio(envio):
            remitos_corregidos += 1
        envio.remito_norm = normalizar_remito(envio.remito)
    remitos_corregidos += propagar_remitos_cd(envios)
    for envio in envios:
        envio.remito_norm = normalizar_remito(envio.remito)
        aplicar_reglas_envio(envio, preservar_postventa=bool(envio.regla_postventa))
        if not envio.regla_postventa:
            aplicar_postventa_desde_tango(envio)

    prov_stats = procesar_proveedores_envios(envios, tarifario_ctx=tarifario_ctx)
    cobro_stats = aplicar_cobro_todos_envios(
        envios, db=db, tarifario_ctx=tarifario_ctx
    )
    for envio in envios:
        _finalizar_color_interior(envio)

    idx: dict[str, list[Envio]] = defaultdict(list)
    for e in envios:
        if not e.excluir_planilla and e.remito_norm:
            idx[e.remito_norm].append(e)
    for grupo in idx.values():
        if grupo[0].prefactura_proveedor is not None:
            recalcular_grupo(grupo)

    db.commit()
    return {
        "procesados": len(envios),
        "batch_id": batch_id,
        "nuevos_lote": len(nuevos),
        "limpiados": limpiados,
        "remitos_corregidos": remitos_corregidos,
        "proveedores": prov_stats,
        "cobro_pedidos": cobro_stats,
    }


def _finalizar_color_interior(envio: Envio) -> None:
    """Color por defecto para interior sin otra regla explícita."""
    if envio.regla_postventa:
        return
    if envio.excluir_planilla and envio.regla_color:
        if envio.costo_tarifario and envio.costo_tarifario > 0:
            return
        if es_retiro_sin_flete_domicilio(envio):
            return
    if not envio.costo_tarifario and not envio.proveedor_tarifa:
        envio.regla_color = "amarillo"
        envio.regla_motivo = "Sin tarifa en tarifario para este destino/artículo"
        return
    if envio.costo_tarifario and envio.costo_tarifario > 0:
        envio.regla_color = "verde"
        envio.regla_motivo = MOTIVO_TARIFA_SIN_PREF
    elif envio.alerta_clickpack:
        envio.macheo_estado = envio.macheo_estado or "pendiente_clickpack"
        envio.regla_color = "amarillo"
        envio.regla_motivo = MOTIVO_FALTA_PREF
    else:
        envio.regla_color = "amarillo"
        envio.regla_motivo = "Interior — revisar tarifa o datos Tango"


_IMPORT_FLUSH_EVERY = 400


def import_excel_file(
    db: Session,
    content: bytes,
    filename: str,
    *,
    proveedor_tarifa: str = "CLICKPAC",
    recalc_tarifas: bool = True,
    defer_recalc: bool = False,
) -> tuple[ImportBatch, int]:
    rows = parse_exportacion_excel(content)
    batch = ImportBatch(
        filename=filename,
        source="tango",
        rows_in_file=len(rows),
        rows_inserted=0,
        rows_skipped=0,
    )
    db.add(batch)
    db.flush()

    existing = set(db.scalars(select(Envio.fingerprint)).all())
    rows_rejected = 0
    pending_flush = 0

    for row in rows:
        if not fila_es_valida(row):
            rows_rejected += 1
            continue

        fp = build_fingerprint(row)
        if fp in existing:
            batch.rows_skipped += 1
            continue

        if row.get("nro_pedido") and row.get("remito") == row.get("nro_pedido"):
            row["remito"] = None
        corregir_remito_fila(row)
        envio = Envio(
            fingerprint=fp,
            import_batch_id=batch.id,
            remito=row.get("remito"),
            nro_pedido=row.get("nro_pedido"),
            cod_articulo=row.get("cod_articulo"),
            descripcion=row.get("descripcion"),
            cantidad=row.get("cantidad"),
            fecha_pedido=row.get("fecha_pedido"),
            fecha_entrega=row.get("fecha_entrega"),
            fecha_pedido_d=parse_fecha_tango(row.get("fecha_pedido")),
            fecha_entrega_d=parse_fecha_tango(row.get("fecha_entrega")),
            razon_social=row.get("razon_social"),
            domicilio=row.get("domicilio"),
            localidad=row.get("localidad"),
            provincia=row.get("provincia"),
            cp=row.get("cp"),
            deposito=row.get("deposito"),
            transporte_cod=row.get("transporte_cod"),
            transporte_nombre=row.get("transporte_nombre"),
            clasificacion=row.get("clasificacion"),
            estado_pedido=row.get("estado_pedido"),
            leyenda_5=row.get("leyenda_5"),
            vendedor=row.get("vendedor"),
            m3=row.get("m3"),
            tipo_gestion=row.get("tipo_gestion"),
            sub_tipo_gestion=row.get("sub_tipo"),
            raw_json=row_to_json(row),
        )
        aplicar_reglas_envio(envio)
        aplicar_postventa_desde_tango(envio)

        db.add(envio)
        existing.add(fp)
        batch.rows_inserted += 1
        pending_flush += 1
        if pending_flush >= _IMPORT_FLUSH_EVERY:
            db.flush()
            pending_flush = 0

    db.commit()

    if batch.rows_inserted and recalc_tarifas and not defer_recalc:
        reaplicar_envios_post_import(db, batch.id)

    db.refresh(batch)
    return batch, rows_rejected


def revertir_import_batch(db: Session, batch_id: int) -> dict[str, int]:
    """Elimina envíos de un lote erróneo para poder reimportar."""
    n = db.scalar(
        select(Envio.id).where(Envio.import_batch_id == batch_id).limit(1)
    )
    if n is None:
        batch = db.get(ImportBatch, batch_id)
        if batch:
            db.delete(batch)
            db.commit()
        return {"envios_eliminados": 0}

    result = db.execute(delete(Envio).where(Envio.import_batch_id == batch_id))
    db.execute(delete(ImportBatch).where(ImportBatch.id == batch_id))
    db.commit()
    return {"envios_eliminados": result.rowcount or 0}
