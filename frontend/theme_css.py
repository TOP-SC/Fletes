"""Estilos globales Streamlit — claro y oscuro."""

from __future__ import annotations

# Variables y reglas compartidas (acento por módulo vía --mod-accent)
BASE_CSS = """
:root {
    --brand-navy: #1a365d;
    --brand-blue: #2c5282;
    --mod-accent: #2b6cb0;
    --mod-accent2: #4299e1;
    --mod-bg: #ebf4ff;
    --app-bg: linear-gradient(165deg, #faf8f5 0%, #f0f4fa 42%, #f3eef8 100%);
    --surface: #ffffff;
    --surface-2: #f8fafc;
    --ink: #1e2a3a;
    --ink-muted: #5c6b7d;
    --border: #dde5f0;
    --sidebar-bg: linear-gradient(180deg, #f8fafc 0%, #eef2f8 100%);
    --sidebar-ink: #2c3e50;
    --metric-bg: #ffffffee;
    --watermark: rgba(30, 42, 58, 0.42);
}
"""

LIGHT_CSS = """
.stApp { background: var(--app-bg); color: var(--ink); }
[data-testid="stHeader"] { background: transparent !important; }
[data-testid="stSidebar"] {
    background: var(--sidebar-bg) !important;
    border-right: 1px solid #d5dde8;
}
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stMarkdown, [data-testid="stSidebar"] p,
[data-testid="stSidebar"] span { color: var(--sidebar-ink) !important; }
[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {
    background: color-mix(in srgb, var(--mod-accent) 14%, #ffffff) !important;
    border-left-color: var(--mod-accent) !important;
}
h1, h2, h3 { color: #2c3e50 !important; }
.main, .block-container, [data-testid="stAppViewContainer"] p,
[data-testid="stAppViewContainer"] label, [data-testid="stAppViewContainer"] span {
    color: var(--ink);
}
div[data-testid="stMetric"] {
    background: var(--metric-bg) !important;
    border: 1px solid var(--border);
}
div[data-testid="stMetric"] label,
div[data-testid="stMetric"] [data-testid="stMetricLabel"] p {
    color: var(--ink-muted) !important;
}
div[data-testid="stMetric"] [data-testid="stMetricValue"],
div[data-testid="stMetric"] [data-testid="stMetricDelta"] {
    color: var(--ink) !important;
}
section.main div[data-testid="stVerticalBlockBorderWrapper"]:has(.panel-acciones-label) {
    background: var(--mod-bg) !important;
    border-color: rgba(30, 42, 58, 0.1) !important;
}
section.main div[data-testid="stVerticalBlockBorderWrapper"]:has(.panel-acciones-label)
[data-testid="stMetric"] {
    background: var(--surface) !important;
}
section.main div[data-testid="stVerticalBlockBorderWrapper"]:has(.panel-acciones-label)
[data-testid="stMetric"] [data-testid="stMetricValue"] {
    color: var(--ink) !important;
}
.stCaption, small { color: var(--ink-muted) !important; }
div[data-baseweb="select"] > div, div[data-baseweb="input"] > div,
textarea, input {
    background-color: var(--surface) !important;
    color: var(--ink) !important;
    border-color: var(--border) !important;
}
.top-watermark { color: var(--watermark); }
"""

