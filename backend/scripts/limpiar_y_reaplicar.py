"""
Limpia costos/proveedor calculados y reaplica reglas + tarifarios en todos los envíos.

Uso (desde backend/):
  python scripts/limpiar_y_reaplicar.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal
from app.services.import_service import reaplicar_todos_envios


def main() -> None:
    db = SessionLocal()
    try:
        stats = reaplicar_todos_envios(db)
        print("Reaplicación completa:")
        for k, v in stats.items():
            print(f"  {k}: {v}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
