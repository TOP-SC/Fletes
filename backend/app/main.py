from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    envios,
    importacion,
    maestro,
    mundo1,
    fletes,
    proveedores,
    sucursales,
    sistema,
    tarifas,
    transportes,
)
from app.config import settings
from app.database import init_db
from app.version import API_BUILD

app = FastAPI(
    title="Control de Fletes API",
    description="Backend para importación Tango, reglas Mundo 1/2 y tarifarios.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

prefix = settings.api_prefix
app.include_router(importacion.router, prefix=prefix)
app.include_router(envios.router, prefix=prefix)
app.include_router(tarifas.router, prefix=prefix)
app.include_router(mundo1.router, prefix=prefix)
app.include_router(fletes.router, prefix=prefix)
app.include_router(maestro.router, prefix=prefix)
app.include_router(proveedores.router, prefix=prefix)
app.include_router(sistema.router, prefix=prefix)
app.include_router(sucursales.router, prefix=prefix)
app.include_router(transportes.router, prefix=prefix)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    _seed_sucursales()
    _seed_transportes()
    _migrate_tarifario_versiones()


def _seed_transportes() -> None:
    from app.database import SessionLocal
    from app.services.transportes_service import sincronizar_transportes

    db = SessionLocal()
    try:
        sincronizar_transportes(db)
    finally:
        db.close()


def _migrate_tarifario_versiones() -> None:
    from app.database import SessionLocal
    from app.services.tarifario_version_service import migrate_legacy_tarifas

    db = SessionLocal()
    try:
        migrate_legacy_tarifas(db)
    finally:
        db.close()


def _seed_sucursales() -> None:
    from app.database import SessionLocal
    from app.services.sucursales_service import sincronizar_sucursales

    db = SessionLocal()
    try:
        sincronizar_sucursales(db)
    finally:
        db.close()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "build": API_BUILD}