DARK_CSS = """
:root {
    --app-bg: linear-gradient(165deg, #0b0f14 0%, #111827 38%, #0f172a 100%);
    --surface: #1e293b;
    --surface-2: #162032;
    --ink: #e8eef6;
    --ink-muted: #94a3b8;
    --border: #334155;
    --sidebar-bg: linear-gradient(180deg, #0f172a 0%, #111827 100%);
    --sidebar-ink: #cbd5e1;
    --metric-bg: #1e293b;
    --mod-bg: #1a2740;
    --watermark: rgba(148, 163, 184, 0.35);
}
.stApp { background: var(--app-bg) !important; color: var(--ink); }
[data-testid="stHeader"] { background: transparent !important; }
[data-testid="stSidebar"] {
    background: var(--sidebar-bg) !important;
    border-right: 1px solid var(--border) !important;
}
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stMarkdown, [data-testid="stSidebar"] p,
[data-testid="stSidebar"] span { color: var(--sidebar-ink) !important; }
[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {
    background: color-mix(in srgb, var(--mod-accent) 22%, #1e293b) !important;
    border-left-color: var(--mod-accent) !important;
}
[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) *,
[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked)
[data-testid="stMarkdownContainer"] p {
    color: #f1f5f9 !important;
    -webkit-text-fill-color: #f1f5f9 !important;
}
[data-testid="stSidebar"] [data-testid="stExpander"] summary { color: #94a3b8 !important; }
.main, .block-container, [data-testid="stAppViewContainer"] p,
[data-testid="stAppViewContainer"] label, [data-testid="stAppViewContainer"] span {
    color: var(--ink);
}
h1, h2, h3, h4 { color: var(--ink) !important; }
.page-header {
    background: var(--mod-bg) !important;
    border-color: var(--border) !important;
    box-shadow: 0 2px 16px rgba(0,0,0,0.25) !important;
}
.page-header h1 { color: var(--ink) !important; }
.page-header .page-header-caption { color: var(--ink-muted) !important; }
div[data-testid="stMetric"] {
    background: var(--metric-bg) !important;
    border-color: var(--border) !important;
    box-shadow: 0 2px 12px rgba(0,0,0,0.2) !important;
}
div[data-testid="stMetric"] label { color: var(--ink-muted) !important; }
div[data-testid="stMetric"] [data-testid="stMetricValue"] { color: var(--ink) !important; }
section.main div[data-testid="stVerticalBlockBorderWrapper"]:has(.panel-acciones-label) {
    background: var(--mod-bg) !important;
    border-color: var(--border) !important;
    box-shadow: 0 2px 16px rgba(0,0,0,0.22) !important;
}
section.main div[data-testid="stVerticalBlockBorderWrapper"]:has(.panel-acciones-label) [data-testid="stMetric"] {
    background: var(--surface) !important;
}
.dash-card {
    background: var(--surface) !important;
    border-color: var(--border) !important;
}
.dash-card-body { color: var(--ink) !important; }
.leyenda-chip { border-color: var(--border) !important; }
[data-testid="stDataFrame"], [data-testid="stTable"] {
    border-radius: 10px;
}
.stTabs [data-baseweb="tab-list"] { background: transparent; }
.stTabs [data-baseweb="tab-list"] button { color: var(--ink-muted) !important; }
.stTabs [data-baseweb="tab-list"] button[aria-selected="true"] {
    color: var(--mod-accent) !important;
}
div[data-baseweb="select"] > div, div[data-baseweb="input"] > div,
textarea, input {
    background-color: var(--surface) !important;
    color: var(--ink) !important;
    border-color: var(--border) !important;
}
[data-testid="stAlert"] { border-radius: 10px; }
.top-watermark { color: var(--watermark) !important; }
.kpi-entregas-wrap {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 1rem 1.1rem;
    margin-top: 0;
    box-shadow: 0 4px 20px rgba(0,0,0,0.15);
}
.kpi-entregas-wrap h3 { color: var(--ink) !important; font-size: 0.95rem !important; margin: 0 0 0.35rem !important; }
.kpi-entregas-wrap .sub { color: var(--ink-muted); font-size: 0.75rem; margin-bottom: 0.65rem; }
.kpi-entregas-total {
    display: flex; gap: 1.5rem; flex-wrap: wrap;
    margin: 0.5rem 0 0.75rem;
    font-size: 0.82rem;
}
.kpi-entregas-total strong { color: var(--ink); }
[data-testid="stExpander"] {
    background: var(--surface) !important;
    border-color: var(--border) !important;
}
[data-testid="stExpander"] summary { color: var(--ink) !important; }
.stCaption, small { color: var(--ink-muted) !important; }
section.main div[data-testid="stVerticalBlockBorderWrapper"]:has(.panel-acciones-label)
[data-testid="stMetric"] [data-testid="stMetricValue"] {
    color: var(--ink) !important;
}
section.main div[data-testid="stVerticalBlockBorderWrapper"]:has(.panel-acciones-label)
[data-testid="stMetric"] label,
section.main div[data-testid="stVerticalBlockBorderWrapper"]:has(.panel-acciones-label)
[data-testid="stMetric"] [data-testid="stMetricLabel"] p {
    color: var(--ink-muted) !important;
}
"""

SIDEBAR_NAV_CSS = """
/* Nav lateral: texto siempre legible aunque Streamlit use tema oscuro del SO */
[data-testid="stSidebar"] div[role="radiogroup"] label {
    color: var(--sidebar-ink) !important;
}
[data-testid="stSidebar"] div[role="radiogroup"] label:not(:has(input:checked)) *,
[data-testid="stSidebar"] div[role="radiogroup"] label:not(:has(input:checked))
[data-testid="stMarkdownContainer"],
[data-testid="stSidebar"] div[role="radiogroup"] label:not(:has(input:checked))
[data-testid="stMarkdownContainer"] p,
[data-testid="stSidebar"] div[role="radiogroup"] label:not(:has(input:checked))
[data-testid="stMarkdownContainer"] span {
    color: var(--sidebar-ink) !important;
    -webkit-text-fill-color: var(--sidebar-ink) !important;
}
[data-testid="stSidebar"] div[role="radiogroup"] input[type="radio"] {
    accent-color: var(--mod-accent);
}
"""

