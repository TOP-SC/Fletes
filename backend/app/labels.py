"""Textos de negocio visibles al usuario (reglas, colores, acciones)."""

# Leyenda de colores (grilla)
COLOR_LEYENDA: dict[str, str] = {
    "amarillo": "Pendiente — tarifa o prefactura",
    "verde": "OK — prefactura conciliada",
    "rojo": "Diferencia / no paga",
    "gris": "Amba excluido",
    "naranja": "Revisar carga / postventa",
    "celeste": "Abona Wamaro — sin prefactura",
}

# Motivos de regla (columna obs / detalle)
MOTIVO_SIN_PREFACTURA = "Sin prefactura del proveedor — pendiente de cruce"
MOTIVO_CANAL_RED = "Canal red/crossdock — revisar cruce con prefactura"
MOTIVO_PREFACTURA_OK = "Prefactura conciliada OK"
MOTIVO_ABONA_WAMARO = "Abona Wamaro — sin prefactura aún"
MOTIVO_ENTREGA_CLIENTE = (
    "Entrega en cliente en interior — posible error de carga (revisar canal)"
)
MOTIVO_TARIFA_SIN_PREF = "Interior — tarifa calculada (sin prefactura cargada)"
MOTIVO_FALTA_PREF = "Falta prefactura del proveedor — pendiente de cruce"
MOTIVO_CONJUNTO_OK = "Conjunto colchón+somier conciliado OK"
