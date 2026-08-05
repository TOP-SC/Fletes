"""
Informe KPI ISO 9001 — Control de Fletes (patrón TicketFlow, dominio logístico).

Adaptación: la entidad principal es el **caso/remito** (grupo de renglones Tango),
no un ticket de helpdesk. Donde no hay dato (CSAT, encuesta, SLA prometido),
el KPI muestra «—» con nota clara; nunca falla.
"""

from __future__ import annotations

import math
from collections import Counter
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models import Envio
from app.services.fecha_utils import parse_fecha_tango
from app.services.maestro_service import _agrupar_por_caso
from app.services.remito_maestro import estado_remito_envio

KPI_DEFINITIONS: list[dict[str, str]] = [
    {
        "id": "KPI1",
        "stage": "Atención / ciclo",
        "name": "Tiempo medio pedido → entrega",
        "objective": "Medir la demora operativa desde el pedido Tango hasta la fecha de entrega.",
        "formula": "Promedio de días (fecha_pedido → fecha_entrega) en casos con ambas fechas.",
        "iso": "ISO 9001 — 8.2 / 9.1 (seguimiento del desempeño del servicio)",
    },
    {
        "id": "KPI2",
        "stage": "Atención / ciclo",
        "name": "MTTR logístico (casos con remito)",
        "objective": "Tiempo medio de resolución operativa entre pedidos ya remitidos.",
        "formula": "Promedio de días (pedido → entrega) solo en casos con remito oficial.",
        "iso": "ISO 9001 — 8.5 / 9.1 (eficacia del proceso de entrega)",
    },
    {
        "id": "KPI3",
        "stage": "Backlog de control",
        "name": "Volumen en backlog de control",
        "objective": "Cuántos casos siguen pendientes de cierre de control de fletes.",
        "formula": (
            "Conteo de casos con: falta tarifa, elegir proveedor, macheo pendiente "
            "o sin remito con fecha de entrega."
        ),
        "iso": "ISO 9001 — 8.7 / 10.2 (control de salidas no conformes / pendientes)",
    },
    {
        "id": "KPI4",
        "stage": "Cumplimiento",
        "name": "Tasa de remito a tiempo (proxy SLA)",
        "objective": (
            "Porcentaje de casos con fecha de entrega que ya tienen remito oficial. "
            "No existe fecha prometida contractual en Tango; es proxy de cumplimiento."
        ),
        "formula": "Casos con remito / casos con fecha de entrega × 100.",
        "iso": "ISO 9001 — 8.2.1 / 9.1.2 (satisfacción / conformidad del servicio)",
    },
    {
        "id": "KPI5",
        "stage": "Retrabajo",
        "name": "Tasa de retrabajo / postventa",
        "objective": "Incidencia de casos que requieren corrección (postventa o diferencia vs prefactura).",
        "formula": (
            "Casos con postventa valorizable/gestión o |diferencia prefactura| > 0, "
            "sobre casos con remito × 100."
        ),
        "iso": "ISO 9001 — 8.7 / 10.2 (no conformidad y acción correctiva)",
    },
    {
        "id": "KPI6",
        "stage": "Satisfacción",
        "name": "CSAT promedio",
        "objective": "Promedio de satisfacción del cliente (encuesta).",
        "formula": "Media de calificaciones CSAT.",
        "iso": "ISO 9001 — 9.1.2 (satisfacción del cliente)",
    },
    {
        "id": "KPI7",
        "stage": "Satisfacción",
        "name": "Tasa de respuesta a encuesta",
        "objective": "Porcentaje de casos cerrados con encuesta respondida.",
        "formula": "Encuestas respondidas / casos con remito × 100.",
        "iso": "ISO 9001 — 9.1.2 / 9.1.3 (análisis y evaluación)",
    },
]

_CHART_COLORS = (
    "#2563eb",
    "#16a34a",
    "#dc2626",
    "#ca8a04",
    "#7c3aed",
    "#0891b2",
    "#ea580c",
    "#64748b",
)


def _as_date(envio: Envio, which: str) -> date | None:
    if which == "pedido":
        if envio.fecha_pedido_d:
            return envio.fecha_pedido_d
        return parse_fecha_tango(envio.fecha_pedido)
    if envio.fecha_entrega_d:
        return envio.fecha_entrega_d
    return parse_fecha_tango(envio.fecha_entrega)


