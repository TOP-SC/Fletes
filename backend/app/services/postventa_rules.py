"""Reglas de postventa (grilla = misma base Tango en muchos casos)."""

from app.config import settings
from app.models import Envio, PostventaRegistro

REGLA_OBSERVACION = {
    "gestion_retiro_25": "Postventa: cambio/gestión retiro — +25% sobre tarifa",
    "cruce_medidas_aprobado": "Postventa: cruce de medidas (error interno) — se aprueba viaje",
    "no_pagar_transporte": "Postventa: rotura/extravío/error expreso — NO SE PAGA ($0)",
    "costo_cero_pendiente": "Postventa: duda/retorno no justificado — costo $0 hasta validar",
    "revisar_manual": "Postventa: revisar motivo manualmente",
}


def clasificar_postventa(motivo: str | None, tipo: str | None) -> str:
    text = f"{motivo or ''} {tipo or ''}".upper()
    if any(k in text for k in ("CAMBIO", "GESTION DE RETIRO", "GESTIÓN DE RETIRO", "RETIRO")):
        return "gestion_retiro_25"
    if any(k in text for k in ("CRUCE DE MEDIDA", "CRUCE MEDIDA", "ERROR INTERNO")):
        return "cruce_medidas_aprobado"
    if any(
        k in text
        for k in (
            "ROTURA",
            "EXTRAV",
            "REPOSICION",
            "REPOSICIÓN",
            "ERROR MEDIDA",
            "EXPRESO",
        )
    ):
        return "no_pagar_transporte"
    if any(k in text for k in ("DUDA", "NO JUSTIFIC", "PENDIENTE")):
        return "costo_cero_pendiente"
    return "revisar_manual"


def _aplicar_regla_a_envio(envio: Envio, regla: str, motivo_texto: str) -> None:
    envio.motivo_postventa = motivo_texto
    envio.regla_postventa = regla
    obs = REGLA_OBSERVACION.get(regla, "")
    if obs:
        prev = envio.observaciones or ""
        envio.observaciones = f"{prev} | {obs}".strip(" |") if prev else obs

    if regla == "gestion_retiro_25":
        base = envio.costo_tarifario or envio.costo_total
        if base and base > settings.seguro_fijo:
            tarifa_sin_seguro = base - settings.seguro_fijo
            envio.costo_tarifario = round(
                tarifa_sin_seguro * (1 + settings.gestion_retiro_pct) + settings.seguro_fijo,
                2,
            )
        envio.regla_color = "naranja"
        envio.regla_motivo = obs
    elif regla == "cruce_medidas_aprobado":
        envio.regla_color = "verde"
        envio.regla_motivo = obs
    elif regla in ("no_pagar_transporte", "costo_cero_pendiente"):
        envio.costo_total = 0.0
        envio.costo_tarifario = 0.0
        envio.regla_color = "rojo"
        envio.regla_motivo = obs
    else:
        envio.regla_color = "naranja"
        envio.regla_motivo = obs


def aplicar_postventa_desde_tango(envio: Envio) -> None:
    """Si el Excel Tango trae TipoGestion / SubTipo, aplicar reglas sin archivo aparte."""
    if not envio.tipo_gestion and not envio.sub_tipo_gestion:
        return
    regla = clasificar_postventa(envio.tipo_gestion, envio.sub_tipo_gestion)
    if regla == "revisar_manual" and not (envio.tipo_gestion or envio.sub_tipo_gestion):
        return
    motivo = f"{envio.tipo_gestion or ''} {envio.sub_tipo_gestion or ''}".strip()
    _aplicar_regla_a_envio(envio, regla, motivo)


def aplicar_regla_postventa_a_envio(envio: Envio, registro: PostventaRegistro) -> None:
    regla = clasificar_postventa(registro.motivo, registro.tipo_gestion)
    registro.regla_aplicada = regla
    envio.postventa_id = registro.id
    _aplicar_regla_a_envio(envio, regla, registro.motivo or "")
