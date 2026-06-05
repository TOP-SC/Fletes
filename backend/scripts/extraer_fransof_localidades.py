"""Extrae localidades FRANSOF desde tarifario Mantello (hoja fransof)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "fransof_localidades.json"

# Zonas según localidades fransof.xlsx (imagen embebida)
ZONAS_IMAGEN: dict[str, int] = {
    "ROSARIO": 1,
    "GRANADERO BAIGORRIA": 1,
    "VILLA GOBERNADOR GALVEZ": 1,
    "CAPITAN BERMUDEZ": 2,
    "FRAY LUIS BELTRAN": 2,
    "SAN LORENZO": 2,
    "PUERTO GENERAL SAN MARTIN": 2,
    "PUEBLO ESTHER": 3,
    "PEREZ": 3,
    "SOLDINI": 3,
    "ESPERANZA": 4,
    "FRANCK": 4,
    "BELLA ITALIA": 4,
    "RAFAELA": 4,
    "FRONTERA": 4,
    "SAN FRANCISCO": 4,
    "FUNES": 5,
    "ROLDAN": 5,
    "IBARLUCEA": 5,
    "AROCENA": 6,
    "CORONDA": 6,
    "DESVIO ARIJON": 6,
    "SAUCE VIEJO": 6,
    "SANTO TOME": 6,
    "SANTA FE": 6,
    "RECREO": 6,
    "PARANA": 7,
}

ALIAS: dict[str, list[str]] = {
    "GRANADERO BAIGORRIA": ["GDRO BAIGORRIA", "GDRO.BAIGORRIA"],
    "VILLA GOBERNADOR GALVEZ": ["VILLA GDOR GALVEZ", "VILLA GDOR. GALVEZ"],
    "FRANCK": ["FRANK"],
    "DESVIO ARIJON": ["DESVIO ARIJON", "DESVÍO ARIJON"],
}

PROVINCIA_POR_LOCALIDAD: dict[str, str] = {
    "SAN FRANCISCO": "Córdoba",
    "PARANA": "Entre Ríos",
}

BASURA = {
    "CAMA CAJON / SOFA CAMA / BASE DIVAN",
    "NUEVAS LOCALIDADES PARA ENTREGAS DE MERCADERIA",
    "LUNES",
}


def _norm(s: str) -> str:
    t = (s or "").strip().upper()
    for a, b in [("Á", "A"), ("É", "E"), ("Í", "I"), ("Ó", "O"), ("Ú", "U"), ("Ñ", "N")]:
        t = t.replace(a, b)
    t = re.sub(r"\s+", " ", t)
    return t


def _limpiar_nombre(raw: str) -> str | None:
    s = _norm(raw)
    if not s or s in BASURA or s.isdigit():
        return None
    s = re.sub(r"\s*\([^)]*\)\s*", " ", s).strip()
    s = re.sub(r"\s+", " ", s)
    if not s or s in BASURA:
        return None
    return s


def _leer_tarifario(path: Path) -> list[str]:
    df = pd.read_excel(path, sheet_name="fransof", header=None)
    out: list[str] = []
    for i in range(1, len(df)):
        loc = _limpiar_nombre(str(df.iloc[i, 0]))
        if loc:
            out.append(loc)
    return out


def main() -> None:
    tarifario = Path(
        r"s:\Administración\TOP\LOG -  Envios Fletes 200326"
        r"\TARIFARIOS INTERIOR y FLETES SUC 2026 (1).xlsx"
    )
    if len(sys.argv) > 1:
        tarifario = Path(sys.argv[1])

    nombres = set(ZONAS_IMAGEN)
    if tarifario.exists():
        nombres.update(_leer_tarifario(tarifario))

    items = []
    for nombre in sorted(nombres, key=lambda x: (ZONAS_IMAGEN.get(x, 99), x)):
        prov = PROVINCIA_POR_LOCALIDAD.get(nombre, "Santa Fe")
        items.append(
            {
                "nombre": nombre,
                "provincia": prov,
                "zona": ZONAS_IMAGEN.get(nombre),
                "alias": ALIAS.get(nombre, []),
            }
        )

    payload = {
        "proveedor": "FRANSOF",
        "notas": (
            "Cobertura FRANSOF por localidad (principalmente Santa Fe). "
            "Fuente: localidades fransof.xlsx + hoja fransof del tarifario."
        ),
        "localidades": items,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Escrito {OUT} — {len(items)} localidades")


if __name__ == "__main__":
    main()