def _caso_from_grupo(key: str, lineas: list[Envio]) -> dict[str, Any]:
    base = lineas[0]
    fp = _as_date(base, "pedido")
    fe = _as_date(base, "entrega")
    ciclo_dias: float | None = None
    if fp and fe:
        ciclo_dias = float((fe - fp).days)
    costo = max((float(l.costo_tarifario or 0) for l in lineas), default=0.0)
    pref = next((l.prefactura_proveedor for l in lineas if l.prefactura_proveedor is not None), None)
    dif = next((l.diferencia for l in lineas if l.diferencia is not None), None)
    macheo = next((l.macheo_estado for l in lineas if l.macheo_estado), None)
    postventa = any(
        (l.tipo_gestion or l.sub_tipo_gestion or l.regla_postventa) for l in lineas
    )
    requiere_prov = any(l.requiere_elegir_proveedor for l in lineas)
    estado_r = estado_remito_envio(base)
    return {
        "caso_id": key,
        "fecha_pedido": fp,
        "fecha_entrega": fe,
        "ciclo_dias": ciclo_dias,
        "estado_remito": estado_r,
        "con_remito": estado_r == "con_remito",
        "costo_tarifario": costo,
        "prefactura": pref,
        "diferencia": dif,
        "macheo_estado": macheo,
        "postventa": postventa,
        "requiere_proveedor": requiere_prov,
        "proveedor": (base.proveedor_tarifa or "").strip().upper() or "SIN ASIGNAR",
        "excluir_planilla": bool(base.excluir_planilla),
    }


def _casos_desde_db(db: Session) -> list[dict[str, Any]]:
    envios = list(db.query(Envio).all())
    grupos = _agrupar_por_caso(envios)
    return [_caso_from_grupo(k, g) for k, g in grupos.items()]


def _mean(vals: list[float]) -> float | None:
    if not vals:
        return None
    return sum(vals) / len(vals)


def _pct(num: float, den: float) -> float | None:
    if den <= 0:
        return None
    return round(100.0 * num / den, 1)


def _result(
    display: str,
    *,
    unit: str = "",
    note: str = "",
    value: float | None = None,
) -> dict[str, Any]:
    return {"display": display, "unit": unit, "note": note, "value": value}


def _bucket_ciclo(dias: float) -> str:
    if dias <= 1:
        return "≤ 1 día"
    if dias <= 3:
        return "1–3 días"
    if dias <= 7:
        return "3–7 días"
    if dias <= 15:
        return "7–15 días"
    return "> 15 días"


