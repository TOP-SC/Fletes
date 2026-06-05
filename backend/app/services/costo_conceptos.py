"""
Conceptos de costo en Control de Fletes.

Costo proveedor (nosotros)
    Lo que el transportista / red nos factura según tarifario (CLICPAQ, LBO,
    FLETES_SUC, etc.). Se persiste en ``costo_tarifario`` (+ seguro en la línea
    de cobro del pedido). **No debe quedar en 0** solo porque el envío salga de
    la planilla interior.

Cobro al cliente
    Lo que se le cobra al cliente final en la venta. En CABA/GBA muchas ventas
    llevan flete bonificado: el cliente ve **$0**, pero igual hay costo proveedor.

excluir_planilla
    El envío **no entra al maestro interior** (red Clickpac / provincias). No
    significa “sin costo logístico”. Típicamente: AMBA/GBA (``es_amba_gba``) o
    retiro en sucursal.

Referencias: ``docs/TARIFA_LOGISTICA_CABA_GBA.md``, ``cobro_logistica_service``.
"""

from __future__ import annotations

from app.models import Envio
from app.services.rules_service import es_amba_gba
from app.transporte_reglas import sin_flete_domicilio_transporte

PROVEEDOR_FLETE_LOCAL = "FLETES_SUC"


def es_retiro_sin_flete_domicilio(envio: Envio) -> bool:
    return sin_flete_domicilio_transporte(envio.transporte_cod, envio.transporte_nombre)


def es_amba_gba_envio(envio: Envio) -> bool:
    return es_amba_gba(envio.provincia, envio.localidad, envio.cp)


def debe_calcular_costo_proveedor(envio: Envio) -> bool:
    """Hay tarifario aplicable salvo retiro en sucursal o reglas postventa especiales."""
    if es_retiro_sin_flete_domicilio(envio):
        return False
    if envio.regla_postventa in ("no_pagar_transporte", "costo_cero_pendiente"):
        return False
    return True


def cobro_al_cliente_es_cero(envio: Envio) -> bool:
    """Flete bonificado al cliente (planilla AMBA/GBA u otras reglas de exclusión)."""
    return bool(envio.excluir_planilla) and es_amba_gba_envio(envio)


def motivo_exclusion_planilla(envio: Envio) -> str:
    if es_retiro_sin_flete_domicilio(envio):
        return "Retiro sin flete domicilio (excluir planilla interior)"
    from app.services.transportes_service import lookup_transporte_catalogo

    row = lookup_transporte_catalogo(envio.transporte_cod, envio.transporte_nombre)
    if row and row.get("tipo") == "sucursal":
        return "Envío/retiro en sucursal (excluir planilla interior)"
    if row and row.get("tipo") == "correo":
        return "Envío por correo (excluir planilla interior)"
    if row and row.get("tipo") == "costa":
        return "Expreso Costa (excluir planilla interior)"
    if row and row.get("alerta_uso"):
        return row.get("notas") or "Transporte de uso especial (excluir planilla interior)"
    if es_amba_gba_envio(envio):
        return (
            "AMBA/GBA: fuera planilla interior; cobro al cliente puede ser $0 — "
            "costo proveedor por tarifario FLETES_SUC"
        )
    return "Excluido de planilla interior"
