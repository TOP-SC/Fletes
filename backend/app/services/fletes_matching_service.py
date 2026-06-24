"""Heurísticas de geocodificación y asignación de sucursal para Fletes (AMBA/GBA)."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.config import DEPOSITO_CD_HURLINGHAM, DEPOSITO_CD_TORTUGUITAS
from app.models import Envio, Sucursal
from app.services.kilometrizador_service import GeoPoint, Kilometrizador, get_kilometrizador
from app.services.sucursales_service import listar_sucursales
from app.services.zona_km import km_a_zona

DEPOSITO_SUCURSAL: dict[str, str] = {
    DEPOSITO_CD_TORTUGUITAS: "CD",
    DEPOSITO_CD_HURLINGHAM: "TH",
}

# Km de referencia cuando no hay coordenadas del domicilio pero la localidad coincide con la sucursal.
KM_ESTIMADO_MISMA_ZONA = 12.0
KM_ESTIMADO_PARTIDO_CERCANO = 22.0

# Alias explícitos (clave normalizada → código sucursal). Orden: claves largas primero al buscar.
ALIAS_LOCALIDAD_SUCURSAL: dict[str, str] = {
    "RINCON DE MILBERG": "ND",
    "NORDELTA": "ND",
    "GENERAL PACHECO": "GP",
    "PACHECO": "GP",
    "TRONCOS DEL TALAR": "ND",
    "LOMAS DE PALOMAR": "LO",
    "CIUDAD JARDIN": "LO",
    "PALOMAR": "LO",
    "CIUDADELA": "SJ",
    "MUNIZ": "MO",
    "HURLINGHAM": "PL",
    "ITUZAINGO": "PL",
    "WILDE": "AV",
    "BERAZATEGUI": "QU",
    "BERAZATGUI": "QU",
    "LA LONJA": "PI",
    "DEL VISO": "PI",
    "MANZANARES": "PI",
    "PRESIDENTE DERQUI": "PI",
    "LOMAS DE ZAMORA": "LO",
    "REMEDIOS DE ESCALADA": "LA",
    "VICENTE LOPEZ": "SV",
    "SAN MIGUEL": "SM",
    "SAN JUSTO": "SJ",
    "SAN MARTIN": "SN",
    "PARQUE LELOIR": "PL",
    "LA PLATA": "LP",
    "PILAR": "PI",
    "BENAVIDEZ": "BE",
    "AVELLANEDA": "AV",
    "QUILMES": "QU",
    "LANUS": "LA",
    "TIGRE": "ND",
    "MORENO": "MO",
    "CANNING": "CA",
    "EZEIZA": "CA",
    "MARTINEZ": "YR",
    "BOULOGNE": "TH",
    "FLORES": "FL",
    "BOEDO": "FL",
    "ALMAGRO": "FL",
    "CABALLITO": "FL",
    "PARQUE PATRICIOS": "FL",
    "ROSARIO": "RO",
    "SALTA": "SA",
    "CORDOBA": "CP",
}


@dataclass
class ResultadoGeocode:
    punto: GeoPoint | None
    query: str
    metodo: str


@dataclass
class ResultadoSucursal:
    sucursal: Sucursal | None
    metodo: str
    alias: str | None = None


def norm_texto(s: str | None) -> str:
    if not s:
        return ""
    ss = str(s).strip()
    ss = unicodedata.normalize("NFKD", ss)
    ss = "".join(c for c in ss if not unicodedata.combining(c))
    ss = re.sub(r"[^A-Za-z0-9\s]", " ", ss)
    ss = re.sub(r"\s{2,}", " ", ss).strip()
    return ss.upper()


def limpiar_fragmento(texto: str | None) -> str:
    if not texto:
        return ""
    s = str(texto).strip()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(
        r"^(CASA|PRINCIPAL|TRABAJO|LABORAL|ENTREGA|FISCAL|DEPTO|DPTO|"
        r"DIREC(?:CION)?\s*GEO|DIRECCION\s*COMERCIAL)\s*:?\s*",
        "",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(r"\bPiso\s*:\s*\d*\s*", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"\bDepto\s*:\s*\w*\s*", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"\s{2,}", " ", s).strip(" ,")
    return s


def _provincia_query(envio: Envio) -> str:
    prov = limpiar_fragmento(envio.provincia) or "Buenos Aires"
    if prov.upper() in ("CAPITAL FEDERAL", "CABA"):
        return "Ciudad Autónoma de Buenos Aires"
    return prov


def fingerprint_domicilio(envio: Envio) -> str | None:
    """Clave estable domicilio+localidad+cp (reutilizar geocodificación entre remitos)."""
    partes = [
        limpiar_fragmento(envio.domicilio),
        limpiar_fragmento(envio.localidad),
        limpiar_fragmento(envio.cp),
        _provincia_query(envio),
    ]
    texto = "|".join(norm_texto(p) for p in partes if p)
    if len(texto) < 8:
        return None
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:32]


def texto_destino_envio(envio: Envio) -> str:
    partes = [
        limpiar_fragmento(envio.domicilio),
        limpiar_fragmento(envio.localidad),
        limpiar_fragmento(envio.provincia),
        limpiar_fragmento(envio.cp),
    ]
    return " ".join(p for p in partes if p)


_CABA_PROVINCIAS = frozenset(
    {
        "CAPITAL FEDERAL",
        "CABA",
        "CIUDAD AUTONOMA DE BUENOS AIRES",
        "CIUDAD DE BUENOS AIRES",
        "FEDERAL",
    }
)

_CABA_BARRIOS = frozenset(
    {
        "BOEDO",
        "FLORES",
        "ALMAGRO",
        "CABALLITO",
        "BALVANERA",
        "SAN TELMO",
        "RECOLETA",
        "PALERMO",
        "BELGRANO",
        "NUNEZ",
        "VILLA CRESPO",
        "PARQUE PATRICIOS",
        "BARRACAS",
        "LA BOCA",
        "PUERTO MADERO",
        "VILLA URQUIZA",
        "VILLA PUEYRREDON",
        "SAAVEDRA",
        "COGHLAN",
        "VILLA DEVOTO",
        "VILLA DEL PARQUE",
        "MONTE CASTRO",
        "VELEZ SARSFIELD",
        "LINIERS",
        "MATADEROS",
        "PARQUE CHACABUCO",
        "VILLA SOLDATI",
        "VILLA LUGANO",
        "POMPEYA",
        "CONSTITUCION",
    }
)

# Barrio CABA → sucursal de referencia (cuando localidad Tango es genérica)
_BARRIO_CABA_SUCURSAL: dict[str, str] = {
    "BOEDO": "FL",
    "ALMAGRO": "FL",
    "CABALLITO": "FL",
    "FLORES": "FL",
    "PARQUE PATRICIOS": "FL",
    "BALVANERA": "FL",
    "SAN TELMO": "FL",
    "BARRACAS": "FL",
    "LA BOCA": "FL",
    "POMPEYA": "FL",
    "CONSTITUCION": "FL",
    "LINIERS": "FL",
    "MATADEROS": "FL",
    "VELEZ SARSFIELD": "FL",
    "MONTE CASTRO": "FL",
    "VILLA DEL PARQUE": "FL",
    "VILLA DEVOTO": "FL",
    "VILLA CRESPO": "FL",
    "RECOLETA": "SF",
    "PALERMO": "SF",
    "BELGRANO": "CO",
    "NUNEZ": "CO",
    "COGHLAN": "CO",
    "VILLA URQUIZA": "CO",
    "VILLA PUEYRREDON": "CO",
    "SAAVEDRA": "CO",
    "PUERTO MADERO": "SF",
    "VILLA SOLDATI": "PL",
    "VILLA LUGANO": "PL",
    "PARQUE CHACABUCO": "FL",
}


def es_destino_caba(envio: Envio) -> bool:
    prov = norm_texto(envio.provincia)
    loc = norm_texto(envio.localidad)
    if prov in _CABA_PROVINCIAS or "CAPITAL FEDERAL" in prov or prov == "FEDERAL":
        return True
    if loc in ("CABA", "CAPITAL FEDERAL", "CIUDAD AUTONOMA DE BUENOS AIRES"):
        return True
    if loc in _CABA_BARRIOS:
        return True
    dom = norm_texto(envio.domicilio)
    return any(b in dom for b in _CABA_BARRIOS)


def barrio_caba_desde_envio(envio: Envio) -> str | None:
    """Detecta barrio en domicilio o localidad (CABA con localidad genérica en Tango)."""
    dom = norm_texto(envio.domicilio)
    loc = norm_texto(envio.localidad)
    for barrio in sorted(_CABA_BARRIOS, key=len, reverse=True):
        if barrio in dom or barrio in loc:
            return barrio
    return None


def texto_alias_sucursal(envio: Envio) -> str:
    """Localidad + provincia; en CABA agrega barrio del domicilio (sin nombre de calle)."""
    partes: list[str] = []
    barrio = barrio_caba_desde_envio(envio)
    if barrio:
        partes.append(barrio)
    loc = norm_texto(envio.localidad)
    if loc and loc not in partes and loc not in _CLAVES_GENERICAS:
        partes.append(loc)
    prov = norm_texto(envio.provincia)
    if prov and prov not in _CLAVES_GENERICAS:
        partes.append(prov)
    return " ".join(partes)


def textos_match_sucursal(envio: Envio) -> list[str]:
    """Candidatos de texto para inferir sucursal (más específico primero)."""
    vistos: set[str] = set()
    out: list[str] = []
    for raw in (
        texto_alias_sucursal(envio),
        limpiar_fragmento(envio.domicilio),
        limpiar_fragmento(envio.localidad),
        texto_destino_envio(envio),
    ):
        t = norm_texto(raw)
        if not t or t in vistos:
            continue
        vistos.add(t)
        out.append(t)
    return out


def match_sucursal_envio(
    db: Session,
    envio: Envio,
) -> tuple[str | None, str | None]:
    """Busca código sucursal probando alias, domicilio y localidad."""
    barrio = barrio_caba_desde_envio(envio)
    if barrio and barrio in _BARRIO_CABA_SUCURSAL:
        return _BARRIO_CABA_SUCURSAL[barrio], barrio
    for texto in textos_match_sucursal(envio):
        cod, clave = match_localidad_sucursal(db, texto, envio=envio)
        if cod:
            return cod, clave
    return None, None


def _clave_coincide_en_destino(clave: str, norm: str, envio: Envio) -> bool:
    if clave not in norm:
        return False
    if clave == "LA PLATA" and es_destino_caba(envio):
        dom = norm_texto(envio.domicilio)
        if re.search(r"\bAV\.?\s*LA\s+PLATA\b", dom) or re.search(
            r"\bAVENIDA\s+LA\s+PLATA\b", dom
        ):
            return False
    return True


def variantes_query_destino(envio: Envio) -> list[tuple[str, str]]:
    """Lista (etiqueta_metodo, query) de más específica a más amplia."""
    dom = limpiar_fragmento(envio.domicilio)
    loc = limpiar_fragmento(envio.localidad)
    prov = _provincia_query(envio)
    cp = limpiar_fragmento(envio.cp)
    out: list[tuple[str, str]] = []

    loc_norm = norm_texto(loc)
    if es_destino_caba(envio):
        barrio = barrio_caba_desde_envio(envio)
        if barrio and dom:
            out.insert(
                0,
                (
                    "caba_barrio",
                    ", ".join(p for p in (dom, barrio.title(), prov, cp) if p),
                ),
            )
        if dom and loc_norm in _CLAVES_GENERICAS:
            out.insert(
                0,
                ("caba_domicilio", ", ".join(p for p in (dom, "CABA", "Argentina") if p)),
            )
    if dom and loc:
        out.append(("completa", ", ".join(p for p in (dom, loc, prov, cp) if p)))
    if dom and loc:
        out.append(("domicilio_localidad", ", ".join(p for p in (dom, loc, prov) if p)))
    # Calle sin número / barrio cerrado: quitar números al final para Nominatim
    if dom:
        dom_ligero = re.sub(r"\s+\d{1,5}\s*$", "", dom).strip()
        if dom_ligero and dom_ligero != dom and loc:
            out.append(("calle_sin_numero", ", ".join((dom_ligero, loc, prov))))
    if loc:
        out.append(("localidad", ", ".join(p for p in (loc, prov, cp) if p)))
        out.append(("localidad_cp", ", ".join(p for p in (loc, cp, prov) if p)))
    if dom and not loc:
        out.append(("solo_domicilio", ", ".join(p for p in (dom, prov) if p)))
    # Deduplicar queries
    visto: set[str] = set()
    unicos: list[tuple[str, str]] = []
    for metodo, q in out:
        qn = q.strip()
        if not qn or qn.lower() in visto:
            continue
        visto.add(qn.lower())
        unicos.append((metodo, qn))
    return unicos


def geocodificar_destino(
    envio: Envio,
    km: Kilometrizador | None = None,
) -> ResultadoGeocode:
    svc = km or get_kilometrizador()
    ultima_q = ""
    for metodo, query in variantes_query_destino(envio):
        ultima_q = query
        try:
            punto = svc.geocode(query)
            return ResultadoGeocode(punto=punto, query=query, metodo=metodo)
        except Exception:
            continue
    return ResultadoGeocode(punto=None, query=ultima_q, metodo="sin_geocode")


def _tokens_desde_sucursal(s: Sucursal) -> list[str]:
    tokens: list[str] = []
    nm = norm_texto(s.nombre)
    if nm and len(nm) >= 4:
        tokens.append(nm)
    loc_raw = (s.localidad or "").strip()
    if loc_raw:
        # "Banfield, Lomas de Zamora, Buenos Aires" → Banfield, Lomas de Zamora
        parte = re.split(r",|\(CP", loc_raw, maxsplit=2)[0].strip()
        parte = re.sub(r"\bC\.A\.B\.A\.?\b", "CABA", parte, flags=re.IGNORECASE)
        for frag in re.split(r",| y ", parte):
            t = norm_texto(frag)
            if t and len(t) >= 4 and t not in ("ARGENTINA", "BUENOS AIRES", "GBA SUR"):
                tokens.append(t)
    return tokens


def indice_localidad_sucursal(db: Session) -> list[tuple[str, str]]:
    """Pares (clave_normalizada, codigo) ordenados por longitud descendente."""
    pares: dict[str, str] = dict(ALIAS_LOCALIDAD_SUCURSAL)
    for s in listar_sucursales(db, solo_activas=True):
        cod = (s.codigo or "").strip().upper()
        if not cod or cod in ("SV", "JU"):
            continue
        for tok in _tokens_desde_sucursal(s):
            if tok not in pares:
                pares[tok] = cod
    ordenados = sorted(pares.items(), key=lambda x: len(x[0]), reverse=True)
    return ordenados


_CLAVES_GENERICAS = frozenset(
    {
        "BUENOS AIRES",
        "ARGENTINA",
        "GBA SUR",
        "PROVINCIA DE BUENOS AIRES",
        "CABA",
        "CAPITAL FEDERAL",
    }
)


def match_localidad_sucursal(
    db: Session,
    texto: str,
    *,
    envio: Envio | None = None,
) -> tuple[str | None, str | None]:
    """Devuelve (codigo_sucursal, alias_matcheado)."""
    norm = norm_texto(texto)
    if not norm:
        return None, None
    for clave, cod in indice_localidad_sucursal(db):
        if len(clave) < 4 or clave in _CLAVES_GENERICAS:
            continue
        if clave not in norm:
            continue
        if envio is not None and not _clave_coincide_en_destino(clave, norm, envio):
            continue
        return cod, clave
    return None, None


def sucursal_por_deposito(deposito: str | None) -> str | None:
    if not deposito:
        return None
    return DEPOSITO_SUCURSAL.get(str(deposito).strip())


def sucursal_mas_cercana(
    db: Session,
    dest_lat: float,
    dest_lon: float,
    *,
    preferir_cod: str | None = None,
    solo_amba: bool = True,
) -> Sucursal | None:
    from app.services.kilometrizador_service import haversine_km

    candidatos = listar_sucursales(db, solo_activas=True)
    mejor: Sucursal | None = None
    mejor_km = 1e9
    pref = (preferir_cod or "").strip().upper()
    for s in candidatos:
        if s.lat is None or s.lon is None:
            continue
        if solo_amba and s.zona == "INTERIOR":
            continue
        d = haversine_km((s.lat, s.lon), (dest_lat, dest_lon))
        if pref and s.codigo == pref:
            d *= 0.82
        if d < mejor_km:
            mejor_km = d
            mejor = s
    return mejor


def resolver_sucursal(
    db: Session,
    envio: Envio,
    *,
    dest: GeoPoint | None = None,
    sucursal_cod: str | None = None,
) -> ResultadoSucursal:
    cod = (sucursal_cod or sucursal_por_deposito(envio.deposito) or "").strip().upper()
    if cod:
        suc = db.get(Sucursal, cod)
        if suc and suc.lat is not None:
            return ResultadoSucursal(sucursal=suc, metodo="deposito" if not sucursal_cod else "explicito")

    alias_cod, alias_key = match_sucursal_envio(db, envio)

    if dest and dest.lat and dest.lon:
        suc = sucursal_mas_cercana(
            db, dest.lat, dest.lon, preferir_cod=alias_cod, solo_amba=True
        )
        if suc:
            metodo = "geocode_cercana"
            if alias_cod and suc.codigo == alias_cod:
                metodo = "geocode_localidad"
            return ResultadoSucursal(sucursal=suc, metodo=metodo, alias=alias_key)

    if alias_cod:
        suc = db.get(Sucursal, alias_cod)
        if suc:
            return ResultadoSucursal(
                sucursal=suc, metodo="solo_localidad", alias=alias_key
            )

    return ResultadoSucursal(sucursal=None, metodo="sin_sucursal")


def km_estimado_sin_coordenadas(
    *,
    misma_zona_logica: bool,
) -> float:
    if misma_zona_logica:
        return KM_ESTIMADO_MISMA_ZONA
    return KM_ESTIMADO_PARTIDO_CERCANO


def es_estimado_provider(km_provider: str | None) -> bool:
    if not km_provider:
        return False
    p = km_provider.lower()
    return "estimado" in p or "solo_localidad" in p


def construir_flete_distancia(
    db: Session,
    envio: Envio,
    *,
    sucursal_cod: str | None = None,
) -> dict[str, Any]:
    """
    Calcula km/zona con cascada. No lanza si hay match por localidad;
    devuelve dict con datos para persistir o error en 'error'.
    """
    km = get_kilometrizador()
    geo = geocodificar_destino(envio, km)
    res_suc = resolver_sucursal(db, envio, dest=geo.punto, sucursal_cod=sucursal_cod)
    suc = res_suc.sucursal
    if not suc or suc.lat is None or suc.lon is None:
        return {"error": "No hay sucursal con coordenadas"}

    destino_q = geo.query or texto_destino_envio(envio)
    metodo_parts = [res_suc.metodo]
    if geo.metodo != "sin_geocode":
        metodo_parts.append(f"geo_{geo.metodo}")

    distance_km: float
    provider: str
    dest_lat: float | None = None
    dest_lon: float | None = None
    estimado = False

    if geo.punto:
        origen = GeoPoint(lat=suc.lat, lon=suc.lon, label=suc.nombre, source="sucursal")
        ruta = km.route(origen, geo.punto)
        distance_km = float(ruta.get("distance_km") or 0.0)
        provider = str(ruta.get("provider") or "haversine")
        dest_lat = geo.punto.lat
        dest_lon = geo.punto.lon
    else:
        misma = bool(res_suc.alias and res_suc.metodo == "solo_localidad")
        distance_km = km_estimado_sin_coordenadas(misma_zona_logica=misma)
        provider = "estimado_localidad"
        estimado = True
        metodo_parts.append("km_estimado")

    _, zona_key = km_a_zona(distance_km)
    km_provider = "|".join(metodo_parts + ([provider] if provider else []))

    return {
        "sucursal_cod": suc.codigo,
        "distance_km": round(distance_km, 2),
        "zona_km": zona_key,
        "km_provider": km_provider[:80],
        "destino_query": (destino_q or "")[:500],
        "dest_lat": dest_lat,
        "dest_lon": dest_lon,
        "estimado": estimado,
        "motivo": _motivo_asignacion(res_suc, geo, estimado),
    }


def _motivo_asignacion(
    res_suc: ResultadoSucursal,
    geo: ResultadoGeocode,
    estimado: bool,
) -> str:
    if estimado and res_suc.alias:
        return f"Entrega organizada desde {res_suc.sucursal.nombre if res_suc.sucursal else res_suc.alias} (localidad {res_suc.alias}, km estimado)"
    if geo.punto and res_suc.metodo == "geocode_localidad":
        return f"Sucursal {res_suc.sucursal.nombre if res_suc.sucursal else ''} por coincidencia de localidad"
    if geo.punto:
        return "Km desde sucursal más cercana al domicilio geocodificado"
    if res_suc.metodo == "deposito":
        return "Sucursal según depósito de origen"
    return "Asignación automática de flete"