def compute_iso_kpis(casos: list[dict[str, Any]]) -> dict[str, Any]:
    """Calcula los 7 KPIs ISO adaptados al dominio Fletes."""
    generated_at = datetime.now(timezone.utc).astimezone().strftime("%d/%m/%Y %H:%M")

    ciclos_todos = [
        float(c["ciclo_dias"])
        for c in casos
        if c.get("ciclo_dias") is not None and c["ciclo_dias"] >= 0
    ]
    ciclos_remito = [
        float(c["ciclo_dias"])
        for c in casos
        if c.get("con_remito")
        and c.get("ciclo_dias") is not None
        and c["ciclo_dias"] >= 0
    ]

    m1 = _mean(ciclos_todos)
    m2 = _mean(ciclos_remito)

    backlog = [
        c
        for c in casos
        if c.get("requiere_proveedor")
        or (c.get("con_remito") and not (c.get("costo_tarifario") or 0) and not c.get("excluir_planilla"))
        or (c.get("macheo_estado") == "pendiente_clickpack")
        or (c.get("estado_remito") in ("sin_remito", "solo_transito") and c.get("fecha_entrega"))
    ]

    con_fecha = [c for c in casos if c.get("fecha_entrega")]
    con_remito_y_fecha = [c for c in con_fecha if c.get("con_remito")]
    p4 = _pct(len(con_remito_y_fecha), len(con_fecha))

    cerrados = [c for c in casos if c.get("con_remito")]
    retrabajo = [
        c
        for c in cerrados
        if c.get("postventa")
        or (
            c.get("diferencia") is not None
            and abs(float(c["diferencia"])) > 0.01
        )
    ]
    p5 = _pct(len(retrabajo), len(cerrados))

    results: dict[str, dict[str, Any]] = {
        "KPI1": (
            _result(
                f"{m1:.1f}",
                unit="días",
                note=f"n={len(ciclos_todos)} casos con pedido y entrega",
                value=round(m1, 2),
            )
            if m1 is not None
            else _result("—", note="Sin casos con fecha de pedido y entrega")
        ),
        "KPI2": (
            _result(
                f"{m2:.1f}",
                unit="días",
                note=f"n={len(ciclos_remito)} casos con remito oficial",
                value=round(m2, 2),
            )
            if m2 is not None
            else _result("—", note="Sin casos con remito y fechas para MTTR")
        ),
        "KPI3": _result(
            str(len(backlog)),
            unit="casos",
            note=(
                f"Pendientes de control sobre {len(casos)} casos totales "
                "(tarifa / proveedor / macheo / remito)"
            ),
            value=float(len(backlog)),
        ),
        "KPI4": (
            _result(
                f"{p4:.1f}",
                unit="%",
                note=(
                    f"{len(con_remito_y_fecha)}/{len(con_fecha)} con remito "
                    "(proxy: no hay fecha prometida contractual en Tango)"
                ),
                value=p4,
            )
            if p4 is not None
            else _result("—", note="Sin casos con fecha de entrega")
        ),
        "KPI5": (
            _result(
                f"{p5:.1f}",
                unit="%",
                note=f"{len(retrabajo)}/{len(cerrados)} con postventa o diferencia prefactura",
                value=p5,
            )
            if p5 is not None
            else _result("—", note="Sin casos con remito para medir retrabajo")
        ),
        "KPI6": _result(
            "—",
            note="Sin dato: la app no registra calificaciones CSAT / encuesta de satisfacción",
        ),
        "KPI7": _result(
            "—",
            note="Sin dato: no hay módulo de encuestas respondidas por caso cerrado",
        ),
    }

    # --- Charts ---
    est_rem = Counter(c.get("estado_remito") or "desconocido" for c in casos)
    label_est = {
        "con_remito": "Con remito",
        "sin_remito": "Sin remito",
        "solo_transito": "Solo tránsito (X)",
        "sin_fecha_entrega": "Sin fecha entrega",
    }
    chart_estado = {
        "title": "Casos por estado de remito",
        "slices": [
            {"label": label_est.get(k, str(k)), "value": int(v)}
            for k, v in est_rem.most_common()
            if v > 0
        ],
    }

    bl_reasons = Counter()
    for c in backlog:
        if c.get("requiere_proveedor"):
            bl_reasons["Elegir proveedor"] += 1
        elif c.get("macheo_estado") == "pendiente_clickpack":
            bl_reasons["Macheo pendiente"] += 1
        elif c.get("estado_remito") in ("sin_remito", "solo_transito"):
            bl_reasons["Sin remito oficial"] += 1
        elif not (c.get("costo_tarifario") or 0):
            bl_reasons["Sin tarifa"] += 1
        else:
            bl_reasons["Otro pendiente"] += 1
    chart_backlog = {
        "title": "Composición del backlog de control",
        "slices": [
            {"label": k, "value": int(v)} for k, v in bl_reasons.most_common() if v > 0
        ]
        or [{"label": "Sin backlog", "value": 1}],
    }

    buckets = Counter(_bucket_ciclo(d) for d in ciclos_todos)
    order_b = ["≤ 1 día", "1–3 días", "3–7 días", "7–15 días", "> 15 días"]
    chart_ciclo = {
        "title": "Distribución del ciclo pedido → entrega",
        "slices": [
            {"label": b, "value": int(buckets[b])} for b in order_b if buckets.get(b)
        ]
        or [{"label": "Sin datos de ciclo", "value": 1}],
    }

    macheo_c = Counter()
    for c in casos:
        if c.get("prefactura") is not None:
            dif = c.get("diferencia")
            if dif is not None and abs(float(dif)) > 0.01:
                macheo_c["Con diferencia"] += 1
            else:
                macheo_c["Macheo OK"] += 1
        elif c.get("macheo_estado") == "pendiente_clickpack":
            macheo_c["Pendiente prefactura"] += 1
        else:
            macheo_c["Sin prefactura"] += 1
    chart_macheo = {
        "title": "Estado de macheo / prefactura",
        "slices": [
            {"label": k, "value": int(v)} for k, v in macheo_c.most_common() if v > 0
        ],
    }

    prov_c = Counter(c.get("proveedor") or "SIN ASIGNAR" for c in casos if c.get("con_remito"))
    top_prov = prov_c.most_common(6)
    otros = sum(v for _, v in prov_c.most_common()[6:])
    slices_prov = [{"label": k, "value": int(v)} for k, v in top_prov]
    if otros:
        slices_prov.append({"label": "Otros", "value": int(otros)})
    chart_prov = {
        "title": "Casos con remito por proveedor de tarifa",
        "slices": slices_prov or [{"label": "Sin datos", "value": 1}],
    }

    charts = [chart_estado, chart_backlog, chart_ciclo, chart_macheo, chart_prov]

    totals = {
        "casos": len(casos),
        "con_remito": sum(1 for c in casos if c.get("con_remito")),
        "backlog": len(backlog),
        "con_fecha_entrega": len(con_fecha),
        "postventa_o_dif": len(retrabajo),
    }

    return {
        "generated_at": generated_at,
        "app": "Control de Fletes",
        "domain": "Logística / casos-remito Tango",
        "definitions": KPI_DEFINITIONS,
        "results": results,
        "charts": charts,
        "totals": totals,
    }


