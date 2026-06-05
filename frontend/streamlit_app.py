"""Control de Fletes — interfaz Streamlit."""

from __future__ import annotations

import html as html_lib
import json
import os
import sys
from pathlib import Path
from typing import Any, cast

import httpx  # pyright: ignore[reportMissingImports]
import pandas as pd
import streamlit as st

API_URL = os.getenv("FLETES_API_URL", "http://127.0.0.1:8000/api/v1")
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
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
    from app.labels import COLOR_LEYENDA
    from app.ui_labels import (
        etiqueta_columna,
        etiqueta_menu,
        etiqueta_pagina,
        etiqueta_proveedor,
        fmt_celda_maestro,
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
    COLOR_LEYENDA = {
        "amarillo": "Pendiente — tarifa o prefactura",
        "verde": "OK — prefactura conciliada",
        "rojo": "Diferencia / no paga",
        "gris": "Amba excluido",
        "naranja": "Revisar carga / postventa",
        "celeste": "Abona Wamaro — sin prefactura",
    }

API_BUILD_ESPERADO = "fletes-maestro-manual-align-2026-06-05"


def _as_dataframe(data: object) -> pd.DataFrame:
    """Asegura DataFrame para el type checker (filtros pandas devuelven uniones amplias)."""
    if isinstance(data, pd.DataFrame):
        return data
    return pd.DataFrame(data)

# Fondos pastel + texto oscuro (legible en tema claro)
COLOR_MAP = {
    "amarillo": ("#FFF8DC", "#5C4A00"),
    "rojo": ("#FFE4E4", "#8B2525"),
    "gris": ("#ECEFF3", "#4A5568"),
    "celeste": ("#E3F0FF", "#1E4A7A"),
    "verde": ("#E6F6EA", "#1F5C35"),
    "naranja": ("#FFECD9", "#7A4510"),
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
    "REMITOS",
    "ESTADO REMITO",
    "NRO TRANSP",
    "DESTINATARIO",
    "LOCALIDAD",
    "PROVINCIA",
    "TRANSPORTE",
    "PROVEEDOR",
    "BULTOS",
    "LOGISTICA",
    "SEGURO",
    "PRECIO NETO",
    "total",
]

# Proporciones de columnas en grilla maestro / elegir proveedor (sin dif/obs/suc)
MAESTRO_COL_RATIOS: dict[str, float] = {
    "FECHA": 0.72,
    "FECHA PEDIDO": 0.72,
    "FECHA ENTREGA": 0.72,
    "ESTADO REMITO": 0.95,
    "NRO TRANSP": 0.42,
    "REMITOS": 1.0,
    "DESTINATARIO": 1.65,
    "LOCALIDAD": 1.05,
    "PROVINCIA": 0.78,
    "TRANSPORTE": 1.0,
    "PROVEEDOR": 1.2,
    "BULTOS": 0.48,
    "LOGISTICA": 0.9,
    "SEGURO": 0.72,
    "PRECIO NETO": 0.9,
    "total": 0.9,
    "SUCURSAL": 0.5,
    "KM": 0.55,
    "ZONA KM": 0.8,
    "TARIFA REF": 1.15,
}


def fmt_fecha_sin_hora(value: Any) -> str:
    """Solo fecha (sin 00:00:00) para grillas y detalle."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if isinstance(value, pd.Timestamp):
        return value.strftime("%d/%m/%Y")
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
        elif col in ("PROVEEDOR", "DESTINATARIO", "LOCALIDAD", "PROVINCIA", "TRANSPORTE"):
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
    tango = ren.get("tango_completo") or {}
    if tango:
        return df_campos_tango(tango)
    omitir = {"id", "tango_completo", "regla_color"}
    filas = [
        {
            "campo": etiqueta_columna(str(k)),
            "valor": valor_celda_display(v, str(k)),
        }
        for k, v in ren.items()
        if k not in omitir and v is not None and str(v).strip() != ""
    ]
    return pd.DataFrame(filas)


def inject_theme() -> None:
    st.markdown(
        """
        <style>
        .stApp {
            background: linear-gradient(165deg, #f7f9fc 0%, #eef2f7 45%, #f4f0f8 100%);
        }
        [data-testid="stSidebar"] {
            background-color: #e8eef6 !important;
            border-right: 1px solid #d5dde8;
        }
        section[data-testid="stSidebar"],
        [data-testid="stSidebar"] > div,
        [data-testid="stSidebar"] [data-testid="stSidebarContent"] {
            scrollbar-width: none !important;
            -ms-overflow-style: none !important;
        }
        section[data-testid="stSidebar"]::-webkit-scrollbar,
        [data-testid="stSidebar"] > div::-webkit-scrollbar,
        [data-testid="stSidebar"] [data-testid="stSidebarContent"]::-webkit-scrollbar {
            display: none !important;
            width: 0 !important;
            height: 0 !important;
        }
        [data-testid="stSidebar"] [data-testid="stSidebarContent"] {
            padding-top: 0.75rem !important;
            padding-bottom: 0.5rem !important;
            overflow-x: hidden !important;
        }
        [data-testid="stSidebar"] h1, [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] .stMarkdown {
            color: #2c3e50 !important;
        }
        [data-testid="stSidebar"] .sidebar-brand {
            font-size: 1.15rem !important;
            font-weight: 700 !important;
            margin: 0 0 0.1rem 0 !important;
            line-height: 1.2 !important;
        }
        [data-testid="stSidebar"] .sidebar-brand-caption {
            font-size: 0.78rem !important;
            margin: 0 0 0.35rem 0 !important;
            color: #5a6b7d !important;
        }
        [data-testid="stSidebar"] div[role="radiogroup"] {
            gap: 0 !important;
        }
        [data-testid="stSidebar"] div[role="radiogroup"] label {
            font-size: 0.95rem !important;
            font-weight: 600 !important;
            padding: 0.12rem 0.1rem !important;
            min-height: 0 !important;
            margin: 0 !important;
        }
        [data-testid="stSidebar"] div[role="radiogroup"] label p,
        [data-testid="stSidebar"] div[role="radiogroup"] label span {
            font-size: 0.95rem !important;
            line-height: 1.2 !important;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] {
            margin: 0.15rem 0 0.1rem 0 !important;
            border: none !important;
            background: transparent !important;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] summary {
            font-size: 0.88rem !important;
            font-weight: 700 !important;
            color: #3d5a80 !important;
            padding: 0.15rem 0 !important;
            min-height: 0 !important;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] {
            padding: 0 0 0 0.65rem !important;
            border-left: 2px solid #b8c9de;
            margin-left: 0.25rem !important;
        }
        [data-testid="stSidebar"] hr {
            margin: 0.35rem 0 !important;
        }
        [data-testid="stSidebar"] .nav-status-ok,
        [data-testid="stSidebar"] .nav-status-warn,
        [data-testid="stSidebar"] .nav-status-err {
            font-size: 0.82rem !important;
            padding: 0.35rem 0.5rem !important;
            border-radius: 6px !important;
            margin: 0.25rem 0 0 !important;
        }
        [data-testid="stSidebar"] .nav-status-ok {
            background: #d4edda !important;
            color: #1f5c35 !important;
        }
        [data-testid="stSidebar"] .nav-status-warn {
            background: #fff3cd !important;
            color: #7a5c00 !important;
        }
        [data-testid="stSidebar"] .nav-status-err {
            background: #f8d7da !important;
            color: #8b2525 !important;
        }
        h1, h2, h3 { color: #2c3e50 !important; }
        .block-container { padding-top: 1.5rem; }
        div[data-testid="stMetric"] {
            background: #ffffffee;
            border: 1px solid #dde5f0;
            border-radius: 16px;
            padding: 0.65rem 0.85rem 0.65rem 1rem;
            box-shadow: 0 2px 8px #0000000a;
            overflow: hidden;
        }
        div[data-testid="stMetric"] label {
            font-size: 0.78rem !important;
        }
        div[data-testid="stMetric"] [data-testid="stMetricValue"] {
            font-size: 1.35rem !important;
        }
        .leyenda-wrap {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            align-items: center;
            margin: 0.35rem 0 0.75rem 0;
            padding: 0;
            width: 100%;
        }
        .leyenda-chip {
            display: inline-flex;
            align-items: center;
            flex: 0 0 auto;
            margin: 0;
            padding: 5px 12px;
            border-radius: 999px;
            font-size: 0.8rem;
            line-height: 1.25;
            white-space: nowrap;
            border: 1px solid #00000012;
            box-shadow: 0 1px 2px #0000000a;
        }
        .dash-card {
            position: relative;
            border-radius: 16px;
            border: 1px solid #dde5f0;
            padding: 1rem 1rem 1rem 1.15rem;
            margin-bottom: 0.35rem;
            box-shadow: 0 2px 10px #0000000d;
            min-height: 4.5rem;
        }
        .dash-card-accent {
            position: absolute;
            left: 0;
            top: 0;
            bottom: 0;
            width: 6px;
            border-radius: 16px 0 0 16px;
        }
        .dash-card-body {
            color: #2c3e50;
            font-size: 0.92rem;
            line-height: 1.45;
        }
        .dash-card-body strong {
            font-size: 0.98rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def api_client() -> httpx.Client:
    return httpx.Client(base_url=API_URL, timeout=120.0)


def check_health() -> bool:
    base = API_URL.removesuffix("/api/v1").rstrip("/")
    try:
        with httpx.Client(timeout=5.0) as c:
            c.get(f"{base}/health").raise_for_status()
            return True
    except Exception:
        return False


def api_build_actual() -> str | None:
    base = API_URL.removesuffix("/api/v1").rstrip("/")
    try:
        with httpx.Client(timeout=5.0) as c:
            r = c.get(f"{base}/health")
            r.raise_for_status()
            return r.json().get("build")
    except Exception:
        return None


def api_es_actual() -> bool:
    return api_build_actual() == API_BUILD_ESPERADO


def filtrar_df_zona_proveedor(df: pd.DataFrame, proveedor: str | None) -> pd.DataFrame:
    """Filtro por destino (respaldo si la API en ejecución es vieja)."""
    if not proveedor or df.empty or "PROVINCIA" not in df.columns:
        return df
    vista_fn = caso_en_vista_proveedor
    if vista_fn is None:
        return df

    def _ok(row: pd.Series) -> bool:
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


def _ui_filtros_fecha_remito(key_prefix: str) -> dict[str, Any]:
    """Filtros API: mes a controlar, campo fecha, estado remito."""
    opciones = _opciones_mes_control()
    labels = [o[2] for o in opciones]
    c1, c2, c3 = st.columns([2, 1.4, 1.6])
    idx = c1.selectbox(
        "Mes a controlar",
        range(len(labels)),
        format_func=lambda i: labels[i],
        key=f"{key_prefix}_mes_idx",
    )
    anio, mes, label_mes = opciones[idx]
    campo_ui = c2.selectbox(
        "Filtrar casos por",
        (
            "Pedido o entrega (cualquiera)",
            "Solo fecha de pedido",
            "Solo fecha de entrega",
        ),
        key=f"{key_prefix}_campo_fecha",
    )
    campo_map = {
        "Pedido o entrega (cualquiera)": "cualquiera",
        "Solo fecha de pedido": "pedido",
        "Solo fecha de entrega": "entrega",
    }
    campo_api = campo_map[campo_ui]
    if campo_api == "entrega":
        c1.caption(f"Casos con **entrega** en **{label_mes}** (1 al último día del mes).")
    elif campo_api == "pedido":
        c1.caption(f"Casos con **pedido** en **{label_mes}** (1 al último día del mes).")
    else:
        c1.caption(
            f"Casos con **pedido o entrega** en **{label_mes}** (1 al último día del mes)."
        )
    remito_ui = c3.selectbox(
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
    params: dict[str, Any] = {
        "campo_fecha": campo_api,
        "remito_estado": remito_map[remito_ui],
        "mes_control_anio": anio,
        "mes_control_mes": mes,
    }
    return params


def _params_sin_mes_si_busca(params: dict[str, Any], buscar: str) -> dict[str, Any]:
    """Con texto de búsqueda, recorrer toda la base importada (sin mes a controlar)."""
    p = dict(params)
    if buscar.strip():
        p.pop("mes_control_anio", None)
        p.pop("mes_control_mes", None)
        p.pop("campo_fecha", None)
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


def get_maestro_filas(**params: Any) -> tuple[list[dict], bool]:
    """GET /maestro; devuelve filas y si la API aplicó filtro de zona."""
    with api_client() as client:
        q = dict(params)
        if q.get("proveedor"):
            q["vista_proveedor"] = q["proveedor"]
        r = client.get("/maestro", params=q, timeout=300.0)
        r.raise_for_status()
        filas = r.json()
        vista = (params.get("proveedor") or "").strip().upper()
        if not vista:
            return filas, True
        hdr = (r.headers.get("X-Maestro-Filtro-Zona") or "").upper()
        return filas, hdr == vista


@st.cache_data(ttl=120, show_spinner=False)
def get_maestro_filas_cached(params_key: str) -> tuple[list[dict], bool]:
    """Cache corto por combinación de filtros (evita re-fetch en reruns)."""
    return get_maestro_filas(**json.loads(params_key))


@st.cache_data(ttl=120, show_spinner=False)
def get_fletes_casos_cached(params_key: str) -> list[dict]:
    return get_json("/fletes/casos", **json.loads(params_key))


def get_json(path: str, **params: Any) -> Any:
    with api_client() as client:
        r = client.get(path, params=params)
        r.raise_for_status()
        return r.json()


def post_file(path: str, file_name: str, content: bytes, **params: str) -> Any:
    with api_client() as client:
        files = {"file": (file_name, content)}
        r = client.post(path, files=files, params=params or None)
        r.raise_for_status()
        return r.json()


def style_maestro(df: pd.DataFrame) -> Any:
    if df.empty:
        return df

    def row_style(row: pd.Series) -> list[str]:
        key = row.get("_regla_color") if "_regla_color" in row.index else None
        pair = COLOR_MAP.get(key) if key else None
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

    destino = (info.get("destino") or "—").strip()
    km = info.get("distance_km")
    zona = (info.get("zona_etiqueta") or info.get("zona_km") or "").strip()

    if km is not None:
        km_f = float(km)
        km_txt = f"~{km_f:,.1f} km".replace(",", ".") if info.get("es_estimado") else f"{km_f:,.1f} km".replace(",", ".")
        tipo_km = "estimado" if info.get("es_estimado") else "por ruta"
        linea = f"{origen}: {suc_txt} → **{destino}** · **{km_txt}** ({tipo_km})"
        if zona:
            linea += f" · Zona **{zona}**"
        st.markdown(linea)
        if info.get("es_estimado") or info.get("pendiente_calculo"):
            st.caption(
                "Para la distancia real al domicilio, usá **Fletes → Calcular km** "
                "(geocodifica la dirección y mide la ruta desde la sucursal)."
            )
    elif cod != "—":
        st.info(
            f"{origen}: **{cod}**"
            + (f" ({nombre})" if nombre else "")
            + f" → **{destino}**. "
            "Todavía no hay km calculado — andá a **Fletes → Calcular km**."
        )
    else:
        st.caption("Sin sucursal asignada todavía para este envío local.")


DETALLE_POPUP = "_detalle_popup"


def _render_contenido_detalle_caso(caso_id: str, titulo: str) -> None:
    """Cuerpo del detalle (panel inline, sin dialog)."""
    st.markdown(f"**{titulo}**")
    st.caption(
        "Un caso = un remito (puede tener varios artículos: colchón, base, postventa desde Tango)."
    )
    try:
        det = get_json(f"/maestro/caso/{caso_id}")
    except Exception as exc:
        st.error(f"No se pudo cargar el detalle: {exc}")
        return

    m = det.get("maestro", {})
    st.markdown("#### Proveedor de tarifa")
    prov = m.get("PROVEEDOR") or m.get("_proveedor_tarifa")
    if prov:
        st.write(f"**Asignado:** {etiqueta_proveedor(str(prov))}")
    cobro_prov = float(m.get("COBRO PROVINCIA") or 0)
    cobro_red = float(m.get("COBRO RED") or 0)
    if cobro_red or cobro_prov:
        if cobro_prov > 0:
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
                for cr in det["cobro_renglones"]:
                    st.write(
                        f"- `{cr.get('tipo_linea')}` — {cr.get('descripcion') or '—'} "
                        f"(cant. {cr.get('cantidad')})"
                    )
            for pc in det.get("cobro_pedidos") or []:
                for adv in pc.get("advertencias") or []:
                    st.caption(adv)
        except json.JSONDecodeError:
            pass

    _render_distancia_sucursal(det.get("distancia_sucursal"))

    st.markdown("#### Resumen maestro")
    m_cols = [k for k in m.keys() if not k.startswith("_")]
    m_df = preparar_maestro_df(pd.DataFrame([{k: m.get(k) for k in m_cols}]))
    st.dataframe(style_maestro(m_df), width="stretch", hide_index=True)

    st.markdown("#### Renglones Tango (artículos / postventa)")
    renglones = det.get("renglones", [])
    if renglones:
        for i, ren in enumerate(renglones, 1):
            titulo_ren = ren.get("descripcion") or ren.get("cod_articulo") or f"Renglón {i}"
            with st.expander(f"{i}. {titulo_ren}", expanded=(len(renglones) == 1)):
                df_ren = df_detalle_renglon(ren)
                if df_ren.empty:
                    st.caption("Sin datos adicionales para este renglón.")
                else:
                    st.dataframe(
                        df_ren,
                        width="stretch",
                        height=min(400, 35 * len(df_ren)),
                        hide_index=True,
                    )
    else:
        st.warning("Sin renglones para este caso.")


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
    """Limpia estado del popup de detalle."""
    st.session_state.pop(DETALLE_POPUP, None)
    st.session_state.pop("popup_caso_id", None)
    st.session_state.pop("mostrar_popup_caso", None)
    st.session_state.pop("detalle_dialog_abierto", None)
    st.session_state.pop(f"{sel_key}_detalle_caso_id", None)
    st.session_state.pop(f"{sel_key}_detalle_titulo", None)
    st.session_state.pop(f"{sel_key}_abrir_caso", None)
    if sel_key in st.session_state:
        st.session_state[sel_key] = {"selection": {"rows": []}}


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
    }


def _hex_to_rgba(hex_color: str, alpha: float = 0.14) -> str:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return f"rgba(255,255,255,{alpha})"
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{alpha})"


def _css_grilla_detalle() -> None:
    """Grilla tipo tabla: filas uniformes."""
    st.markdown(
        """
        <style>
        .grilla-celda-dato {
            padding: 0 7px;
            height: 1.85rem;
            line-height: 1.85rem;
            font-size: 0.78rem;
            overflow: hidden;
            white-space: nowrap;
            text-overflow: ellipsis;
            border-bottom: 1px solid #c8d4e0;
            box-sizing: border-box;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] {
            font-size: 0.78rem;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stHorizontalBlock"] {
            align-items: stretch !important;
            margin: 0 !important;
            padding: 0 !important;
            min-height: 1.85rem !important;
            max-height: 1.85rem !important;
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
            min-height: 1.85rem !important;
            max-height: 1.85rem !important;
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
            font-size: 0.68rem !important;
            padding: 0 !important;
            min-height: 1.15rem !important;
            height: 1.15rem !important;
            max-height: 1.15rem !important;
            width: 1.15rem !important;
            min-width: 1.15rem !important;
            max-width: 1.15rem !important;
            margin: 0 !important;
            line-height: 1 !important;
            border-radius: 999px !important;
            background: rgba(255,255,255,0.55) !important;
            border: 1px solid rgba(0,0,0,0.06) !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="column"]:first-child button p {
            font-size: 0.68rem !important;
            line-height: 1 !important;
            margin: 0 !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stSelectbox"] {
            margin: 0 !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stSelectbox"] > div {
            min-height: 1.85rem !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stSelectbox"] div[data-baseweb="select"] {
            min-height: 1.65rem !important;
            height: 1.65rem !important;
            font-size: 0.74rem !important;
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
    title = f' title="{html_lib.escape(texto)}"' if len(texto) > 22 else ""
    if not texto:
        return f'<div class="grilla-celda-dato" style="background:{tint};"></div>'
    return (
        f'<div class="grilla-celda-dato" style="background:{tint};color:{fg};'
        f'{control}"{title}>'
        f"{html_lib.escape(texto)}</div>"
    )


_COL_BOTON_DETALLE = 0.14
_GRILLA_PAGE_SIZE = 50


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
    ratios_fila = [_COL_BOTON_DETALLE] + ratios_datos

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
    for col, name in zip(hdr[1:], cols_grilla):
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
                color_key = "rojo"
                bg, fg = COLOR_MAP.get(color_key, ("#FFE4E4", "#8B2525"))
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
            color_key = str(fila.get("_regla_color") or "")
            bg, fg = COLOR_MAP.get(color_key, ("#ffffff", "#2c3e50"))
            tint = _hex_to_rgba(bg, 0.38)
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
            for i, col_name in enumerate(cols_grilla):
                col_widget = cols[i + 1]
                if col_name == "PROVEEDOR" and key_prefix:
                    opciones, mapa = _opciones_select_proveedor(fila)
                    mapa_key = f"{key_prefix}_map_{caso_id}"
                    state_key = f"{key_prefix}_pe_{caso_id}"
                    st.session_state[mapa_key] = mapa
                    if len(opciones) <= 1:
                        col_widget.markdown(
                            f'<div class="grilla-celda-dato" style="background:{tint};color:{fg};">'
                            "Sin tarifa</div>",
                            unsafe_allow_html=True,
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
) -> None:
    """Grilla maestro/fletes: icono lupa por fila (paginada si hay muchos casos)."""
    _procesar_clic_grilla_pendiente(df, sel_key)
    _render_panel_detalle(sel_key)
    _css_grilla_detalle()

    cols_grilla = [
        c
        for c in show_df.columns
        if c not in ("_regla_color", "_caso_id", "_es_marcador_tarifario")
    ]
    total = len(df)
    offset = _controles_paginacion_grilla(total, sel_key)
    df_page = df.iloc[offset : offset + _GRILLA_PAGE_SIZE]
    _render_grilla_filas_click(
        df_page,
        cols_grilla,
        sel_key=sel_key,
        height=height,
        key_prefix=key_prefix,
        row_offset=offset,
    )


def _texto_celda_grilla(fila: dict[str, Any], col_name: str) -> str:
    raw = fila.get(col_name)
    if col_name in ("PROVEEDOR", "DESTINATARIO", "LOCALIDAD", "PROVINCIA", "TRANSPORTE"):
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


def leyenda_colores() -> None:
    chips = []
    for key, label in COLOR_LEYENDA.items():
        bg, fg = COLOR_MAP[key]
        chips.append(
            f'<span class="leyenda-chip" style="background:{bg};color:{fg}">{label}</span>'
        )
    st.markdown(f'<div class="leyenda-wrap">{"".join(chips)}</div>', unsafe_allow_html=True)


def _dash_card(body: str, accent: str, bg: str = "#ffffff") -> str:
    return (
        f'<div class="dash-card" style="background:{bg};">'
        f'<div class="dash-card-accent" style="background:{accent};"></div>'
        f'<div class="dash-card-body">{body}</div></div>'
    )


def _css_dashboard() -> None:
    st.markdown(
        """
        <style>
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


def plantilla_download(nombre: str, etiqueta: str) -> None:
    path = DATA_DIR / nombre
    if path.exists():
        st.download_button(etiqueta, path.read_bytes(), file_name=nombre, width="stretch")


# --- Páginas ---


def pagina_dashboard() -> None:
    st.title("Dashboard")
    _css_dashboard()
    st.markdown(
        "Vista general del control logístico. Los datos se acumulan con cada importación "
        "(no se pisan registros ya cargados)."
    )

    if not check_health():
        st.warning("El servidor no está activo. Ejecutá **Iniciar_Fletes.bat** en la carpeta del proyecto.")
        return

    try:
        general = get_json("/envios/stats")
        interior = get_json("/mundo1/stats")
    except Exception as exc:
        st.error(f"No se pudieron cargar estadísticas: {exc}")
        return

    st.subheader("Resumen general")
    st.markdown('<div class="dash-metrics">', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total envíos en base", general["total_envios"])
    c2.metric("Excluidos Amba / retiro", general["excluidos"])
    c3.metric("Canal red / crossdock", general["alertas_clickpack"])
    c4.metric("Abona Wamaro", general["abona_wamaro"])
    st.markdown("</div>", unsafe_allow_html=True)

    st.subheader("Envíos al interior")
    st.markdown('<div class="dash-metrics">', unsafe_allow_html=True)
    i1, i2, i3, i4, i5 = st.columns(5)
    i1.metric("Renglones interior", interior["envios_interior"])
    i2.metric("Con tarifa calculada", interior.get("con_tarifa", 0))
    i3.metric("Prefacturas cargadas", interior["prefacturas_clickpack"])
    i4.metric("Cruces OK", interior["macheo_matcheados"])
    i5.metric("Con diferencia $", interior["con_diferencia"])

    c1, c2, c3 = st.columns(3)
    c1.metric("Conjuntos colchón+somier", interior["macheo_conjuntos"])
    c2.metric("Sin datos Tango", interior.get("sin_datos_tango", 0))
    c3.metric("Sin prefactura", interior.get("pendientes_sin_prefactura", 0))
    st.markdown("</div>", unsafe_allow_html=True)

    por_color = interior.get("por_color") or {}
    if por_color:
        labels = {**COLOR_LEYENDA, "sin_color": "Sin clasificar"}
        chips = []
        for key, n in sorted(por_color.items(), key=lambda x: -x[1]):
            if n <= 0:
                continue
            bg, fg = COLOR_MAP.get(key, ("#f0f0f0", "#2c3e50"))
            lbl = labels.get(key, key)
            chips.append(
                f'<span class="leyenda-chip" style="background:{bg};color:{fg}">{lbl}: {n}</span>'
            )
        if chips:
            st.markdown(
                "**Clasificación por color:** "
                f'<div class="leyenda-wrap">{"".join(chips)}</div>',
                unsafe_allow_html=True,
            )

    sin_datos = interior.get("sin_datos_tango", 0)
    if sin_datos:
        st.error(
            f"Hay **{sin_datos}** renglones importados **sin remito ni artículo** "
            "(columnas del Excel no reconocidas). Andá a **Configuración → Tango** "
            "y usá **Revertir último lote erróneo**, luego volvé a importar."
        )

    pend = interior.get("pendientes_sin_prefactura", 0)
    if pend and interior["prefacturas_clickpack"] == 0:
        st.info(
            f"Hay **{pend}** envíos sin prefactura del proveedor. "
            "Importá el reporte en **Configuración → Prefactura Clicpaq** y ejecutá **Cruce prefacturas**."
        )
    elif pend:
        st.info(f"Hay **{pend}** envíos aún sin cruce con prefactura.")

    if general.get("ultimo_import"):
        st.caption(f"Última importación Tango: {general['ultimo_import']}")

    st.subheader("Accesos rápidos")
    a1, a2, a3 = st.columns(3)
    cards = [
        (
            "**Envíos interior** — planilla, cruce prefacturas y conciliación.",
            "#E6C200",
            "#FFF8DC",
        ),
        (
            "**Fletes** — control CABA/GBA (en desarrollo).",
            "#5B9BD5",
            "#E3F0FF",
        ),
        (
            "**Configuración** — Excel Tango, tarifarios y plantillas.",
            "#7CB89A",
            "#E6F6EA",
        ),
    ]
    for col, (body, accent, bg) in zip((a1, a2, a3), cards):
        col.markdown(_dash_card(body, accent, bg), unsafe_allow_html=True)


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
) -> None:
    st.title(etiqueta_pagina(titulo))
    st.caption(subtitulo)
    sel_key = f"{key_prefix}_sel"

    if not check_health():
        st.stop()

    if not api_es_actual():
        st.error(
            "La **API** que está corriendo es una versión anterior (no aplica filtros por zona). "
            "Cerrá la ventana minimizada **Fletes-API**, ejecutá de nuevo **Iniciar_Fletes.bat** "
            "o corré `python scripts/kill_api_port.py` y volvé a iniciar."
        )

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
    color_f = f1.selectbox(
        "Filtrar por color",
        ["Todos", "Verde (OK)", "Amarillo", "Celeste", "Rojo", "Gris", "Naranja"],
        key=f"{key_prefix}_color_f",
    )
    solo_macheo = False
    if not solo_pendiente_proveedor and not modo_elegir_proveedor:
        solo_macheo = f2.checkbox(
            "Solo prefactura conciliada", value=False, key=f"{key_prefix}_solo_macheo"
        )
    buscar = f3.text_input(
        "Buscar remito o destinatario",
        placeholder="Ej: 318022 — busca en toda la base",
        key=f"{key_prefix}_buscar",
    )

    filtros_extra = _ui_filtros_fecha_remito(key_prefix)

    leyenda_colores()
    if modo_elegir_proveedor:
        st.caption(
            "Solo casos excepcionales sin crossdock automático. "
            "**Crossdock** solo si el destino es Córdoba, Rosario o NOA **y** hay tarifa de "
            "**CLICPAQ + última milla** (LBO/FRANSOF/ALFARO). GBA u otro destino con CLICPAQ = un solo tramo."
        )
    else:
        st.caption(
            "Usá la **lupa** (primera columna) para ver el caso completo. "
            "El **proveedor** se asigna por destino y tarifario (Rosario puede requerir elección manual)."
        )

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
    params_api = _params_sin_mes_si_busca(params, buscar)

    try:
        spinner = (
            "Buscando en toda la base importada…"
            if buscar.strip()
            else "Cargando maestro…"
        )
        with st.spinner(spinner):
            filas, api_filtro_ok = get_maestro_filas_cached(
                json.dumps(params_api, sort_keys=True, default=str)
            )
        if not filas:
            if modo_elegir_proveedor:
                st.success("No hay registros pendientes de elegir proveedor.")
            else:
                st.info("Sin datos. Importá Tango desde **Configuración**.")
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
        total_maestro = len(df)

        if proveedor:
            st.metric(f"Registros en zona {etiqueta_proveedor(proveedor)}", total_maestro)
        elif solo_pendiente_proveedor or modo_elegir_proveedor:
            st.metric("Empates de proveedor", total_maestro)

        COLOR_FILTRO = {
            "Verde (OK)": "verde",
            "Amarillo": "amarillo",
            "Celeste": "celeste",
            "Rojo": "rojo",
            "Gris": "gris",
            "Naranja": "naranja",
        }
        if color_f != "Todos" and "_regla_color" in df.columns:
            df = _as_dataframe(df[df["_regla_color"] == COLOR_FILTRO[color_f]])

        if solo_macheo and "PRECIO NETO" in df.columns:
            pn = cast(pd.Series, pd.to_numeric(df["PRECIO NETO"], errors="coerce"))
            df = _as_dataframe(df[pn.notna() & (pn > 0)])

        if buscar.strip():
            df = _filtrar_df_buscar(
                df,
                buscar,
                ("REMITOS", "ENVIO", "DESTINATARIO", "LOCALIDAD", "PROVEEDOR"),
            )

        if solo_diff and "dif" in df.columns:
            dif_num = cast(pd.Series, pd.to_numeric(df["dif"], errors="coerce"))
            df = _as_dataframe(df[dif_num.notna() & (dif_num.abs() > 0.01)])
            st.warning(
                "Filtro **Solo con dif.** activo: registros con prefactura OK (dif = 0) **no se muestran**."
            )

        if buscar.strip():
            st.caption(
                f"Búsqueda en **toda la base importada** (sin filtro de mes): "
                f"**{len(df)}** de **{total_maestro}** registros."
            )
        else:
            st.caption(f"Mostrando **{len(df)}** de **{total_maestro}** registros.")

        cols_grilla = [c for c in MAESTRO_VISTA_GRILLA if c in df.columns]
        show_df = _as_dataframe(df[cols_grilla].copy())
        if "_regla_color" in df.columns:
            show_df["_regla_color"] = df["_regla_color"]
        for meta in ("_caso_id", "_es_marcador_tarifario"):
            if meta in df.columns:
                show_df[meta] = df[meta]

        sel_key = f"{key_prefix}_sel"
        if modo_elegir_proveedor:
            st.caption(
                "Casos con **empate de tarifario**. Elegí proveedor en la columna **Proveedor** "
                "de cada fila. **🔍** abre el detalle."
            )
            _render_grilla_elegir_proveedor(df, key_prefix, sel_key=sel_key)
        else:
            _render_grilla_con_detalle(show_df, df, sel_key=sel_key)

        if not solo_pendiente_proveedor and not modo_elegir_proveedor:
            with api_client() as c:
                r = c.get("/maestro/export", params={"incluir_excluidos": incluir_excl})
                r.raise_for_status()
            st.download_button(
                "Exportar planilla Excel (Tortuguitas + SA)",
                r.content,
                file_name="maestro_wamaro.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
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


MENU_PRINCIPAL = ["Dashboard", "MAESTRO", "Fletes", "Configuración"]


def _nav_on_principal() -> None:
    st.session_state.pagina_menu = st.session_state.nav_menu_principal


def _nav_on_proveedor() -> None:
    st.session_state.pagina_menu = st.session_state.nav_menu_proveedor


def _sidebar_nav_tree() -> str:
    """Menú compacto: radios + carpeta Proveedores (sin scroll en pantallas normales)."""
    if "pagina_menu" not in st.session_state:
        st.session_state.pagina_menu = "Dashboard"

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


def pagina_fletes() -> None:
    st.title("Fletes")
    st.caption(
        "Entregas CABA/GBA y retiro en sucursal. "
        "Tarifa de referencia: tarifario **fletes sucursales** (por zona km)."
    )

    if not check_health():
        st.warning("Ejecutá **Iniciar_Fletes.bat**.")
        st.stop()

    filtros_extra = _ui_filtros_fecha_remito("fletes")

    stats_params: dict[str, Any] = {}
    if filtros_extra.get("mes_control_anio") and filtros_extra.get("mes_control_mes"):
        stats_params["mes_control_anio"] = filtros_extra["mes_control_anio"]
        stats_params["mes_control_mes"] = filtros_extra["mes_control_mes"]
        stats_params["campo_fecha"] = filtros_extra.get("campo_fecha", "cualquiera")

    try:
        with st.spinner("Calculando métricas Fletes…"):
            stats = get_json("/fletes/stats", **stats_params)
    except Exception as exc:
        st.error(f"No se pudo conectar al módulo Fletes: {exc}")
        st.stop()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Casos fletes", stats.get("casos_fletes", 0))
    c2.metric("Renglones Amba/GBA", stats.get("renglones_fletes", stats.get("renglones_mundo2", 0)))
    c3.metric("Con km calculado", stats.get("con_km_calculado", 0))
    c4.metric("Pend. zona km", stats.get("pendiente_zona_km", 0))
    if stats.get("envios_cargados") is not None:
        st.caption(
            f"Período filtrado: **{stats.get('envios_cargados', 0):,}** renglones Tango en memoria "
            f"(no se carga toda la base si elegiste mes a controlar)."
        )

    with st.expander("Qué falta bajar de Tango (cuando puedas)"):
        st.markdown(
            """
            - Export del tablero **Seguimientos centralizados** para entregas locales (Distribuidora / sucursales).
            - Que el Excel traiga **código de sucursal** (AV, BE, CA…) si existe.
            - Km o prefactura **Gama / Blast** cuando tengan el formato.

            Detalle: `data/TANGO_PENDIENTE_MUNDO2.md`
            """
        )

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
    color_f = f2.selectbox(
        "Filtrar por color",
        ["Todos", "Verde (OK)", "Amarillo", "Celeste", "Rojo", "Gris", "Naranja"],
        key="fletes_color",
    )
    buscar = f3.text_input(
        "Buscar remito o destinatario",
        placeholder="Ej: 318022 — busca en toda la base",
        key="fletes_buscar",
    )
    try:
        fleteros_api = get_json("/fletes/fleteros")
        opciones_f = ["Todos"] + [f["nombre_corto"] for f in fleteros_api]
    except Exception:
        opciones_f = ["Todos"]
    fletero_f = f4.selectbox("Fletero local", opciones_f, key="fletes_fletero")

    leyenda_colores()

    c_calc, _ = st.columns([2, 4])
    if c_calc.button("Calcular km pendientes (hasta 25)", key="fletes_calc_km"):
        try:
            with api_client() as c:
                r = c.post("/fletes/calcular-km", params={"limit": 25})
                r.raise_for_status()
                st.toast(r.json())
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    st.caption(
        "Pedidos Amba/GBA ya importados desde Tango. "
        "**REMITOS** muestra solo **RAR** o **R** (remito del CD). Si la celda está vacía, "
        "ese export trae solo la **X** de tránsito en REMITO DI — cargá también el Excel "
        "completo de Limansky (columna *NRO REMITO LEGAL LIMANSKY*) o reaplicá reglas en Maestro. "
        "**Calcular km** usa geocodificación y sucursal por localidad."
    )

    params: dict[str, Any] = {}
    params.update(filtros_extra)
    if origen_f == "Tortuguitas":
        params["origen"] = "tortuguitas"
    elif origen_f == "SA / Limansky":
        params["origen"] = "sa"
    if fletero_f and fletero_f != "Todos":
        params["fletero"] = fletero_f
        if (
            not buscar.strip()
            and params.get("mes_control_mes")
            and params.get("mes_control_anio")
        ):
            try:
                res_f = get_json(
                    "/fletes/internos/resumen",
                    mes=int(params["mes_control_mes"]),
                    anio=int(params["mes_control_anio"]),
                    fletero=fletero_f,
                )
                for row in res_f.get("fleteros") or []:
                    if row.get("nombre_corto") == fletero_f:
                        st.info(
                            f"**{fletero_f}** en el período: "
                            f"{row.get('entregas', 0)} entregas Drive · "
                            f"{row.get('matcheadas', 0)} en maestro Fletes · "
                            f"total a pagar **{fmt_pesos_ar(row.get('total_pagar', 0))}** "
                            f"(detalle en grilla; carga del Excel en Configuración → Fleteros locales)."
                        )
                        break
            except Exception:
                pass

    params_api = _params_sin_mes_si_busca(params, buscar)

    try:
        spinner = (
            "Buscando en toda la base importada…"
            if buscar.strip()
            else "Cargando casos Fletes…"
        )
        with st.spinner(spinner):
            filas = get_fletes_casos_cached(
                json.dumps(params_api, sort_keys=True, default=str)
            )
        if not filas:
            st.info(
                "No hay casos de flete en la base. Si ya importaste Tango, "
                "revisá que haya pedidos Amba/GBA o ejecutá **Reaplicar reglas** en Maestro."
            )
            return

        df = preparar_maestro_df(pd.DataFrame(filas))
        COLOR_FILTRO = {
            "Verde (OK)": "verde",
            "Amarillo": "amarillo",
            "Celeste": "celeste",
            "Rojo": "rojo",
            "Gris": "gris",
            "Naranja": "naranja",
        }
        if color_f != "Todos" and "_regla_color" in df.columns:
            df = _as_dataframe(df[df["_regla_color"] == COLOR_FILTRO[color_f]])

        if buscar.strip():
            df = _filtrar_df_buscar(
                df,
                buscar,
                ("REMITOS", "ENVIO", "DESTINATARIO", "LOCALIDAD", "FLETERO"),
            )

        if buscar.strip():
            st.caption(
                f"Búsqueda en **toda la base importada** (sin filtro de mes): "
                f"**{len(df)}** casos. Usá la **lupa** a la izquierda de cada fila."
            )
        else:
            st.caption(
                f"Mostrando **{len(df)}** casos. "
                "Usá la **lupa** a la izquierda de cada fila (mismo popup que en Maestro). "
            )

        cols = [c for c in FLETES_VISTA_GRILLA if c in df.columns]
        show_df = _as_dataframe(df[cols].copy())
        if "_regla_color" in df.columns:
            show_df["_regla_color"] = df["_regla_color"]

        _render_grilla_con_detalle(show_df, df, sel_key="fletes_sel")
    except Exception as exc:
        st.error(str(exc))


def _config_fleteros_locales() -> None:
    """Pestaña Configuración — Excel Drive + macheo contra maestro Fletes."""
    from datetime import date

    st.subheader("Fleteros locales (AMBA / GBA)")
    st.caption(
        "Entregas sucursal → domicilio con fleteros de confianza (BLAS, GAMA, ARMANDO…). "
        "El cliente puede ver **$0**; acá cargás el Excel del Drive y lo cruzás con el **maestro Fletes**. "
        "El resultado se ve en **Fletes** (columna y filtro Fletero)."
    )
    plantilla_download(
        "plantilla_fletes_solicitud.xlsx",
        "Descargar plantilla / ejemplo (Drive)",
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

    upl = st.file_uploader(
        "Excel «Fletes solicitados sucursales»",
        type=["xlsx"],
        key="cfg_fleteros_import",
    )
    b1, b2 = st.columns(2)
    if b1.button("Importar Excel", type="primary", disabled=upl is None):
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

    if b2.button("Machear con maestro Fletes", disabled=n_sol == 0):
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
    else:
        st.info(
            "Sin datos de fleteros locales. Subí el Excel del Drive "
            "(ej. «Fletes Solicitados sucursales MAYO») y luego ejecutá el macheo."
        )


def pagina_configuracion() -> None:
    st.title("Configuración")
    st.caption("Carga de archivos, tarifarios y parámetros del sistema.")

    if not check_health():
        st.warning("Conectá el servidor con **Iniciar_Fletes.bat** antes de importar.")
        st.stop()

    tab_tango, tab_cp, tab_pv, tab_liq, tab_tar, tab_flet, tab_sys = st.tabs(
        [
            "Tango (principal)",
            "Prefactura Clicpaq",
            "Postventa",
            "Liquidación",
            "Tarifarios",
            "Fleteros locales",
            "Sistema",
        ]
    )

    with tab_tango:
        st.subheader("Exportacion.xlsx — SommierCenter")
        st.markdown(
            """
            **Cómo exportar en Tango (estándar recomendado)**

            1. Elegí el **mes a controlar** en Maestro/Fletes (ej. mayo).
            2. En Tango, exportá el **mes que estás controlando** (ej. 01/05 → 31/05).
            3. **Cada archivo nuevo se suma** a la base (las filas ya importadas no se pisan).
            4. El remito oficial es **RAR / R** (`NRO REMITO LEGAL LIMANSKY`); la **X** es tránsito.

            Podés importar **abril, mayo y junio** por separado; la grilla filtra por el mes elegido.
            """
        )
        tango = st.file_uploader("Archivo Tango", type=["xlsx"], key="cfg_tango")
        if st.button("Importar Tango", type="primary", disabled=tango is None):
            try:
                if tango is None:
                    raise RuntimeError("Seleccioná un archivo Tango.")
                r = post_file("/import/tango", tango.name, tango.getvalue())
                msg = r["message"]
                if r.get("rows_rejected"):
                    st.warning(msg)
                else:
                    st.success(msg)
                st.caption(
                    f"Archivo: {r['rows_in_file']} filas · "
                    f"{r['rows_inserted']} nuevas · {r['rows_skipped']} omitidas"
                )
                get_maestro_filas_cached.clear()
                get_fletes_casos_cached.clear()
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
        plantilla_download("plantilla_clickpack.xlsx", "Plantilla prefactura")
        plantilla_download(
            "prefactura_clickpack_prueba.xlsx",
            "Descargar prefactura ficticia de prueba (3 remitos)",
        )
        st.caption(
            "La prefactura de prueba trae importes para remitos en canal red (transporte 51/40) "
            "que ya tienen tarifa. **No sirve** si el costo tarifario es $0."
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
            "La grilla de postventa suele ser **la misma exportación de Tango**. "
            "Si el Excel trae columnas **TipoGestion** y **SubTipo**, las reglas se aplican "
            "al importar o al **Reaplicar reglas** en Envíos interior. "
            "También podés cargar motivos en un archivo aparte."
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

    with tab_sys:
        st.subheader("Sistema")
        st.text_input("URL del API", value=API_URL, disabled=True)
        st.markdown(
            """
            - **Seguro fijo:** $30 por envío (tarifario)
            - **Gestión retiro postventa:** +25%
            - **Depósitos** (editar en `backend/app/config.py`):
              - `14` → CD Tortuguitas
              - `12` → Limansky Hurlingham
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
            "Al finalizar el mes, vaciá los datos operativos para cargar el nuevo Excel de Tango. "
            "Los **tarifarios se conservan** (salvo que marques la opción)."
        )

        try:
            conteo = get_json("/sistema/conteo")
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Envíos", conteo["envios"])
            c2.metric("Prefacturas", conteo["prefacturas_clickpack"])
            c3.metric("Postventa", conteo["postventa"])
            c4.metric("Liquidación", conteo["liquidacion"])
            c5.metric("Tarifas", conteo["tarifas"])
        except Exception:
            conteo = None

        borrar_tarifas = st.checkbox("También vaciar tarifarios cargados", value=False)
        confirmar = st.checkbox("Confirmo que quiero vaciar los datos del período", value=False)
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


# --- Main ---

st.set_page_config(
    page_title="Control de Fletes",
    page_icon="🚚",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_theme()

# Limpiar enlaces viejos (?_gcaso=) que abrían pestaña duplicada
if st.query_params.get("_gcaso") or st.query_params.get("_gsk"):
    try:
        del st.query_params["_gcaso"]
        del st.query_params["_gsk"]
    except Exception:
        pass

st.sidebar.markdown(
    '<p class="sidebar-brand">Control de Fletes</p>'
    '<p class="sidebar-brand-caption">SommierCenter · Wamaro</p>',
    unsafe_allow_html=True,
)

pagina = _sidebar_nav_tree()

st.sidebar.markdown("---")
if check_health():
    build = api_build_actual()
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
    pagina_casos(titulo="MAESTRO", key_prefix="maestro")
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
