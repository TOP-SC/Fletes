"""Control de Fletes — interfaz Streamlit."""

from __future__ import annotations

import html as html_lib
import json
import os
import sys
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, cast

import httpx
from theme_css import theme_stylesheet
import pandas as pd
import streamlit as st

API_URL = os.getenv("FLETES_API_URL", "http://127.0.0.1:8000/api/v1")
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
# Carpeta LOG en red — Excel «Fletes solicitados sucursales» (Drive vendedores)
FLETEROS_LOG_S_DIR = Path(
    r"S:\Administración\TOP\LOG -  Envios Fletes 200326"
)
_BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import importlib

caso_en_vista_proveedor = None
proveedores_para_selector = None
proveedores_acotados_por_transporte = None

try:
    import app.proveedores as _proveedores_mod
    import app.transporte_reglas as _transporte_mod
    import app.ui_labels as _ui_labels_mod

    importlib.reload(_transporte_mod)
    importlib.reload(_proveedores_mod)
    importlib.reload(_ui_labels_mod)
    from app.proveedores import caso_en_vista_proveedor, proveedores_para_selector
    from app.transporte_reglas import proveedores_acotados_por_transporte
    from app.ui_labels import (
        abreviar_provincia,
        etiqueta_columna,
        etiqueta_menu,
        etiqueta_pagina,
        etiqueta_proveedor,
        fmt_celda_maestro,
        nombre_provincia_completo,
    )
except ImportError:
    def etiqueta_menu(clave: str) -> str:
        return clave

    def etiqueta_pagina(titulo: str) -> str:
        return titulo

    def etiqueta_columna(clave: str) -> str:
        return clave

    def etiqueta_proveedor(codigo: str | None) -> str:
        return str(codigo or "")

    def fmt_celda_maestro(valor: object, columna: str) -> str:
        return "" if valor is None else str(valor).strip()

    def abreviar_provincia(provincia: str | None) -> str:
        return str(provincia or "").strip()

    def nombre_provincia_completo(provincia: str | None) -> str:
        return str(provincia or "").strip()
API_BUILD_ESPERADO = "fletes-suc-cc-force-2026-07-14"

AUTH_TOKEN_KEY = "auth_token"
AUTH_USER_KEY = "auth_username"
AUTH_SUPER_KEY = "auth_is_super_admin"

# Acentos por módulo (sobrio con personalidad)
MODULE_THEMES: dict[str, dict[str, str]] = {
    "Dashboard": {"accent": "#1a365d", "accent2": "#3182ce", "bg": "#eef4fc", "icon": "◆"},
    "MAESTRO": {"accent": "#2b6cb0", "accent2": "#4299e1", "bg": "#ebf4ff", "icon": "▣"},
    "Resumen": {"accent": "#7c2d12", "accent2": "#c2410c", "bg": "#fff7ed", "icon": "◈"},
    "Fletes": {"accent": "#0f766e", "accent2": "#14b8a6", "bg": "#ecfdf5", "icon": "▶"},
    "Configuración": {"accent": "#475569", "accent2": "#64748b", "bg": "#f1f5f9", "icon": "⚙"},
    "CLICPAQ": {"accent": "#5b21b6", "accent2": "#7c3aed", "bg": "#f5f3ff", "icon": "◎"},
    "FRANSOF": {"accent": "#b45309", "accent2": "#d97706", "bg": "#fffbeb", "icon": "▷"},
    "ALFARO": {"accent": "#be123c", "accent2": "#e11d48", "bg": "#fff1f2", "icon": "▷"},
    "LBO": {"accent": "#0369a1", "accent2": "#0ea5e9", "bg": "#f0f9ff", "icon": "▷"},
    "Proveedor a elegir": {"accent": "#c2410c", "accent2": "#ea580c", "bg": "#fff7ed", "icon": "?"},
}


def _theme_for(pagina_o_titulo: str) -> dict[str, str]:
    return MODULE_THEMES.get(pagina_o_titulo, MODULE_THEMES["MAESTRO"])


def _as_dataframe(data: object) -> pd.DataFrame:
    """Asegura DataFrame para el type checker (filtros pandas devuelven uniones amplias)."""
    if isinstance(data, pd.DataFrame):
        return data
    return pd.DataFrame(data)

# Solo filas con alerta (detalle en lupa)
COLOR_MAP = {
    "alerta": ("#FFE8E8", "#7A3030"),
}

MENU_PROVEEDORES = [
    "CLICPAQ",
    "FRANSOF",
    "ALFARO",
    "LBO",
    "Proveedor a elegir",
]

# Columnas que vienen de Tango vs las que agrega la planilla maestra (costos/control)
COLUMNAS_TANGO = {
    "id", "remito", "nro_pedido", "cod_articulo", "descripcion", "cantidad",
    "fecha_pedido", "fecha_entrega", "razon_social", "localidad", "provincia",
    "transporte_nombre", "clasificacion", "origen_cd", "abona_wamaro",
}
COLUMNAS_CONTROL = {
    "observaciones", "costo_tarifario", "costo_total", "prefactura_proveedor",
    "diferencia", "sucursal_cc", "macheo_estado", "regla_postventa",
    "regla_color", "regla_motivo",
}
CONTROL_TINT = "#E2E9F4"
CONTROL_BORDER = "#8FA8C8"

# Columnas control del maestro manual WAMARO (costos / observaciones)
MAESTRO_CONTROL = {
    "obs", "costo", "total", "dif", "suc",
    "LOGISTICA", "SEGURO", "GESTION", "ADICIONAL", "PRECIO NETO", "VALOR DECLARADO",
}

MAESTRO_MONEDA = MAESTRO_CONTROL | {"PESO FACTURADO"}

# Columnas visibles en la grilla principal (el resto va al popup)
FLETES_VISTA_GRILLA = [
    "FECHA PEDIDO",
    "FECHA ENTREGA",
    "REMITOS",
    "ESTADO REMITO",
    "DESTINATARIO",
    "LOCALIDAD",
    "PROVINCIA",
    "TRANSPORTE",
    "FLETERO",
    "SUCURSAL",
    "KM",
    "ZONA KM",
    "BULTOS",
    "TARIFA REF",
    "total",
]

MAESTRO_VISTA_GRILLA = [
    "FECHA PEDIDO",
    "FECHA ENTREGA",
    "ESTADO PEDIDO",
    "REMITOS",
    "ESTADO REMITO",
    "NRO TRANSP",
    "DESTINATARIO",
    "LOCALIDAD",
    "PROVINCIA",
    "TRANSPORTE",
    "PROVEEDOR",
    "CEDOL",
    "suc",
    "COD CLIENTE",
    "BULTOS",
    "LOGISTICA",
    "SEGURO",
    "PRECIO NETO",
    "total",
]

# Proporciones de columnas en grilla maestro / elegir proveedor (sin dif/obs/suc)
MAESTRO_COL_RATIOS: dict[str, float] = {
    "FECHA": 0.72,
    "FECHA PEDIDO": 0.68,
    "FECHA ENTREGA": 0.68,
    "ESTADO PEDIDO": 0.82,
    "ESTADO REMITO": 0.78,
    "NRO TRANSP": 0.38,
    "REMITOS": 0.95,
    "DESTINATARIO": 1.55,
    "LOCALIDAD": 0.95,
    "PROVINCIA": 0.38,
    "TRANSPORTE": 0.62,
    "PROVEEDOR": 1.05,
    "CEDOL": 0.42,
    "suc": 0.55,
    "COD CLIENTE": 0.7,
    "BULTOS": 0.42,
    "LOGISTICA": 0.85,
    "SEGURO": 0.62,
    "PRECIO NETO": 0.85,
    "total": 0.85,
    "SUCURSAL": 0.5,
    "KM": 0.55,
    "ZONA KM": 0.8,
    "TARIFA REF": 1.15,
    "FLETERO": 0.65,
}


def fmt_fecha_sin_hora(value: Any) -> str:
    """Solo fecha (sin 00:00:00) para grillas y detalle."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return pd.Timestamp(value).strftime("%d/%m/%Y")
    s = str(value).strip()
    if not s:
        return ""
    if " " in s:
        s = s.split(" ", 1)[0].strip()
    if "T" in s and len(s) >= 10:
        s = s.split("T", 1)[0]
    return s


def fmt_pesos_ar(value: Any) -> str:
    """Formato visual AR: enteros sin decimales basura; miles con punto."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(n - round(n)) < 0.01:
        return f"{int(round(n)):,}".replace(",", ".")
    ent = f"{int(abs(n)):,}".replace(",", ".")
    dec = f"{n:.2f}".split(".")[1]
    return f"-{ent},{dec}" if n < 0 else f"{ent},{dec}"


def preparar_maestro_df(df: pd.DataFrame) -> pd.DataFrame:
    """Convierte montos a numérico, fechas sin hora y texto presentable."""
    out = df.copy()
    for col in out.columns:
        if col in MAESTRO_MONEDA:
            out[col] = pd.to_numeric(out[col], errors="coerce")
        elif col == "FECHA" or "fecha" in col.lower():
            out[col] = out[col].apply(fmt_fecha_sin_hora)
        elif col in ("PROVEEDOR", "DESTINATARIO", "LOCALIDAD", "PROVINCIA", "TRANSPORTE", "ESTADO PEDIDO"):
            out[col] = out[col].apply(lambda v, c=col: fmt_celda_maestro(v, c))
    return out


def valor_celda_display(value: Any, campo: str | None = None) -> str:
    """Texto uniforme para tablas Streamlit/Arrow (evita mezcla str/float en columna valor)."""
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str)
    if campo and "fecha" in campo.lower():
        return fmt_fecha_sin_hora(value)
    if campo:
        return fmt_celda_maestro(value, campo)
    return str(value).strip()


def df_campos_tango(tango: dict[str, Any]) -> pd.DataFrame:
    """DataFrame campo/valor compatible con Arrow."""
    filas = [
        {
            "campo": etiqueta_columna(str(k)),
            "valor": valor_celda_display(v, str(k)),
        }
        for k, v in sorted(tango.items(), key=lambda x: str(x[0]))
        if not str(k).startswith("_")
    ]
    return pd.DataFrame(filas)


def df_detalle_renglon(ren: dict[str, Any]) -> pd.DataFrame:
    """Tabla campo/valor para el detalle de un renglón (sin bloques JSON)."""
    bultos = ren.get("bultos")

    def _fila_bultos() -> dict[str, str] | None:
        if bultos is None:
            return None
        from app.services.bultos_service import etiqueta_bultos_detalle

        txt = etiqueta_bultos_detalle(
            tipo_linea=ren.get("tipo_linea"),
            descripcion=ren.get("descripcion"),
            cod_articulo=ren.get("cod_articulo"),
            cantidad=ren.get("cantidad"),
            bultos=int(bultos) if bultos else None,
        )
        if not txt:
            return None
        return {"campo": "Bultos", "valor": txt}

    tango = ren.get("tango_completo") or {}
    if tango:
        df = df_campos_tango(tango)
        fila_b = _fila_bultos()
        if fila_b and not df.empty:
            df = pd.concat([pd.DataFrame([fila_b]), df], ignore_index=True)
        return df

    omitir = {
        "id",
        "tango_completo",
        "regla_color",
        "cantidad_display",
        "tipo_linea",
        "bultos",
    }
    filas = [
        {
            "campo": etiqueta_columna(str(k)),
            "valor": valor_celda_display(v, str(k)),
        }
        for k, v in ren.items()
        if k not in omitir and v is not None and str(v).strip() != ""
    ]
    fila_b = _fila_bultos()
    if fila_b:
        filas.insert(0, fila_b)
    return pd.DataFrame(filas)