def compute_iso_kpis_from_db(db: Session) -> dict[str, Any]:
    return compute_iso_kpis(_casos_desde_db(db))


def render_pie_svg(slices: list[dict[str, Any]], title: str, size: int = 220) -> str:
    """Torta SVG autocontenida (sin JS)."""
    clean = [
        {"label": str(s.get("label") or ""), "value": float(s.get("value") or 0)}
        for s in slices
        if float(s.get("value") or 0) > 0
    ]
    total = sum(s["value"] for s in clean)
    if total <= 0:
        return (
            f'<div class="chart"><h3>{_esc(title)}</h3>'
            f'<p class="muted">Sin datos</p></div>'
        )

    cx = cy = size / 2
    r = size * 0.38
    angle = -math.pi / 2
    paths: list[str] = []
    legend: list[str] = []
    for i, s in enumerate(clean):
        frac = s["value"] / total
        sweep = frac * 2 * math.pi
        x1 = cx + r * math.cos(angle)
        y1 = cy + r * math.sin(angle)
        angle2 = angle + sweep
        x2 = cx + r * math.cos(angle2)
        y2 = cy + r * math.sin(angle2)
        large = 1 if sweep > math.pi else 0
        color = _CHART_COLORS[i % len(_CHART_COLORS)]
        if len(clean) == 1:
            paths.append(
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{color}" />'
            )
        else:
            paths.append(
                f'<path d="M {cx:.1f} {cy:.1f} L {x1:.1f} {y1:.1f} '
                f'A {r:.1f} {r:.1f} 0 {large} 1 {x2:.1f} {y2:.1f} Z" fill="{color}" />'
            )
        pct = 100.0 * frac
        legend.append(
            f'<li><span class="swatch" style="background:{color}"></span>'
            f'{_esc(s["label"])} — {s["value"]:.0f} ({pct:.1f}%)</li>'
        )
        angle = angle2

    return (
        f'<div class="chart"><h3>{_esc(title)}</h3>'
        f'<svg viewBox="0 0 {size} {size}" width="{size}" height="{size}" '
        f'role="img" aria-label="{_esc(title)}">{"".join(paths)}</svg>'
        f'<ul class="legend">{"".join(legend)}</ul></div>'
    )


