from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(255))
    source: Mapped[str] = mapped_column(String(40), default="tango")
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    rows_in_file: Mapped[int] = mapped_column(Integer, default=0)
    rows_inserted: Mapped[int] = mapped_column(Integer, default=0)
    rows_skipped: Mapped[int] = mapped_column(Integer, default=0)


class Envio(Base):
    """Renglón de pedido importado desde Tango (Exportacion.xlsx)."""

    __tablename__ = "envios"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_envio_fingerprint"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    import_batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    remito: Mapped[str | None] = mapped_column(String(50), index=True)
    remito_norm: Mapped[str | None] = mapped_column(String(40), index=True)
    nro_pedido: Mapped[str | None] = mapped_column(String(50), index=True)
    cod_articulo: Mapped[str | None] = mapped_column(String(80))
    descripcion: Mapped[str | None] = mapped_column(Text)
    cantidad: Mapped[float | None] = mapped_column(Float)
    fecha_pedido: Mapped[str | None] = mapped_column(String(30))
    fecha_entrega: Mapped[str | None] = mapped_column(String(30))
    fecha_pedido_d: Mapped[date | None] = mapped_column(Date, index=True)
    fecha_entrega_d: Mapped[date | None] = mapped_column(Date, index=True)
    razon_social: Mapped[str | None] = mapped_column(String(200))
    domicilio: Mapped[str | None] = mapped_column(String(300))
    localidad: Mapped[str | None] = mapped_column(String(120), index=True)
    provincia: Mapped[str | None] = mapped_column(String(80), index=True)
    cp: Mapped[str | None] = mapped_column(String(20))
    deposito: Mapped[str | None] = mapped_column(String(20))
    origen_cd: Mapped[str | None] = mapped_column(String(40))
    transporte_cod: Mapped[str | None] = mapped_column(String(20))
    transporte_nombre: Mapped[str | None] = mapped_column(String(120))
    clasificacion: Mapped[str | None] = mapped_column(String(80))
    estado_pedido: Mapped[str | None] = mapped_column(String(40))
    leyenda_5: Mapped[str | None] = mapped_column(Text)
    vendedor: Mapped[str | None] = mapped_column(String(120))
    m3: Mapped[float | None] = mapped_column(Float)

    observaciones: Mapped[str | None] = mapped_column(Text)
    costo_total: Mapped[float | None] = mapped_column(Float)
    costo_tarifario: Mapped[float | None] = mapped_column(Float)
    diferencia: Mapped[float | None] = mapped_column(Float)
    sucursal_cc: Mapped[str | None] = mapped_column(String(80))
    prefactura_proveedor: Mapped[float | None] = mapped_column(Float)

    excluir_planilla: Mapped[bool] = mapped_column(default=False)
    alerta_clickpack: Mapped[bool] = mapped_column(default=False)
    abona_wamaro: Mapped[bool] = mapped_column(default=False)
    entrega_cliente_sospechosa: Mapped[bool] = mapped_column(default=False)
    regla_color: Mapped[str | None] = mapped_column(String(20))
    regla_motivo: Mapped[str | None] = mapped_column(String(255))

    macheo_estado: Mapped[str | None] = mapped_column(String(30))
    prefactura_clickpac_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    postventa_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tipo_gestion: Mapped[str | None] = mapped_column(String(80))
    sub_tipo_gestion: Mapped[str | None] = mapped_column(String(80))
    motivo_postventa: Mapped[str | None] = mapped_column(String(120))
    regla_postventa: Mapped[str | None] = mapped_column(String(80))

    proveedor_tarifa: Mapped[str | None] = mapped_column(String(40), index=True)
    proveedores_candidatos: Mapped[str | None] = mapped_column(Text)
    requiere_elegir_proveedor: Mapped[bool] = mapped_column(default=False)
    cedol_codigo: Mapped[str | None] = mapped_column(String(8))
    cedol_manual: Mapped[bool] = mapped_column(default=False)

    raw_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class PrefacturaClickpac(Base):
    """Reporte diario Clickpack (lo facturado el día anterior)."""

    __tablename__ = "prefacturas_clickpac"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_prefactura_fp"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    import_batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    remito: Mapped[str | None] = mapped_column(String(50))
    remito_norm: Mapped[str | None] = mapped_column(String(40), index=True)
    fecha_reporte: Mapped[str | None] = mapped_column(String(30))
    importe: Mapped[float] = mapped_column(Float)
    provincia: Mapped[str | None] = mapped_column(String(80))
    localidad: Mapped[str | None] = mapped_column(String(120))
    cliente: Mapped[str | None] = mapped_column(String(200))
    macheo_estado: Mapped[str | None] = mapped_column(String(30), default="pendiente")
    raw_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PostventaRegistro(Base):
    """Grilla de postventa (mail)."""

    __tablename__ = "postventa_registros"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_postventa_fp"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    import_batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    remito: Mapped[str | None] = mapped_column(String(50))
    remito_norm: Mapped[str | None] = mapped_column(String(40), index=True)
    motivo: Mapped[str | None] = mapped_column(String(255))
    tipo_gestion: Mapped[str | None] = mapped_column(String(80))
    fecha: Mapped[str | None] = mapped_column(String(30))
    regla_aplicada: Mapped[str | None] = mapped_column(String(80))
    raw_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class LiquidacionLinea(Base):
    """Liquidación oficial quincenal Clickpack."""

    __tablename__ = "liquidacion_lineas"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_liquidacion_fp"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    import_batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    periodo: Mapped[str | None] = mapped_column(String(40))
    remito: Mapped[str | None] = mapped_column(String(50))
    remito_norm: Mapped[str | None] = mapped_column(String(40), index=True)
    importe_liquidacion: Mapped[float] = mapped_column(Float)
    macheo_estado: Mapped[str | None] = mapped_column(String(30), default="pendiente")
    raw_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class FleteDistancia(Base):
    """Km y zona calculados sucursal → domicilio (cache por remito y domicilio)."""

    __tablename__ = "flete_distancias"

    remito_norm: Mapped[str] = mapped_column(String(40), primary_key=True)
    domicilio_fp: Mapped[str | None] = mapped_column(String(64), index=True)
    sucursal_cod: Mapped[str | None] = mapped_column(String(8), index=True)
    distance_km: Mapped[float | None] = mapped_column(Float)
    zona_km: Mapped[str | None] = mapped_column(String(24))
    km_provider: Mapped[str | None] = mapped_column(String(20))
    destino_query: Mapped[str | None] = mapped_column(String(500))
    dest_lat: Mapped[float | None] = mapped_column(Float)
    dest_lon: Mapped[float | None] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Transporte(Base):
    """Catálogo Tango COD_GVA24 — códigos en uso habitual (data/transportes.json)."""

    __tablename__ = "transportes"

    codigo: Mapped[str] = mapped_column(String(20), primary_key=True)
    descripcion: Mapped[str] = mapped_column(String(200))
    en_uso: Mapped[bool] = mapped_column(default=True)
    tipo: Mapped[str | None] = mapped_column(String(40))
    zona: Mapped[str | None] = mapped_column(String(40))
    proveedor: Mapped[str | None] = mapped_column(String(40))
    modo: Mapped[str | None] = mapped_column(String(40))
    excluir_planilla: Mapped[bool] = mapped_column(default=False)
    sin_flete_domicilio: Mapped[bool] = mapped_column(default=False)
    es_canal_clicpaq: Mapped[bool] = mapped_column(default=False)
    alerta_uso: Mapped[bool] = mapped_column(default=False)
    notas: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class Sucursal(Base):
    """Sucursales SommierCenter (códigos AV, BE, CA… del tablero Tango)."""

    __tablename__ = "sucursales"

    codigo: Mapped[str] = mapped_column(String(8), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    direccion: Mapped[str | None] = mapped_column(String(300))
    localidad: Mapped[str | None] = mapped_column(String(300))
    provincia: Mapped[str | None] = mapped_column(String(80))
    zona: Mapped[str | None] = mapped_column(String(20), index=True)
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    activa: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class TarifarioVersion(Base):
    """Versión de tarifario por proveedor (borrador → activa → histórica)."""

    __tablename__ = "tarifario_versiones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    proveedor: Mapped[str] = mapped_column(String(40), index=True)
    vigencia_desde: Mapped[str | None] = mapped_column(String(20))
    vigencia_hasta: Mapped[str | None] = mapped_column(String(20))
    estado: Mapped[str] = mapped_column(String(20), index=True, default="borrador")
    archivo_origen: Mapped[str | None] = mapped_column(String(255))
    hoja_origen: Mapped[str | None] = mapped_column(String(80))
    filas_count: Mapped[int] = mapped_column(Integer, default=0)
    notas: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Tarifa(Base):
    __tablename__ = "tarifas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_id: Mapped[int | None] = mapped_column(
        Integer, index=True, nullable=True
    )
    proveedor: Mapped[str] = mapped_column(String(80), index=True)
    provincia: Mapped[str] = mapped_column(String(80), index=True)
    localidad: Mapped[str] = mapped_column(String(120), index=True)
    tipo_producto: Mapped[str] = mapped_column(String(80))
    medida: Mapped[str] = mapped_column(String(40))
    precio: Mapped[float] = mapped_column(Float)
    cedol: Mapped[str | None] = mapped_column(String(40))
    vigencia_desde: Mapped[str | None] = mapped_column(String(20))
    vigencia_hasta: Mapped[str | None] = mapped_column(String(20))
    notas: Mapped[str | None] = mapped_column(Text)