def inject_theme(*, dark: bool = False) -> None:
    st.markdown(theme_stylesheet(dark=dark), unsafe_allow_html=True)
    st.markdown(
        """
        <style>
        .module-metrics div[data-testid="stMetric"],
        div[data-testid="stMetric"] label {
            font-size: 0.78rem !important;
        }
        div[data-testid="stMetric"] [data-testid="stMetricValue"] {
            font-size: 1.35rem !important;
        }
        div[data-testid="stMetric"] label p,
        div[data-testid="stMetric"] [data-testid="stMetricLabel"] p {
            color: var(--ink-muted) !important;
        }
        div[data-testid="stMetric"] [data-testid="stMetricValue"] {
            color: var(--ink) !important;
        }
        .module-metrics.pend-filter-on [data-testid="column"]:nth-child(4) [data-testid="stMetric"] {
            border-left-color: #c53030 !important;
            background: #fff8f8 !important;
        }
        .module-metrics.pend-filter-on [data-testid="column"]:nth-child(4) [data-testid="stMetricValue"] {
            color: #c53030 !important;
        }
        .leyenda-wrap {
            display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
            margin: 0.35rem 0 0.75rem 0; width: 100%;
        }
        .leyenda-chip {
            display: inline-flex; align-items: center; flex: 0 0 auto; margin: 0;
            padding: 5px 12px; border-radius: 999px; font-size: 0.78rem; font-weight: 600;
            line-height: 1.25; white-space: nowrap; border: 1px solid #00000014;
            box-shadow: 0 1px 3px #0000000c;
        }
        .leyenda-chip.chip-alerta { background: #ffe8e8; color: #7a3030; border-color: #e8b4b4; }
        .leyenda-chip.chip-ok { background: #e8f5e9; color: #1b5e20; border-color: #a5d6a7; }
        .leyenda-chip.chip-info { background: #e3f2fd; color: #1565c0; border-color: #90caf9; }
        .leyenda-chip.chip-luz { background: #fff8e1; color: #6d4c00; border-color: #ffe082; }
        .dash-card {
            position: relative; border-radius: 16px; border: 1px solid var(--border);
            padding: 1rem 1rem 1rem 1.15rem; margin-bottom: 0.35rem;
            box-shadow: 0 2px 10px #0000000d; min-height: 4.5rem;
            background: var(--surface);
        }
        .dash-card:hover { transform: translateY(-1px); box-shadow: 0 4px 14px #00000012; }
        .dash-card-accent {
            position: absolute; left: 0; top: 0; bottom: 0; width: 6px;
            border-radius: 16px 0 0 16px;
        }
        .dash-card-body { color: var(--ink); font-size: 0.92rem; line-height: 1.45; }
        .login-wrap {
            max-width: 420px; margin: 3rem auto 2rem auto; padding: 2rem 2.25rem;
            background: #ffffff; border: 1px solid #dde5f0; border-radius: 18px;
            box-shadow: 0 12px 40px rgba(26, 54, 93, 0.12);
        }
        .users-tab-locked-banner {
            background: var(--surface-2); border: 1px dashed var(--border);
            border-radius: 10px; padding: 0.75rem 1rem; color: var(--ink-muted);
            font-size: 0.88rem; margin-bottom: 1rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def inject_login_shell() -> None:
    """Pantalla de login a full viewport — fondo logístico / mapa."""
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] { display: none !important; }
        [data-testid="stHeader"] { background: transparent !important; }
        [data-testid="stToolbar"] { display: none !important; }
        .stApp {
            background: linear-gradient(145deg, #071525 0%, #0d4f8b 38%, #0f766e 72%, #134e4a 100%) !important;
        }
        .main .block-container {
            max-width: 100% !important;
            padding-top: 3vh !important;
            padding-bottom: 3rem !important;
            z-index: 2;
            position: relative;
        }
        /* Tarjeta login — ancho fijo centrado vía columnas Streamlit */
        form[data-testid="stForm"] {
            background: rgba(255, 255, 255, 0.94);
            backdrop-filter: blur(18px);
            -webkit-backdrop-filter: blur(18px);
            border: 1px solid rgba(255, 255, 255, 0.7);
            border-radius: 18px;
            padding: 1.35rem 1.5rem 1.15rem;
            box-shadow: 0 20px 44px rgba(0, 0, 0, 0.22);
            margin: 0;
        }
        form[data-testid="stForm"] .login-form-title {
            font-weight: 700;
            color: #1a365d;
            font-size: 1.08rem;
            margin: 0 0 0.85rem 0;
            padding: 0;
        }
        form[data-testid="stForm"] label[data-testid="stWidgetLabel"] p {
            font-weight: 600 !important;
            color: #475569 !important;
            font-size: 0.82rem !important;
        }
        form[data-testid="stForm"] input {
            min-height: 2.85rem !important;
            height: 2.85rem !important;
            padding: 0.55rem 0.85rem !important;
            border-radius: 10px !important;
            border: 1px solid #cbd5e1 !important;
            background: #ffffff !important;
            font-size: 0.95rem !important;
            color: #1e293b !important;
        }
        form[data-testid="stForm"] input::placeholder {
            color: #94a3b8 !important;
        }
        form[data-testid="stForm"] [data-testid="stTextInput"] {
            margin-bottom: 0.35rem;
        }
        form[data-testid="stForm"] button[kind="primaryFormSubmit"],
        form[data-testid="stForm"] button[data-testid="stFormSubmitButton"] {
            min-height: 2.85rem !important;
            border-radius: 10px !important;
            font-weight: 600 !important;
            margin-top: 0.5rem !important;
        }
        .login-hero {
            text-align: center;
            margin-bottom: 1.1rem;
            color: #fff;
        }
        .login-scene {
            position: fixed;
            inset: 0;
            z-index: 0;
            pointer-events: none;
            overflow: hidden;
        }
        .login-scene-grid {
            position: absolute;
            inset: -20%;
            background-image:
                linear-gradient(rgba(255,255,255,0.04) 1px, transparent 1px),
                linear-gradient(90deg, rgba(255,255,255,0.04) 1px, transparent 1px);
            background-size: 48px 48px;
            transform: perspective(600px) rotateX(58deg) scale(1.4);
            transform-origin: center 80%;
            opacity: 0.55;
            animation: loginGridDrift 28s linear infinite;
        }
        @keyframes loginGridDrift {
            0% { background-position: 0 0, 0 0; }
            100% { background-position: 48px 48px, 48px 48px; }
        }
        .login-scene-glow {
            position: absolute;
            width: 70vmax;
            height: 70vmax;
            border-radius: 50%;
            filter: blur(80px);
            opacity: 0.35;
        }
        .login-scene-glow.a {
            top: -15%;
            left: -10%;
            background: #3182ce;
        }
        .login-scene-glow.b {
            bottom: -20%;
            right: -15%;
            background: #14b8a6;
        }
        .login-scene-map {
            position: absolute;
            inset: 0;
            opacity: 0.22;
        }
        .login-scene-map svg {
            width: 100%;
            height: 100%;
        }
        .login-route {
            fill: none;
            stroke: rgba(255,255,255,0.45);
            stroke-width: 1.2;
            stroke-dasharray: 6 8;
            animation: loginRouteFlow 18s linear infinite;
        }
        .login-route.delay { animation-delay: -6s; opacity: 0.7; }
        @keyframes loginRouteFlow {
            to { stroke-dashoffset: -120; }
        }
        .login-pin {
            fill: #fbbf24;
            filter: drop-shadow(0 0 6px rgba(251, 191, 36, 0.8));
            animation: loginPinPulse 2.8s ease-in-out infinite;
        }
        .login-pin.b { fill: #38bdf8; animation-delay: -1.2s; }
        .login-pin.c { fill: #34d399; animation-delay: -2s; }
        @keyframes loginPinPulse {
            0%, 100% { opacity: 0.75; transform: scale(1); }
            50% { opacity: 1; transform: scale(1.15); }
        }
        .login-scene-overlay {
            position: absolute;
            inset: 0;
            background: linear-gradient(
                180deg,
                rgba(7, 21, 37, 0.15) 0%,
                rgba(7, 21, 37, 0.45) 55%,
                rgba(7, 21, 37, 0.72) 100%
            );
        }
        .login-hero-icon {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 3.25rem;
            height: 3.25rem;
            border-radius: 14px;
            background: linear-gradient(135deg, rgba(49, 130, 206, 0.35), rgba(20, 184, 166, 0.35));
            border: 1px solid rgba(255,255,255,0.25);
            backdrop-filter: blur(8px);
            font-size: 1.55rem;
            margin-bottom: 0.65rem;
            box-shadow: 0 8px 24px rgba(0,0,0,0.2);
        }
        .login-hero h1 {
            font-size: 1.65rem !important;
            font-weight: 700 !important;
            color: #ffffff !important;
            margin: 0 0 0.35rem 0 !important;
            letter-spacing: -0.02em;
        }
        .login-hero .login-tagline {
            font-size: 0.92rem;
            color: rgba(255,255,255,0.82);
            margin: 0;
            line-height: 1.45;
        }
        .login-hero .login-brand {
            font-size: 0.76rem;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            color: rgba(255,255,255,0.55);
            margin-top: 0.5rem;
        }
        .login-foot-wrap {
            text-align: center;
            margin-top: 0.85rem;
        }
        .login-foot-wrap .login-foot {
            font-size: 0.78rem;
            color: rgba(255, 255, 255, 0.62);
            text-align: center;
            margin: 0;
        }
        .login-kpis {
            display: flex;
            justify-content: center;
            gap: 1.25rem;
            margin-top: 1.25rem;
            flex-wrap: wrap;
        }
        .login-kpi {
            font-size: 0.72rem;
            color: rgba(255,255,255,0.65);
            text-align: center;
        }
        .login-kpi strong {
            display: block;
            color: rgba(255,255,255,0.92);
            font-size: 0.82rem;
            margin-bottom: 0.1rem;
        }
        .top-watermark { display: none !important; }
        </style>
        <div class="login-scene" aria-hidden="true">
            <div class="login-scene-glow a"></div>
            <div class="login-scene-glow b"></div>
            <div class="login-scene-grid"></div>
            <div class="login-scene-map">
                <svg viewBox="0 0 1200 800" preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg">
                    <path class="login-route" d="M120,520 C280,420 360,380 520,340 S780,280 920,220 S1080,180 1140,140"/>
                    <path class="login-route delay" d="M80,620 C240,560 400,500 560,460 S820,400 980,360 S1100,320 1160,280"/>
                    <path class="login-route" d="M200,680 C340,620 480,580 640,520 S880,440 1020,400"/>
                    <circle class="login-pin" cx="520" cy="340" r="7"/>
                    <circle class="login-pin b" cx="920" cy="220" r="6"/>
                    <circle class="login-pin c" cx="640" cy="520" r="6"/>
                    <circle class="login-pin" cx="280" cy="480" r="5" opacity="0.8"/>
                    <circle class="login-pin b" cx="980" cy="360" r="5" opacity="0.8"/>
                </svg>
            </div>
            <div class="login-scene-overlay"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _login_hero_html() -> str:
    return """
        <div class="login-hero">
            <div class="login-hero-icon">🚚</div>
            <h1>Control de Fletes</h1>
            <p class="login-tagline">Control logístico · geolocalización · tarifarios y rutas</p>
            <p class="login-brand">SommierCenter · Wamaro · TOP</p>
        </div>
    """


def inject_top_watermark() -> None:
    st.markdown(
        '<div class="top-watermark" aria-hidden="true">'
        "Creado por Proyecto y Transformación Operativa (TOP)"
        "</div>",
        unsafe_allow_html=True,
    )


MODULE_DARK_BG: dict[str, str] = {
    "Dashboard": "#1a2740",
    "MAESTRO": "#1a2f4a",
    "Resumen": "#2a1f18",
    "Fletes": "#142e2a",
    "Configuración": "#1e293b",
    "CLICPAQ": "#2e1065",
    "FRANSOF": "#3b2206",
    "ALFARO": "#3f0d1a",
    "LBO": "#0c3d5c",
    "Proveedor a elegir": "#2a1f18",
}


def inject_module_accent(pagina: str) -> None:
    """Variables CSS y acento del módulo activo."""
    theme = _theme_for(pagina)
    mod_bg = theme["bg"]
    if st.session_state.get("dark_mode"):
        mod_bg = MODULE_DARK_BG.get(pagina, "#1e293b")
    st.markdown(
        f"""
        <style>
        :root {{
            --mod-accent: {theme["accent"]};
            --mod-accent2: {theme["accent2"]};
            --mod-bg: {mod_bg};
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_page_header(titulo: str, subtitulo: str, theme_key: str) -> None:
    theme = _theme_for(theme_key)
    icon = theme.get("icon", "")
    st.markdown(
        f"""
        <div class="page-header">
            <h1><span class="page-header-icon">{icon}</span>{html_lib.escape(titulo)}</h1>
            <p class="page-header-caption">{html_lib.escape(subtitulo)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


@contextmanager
def _panel_acciones(theme_key: str, titulo: str = "Operaciones"):
    """Recuadro destacado para filtros, botones y métricas operativas."""
    _ = _theme_for(theme_key)
    with st.container(border=True):
        st.markdown(
            f'<p class="panel-acciones-label">{html_lib.escape(titulo)}</p>',
            unsafe_allow_html=True,
        )
        yield


def _render_ayuda_referencia(
    titulo: str,
    secciones: list[tuple[str, str]],
    *,
    expanded: bool = False,
    html_indices: frozenset[int] | None = None,
) -> None:
    if not secciones:
        return
    html_idx = html_indices or frozenset()
    with st.expander(titulo, expanded=expanded):
        for i, (subtitulo, cuerpo) in enumerate(secciones):
            if subtitulo:
                st.markdown(f"**{subtitulo}**")
            if i in html_idx:
                st.markdown(cuerpo, unsafe_allow_html=True)
            else:
                st.markdown(cuerpo)
            if i < len(secciones) - 1:
                st.divider()


def _render_ayuda_grilla(
    *,
    siglas: str = "",
    notas: str = "",
    paginacion: str = "",
) -> None:
    with st.expander("Ayuda de la grilla", expanded=False):
        st.markdown("Seleccioná **una fila** para ver el detalle abajo.")
        if paginacion:
            st.caption(paginacion)
        if notas:
            st.markdown(notas)
        if siglas:
            st.caption(siglas)


def _html_leyenda_operativa() -> str:
    return """
        <div class="leyenda-wrap">
            <span class="leyenda-chip chip-alerta">● Revisar</span>
            <span class="leyenda-chip chip-ok">● OK</span>
            <span class="leyenda-chip chip-info">🔍 Detalle</span>
            <span class="leyenda-chip chip-luz">Luz = columna a revisar</span>
        </div>
        """


def _render_leyenda_operativa() -> None:
    st.markdown(_html_leyenda_operativa(), unsafe_allow_html=True)


def api_client() -> httpx.Client:
    return httpx.Client(base_url=API_URL, timeout=120.0)


def _auth_headers() -> dict[str, str]:
    token = st.session_state.get(AUTH_TOKEN_KEY)
    return {"X-Auth-Token": token} if token else {}


def _is_super_admin() -> bool:
    return bool(st.session_state.get(AUTH_SUPER_KEY))


def _auth_get_json(path: str) -> Any:
    with httpx.Client(base_url=API_URL, timeout=30.0) as client:
        r = client.get(path, headers=_auth_headers())
        r.raise_for_status()
        return r.json()


def _auth_post_json(path: str, payload: dict[str, Any]) -> Any:
    with httpx.Client(base_url=API_URL, timeout=30.0) as client:
        r = client.post(path, json=payload, headers=_auth_headers())
        r.raise_for_status()
        return r.json()


def _auth_delete(path: str) -> None:
    with httpx.Client(base_url=API_URL, timeout=30.0) as client:
        r = client.delete(path, headers=_auth_headers())
        r.raise_for_status()


def _auth_put_json(path: str, payload: dict[str, Any]) -> Any:
    with httpx.Client(base_url=API_URL, timeout=30.0) as client:
        r = client.put(path, json=payload, headers=_auth_headers())
        r.raise_for_status()
        return r.json()


def _auth_patch_json(path: str, payload: dict[str, Any]) -> Any:
    with httpx.Client(base_url=API_URL, timeout=30.0) as client:
        r = client.patch(path, json=payload, headers=_auth_headers())
        r.raise_for_status()
        return r.json()


def _clear_auth_session() -> None:
    for key in (AUTH_TOKEN_KEY, AUTH_USER_KEY, AUTH_SUPER_KEY):
        st.session_state.pop(key, None)


def _set_auth_session(token: str, username: str, is_super_admin: bool) -> None:
    st.session_state[AUTH_TOKEN_KEY] = token
    st.session_state[AUTH_USER_KEY] = username
    st.session_state[AUTH_SUPER_KEY] = is_super_admin


def _restore_auth_session() -> bool:
    token = st.session_state.get(AUTH_TOKEN_KEY)
    if not token:
        return False
    if not check_health_cached():
        return bool(st.session_state.get(AUTH_USER_KEY))
    try:
        me = _auth_get_json("/auth/me")
        _set_auth_session(token, me["username"], bool(me.get("is_super_admin")))
        return True
    except Exception:
        _clear_auth_session()
        return False


def _auth_logout() -> None:
    try:
        if st.session_state.get(AUTH_TOKEN_KEY) and check_health_cached():
            with httpx.Client(base_url=API_URL, timeout=10.0) as client:
                client.post("/auth/logout", headers=_auth_headers())
    except Exception:
        pass
    _clear_auth_session()
    for key in ("login_user_input", "login_pass_input", "login_form_submitted"):
        st.session_state.pop(key, None)


def _pagina_login() -> None:
    inject_login_shell()

    _sp1, col, _sp2 = st.columns([1, 1.05, 1])

    with col:
        st.markdown(_login_hero_html(), unsafe_allow_html=True)

        if not check_health_cached():
            st.error("El servidor no está disponible. Ejecutá **Iniciar_Fletes.bat** e intentá de nuevo.")
            return

        for _lk in ("login_user_input", "login_pass_input"):
            if _lk not in st.session_state:
                st.session_state[_lk] = ""

        with st.form("login_form", clear_on_submit=False):
            st.markdown('<p class="login-form-title">Iniciar sesión</p>', unsafe_allow_html=True)
            usuario = st.text_input(
                "Usuario",
                placeholder="Ingresá tu usuario",
                key="login_user_input",
                autocomplete="off",
            )
            clave = st.text_input(
                "Contraseña",
                type="password",
                placeholder="Ingresá tu contraseña",
                key="login_pass_input",
                autocomplete="new-password",
            )
            submit = st.form_submit_button("Entrar", type="primary", use_container_width=True)

        st.markdown(
            """
            <div class="login-foot-wrap">
              <p class="login-foot">Acceso restringido — contactá al administrador TOP si no tenés usuario.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            """
            <div class="login-kpis">
                <div class="login-kpi"><strong>29</strong> sucursales</div>
                <div class="login-kpi"><strong>3</strong> mundos logísticos</div>
                <div class="login-kpi"><strong>Km</strong> tarifario AMBA</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if submit:
            if not (usuario or "").strip():
                st.error("Ingresá tu usuario.")
                return
            if not clave:
                st.error("Ingresá tu contraseña.")
                return
            try:
                with httpx.Client(base_url=API_URL, timeout=30.0) as client:
                    r = client.post(
                        "/auth/login",
                        json={"username": usuario.strip(), "password": clave},
                    )
                    r.raise_for_status()
                    data = r.json()
                _set_auth_session(data["token"], data["username"], bool(data.get("is_super_admin")))
                st.session_state.pop("login_user_input", None)
                st.session_state.pop("login_pass_input", None)
                st.rerun()
            except httpx.HTTPStatusError as exc:
                st.error(_detalle_error_api(exc))
            except Exception as exc:
                st.error(str(exc))


def _config_seguridad() -> None:
    """Login, contraseña propia y (super admin) altas/bajas de usuarios con acceso."""
    is_super = _is_super_admin()
    logged = st.session_state.get(AUTH_USER_KEY) or ""
    rol_txt = "Super administrador" if is_super else "Operador"

    st.subheader("Seguridad y acceso")
    st.caption(
        "La aplicación exige **usuario y contraseña** al entrar. "
        "Solo quienes figuren acá abajo pueden usar el sistema."
    )

    st.markdown("#### Tu sesión")
    c1, c2 = st.columns(2)
    c1.metric("Usuario conectado", logged or "—")
    c2.metric("Rol", rol_txt)

    with st.form("cfg_mi_password", clear_on_submit=True):
        st.markdown("**Cambiar mi contraseña**")
        actual_pass = st.text_input("Contraseña actual", type="password", key="cfg_mi_pass_actual")
        nueva_pass = st.text_input("Nueva contraseña", type="password", key="cfg_mi_pass_nueva")
        nueva_pass2 = st.text_input("Repetir nueva contraseña", type="password", key="cfg_mi_pass_nueva2")
        if st.form_submit_button("Actualizar mi contraseña", type="primary"):
            if not actual_pass:
                st.error("Ingresá tu contraseña actual.")
            elif nueva_pass != nueva_pass2:
                st.error("Las contraseñas nuevas no coinciden.")
            elif len(nueva_pass or "") < 6:
                st.error("La nueva contraseña debe tener al menos 6 caracteres.")
            else:
                try:
                    _auth_post_json(
                        "/auth/me/password",
                        {"current_password": actual_pass, "new_password": nueva_pass},
                    )
                    st.success("Contraseña actualizada. Cerrá sesión y volvé a entrar.")
                    _auth_logout()
                    st.rerun()
                except httpx.HTTPStatusError as exc:
                    st.error(_detalle_error_api(exc))
                except Exception as exc:
                    st.error(str(exc))

    st.markdown("---")
    st.markdown("#### Usuarios con acceso a la app")

    if not is_super:
        st.markdown(
            """
            <div class="users-tab-locked-banner">
              🔒 Solo el <strong>super administrador</strong> puede dar de alta, editar o quitar usuarios.
              Si necesitás acceso para alguien más, pedíselo al administrador TOP.
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    st.caption(
        "Como super administrador podés agregar o quitar usuarios, cambiar roles y restablecer claves. "
        "Las contraseñas están cifradas: **no se pueden ver**, solo restablecer."
    )

    try:
        users = _auth_get_json("/auth/usuarios")
    except Exception as exc:
        st.error(f"No se pudo cargar la lista de usuarios: {exc}")
        return

    n_super = sum(1 for u in users if u.get("is_super_admin"))
    n_activos = sum(1 for u in users if u.get("activo"))
    m1, m2, m3 = st.columns(3)
    m1.metric("Usuarios totales", len(users))
    m2.metric("Super administradores", n_super)
    m3.metric("Activos", n_activos)

    if users:
        filas = []
        for u in users:
            filas.append(
                {
                    "Usuario": u["username"],
                    "Rol": "Super administrador" if u.get("is_super_admin") else "Operador",
                    "Estado": "Activo" if u.get("activo") else "Inactivo",
                    "Alta": (u.get("created_at") or "")[:10] or "—",
                }
            )
        st.dataframe(
            pd.DataFrame(filas),
            width="stretch",
            hide_index=True,
            height=min(280, 48 + 35 * len(filas)),
        )

    st.markdown("**Agregar usuario**")
    c_new, c_rol = st.columns([2, 1])
    with c_new:
        nuevo_user = st.text_input("Usuario nuevo", key="cfg_user_new")
        nueva_pass = st.text_input(
            "Contraseña inicial",
            type="password",
            key="cfg_user_pass",
            help="Mínimo 6 caracteres.",
        )
    with c_rol:
        nuevo_rol = st.selectbox("Rol", ["Operador", "Super administrador"], key="cfg_user_new_rol")
    if st.button("Agregar usuario", type="primary", key="cfg_user_add"):
        try:
            _auth_post_json(
                "/auth/usuarios",
                {
                    "username": nuevo_user,
                    "password": nueva_pass,
                    "is_super_admin": nuevo_rol == "Super administrador",
                },
            )
            st.success(f"Usuario «{nuevo_user.strip().lower()}» creado.")
            st.rerun()
        except httpx.HTTPStatusError as exc:
            st.error(_detalle_error_api(exc))
        except Exception as exc:
            st.error(str(exc))

    if not users:
        return

    st.markdown("---")
    st.markdown("**Administrar usuario**")
    opciones_admin = [u["username"] for u in users]
    sel = st.selectbox("Seleccionar usuario", opciones_admin, key="cfg_user_edit_sel")
    actual = next((u for u in users if u["username"] == sel), None)
    if actual is None:
        return

    es_top = sel == "top"
    if es_top:
        st.info("Usuario principal del sistema — no se puede desactivar ni quitar super admin.")

    with st.form("cfg_user_edit_form", clear_on_submit=False):
        rol_edit = st.selectbox(
            "Rol",
            ["Operador", "Super administrador"],
            index=1 if actual.get("is_super_admin") else 0,
            disabled=es_top,
            key="cfg_user_edit_rol",
        )
        activo_edit = st.checkbox(
            "Usuario activo (puede iniciar sesión)",
            value=bool(actual.get("activo", True)),
            disabled=es_top,
            key="cfg_user_edit_activo",
        )
        st.markdown("**Restablecer contraseña** (opcional)")
        st.caption("Dejá en blanco para no cambiar la clave.")
        pass1 = st.text_input("Nueva contraseña", type="password", key="cfg_user_edit_pass1")
        pass2 = st.text_input("Repetir contraseña", type="password", key="cfg_user_edit_pass2")

        if st.form_submit_button("Guardar cambios", type="primary"):
            payload: dict[str, Any] = {
                "is_super_admin": rol_edit == "Super administrador",
                "activo": activo_edit,
            }
            if pass1 or pass2:
                if pass1 != pass2:
                    st.error("Las contraseñas no coinciden.")
                    return
                if len(pass1) < 6:
                    st.error("La contraseña debe tener al menos 6 caracteres.")
                    return
                payload["password"] = pass1
            try:
                _auth_patch_json(f"/auth/usuarios/{sel}", payload)
                st.success(f"Cambios guardados para «{sel}».")
                if payload.get("password") and sel == st.session_state.get(AUTH_USER_KEY):
                    st.warning("Cambiaste tu propia contraseña: cerrá sesión y volvé a entrar.")
                st.rerun()
            except httpx.HTTPStatusError as exc:
                st.error(_detalle_error_api(exc))
            except Exception as exc:
                st.error(str(exc))

    a1, a2 = st.columns([1, 2])
    with a1:
        if st.button("Cerrar sesiones del usuario", key="cfg_user_revoke_sess", use_container_width=True):
            try:
                r = _auth_post_json(f"/auth/usuarios/{sel}/cerrar-sesiones", {})
                st.success(f"Sesiones cerradas: {r.get('cerradas', 0)}")
            except httpx.HTTPStatusError as exc:
                st.error(_detalle_error_api(exc))
    with a2:
        st.caption("Forzá cierre de sesión si perdió acceso o hay que renovar el login.")

    if not actual.get("is_super_admin"):
        if st.button("Quitar acceso (eliminar usuario)", key="cfg_user_del_btn", type="secondary"):
            try:
                _auth_delete(f"/auth/usuarios/{sel}")
                st.success(f"Usuario «{sel}» eliminado.")
                st.rerun()
            except httpx.HTTPStatusError as exc:
                st.error(_detalle_error_api(exc))

    with st.expander("Roles y seguridad"):
        st.markdown(
            """
            | Rol | Permisos |
            |-----|----------|
            | **Operador** | Toda la app salvo gestión de usuarios y cierre mensual destructivo. |
            | **Super administrador** | Todo + usuarios + cierre mensual. |

            - Sin usuario activo en esta lista **no hay acceso** a la app (pantalla de login).
            - Las contraseñas **nunca** se muestran (almacenamiento cifrado).
            - Al cambiar contraseña o desactivar, se cierran las sesiones abiertas.
            - Debe quedar **al menos un** super administrador activo.
            """
        )


def _config_usuarios() -> None:
    """Compatibilidad — usar _config_seguridad."""
    _config_seguridad()


def _detalle_error_api(exc: Exception) -> str:
    """Mensaje legible de error FastAPI (detail) para mostrar en UI."""
    resp = getattr(exc, "response", None)
    if resp is not None:
        try:
            data = resp.json()
            detail = data.get("detail")
            if isinstance(detail, list):
                return "; ".join(str(d) for d in detail)
            if detail:
                return str(detail)
        except Exception:
            pass
        text = getattr(resp, "text", None)
        if text:
            return str(text)[:500]
    return str(exc)


def check_health() -> bool:
    base = API_URL.removesuffix("/api/v1").rstrip("/")
    try:
        with httpx.Client(timeout=5.0) as c:
            c.get(f"{base}/health").raise_for_status()
            return True
    except Exception:
        return False


@st.cache_data(ttl=30, show_spinner=False)
def check_health_cached() -> bool:
    """Evita ping HTTP en cada rerun / cambio de menú."""
    return check_health()


@st.cache_data(ttl=30, show_spinner=False)
def api_build_cached() -> str | None:
    base = API_URL.removesuffix("/api/v1").rstrip("/")
    try:
        with httpx.Client(timeout=5.0) as c:
            r = c.get(f"{base}/health")
            r.raise_for_status()
            return r.json().get("build")
    except Exception:
        return None


def api_build_actual() -> str | None:
    return api_build_cached()


def api_es_actual() -> bool:
    return api_build_cached() == API_BUILD_ESPERADO


def filtrar_df_zona_proveedor(df: pd.DataFrame, proveedor: str | None) -> pd.DataFrame:
    """Filtro por destino (respaldo si la API en ejecución es vieja)."""
    if not proveedor or df.empty or "PROVINCIA" not in df.columns:
        return df
    vista_fn = caso_en_vista_proveedor
    if vista_fn is None:
        return df

    def _ok(row: pd.Series) -> bool:
        try:
            return bool(
                vista_fn(
                    proveedor,
                    row.get("PROVINCIA"),
                    row.get("LOCALIDAD"),
                    transporte_cod=row.get("_transporte_cod") or row.get("NRO TRANSP"),
                    transporte_nombre=row.get("TRANSPORTE"),
                    proveedor_asignado=row.get("PROVEEDOR"),
                )
            )
        except TypeError:
            return bool(
                vista_fn(
                    proveedor,
                    row.get("PROVINCIA"),
                    row.get("LOCALIDAD"),
                )
            )

    filtrado = df[df.apply(_ok, axis=1)]
    return pd.DataFrame(filtrado)


def _opciones_mes_control() -> list[tuple[int, int, str]]:
    from datetime import date

    hoy = date.today()
    meses: list[tuple[int, int, str]] = []
    y, m = hoy.year, hoy.month
    nombres = (
        "Enero",
        "Febrero",
        "Marzo",
        "Abril",
        "Mayo",
        "Junio",
        "Julio",
        "Agosto",
        "Septiembre",
        "Octubre",
        "Noviembre",
        "Diciembre",
    )
    for _ in range(18):
        meses.append((y, m, f"{nombres[m - 1]} {y}"))
        m -= 1
        if m < 1:
            m = 12
            y -= 1
    return meses


SESSION_MES_CONTROL_IDX = "global_mes_control_idx"


def _ui_mes_control_adrian() -> dict[str, Any]:
    """Mes a controlar — Modo TOP siempre usa fecha de entrega (LOG diario)."""
    opciones = _opciones_mes_control()
    labels = [o[2] for o in opciones]
    if SESSION_MES_CONTROL_IDX not in st.session_state:
        st.session_state[SESSION_MES_CONTROL_IDX] = 0
    idx = st.selectbox(
        "Mes a controlar",
        range(len(labels)),
        format_func=lambda i: labels[i],
        key=SESSION_MES_CONTROL_IDX,
    )
    anio, mes, label_mes = opciones[idx]
    st.caption(
        f"Casos LOG con **entrega** en **{label_mes}**. "
        "La columna *Fecha pedido* puede ser anterior — el corte operativo es por **entrega**."
    )
    return {"mes_control_anio": anio, "mes_control_mes": mes}


def _ui_filtros_fecha_remito(key_prefix: str) -> dict[str, Any]:
    """Filtros UI: rango Desde–Hasta, campo fecha y estado remito (sin cargar datos)."""
    from datetime import date, timedelta

    hoy = date.today()
    d_defecto = hoy.replace(day=1)
    h_defecto = hoy

    c1, c2, c3, c4 = st.columns([1.2, 1.2, 1.6, 1.5])
    desde = c1.date_input(
        "Desde",
        value=d_defecto,
        max_value=hoy + timedelta(days=60),
        key=f"{key_prefix}_fecha_desde",
        help="Inicio del período a controlar (inclusive).",
    )
    hasta = c2.date_input(
        "Hasta",
        value=h_defecto,
        max_value=hoy + timedelta(days=60),
        key=f"{key_prefix}_fecha_hasta",
        help="Fin del período a controlar (inclusive).",
    )
    campo_ui = c3.selectbox(
        "Filtrar casos por",
        (
            "Solo fecha de entrega",
            "Pedido o entrega (cualquiera)",
            "Solo fecha de pedido",
        ),
        index=0,
        key=f"{key_prefix}_campo_fecha",
        help="Estándar: período = fecha de entrega (mismo criterio DIST y Limansky).",
    )
    campo_map = {
        "Solo fecha de entrega": "entrega",
        "Pedido o entrega (cualquiera)": "cualquiera",
        "Solo fecha de pedido": "pedido",
    }
    campo_api = campo_map[campo_ui]
    remito_ui = c4.selectbox(
        "Remito",
        (
            "Todos",
            "Con remito",
            "Sin remito",
            "Sin fecha de entrega",
        ),
        key=f"{key_prefix}_remito_estado",
    )
    remito_map = {
        "Todos": "todos",
        "Con remito": "con_remito",
        "Sin remito": "sin_remito",
        "Sin fecha de entrega": "sin_fecha_entrega",
    }

    if isinstance(desde, tuple):
        desde = desde[0] if desde else d_defecto
    if isinstance(hasta, tuple):
        hasta = hasta[0] if hasta else h_defecto

    dias = (hasta - desde).days + 1 if hasta and desde else 0
    if campo_api == "entrega":
        c1.caption("Corte operativo por **fecha de entrega**.")
    elif campo_api == "pedido":
        c1.caption("Consulta excepcional por **fecha de pedido**.")
    else:
        c1.caption("Pedido **o** entrega en el rango (más amplio).")

    if dias > 62:
        st.warning(
            f"El rango tiene **{dias} días**. Para que la app se mantenga liviana, "
            "preferí períodos de hasta ~2 meses (ej. 15/06 → 15/07)."
        )
    elif dias > 0:
        st.caption(
            f"Período en pantalla: **{desde.strftime('%d/%m/%Y')}** → "
            f"**{hasta.strftime('%d/%m/%Y')}** ({dias} día{'s' if dias != 1 else ''}). "
            "Tocá **Cargar período** para traer datos."
        )

    return {
        "campo_fecha": campo_api,
        "remito_estado": remito_map[remito_ui],
        "fecha_desde_ui": desde.isoformat() if desde else None,
        "fecha_hasta_ui": hasta.isoformat() if hasta else None,
    }


def _params_sin_mes_si_busca(params: dict[str, Any], buscar: str) -> dict[str, Any]:
    """Con texto de búsqueda, recorrer toda la base importada (sin rango de fechas)."""
    p = dict(params)
    if buscar.strip():
        p.pop("mes_control_anio", None)
        p.pop("mes_control_mes", None)
        p.pop("fecha_desde", None)
        p.pop("fecha_hasta", None)
        p.pop("campo_fecha", None)
        p.pop("fecha_desde_ui", None)
        p.pop("fecha_hasta_ui", None)
    return p


def _firma_filtros_maestro_ui(
    *,
    origen_f: str,
    incluir_excl: bool,
    solo_alerta: bool,
    solo_macheo: bool,
    solo_diff: bool,
    filtros_extra: dict[str, Any],
) -> str:
    return json.dumps(
        {
            "origen": origen_f,
            "incluir_excl": incluir_excl,
            "solo_alerta": solo_alerta,
            "solo_macheo": solo_macheo,
            "solo_diff": solo_diff,
            "filtros_extra": filtros_extra,
        },
        sort_keys=True,
        default=str,
    )


def _invalidar_carga_si_cambian_filtros(
    key_prefix: str,
    firma_ui: str,
    modo_carga_key: str,
    *,
    clear_cache_fn: Any,
) -> None:
    ui_sig_key = f"{key_prefix}_ui_sig"
    if (
        st.session_state.get(ui_sig_key) is not None
        and st.session_state.get(ui_sig_key) != firma_ui
        and st.session_state.get(modo_carga_key)
    ):
        st.session_state.pop(modo_carga_key, None)
        st.session_state.pop(f"{key_prefix}_rango_activo", None)
        clear_cache_fn()
        st.warning(
            "Cambiaste filtros — volvé a tocar **Cargar período** o **Buscar en toda la base**."
        )
    st.session_state[ui_sig_key] = firma_ui


def _render_carga_rango(
    key_prefix: str,
    filtros_extra: dict[str, Any],
    buscar: str,
    *,
    clear_cache_fn: Any,
    modulo: str,
    page_state_key: str | None = None,
) -> str | None:
    """Botones Cargar período / Buscar. Devuelve modo_carga o None (sin datos)."""
    modo_carga_key = f"{key_prefix}_modo_carga"
    fd = filtros_extra.get("fecha_desde_ui")
    fh = filtros_extra.get("fecha_hasta_ui")

    st.markdown("##### Cargar período")
    b1, b2 = st.columns([1.4, 2.6])
    with b1:
        if st.button(
            "Cargar período",
            key=f"{key_prefix}_btn_rango",
            type="primary",
            use_container_width=True,
            disabled=not (fd and fh),
        ):
            if fd and fh and fh < fd:
                st.error("La fecha **Hasta** no puede ser anterior a **Desde**.")
            else:
                st.session_state[modo_carga_key] = "rango"
                st.session_state[f"{key_prefix}_rango_activo"] = {
                    "fecha_desde": fd,
                    "fecha_hasta": fh,
                    "campo_fecha": filtros_extra.get("campo_fecha"),
                    "remito_estado": filtros_extra.get("remito_estado"),
                }
                if page_state_key:
                    st.session_state[page_state_key] = 1
                clear_cache_fn()
                st.rerun()
    with b2:
        if st.button(
            "Buscar en toda la base",
            key=f"{key_prefix}_btn_buscar",
            disabled=not buscar.strip(),
            use_container_width=True,
        ):
            st.session_state[modo_carga_key] = "buscar"
            st.session_state[f"{key_prefix}_q_buscar"] = buscar.strip()
            st.session_state.pop(f"{key_prefix}_rango_activo", None)
            if page_state_key:
                st.session_state[page_state_key] = 1
            clear_cache_fn()
            st.rerun()

    modo_carga = st.session_state.get(modo_carga_key)
    if not modo_carga:
        st.info(
            f"**{modulo}** no carga solo al entrar. Elegí **Desde / Hasta** y tocá "
            "**Cargar período**, o buscá un remito puntual — así la consulta se mantiene liviana."
        )
        return None

    if modo_carga == "rango":
        activo = st.session_state.get(f"{key_prefix}_rango_activo") or {}
        d1 = activo.get("fecha_desde") or fd
        d2 = activo.get("fecha_hasta") or fh
        if d1 and d2:
            from datetime import date

            etiq = (
                f"{date.fromisoformat(d1).strftime('%d/%m/%Y')} → "
                f"{date.fromisoformat(d2).strftime('%d/%m/%Y')}"
            )
            st.caption(f"Cargando período **{etiq}**")
        else:
            st.caption("Cargando período seleccionado…")
    else:
        st.caption(
            f"Búsqueda puntual: **{st.session_state.get(f'{key_prefix}_q_buscar', buscar.strip())}**"
        )
    return str(modo_carga)


def _params_api_rango(
    params: dict[str, Any],
    *,
    key_prefix: str,
    buscar: str,
    modo_carga: str,
) -> dict[str, Any]:
    """Arma params de API: rango activo o búsqueda sin fechas."""
    p = dict(params)
    p.pop("fecha_desde_ui", None)
    p.pop("fecha_hasta_ui", None)
    p.pop("mes_control_anio", None)
    p.pop("mes_control_mes", None)

    if modo_carga == "rango":
        activo = st.session_state.get(f"{key_prefix}_rango_activo") or {}
        fd = activo.get("fecha_desde")
        fh = activo.get("fecha_hasta")
        if not fd or not fh:
            raise ValueError("Definí Desde y Hasta y tocá Cargar período.")
        if fh < fd:
            raise ValueError("La fecha Hasta no puede ser anterior a Desde.")
        p["fecha_desde"] = fd
        p["fecha_hasta"] = fh
        if activo.get("campo_fecha"):
            p["campo_fecha"] = activo["campo_fecha"]
        if activo.get("remito_estado"):
            p["remito_estado"] = activo["remito_estado"]
    elif modo_carga == "buscar":
        qtxt = st.session_state.get(f"{key_prefix}_q_buscar", buscar.strip())
        p["q"] = qtxt
        p = _params_sin_mes_si_busca(p, qtxt)
    return p


def _filtrar_df_buscar(df: pd.DataFrame, buscar: str, columnas: tuple[str, ...]) -> pd.DataFrame:
    q = buscar.strip().upper()
    if not q:
        return df
    mask = pd.Series(False, index=df.index)
    for col in columnas:
        if col in df.columns:
            mask |= df[col].astype(str).str.upper().str.contains(q, na=False)
    return _as_dataframe(df[mask])


_MAESTRO_API_PAGE_SIZE = 150


def get_maestro_filas(**params: Any) -> tuple[dict[str, Any], bool]:
    """GET /maestro paginado; devuelve payload y si la API aplicó filtro de zona."""
    with api_client() as client:
        q = dict(params)
        if q.get("proveedor"):
            q["vista_proveedor"] = q["proveedor"]
        q.setdefault("page_size", _MAESTRO_API_PAGE_SIZE)
        r = client.get("/maestro", params=q, timeout=120.0)
        r.raise_for_status()
        payload = r.json()
        vista = (params.get("proveedor") or "").strip().upper()
        if not vista:
            return payload, True
        hdr = (r.headers.get("X-Maestro-Filtro-Zona") or "").upper()
        return payload, hdr == vista


@st.cache_data(ttl=300, show_spinner=False)
def get_maestro_filas_cached(params_key: str) -> tuple[dict[str, Any], bool]:
    """Cache corto por combinación de filtros (evita re-fetch en reruns)."""
    return get_maestro_filas(**json.loads(params_key))


def _reset_maestro_page_si_cambian_filtros(key_prefix: str, firma: str) -> int:
    """Vuelve a página 1 cuando cambian filtros; devuelve página actual."""
    page_key = f"{key_prefix}_maestro_page"
    sig_key = f"{key_prefix}_maestro_sig"
    if st.session_state.get(sig_key) != firma:
        st.session_state[sig_key] = firma
        st.session_state[page_key] = 1
    page = int(st.session_state.get(page_key, 1) or 1)
    st.session_state[page_key] = page
    return page


def _reset_page_si_buscar_cambia(key_prefix: str, buscar_key: str) -> None:
    """Vuelve a página 1 cuando cambia el texto de búsqueda en grilla."""
    page_key = f"{key_prefix}_maestro_page"
    sig_key = f"{key_prefix}_buscar_sig"
    q = str(st.session_state.get(buscar_key, "") or "").strip()
    if st.session_state.get(sig_key) != q:
        st.session_state[sig_key] = q
        st.session_state[page_key] = 1


def _controles_paginacion_maestro_api(
    key_prefix: str,
    *,
    total: int,
    page: int,
    page_size: int,
    total_pages: int,
    buscar_key: str | None = None,
    buscar_placeholder: str = "Buscar remito, destinatario, localidad…",
) -> int:
    """Controles Anterior/Siguiente contra la API; devuelve número de página (1-based)."""
    page_key = f"{key_prefix}_maestro_page"
    show_nav = total > page_size

    if buscar_key:
        c1, c2, c3, c4 = st.columns([1, 2.2, 1, 2.6])
    else:
        c1, c2, c3 = st.columns([1.2, 2.6, 1.2])
        c4 = None

    with c1:
        if show_nav:
            if st.button("← Anterior", key=f"{key_prefix}_api_prev", disabled=page <= 1):
                st.session_state[page_key] = max(1, page - 1)
                st.rerun()
    fin = min(page * page_size, total)
    inicio = (page - 1) * page_size + 1 if total else 0
    with c2:
        if show_nav:
            st.caption(
                f"Casos **{inicio}–{fin}** de **{total}** · página **{page}/{total_pages}** "
                f"({page_size} por carga)"
            )
        elif total:
            st.caption(f"**{total}** caso(s) en esta vista")
    with c3:
        if show_nav:
            if st.button(
                "Siguiente →",
                key=f"{key_prefix}_api_next",
                disabled=page >= total_pages,
            ):
                st.session_state[page_key] = min(total_pages, page + 1)
                st.rerun()
    if buscar_key and c4 is not None:
        with c4:
            st.text_input(
                "Buscar",
                key=buscar_key,
                placeholder=buscar_placeholder,
                label_visibility="collapsed",
            )

    if not show_nav and not buscar_key:
        return 1
    return page


@st.cache_data(ttl=300, show_spinner=False)
def get_fletes_pagina_cached(params_key: str) -> dict[str, Any]:
    return get_json("/fletes/casos", **json.loads(params_key))


@st.cache_data(ttl=300, show_spinner=False)
def get_fletes_stats_cached(params_key: str) -> dict:
    return get_json("/fletes/stats", **json.loads(params_key))


@st.cache_data(ttl=300, show_spinner=False)
def get_fleteros_cached() -> list[dict]:
    return get_json("/fletes/fleteros")


def _clear_fletes_cache() -> None:
    get_fletes_pagina_cached.clear()
    get_fletes_stats_cached.clear()
    get_fleteros_cached.clear()


@st.cache_data(ttl=300, show_spinner=False)
def get_adrian_resumen_cached(params_key: str) -> dict:
    return get_json("/modo-adrian/resumen", **json.loads(params_key))


@st.cache_data(ttl=300, show_spinner=False)
def get_adrian_dias_cached(params_key: str) -> dict:
    return get_json("/modo-adrian/dias", **json.loads(params_key))


@st.cache_data(ttl=300, show_spinner=False)
def get_adrian_dia_cached(params_key: str) -> dict:
    return get_json("/modo-adrian/dia", **json.loads(params_key))


@st.cache_data(ttl=300, show_spinner=False)
def get_adrian_mes_cached(params_key: str) -> dict:
    return get_json("/modo-adrian/casos", **json.loads(params_key))


def _clear_adrian_cache() -> None:
    get_adrian_resumen_cached.clear()
    get_adrian_dias_cached.clear()
    get_adrian_dia_cached.clear()
    get_adrian_mes_cached.clear()


@st.cache_data(ttl=300, show_spinner=False)
def get_dashboard_stats_cached() -> tuple[dict, dict]:
    return get_json("/envios/stats"), get_json("/mundo1/stats")


@st.cache_data(ttl=300, show_spinner=False)
def get_dashboard_gerencial_cached() -> dict:
    return get_json("/dashboard/gerencial")


@st.cache_data(ttl=300, show_spinner=False)
def get_kpi_entregas_cached(params_key: str) -> dict:
    return get_json("/dashboard/kpi-entregas", **json.loads(params_key))


@st.cache_data(ttl=300, show_spinner=False)
def get_fletes_stats_dashboard_cached(params_key: str) -> dict:
    return get_json("/fletes/stats", **json.loads(params_key))


def get_json(path: str, **params: Any) -> Any:
    with api_client() as client:
        r = client.get(path, params=params)
        r.raise_for_status()
        return r.json()


def post_file(
    path: str,
    file_name: str,
    content: bytes,
    *,
    timeout: float = 600.0,
    **params: str | bool,
) -> Any:
    with httpx.Client(base_url=API_URL, timeout=timeout) as client:
        files = {"file": (file_name, content)}
        q = {k: v for k, v in params.items() if v is not None}
        r = client.post(path, files=files, params=q or None)
        r.raise_for_status()
        return r.json()


def post_json(
    path: str,
    body: dict[str, Any],
    *,
    timeout: float = 180.0,
    **params: str | bool,
) -> Any:
    with httpx.Client(base_url=API_URL, timeout=timeout) as client:
        q = {k: v for k, v in params.items() if v is not None}
        r = client.post(path, json=body, params=q or None)
        r.raise_for_status()
        return r.json()


def style_maestro(df: pd.DataFrame) -> Any:
    if df.empty:
        return df

    def row_style(row: pd.Series) -> list[str]:
        key = row.get("_regla_color") if "_regla_color" in row.index else None
        pair = COLOR_MAP.get(key) if key == "alerta" else None
        styles: list[str] = []
        for col_name in row.index:
            is_control = col_name in MAESTRO_CONTROL
            border = f"border-left: 2px solid {CONTROL_BORDER};" if is_control else ""
            nowrap = (
                "white-space: nowrap;"
                if col_name in MAESTRO_MONEDA or col_name in (
                "FECHA",
                "NRO TRANSP",
                "REMITOS",
                "BULTOS",
            )
                else ""
            )
            if pair:
                bg, fg = pair
                styles.append(
                    f"background-color: {bg}; color: {fg}; {border} {nowrap}"
                )
            elif is_control:
                styles.append(
                    f"background-color: {CONTROL_TINT}; color: #2c3e50; font-weight: 500; {border}"
                )
            else:
                styles.append("color: #2c3e50;")
        return styles

    styled = df.style.apply(row_style, axis=1)
    for col in df.columns:
        if col in MAESTRO_MONEDA:
            styled = styled.format(fmt_pesos_ar, subset=[col], na_rep="")
    if "_regla_color" in df.columns:
        try:
            styled = styled.hide(  # pyright: ignore[reportAttributeAccessIssue]
                subset=["_regla_color"], axis="columns"
            )
        except AttributeError:
            pass
    try:
        styled = styled.format_index(axis=1, formatter=etiqueta_columna)
    except Exception:
        pass
    return styled


def _etiqueta_origen_sucursal(origen: str | None) -> str:
    return {
        "fijada": "Sucursal fijada (Tango)",
        "sugerida": "Sucursal sugerida",
        "calculada": "Sucursal del cálculo",
    }.get(str(origen or ""), "Sucursal")


def _render_distancia_sucursal(info: dict[str, Any] | None) -> None:
    """Bloque legible: sucursal → destino y km."""
    if not info:
        return
    if not info.get("aplica", True):
        if info.get("motivo"):
            st.caption(info["motivo"])
        return

    st.markdown("#### Distancia sucursal → destino")
    cod = info.get("sucursal_cod") or "—"
    nombre = (info.get("sucursal_nombre") or "").strip()
    origen = _etiqueta_origen_sucursal(info.get("origen_sucursal"))
    suc_txt = f"**{cod}**"
    if nombre:
        suc_txt += f" ({nombre})"

    domicilio = (info.get("domicilio") or info.get("destino") or "—").strip()
    km = info.get("distance_km")
    zona = (info.get("zona_etiqueta") or info.get("zona_km") or "").strip()

    if info.get("error_calculo"):
        st.warning(f"No se pudo geocodificar: {info['error_calculo']}")

    if km is not None:
        km_f = float(km)
        km_txt = f"~{km_f:,.1f} km".replace(",", ".") if info.get("es_estimado") else f"{km_f:,.1f} km".replace(",", ".")
        tipo_km = "estimado" if info.get("es_estimado") else "por ruta"
        linea = f"{origen}: {suc_txt} → **{domicilio}** · **{km_txt}** ({tipo_km})"
        if zona:
            linea += f" · Zona **{zona}**"
        st.markdown(linea)
        if info.get("desde_cache_domicilio"):
            st.caption("Km reutilizado de otro remito con el mismo domicilio (sin nueva geocodificación).")
        elif info.get("es_estimado") or info.get("pendiente_calculo"):
            st.caption(
                "Km estimado por localidad. Para medir la ruta real al domicilio, "
                "usá **Fletes → Calcular km** o el botón de abajo."
            )
    elif cod != "—":
        st.info(
            f"{origen}: **{cod}**"
            + (f" ({nombre})" if nombre else "")
            + f" → **{domicilio}**. "
            "Todavía no hay km calculado."
        )
    else:
        st.caption("Sin sucursal asignada todavía para este envío local.")


def _render_cross_seguimiento_caso(det: dict[str, Any]) -> None:
    """Estado operativo cross (planilla Retirado por …) — solo revisión, no factura."""
    cross = det.get("cross_seguimiento")
    if not cross:
        return

    st.markdown("#### Seguimiento cross (planilla operativa)")
    prov = cross.get("proveedor")
    if prov:
        st.write(f"**Operador:** {etiqueta_proveedor(str(prov))}")
    ent = (cross.get("entregado") or "pendiente").upper()
    if ent == "SI":
        st.success(f"**Entregado:** SI · coord. {cross.get('fecha_entrega_coord') or '—'}")
    elif ent == "NO":
        st.error(f"**Entregado:** NO")
    else:
        st.info(f"**Entregado:** pendiente / sin dato en planilla")

    if cross.get("fecha_retiro"):
        st.caption(f"Retiro: {cross['fecha_retiro']}")
    if cross.get("observacion"):
        st.caption(f"Obs planilla: {cross['observacion']}")
    if cross.get("archivo_origen"):
        st.caption(
            f"Fuente: {cross['archivo_origen']}"
            + (f" · hoja «{cross['hoja_origen']}»" if cross.get("hoja_origen") else "")
        )
    if cross.get("match_estado") == "sin_maestro":
        st.warning(
            "Este remito está en la planilla cross pero no en el maestro importado "
            "(otro mes o aún no cargado en Tango)."
        )


def _render_cedol_caso(caso_id: str, det: dict[str, Any]) -> None:
    """CEDOL tarifario (CLICPAQ/ALFARO) con corrección manual opcional."""
    cedol = det.get("cedol") or {}
    if not cedol.get("aplica"):
        return

    st.markdown("#### CEDOL (zona tarifaria)")
    efectivo = cedol.get("cedol_efectivo") or "—"
    auto = cedol.get("cedol_auto") or "—"
    loc = cedol.get("localidad") or ""
    prov = cedol.get("provincia") or ""

    if cedol.get("cedol_manual"):
        st.write(
            f"**CEDOL activo:** `{efectivo}` — corregido manualmente "
            f"(automático sería `{auto}` para {loc}, {prov})"
        )
    else:
        st.write(
            f"**CEDOL activo:** `{efectivo}` — resuelto por destino ({loc}, {prov})"
        )
    st.caption(
        "Códigos del tarifario Mantello (ej. A0 capital Salta, A1 interior). "
        "Si la carga de Tango trae localidad ambigua, podés corregir acá y recalcular."
    )

    opciones = det.get("cedol_opciones") or []
    if not opciones:
        st.caption("Sin códigos CEDOL en el tarifario vigente para este proveedor.")
        return

    idx_auto = 0
    labels = ["Automático (según destino)"]
    values: list[str | None] = [None]
    for cod in opciones:
        labels.append(cod)
        values.append(cod)
        if cod == efectivo and not cedol.get("cedol_manual"):
            idx_auto = len(values) - 1

    default_idx = idx_auto
    if cedol.get("cedol_manual") and efectivo in values:
        default_idx = values.index(efectivo)

    col_sel, col_btn, col_rst = st.columns([2, 1, 1])
    with col_sel:
        sel_label = st.selectbox(
            "CEDOL",
            labels,
            index=default_idx,
            key=f"cedol_sel_{caso_id}",
            label_visibility="collapsed",
        )
    sel_cedol = values[labels.index(sel_label)]

    with col_btn:
        aplicar = st.button(
            "Aplicar y recalcular",
            key=f"cedol_apply_{caso_id}",
            type="primary",
        )
    with col_rst:
        restaurar = st.button("Restaurar automático", key=f"cedol_auto_{caso_id}")

    if aplicar:
        if sel_cedol is None and not cedol.get("cedol_manual"):
            st.info("Ya está en modo automático.")
        else:
            try:
                body: dict[str, Any] = {}
                if sel_cedol is None:
                    body["restaurar_auto"] = True
                else:
                    body["cedol"] = sel_cedol
                with api_client() as c:
                    r = c.post(f"/maestro/caso/{caso_id}/cedol", json=body)
                    r.raise_for_status()
                get_maestro_filas_cached.clear()
                get_adrian_resumen_cached.clear()
                get_adrian_dias_cached.clear()
                get_adrian_dia_cached.clear()
                get_adrian_mes_cached.clear()
                st.success("CEDOL actualizado — recalculando…")
                st.rerun()
            except Exception as exc:
                st.error(f"No se pudo aplicar CEDOL: {_detalle_error_api(exc)}")

    if restaurar:
        if not cedol.get("cedol_manual"):
            st.info("El CEDOL ya es automático.")
        else:
            try:
                with api_client() as c:
                    r = c.post(
                        f"/maestro/caso/{caso_id}/cedol",
                        json={"restaurar_auto": True},
                    )
                    r.raise_for_status()
                get_maestro_filas_cached.clear()
                get_adrian_resumen_cached.clear()
                get_adrian_dias_cached.clear()
                get_adrian_dia_cached.clear()
                get_adrian_mes_cached.clear()
                st.success("CEDOL automático restaurado — recalculando…")
                st.rerun()
            except Exception as exc:
                st.error(f"No se pudo restaurar: {_detalle_error_api(exc)}")


DETALLE_POPUP = "_detalle_popup"


def _render_bloque_detalle_fletes(caso_id: str) -> bool:
    """Detalle operativo Fletes (alertas, km, fletero). Devuelve False si falló."""
    try:
        det = get_json(f"/fletes/caso/{caso_id}")
    except Exception as exc:
        st.error(f"No se pudo cargar detalle Fletes: {exc}")
        return False

    f = det.get("fletes") or {}
    alertas = _parse_alertas_celdas(f.get("_alertas_celdas"))
    if alertas:
        for al in alertas:
            cols_txt = ", ".join(al.get("columnas") or [])
            st.warning(f"**{cols_txt}:** {al.get('motivo', '')}")
    elif f.get("_alerta_motivo"):
        st.warning(str(f["_alerta_motivo"]))
    elif f.get("_regla_motivo"):
        st.info(str(f["_regla_motivo"]))

    st.markdown("#### Flete local (CABA/GBA)")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Fletero", f.get("FLETERO") or "—")
    c2.metric("Sucursal", f.get("SUCURSAL") or "—")
    c3.metric("Km", f.get("KM") or "—")
    c4.metric("Zona km", f.get("ZONA KM") or "—")
    if f.get("TARIFA REF"):
        st.write(f"**Tarifa ref.:** {f.get('TARIFA REF')}")
    if f.get("total"):
        st.write(f"**Total ref. (log + seguro):** {fmt_pesos_ar(f.get('total'))}")
    if f.get("_pedido_cobro"):
        st.caption(f"**Pedido:** {f['_pedido_cobro']}")
    for adv in f.get("_pedido_advertencias") or []:
        st.caption(adv)

    sol = det.get("solicitud_drive")
    if sol:
        st.markdown("#### Solicitud Drive")
        st.write(
            f"**{sol.get('fletero_corto') or sol.get('fletero') or '—'}** · "
            f"pedido `{sol.get('nro_pedido') or '—'}` · "
            f"estado {sol.get('estado') or '—'}"
        )

    dist_info = det.get("distancia_sucursal") or {}
    _render_distancia_sucursal(dist_info)
    if dist_info.get("aplica") and (
        dist_info.get("pendiente_calculo") or dist_info.get("es_estimado")
    ):
        if st.button("Calcular km real", key=f"fletes_calc_km_{caso_id}", type="primary"):
            try:
                with api_client() as c:
                    r = c.post(f"/fletes/caso/{caso_id}/calcular-km")
                    r.raise_for_status()
                get_fletes_pagina_cached.clear()
                st.success("Distancia calculada — actualizando…")
                st.rerun()
            except Exception as exc:
                st.error(f"No se pudo calcular: {exc}")

    renglones = det.get("renglones") or []
    if renglones:
        st.markdown("#### Artículos del caso")
        st.dataframe(
            pd.DataFrame(renglones),
            width="stretch",
            hide_index=True,
            height=min(220, 40 + 35 * len(renglones)),
        )
    return True


def _omitir_campo_renglon(clave: str) -> bool:
    return clave in {
        "id",
        "tango_completo",
        "tipo_linea",
        "cantidad_display",
        "bultos",
        "regla_color",
    } or clave.startswith("_")


def _campos_planos_renglon(ren: dict[str, Any]) -> dict[str, Any]:
    """Une Tango + columnas del renglón (sin JSON crudo en pantalla)."""
    out: dict[str, Any] = {}
    tango = ren.get("tango_completo")
    if isinstance(tango, dict):
        for k, v in tango.items():
            if _omitir_campo_renglon(str(k)):
                continue
            out[str(k)] = v
    for k, v in ren.items():
        if _omitir_campo_renglon(str(k)):
            continue
        if v is None or (isinstance(v, str) and not str(v).strip()):
            continue
        out[str(k)] = v
    return out


def _valor_celda_editable(valor: Any) -> str:
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "sí" if valor else "no"
    if isinstance(valor, float) and pd.isna(valor):
        return ""
    if isinstance(valor, (dict, list)):
        return json.dumps(valor, ensure_ascii=False, default=str)
    return str(valor).strip()


def _parse_valor_editado(clave: str, texto: str, original: Any) -> Any:
    txt = (texto or "").strip()
    if isinstance(original, bool) or clave in {
        "excluir_planilla",
        "alerta_clickpack",
        "abona_wamaro",
        "entrega_cliente_sospechosa",
        "requiere_elegir_proveedor",
        "cedol_manual",
    }:
        return txt.lower() in ("1", "true", "si", "sí", "yes", "s")
    if isinstance(original, (int, float)) and not isinstance(original, bool):
        if txt == "":
            return None
        return float(txt.replace(",", "."))
    if clave in {
        "cantidad",
        "m3",
        "costo_total",
        "costo_tarifario",
        "diferencia",
        "prefactura_proveedor",
    }:
        if txt == "":
            return None
        try:
            return float(txt.replace(",", "."))
        except ValueError:
            return txt
    return txt or None


_CAMPOS_EDITABLES_DETALLE: frozenset[str] = frozenset(
    {
        # Control operativo (Adrián: casos puntuales / liquidación)
        "excluir_planilla",
        "proveedor_tarifa",
        "costo_tarifario",
        "costo_total",
        "prefactura_proveedor",
        "sucursal_cc",
        "observaciones",
        "regla_motivo",
        # Flags / postventa
        "abona_wamaro",
        "alerta_clickpack",
        "cedol_manual",
        "entrega_cliente_sospechosa",
        "requiere_elegir_proveedor",
        "sub_tipo_gestion",
        "tipo_gestion",
    }
)
_CAMPOS_BOOL_DETALLE: frozenset[str] = frozenset(
    {
        "abona_wamaro",
        "alerta_clickpack",
        "cedol_manual",
        "entrega_cliente_sospechosa",
        "excluir_planilla",
        "requiere_elegir_proveedor",
    }
)
# Orden preferido en la tabla verde (lo crítico arriba).
_ORDEN_EDITABLES_DETALLE: tuple[str, ...] = (
    "excluir_planilla",
    "proveedor_tarifa",
    "costo_tarifario",
    "costo_total",
    "prefactura_proveedor",
    "sucursal_cc",
    "observaciones",
    "regla_motivo",
    "tipo_gestion",
    "sub_tipo_gestion",
    "alerta_clickpack",
    "abona_wamaro",
    "cedol_manual",
    "entrega_cliente_sospechosa",
    "requiere_elegir_proveedor",
)


def _render_renglones_tango_editables(caso_id: str, renglones: list[dict[str, Any]]) -> None:
    """Detalle: campos editables alineados al feedback de control/liquidación."""
    st.markdown("#### Renglones Tango (artículos / postventa)")
    st.caption(
        "Filas en **verde** = editables. "
        "**Anular remito** marca el caso como fuera de liquidación (antes: excluir planilla). "
        "**Costo tarifario / total:** se calculan solos con el tarifario cargado al cambiar "
        "proveedor; solo editálos a mano si el cálculo automático está mal (ej. multi‑artículo). "
        "Sucursal CC y observaciones: para centro de costo y notas de control."
    )
    st.markdown(
        """
        <style>
        div[class*="st-key-det_ren_ok_"] [data-testid="stDataFrame"] td,
        div[class*="st-key-det_ren_ok_"] [role="gridcell"] {
            background-color: #dcfce7 !important;
        }
        div[class*="st-key-det_ren_ok_"] [data-testid="stDataFrame"] th,
        div[class*="st-key-det_ren_ok_"] [role="columnheader"] {
            background-color: #bbf7d0 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    if not renglones:
        st.warning("Sin renglones para este caso.")
        return

    edits: list[dict[str, Any]] = []
    for i, ren in enumerate(renglones, 1):
        rid = ren.get("id")
        if rid is None:
            continue
        titulo_ren = ren.get("descripcion") or ren.get("cod_articulo") or f"Renglón {i}"
        planos = _campos_planos_renglon(ren)
        bultos = ren.get("bultos")
        with st.expander(f"{i}. {titulo_ren}", expanded=(len(renglones) == 1)):
            if bultos is not None:
                try:
                    from app.services.bultos_service import etiqueta_bultos_detalle

                    txt_b = etiqueta_bultos_detalle(
                        tipo_linea=ren.get("tipo_linea"),
                        descripcion=ren.get("descripcion"),
                        cod_articulo=ren.get("cod_articulo"),
                        cantidad=ren.get("cantidad"),
                        bultos=int(bultos) if bultos else None,
                    )
                    if txt_b:
                        st.caption(f"Bultos: {txt_b}")
                except Exception:
                    st.caption(f"Bultos: {bultos}")

            # Campos editables (siempre visibles, aunque vengan vacíos/False)
            filas_ok: list[dict[str, str]] = []
            for k in _ORDEN_EDITABLES_DETALLE:
                if k not in _CAMPOS_EDITABLES_DETALLE:
                    continue
                if k in planos:
                    v = planos[k]
                elif k in ren:
                    v = ren.get(k)
                elif k in _CAMPOS_BOOL_DETALLE:
                    v = False
                else:
                    v = ""
                filas_ok.append(
                    {
                        "clave": k,
                        "campo": etiqueta_columna(k),
                        "valor": _valor_celda_editable(v),
                    }
                )
            df_ok = pd.DataFrame(filas_ok)
            editado = st.data_editor(
                df_ok,
                width="stretch",
                hide_index=True,
                num_rows="fixed",
                disabled=["clave", "campo"],
                column_order=["campo", "valor"],
                column_config={
                    "clave": None,
                    "campo": st.column_config.TextColumn("campo", width="medium"),
                    "valor": st.column_config.TextColumn("valor", width="large"),
                },
                key=f"det_ren_ok_{caso_id}_{rid}",
                height=min(520, 38 + 35 * len(filas_ok)),
            )

            # Resto solo lectura
            filas_ro = [
                {
                    "campo": etiqueta_columna(k),
                    "valor": _valor_celda_editable(v),
                }
                for k, v in sorted(planos.items(), key=lambda x: str(x[0]).lower())
                if k not in _CAMPOS_EDITABLES_DETALLE
            ]
            if filas_ro:
                st.caption("Resto de datos (solo lectura)")
                st.dataframe(
                    pd.DataFrame(filas_ro),
                    width="stretch",
                    hide_index=True,
                    height=min(320, 38 + 35 * len(filas_ro)),
                )

            nuevos: dict[str, Any] = {"id": int(rid)}
            for _, row in editado.iterrows():
                clave = str(row.get("clave") or "").strip()
                if clave not in _CAMPOS_EDITABLES_DETALLE:
                    continue
                raw_val = row.get("valor")
                orig = planos.get(clave, ren.get(clave))
                if clave in _CAMPOS_BOOL_DETALLE and orig is None:
                    orig = False
                nuevos[clave] = _parse_valor_editado(
                    clave, str(raw_val if raw_val is not None else ""), orig
                )
            edits.append(nuevos)

    guardar = st.button("Guardar cambios", type="primary", key=f"det_ren_save_{caso_id}")
    if not guardar:
        return
    if not edits:
        st.warning("No hay renglones para guardar.")
        return

    body: dict[str, Any] = {
        "recalcular": True,
        "renglones": edits,
    }
    # Compartidos a todas las líneas del caso
    for k in ("proveedor_tarifa", "sucursal_cc", "prefactura_proveedor"):
        if k in edits[0] and edits[0][k] is not None:
            body[k] = edits[0][k]

    try:
        with api_client() as c:
            r = c.patch(f"/maestro/caso/{caso_id}", json=body)
            r.raise_for_status()
            out = r.json()
        get_maestro_filas_cached.clear()
        get_fletes_pagina_cached.clear()
        get_adrian_resumen_cached.clear()
        nuevo = str(out.get("caso_id") or caso_id)
        popup = dict(st.session_state.get(DETALLE_POPUP) or {})
        if popup:
            popup["caso_id"] = nuevo
            st.session_state[DETALLE_POPUP] = popup
        extras = []
        if out.get("recalculado"):
            extras.append("reglas/tarifas")
        if out.get("costos_manuales"):
            extras.append(f"costos manuales: {out['costos_manuales']}")
        st.success(
            "Cambios guardados"
            + (f" — {', '.join(extras)}." if extras else ".")
        )
        st.rerun()
    except Exception as exc:
        st.error(f"No se pudo guardar: {exc}")


def _render_contenido_detalle_caso(caso_id: str, titulo: str) -> None:
    """Cuerpo del detalle (panel inline, sin dialog)."""
    popup = st.session_state.get(DETALLE_POPUP) or {}
    modulo = str(popup.get("modulo") or "maestro")

    st.markdown(f"**{titulo}**")
    if modulo == "fletes":
        st.caption(
            "Flete local CABA/GBA — tarifa ref. sucursales, zona km y fletero Drive."
        )
        _render_bloque_detalle_fletes(caso_id)
        return

    st.caption(
        "Un caso = un remito (puede tener varios artículos: colchón, base, postventa desde Tango)."
    )
    try:
        det = get_json(f"/maestro/caso/{caso_id}")
    except Exception as exc:
        st.error(f"No se pudo cargar el detalle: {exc}")
        return

    m = det.get("maestro", {})
    renglones = det.get("renglones", [])
    alertas_det = _parse_alertas_celdas(m.get("_alertas_celdas"))
    if alertas_det:
        for al in alertas_det:
            cols_txt = ", ".join(al.get("columnas") or [])
            st.warning(f"**{cols_txt}:** {al.get('motivo', '')}")
    elif m.get("_alerta_motivo"):
        st.warning(str(m["_alerta_motivo"]))

    st.markdown("#### Proveedor de tarifa")
    prov = m.get("PROVEEDOR") or m.get("_proveedor_tarifa")
    if prov:
        st.write(f"**Asignado:** {etiqueta_proveedor(str(prov))}")
    cobro_prov = float(m.get("COBRO PROVINCIA") or 0)
    cobro_red = float(m.get("COBRO RED") or 0)
    if cobro_red or cobro_prov:
        if cobro_prov > 0 and cobro_red > 0:
            st.write(
                f"**Cobro red (Clicpaq):** ${cobro_red:,.2f} · "
                f"**Última milla:** ${cobro_prov:,.2f} · "
                f"**Total cross:** ${cobro_red + cobro_prov + float(m.get('SEGURO') or 0):,.2f} · "
                f"**Seguro:** ${float(m.get('SEGURO') or 0):,.2f}"
            )
        elif cobro_prov > 0:
            st.write(
                f"**Cobro red:** ${cobro_red:,.2f} · "
                f"**Última milla:** ${cobro_prov:,.2f} · "
                f"**Seguro (caso):** ${float(m.get('SEGURO') or 0):,.2f}"
            )
        else:
            st.write(
                f"**Logística:** ${cobro_red:,.2f} · "
                f"**Seguro (caso):** ${float(m.get('SEGURO') or 0):,.2f}"
            )
    if m.get("_requiere_elegir_proveedor"):
        st.warning("Requiere elegir proveedor — andá a **Proveedor a elegir** en el menú.")
    cand_raw = m.get("_proveedores_candidatos")
    if cand_raw:
        try:
            parsed = json.loads(cand_raw)
            tramos_x = parsed.get("tramos") or [] if isinstance(parsed, dict) else []
            if isinstance(parsed, dict) and parsed.get("modo") == "crossdock" and len(tramos_x) >= 2:
                st.info(
                    "Crossdocking (Córdoba / Rosario / NOA): un **solo remito del CD** recorre todo el viaje "
                    "(no se reemite en sucursal). CLICPAQ → hub y última milla (LBO/FRANSOF/ALFARO) "
                    "→ cliente. La **X** del Excel es solo tránsito interno."
                )
                if parsed.get("nota_remito"):
                    st.caption(parsed["nota_remito"])
                tramos = tramos_x
                subtotal = 0.0
                for c in tramos:
                    nom = etiqueta_proveedor(c.get("proveedor"))
                    nota = c.get("nota") or ""
                    precio = float(c.get("precio") or 0)
                    subtotal += precio
                    st.write(f"- **{nom}** — {nota}: ${precio:,.2f}")
                if subtotal > 0:
                    st.write(f"**Suma tarifas crossdock:** ${subtotal:,.2f} (+ seguro en total)")
            elif det.get("cobro_unidad"):
                cu = det["cobro_unidad"]
                st.markdown("#### Cobro del pedido (un envío)")
                st.write(f"**{cu.get('resumen', '')}** — logística ${float(cu.get('logistica') or 0):,.2f}")
                for t in cu.get("tramos") or []:
                    st.write(
                        f"- {etiqueta_proveedor(t.get('proveedor'))}: "
                        f"${float(t.get('monto') or 0):,.2f} {t.get('nota') or ''}"
                    )
            elif isinstance(parsed, list) and parsed:
                st.markdown("#### Candidatos tarifario")
                for c in parsed:
                    nom = etiqueta_proveedor(c.get("proveedor"))
                    st.write(f"- {nom}: ${c.get('precio', 0):,.2f}")
            if det.get("cobro_renglones"):
                st.markdown("#### Renglones del pedido")
                from app.services.bultos_service import etiqueta_bultos_detalle

                for cr in det["cobro_renglones"]:
                    cant_txt = etiqueta_bultos_detalle(
                        tipo_linea=cr.get("tipo_linea"),
                        descripcion=cr.get("descripcion"),
                        cod_articulo=None,
                        cantidad=cr.get("cantidad"),
                        bultos=cr.get("bultos"),
                    ) or f"cant. {cr.get('cantidad')}"
                    st.write(
                        f"- `{cr.get('tipo_linea')}` — {cr.get('descripcion') or '—'} "
                        f"({cant_txt})"
                    )
            for pc in det.get("cobro_pedidos") or []:
                for adv in pc.get("advertencias") or []:
                    st.caption(adv)
        except json.JSONDecodeError:
            pass

    dist_info = det.get("distancia_sucursal") or {}
    _render_distancia_sucursal(dist_info)
    _render_cedol_caso(caso_id, det)
    _render_cross_seguimiento_caso(det)
    if dist_info.get("aplica") and (dist_info.get("pendiente_calculo") or dist_info.get("es_estimado")):
        col_km, _ = st.columns([1, 3])
        with col_km:
            if st.button("Calcular km real", key=f"calc_km_{caso_id}", type="primary"):
                try:
                    with api_client() as c:
                        r = c.post(f"/fletes/caso/{caso_id}/calcular-km")
                        r.raise_for_status()
                    get_fletes_pagina_cached.clear()
                    get_maestro_filas_cached.clear()
                    st.success("Distancia calculada — actualizando detalle…")
                    st.rerun()
                except Exception as exc:
                    st.error(f"No se pudo calcular: {exc}")

    pv_regla = None
    pv_motivo = None
    for ren in renglones:
        pv_regla = ren.get("regla_postventa") or pv_regla
        pv_motivo = ren.get("motivo_postventa") or ren.get("tipo_gestion") or pv_motivo
    if pv_regla or pv_motivo:
        st.markdown("#### Postventa (detalle Tango)")
        if pv_motivo:
            st.caption(f"**Motivo / gestión:** {pv_motivo}")
        if pv_regla and pv_regla != "revisar_manual":
            st.caption(f"**Regla logística aplicada:** `{pv_regla}`")
        if pv_regla == "revisar_manual":
            st.warning(
                "Motivo postventa sin regla logística automática. "
                "Definí si el viaje se paga o queda en $0 (Mantello Paso 4)."
            )
            c_ap, c_np = st.columns(2)
            with c_ap:
                if st.button("Aprobar viaje postventa", key=f"pv_ok_{caso_id}", type="primary"):
                    try:
                        with api_client() as c:
                            r = c.post(
                                f"/maestro/caso/{caso_id}/postventa",
                                json={"accion": "aprobar_viaje"},
                            )
                            r.raise_for_status()
                        get_fletes_pagina_cached.clear()
                        get_maestro_filas_cached.clear()
                        st.success("Viaje aprobado — actualizando…")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
            with c_np:
                if st.button("No se paga transporte", key=f"pv_no_{caso_id}"):
                    try:
                        with api_client() as c:
                            r = c.post(
                                f"/maestro/caso/{caso_id}/postventa",
                                json={"accion": "no_pagar"},
                            )
                            r.raise_for_status()
                        get_fletes_pagina_cached.clear()
                        get_maestro_filas_cached.clear()
                        st.success("Marcado como no pago — actualizando…")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
        elif pv_regla in ("cruce_medidas_aprobado", "viaje_aprobado"):
            st.info(
                "Reclamo clasificado — el cobro sigue el circuito del transporte "
                "(40/51/82 + tarifario)."
            )
        elif pv_regla == "gestion_retiro_25":
            st.info("Gestión retiro: +25% sobre tarifa logística al cerrar cobro.")
        elif pv_regla in ("no_pagar_transporte", "costo_cero_pendiente"):
            st.info("Regla logística: transporte en $0 hasta validar con proveedor.")

    _render_renglones_tango_editables(caso_id, renglones)


def _render_panel_detalle(sel_key: str) -> None:
    """Panel fijo arriba de la grilla; el cierre limpia estado y hace rerun."""
    info = st.session_state.get(DETALLE_POPUP)
    if not info or not info.get("caso_id"):
        return
    if str(info.get("sel_key") or "") != sel_key:
        return

    caso_id = str(info["caso_id"])
    titulo = str(info.get("titulo") or caso_id)
    with st.container(border=True):
        c_tit, c_btn = st.columns([5, 1])
        c_tit.markdown("### Detalle del caso")
        if c_btn.button(
            "Cerrar",
            type="primary",
            key=f"cerrar_detalle_{sel_key}_{caso_id}",
        ):
            _cerrar_popup_detalle(sel_key)
            st.rerun()
        _render_contenido_detalle_caso(caso_id, titulo)


def _cerrar_popup_detalle(sel_key: str) -> None:
    """Limpia estado del popup de detalle (no tocar sel_key: el widget aún no debe existir)."""
    st.session_state.pop(DETALLE_POPUP, None)
    st.session_state.pop("popup_caso_id", None)
    st.session_state.pop("mostrar_popup_caso", None)
    st.session_state.pop("detalle_dialog_abierto", None)
    st.session_state.pop(f"{sel_key}_detalle_caso_id", None)
    st.session_state.pop(f"{sel_key}_detalle_titulo", None)
    st.session_state.pop(f"{sel_key}_abrir_caso", None)
    st.session_state[f"{sel_key}_limpiar_seleccion"] = True


def _limpiar_seleccion_grilla_si_pendiente(sel_key: str) -> None:
    """Borra selección del dataframe antes de crear el widget (evita error Streamlit)."""
    if st.session_state.pop(f"{sel_key}_limpiar_seleccion", False):
        st.session_state.pop(sel_key, None)


def _abrir_detalle_por_id(caso_id: str, df: pd.DataFrame, sel_key: str) -> None:
    if not caso_id:
        return
    titulo = str(caso_id)
    if df is not None and "_caso_id" in df.columns:
        filas = df[df["_caso_id"].astype(str) == str(caso_id)]
        if not filas.empty:
            titulo = _etiqueta_caso(filas.iloc[0])
    prev = st.session_state.get(DETALLE_POPUP) or {}
    if (
        str(prev.get("caso_id")) == str(caso_id)
        and str(prev.get("sel_key")) == sel_key
    ):
        _cerrar_popup_detalle(sel_key)
        return
    st.session_state[DETALLE_POPUP] = {
        "caso_id": str(caso_id),
        "titulo": titulo,
        "sel_key": sel_key,
        "modulo": "fletes" if sel_key == "fletes_sel" else "maestro",
    }


_META_GRILLA = (
    "_regla_color",
    "_caso_id",
    "_es_marcador_tarifario",
    "_alertas_celdas",
    "_alerta_motivo",
    "_cedol_manual",
    "_cedol_auto",
    "_zona_km_asignada",
    "_por_zona_tarifa",
)


def _es_pendiente_zona_km_fila(row: pd.Series) -> bool:
    """Caso Fletes con tarifario local pero sin zona km asignada."""
    if row.get("_por_zona_tarifa") and not row.get("_zona_km_asignada"):
        return True
    tarifa = str(row.get("TARIFA REF") or "").strip()
    zona = str(row.get("ZONA KM") or "").strip()
    if tarifa and (not zona or zona == "—"):
        return True
    return False


def _filtrar_pendiente_zona_km(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    mask = df.apply(_es_pendiente_zona_km_fila, axis=1)
    return _as_dataframe(df[mask])


def _parse_alertas_celdas(raw: Any) -> list[dict[str, Any]]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [a for a in raw if isinstance(a, dict)]
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else []
        return [a for a in parsed if isinstance(a, dict)] if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return []


def _motivo_luz_columna(fila: dict[str, Any], col_name: str) -> str | None:
    for alerta in _parse_alertas_celdas(fila.get("_alertas_celdas")):
        if col_name in (alerta.get("columnas") or []):
            return str(alerta.get("motivo") or "").strip() or None
    return None


def _html_luz_alerta(motivo: str) -> str:
    t = html_lib.escape(motivo)
    return (
        f'<span class="alerta-luz" title="{t}" aria-label="{t}"></span>'
    )


def _hex_to_rgba(hex_color: str, alpha: float = 0.14) -> str:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return f"rgba(255,255,255,{alpha})"
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{alpha})"


def _css_grilla_detalle() -> None:
    """Grilla tipo tabla: filas densas (menos scroll)."""
    st.markdown(
        """
        <style>
        .grilla-celda-dato {
            display: flex;
            align-items: center;
            gap: 3px;
            padding: 0 5px;
            height: 1.42rem;
            line-height: 1.42rem;
            font-size: 0.72rem;
            overflow: hidden;
            white-space: nowrap;
            text-overflow: ellipsis;
            border-bottom: 1px solid #c8d4e0;
            box-sizing: border-box;
        }
        .grilla-celda-dato[title] {
            cursor: help;
        }
        .alerta-luz {
            display: inline-block;
            width: 6px;
            height: 6px;
            min-width: 6px;
            border-radius: 50%;
            background: #e53935;
            box-shadow: 0 0 0 1px rgba(229, 57, 53, 0.28);
            cursor: help;
            flex-shrink: 0;
        }
        .celda-luz-wrap {
            display: flex;
            align-items: center;
            min-height: 1.42rem;
            border-bottom: 1px solid #c8d4e0;
            padding: 0 3px;
            height: 100%;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] {
            font-size: 0.72rem;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stHorizontalBlock"] {
            align-items: stretch !important;
            margin: 0 !important;
            padding: 0 !important;
            min-height: 1.42rem !important;
            max-height: 1.42rem !important;
            overflow: hidden !important;
            gap: 0 !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="element-container"] {
            margin-bottom: 0 !important;
            padding-bottom: 0 !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="column"] {
            padding-top: 0 !important;
            padding-bottom: 0 !important;
            min-height: 1.42rem !important;
            max-height: 1.42rem !important;
            overflow: hidden !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="column"]:first-child {
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            border-bottom: 1px solid #c8d4e0;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="column"]:first-child div[data-testid="stButton"],
        div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="column"]:first-child div[data-testid="stElementContainer"] {
            margin: 0 !important;
            padding: 0 !important;
            width: auto !important;
            min-height: 0 !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="column"]:first-child button,
        div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="column"]:first-child [data-testid="stBaseButton-tertiary"] {
            font-size: 0.62rem !important;
            padding: 0 !important;
            min-height: 1.05rem !important;
            height: 1.05rem !important;
            max-height: 1.05rem !important;
            width: 1.05rem !important;
            min-width: 1.05rem !important;
            max-width: 1.05rem !important;
            margin: 0 !important;
            line-height: 1 !important;
            border-radius: 999px !important;
            background: rgba(255,255,255,0.55) !important;
            border: 1px solid rgba(0,0,0,0.06) !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="column"]:first-child button p {
            font-size: 0.62rem !important;
            line-height: 1 !important;
            margin: 0 !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stSelectbox"] {
            margin: 0 !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stSelectbox"] > div {
            min-height: 1.42rem !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stSelectbox"] div[data-baseweb="select"] {
            min-height: 1.28rem !important;
            height: 1.28rem !important;
            font-size: 0.70rem !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _fila_clic_detalle(caso_id: str, sel_key: str) -> None:
    st.session_state[f"{sel_key}_abrir_caso"] = caso_id


def _procesar_clic_grilla_pendiente(df: pd.DataFrame, sel_key: str) -> None:
    caso_id = st.session_state.pop(f"{sel_key}_abrir_caso", None)
    if caso_id:
        _abrir_detalle_por_id(str(caso_id), df, sel_key)


def _celda_html(
    fila: dict[str, Any],
    col_name: str,
    bg: str,
    fg: str,
) -> str:
    texto = _texto_celda_grilla(fila, col_name)
    tint = _hex_to_rgba(bg, 0.38)
    control = "border-left:2px solid #8FA8C8;" if col_name in MAESTRO_CONTROL else ""
    title = ""
    if col_name == "PROVINCIA":
        full = nombre_provincia_completo(fila.get("PROVINCIA"))
        if full:
            title = f' title="{html_lib.escape(full)}"'
    elif len(texto) > 22:
        title = f' title="{html_lib.escape(texto)}"'
    luz_motivo = _motivo_luz_columna(fila, col_name)
    luz = _html_luz_alerta(luz_motivo) if luz_motivo else ""
    if not texto and not luz:
        return f'<div class="grilla-celda-dato" style="background:{tint};"></div>'
    return (
        f'<div class="grilla-celda-dato" style="background:{tint};color:{fg};'
        f'{control}"{title}>'
        f"{luz}<span style='overflow:hidden;text-overflow:ellipsis;'>"
        f"{html_lib.escape(texto)}</span></div>"
    )


_COL_BOTON_DETALLE = 0.07
_COL_ALERTA = 0.05
_GRILLA_PAGE_SIZE = 150


def _df_grilla_rapida(df_page: pd.DataFrame, cols_grilla: list[str]) -> pd.DataFrame:
    """Tabla ligera para st.dataframe (sin miles de widgets Streamlit)."""
    filas: list[dict[str, str]] = []
    for _, row in df_page.iterrows():
        fila = row.to_dict()
        out: dict[str, str] = {}
        if fila.get("_regla_color") == "alerta":
            out["!"] = "⚠"
        else:
            out["!"] = ""
        for col in cols_grilla:
            if col in df_page.columns:
                out[etiqueta_columna(col)] = _texto_celda_grilla(fila, col)
        filas.append(out)
    return pd.DataFrame(filas)


def _siglas_provincia_en_vista(df_page: pd.DataFrame) -> str:
    """Leyenda compacta de siglas presentes en la página (para st.dataframe)."""
    if df_page.empty or "PROVINCIA" not in df_page.columns:
        return ""
    vistos: dict[str, str] = {}
    for raw in df_page["PROVINCIA"].dropna().unique():
        abrev = abreviar_provincia(str(raw))
        full = nombre_provincia_completo(raw)
        if not abrev or not full:
            continue
        if abrev.upper() == full.upper():
            continue
        vistos[abrev] = full
    if not vistos:
        return ""
    partes = [f"**{sigla}** = {nombre}" for sigla, nombre in sorted(vistos.items(), key=lambda x: x[1])]
    return "Siglas en esta vista — Provincia: " + " · ".join(partes)


def _sincronizar_seleccion_grilla(df_page: pd.DataFrame, sel_key: str) -> None:
    """Abre detalle al seleccionar fila en st.dataframe."""
    sel = st.session_state.get(sel_key)
    if not isinstance(sel, dict):
        return
    rows = (sel.get("selection") or {}).get("rows") or []
    if not rows:
        return
    pos = int(rows[0])
    if pos < 0 or pos >= len(df_page):
        return
    caso_id = df_page.iloc[pos].get("_caso_id")
    if not caso_id:
        return
    popup = st.session_state.get(DETALLE_POPUP) or {}
    if str(popup.get("caso_id")) == str(caso_id) and str(popup.get("sel_key")) == sel_key:
        return
    titulo = _etiqueta_caso(df_page.iloc[pos])
    st.session_state[DETALLE_POPUP] = {
        "caso_id": str(caso_id),
        "titulo": titulo,
        "sel_key": sel_key,
        "modulo": "fletes" if sel_key == "fletes_sel" else "maestro",
    }


def _controles_paginacion_grilla(total: int, sel_key: str) -> int:
    """Paginación de la grilla; devuelve índice de inicio (0 si cabe en una página)."""
    if total <= _GRILLA_PAGE_SIZE:
        return 0
    pages = max(1, (total + _GRILLA_PAGE_SIZE - 1) // _GRILLA_PAGE_SIZE)
    pkey = f"{sel_key}_pag"
    page = min(int(st.session_state.get(pkey, 0) or 0), pages - 1)
    st.session_state[pkey] = page

    c1, c2, c3 = st.columns([1.2, 2.6, 1.2])
    with c1:
        if st.button("← Anterior", key=f"{sel_key}_pag_prev", disabled=page <= 0):
            st.session_state[pkey] = page - 1
            st.rerun()
    fin = min((page + 1) * _GRILLA_PAGE_SIZE, total)
    inicio = page * _GRILLA_PAGE_SIZE + 1
    with c2:
        st.caption(f"Filas **{inicio}–{fin}** de **{total}** · página **{page + 1}/{pages}**")
    with c3:
        if st.button("Siguiente →", key=f"{sel_key}_pag_next", disabled=page >= pages - 1):
            st.session_state[pkey] = page + 1
            st.rerun()
    return page * _GRILLA_PAGE_SIZE


def _render_grilla_filas_click(
    df: pd.DataFrame,
    cols_grilla: list[str],
    *,
    sel_key: str,
    height: int = 480,
    key_prefix: str | None = None,
    row_offset: int = 0,
) -> None:
    """Grilla con lupa + datos; opcional columna Proveedor (select) en la misma fila."""
    if not cols_grilla:
        return
    ratios_datos = _ratios_columnas(cols_grilla)
    ratios_fila = [_COL_BOTON_DETALLE, _COL_ALERTA] + ratios_datos

    st.markdown(
        '<div class="grilla-wrap" style="border:1px solid #d5dde8;border-radius:12px;overflow:hidden;">',
        unsafe_allow_html=True,
    )
    hdr = st.columns(ratios_fila)
    hdr[0].markdown(
        '<div style="font-size:0.78rem;font-weight:600;color:#2c3e50;'
        'padding:6px 2px;background:#eceff3;border-bottom:1px solid #d5dde8;'
        'text-align:center;" title="Ver detalle">🔍</div>',
        unsafe_allow_html=True,
    )
    hdr[1].markdown(
        '<div style="font-size:0.78rem;font-weight:600;color:#2c3e50;'
        'padding:6px 2px;background:#eceff3;border-bottom:1px solid #d5dde8;'
        'text-align:center;" title="Revisar">!</div>',
        unsafe_allow_html=True,
    )
    for col, name in zip(hdr[2:], cols_grilla):
        col.markdown(
            f'<div style="font-size:0.76rem;font-weight:600;color:#2c3e50;'
            f'padding:6px 5px;background:#eceff3;border-bottom:1px solid #d5dde8;">'
            f"{html_lib.escape(etiqueta_columna(name))}</div>",
            unsafe_allow_html=True,
        )

    with st.container(height=height):
        for idx, (_, row) in enumerate(df.iterrows()):
            fila = row.to_dict()
            if fila.get("_es_marcador_tarifario") is True:
                bg, fg = COLOR_MAP.get("alerta", ("#FFE8E8", "#7A3030"))
                texto = (
                    f"⚠ {fila.get('REMITOS', 'CAMBIO TARIFARIO')} — "
                    f"{fila.get('DESTINATARIO', '')}"
                )
                st.markdown(
                    f'<div style="background:{bg};color:{fg};font-weight:600;'
                    f'padding:6px 12px;margin:0;border-top:2px solid #c44;'
                    f'border-bottom:2px solid #c44;font-size:0.82rem;">'
                    f"{html_lib.escape(texto)}</div>",
                    unsafe_allow_html=True,
                )
                continue
            caso_id = str(fila.get("_caso_id") or "").strip()
            if not caso_id:
                continue
            if fila.get("_regla_color") == "alerta":
                bg, fg = COLOR_MAP["alerta"]
            else:
                bg, fg = "#ffffff", "#2c3e50"
            tint = _hex_to_rgba(bg, 0.38) if fila.get("_regla_color") == "alerta" else "#ffffff"
            row_key = row_offset + idx

            cols = st.columns(ratios_fila)
            with cols[0]:
                st.button(
                    "🔍",
                    key=f"{sel_key}_det_{row_key}_{caso_id}",
                    help="Ver detalle del caso",
                    type="tertiary",
                    on_click=_fila_clic_detalle,
                    args=(caso_id, sel_key),
                )
            alerta_txt = "⚠" if fila.get("_regla_color") == "alerta" else ""
            cols[1].markdown(
                f'<div class="grilla-celda-dato" style="background:{tint};color:{fg};'
                f'justify-content:center;font-size:0.82rem;"'
                f' title="Revisar fila">{html_lib.escape(alerta_txt)}</div>',
                unsafe_allow_html=True,
            )
            for i, col_name in enumerate(cols_grilla):
                col_widget = cols[i + 2]
                if col_name == "PROVEEDOR" and key_prefix:
                    opciones, mapa = _opciones_select_proveedor(fila)
                    mapa_key = f"{key_prefix}_map_{caso_id}"
                    state_key = f"{key_prefix}_pe_{caso_id}"
                    st.session_state[mapa_key] = mapa
                    luz_prov = _motivo_luz_columna(fila, "PROVEEDOR")
                    luz_html = _html_luz_alerta(luz_prov) if luz_prov else ""
                    if len(opciones) <= 1:
                        col_widget.markdown(
                            f'<div class="grilla-celda-dato" style="background:{tint};color:{fg};">'
                            f"{luz_html}Sin tarifa</div>",
                            unsafe_allow_html=True,
                        )
                    else:
                        if luz_html:
                            luz_col, sel_col = col_widget.columns([0.07, 0.93], gap="small")
                            luz_col.markdown(
                                f'<div class="celda-luz-wrap" style="justify-content:center;">'
                                f"{luz_html}</div>",
                                unsafe_allow_html=True,
                            )
                            with sel_col:
                                st.selectbox(
                                    "Proveedor",
                                    options=opciones,
                                    key=state_key,
                                    label_visibility="collapsed",
                                    on_change=_asignar_proveedor_callback,
                                    args=(caso_id, state_key, mapa_key),
                                )
                        else:
                            with col_widget:
                                st.selectbox(
                                    "Proveedor",
                                    options=opciones,
                                    key=state_key,
                                    label_visibility="collapsed",
                                    on_change=_asignar_proveedor_callback,
                                    args=(caso_id, state_key, mapa_key),
                                )
                else:
                    col_widget.markdown(
                        _celda_html(fila, col_name, bg, fg),
                        unsafe_allow_html=True,
                    )

    st.markdown("</div>", unsafe_allow_html=True)


def _render_grilla_con_detalle(
    show_df: pd.DataFrame,
    df: pd.DataFrame,
    *,
    sel_key: str,
    height: int = 480,
    key_prefix: str | None = None,
    paginar_cliente: bool = True,
    ayuda_notas: str = "",
) -> None:
    """Grilla maestro/fletes/adrian: dataframe nativo + detalle al seleccionar fila."""
    _procesar_clic_grilla_pendiente(df, sel_key)

    cols_grilla = [c for c in show_df.columns if c not in _META_GRILLA]
    total = len(df)
    if paginar_cliente and total > _GRILLA_PAGE_SIZE:
        offset = _controles_paginacion_grilla(total, sel_key)
        df_page = df.iloc[offset : offset + _GRILLA_PAGE_SIZE]
    else:
        offset = 0
        df_page = df

    if key_prefix:
        _render_panel_detalle(sel_key)
        _css_grilla_detalle()
        _render_grilla_filas_click(
            df_page,
            cols_grilla,
            sel_key=sel_key,
            height=height,
            key_prefix=key_prefix,
            row_offset=offset,
        )
        return

    display = _df_grilla_rapida(df_page, cols_grilla)
    siglas = _siglas_provincia_en_vista(df_page)
    paginacion = ""
    if paginar_cliente and total > len(df_page):
        paginacion = f"Mostrando **{len(df_page)}** de **{total}** casos."
    _render_ayuda_grilla(siglas=siglas, notas=ayuda_notas, paginacion=paginacion)
    _limpiar_seleccion_grilla_si_pendiente(sel_key)
    st.dataframe(
        display,
        width="stretch",
        height=height,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key=sel_key,
    )
    _sincronizar_seleccion_grilla(df_page, sel_key)
    _render_panel_detalle(sel_key)


def _texto_celda_grilla(fila: dict[str, Any], col_name: str) -> str:
    raw = fila.get(col_name)
    if col_name in (
        "PROVEEDOR",
        "DESTINATARIO",
        "LOCALIDAD",
        "PROVINCIA",
        "TRANSPORTE",
        "ESTADO PEDIDO",
    ):
        return fmt_celda_maestro(raw, col_name)
    return _celda_grilla_texto(raw, col_name)


def _anchos_columnas_grilla(cols: list[str]) -> list[float]:
    total = sum(MAESTRO_COL_RATIOS.get(c, 0.75) for c in cols)
    return [100.0 * MAESTRO_COL_RATIOS.get(c, 0.75) / total for c in cols]


def _etiqueta_caso(row: pd.Series) -> str:
    rem = row.get("REMITOS")
    if not rem or rem in ("—", "Sin RAR/R", "Sin remito"):
        rem = row.get("ENVIO") or "?"
    else:
        rem = str(rem)
    dest = row.get("DESTINATARIO") or ""
    reng = row.get("_cantidad_renglones", 1)
    return f"{rem} — {dest} ({reng} reng.)"


def _dash_card(body: str, accent: str, bg: str = "#ffffff") -> str:
    return (
        f'<div class="dash-card" style="background:{bg};">'
        f'<div class="dash-card-accent" style="background:{accent};"></div>'
        f'<div class="dash-card-body">{body}</div></div>'
    )


def _fmt_num_ar(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _fmt_pesos_compact(value: float) -> str:
    n = float(value or 0)
    if n >= 1_000_000_000:
        return f"$ {n / 1_000_000_000:.2f} B"
    if n >= 1_000_000:
        return f"$ {n / 1_000_000:.1f} M"
    if n >= 10_000:
        return f"$ {n / 1_000:.0f} K"
    return fmt_pesos_ar(n)


_PROV_CHART_COLORS = ["#7c3aed", "#d97706", "#e11d48", "#0ea5e9", "#f59e0b", "#64748b"]
_ZONA_CHART_COLORS = {
    "B": "#2563eb",
    "S": "#059669",
    "M": "#7c3aed",
    "C": "#0ea5e9",
    "T": "#0891b2",
    "R": "#db2777",
    "N": "#16a34a",
    "H": "#ca8a04",
    "D": "#9333ea",
    "J": "#ea580c",
    "Z": "#64748b",
    "CO": "#1d4ed8",
    "TU": "#0284c7",
    "NE": "#4f46e5",
    "SA": "#0d9488",
    "EN": "#c026d3",
}


def _zona_chart_color(codigo: str) -> str:
    cod = (codigo or "?").strip().upper()
    if cod in _ZONA_CHART_COLORS:
        return _ZONA_CHART_COLORS[cod]
    pref = cod[:1] if cod else "?"
    return _ZONA_CHART_COLORS.get(pref, "#64748b")


_DASHBOARD_EMBED = Path(__file__).parent / "assets" / "dashboard_embed.html"


def _css_dashboard_embed() -> None:
    st.markdown(
        """
        <style>
        [data-testid="stAppViewContainer"] .main .block-container {
            padding-top: 1.25rem;
        }
        [data-testid="stIframe"] {
            background: transparent !important;
            margin-bottom: 0 !important;
            padding-bottom: 0 !important;
        }
        [data-testid="stIframe"] iframe {
            display: block;
            background: transparent !important;
            border: none !important;
            min-height: 0 !important;
            margin-bottom: 0 !important;
        }
        .kpi-entregas-section {
            margin-top: 0 !important;
        }
        .dash-metrics div[data-testid="stMetric"] {
            border-left-width: 5px;
            border-left-style: solid;
        }
        .dash-metrics [data-testid="column"]:nth-child(1) [data-testid="stMetric"] {
            border-left-color: #F5D547;
        }
        .dash-metrics [data-testid="column"]:nth-child(2) [data-testid="stMetric"] {
            border-left-color: #8FA8C8;
        }
        .dash-metrics [data-testid="column"]:nth-child(3) [data-testid="stMetric"] {
            border-left-color: #F4A261;
        }
        .dash-metrics [data-testid="column"]:nth-child(4) [data-testid="stMetric"] {
            border-left-color: #7CB89A;
        }
        .dash-metrics [data-testid="column"]:nth-child(5) [data-testid="stMetric"] {
            border-left-color: #B39DDB;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_dashboard_embed(payload: dict[str, Any], *, dark: bool = False) -> None:
    template = _DASHBOARD_EMBED.read_text(encoding="utf-8")
    payload = {**payload, "dark": dark}
    data_json = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
    html = template.replace("__DASHBOARD_DATA__", data_json)
    # height="content": Streamlit mide el srcdoc y evita el hueco fijo del iframe antiguo.
    st.iframe(html, height="content")


def _kpi_entregas_a_df(bloque: dict[str, Any], *, mostrar_importes: bool) -> pd.DataFrame:
    anio_prev = bloque.get("anio_prev")
    anio_ctrl = bloque.get("anio_ctrl")
    rows = []
    for f in bloque.get("filas") or []:
        prev_e = int(f.get("prev_entregas") or 0)
        ctrl_e = int(f.get("ctrl_entregas") or 0)
        prev_i = f.get("prev_importe")
        ctrl_i = f.get("ctrl_importe")
        if not mostrar_importes:
            if prev_e == 0 and ctrl_e == 0:
                continue
        elif not any([prev_e, ctrl_e, float(prev_i or 0), float(ctrl_i or 0)]):
            continue
        row: dict[str, Any] = {
            "Mes pedido": str(f.get("mes") or "").capitalize(),
            f"Entregas {anio_prev}": prev_e,
            f"Entregas {anio_ctrl}": ctrl_e,
        }
        if mostrar_importes:
            row[f"Importe {anio_prev}"] = float(prev_i or 0)
            row[f"Importe {anio_ctrl}"] = float(ctrl_i or 0)
        rows.append(row)
    tot_prev = bloque.get("total_prev") or {}
    tot_ctrl = bloque.get("total_ctrl") or {}
    total_row: dict[str, Any] = {
        "Mes pedido": "TOTAL",
        f"Entregas {anio_prev}": int(tot_prev.get("entregas") or 0),
        f"Entregas {anio_ctrl}": int(tot_ctrl.get("entregas") or 0),
    }
    if mostrar_importes:
        total_row[f"Importe {anio_prev}"] = float(tot_prev.get("importe") or 0)
        total_row[f"Importe {anio_ctrl}"] = float(tot_ctrl.get("importe") or 0)
    rows.append(total_row)
    return pd.DataFrame(rows)


def _render_kpi_entregas_section() -> None:
    """Tablas «entregas x mes» — réplica Excel Grateful FC (volumen; importes = facturas pendientes)."""
    hoy = date.today()

    st.markdown('<div class="kpi-entregas-section">', unsafe_allow_html=True)
    st.markdown(
        '<div class="kpi-entregas-wrap">'
        "<h3>Entregas por mes — control LOG</h3>"
        "<p class=\"sub\">Volumen por quincena y CD (Hurlingham dep. 12 / Tortuguitas dep. 14). "
        "Estructura lista; importes cuando exista la fuente de <strong>facturas</strong> del proveedor.</p>"
        "</div>",
        unsafe_allow_html=True,
    )

    with st.expander("¿Para qué sirve este informe?", expanded=False):
        st.markdown(
            """
**Motivo de negocio**

Adrián armaba a mano un Excel (*Grateful FC*) para responder cada mes:

- ¿Cuántas entregas salieron por la red LOG (Clicpaq / La Costa) en cada quincena?
- ¿Cuánto **facturó** el proveedor, comparado con el mismo mes del año anterior?
- ¿Cuánto corresponde a **Hurlingham** (dep. 12) vs **Tortuguitas** (dep. 14)?

**Importante — fuente de los importes**

| Dato | Origen correcto (Excel Adrián) | Qué usa la app hoy |
|---|---|---|
| Entregas | Tango + reglas LOG | ✅ Activo |
| Importes | **Facturas** del proveedor LOG | ⏳ Pendiente (origen a definir) |
| Prefactura / tarifario Maestro | No es el cierre mensual | Solo referencia interna |

Hasta integrar las facturas, el informe muestra **solo volumen** para no confundir con prefacturas.

**Cómo leerlo**

| Concepto | Regla |
|---|---|
| Mes de control | Quincenas que se comparan (ej. junio 2026 vs junio 2025) |
| Corte | **Fecha de entrega** dentro de cada quincena |
| Filas de la tabla | Mes de **fecha de pedido** |
| Hurlingham | Depósito **12** — Clicpaq + Limansky desde ese CD |
| Tortuguitas | Depósito **14** — centro de distribución principal |

**Universo «LOG WAMARO»** = canales 51 y 83.
            """
        )

    c1, c2, c3 = st.columns([1, 1, 1.4])
    with c1:
        mes_sel = st.selectbox(
            "Mes de control",
            list(range(1, 13)),
            index=max(0, hoy.month - 1),
            format_func=lambda m: (
                "Ene Feb Mar Abr May Jun Jul Ago Sep Oct Nov Dic".split()[m - 1]
            ),
            key="kpi_ent_mes",
        )
    with c2:
        anio_sel = st.number_input(
            "Año",
            min_value=2020,
            max_value=2100,
            value=hoy.year,
            step=1,
            key="kpi_ent_anio",
        )
    with c3:
        circuito = st.selectbox(
            "Universo",
            ["adrian", "interior", "todos"],
            format_func=lambda x: {
                "adrian": "LOG WAMARO (canal 51/83 — como Adrián)",
                "interior": "Maestro interior (sin AMBA/retiro)",
                "todos": "Todos los casos maestro",
            }[x],
            key="kpi_ent_circuito",
        )

    params = json.dumps(
        {"anio": int(anio_sel), "mes": int(mes_sel), "circuito": circuito},
        sort_keys=True,
    )
    try:
        kpi = get_kpi_entregas_cached(params)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            st.info(
                "El servidor aún no expone `/dashboard/kpi-entregas`. "
                "Reiniciá con **Iniciar_Fletes.bat**."
            )
        else:
            st.warning(f"No se pudo cargar el informe de entregas: {exc}")
        return
    except Exception as exc:
        st.warning(f"No se pudo cargar el informe de entregas: {exc}")
        return

    gran = kpi.get("gran_total") or {}
    per = kpi.get("periodo") or {}
    estado = kpi.get("estado") or {}
    listo = bool(estado.get("listo_para_cierre"))
    imp_ref = gran.get("importe_referencia_tarifario")

    if not listo:
        st.info(estado.get("mensaje") or (
            "Importes pendientes: el Excel de Adrián usaba **facturas** del proveedor LOG, "
            "no prefacturas ni tarifario. Hoy solo se muestra volumen."
        ))

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total entregas (mes ctrl.)", int(gran.get("entregas") or 0))
    if listo:
        m2.metric("Costo total (facturas)", fmt_pesos_ar(gran.get("importe")))
        m3.metric("Promedio por entrega", fmt_pesos_ar(gran.get("promedio")))
    else:
        m2.metric("Costo total (facturas)", "Pendiente")
        m3.metric("Promedio", "—")
    m4.metric(
        f"Remitos emitidos ({per.get('mes_nombre', '')})",
        int(kpi.get("remitos_emitidos_mes") or 0),
    )

    if not listo and imp_ref:
        with st.expander("Referencia interna (tarifario Maestro — no usar para cierre)", expanded=False):
            st.caption(
                "Solo orientativo. El cierre mensual del Excel requiere facturas del proveedor, "
                "no este valor calculado desde prefacturas/tarifario."
            )
            st.metric("Suma tarifario LOGISTICA (mes ctrl.)", fmt_pesos_ar(imp_ref))

    proposito = kpi.get("proposito") or {}
    depositos = proposito.get("depositos") or []
    if depositos:
        dep_txt = " · ".join(
            f"**{d.get('bloque')}** (dep. {d.get('codigo')}): {d.get('descripcion')}"
            for d in depositos
        )
        st.caption(dep_txt)

    bloques = kpi.get("bloques") or []
    if not bloques:
        st.info("Sin datos para el período seleccionado.")
        return

    tabs = st.tabs([str(b.get("titulo") or "?") for b in bloques])
    for tab, bloque in zip(tabs, bloques):
        with tab:
            df = _kpi_entregas_a_df(bloque, mostrar_importes=listo)
            if df.empty:
                st.caption("Sin movimientos en esta quincena / origen.")
            else:
                df_show = df.copy()
                for col in df_show.columns:
                    if str(col).startswith("Importe"):
                        df_show[col] = df_show[col].map(
                            lambda v: fmt_pesos_ar(v) if v is not None and pd.notna(v) else ""
                        )
                st.dataframe(
                    df_show,
                    width="stretch",
                    hide_index=True,
                    height=min(420, 38 + 32 * len(df)),
                )
            tot = bloque.get("total_ctrl") or {}
            pie = (
                f"Total {bloque.get('anio_ctrl')}: **{tot.get('entregas', 0)}** entregas"
            )
            if listo:
                pie += f" · **{fmt_pesos_ar(tot.get('importe'))}** · prom. **{fmt_pesos_ar(tot.get('promedio'))}**"
            if bloque.get("origen_descripcion"):
                pie = f"*{bloque.get('origen_descripcion')}* · {pie}"
            st.caption(pie)

    for nota in kpi.get("notas") or []:
        st.caption(f"· {nota}")
    st.markdown("</div>", unsafe_allow_html=True)


def plantilla_download(nombre: str, etiqueta: str) -> None:
    path = DATA_DIR / nombre
    if path.exists():
        st.download_button(etiqueta, path.read_bytes(), file_name=nombre, width="stretch")


# --- Páginas ---


def pagina_dashboard() -> None:
    _css_dashboard_embed()

    if not check_health_cached():
        st.warning("El servidor no está activo. Ejecutá **Iniciar_Fletes.bat** en la carpeta del proyecto.")
        return

    if not _DASHBOARD_EMBED.is_file():
        st.error("No se encontró la plantilla del dashboard (`frontend/assets/dashboard_embed.html`).")
        return

    try:
        general, _interior = get_dashboard_stats_cached()
    except Exception as exc:
        st.error(f"No se pudieron cargar estadísticas: {exc}")
        return

    try:
        ger = get_dashboard_gerencial_cached()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            st.error(
                "El **servidor API** no tiene el dashboard nuevo (`/dashboard/gerencial`). "
                "Cerrá todo y volvé a ejecutar **Iniciar_Fletes.bat** "
                "(reinicia backend + interfaz con el código actual)."
            )
        else:
            st.error(f"No se pudieron cargar estadísticas gerenciales: {exc}")
        return
    except Exception as exc:
        st.error(f"No se pudieron cargar estadísticas gerenciales: {exc}")
        return

    k = ger.get("kpis") or {}
    ultimo = general.get("ultimo_import")
    ultimo_txt = fmt_fecha_sin_hora(ultimo) if ultimo else "Sin importar"
    per = ger.get("periodo") or {}
    meses = ("", "Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic")
    periodo_txt = f"{meses[int(per.get('mes') or 0)]} {per.get('anio', '')}".strip()

    costo = float(k.get("costo_tarifado") or 0)
    remitos = int(k.get("remitos_interior") or 0)
    pct_tar = float(k.get("pct_tarifados") or 0)
    diff_abs = float(k.get("diferencias_abs") or 0)

    alertas: list[dict[str, str]] = []
    for p in ger.get("problemas") or []:
        if int(p.get("valor") or 0) <= 0:
            continue
        tipo = "error" if p.get("label") in ("Sin datos Tango", "Sin tarifa") else "warn"
        if p.get("label") == "Sin prefactura":
            tipo = "info"
        alertas.append(
            {
                "tipo": tipo,
                "texto": f"{p.get('label')}: {p.get('valor')} — {p.get('hint', '')}",
            }
        )
    alertas = alertas[:4]

    prov_rows = ger.get("top_provincias") or []
    zona_rows = ger.get("top_zonas") or []
    transp_rows = ger.get("top_transportes") or []
    prov_mix = ger.get("proveedores") or []
    fleteros_mes = ger.get("fleteros_mes") or []
    fleteros_sol = ger.get("fleteros_solicitudes") or []
    top_suc = ger.get("top_sucursales") or []

    fleteros_chart: dict[str, Any]
    if fleteros_mes and any(int(x.get("entregas") or 0) > 0 for x in fleteros_mes):
        fleteros_chart = {
            "modo": "mes",
            "labels": [str(x.get("codigo") or "?") for x in fleteros_mes],
            "values": [int(x.get("entregas") or 0) for x in fleteros_mes],
        }
    elif top_suc:
        fleteros_chart = {
            "modo": "sucursales",
            "labels": [str(x.get("sucursal") or "?") for x in top_suc],
            "values": [int(x.get("envios") or 0) for x in top_suc],
        }
    elif fleteros_sol:
        fleteros_chart = {
            "modo": "solicitudes",
            "labels": [str(x.get("codigo") or "?") for x in fleteros_sol],
            "values": [int(x.get("solicitudes") or 0) for x in fleteros_sol],
        }
    else:
        fleteros_chart = {"modo": "vacio", "labels": [], "values": []}

    payload: dict[str, Any] = {
        "meta": {
            "ultimo_import": ultimo_txt,
            "periodo": periodo_txt or "—",
        },
        "kpis": [
            {
                "valor": _fmt_pesos_compact(costo) if costo else "—",
                "titulo": "Costo tarifado",
                "detalle": "Suma logística interior con tarifa calculada",
                "accent": "#1e3a5f",
            },
            {
                "valor": _fmt_num_ar(remitos),
                "titulo": "Remitos interior",
                "detalle": "Casos únicos en control (sin Amba/retiro)",
                "accent": "#2563eb",
            },
            {
                "valor": f"{pct_tar:.0f}%" if remitos else "—",
                "titulo": "Cobertura tarifaria",
                "detalle": f"{_fmt_num_ar(int(k.get('remitos_con_tarifa') or 0))} con tarifa asignada",
                "accent": "#059669",
            },
            {
                "valor": _fmt_pesos_compact(diff_abs) if diff_abs else "0",
                "titulo": "Desvío acumulado",
                "detalle": "Diferencia tarifa vs prefactura (absoluto)",
                "accent": "#d97706" if diff_abs else "#059669",
            },
        ],
        "alertas": alertas,
        "charts": {
            "provincias": {
                "labels": [str(r.get("provincia") or "?") for r in prov_rows],
                "values": [
                    float(r.get("costo") or 0) if r.get("costo") is not None else int(r.get("remitos") or 0)
                    for r in prov_rows
                ],
                "remitos": [int(r.get("remitos") or 0) for r in prov_rows],
                "unidad": "pesos",
            },
            "zonas": {
                "labels": [
                    f"{r.get('codigo') or '?'} · {(r.get('zona') or '')[:22]}"
                    for r in zona_rows
                ],
                "values": [int(r.get("remitos") or 0) for r in zona_rows],
                "colors": [_zona_chart_color(str(r.get("codigo") or "")) for r in zona_rows],
            },
            "transportes": {
                "labels": [str(r.get("transporte") or "?") for r in transp_rows],
                "values": [int(r.get("remitos") or 0) for r in transp_rows],
            },
            "proveedores": {
                "labels": [str(r.get("proveedor") or "?") for r in prov_mix],
                "values": [int(r.get("casos") or 0) for r in prov_mix],
                "colors": _PROV_CHART_COLORS[: len(prov_mix)],
                "center": str(len(prov_mix)),
            },
            "fleteros": fleteros_chart,
        },
    }

    with st.container(border=False, gap=None):
        _render_dashboard_embed(payload, dark=bool(st.session_state.get("dark_mode")))
        _render_kpi_entregas_section()

    st.divider()
    st.subheader("Export contable / ARCA")
    st.caption(
        "Costos de flete por provincia (Interior + CABA/AMBA) — base para enviar a contabilidad."
    )
    arca_key = "dashboard_export_provincias_xlsx"
    if st.button("Generar Excel costos por provincia", key="dash_arca_export_btn"):
        try:
            with st.spinner("Generando Excel…"):
                with httpx.Client(base_url=API_URL, timeout=120.0) as c:
                    r = c.get("/dashboard/export-provincias")
                    r.raise_for_status()
                st.session_state[arca_key] = r.content
            st.success("Excel listo — usá el botón de descarga.")
        except Exception as exc:
            st.error(f"No se pudo exportar: {exc}")
    if st.session_state.get(arca_key):
        st.download_button(
            "Descargar costos_flete_por_provincia.xlsx",
            st.session_state[arca_key],
            file_name="costos_flete_por_provincia.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dash_arca_export_dl",
        )


def _ratios_columnas(nombres: list[str]) -> list[float]:
    return [MAESTRO_COL_RATIOS.get(c, 0.6) for c in nombres]


def _celda_grilla_texto(val: Any, col_name: str) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    if col_name in ("FECHA", "FECHA PEDIDO", "FECHA ENTREGA") or "fecha" in col_name.lower():
        return fmt_fecha_sin_hora(val)
    if col_name in MAESTRO_MONEDA:
        return fmt_pesos_ar(val)
    return str(val)


def _render_grilla_elegir_proveedor(
    df: pd.DataFrame,
    key_prefix: str,
    *,
    sel_key: str,
) -> None:
    """Misma grilla que Maestro: proveedor como columna en cada fila."""
    cols_grilla = [c for c in MAESTRO_VISTA_GRILLA if c in df.columns]
    if not cols_grilla:
        return
    _procesar_clic_grilla_pendiente(df, sel_key)
    _render_panel_detalle(sel_key)
    _css_grilla_detalle()
    total = len(df)
    offset = _controles_paginacion_grilla(total, sel_key)
    df_page = df.iloc[offset : offset + _GRILLA_PAGE_SIZE]
    _render_grilla_filas_click(
        df_page,
        cols_grilla,
        sel_key=sel_key,
        key_prefix=key_prefix,
        row_offset=offset,
    )


def pagina_casos(
    *,
    titulo: str = "MAESTRO",
    subtitulo: str = "Pedidos desde Tango — tarifario por proveedor y control Wamaro.",
    proveedor: str | None = None,
    solo_pendiente_proveedor: bool = False,
    modo_elegir_proveedor: bool = False,
    key_prefix: str = "casos",
    carga_por_quincena: bool = True,
) -> None:
    _render_page_header(etiqueta_pagina(titulo), subtitulo, titulo)
    sel_key = f"{key_prefix}_sel"

    if not check_health_cached():
        st.stop()

    if not api_es_actual():
        st.error(
            "La **API** que está corriendo es una versión anterior (no aplica filtros por zona). "
            "Cerrá la ventana minimizada **Fletes-API**, ejecutá de nuevo **Iniciar_Fletes.bat** "
            "o corré `python scripts/kill_api_port.py` y volvé a iniciar."
        )

    ayuda_secciones: list[tuple[str, str]] = [
        (
            "Leyenda",
            _html_leyenda_operativa(),
        ),
        (
            "Filas y alertas",
            "Fila **roja** = hay algo para revisar. **Luz roja** en una columna = dónde está el problema. "
            "**🔍** abre el detalle.",
        ),
    ]
    if modo_elegir_proveedor:
        ayuda_secciones.append(
            (
                "Proveedor a elegir",
                "Solo casos excepcionales sin crossdock automático. **Crossdock** solo si el destino es "
                "Córdoba, Rosario o NOA **y** hay tarifa de **CLICPAQ + última milla** (LBO/FRANSOF/ALFARO). "
                "GBA u otro destino con CLICPAQ = un solo tramo. "
                "Casos con **empate de tarifario**: elegí proveedor en la columna **Proveedor** de cada fila.",
            )
        )
    _render_ayuda_referencia("Ayuda y referencia", ayuda_secciones, html_indices=frozenset({0}))

    with _panel_acciones(titulo, "Filtros y acciones"):
        c1, c2, c3, c4, c5 = st.columns(5)
        origen_f = c1.selectbox(
            "Origen",
            ["Todos", "Tortuguitas", "SA / Limansky"],
            format_func=lambda x: {
                "Todos": "Todos",
                "Tortuguitas": "Wamaro Tortuguitas",
                "SA / Limansky": "Wamaro SA",
            }[x],
            key=f"{key_prefix}_origen",
        )
        incluir_excl = c2.checkbox(
            "Incluir Amba / GBA",
            value=not modo_elegir_proveedor,
            key=f"{key_prefix}_incl_excl",
        )
        solo_diff = c3.checkbox("Solo con dif.", value=False, key=f"{key_prefix}_solo_diff")
        if c4.button("Reaplicar reglas y proveedores", key=f"{key_prefix}_reaplicar"):
            with st.spinner("Reaplicando reglas y cobros (puede tardar 1–2 min)…"):
                with api_client() as c:
                    r = c.post("/envios/reaplicar-reglas", timeout=300.0)
                    r.raise_for_status()
                    data = r.json()
                msg = f"Procesados: {data.get('procesados', 0)}"
                if data.get("remitos_corregidos"):
                    msg += f" · Remitos X→RAR: {data['remitos_corregidos']}"
                prov = data.get("proveedores") or {}
                if prov.get("crossdock"):
                    msg += f" · Crossdock: {prov['crossdock']}"
                st.toast(msg)
            st.rerun()
        if c5.button("Cruce prefacturas", key=f"{key_prefix}_macheo"):
            with api_client() as c:
                r = c.post("/mundo1/macheo/ejecutar")
                r.raise_for_status()
                st.toast(r.json())
            st.rerun()

        f1, f2, f3 = st.columns([2, 2, 3])
        solo_alerta = f1.checkbox(
            "Solo con alerta",
            value=False,
            key=f"{key_prefix}_solo_alerta",
        )
        solo_macheo = False
        if not solo_pendiente_proveedor and not modo_elegir_proveedor:
            solo_macheo = f2.checkbox(
                "Solo prefactura conciliada", value=False, key=f"{key_prefix}_solo_macheo"
            )
        buscar = f3.text_input(
            "Buscar remito o destinatario",
            placeholder="Ej: 318022 — luego «Buscar en toda la base»",
            key=f"{key_prefix}_buscar",
        )

        filtros_extra = _ui_filtros_fecha_remito(key_prefix)
        modo_carga_key = f"{key_prefix}_modo_carga"

        firma_ui = _firma_filtros_maestro_ui(
            origen_f=origen_f,
            incluir_excl=incluir_excl,
            solo_alerta=solo_alerta,
            solo_macheo=solo_macheo,
            solo_diff=solo_diff,
            filtros_extra=filtros_extra,
        )
        if carga_por_quincena:
            _invalidar_carga_si_cambian_filtros(
                key_prefix,
                firma_ui,
                modo_carga_key,
                clear_cache_fn=get_maestro_filas_cached.clear,
            )
        else:
            st.session_state[f"{key_prefix}_ui_sig"] = firma_ui

        modo_carga: str | None = None
        if carga_por_quincena:
            modo_carga = _render_carga_rango(
                key_prefix,
                filtros_extra,
                buscar,
                clear_cache_fn=get_maestro_filas_cached.clear,
                modulo="El maestro",
                page_state_key=f"{key_prefix}_maestro_page",
            )
            if not modo_carga:
                return

    params: dict[str, Any] = {"incluir_excluidos": incluir_excl}
    params.update(filtros_extra)
    if origen_f == "Tortuguitas":
        params["origen"] = "tortuguitas"
    elif origen_f == "SA / Limansky":
        params["origen"] = "sa"
    if proveedor:
        params["proveedor"] = proveedor
    if solo_pendiente_proveedor:
        params["solo_pendiente_proveedor"] = True
    if solo_alerta:
        params["solo_alerta"] = True
    if solo_macheo:
        params["solo_macheo"] = True
    if solo_diff:
        params["solo_con_dif"] = True

    if carga_por_quincena and modo_carga:
        try:
            params_api = _params_api_rango(
                params,
                key_prefix=key_prefix,
                buscar=buscar,
                modo_carga=modo_carga,
            )
        except ValueError as exc:
            st.error(str(exc))
            return
    else:
        if buscar.strip():
            params["q"] = buscar.strip()
        params_api = _params_sin_mes_si_busca(params, buscar)
        params_api.pop("fecha_desde_ui", None)
        params_api.pop("fecha_hasta_ui", None)

    firma_filtros = json.dumps(params_api, sort_keys=True, default=str)
    page = _reset_maestro_page_si_cambian_filtros(key_prefix, firma_filtros)
    params_api["page"] = page
    params_api["page_size"] = _MAESTRO_API_PAGE_SIZE

    try:
        spinner = (
            "Buscando en toda la base importada…"
            if (carga_por_quincena and modo_carga == "buscar") or (not carga_por_quincena and buscar.strip())
            else "Cargando casos del período…"
        )
        with st.spinner(spinner):
            payload, api_filtro_ok = get_maestro_filas_cached(
                json.dumps(params_api, sort_keys=True, default=str)
            )
        filas = payload.get("filas") or []
        total_maestro = int(payload.get("total") or 0)
        page = int(payload.get("page") or page)
        page_size = int(payload.get("page_size") or _MAESTRO_API_PAGE_SIZE)
        total_pages = int(payload.get("total_pages") or 1)
        st.session_state[f"{key_prefix}_maestro_page"] = page

        if not filas and total_maestro == 0:
            if modo_elegir_proveedor:
                st.success("No hay registros pendientes de elegir proveedor.")
            else:
                st.info(
                    "Sin datos en ese rango. Probá otras fechas o importá Tango desde **Configuración**."
                )
            return

        df = preparar_maestro_df(pd.DataFrame(filas))
        if proveedor and not api_filtro_ok:
            antes = len(df)
            df = filtrar_df_zona_proveedor(df, proveedor)
            if len(df) < antes:
                st.warning(
                    f"Filtro de zona aplicado en pantalla ({antes} → {len(df)}). "
                    "Reiniciá la API con **Iniciar_Fletes.bat** para tarifas correctas por proveedor."
                )

        if proveedor:
            st.metric(f"Registros en zona {etiqueta_proveedor(proveedor)}", total_maestro)
        elif solo_pendiente_proveedor or modo_elegir_proveedor:
            st.metric("Empates de proveedor", total_maestro)

        if solo_diff:
            st.warning(
                "Filtro **Solo con dif.** activo: registros con prefactura OK (dif = 0) **no se muestran**."
            )

        if buscar.strip():
            st.caption(
                f"Búsqueda en **toda la base importada** (sin filtro de mes): "
                f"**{total_maestro}** caso(s) encontrado(s)."
            )

        page = _controles_paginacion_maestro_api(
            key_prefix,
            total=total_maestro,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

        cols_grilla = [c for c in MAESTRO_VISTA_GRILLA if c in df.columns]
        show_df = _as_dataframe(df[cols_grilla].copy())
        for meta in _META_GRILLA:
            if meta in df.columns:
                show_df[meta] = df[meta]

        sel_key = f"{key_prefix}_sel"
        if modo_elegir_proveedor:
            _render_grilla_elegir_proveedor(
                df,
                key_prefix,
                sel_key=sel_key,
            )
        else:
            _render_grilla_con_detalle(show_df, df, sel_key=sel_key, paginar_cliente=False)

        if not solo_pendiente_proveedor and not modo_elegir_proveedor:
            export_key = f"{key_prefix}_export_xlsx"
            st.caption(
                "Export completo (todos los remitos del filtro actual, no solo la página)."
            )
            if st.button(
                "Generar planilla Excel (Tortuguitas + SA)",
                key=f"{key_prefix}_export_btn",
                type="secondary",
            ):
                try:
                    export_params: dict[str, Any] = {
                        "incluir_excluidos": incluir_excl,
                    }
                    for k in ("fecha_desde", "fecha_hasta", "campo_fecha", "proveedor"):
                        v = params_api.get(k)
                        if v not in (None, ""):
                            export_params[k] = v
                    with st.spinner("Generando Excel… puede tardar 1–2 minutos con muchos registros."):
                        with httpx.Client(base_url=API_URL, timeout=300.0) as c:
                            r = c.get("/maestro/export", params=export_params)
                            r.raise_for_status()
                        st.session_state[export_key] = r.content
                    st.success("Planilla lista — usá el botón de descarga.")
                except Exception as exc:
                    st.error(f"No se pudo exportar: {exc}")

            if st.session_state.get(export_key):
                st.download_button(
                    "Descargar maestro_wamaro.xlsx",
                    st.session_state[export_key],
                    file_name="maestro_wamaro.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"{key_prefix}_export_dl",
                )

    except Exception as exc:
        st.error(str(exc))


def _parse_candidatos_maestro(raw: Any) -> list[dict]:
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    try:
        return json.loads(raw) if isinstance(raw, str) else []
    except json.JSONDecodeError:
        return []


def _opciones_select_proveedor(fila: dict) -> tuple[list[str], dict[str, str]]:
    """Etiquetas para selectbox y mapa etiqueta → id proveedor."""
    candidatos = _parse_candidatos_maestro(fila.get("_proveedores_candidatos"))
    provincia = fila.get("PROVINCIA")
    localidad = fila.get("LOCALIDAD")
    cod_transp = fila.get("_transporte_cod") or fila.get("NRO TRANSP")
    nombre_transp = fila.get("TRANSPORTE")

    if proveedores_para_selector:
        try:
            items = proveedores_para_selector(
                provincia,
                localidad,
                candidatos,
                transporte_cod=cod_transp,
                transporte_nombre=nombre_transp,
            )
        except TypeError:
            items = proveedores_para_selector(provincia, localidad, candidatos)
            if proveedores_acotados_por_transporte:
                acotados = proveedores_acotados_por_transporte(
                    cod_transp, provincia, localidad, transporte_nombre=nombre_transp
                )
                if acotados:
                    items = [
                        (n, p)
                        for n, p in items
                        if str(n or "").strip().upper() in acotados
                    ]
    else:
        items = [(c.get("proveedor", ""), c.get("precio")) for c in candidatos if c.get("proveedor")]

    etiquetas: list[str] = ["— Elegir —"]
    mapa: dict[str, str] = {}
    sugerido = None
    try:
        from app.transporte_reglas import proveedor_sugerido_transporte

        sugerido = proveedor_sugerido_transporte(
            cod_transp, provincia, localidad, transporte_nombre=nombre_transp
        )
    except ImportError:
        pass

    for nombre, precio in items:
        if not nombre:
            continue
        star = "★ " if sugerido and nombre == sugerido else ""
        nom_vis = etiqueta_proveedor(str(nombre))
        if precio is not None and float(precio) > 0:
            lbl = f"{star}{nom_vis} ({fmt_pesos_ar(precio)})"
        else:
            lbl = f"{star}{nom_vis}"
        etiquetas.append(lbl)
        mapa[lbl] = str(nombre).strip().upper()
    return etiquetas, mapa


def _asignar_proveedor_callback(caso_id: str, state_key: str, mapa_key: str) -> None:
    etiqueta = st.session_state.get(state_key, "")
    if not etiqueta or str(etiqueta).startswith("—"):
        return
    mapa = st.session_state.get(mapa_key, {})
    proveedor = mapa.get(etiqueta) or str(etiqueta).split(" (")[0].strip().upper()
    if not proveedor or not caso_id:
        return
    try:
        with api_client() as client:
            r = client.post(
                "/proveedores/elegir",
                json={"remito_norm": caso_id, "proveedor": proveedor},
            )
            r.raise_for_status()
        st.toast(f"Proveedor {proveedor} asignado")
    except Exception as exc:
        st.session_state[state_key] = "— Elegir —"
        st.error(str(exc))


def _page_clicpaq() -> None:
    pagina_casos(
        titulo="CLICPAQ",
        subtitulo="Destinos de interior Clicpaq (excluye Salta/Jujuy/Tucumán y Córdoba exclusivos). Tarifario Clicpaq.",
        proveedor="CLICPAQ",
        key_prefix="clicpaq",
    )


def _page_fransof() -> None:
    pagina_casos(
        titulo="FRANSOF",
        subtitulo="Solo Rosario — tarifario Fransof.",
        proveedor="FRANSOF",
        key_prefix="fransof",
    )


def _page_alfaro() -> None:
    pagina_casos(
        titulo="ALFARO",
        subtitulo="Salta, Jujuy y Tucumán — tarifario Alfaro.",
        proveedor="ALFARO",
        key_prefix="alfaro",
    )


def _page_lbo() -> None:
    pagina_casos(
        titulo="LBO",
        subtitulo="Córdoba — tarifario LBO.",
        proveedor="LBO",
        key_prefix="lbo",
    )


MENU_PRINCIPAL = ["Dashboard", "MAESTRO", "Resumen", "Fletes", "Configuración"]


def _nav_on_principal() -> None:
    st.session_state.pagina_menu = st.session_state.nav_menu_principal


def _nav_on_proveedor() -> None:
    st.session_state.pagina_menu = st.session_state.nav_menu_proveedor


def _sidebar_nav_tree() -> str:
    """Menú compacto: radios + carpeta Proveedores (sin scroll en pantallas normales)."""
    if "pagina_menu" not in st.session_state:
        st.session_state.pagina_menu = "Dashboard"
    if st.session_state.pagina_menu == "Modo TOP":
        st.session_state.pagina_menu = "Resumen"

    activa = st.session_state.pagina_menu
    idx_principal = (
        MENU_PRINCIPAL.index(activa) if activa in MENU_PRINCIPAL else None
    )
    idx_proveedor = (
        MENU_PROVEEDORES.index(activa) if activa in MENU_PROVEEDORES else None
    )

    st.sidebar.radio(
        "Menú principal",
        MENU_PRINCIPAL,
        index=idx_principal,
        key="nav_menu_principal",
        label_visibility="collapsed",
        format_func=etiqueta_menu,
        on_change=_nav_on_principal,
    )

    with st.sidebar.expander("Proveedores", expanded=idx_proveedor is not None):
        st.radio(
            "Proveedores",
            MENU_PROVEEDORES,
            index=idx_proveedor,
            key="nav_menu_proveedor",
            label_visibility="collapsed",
            format_func=etiqueta_menu,
            on_change=_nav_on_proveedor,
        )

    nueva = st.session_state.pagina_menu
    anterior = st.session_state.get("_nav_pagina_anterior")
    if anterior is not None and anterior != nueva:
        st.session_state.pop(DETALLE_POPUP, None)
    st.session_state["_nav_pagina_anterior"] = nueva
    return nueva


def pagina_proveedor_elegir() -> None:
    pagina_casos(
        titulo="Proveedor a elegir",
        subtitulo=(
            "Solo remitos donde el **tarifario tiene 2+ proveedores** para esa localidad. "
            "Si el tarifario solo tiene uno, se asigna automático al reaplicar reglas."
        ),
        solo_pendiente_proveedor=True,
        modo_elegir_proveedor=True,
        key_prefix="elegir",
    )


def pagina_envios_interior() -> None:
    pagina_casos()


def pagina_modo_adrian() -> None:
    """Vista micro: LOG WAMARO diario (Resumen) vs maestro macro."""
    _render_page_header(
        etiqueta_pagina("Resumen"),
        "LOG WAMARO por día de entrega — interior y red Clickpack. "
        "Misma planilla Tango, recorte operativo del LOG diario (canal 51/83).",
        "Resumen",
    )

    if not check_health_cached():
        st.warning("Ejecutá **Iniciar_Fletes.bat**.")
        st.stop()

    if not api_es_actual():
        st.error(
            "La API es una versión anterior (falta el módulo **Resumen**). "
            "Reiniciá con **Iniciar_Fletes.bat**."
        )

    _render_ayuda_referencia(
        "¿Qué es esta vista?",
        [
            (
                "",
                "**Macro (Maestro / Fletes):** todos los casos Tango, tarifario completo, AMBA incluido. "
                "Los **fleteros locales** (transportistas AMBA/GBA de confianza) se cargan desde el Excel Drive "
                "y se ven en **Fletes** — no en esta planilla diaria.  \n\n"
                "**Resumen (LOG diario):** planilla diaria **WAMARO TORTUGUITAS** (CD Tortuguitas) — "
                "canal **51** (Expreso Clicpaq) y **83** (La Costa), remito oficial, "
                "un Excel por **fecha de entrega**. Mismo Tango ya importado; "
                "antes se armaba a mano, un archivo por día.",
            ),
        ],
    )

    planilla_api = "tortuguitas"

    with _panel_acciones("Resumen", "Filtros y acciones"):
        filtros = _ui_mes_control_adrian()
        params_mes = {
            "mes_control_anio": filtros["mes_control_anio"],
            "mes_control_mes": filtros["mes_control_mes"],
        }

        act1, act2, act3 = st.columns([1.4, 1.4, 2.2])
        if act1.button("Cruce prefacturas CLICPAQ", key="adrian_macheo"):
            with st.spinner("Cruzando prefacturas CLP con remitos…"):
                with api_client() as c:
                    r = c.post("/mundo1/macheo/ejecutar")
                    r.raise_for_status()
                    st.toast(r.json())
            _clear_adrian_cache()
            get_maestro_filas_cached.clear()
            st.rerun()
        if act2.button("Reaplicar reglas y proveedores", key="adrian_reaplicar"):
            with st.spinner("Reaplicando reglas y cobros…"):
                with api_client() as c:
                    r = c.post("/envios/reaplicar-reglas", timeout=300.0)
                    r.raise_for_status()
                    st.toast(f"Procesados: {r.json().get('procesados', 0)}")
            _clear_adrian_cache()
            get_maestro_filas_cached.clear()
            st.rerun()
        act3.caption(
            "Prefactura CLICPAQ **compartida** con el Maestro: importá en **Configuración** "
            "y ejecutá **Cruce prefacturas** (acá o en Maestro)."
        )

        try:
            with st.spinner("Cargando resumen…"):
                resumen = get_adrian_resumen_cached(json.dumps(params_mes, sort_keys=True))
                dias_resp = get_adrian_dias_cached(
                    json.dumps({**params_mes, "planilla": planilla_api}, sort_keys=True)
                )
        except Exception as exc:
            st.error(f"No se pudo cargar el resumen: {exc}")
            return

        pf = resumen.get("prefactura_clp") or {}
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Casos LOG (mes)", resumen.get("casos_tortuguitas", 0))
        m2.metric("Con prefactura CLP", pf.get("con_prefactura_clp", 0))
        m3.metric("Sin prefactura CLP", pf.get("sin_prefactura_clp", 0))
        m4.metric("Días con entregas", len(dias_resp.get("dias") or []))
        if pf.get("con_diferencia_prefactura"):
            st.caption(
                f"**{pf['con_diferencia_prefactura']}** caso(s) con diferencia prefactura vs tarifario."
            )

        dias = dias_resp.get("dias") or []
        if not dias:
            st.info(
                "Sin casos LOG en este mes con los filtros del corte diario. "
                "Probá otro mes o importá Tango desde **Configuración**."
            )
            return

        total_mes = int(resumen.get("casos_tortuguitas") or 0)
        opciones_dia = ["__todos__"] + [d["fecha"] for d in dias]
        labels_dia: dict[str, str] = {
            "__todos__": f"Mostrar todo — {total_mes} caso(s)",
        }
        for d in dias:
            labels_dia[d["fecha"]] = f"{d['fecha']} — {d['casos']} caso(s)"

        mes_key = f"{params_mes['mes_control_anio']}-{params_mes['mes_control_mes']}"
        if st.session_state.get("adrian_mes_prev") != mes_key:
            st.session_state.adrian_dia_sel = "__todos__"
            st.session_state.adrian_mes_prev = mes_key
            st.session_state.pop("adrian_buscar_grilla", None)
            st.session_state.pop("adrian_buscar_sig", None)
        elif st.session_state.get("adrian_dia_sel") not in opciones_dia:
            st.session_state.adrian_dia_sel = "__todos__"

        sel_dia = st.selectbox(
            "Día de entrega — WAMARO TORTUGUITAS",
            opciones_dia,
            format_func=lambda k: labels_dia[k],
            key="adrian_dia_sel",
        )
        ver_todo = sel_dia == "__todos__"

        page_key = "adrian_maestro_page"
        if st.session_state.get("adrian_dia_prev") != sel_dia:
            st.session_state[page_key] = 1
        st.session_state.adrian_dia_prev = sel_dia

        page = int(st.session_state.get(page_key, 1))
        page_size = 150

        buscar_key = "adrian_buscar_grilla"
        _reset_page_si_buscar_cambia("adrian", buscar_key)
        buscar = str(st.session_state.get(buscar_key, "") or "").strip()

        try:
            if ver_todo:
                mes_params: dict[str, Any] = {
                    "mes_control_anio": params_mes["mes_control_anio"],
                    "mes_control_mes": params_mes["mes_control_mes"],
                    "planilla": planilla_api,
                    "page": page,
                    "page_size": page_size,
                }
                if buscar:
                    mes_params["q"] = buscar
                with st.spinner("Cargando LOG del mes…"):
                    payload = get_adrian_mes_cached(
                        json.dumps(mes_params, sort_keys=True)
                    )
            else:
                dia_params: dict[str, Any] = {
                    "dia": sel_dia,
                    "planilla": planilla_api,
                    "page": page,
                    "page_size": page_size,
                }
                if buscar:
                    dia_params["q"] = buscar
                with st.spinner(f"Cargando LOG del {sel_dia}…"):
                    payload = get_adrian_dia_cached(
                        json.dumps(dia_params, sort_keys=True)
                    )
        except Exception as exc:
            st.error(str(exc))
            return

        filas = payload.get("filas") or []
        total = int(payload.get("total") or 0)
        page = int(payload.get("page") or page)
        total_pages = int(payload.get("total_pages") or 1)
        st.session_state[page_key] = page

        if ver_todo:
            st.caption(
                f"**{total}** caso(s) con entrega en el mes · planilla **WAMARO TORTUGUITAS**. "
                "Elegí un día arriba para ver el corte diario o exportar la planilla del día."
            )
        else:
            st.caption(
                f"**{total}** caso(s) con entrega **{sel_dia}** · planilla **WAMARO TORTUGUITAS**. "
                "Columna TRANSPORTE en formato operativo (CLICPAQ / LA COSTA)."
            )

        if not filas:
            st.warning("Sin filas para esta vista.")
            _controles_paginacion_maestro_api(
                "adrian",
                total=total,
                page=page,
                page_size=page_size,
                total_pages=total_pages,
                buscar_key=buscar_key,
            )
            return

        if buscar:
            st.caption(f"Búsqueda **«{buscar}»** — **{total}** caso(s) encontrado(s).")
        page = _controles_paginacion_maestro_api(
            "adrian",
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            buscar_key=buscar_key,
        )

    ref = resumen.get("referencia_adrian_abr_2026") or {}
    _render_ayuda_referencia(
        "Referencia validación (abr 2026)",
        [
            (
                "",
                f"Referencia manual abr/2026 — LOG Tortuguitas: **{ref.get('log_tortuguitas_remitos', '—')}** "
                f"remitos · LOG SA: **{ref.get('log_sa_remitos', '—')}** remitos. "
                "Solo referencia histórica; no limita el sistema.",
            ),
        ],
    )

    df = preparar_maestro_df(pd.DataFrame(filas))
    cols_grilla = [c for c in MAESTRO_VISTA_GRILLA if c in df.columns]
    show_df = _as_dataframe(df[cols_grilla].copy())
    for meta in _META_GRILLA:
        if meta in df.columns:
            show_df[meta] = df[meta]

    _render_grilla_con_detalle(
        show_df,
        df,
        sel_key="adrian_sel",
        paginar_cliente=False,
        ayuda_notas=(
            "Tarifario y **prefactura CLICPAQ compartidos con el Maestro**. "
            "PRECIO NETO / dif se cargan con el cruce CLP. "
            "Fila roja solo si falta tarifa o hay diferencia real."
        ),
    )

    if not ver_todo:
        export_key = "adrian_export_xlsx"
        from datetime import date as _date

        d_obj = _date.fromisoformat(sel_dia)
        fname = f"WAMARO TORTUGUITAS - {d_obj.day:02d}_{d_obj.month:02d}_{d_obj.year}.xlsx"

        if st.button("Generar Excel del día (formato WAMARO)", key="adrian_export_btn"):
            try:
                with st.spinner("Generando Excel…"):
                    with httpx.Client(base_url=API_URL, timeout=120.0) as c:
                        r = c.get(
                            "/modo-adrian/export-dia",
                            params={"dia": sel_dia, "planilla": planilla_api},
                        )
                        r.raise_for_status()
                    st.session_state[export_key] = r.content
                st.success("Planilla lista — descargá abajo.")
            except Exception as exc:
                st.error(f"No se pudo exportar: {exc}")

        if st.session_state.get(export_key):
            st.download_button(
                f"Descargar {fname}",
                st.session_state[export_key],
                file_name=fname,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="adrian_export_dl",
            )


def pagina_fletes() -> None:
    _render_page_header(
        "Fletes",
        "Mirada macro Mundo 2 — entregas CABA/GBA, **fleteros locales** (transporte sucursal → domicilio) "
        "y tarifa ref. fletes sucursales (zona km).",
        "Fletes",
    )
    _render_ayuda_referencia(
        "Ayuda y referencia",
        [
            ("Leyenda", _html_leyenda_operativa()),
            (
                "Alertas",
                "Columnas **Fletero**, **Sucursal**, **Km** y **Zona km** marcan ⚠ cuando falta "
                "completar datos locales. Seleccioná una fila para ver el detalle.",
            ),
        ],
        html_indices=frozenset({0}),
    )

    if not check_health_cached():
        st.warning("Ejecutá **Iniciar_Fletes.bat**.")
        st.stop()

    key_prefix = "fletes"

    with _panel_acciones("Fletes", "Filtros y acciones"):
        filtros_extra = _ui_filtros_fecha_remito("fletes")
        modo_carga_key = f"{key_prefix}_modo_carga"

        f1, f2, f3, f4 = st.columns([2, 2, 2, 2])
        origen_f = f1.selectbox(
            "Origen CD",
            ["Todos", "Tortuguitas", "SA / Limansky"],
            format_func=lambda x: {
                "Todos": "Todos",
                "Tortuguitas": "Wamaro Tortuguitas",
                "SA / Limansky": "Wamaro SA",
            }[x],
            key="fletes_origen",
        )
        solo_alerta_f = f2.checkbox("Solo con alerta", value=False, key="fletes_solo_alerta")
        buscar = f3.text_input(
            "Buscar remito o destinatario",
            placeholder="Ej: 318022 — luego «Buscar en toda la base»",
            key="fletes_buscar",
        )
        try:
            fleteros_api = get_fleteros_cached()
            opciones_f = ["Todos"] + [f["nombre_corto"] for f in fleteros_api]
        except Exception:
            opciones_f = ["Todos"]
        fletero_f = f4.selectbox("Fletero local", opciones_f, key="fletes_fletero")

        firma_ui = json.dumps(
            {
                "origen": origen_f,
                "solo_alerta": solo_alerta_f,
                "fletero": fletero_f,
                "pend_zona": bool(st.session_state.get("fletes_solo_pendiente_zona", False)),
                "filtros_extra": filtros_extra,
            },
            sort_keys=True,
            default=str,
        )
        _invalidar_carga_si_cambian_filtros(
            key_prefix,
            firma_ui,
            modo_carga_key,
            clear_cache_fn=_clear_fletes_cache,
        )

        modo_carga = _render_carga_rango(
            key_prefix,
            filtros_extra,
            buscar,
            clear_cache_fn=_clear_fletes_cache,
            modulo="Fletes",
            page_state_key=f"{key_prefix}_maestro_page",
        )
        if not modo_carga:
            return

    params_base: dict[str, Any] = dict(filtros_extra)
    if origen_f == "Tortuguitas":
        params_base["origen"] = "tortuguitas"
    elif origen_f == "SA / Limansky":
        params_base["origen"] = "sa"
    if fletero_f and fletero_f != "Todos":
        params_base["fletero"] = fletero_f
    if solo_alerta_f:
        params_base["solo_alerta"] = True
    if st.session_state.get("fletes_solo_pendiente_zona"):
        params_base["solo_pendiente_zona_km"] = True

    try:
        params_api = _params_api_rango(
            params_base,
            key_prefix=key_prefix,
            buscar=buscar,
            modo_carga=modo_carga,
        )
    except ValueError as exc:
        st.error(str(exc))
        return

    firma_filtros = json.dumps(params_api, sort_keys=True, default=str)
    page = _reset_maestro_page_si_cambian_filtros(key_prefix, firma_filtros)
    params_api["page"] = page
    params_api["page_size"] = _MAESTRO_API_PAGE_SIZE

    params_api["page"] = page
    params_api["page_size"] = _MAESTRO_API_PAGE_SIZE

    stats_params = {
        k: params_api[k]
        for k in ("fecha_desde", "fecha_hasta", "campo_fecha", "mes_control_anio", "mes_control_mes")
        if k in params_api
    }

    try:
        spinner = (
            "Buscando en toda la base importada…"
            if modo_carga == "buscar"
            else "Cargando casos Fletes…"
        )
        with st.spinner(spinner):
            payload = get_fletes_pagina_cached(
                json.dumps(params_api, sort_keys=True, default=str)
            )
        filas = payload.get("filas") or []
        total_fletes = int(payload.get("total") or 0)
        page = int(payload.get("page") or page)
        page_size = int(payload.get("page_size") or _MAESTRO_API_PAGE_SIZE)
        total_pages = int(payload.get("total_pages") or 1)
        st.session_state[f"{key_prefix}_maestro_page"] = page

        if not filas and total_fletes == 0:
            st.info(
                "No hay casos de flete en la base. Si ya importaste Tango, "
                "revisá que haya pedidos Amba/GBA o ejecutá **Reaplicar reglas** en Maestro."
            )
            return

        df = preparar_maestro_df(pd.DataFrame(filas))

        if st.session_state.get("fletes_solo_pendiente_zona"):
            st.info(
                f"Grilla filtrada: **{total_fletes}** casos **pendientes de zona km** "
                "(tienen tarifario local pero falta asignar zona / calcular km)."
            )
        elif modo_carga == "buscar":
            st.caption(
                f"Búsqueda en **toda la base importada** (sin filtro de mes): "
                f"**{total_fletes}** caso(s) encontrado(s)."
            )
        elif solo_alerta_f:
            st.caption(f"**{total_fletes}** casos con alerta en el período.")
        else:
            st.caption(f"**{total_fletes}** casos en el período.")

        page = _controles_paginacion_maestro_api(
            key_prefix,
            total=total_fletes,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

        cols = [c for c in FLETES_VISTA_GRILLA if c in df.columns]
        show_df = _as_dataframe(df[cols].copy())
        for meta in _META_GRILLA:
            if meta in df.columns:
                show_df[meta] = df[meta]

        _render_grilla_con_detalle(show_df, df, sel_key="fletes_sel", paginar_cliente=False)
    except Exception as exc:
        st.error(str(exc))
        return

    try:
        with st.spinner("Métricas del período…"):
            stats = get_fletes_stats_cached(
                json.dumps(stats_params, sort_keys=True, default=str)
            )
    except Exception as exc:
        st.warning(f"Métricas no disponibles: {exc}")
        stats = {}

    pend_zona_raw = stats.get("pendiente_zona_km")
    pend_zona = int(pend_zona_raw) if pend_zona_raw is not None else 0
    filtro_pendiente = bool(st.session_state.get("fletes_solo_pendiente_zona", False))
    metrics_cls = "module-metrics pend-filter-on" if filtro_pendiente else "module-metrics"

    st.markdown("---")
    st.markdown(f'<div class="{metrics_cls}">', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Casos fletes", stats.get("casos_fletes", total_fletes))
    c2.metric("Renglones Amba/GBA", stats.get("renglones_fletes", stats.get("renglones_mundo2", 0)))
    c3.metric("Con km calculado", stats.get("con_km_calculado", 0))
    with c4:
        if pend_zona_raw is None:
            c4.metric("Pend. zona km", "—")
        else:
            c4.metric("Pend. zona km", pend_zona)
            if pend_zona > 0:
                btn_label = "Ver todos" if filtro_pendiente else "Ver pendientes"
                if st.button(
                    btn_label,
                    key="fletes_toggle_pend_zona",
                    type="secondary" if filtro_pendiente else "primary",
                    use_container_width=True,
                ):
                    st.session_state["fletes_solo_pendiente_zona"] = not filtro_pendiente
                    st.rerun()
            elif filtro_pendiente:
                st.session_state["fletes_solo_pendiente_zona"] = False
    st.markdown("</div>", unsafe_allow_html=True)

    if stats.get("envios_cargados") is not None:
        st.caption(
            f"Período cargado: **{stats.get('envios_cargados', 0):,}** renglones Tango en memoria."
        )

    # Mes de referencia para el panel fleteros (usa el "Hasta" del rango activo)
    from datetime import date as _date_ref

    mes_ref, anio_ref = _date_ref.today().month, _date_ref.today().year
    activo_panel = st.session_state.get(f"{key_prefix}_rango_activo") or {}
    fh_panel = activo_panel.get("fecha_hasta") or params_api.get("fecha_hasta")
    if fh_panel:
        try:
            d_panel = _date_ref.fromisoformat(str(fh_panel)[:10])
            mes_ref, anio_ref = d_panel.month, d_panel.year
        except ValueError:
            pass
    _render_panel_fleteros_macro(stats, mes=mes_ref, anio=anio_ref)

    with st.expander("Qué falta bajar de Tango (cuando puedas)"):
        st.markdown(
            """
            - Export del tablero **Seguimientos centralizados** para entregas locales (Distribuidora / sucursales).
            - Que el Excel traiga **código de sucursal** (AV, BE, CA…) si existe.
            - Km en Tango (si existe) o prefactura del **transportista de flete local** cuando tengan formato.

            Detalle: `data/TANGO_PENDIENTE_MUNDO2.md`
            """
        )

    if (
        fletero_f
        and fletero_f != "Todos"
        and modo_carga == "rango"
        and not buscar.strip()
    ):
        activo = st.session_state.get(f"{key_prefix}_rango_activo") or {}
        fd = activo.get("fecha_desde") or ""
        fh = activo.get("fecha_hasta") or ""
        # Resumen mensual del fletero: usa mes del "Hasta" como referencia
        try:
            from datetime import date as _date

            d_ref = _date.fromisoformat(fh) if fh else None
            if d_ref is not None:
                res_f = get_json(
                    "/fletes/internos/resumen",
                    mes=d_ref.month,
                    anio=d_ref.year,
                    fletero=fletero_f,
                )
                for row in res_f.get("fleteros") or []:
                    if row.get("nombre_corto") == fletero_f:
                        st.info(
                            f"**{fletero_f}** en {d_ref.strftime('%m/%Y')}: "
                            f"{row.get('entregas', 0)} entregas Drive · "
                            f"{row.get('matcheadas', 0)} en maestro Fletes · "
                            f"total a pagar **{fmt_pesos_ar(row.get('total_pagar', 0))}** "
                            f"(resumen del mes; la grilla respeta el rango "
                            f"**{fd} → {fh}**)."
                        )
                        break
        except Exception:
            pass

    c_prev, c_km500, c_km1000, _ = st.columns([2, 2, 2, 2])
    if c_prev.button("Actualizar preview (alias/barrio)", key="fletes_enrich_preview"):
        try:
            with api_client() as c:
                r = c.post("/fletes/enriquecer-preview")
                r.raise_for_status()
                st.session_state["fletes_preview_stats"] = r.json()
                get_fletes_pagina_cached.clear()
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    def _calcular_km_fletes(limite: int) -> None:
        try:
            with st.spinner(f"Calculando km reales (hasta {limite})…"):
                with api_client() as c:
                    r = c.post("/fletes/calcular-km", params={"limit": limite})
                    r.raise_for_status()
                    st.session_state["fletes_km_stats"] = r.json()
                get_fletes_pagina_cached.clear()
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    if c_km500.button("Km reales (500)", key="fletes_calc_km_500"):
        _calcular_km_fletes(500)
    if c_km1000.button("Km reales (1000)", key="fletes_calc_km_1000"):
        _calcular_km_fletes(1000)

    prev_stats = st.session_state.get("fletes_preview_stats")
    km_stats = st.session_state.get("fletes_km_stats")
    if prev_stats and prev_stats.get("enriquecidos"):
        st.caption(
            f"Preview automático: **{prev_stats['enriquecidos']}** casos con sucursal/km estimado."
        )
    if km_stats and km_stats.get("calculados"):
        reuso = km_stats.get("reusados_domicilio", 0)
        extra = f" · **{reuso}** reusados por domicilio" if reuso else ""
        st.caption(
            f"Último cálculo km: **{km_stats['calculados']}** casos "
            f"({km_stats.get('estimados_localidad', 0)} estimados por localidad){extra}."
        )

    st.caption(
        "Tras cargar el período: hasta **30 km reales** automáticos por rango. "
        "**Actualizar preview** asigna sucursal/km estimado; **Km reales (500/1000)** geocodifica el resto."
    )


def _archivos_fleteros_red() -> list[Path]:
    """Excels «Fletes solicitados sucursales» en carpeta LOG (S:)."""
    base = FLETEROS_LOG_S_DIR
    if not base.is_dir():
        return []
    found: list[Path] = []
    seen: set[str] = set()
    for pat in (
        "*Fletes Solicitados*Log*.xlsx",
        "*Copia de Fletes Solicitados*.xlsx",
    ):
        for p in sorted(base.glob(pat), key=lambda x: -x.stat().st_mtime):
            if p.name not in seen:
                seen.add(p.name)
                found.append(p)
    return found


def _importar_fleteros_desde_path(path: Path, *, matchear: bool = False) -> dict[str, Any]:
    return post_file(
        "/fletes/internos/import",
        path.name,
        path.read_bytes(),
        matchear="true" if matchear else "false",
    )


def _render_panel_fleteros_macro(
    stats: dict[str, Any] | None,
    *,
    mes: int,
    anio: int,
) -> None:
    """Resumen fleteros Drive + maestro Fletes (mirada macro Mundo 2)."""
    fd = (stats or {}).get("fleteros_drive") or {}
    fp = (stats or {}).get("fleteros_periodo") or {}
    if not fd.get("solicitudes"):
        st.info(
            "Sin solicitudes de fleteros en la base. Importá el Excel del Drive en "
            "**Configuración → Fleteros locales** (archivos en carpeta LOG **S:**)."
        )
        return

    st.markdown("**Fleteros locales (Drive → maestro)**")
    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Solicitudes Drive", fd.get("solicitudes", 0))
    r2.metric("Matcheadas", fd.get("matcheadas", 0))
    r3.metric("Casos con fletero", (stats or {}).get("casos_con_fletero", 0))
    r4.metric(
        "Total a pagar (mes)",
        fmt_pesos_ar(fp.get("total_pagar", 0)),
        help="Tarifario FLETES_SUC sobre casos matcheados en el mes de control.",
    )
    por_f = fp.get("por_fletero") or []
    if por_f:
        df_f = pd.DataFrame(por_f)
        show = [
            c
            for c in (
                "nombre_corto",
                "entregas",
                "matcheadas",
                "total_pagar",
                "sin_tarifa",
            )
            if c in df_f.columns
        ]
        rename = {
            "nombre_corto": "Fletero",
            "entregas": "Drive",
            "matcheadas": "En maestro",
            "total_pagar": "Total $",
            "sin_tarifa": "Sin tarifa",
        }
        df_show = df_f[show].copy()
        df_show.columns = [rename.get(str(c), str(c)) for c in df_show.columns]
        if "Total $" in df_show.columns:
            df_show["Total $"] = [
                fmt_pesos_ar(v) for v in df_show["Total $"].tolist()
            ]
        st.dataframe(df_show, width="stretch", hide_index=True, height=min(220, 38 + 35 * len(df_show)))


def _config_fleteros_locales() -> None:
    """Pestaña Configuración — Excel Drive + macheo contra maestro Fletes."""
    from datetime import date

    st.subheader("Fleteros locales (AMBA / GBA)")
    st.caption(
        "**Mirada macro (Mundo 2 / Fletes):** entregas sucursal → domicilio con "
        "**fleteros locales** (transportistas de confianza en AMBA/GBA). El cliente puede ver **$0**; "
        "acá cargás el Excel del Drive y lo cruzás con el **maestro Fletes**. "
        "**No aplica** al LOG diario Resumen (interior canal 51/83)."
    )
    plantilla_download(
        "plantilla_fletes_solicitud.xlsx",
        "Descargar plantilla Excel (formato Drive)",
    )
    st.caption(
        "Mismo formato que el Excel compartido en Drive "
        "«Fletes solicitados sucursales»."
    )

    try:
        solicitudes = get_json("/fletes/internos/solicitudes")
    except Exception:
        solicitudes = []

    n_sol = len(solicitudes)
    n_match = sum(
        1
        for s in solicitudes
        if str(s.get("match_estado") or "").startswith("matcheado")
    )
    c1, c2, c3 = st.columns(3)
    c1.metric("Registros cargados", n_sol)
    c2.metric("Matcheados con maestro", n_match)
    c3.metric("Pendientes de cruce", max(0, n_sol - n_match))

    archivos_red = _archivos_fleteros_red()
    with st.expander("Importar desde carpeta LOG (S:)", expanded=not n_sol and bool(archivos_red)):
        st.markdown(
            f"Carpeta: `{FLETEROS_LOG_S_DIR}`  \n"
            "Archivos detectados (export Drive «Fletes solicitados sucursales»):"
        )
        if not archivos_red:
            st.warning(
                "No se encontró la carpeta de red o no hay Excels de fleteros. "
                "Usá el uploader manual abajo."
            )
        else:
            for p in archivos_red:
                kb = max(1, p.stat().st_size // 1024)
                bc1, bc2 = st.columns([3, 1])
                bc1.caption(f"**{p.name}** ({kb} KB)")
                if bc2.button("Importar", key=f"cfg_flet_s_{p.name}"):
                    try:
                        with st.spinner(f"Importando {p.name}…"):
                            r = _importar_fleteros_desde_path(p, matchear=False)
                        st.success(
                            f"{p.name}: {r.get('insertados', 0)} nuevos · "
                            f"{r.get('actualizados', 0)} actualizados"
                        )
                        if r.get("fleteros"):
                            st.caption(f"Fleteros: {', '.join(r['fleteros'])}")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
            if st.button(
                "Importar todos + machear",
                type="primary",
                key="cfg_flet_s_todos",
                disabled=not archivos_red,
            ):
                try:
                    total_ins = total_upd = 0
                    fleteros_v: set[str] = set()
                    with st.spinner("Importando desde S:…"):
                        for p in archivos_red:
                            r = _importar_fleteros_desde_path(p, matchear=False)
                            total_ins += int(r.get("insertados") or 0)
                            total_upd += int(r.get("actualizados") or 0)
                            fleteros_v.update(r.get("fleteros") or [])
                        with api_client() as c:
                            m = c.post("/fletes/internos/matchear")
                            m.raise_for_status()
                            match = m.json()
                    st.success(
                        f"Importados: {total_ins} nuevos · {total_upd} actualizados · "
                        f"macheo {match.get('matcheadas', 0)}/{match.get('procesadas', 0)}"
                    )
                    if fleteros_v:
                        st.caption(f"Fleteros: {', '.join(sorted(fleteros_v))}")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

    upl = st.file_uploader(
        "Excel «Fletes solicitados sucursales»",
        type=["xlsx"],
        key="cfg_fleteros_import",
    )
    b1, b2 = st.columns(2)
    if b1.button("Importar Excel", type="primary", disabled=upl is None, key="cfg_flet_btn_import"):
        try:
            if upl is None:
                raise RuntimeError("Seleccioná un archivo.")
            r = post_file(
                "/fletes/internos/import",
                upl.name,
                upl.getvalue(),
                matchear="false",
            )
            st.success(
                f"Cargados: {r.get('insertados', 0)} nuevos · "
                f"{r.get('actualizados', 0)} actualizados"
            )
            if r.get("fleteros"):
                st.caption(f"Fleteros detectados: {', '.join(r['fleteros'])}")
            st.info("Ejecutá **Machear con maestro Fletes** para cruzar con Tango.")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    if b2.button("Machear con maestro Fletes", disabled=n_sol == 0, key="cfg_flet_btn_match"):
        try:
            with api_client() as c:
                r = c.post("/fletes/internos/matchear")
                r.raise_for_status()
                m = r.json()
            st.success(
                f"Macheo: {m.get('matcheadas', 0)} de {m.get('procesadas', 0)} · "
                f"por pedido: {m.get('matcheadas_pedido', 0)} · "
                f"por cliente/fecha: {m.get('matcheadas_cliente', 0)} · "
                f"sin caso en maestro: {m.get('sin_envio', 0)}"
            )
            st.caption(
                f"Casos Fletes en maestro: {m.get('envios_fletes_maestro', '—')} · "
                f"pedidos indexados: {m.get('pedidos_indexados', '—')}"
            )
            if m.get("sin_envio", 0) > 0:
                st.warning(
                    "Los no matcheados suelen faltar en el export Tango del mes "
                    "(pedido del Drive distinto al NRO PEDIDO del maestro). "
                    "Revisá que Tango esté importado para ese mes y volvé a machear."
                )
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    if solicitudes:
        df_sol = pd.DataFrame(solicitudes)
        show = [
            c
            for c in (
                "id_flete",
                "fletero",
                "cliente",
                "nro_pedido",
                "local_entrega",
                "fecha_entrega",
                "match_estado",
                "remito_norm",
                "estado",
            )
            if c in df_sol.columns
        ]
        st.markdown("**Datos cargados**")
        st.dataframe(df_sol[show], width="stretch", hide_index=True)

        st.markdown("---")
        st.markdown("**Resumen por fletero (período)**")
        mc1, mc2 = st.columns(2)
        hoy = date.today()
        mes_ctrl = mc1.number_input(
            "Mes control", 1, 12, hoy.month, key="cfg_fleteros_mes"
        )
        anio_ctrl = mc2.number_input(
            "Año control", 2024, 2030, hoy.year, key="cfg_fleteros_anio"
        )
        try:
            resumen = get_json(
                "/fletes/internos/resumen",
                mes=int(mes_ctrl),
                anio=int(anio_ctrl),
            )
            r1, r2 = st.columns(2)
            r1.metric("Entregas en período", resumen.get("total_entregas", 0))
            r2.metric(
                "Total a pagar (tarifario FLETES_SUC)",
                fmt_pesos_ar(resumen.get("total_pagar", 0)),
            )
            filas_res = resumen.get("fleteros") or []
            if filas_res:
                df_res = pd.DataFrame(filas_res)
                show_cols = [
                    c
                    for c in (
                        "nombre_corto",
                        "fletero",
                        "entregas",
                        "matcheadas",
                        "total_pagar",
                        "sin_tarifa",
                    )
                    if c in df_res.columns
                ]
                rename_map = {
                    "nombre_corto": "Código",
                    "fletero": "Nombre",
                    "entregas": "Entregas",
                    "matcheadas": "En maestro",
                    "total_pagar": "Total $",
                    "sin_tarifa": "Sin tarifa km",
                }
                df_resumen = df_res[show_cols].copy()
                df_resumen.columns = [
                    rename_map.get(str(c), str(c)) for c in df_resumen.columns
                ]
                st.dataframe(df_resumen, width="stretch", hide_index=True)
        except Exception as exc:
            st.error(str(exc))

        with st.expander("Mantenimiento", expanded=False):
            st.caption(
                "Vaciar solicitudes importadas del Drive. **No afecta** envíos Tango, "
                "tarifarios ni el maestro Fletes."
            )
            if st.button("Vaciar solicitudes cargadas", key="cfg_flet_vaciar"):
                try:
                    with api_client() as c:
                        r = c.delete("/fletes/internos/solicitudes")
                        r.raise_for_status()
                        msg = r.json()
                    st.success(msg.get("message", "Listo"))
                    get_fleteros_cached.clear()
                    get_fletes_pagina_cached.clear()
                    get_fletes_stats_cached.clear()
                    get_dashboard_stats_cached.clear()
                    get_dashboard_gerencial_cached.clear()
                    get_kpi_entregas_cached.clear()
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
    else:
        st.info(
            "Sin datos de fleteros locales. Importá desde la carpeta LOG en **S:** "
            "(archivos «Fletes Solicitados sucursales» del mes en curso) "
            "o subí un Excel manualmente."
        )


@st.dialog("Importar planilla desde Drive")
def _dialog_import_cross_drive() -> None:
    st.markdown(
        "Pegá el link compartido de Google Sheets o Drive "
        "(permiso **Lector con link**). El sistema descarga el Excel e importa "
        "las pestañas **Retirado por …**."
    )
    url = st.text_input(
        "Link de Google Sheets / Drive",
        placeholder="https://docs.google.com/spreadsheets/d/…",
        key="cfg_cross_drive_url",
    )
    nombre = st.text_input(
        "Nombre (opcional)",
        placeholder="ej. Cross Córdoba",
        key="cfg_cross_drive_nombre",
    )
    matchear = st.checkbox(
        "Machear con maestro al importar", value=True, key="cfg_cross_drive_match"
    )
    c_ok, c_cancel = st.columns(2)
    if c_cancel.button("Cancelar", key="cfg_cross_drive_cancel"):
        st.rerun()
    if c_ok.button("Descargar e importar", type="primary", key="cfg_cross_drive_ok"):
        link = (url or "").strip()
        if not link:
            st.error("Pegá el link del archivo.")
            return
        try:
            with st.spinner("Descargando planilla…"):
                data = post_json(
                    "/cross/import-drive-link",
                    {"url": link, "nombre": (nombre or "").strip() or None},
                    matchear=matchear,
                )
            st.success(data.get("message", "Importado"))
            if data.get("hojas_procesadas"):
                st.caption(f"Hojas: {', '.join(data['hojas_procesadas'])}")
            if data.get("macheo"):
                m = data["macheo"]
                st.info(
                    f"Macheo: {m.get('en_maestro', 0)} en maestro · "
                    f"{m.get('sin_maestro', 0)} solo en planilla"
                )
            get_maestro_filas_cached.clear()
            st.rerun()
        except httpx.HTTPStatusError as exc:
            st.error(_detalle_error_api(exc))
        except Exception as exc:
            st.error(str(exc))


def _config_cross_seguimiento() -> None:
    """Planillas cross «Retirado por …» — revisión colaborativa por remito."""
    st.subheader("Seguimiento cross (interior)")
    st.caption(
        "Importá las planillas de Drive donde cada sucursal registra retiros y entregas "
        "(pestaña **Retirado por Logística Alfaro / Fransof / …**). "
        "No factura: solo cruza por **remito** con el maestro para revisión."
    )

    try:
        resumen = get_json("/cross/resumen")
    except Exception:
        resumen = {}

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Registros cross", resumen.get("total", 0))
    c2.metric("En maestro", resumen.get("en_maestro", 0))
    c3.metric("Entregado SI", resumen.get("entregado_si", 0))
    c4.metric("Entregado NO", resumen.get("entregado_no", 0))

    try:
        planillas = get_json("/cross/planillas-drive")
    except Exception:
        planillas = []

    with st.expander("Planillas Drive configuradas", expanded=bool(planillas)):
        if st.button("Probar acceso a Drive (sin importar)", key="cfg_cross_probe"):
            try:
                with st.spinner("Probando export de cada planilla…"):
                    probe = get_json("/cross/planillas-drive", probar=True)
                st.session_state["cross_probe"] = probe
            except Exception as exc:
                st.error(str(exc))
        probe = st.session_state.get("cross_probe") or []
        probe_by_label = {p.get("label"): p for p in probe if p.get("label")}

        if planillas:
            for p in planillas:
                label = p.get("label")
                estado_cfg = "activa" if p.get("activo") else "off"
                pr = probe_by_label.get(label)
                if pr:
                    if pr.get("ok"):
                        st.success(
                            f"**{label}** — acceso OK · {pr.get('bytes', 0):,} bytes · "
                            f"`{p.get('sheet_id')}`"
                        )
                    else:
                        st.error(f"**{label}** — {pr.get('motivo', 'sin acceso')}")
                        st.caption(f"`{p.get('sheet_id')}` · HTTP {pr.get('http_status', '—')}")
                else:
                    st.caption(f"**{label}** — `{p.get('sheet_id')}` ({estado_cfg})")
        st.info(
            "La app descarga **sin login de Google**. Cada planilla debe estar en "
            "**Compartir → Cualquiera con el enlace → Lector**. "
            "Si solo la compartieron con tu mail @empresa, desde el servidor sigue fallando (401)."
        )
        st.caption(
            "**En maestro = 0** es distinto: los 779 registros cross pueden estar cargados, "
            "pero los remitos aún no coinciden con Tango — usá **Machear con maestro** "
            "después de importar envíos."
        )

    upl = st.file_uploader(
        "Excel cross (pestaña Retirado por …)",
        type=["xlsx"],
        key="cfg_cross_import",
    )
    b1, b2, b3, b4 = st.columns(4)
    if b1.button(
        "Importar Excel", type="primary", disabled=upl is None, key="cfg_cross_btn_import"
    ):
        try:
            if upl is None:
                raise RuntimeError("Seleccioná un archivo.")
            r = post_file("/cross/import", upl.name, upl.getvalue(), matchear="true")
            st.success(r.get("message", "Importado"))
            if r.get("hojas_procesadas"):
                st.caption(f"Hojas: {', '.join(r['hojas_procesadas'])}")
            if r.get("macheo"):
                m = r["macheo"]
                st.info(
                    f"Macheo: {m.get('en_maestro', 0)} en maestro · "
                    f"{m.get('sin_maestro', 0)} solo en planilla"
                )
            get_maestro_filas_cached.clear()
            st.rerun()
        except Exception as exc:
            st.error(_detalle_error_api(exc) if hasattr(exc, "response") else str(exc))

    if b2.button("Sincronizar desde Drive", key="cfg_cross_btn_sync"):
        try:
            with st.spinner("Descargando planillas públicas…"):
                with httpx.Client(base_url=API_URL, timeout=180.0) as c:
                    r = c.post("/cross/sync-drive", params={"matchear": "true"})
                    r.raise_for_status()
                    data = r.json()
            st.success(data.get("message", "Sync OK"))
            for item in data.get("resultados") or []:
                if item.get("ok"):
                    st.caption(
                        f"✓ {item.get('label')}: {item.get('insertados', 0)} nuevos · "
                        f"{item.get('actualizados', 0)} act."
                    )
                else:
                    st.warning(f"✗ {item.get('label')}: {item.get('motivo', 'error')}")
            if data.get("macheo"):
                m = data["macheo"]
                st.info(
                    f"Macheo total: {m.get('en_maestro', 0)} en maestro · "
                    f"{m.get('sin_maestro', 0)} solo planilla"
                )
            get_maestro_filas_cached.clear()
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    if b3.button("Importar desde link Drive", key="cfg_cross_btn_drive_link"):
        _dialog_import_cross_drive()

    if b4.button(
        "Machear con maestro", disabled=not resumen.get("total"), key="cfg_cross_btn_match"
    ):
        try:
            with api_client() as c:
                r = c.post("/cross/matchear")
                r.raise_for_status()
                m = r.json()
            st.success(
                f"Macheo: {m.get('en_maestro', 0)} en maestro · "
                f"{m.get('sin_maestro', 0)} solo en planilla"
            )
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    if resumen.get("total"):
        try:
            regs = get_json("/cross/registros", limit=100, solo_maestro=True)
        except Exception:
            regs = []
        if regs:
            st.markdown("**Últimos con match en maestro**")
            df = pd.DataFrame(regs)
            show = [
                c
                for c in (
                    "remito",
                    "proveedor",
                    "entregado",
                    "fecha_entrega_coord",
                    "match_estado",
                    "archivo_origen",
                )
                if c in df.columns
            ]
            st.dataframe(df[show], width="stretch", hide_index=True, height=220)


def pagina_configuracion() -> None:
    _render_page_header(
        "Configuración",
        "Carga de archivos, tarifarios y parámetros del sistema.",
        "Configuración",
    )

    if not check_health_cached():
        st.warning("Conectá el servidor con **Iniciar_Fletes.bat** antes de importar.")
        st.stop()

    tab_tango, tab_cp, tab_pv, tab_liq, tab_tar, tab_flet, tab_cross, tab_sys, tab_seg = st.tabs(
        [
            "Tango (principal)",
            "Prefactura Clicpaq",
            "Postventa",
            "Liquidación",
            "Tarifarios",
            "Fleteros locales",
            "Cross seguimiento",
            "Sistema",
            "Seguridad y acceso",
        ]
    )

    with tab_tango:
        st.subheader("Exportacion.xlsx — SommierCenter")
        st.markdown(
            """
            **Cómo exportar en Tango (estándar unificado)**

            1. Elegí el **mes a controlar** en Maestro/Fletes (ej. mayo).
            2. En Tango, filtrá y exportá siempre por **fecha de entrega**
               (ej. 01/05 → 31/05) — **Distribuidora (CD) y Limansky (SA)** igual.
            3. El Excel trae **pedido y entrega** en columnas; la app usa entrega para el mes
               de control (pedidos que se entregan en otro mes quedan en el mes correcto).
            4. **Cada archivo nuevo se suma** a la base (las filas ya importadas no se pisan).
            5. Remito oficial: **RAR / R** (`NRO REMITO LEGAL LIMANSKY`); la **X** es tránsito.

            Importá **abril, mayo, junio…** por separado si hace falta. Si un mes se bajó
            antes solo por fecha de pedido, conviene **volver a importar** ese mes por entrega.
            """
        )
        tango = st.file_uploader("Archivo Tango", type=["xlsx"], key="cfg_tango")
        import_rapido = st.checkbox(
            "Importación rápida (varios archivos grandes)",
            value=True,
            help=(
                "Solo carga filas en la base. Al terminar de subir distri, LMK, Salta, etc., "
                "ejecutá «Reaplicar reglas» una vez. Evita timeout y recálculos repetidos."
            ),
            key="cfg_tango_rapido",
        )
        if tango is not None:
            mb = len(tango.getvalue()) / (1024 * 1024)
            if mb > 8:
                st.caption(
                    f"Archivo ~{mb:.1f} MB — activá importación rápida si tarda o da error."
                )
        if st.button("Importar Tango", type="primary", disabled=tango is None):
            try:
                if tango is None:
                    raise RuntimeError("Seleccioná un archivo Tango.")
                data = tango.getvalue()
                mb = len(data) / (1024 * 1024)
                timeout = max(600.0, 120.0 + mb * 45.0)
                with st.spinner(
                    f"Importando {tango.name} (~{mb:.1f} MB)… "
                    f"{'solo filas' if import_rapido else 'filas + tarifas'}"
                ):
                    r = post_file(
                        "/import/tango",
                        tango.name,
                        data,
                        timeout=timeout,
                        defer_recalc=import_rapido,
                    )
                msg = r["message"]
                if r.get("rows_rejected"):
                    st.warning(msg)
                else:
                    st.success(msg)
                st.caption(
                    f"Archivo: {r['rows_in_file']} filas · "
                    f"{r['rows_inserted']} nuevas · {r['rows_skipped']} omitidas"
                )
                if import_rapido and r.get("rows_inserted"):
                    st.info(
                        "Cuando subas todos los seguimientos del mes, andá a "
                        "**Envíos interior → Reaplicar reglas** (o el botón en esta pantalla)."
                    )
                get_maestro_filas_cached.clear()
                get_fletes_pagina_cached.clear()
                get_fletes_stats_cached.clear()
                _clear_adrian_cache()
                get_dashboard_stats_cached.clear()
                get_dashboard_gerencial_cached.clear()
                get_kpi_entregas_cached.clear()
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

        st.markdown("---")
        st.subheader("Después de importar varios Excel")
        st.caption(
            "Un solo recálculo de reglas, proveedores y tarifas para toda la base "
            "(usalo tras importación rápida)."
        )
        if st.button("Reaplicar reglas en toda la base", type="secondary", key="cfg_reaplicar_todo"):
            try:
                with st.spinner("Recalculando reglas, proveedores y cobros… puede tardar varios minutos."):
                    with httpx.Client(base_url=API_URL, timeout=900.0) as c:
                        resp = c.post("/envios/reaplicar-reglas")
                        resp.raise_for_status()
                        st.success(resp.json())
                get_maestro_filas_cached.clear()
                get_fletes_pagina_cached.clear()
                get_fletes_stats_cached.clear()
                _clear_adrian_cache()
                get_dashboard_stats_cached.clear()
                get_dashboard_gerencial_cached.clear()
                get_kpi_entregas_cached.clear()
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

        st.markdown("---")
        st.subheader("Corregir import erróneo")
        st.caption(
            "Si el Excel se cargó pero los envíos quedaron vacíos (sin remito/destino), "
            "revertí el lote y volvé a importar con el servidor actualizado."
        )
        batch_id = st.number_input("ID del lote a revertir", min_value=1, value=2, step=1)
        if st.button("Revertir lote", type="secondary"):
            try:
                with api_client() as c:
                    resp = c.delete(f"/import/batch/{int(batch_id)}")
                    resp.raise_for_status()
                    st.success(f"Lote revertido: {resp.json()}")
            except Exception as exc:
                st.error(str(exc))

    with tab_cp:
        st.subheader("Prefactura diaria del proveedor Clicpaq")
        plantilla_download("plantilla_clickpack.xlsx", "Descargar plantilla prefactura")
        with st.expander("Material de capacitación interna", expanded=False):
            plantilla_download(
                "prefactura_clickpack_prueba.xlsx",
                "Ejemplo prefactura (3 remitos)",
            )
            st.caption(
                "Solo para pruebas de cruce en entorno de desarrollo. "
                "Requiere Tango importado con tarifario aplicado en esos remitos."
            )
        cp = st.file_uploader("Excel prefactura", type=["xlsx"], key="cfg_cp")
        if st.button("Importar prefactura", disabled=cp is None):
            try:
                if cp is None:
                    raise RuntimeError("Seleccioná un archivo de prefactura.")
                r = post_file("/mundo1/import/clickpack", cp.name, cp.getvalue())
                st.success(r["message"])
                with api_client() as c:
                    m = c.post("/mundo1/macheo/ejecutar")
                    m.raise_for_status()
                    st.info(f"Cruce automático: {m.json()}")
            except Exception as exc:
                st.error(str(exc))
        if st.button("Solo ejecutar cruce (sin importar)"):
            try:
                with api_client() as c:
                    m = c.post("/mundo1/macheo/ejecutar")
                    m.raise_for_status()
                    st.success(m.json())
            except Exception as exc:
                st.error(str(exc))

    with tab_pv:
        st.subheader("Grillas postventa")
        st.info(
            "El **detalle postventa** viene del seguimiento Tango (**TipoGestion** / **SubTipo**). "
            "La app lo muestra en cada caso; las **reglas logísticas** (+25%, $0, pagar viaje) "
            "se aplican al importar o con **Aplicar reglas postventa**. "
            "En la planilla manual de referencia también aparecen en la columna **obs**."
        )
        plantilla_download("plantilla_postventa.xlsx", "Plantilla postventa")
        pv = st.file_uploader("Excel postventa", type=["xlsx"], key="cfg_pv")
        c1, c2 = st.columns(2)
        if c1.button("Importar postventa", disabled=pv is None):
            try:
                if pv is None:
                    raise RuntimeError("Seleccioná un archivo de postventa.")
                r = post_file("/mundo1/import/postventa", pv.name, pv.getvalue())
                st.success(r["message"])
            except Exception as exc:
                st.error(str(exc))
        if c2.button("Aplicar reglas postventa"):
            with api_client() as c:
                r = c.post("/mundo1/postventa/aplicar")
                r.raise_for_status()
                st.success(r.json())

    with tab_liq:
        st.subheader("Liquidación quincenal")
        plantilla_download("plantilla_liquidacion.xlsx", "Plantilla liquidación")
        periodo = st.text_input("Período", value="2026-06-01_15", key="cfg_periodo")
        liq = st.file_uploader("Excel liquidación", type=["xlsx"], key="cfg_liq")
        c1, c2 = st.columns(2)
        if c1.button("Importar liquidación", disabled=liq is None):
            try:
                if liq is None:
                    raise RuntimeError("Seleccioná un archivo de liquidación.")
                r = post_file(
                    "/mundo1/import/liquidacion", liq.name, liq.getvalue(), periodo=periodo
                )
                st.success(r["message"])
            except Exception as exc:
                st.error(str(exc))
        if c2.button("Conciliar liquidación"):
            with api_client() as c:
                r = c.post("/mundo1/liquidacion/conciliar")
                r.raise_for_status()
                st.success(r.json())

    with tab_tar:
        st.subheader("Tarifario CEDOL / versiones por proveedor")
        st.info(
            "Flujo: copiá el Excel en **`data/tarifarios/`** → **Escanear carpeta** → revisá "
            "borradores → **Activar** por proveedor → **Recalcular**. "
            "Si un proveedor no tenía versión activa, la primera se activa sola. "
            "Si los precios son iguales a la versión activa, **no se crea borrador**."
        )
        st.markdown(
            f"Carpeta: **`{DATA_DIR / 'tarifarios'}`** — cadencia en `tarifarios_cadencia.json`."
        )
        plantilla_download("plantilla_tarifario.xlsx", "Plantilla tarifario")

        try:
            estado = get_json("/tarifas/estado")
            for prov in estado.get("proveedores", []):
                label = prov.get("label", prov.get("proveedor"))
                activa = prov.get("activa")
                borradores = prov.get("borradores") or []
                cad = prov.get("cadencia") or {}
                freq = cad.get("frecuencia", "—")
                with st.expander(f"{label} — {freq}", expanded=bool(borradores)):
                    if activa:
                        st.caption(
                            f"**Activa** v{activa['id']} · {activa.get('filas_count', 0)} filas · "
                            f"desde {activa.get('vigencia_desde') or '—'} · "
                            f"{activa.get('archivo_origen') or 'legacy'}"
                        )
                    else:
                        st.warning("Sin versión activa")
                    if borradores:
                        st.markdown("**Borradores pendientes**")
                        for b in borradores:
                            c1, c2, c3, c4, c5 = st.columns([3, 1, 2, 1, 1])
                            c1.write(
                                f"v{b['id']} · {b.get('filas_count', 0)} filas · "
                                f"{b.get('archivo_origen', '')}"
                            )
                            vid = b["id"]
                            if c2.button("Preview", key=f"diff_{vid}"):
                                st.session_state["tar_diff_id"] = vid
                            vig = c3.date_input(
                                "Vigente desde",
                                value=None,
                                key=f"vig_act_{vid}",
                                help="Corte en el mes (ej. 16/05). Vacío = fecha del Excel.",
                            )
                            if c4.button("Activar", key=f"act_{vid}", type="primary"):
                                try:
                                    act_params: dict[str, Any] = {"recalcular": True}
                                    if vig:
                                        act_params["vigencia_desde"] = vig.isoformat()
                                    with api_client() as c:
                                        r = c.post(
                                            f"/tarifas/versiones/{vid}/activar",
                                            params=act_params,
                                        )
                                        r.raise_for_status()
                                    data = r.json()
                                    if data.get("omitido"):
                                        st.info(data.get("message", "Sin cambios"))
                                    else:
                                        st.success(data.get("message", "Activada"))
                                    st.rerun()
                                except Exception as exc:
                                    st.error(str(exc))
                            if c5.button("Descartar", key=f"desc_{vid}"):
                                try:
                                    with api_client() as c:
                                        r = c.post(f"/tarifas/versiones/{vid}/descartar")
                                        r.raise_for_status()
                                    st.rerun()
                                except Exception as exc:
                                    st.error(str(exc))
                    if activa and prov.get("versiones_historicas", 0) > 0:
                        if st.button(f"Rollback {label}", key=f"rb_{prov['proveedor']}"):
                            try:
                                with api_client() as c:
                                    r = c.post(
                                        f"/tarifas/versiones/rollback/{prov['proveedor']}"
                                    )
                                    r.raise_for_status()
                                st.success(r.json().get("message", "Rollback OK"))
                                st.rerun()
                            except Exception as exc:
                                st.error(str(exc))

            diff_id = st.session_state.get("tar_diff_id")
            if diff_id:
                try:
                    diff = get_json(f"/tarifas/versiones/{diff_id}/diff")
                    st.markdown(f"**Diff versión {diff_id}** ({diff.get('proveedor', '')})")
                    st.write(
                        f"Agregadas: {diff.get('agregadas', 0)} · "
                        f"Modificadas: {diff.get('modificadas', 0)} · "
                        f"Eliminadas: {diff.get('eliminadas', 0)}"
                    )
                    muestra = diff.get("muestra_cambios") or []
                    if muestra:
                        st.dataframe(pd.DataFrame(muestra), width="stretch", height=200)
                except Exception as exc:
                    st.error(str(exc))
        except Exception as exc:
            st.caption(f"Estado tarifarios: {exc}")

        st.markdown("---")
        if st.button("Escanear carpeta data/tarifarios", type="primary"):
            try:
                with api_client() as c:
                    r = c.post("/tarifas/escanear-carpeta")
                    r.raise_for_status()
                res = r.json()
                if res.get("borradores"):
                    st.success(res.get("message", "OK"))
                    st.dataframe(pd.DataFrame(res["borradores"]), width="stretch")
                elif res.get("omitidos"):
                    st.info(res.get("message", "Sin cambios"))
                else:
                    st.success(res.get("message", "OK"))
                if res.get("omitidos"):
                    st.caption("Proveedores omitidos (mismos precios que la versión activa):")
                    st.dataframe(pd.DataFrame(res["omitidos"]), width="stretch")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

        st.markdown("---")
        st.caption("O subí un archivo puntual (crea borrador por hoja/proveedor):")
        up = st.file_uploader("Excel tarifario", type=["xlsx"], key="cfg_tar")
        if st.button("Importar como borrador", disabled=up is None):
            try:
                if up is None:
                    raise RuntimeError("Seleccioná un archivo de tarifario.")
                r = post_file("/tarifas/import", up.name, up.getvalue())
                st.success(r.get("message", "OK"))
                if r.get("borradores"):
                    st.dataframe(pd.DataFrame(r["borradores"]), width="stretch")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
        try:
            tarifas = get_json("/tarifas")
            st.caption(f"Tarifas en versiones activas: {len(tarifas)}")
            st.dataframe(pd.DataFrame(tarifas), width="stretch", height=220)
            if st.button("Recalcular costos con tarifario"):
                with api_client() as c:
                    r = c.post("/tarifas/recalcular-envios")
                    r.raise_for_status()
                st.success(r.json())
        except Exception as exc:
            st.error(str(exc))

    with tab_flet:
        _config_fleteros_locales()

    with tab_cross:
        _config_cross_seguimiento()

    with tab_sys:
        st.subheader("Sistema")
        st.text_input("URL del API", value=API_URL, disabled=True)
        st.markdown(
            """
            - **Seguro fijo:** $30 por envío (tarifario)
            - **Gestión retiro postventa:** +25%
            - **Depósitos** (editar en `backend/app/config.py`):
              - `14` → CD Tortuguitas (centro de distribución principal)
              - `12` → CD Hurlingham (Clicpaq; Limansky también despacha desde ahí)
            """
        )

        st.markdown("---")
        st.subheader("Sucursales (catálogo)")
        st.caption(
            "Códigos del tablero Tango (AV, BE, CA…). Fuente: `data/sucursales.json`. "
            "Sirve para Fletes (km, zona) y vínculo con el tablero Tango."
        )
        try:
            suc = get_json("/sucursales")
            st.metric("Sucursales cargadas", suc.get("total", 0))
            con_coords = sum(
                1 for s in suc.get("items", []) if s.get("tiene_coordenadas")
            )
            st.caption(f"Con coordenadas GPS: **{con_coords}**")
            if st.button("Resincronizar desde JSON", key="cfg_suc_sync"):
                with api_client() as c:
                    r = c.post("/sucursales/sincronizar")
                    r.raise_for_status()
                    st.success(r.json())
                st.rerun()
            df_suc = pd.DataFrame(suc.get("items", []))
            if not df_suc.empty:
                cols = [
                    c
                    for c in (
                        "codigo",
                        "nombre",
                        "zona",
                        "direccion",
                        "localidad",
                        "tiene_coordenadas",
                    )
                    if c in df_suc.columns
                ]
                st.dataframe(df_suc[cols], width="stretch", height=320, hide_index=True)
        except Exception as exc:
            st.warning(f"No se pudo cargar sucursales: {exc}")

        st.markdown("---")
        st.subheader("Transporte Tango → proveedor")
        st.caption("Reglas acordadas con Mantello (código + destino).")
        try:
            reglas = get_json("/sistema/transporte-reglas")
            st.dataframe(
                pd.DataFrame(reglas.get("reglas", [])),
                width="stretch",
                hide_index=True,
            )
        except Exception:
            st.caption("No se pudo cargar la tabla de reglas.")

        st.markdown("---")
        st.subheader("Cierre mensual")
        st.caption(
            "Borra **todos** los envíos Tango importados (no filtra por mes), prefacturas CLP, "
            "postventa, liquidación, cache de km y solicitudes de fleteros. "
            "**Conserva** tarifarios, transportes, sucursales y catálogo de fleteros "
            "(salvo que marques vaciar tarifarios)."
        )

        try:
            conteo = get_json("/sistema/conteo")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Envíos (renglones Tango)", conteo["envios"])
            c2.metric("Prefacturas CLP", conteo["prefacturas_clickpack"])
            c3.metric("Cache km", conteo.get("flete_distancias", 0))
            c4.metric("Tarifas", conteo["tarifas"])
            c5, c6, c7 = st.columns(3)
            c5.metric("Lotes importación", conteo["importaciones"])
            c6.metric("Solicitudes fletero", conteo.get("flete_solicitudes", 0))
            c7.metric("Postventa / Liq.", (conteo.get("postventa") or 0) + (conteo.get("liquidacion") or 0))
        except Exception:
            conteo = None

        borrar_tarifas = st.checkbox("También vaciar tarifarios cargados", value=False)
        confirmar = st.checkbox("Confirmo que quiero vaciar todos los datos operativos", value=False)
        texto = st.text_input('Escribí CIERRE para habilitar el botón', max_chars=10)

        if st.button(
            "Vaciar base — cierre mensual",
            type="primary",
            disabled=not (confirmar and texto.strip().upper() == "CIERRE"),
        ):
            try:
                with api_client() as c:
                    r = c.post(
                        "/sistema/cierre-mensual",
                        params={"incluir_tarifarios": borrar_tarifas},
                    )
                    r.raise_for_status()
                res = r.json()
                st.success(res.get("mensaje", "Listo"))
                st.json(res.get("eliminados", {}))
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    with tab_seg:
        _config_seguridad()


# --- Main ---

st.set_page_config(
    page_title="Control de Fletes",
    page_icon="🚚",
    layout="wide",
    initial_sidebar_state="expanded",
)

if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = False

if not _restore_auth_session():
    inject_theme(dark=False)
    _pagina_login()
    st.stop()

st.sidebar.markdown(
    '<div class="sidebar-brand-band">'
    '<p class="sidebar-brand-title">Control de Fletes</p>'
    '<p class="sidebar-brand-caption">SommierCenter · Wamaro · TOP</p>'
    "</div>",
    unsafe_allow_html=True,
)

_logged_user = st.session_state.get(AUTH_USER_KEY) or ""
if _logged_user:
    st.sidebar.caption(f"Usuario: **{_logged_user}**")
    if _is_super_admin():
        st.sidebar.caption("Super administrador")
    if st.sidebar.button("Cerrar sesión", use_container_width=True, key="btn_logout"):
        _auth_logout()
        st.rerun()

st.sidebar.toggle(
    "Modo oscuro",
    key="dark_mode",
    help="Aplica tema oscuro en toda la aplicación",
)
inject_theme(dark=bool(st.session_state.dark_mode))
inject_top_watermark()

pagina = _sidebar_nav_tree()
inject_module_accent(pagina)

# Limpiar enlaces viejos (?_gcaso=) que abrían pestaña duplicada
if st.query_params.get("_gcaso") or st.query_params.get("_gsk"):
    try:
        del st.query_params["_gcaso"]
        del st.query_params["_gsk"]
    except Exception:
        pass

st.sidebar.markdown("---")
if check_health_cached():
    build = api_build_cached()
    if build == API_BUILD_ESPERADO:
        st.sidebar.markdown(
            '<p class="nav-status-ok">Servidor conectado</p>',
            unsafe_allow_html=True,
        )
    else:
        st.sidebar.markdown(
            f'<p class="nav-status-warn">API desactualizada · build {build or "?"}</p>',
            unsafe_allow_html=True,
        )
else:
    st.sidebar.markdown(
        '<p class="nav-status-err">Servidor no disponible · Iniciar_Fletes.bat</p>',
        unsafe_allow_html=True,
    )

if pagina == "Dashboard":
    pagina_dashboard()
elif pagina == "MAESTRO":
    pagina_casos(titulo="MAESTRO", key_prefix="maestro", carga_por_quincena=True)
elif pagina == "Resumen":
    pagina_modo_adrian()
elif pagina == "CLICPAQ":
    _page_clicpaq()
elif pagina == "FRANSOF":
    _page_fransof()
elif pagina == "ALFARO":
    _page_alfaro()
elif pagina == "LBO":
    _page_lbo()
elif pagina == "Proveedor a elegir":
    pagina_proveedor_elegir()
elif pagina == "Fletes":
    pagina_fletes()
else:
    pagina_configuracion()
