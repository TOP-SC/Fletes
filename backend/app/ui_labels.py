"""Etiquetas visibles (mayúsculas/minúsculas) — claves internas siguen en mayúsculas."""

from __future__ import annotations

# Proveedores / marcas (código API → cómo se muestra)
PROVEEDOR_DISPLAY: dict[str, str] = {
    "CLICPAQ": "Clicpaq",
    "FRANSOF": "Fransof",
    "ALFARO": "Alfaro",
    "LBO": "LBO",
}

# Menú lateral y títulos de página
MENU_DISPLAY: dict[str, str] = {
    "Dashboard": "Dashboard",
    "MAESTRO": "Maestro",
    "Modo Adrián": "Modo Adrián",
    "Fletes": "Fletes",
    "Configuración": "Configuración",
    "CLICPAQ": "Clicpaq",
    "FRANSOF": "Fransof",
    "ALFARO": "Alfaro",
    "LBO": "LBO",
    "Proveedor a elegir": "Proveedor a elegir",
}

# Columnas del maestro (clave DataFrame → encabezado)
COLUMNA_DISPLAY: dict[str, str] = {
    "FECHA": "Fecha",
    "ENVIO": "Envío",
    "NRO TRANSP": "Nro. transp.",
    "REMITOS": "Remitos",
    "DESTINATARIO": "Destinatario",
    "LOCALIDAD": "Localidad",
    "PROVINCIA": "Provincia",
    "SERVICIO": "Servicio",
    "TRANSPORTE": "Transporte",
    "FLETERO": "Fletero",
    "OBLEA TRANSPORTE": "Oblea transporte",
    "PROVEEDOR": "Proveedor",
    "BULTOS": "Bultos",
    "PESO": "Peso",
    "VOLUMEN": "Volumen",
    "PESO FACTURADO": "Peso facturado",
    "LOGISTICA": "Logística",
    "SEGURO": "Seguro",
    "GESTION": "Gestión",
    "ADICIONAL": "Adicional",
    "VALOR DECLARADO": "Valor declarado",
    "PRECIO NETO": "Precio neto",
    "ARTICULOS": "Artículos",
    "ZONA ORIGEN": "Zona origen",
    "DESCRIPCION ZONA ORIGEN": "Descripción zona origen",
    "ZONA DESTINO": "Zona destino",
    "DESCRIPCION ZONA DESTINO": "Descripción zona destino",
    "obs": "Obs.",
    "costo": "Costo",
    "total": "Total",
    "SUCURSAL": "Sucursal",
    "KM": "Km",
    "ZONA KM": "Zona km",
    "TARIFA REF": "Tarifa ref.",
    "dif": "Dif.",
    "suc": "Suc.",
    "campo": "Campo",
    "valor": "Valor",
}

_PARTICULAS = frozenset({"de", "del", "la", "las", "los", "y", "e", "en", "a", "al"})

_CAMPOS_TITULO = frozenset(
    {
        "DESTINATARIO",
        "LOCALIDAD",
        "PROVINCIA",
        "TRANSPORTE",
        "SERVICIO",
        "ARTICULOS",
        "DESCRIPCION ZONA ORIGEN",
        "DESCRIPCION ZONA DESTINO",
        "ZONA ORIGEN",
        "ZONA DESTINO",
        "OBLEA TRANSPORTE",
    }
)


def etiqueta_menu(clave: str) -> str:
    return MENU_DISPLAY.get(clave, clave)


def etiqueta_pagina(titulo: str) -> str:
    return MENU_DISPLAY.get(titulo, titulo)


def etiqueta_proveedor(codigo: str | None) -> str:
    if not codigo:
        return ""
    key = str(codigo).strip().upper()
    return PROVEEDOR_DISPLAY.get(key, titulo_palabras(str(codigo).strip()))


def etiqueta_columna(clave: str) -> str:
    return COLUMNA_DISPLAY.get(clave, titulo_palabras(str(clave).replace("_", " ")))


def _es_mayus_agresiva(texto: str) -> bool:
    letras = [c for c in texto if c.isalpha()]
    if len(letras) < 3:
        return False
    upper = sum(1 for c in letras if c.isupper())
    return upper / len(letras) >= 0.75


def titulo_palabras(texto: str) -> str:
    """Convierte texto gritado a título legible (VILLA DEL ROSARIO → Villa del Rosario)."""
    s = (texto or "").strip()
    if not s:
        return ""
    if not _es_mayus_agresiva(s):
        return s
    partes = s.split()
    out: list[str] = []
    for i, p in enumerate(partes):
        low = p.lower()
        up = p.upper()
        if up in PROVEEDOR_DISPLAY:
            out.append(PROVEEDOR_DISPLAY[up])
            continue
        if i > 0 and low in _PARTICULAS:
            out.append(low)
        elif len(p) <= 3 and p.isalpha() and p.isupper():
            out.append(up)
        else:
            out.append(low.capitalize())
    return " ".join(out)


def fmt_celda_maestro(valor: object, columna: str) -> str:
    """Texto de celda para grillas (mantiene números y fechas tal cual)."""
    if valor is None or (isinstance(valor, float) and str(valor) == "nan"):
        return ""
    if columna == "PROVEEDOR":
        return etiqueta_proveedor(str(valor))
    if columna in _CAMPOS_TITULO:
        return titulo_palabras(str(valor))
    return str(valor).strip()