class Fletero(Base):
    """Fletero local de confianza (entrega sucursal → domicilio)."""

    __tablename__ = "fleteros"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    nombre_corto: Mapped[str] = mapped_column(String(40), index=True)
    activo: Mapped[bool] = mapped_column(default=True)
    notas: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class FleteSolicitud(Base):
    """Registro del Excel Drive «Fletes solicitados sucursales»."""

    __tablename__ = "flete_solicitudes"
    __table_args__ = (
        UniqueConstraint("id_flete_externo", name="uq_flete_sol_ext"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_flete_externo: Mapped[str] = mapped_column(String(40), index=True)
    fletero_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    nro_pedido: Mapped[str | None] = mapped_column(String(50), index=True)
    nro_pedido_norm: Mapped[str | None] = mapped_column(String(50), index=True)
    remito_norm: Mapped[str | None] = mapped_column(String(40), index=True)
    local_compra: Mapped[str | None] = mapped_column(String(8))
    local_entrega: Mapped[str | None] = mapped_column(String(8))
    fecha_entrega: Mapped[str | None] = mapped_column(String(30))
    fecha_solicitado: Mapped[str | None] = mapped_column(String(30))
    estado: Mapped[str | None] = mapped_column(String(40))
    abona: Mapped[str | None] = mapped_column(String(40))
    motivo: Mapped[str | None] = mapped_column(String(120))
    direccion: Mapped[str | None] = mapped_column(String(400))
    importe_wamaro: Mapped[float | None] = mapped_column(Float)
    importe_cliente: Mapped[float | None] = mapped_column(Float)
    cliente: Mapped[str | None] = mapped_column(String(200))
    articulos_raw: Mapped[str | None] = mapped_column(Text)
    match_estado: Mapped[str | None] = mapped_column(String(30), default="pendiente")
    import_batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class CrossSeguimiento(Base):
    """Seguimiento operativo cross (pestaña Retirado por …) — revisión colaborativa, no factura."""

    __tablename__ = "cross_seguimiento"
    __table_args__ = (UniqueConstraint("remito_norm", name="uq_cross_seg_remito"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    remito_norm: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    remito: Mapped[str | None] = mapped_column(String(50))
    nro_pedido: Mapped[str | None] = mapped_column(String(50), index=True)
    proveedor: Mapped[str | None] = mapped_column(String(40), index=True)
    hoja_origen: Mapped[str | None] = mapped_column(String(120))
    archivo_origen: Mapped[str | None] = mapped_column(String(255))
    import_batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fecha_retiro: Mapped[str | None] = mapped_column(String(30))
    fecha_entrega_coord: Mapped[str | None] = mapped_column(String(30))
    entregado: Mapped[str | None] = mapped_column(String(30), index=True)
    observacion: Mapped[str | None] = mapped_column(Text)
    match_estado: Mapped[str | None] = mapped_column(String(30), default="pendiente", index=True)
    raw_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
