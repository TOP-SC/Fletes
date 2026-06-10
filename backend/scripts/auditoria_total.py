"""Auditoría intensiva post-import Tango + km reales."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

DB = ROOT / "data" / "fletes.db"


def main() -> None:
    if not DB.exists():
        print("ERROR: no existe fletes.db")
        return

    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row

    def q1(sql: str, params=()):
        return c.execute(sql, params).fetchone()[0]

    def qall(sql: str, params=()):
        return c.execute(sql, params).fetchall()

    total = q1("SELECT COUNT(*) FROM envios")
    print("=== ENVIOS ===")
    print(f"total={total}")

    # imports
    try:
        batches = qall(
            "SELECT id, source, filename, created_at, row_count FROM import_batches ORDER BY id DESC LIMIT 15"
        )
        print(f"\n=== IMPORT BATCHES ({len(batches)} recientes) ===")
        for b in batches:
            print(dict(b))
        print(f"total_batches={q1('SELECT COUNT(*) FROM import_batches')}")
    except sqlite3.OperationalError:
        print("sin tabla import_batches")

    print("\n=== CLASIFICACION ===")
    print(f"amba_excluir={q1('SELECT COUNT(*) FROM envios WHERE excluir_planilla=1')}")
    print(f"interior={q1('SELECT COUNT(*) FROM envios WHERE excluir_planilla=0 OR excluir_planilla IS NULL')}")
    print(f"con_costo={q1('SELECT COUNT(*) FROM envios WHERE costo_tarifario IS NOT NULL AND costo_tarifario>0')}")
    print(f"prefactura={q1('SELECT COUNT(*) FROM envios WHERE prefactura_proveedor IS NOT NULL')}")
    print("macheo_ok=" + str(q1("SELECT COUNT(*) FROM envios WHERE macheo_estado='ok'")))
    print(f"elegir_prov={q1('SELECT COUNT(*) FROM envios WHERE requiere_elegir_proveedor=1')}")

    print("\n=== COLORES ===")
    for row in qall("SELECT regla_color, COUNT(*) n FROM envios GROUP BY regla_color ORDER BY n DESC"):
        print(f"  {row[0] or 'null'}: {row[1]}")

    print("\n=== DEPOSITO ===")
    for row in qall(
        "SELECT COALESCE(deposito,'(vacío)') d, COUNT(*) n FROM envios GROUP BY deposito ORDER BY n DESC LIMIT 8"
    ):
        print(f"  {row[0]}: {row[1]}")

    print("\n=== TRANSPORTE TOP (AMBA) ===")
    for row in qall(
        """SELECT transporte_nombre, COUNT(*) n FROM envios
           WHERE excluir_planilla=1 GROUP BY transporte_nombre ORDER BY n DESC LIMIT 8"""
    ):
        print(f"  {row[0]}: {row[1]}")

    print("\n=== FLETE_DISTANCIAS ===")
    n_dist = q1("SELECT COUNT(*) FROM flete_distancias")
    n_km = q1("SELECT COUNT(*) FROM flete_distancias WHERE distance_km IS NOT NULL")
    n_zona = q1("SELECT COUNT(*) FROM flete_distancias WHERE zona_km IS NOT NULL")
    n_fp = q1("SELECT COUNT(*) FROM flete_distancias WHERE domicilio_fp IS NOT NULL")
    n_ped = q1("SELECT COUNT(*) FROM flete_distancias WHERE remito_norm LIKE 'pedido-%'")
    n_preview = q1(
        "SELECT COUNT(*) FROM flete_distancias WHERE km_provider LIKE '%preview%' OR km_provider LIKE '%estimado%'"
    )
    n_real = q1(
        """SELECT COUNT(*) FROM flete_distancias WHERE distance_km IS NOT NULL
           AND (km_provider IS NULL OR (km_provider NOT LIKE '%preview%' AND km_provider NOT LIKE '%estimado%'))"""
    )
    n_reuso = q1("SELECT COUNT(*) FROM flete_distancias WHERE km_provider LIKE '%reuso_domicilio%'")
    print(f"filas_cache={n_dist} con_km={n_km} con_zona={n_zona}")
    print(f"km_reales={n_real} estimados_preview={n_preview} reuso_domicilio={n_reuso}")
    print(f"domicilio_fp={n_fp} clave_pedido={n_ped}")

    print("\n=== KM PROVIDER TOP ===")
    for row in qall(
        """SELECT substr(km_provider,1,40) p, COUNT(*) n FROM flete_distancias
           GROUP BY substr(km_provider,1,40) ORDER BY n DESC LIMIT 8"""
    ):
        print(f"  {row[0]}: {row[1]}")

    print("\n=== SUCURSAL ASIGNADA (cache) ===")
    for row in qall(
        "SELECT sucursal_cod, COUNT(*) n FROM flete_distancias WHERE sucursal_cod IS NOT NULL GROUP BY sucursal_cod ORDER BY n DESC LIMIT 12"
    ):
        print(f"  {row[0]}: {row[1]}")

    # Mundo2 casos sin km en cache
    print("\n=== AMBA SIN CACHE KM (muestra) ===")
    sin_km = q1(
        """SELECT COUNT(DISTINCT COALESCE(remito_norm, nro_pedido, CAST(id AS TEXT)))
           FROM envios e WHERE excluir_planilla=1
           AND NOT EXISTS (
             SELECT 1 FROM flete_distancias f
             WHERE f.remito_norm = e.remito_norm
                OR f.remito_norm = 'pedido-' || e.nro_pedido
           )"""
    )
    print(f"casos_amba_sin_cache_aprox={sin_km}")

    # Simular grilla fletes via API code
    try:
        from app.database import SessionLocal, init_db
        from app.models import Envio
        from app.services.fletes_km_service import mapa_distancias, preparar_contexto_km
        from app.services.mundo2_service import construir_fletes, es_envio_mundo2
        from app.services.tarifario_version_service import TarifarioContext
        from sqlalchemy import select

        init_db()
        db = SessionLocal()
        envios = list(db.scalars(select(Envio)).all())
        m2 = [e for e in envios if es_envio_mundo2(e)]
        dist = mapa_distancias(db)
        filas = construir_fletes(m2, tarifario_ctx=TarifarioContext(db), db=db, distancias=dist)
        con_suc = sum(1 for f in filas if f.get("SUCURSAL"))
        con_km = sum(1 for f in filas if f.get("KM"))
        con_zona = sum(1 for f in filas if f.get("ZONA KM"))
        con_total = sum(1 for f in filas if f.get("total"))
        alerta = sum(1 for f in filas if f.get("_regla_color") == "alerta")
        amarillo = sum(1 for f in filas if f.get("_regla_color") == "amarillo")
        verde = sum(1 for f in filas if f.get("_regla_color") == "verde")
        print("\n=== GRILLA FLETES (simulada) ===")
        print(f"casos={len(filas)} sucursal={con_suc} km={con_km} zona={con_zona} total={con_total}")
        print(f"colores: alerta={alerta} amarillo={amarillo} verde={verde}")
        db.close()
    except Exception as exc:
        print(f"\ngrilla sim error: {exc}")

    print("\n=== AMBA PENDIENTES DETALLE ===")
    print("retiro_amba=" + str(q1("SELECT COUNT(*) FROM envios WHERE excluir_planilla=1 AND UPPER(transporte_nombre) LIKE '%RETIR%'")))
    print("sin_domicilio_amba=" + str(q1("SELECT COUNT(*) FROM envios WHERE excluir_planilla=1 AND (domicilio IS NULL OR TRIM(domicilio)='')")))
    print("con_domicilio_sin_cache=" + str(q1(
        """SELECT COUNT(*) FROM envios e WHERE excluir_planilla=1
           AND TRIM(COALESCE(domicilio,''))!=''
           AND UPPER(transporte_nombre) NOT LIKE '%RETIR%'
           AND NOT EXISTS (SELECT 1 FROM flete_distancias f
             WHERE f.remito_norm=e.remito_norm OR f.remito_norm='pedido-'||e.nro_pedido)"""
    )))

    print("\n=== MAESTRO SIM ===")
    try:
        from app.services.maestro_service import construir_maestro
        from app.services.tarifario_version_service import TarifarioContext
        from app.database import SessionLocal, init_db
        from app.models import Envio
        from sqlalchemy import select

        init_db()
        db = SessionLocal()
        envios = list(db.scalars(select(Envio)).all())
        filas = construir_maestro(envios, tarifario_ctx=TarifarioContext(db), db=db, incluir_excluidos=True)
        from collections import Counter
        col = Counter(f.get("_regla_color") for f in filas)
        print(f"casos={len(filas)} colores={dict(col)}")
        print(f"con_logistica={sum(1 for f in filas if float(f.get('LOGISTICA') or 0)>0)}")
        db.close()
    except Exception as exc:
        print(f"maestro error: {exc}")

    print(f"\ntarifas={q1('SELECT COUNT(*) FROM tarifas')}")
    c.close()


if __name__ == "__main__":
    main()
