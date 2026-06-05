from datetime import datetime

from pydantic import BaseModel


class ImportResult(BaseModel):
    batch_id: int
    filename: str
    rows_in_file: int
    rows_inserted: int
    rows_skipped: int
    rows_rejected: int = 0
    message: str


class EnvioOut(BaseModel):
    id: int
    remito: str | None
    remito_norm: str | None = None
    nro_pedido: str | None
    cod_articulo: str | None
    descripcion: str | None
    cantidad: float | None
    fecha_pedido: str | None
    fecha_entrega: str | None
    razon_social: str | None
    localidad: str | None
    provincia: str | None
    transporte_nombre: str | None
    clasificacion: str | None
    origen_cd: str | None = None
    observaciones: str | None
    costo_total: float | None
    costo_tarifario: float | None
    diferencia: float | None
    sucursal_cc: str | None
    prefactura_proveedor: float | None
    excluir_planilla: bool
    alerta_clickpack: bool
    abona_wamaro: bool
    entrega_cliente_sospechosa: bool = False
    macheo_estado: str | None = None
    motivo_postventa: str | None = None
    regla_postventa: str | None = None
    regla_color: str | None
    regla_motivo: str | None

    model_config = {"from_attributes": True}


class EnvioUpdate(BaseModel):
    observaciones: str | None = None
    costo_total: float | None = None
    prefactura_proveedor: float | None = None
    sucursal_cc: str | None = None


class TarifaIn(BaseModel):
    proveedor: str
    provincia: str
    localidad: str
    tipo_producto: str = ""
    medida: str = ""
    precio: float
    cedol: str | None = None
    vigencia_desde: str | None = None
    vigencia_hasta: str | None = None
    notas: str | None = None


class TarifaOut(TarifaIn):
    id: int
    version_id: int | None = None

    model_config = {"from_attributes": True}


class TarifarioVersionOut(BaseModel):
    id: int
    proveedor: str
    estado: str
    vigencia_desde: str | None = None
    vigencia_hasta: str | None = None
    archivo_origen: str | None = None
    hoja_origen: str | None = None
    filas_count: int = 0
    created_at: str | None = None
    activated_at: str | None = None
    notas: str | None = None


class DashboardStats(BaseModel):
    total_envios: int
    excluidos: int
    alertas_clickpack: int
    abona_wamaro: int
    ultimo_import: datetime | None
    import_batches: int


class ProveedoresReaplicarStats(BaseModel):
    procesados: int = 0
    asignados: int = 0
    pendientes_elegir: int = 0
    sin_tarifa: int = 0
    crossdock: int = 0


class CobroPedidosReaplicarStats(BaseModel):
    pedidos: int = 0
    con_tarifa: int = 0
    sin_tarifa: int = 0


class ReaplicarReglasOut(BaseModel):
    procesados: int
    remitos_corregidos: int = 0
    proveedores: ProveedoresReaplicarStats
    cobro_pedidos: CobroPedidosReaplicarStats | None = None


class Mundo1Stats(BaseModel):
    envios_interior: int
    prefacturas_clickpack: int
    postventa_registros: int
    liquidacion_lineas: int
    macheo_matcheados: int
    macheo_conjuntos: int
    pendientes_sin_prefactura: int
    con_diferencia: int
    sin_datos_tango: int = 0
    con_tarifa: int = 0
    por_color: dict[str, int] = {}