SHARED_COMPONENT_CSS = """
.sidebar-brand-band {
    margin: -0.75rem -1rem 0.85rem -1rem;
    padding: 1rem 1rem 0.9rem 1rem;
    background: linear-gradient(135deg, #1a365d 0%, #2c5282 55%, #3182ce 100%);
    border-radius: 0 0 14px 14px;
    box-shadow: 0 4px 14px rgba(26, 54, 93, 0.22);
}
.sidebar-brand-band .sidebar-brand-title {
    font-size: 1.12rem; font-weight: 700; color: #ffffff;
    margin: 0; line-height: 1.25; letter-spacing: 0.01em;
}
.sidebar-brand-band .sidebar-brand-caption {
    font-size: 0.76rem; color: rgba(255, 255, 255, 0.88); margin: 0.2rem 0 0 0;
}
.page-header {
    background: var(--mod-bg);
    border: 1px solid rgba(0, 0, 0, 0.06);
    border-left: 6px solid var(--mod-accent);
    border-radius: 0 14px 14px 0;
    padding: 0.85rem 1.15rem 0.75rem 1rem;
    margin: 0 0 1rem 0;
    box-shadow: 0 2px 12px rgba(30, 42, 58, 0.06);
}
.page-header h1 {
    font-size: 1.55rem !important; font-weight: 700 !important;
    color: var(--ink) !important; margin: 0 !important; padding: 0 !important;
    line-height: 1.2 !important;
}
.page-header .page-header-icon { color: var(--mod-accent); margin-right: 0.35rem; }
.page-header .page-header-caption {
    font-size: 0.88rem; color: var(--ink-muted); margin: 0.35rem 0 0 0; line-height: 1.4;
}
section[data-testid="stSidebar"],
[data-testid="stSidebar"] > div,
[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
    scrollbar-width: none !important; -ms-overflow-style: none !important;
}
section[data-testid="stSidebar"]::-webkit-scrollbar,
[data-testid="stSidebar"] > div::-webkit-scrollbar,
[data-testid="stSidebar"] [data-testid="stSidebarContent"]::-webkit-scrollbar {
    display: none !important; width: 0 !important; height: 0 !important;
}
[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
    padding-top: 0.75rem !important; padding-bottom: 0.5rem !important;
    overflow-x: hidden !important;
}
[data-testid="stSidebar"] div[role="radiogroup"] { gap: 0.15rem !important; }
[data-testid="stSidebar"] div[role="radiogroup"] label {
    font-size: 0.92rem !important; font-weight: 600 !important;
    padding: 0.42rem 0.55rem 0.42rem 0.65rem !important;
    min-height: 0 !important; margin: 0 !important; border-radius: 8px !important;
    border-left: 4px solid transparent !important;
    transition: background 0.15s ease, border-color 0.15s ease;
}
[data-testid="stSidebar"] [data-testid="stExpander"] {
    margin: 0.15rem 0 0.1rem 0 !important; border: none !important; background: transparent !important;
}
[data-testid="stSidebar"] [data-testid="stExpander"] summary {
    font-size: 0.88rem !important; font-weight: 700 !important;
    padding: 0.15rem 0 !important; min-height: 0 !important;
}
[data-testid="stSidebar"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] {
    padding: 0 0 0 0.65rem !important;
    border-left: 2px solid color-mix(in srgb, var(--mod-accent) 35%, #b8c9de);
    margin-left: 0.25rem !important;
}
.stTabs [data-baseweb="tab-list"] button[aria-selected="true"] {
    border-bottom-color: var(--mod-accent) !important;
    color: var(--mod-accent) !important; font-weight: 600 !important;
}
.stButton button[kind="primary"] {
    background: linear-gradient(135deg, var(--mod-accent) 0%, var(--mod-accent2) 100%) !important;
    border: none !important;
}
[data-testid="stSidebar"] .nav-status-ok { background: #d4edda !important; color: #1f5c35 !important; }
[data-testid="stSidebar"] .nav-status-warn { background: #fff3cd !important; color: #7a5c00 !important; }
[data-testid="stSidebar"] .nav-status-err { background: #f8d7da !important; color: #8b2525 !important; }
.block-container { padding-top: 1.25rem; }
div[data-testid="stMetric"] {
    border-left: 5px solid var(--mod-accent, #8FA8C8);
    border-radius: 14px; padding: 0.65rem 0.85rem 0.65rem 1rem;
    box-shadow: 0 2px 8px #0000000a; overflow: hidden;
}
.panel-acciones-label {
    font-size: 0.68rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.08em; color: var(--mod-accent); margin: 0 0 0.15rem 0;
}
section.main div[data-testid="stVerticalBlockBorderWrapper"]:has(.panel-acciones-label) {
    background: var(--mod-bg) !important;
    border: 1px solid rgba(30, 42, 58, 0.1) !important;
    border-left: 5px solid var(--mod-accent) !important;
    border-radius: 12px !important;
    padding: 0.75rem 0.95rem 0.95rem !important;
    margin-bottom: 1rem !important;
}
.top-watermark {
    position: fixed; bottom: 0.65rem; left: 50%; transform: translateX(-50%);
    font-size: 0.7rem; font-weight: 500; pointer-events: none; z-index: 999;
    white-space: nowrap; text-align: center;
}
"""


def theme_stylesheet(*, dark: bool) -> str:
    variant = DARK_CSS if dark else LIGHT_CSS
    return f"<style>{BASE_CSS}{variant}{SHARED_COMPONENT_CSS}{SIDEBAR_NAV_CSS}</style>"