def _esc(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render_iso_kpi_html(payload: dict[str, Any]) -> str:
    """HTML imprimible autocontenido (CSS inline + SVG)."""
    defs = payload.get("definitions") or []
    results = payload.get("results") or {}
    charts = payload.get("charts") or []
    totals = payload.get("totals") or {}
    generated = payload.get("generated_at") or ""
    app = payload.get("app") or "Control de Fletes"

    rows = []
    for d in defs:
        kid = d.get("id", "")
        r = results.get(kid) or {}
        display = r.get("display", "—")
        unit = r.get("unit") or ""
        val = f"{display} {unit}".strip()
        rows.append(
            "<tr>"
            f"<td>{_esc(kid)}</td>"
            f"<td>{_esc(d.get('stage', ''))}</td>"
            f"<td><strong>{_esc(d.get('name', ''))}</strong><br>"
            f"<span class='muted'>{_esc(d.get('objective', ''))}</span></td>"
            f"<td>{_esc(d.get('formula', ''))}</td>"
            f"<td class='val'>{_esc(val)}</td>"
            f"<td>{_esc(r.get('note', ''))}</td>"
            f"<td>{_esc(d.get('iso', ''))}</td>"
            "</tr>"
        )

    charts_html = "".join(
        render_pie_svg(c.get("slices") or [], c.get("title") or "Gráfico")
        for c in charts
    )

    tot_bits = " · ".join(
        f"{_esc(str(k))}: <strong>{_esc(str(v))}</strong>" for k, v in totals.items()
    )

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8"/>
<title>KPI ISO 9001 — {_esc(app)}</title>
<style>
  :root {{ --ink:#0f172a; --muted:#64748b; --line:#e2e8f0; --bg:#f8fafc; --card:#fff; }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: "Segoe UI", Calibri, Arial, sans-serif;
    color: var(--ink); background: var(--bg); margin: 0; padding: 24px;
    font-size: 13px; line-height: 1.45;
  }}
  header {{
    background: var(--card); border: 1px solid var(--line); border-radius: 8px;
    padding: 18px 22px; margin-bottom: 18px;
  }}
  h1 {{ margin: 0 0 6px; font-size: 1.45rem; }}
  h2 {{ font-size: 1.1rem; margin: 22px 0 10px; }}
  .muted {{ color: var(--muted); font-size: 0.92em; }}
  .totals {{ margin-top: 8px; }}
  table {{
    width: 100%; border-collapse: collapse; background: var(--card);
    border: 1px solid var(--line); border-radius: 8px; overflow: hidden;
  }}
  th, td {{ border-bottom: 1px solid var(--line); padding: 8px 10px; vertical-align: top; text-align: left; }}
  th {{ background: #eef2ff; font-size: 0.85rem; text-transform: uppercase; letter-spacing: .02em; }}
  td.val {{ font-weight: 700; white-space: nowrap; font-size: 1.05rem; }}
  .charts {{
    display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 14px; margin-top: 8px;
  }}
  .chart {{
    background: var(--card); border: 1px solid var(--line); border-radius: 8px;
    padding: 12px 14px;
  }}
  .chart h3 {{ margin: 0 0 8px; font-size: 0.95rem; }}
  .chart svg {{ display: block; margin: 0 auto; }}
  .legend {{ list-style: none; padding: 0; margin: 10px 0 0; }}
  .legend li {{ margin: 3px 0; font-size: 0.88rem; }}
  .swatch {{
    display: inline-block; width: 10px; height: 10px; border-radius: 2px;
    margin-right: 6px; vertical-align: middle;
  }}
  footer {{ margin-top: 22px; color: var(--muted); font-size: 0.85rem; }}
  @media print {{
    body {{ background: #fff; padding: 0; }}
    header, .chart, table {{ border-color: #ccc; box-shadow: none; }}
    .chart {{ break-inside: avoid; }}
  }}
</style>
</head>
<body>
<header>
  <h1>Informe KPI ISO 9001 — {_esc(app)}</h1>
  <div class="muted">Dominio: logística de fletes (casos / remitos Tango). Generado: {_esc(generated)}</div>
  <div class="totals">{tot_bits}</div>
</header>

<h2>Tabla de control de KPIs</h2>
<table>
  <thead>
    <tr>
      <th>ID</th><th>Etapa</th><th>Indicador</th><th>Fórmula</th>
      <th>Valor</th><th>Nota</th><th>Cláusula ISO</th>
    </tr>
  </thead>
  <tbody>
    {''.join(rows)}
  </tbody>
</table>

<h2>Gráficos de distribución</h2>
<div class="charts">
{charts_html}
</div>

<footer>
  Documento de control interno — patrón KPI ISO compartido entre apps TOP.
  Los KPIs 6 y 7 quedan sin dato hasta incorporar encuesta/CSAT al dominio Fletes.
</footer>
</body>
</html>
"""
