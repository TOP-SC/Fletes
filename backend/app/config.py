from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
TARIFARIOS_DIR = DATA_DIR / "tarifarios"
DATA_DIR.mkdir(parents=True, exist_ok=True)
TARIFARIOS_DIR.mkdir(parents=True, exist_ok=True)

# Depósito Tango → etiqueta operativa del CD de origen.
# 12 = Hurlingham: depósito Clicpaq; Limansky también despacha desde ahí (planilla «SA» / bloque Hurlingham).
# 14 = Tortuguitas: centro de distribución principal (planilla «Tortuguitas»).
DEPOSITO_CD_HURLINGHAM = "12"
DEPOSITO_CD_TORTUGUITAS = "14"

DEPOSITO_ORIGEN: dict[str, str] = {
    DEPOSITO_CD_TORTUGUITAS: "CD Tortuguitas",
    DEPOSITO_CD_HURLINGHAM: "CD Hurlingham (Clicpaq / Limansky)",
}

# Textos en origen_cd / depósito que identifican el CD Hurlingham cuando Tango no trae dep=12.
_ORIGEN_TEXTO_HURLINGHAM = (
    "HURLINGHAM",
    "LIMANSKY",
    "THAMES",
    "CD 12",
    "DEP 12",
    "DEPOSITO 12",
    "DEPÓSITO 12",
)
_ORIGEN_TEXTO_TORTUGUITAS = (
    "TORTUGUITAS",
    "CD 14",
    "DEP 14",
    "CENTRO DISTRIB",
    "CENTRO DE DISTRIB",
)


def texto_indica_cd_hurlingham(origen_cd: str | None) -> bool:
    u = (origen_cd or "").upper()
    return any(t in u for t in _ORIGEN_TEXTO_HURLINGHAM)


def texto_indica_cd_tortuguitas(origen_cd: str | None) -> bool:
    u = (origen_cd or "").upper()
    return any(t in u for t in _ORIGEN_TEXTO_TORTUGUITAS)


def clave_planilla_origen(deposito: str | None, origen_cd: str | None) -> str:
    """
    Clave interna para planillas Excel / KPI entregas:
      - ``tortuguitas`` → dep 14 / CD Tortuguitas
      - ``sa`` → dep 12 / CD Hurlingham (histórico «WAMARO SA»; Clicpaq + Limansky)
    """
    dep = (deposito or "").strip()
    if dep == DEPOSITO_CD_HURLINGHAM or texto_indica_cd_hurlingham(origen_cd):
        return "sa"
    if dep == DEPOSITO_CD_TORTUGUITAS or texto_indica_cd_tortuguitas(origen_cd):
        return "tortuguitas"
    return "tortuguitas"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FLETES_")

    database_url: str = f"sqlite:///{DATA_DIR / 'fletes.db'}"
    api_prefix: str = "/api/v1"
    seguro_fijo: float = 30.0
    gestion_retiro_pct: float = 0.25
    proveedor_interior_default: str = "CLICPAQ"


settings = Settings()

# KPI «entregas x mes» (Excel Adrián / Grateful FC):
# El informe histórico usa importes de FACTURAS del proveedor LOG, no prefacturas ni tarifario.
# Activar en True cuando exista la integración de facturas (origen a definir con Logística).
KPI_ENTREGAS_FUENTE_FACTURAS_ACTIVA: bool = False

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
