from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
TARIFARIOS_DIR = DATA_DIR / "tarifarios"
DATA_DIR.mkdir(parents=True, exist_ok=True)
TARIFARIOS_DIR.mkdir(parents=True, exist_ok=True)

# Depósito Tango → origen / centro de costos (completar con códigos reales)
DEPOSITO_ORIGEN: dict[str, str] = {
    "14": "CD Tortuguitas",
    "12": "Limansky Hurlingham",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FLETES_")

    database_url: str = f"sqlite:///{DATA_DIR / 'fletes.db'}"
    api_prefix: str = "/api/v1"
    seguro_fijo: float = 30.0
    gestion_retiro_pct: float = 0.25
    proveedor_interior_default: str = "CLICPAQ"


settings = Settings()

# Planillas cross en Google Drive (lector con link). gid=0 exporta todo el libro.
CROSS_PLANILLAS_DRIVE: list[dict[str, str | bool]] = [
    {
        "label": "Salta",
        "sheet_id": "1kMpxRTNqRhL5N8zoMQ4sqcQmip1QRJVOfVESxc8rTRw",
        "gid": "0",
        "filename": "cross_salta.xlsx",
        "activo": True,
    },
    {
        "label": "Rosario Fransof",
        "sheet_id": "1clgfnzimfr2PxU3ZufA8gXfWBbTWr7SA0FGxxJ-xgRQ",
        "gid": "0",
        "filename": "cross_rosario.xlsx",
        "activo": True,
    },
    {
        "label": "Cross 1",
        "sheet_id": "1HfBEWOS3ZJo9LiiSjKy4kyoJVrx2AwkV-VOvTj0_Ei8",
        "gid": "0",
        "filename": "cross_1.xlsx",
        "activo": True,
    },
    {
        "label": "Cross 3",
        "sheet_id": "1w6nt8Cj8e8c3Zq-mHTgnZmSL3W5D5cws",
        "gid": "1438105487",
        "filename": "cross_3.xlsx",
        "activo": True,
    },
    {
        "label": "Cross 4",
        "sheet_id": "19iiy6FMoY1BqycjfDh8Rz4zB6T76PdWRAZHLRIN-hhQ",
        "gid": "1896747399",
        "filename": "cross_4.xlsx",
        "activo": True,
    },
]
