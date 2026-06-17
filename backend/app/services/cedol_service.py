"""Resolución de código CEDOL (tarifario CLICPAQ/ALFARO) y lookup de precio."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from app.proveedores import normalizar_proveedor
from app.services.medida_utils import medida_a_banda, medidas_equivalentes
from app.services.rules_service import es_amba_gba, normalizar_provincia_geo

_CEDOL_RE = re.compile(r"^[A-Z]\d+$")
_PROVEEDORES_CEDOL = frozenset({"CLICPAQ", "ALFARO"})


def _norm_geo(value: str | None) -> str:
    v = (value or "").strip().upper()
    return "".join(
        c for c in unicodedata.normalize("NFD", v) if unicodedata.category(c) != "Mn"
    )


def _norm(value: str | None) -> str:
    return (value or "").strip().upper()


def cedol_valido(cedol: str | None) -> bool:
    return bool(cedol and _CEDOL_RE.fullmatch(str(cedol).strip().upper()))


@dataclass(frozen=True)
class FilaCedol:
    cedol: str
    provincia: str
    localidad: str
    provincia_norm: str
    localidad_norm: str


def _provincias_coinciden(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    if a in b or b in a:
        return True
    return False


def _tokens_localidad(text: str) -> list[str]:
    t = _norm_geo(text)
    t = re.sub(r"[()/]", " ", t)
    parts = [p for p in re.split(r"\s+", t) if len(p) >= 3]
    return parts


def _localidad_coincide(destino: str, fila: FilaCedol) -> bool:
    loc = _norm_geo(destino)
    if not loc:
        return False
    fl = fila.localidad_norm
    if loc == fl:
        return True
    if fl in loc or loc in fl:
        return True
    if fl == "GENERAL":
        return False
    for tok in _tokens_localidad(fl):
        if tok in loc:
            return True
    for tok in _tokens_localidad(loc):
        if tok in fl:
            return True
    return False


def _es_fila_capital(fila: FilaCedol) -> bool:
    if not fila.cedol.endswith("0"):
        return False
    fl = fila.localidad_norm
    if "CAPITAL" in fl:
        return True
    if fila.cedol in ("H0", "S0", "E0", "M0", "N0", "T0", "X0", "Y0", "Z0", "R0"):
        return True
    if fila.cedol in ("B0", "U0", "U1", "U2", "V0", "L0", "W0", "P0", "Q0", "F0", "G0", "K0", "J0", "D0", "A0"):
        return True
    return False


def _destino_es_capital(provincia_norm: str, localidad: str, fila_capital: FilaCedol) -> bool:
    loc = _norm_geo(localidad)
    if not loc:
        return False
    if _localidad_coincide(loc, fila_capital):
        return True
    fl = fila_capital.localidad_norm
    if "CAPITAL" in fl:
        prov_tokens = _tokens_localidad(provincia_norm)
        if any(t in loc for t in prov_tokens if len(t) >= 4):
            return True
        if loc.endswith(" CAPITAL") or loc.startswith("CAPITAL "):
            return True
    return False


class IndiceCedol:
    """Índice de filas tarifario con código CEDOL por proveedor."""

    def __init__(self, tarifas: list[Any], proveedor: str) -> None:
        self.proveedor = normalizar_proveedor(proveedor) or proveedor
        self.filas: list[FilaCedol] = []
        vistos: set[tuple[str, str, str]] = set()
        for t in tarifas:
            prov_t = normalizar_proveedor(getattr(t, "proveedor", None))
            if prov_t != self.proveedor:
                continue
            cedol = _norm(getattr(t, "cedol", None))
            if not cedol_valido(cedol):
                continue
            prov = _norm_geo(getattr(t, "provincia", None))
            loc = _norm_geo(getattr(t, "localidad", None))
            key = (cedol, prov, loc)
            if key in vistos:
                continue
            vistos.add(key)
            self.filas.append(
                FilaCedol(
                    cedol=cedol,
                    provincia=str(getattr(t, "provincia", "") or ""),
                    localidad=str(getattr(t, "localidad", "") or ""),
                    provincia_norm=prov,
                    localidad_norm=loc,
                )
            )

    def filas_cedol(self, cedol: str) -> list[FilaCedol]:
        c = _norm(cedol)
        return [f for f in self.filas if f.cedol == c]

    def filas_provincia(self, provincia_norm: str) -> list[FilaCedol]:
        return [f for f in self.filas if _provincias_coinciden(provincia_norm, f.provincia_norm)]


def construir_indice_cedol(tarifas: list[Any], proveedor: str) -> IndiceCedol:
    return IndiceCedol(tarifas, proveedor)


def resolver_cedol_destino(
    provincia: str | None,
    localidad: str | None,
    *,
    cp: str | None = None,
    tarifas: list[Any],
    proveedor: str,
) -> str | None:
    """
    Determina el código CEDOL del tarifario para un destino Tango.
    Prioridad: localidad exacta en matriz → capital provincial → interior.
    """
    prov_key = normalizar_proveedor(proveedor)
    if prov_key not in _PROVEEDORES_CEDOL:
        return None

    prov = normalizar_provincia_geo(provincia)
    loc = (localidad or "").strip()
    idx = construir_indice_cedol(tarifas, prov_key)
    if not idx.filas:
        return None

    if es_amba_gba(provincia, localidad, cp):
        for cod in ("B1", "B2"):
            for f in idx.filas_cedol(cod):
                if _localidad_coincide(loc, f):
                    return cod
        return "B0"

    if "BUENOS AIRES" in prov and not es_amba_gba(provincia, localidad, cp):
        for cod in ("B1", "B2"):
            for f in idx.filas_cedol(cod):
                if _localidad_coincide(loc, f):
                    return cod
        return "B3"

    filas_prov = idx.filas_provincia(prov)
    if not filas_prov and prov:
        filas_prov = [
            f
            for f in idx.filas
            if prov[:3] in f.provincia_norm or f.provincia_norm[:3] in prov
        ]

    exactas = [f for f in filas_prov if _localidad_coincide(loc, f)]
    if exactas:
        return max(exactas, key=lambda f: len(f.localidad_norm)).cedol

    if prov == "CHUBUT":
        for cod in ("U0", "U1", "U2", "U3"):
            for f in idx.filas_cedol(cod):
                if _localidad_coincide(loc, f):
                    return cod

    capitales = [f for f in filas_prov if _es_fila_capital(f)]
    for cap in capitales:
        if _destino_es_capital(prov, loc, cap):
            return cap.cedol

    interiores = [
        f
        for f in filas_prov
        if f.cedol.endswith("1") or "INTERIOR" in f.localidad_norm
    ]
    if interiores:
        return interiores[0].cedol

    letra = prov[:1] if prov else ""
    if letra:
        fallback = [f for f in idx.filas if f.cedol.startswith(letra) and f.cedol.endswith("1")]
        if fallback:
            return fallback[0].cedol

    return None


def _tipo_medida_coincide(t: Any, tipo: str, medida: str) -> bool:
    tipo_n = _norm(tipo)
    med_variants = medidas_equivalentes(medida) if medida else set()
    banda = medida_a_banda(medida) if medida else ""
    if banda:
        med_variants.add(banda)

    ttipo = _norm(getattr(t, "tipo_producto", None))
    if ttipo and tipo_n:
        if ttipo == tipo_n:
            pass
        elif ttipo == "GENERICO":
            pass
        elif tipo_n in ("BASE", "SOMIER") and ttipo == "COLCHON":
            pass
        else:
            return False

    tmed = _norm(getattr(t, "medida", None)).replace(" ", "")
    if tmed and med_variants:
        meds = {m.upper().replace(" ", "") for m in med_variants}
        if tmed in meds:
            return True
        if tmed in ("GENERICO", ""):
            return True
        return False
    if tmed and not med_variants:
        return False
    return True


def lookup_tarifa_por_cedol(
    tarifas: list[Any],
    proveedor: str,
    cedol: str,
    tipo_producto: str,
    medida: str,
) -> float | None:
    """Precio exacto por proveedor + CEDOL + tipo + medida."""
    if not cedol_valido(cedol):
        return None
    prov_key = normalizar_proveedor(proveedor) or _norm(proveedor)
    cod = _norm(cedol)

    def _buscar(tipo: str) -> float | None:
        for t in tarifas:
            tprov = normalizar_proveedor(getattr(t, "proveedor", None)) or _norm(
                getattr(t, "proveedor", None)
            )
            if tprov != prov_key:
                continue
            if _norm(getattr(t, "cedol", None)) != cod:
                continue
            if not _tipo_medida_coincide(t, tipo, medida):
                continue
            precio = getattr(t, "precio", None)
            if precio is not None and float(precio) > 0:
                return float(precio)
        return None

    precio = _buscar(tipo_producto)
    if precio is None and _norm(tipo_producto) in ("BASE", "SOMIER"):
        precio = _buscar("COLCHON")
    return precio


def lookup_tarifa_con_cedol(
    tarifas: list[Any],
    proveedor: str,
    provincia: str,
    localidad: str,
    tipo_producto: str,
    medida: str,
    *,
    cp: str | None = None,
) -> tuple[float | None, str | None]:
    """Resuelve CEDOL y devuelve (precio, cedol_usado)."""
    prov_key = normalizar_proveedor(proveedor)
    if prov_key not in _PROVEEDORES_CEDOL:
        return None, None
    cedol = resolver_cedol_destino(
        provincia, localidad, cp=cp, tarifas=tarifas, proveedor=prov_key
    )
    if not cedol:
        return None, None
    precio = lookup_tarifa_por_cedol(
        tarifas, prov_key, cedol, tipo_producto, medida
    )
    return precio, cedol


def listar_cedoles_tarifario(tarifas: list[Any], proveedor: str) -> list[str]:
    """Códigos CEDOL distintos del tarifario activo para un proveedor."""
    idx = construir_indice_cedol(tarifas, proveedor)
    return sorted({f.cedol for f in idx.filas}, key=lambda c: (c[0], int(c[1:])))


def _linea_referencia_cedol(lineas: list[Any]) -> Any:
    """Línea del caso con proveedor/transporte (no renglones Tango vacíos)."""
    for l in lineas:
        if normalizar_proveedor(l.proveedor_tarifa) in _PROVEEDORES_CEDOL:
            return l
    for l in lineas:
        if l.transporte_cod or l.transporte_nombre:
            return l
    return lineas[0]


def _proveedor_cedol_grupo(lineas: list[Any]) -> str | None:
    for l in lineas:
        prov = normalizar_proveedor(l.proveedor_tarifa)
        if prov in _PROVEEDORES_CEDOL:
            return prov
    for l in lineas:
        if not (l.transporte_cod or l.transporte_nombre):
            continue
        from app.services.proveedor_service import _circuito_envio

        circuito = _circuito_envio(l)
        prov = normalizar_proveedor(circuito.get("proveedor"))
        if prov in _PROVEEDORES_CEDOL:
            return prov
    return None


def info_cedol_grupo(lineas: list[Any], tarifas: list[Any] | None) -> dict[str, Any]:
    """CEDOL automático vs manual para un caso (grupo de envíos)."""
    if not lineas:
        return {"aplica": False}
    base = _linea_referencia_cedol(lineas)
    prov = _proveedor_cedol_grupo(lineas)
    if prov not in _PROVEEDORES_CEDOL:
        return {"aplica": False, "proveedor": prov}
    tarifas = tarifas or []
    auto = resolver_cedol_destino(
        base.provincia,
        base.localidad,
        cp=base.cp,
        tarifas=tarifas,
        proveedor=prov,
    )
    manual = any(l.cedol_manual and l.cedol_codigo for l in lineas)
    codigo_guardado = next(
        (l.cedol_codigo for l in lineas if l.cedol_manual and l.cedol_codigo),
        None,
    )
    efectivo = codigo_guardado if manual else auto
    return {
        "aplica": True,
        "proveedor": prov,
        "cedol_efectivo": efectivo,
        "cedol_auto": auto,
        "cedol_manual": manual,
        "cedol_codigo_guardado": codigo_guardado,
        "localidad": base.localidad,
        "provincia": base.provincia,
    }


def aplicar_cedol_caso(
    db: Any,
    lineas: list[Any],
    *,
    cedol: str | None,
    restaurar_auto: bool = False,
) -> dict[str, Any]:
    """
    Persiste override de CEDOL en todas las líneas del caso y recalcula tarifas.
    ``cedol=None`` o ``restaurar_auto=True`` vuelve al CEDOL automático.
    """
    from app.services.rules_service import recalcular_costos_linea, recalcular_grupo
    from app.services.tarifario_version_service import TarifarioContext

    if not lineas:
        raise ValueError("Caso sin líneas")

    base = _linea_referencia_cedol(lineas)
    prov = _proveedor_cedol_grupo(lineas)
    if prov not in _PROVEEDORES_CEDOL:
        raise ValueError(
            f"CEDOL no aplica: el caso no tiene proveedor CLICPAQ/ALFARO asignado "
            f"(remito {getattr(base, 'remito', '') or '—'})."
        )

    ctx = TarifarioContext(db)
    tarifas = ctx.tarifas_para_grupo(lineas)
    opciones = set(listar_cedoles_tarifario(tarifas, prov))

    if restaurar_auto or not cedol:
        for e in lineas:
            e.cedol_manual = False
            e.cedol_codigo = None
        cedol_aplicado = resolver_cedol_destino(
            base.provincia,
            base.localidad,
            cp=base.cp,
            tarifas=tarifas,
            proveedor=prov,
        )
        modo = "auto"
    else:
        cod = str(cedol).strip().upper()
        if not cedol_valido(cod):
            raise ValueError(f"Código CEDOL inválido: {cedol}")
        if cod not in opciones:
            raise ValueError(
                f"CEDOL {cod} no está en el tarifario de {prov}. "
                f"Opciones: {', '.join(sorted(opciones)[:12])}…"
            )
        for e in lineas:
            e.cedol_manual = True
            e.cedol_codigo = cod
        cedol_aplicado = cod
        modo = "manual"

    from app.services.proveedor_service import precio_tarifa_linea

    recalculadas = 0
    for e in lineas:
        prov_linea = normalizar_proveedor(e.proveedor_tarifa) or prov
        if prov_linea not in _PROVEEDORES_CEDOL:
            continue
        precio = precio_tarifa_linea(e, tarifas, prov_linea)
        recalcular_costos_linea(e, precio)
        recalculadas += 1
    if recalculadas == 0:
        raise ValueError(
            "No se pudo recalcular: ninguna línea del caso tiene tarifa CLICPAQ/ALFARO."
        )

    recalcular_grupo(lineas)
    db.commit()

    info = info_cedol_grupo(lineas, tarifas)
    return {
        "ok": True,
        "modo": modo,
        "cedol_aplicado": cedol_aplicado,
        "lineas_recalculadas": recalculadas,
        "cedol": info,
    }
