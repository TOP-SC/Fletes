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
    seguro_fijo: float = 3000.0
    gestion_retiro_pct: float = 0.25
    proveedor_interior_default: str = "CLICPAQ"


settings = Settings()
