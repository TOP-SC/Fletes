from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


# columnas agregadas después del v0.1 — SQLite no altera con create_all
_MIGRATIONS: dict[str, list[tuple[str, str]]] = {
    "import_batches": [("source", "VARCHAR(40) DEFAULT 'tango'")],
    "envios": [
        ("remito_norm", "VARCHAR(40)"),
        ("origen_cd", "VARCHAR(40)"),
        ("entrega_cliente_sospechosa", "BOOLEAN DEFAULT 0"),
        ("macheo_estado", "VARCHAR(30)"),
        ("prefactura_clickpac_id", "INTEGER"),
        ("postventa_id", "INTEGER"),
        ("motivo_postventa", "VARCHAR(120)"),
        ("regla_postventa", "VARCHAR(80)"),
        ("tipo_gestion", "VARCHAR(80)"),
        ("sub_tipo_gestion", "VARCHAR(80)"),
        ("proveedor_tarifa", "VARCHAR(40)"),
        ("proveedores_candidatos", "TEXT"),
        ("requiere_elegir_proveedor", "BOOLEAN DEFAULT 0"),
        ("fecha_pedido_d", "DATE"),
        ("fecha_entrega_d", "DATE"),
        ("cedol_codigo", "VARCHAR(8)"),
        ("cedol_manual", "BOOLEAN DEFAULT 0"),
        ("cod_cliente", "VARCHAR(40)"),
    ],
    "tarifas": [("cedol", "VARCHAR(40)"), ("version_id", "INTEGER")],
    "flete_distancias": [("domicilio_fp", "VARCHAR(64)")],
}


def _migrate_schema() -> None:
    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())
    with engine.begin() as conn:
        for table, cols in _MIGRATIONS.items():
            if table not in existing_tables:
                continue
            existing_cols = {c["name"] for c in insp.get_columns(table)}
            for col_name, col_def in cols:
                if col_name not in existing_cols:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}"))
        if "tarifas" in existing_tables:
            conn.execute(
                text(
                    "UPDATE tarifas SET proveedor='CLICPAQ' "
                    "WHERE UPPER(proveedor) IN ('CLICKPAC','CLICKPACK','CLICKPAQ')"
                )
            )
            conn.execute(
                text("UPDATE tarifas SET proveedor='FRANSOF' WHERE UPPER(proveedor)='FRANOV'")
            )
        if "envios" in existing_tables and "fecha_pedido_d" in {
            c["name"] for c in insp.get_columns("envios")
        }:
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_envios_fecha_pedido_d "
                    "ON envios (fecha_pedido_d)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_envios_fecha_entrega_d "
                    "ON envios (fecha_entrega_d)"
                )
            )


def _backfill_fechas_d() -> None:
    from app.services.envio_query_service import backfill_fechas_envios

    total = 0
    with SessionLocal() as db:
        while True:
            n = backfill_fechas_envios(db, limit=5000)
            total += n
            if n < 5000:
                break
    if total:
        print(f"[fletes] Fechas indexadas en envios: {total} filas")


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_schema()
    _backfill_fechas_d()
