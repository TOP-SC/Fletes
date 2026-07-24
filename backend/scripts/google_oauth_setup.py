"""
Una sola vez: autorizar Google Drive con un usuario SommierCenter (ej. TOP@…).

Uso (en una PC con navegador):
  pip install google-auth google-auth-oauthlib google-auth-httplib2
  # Descargá OAuth Client ID (Desktop) desde Google Cloud Console → credentials.json
  # en data/google_oauth_client.json
  python scripts/google_oauth_setup.py

Genera data/google_oauth_token.json — copiar al servidor en la misma ruta.
Ese token ve lo mismo que el usuario (grupo SommierCenter incluido).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CLIENT = DATA / "google_oauth_client.json"
TOKEN = DATA / "google_oauth_token.json"
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def main() -> int:
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("Instalá: pip install google-auth-oauthlib google-auth google-auth-httplib2")
        return 1
    if not CLIENT.is_file():
        print(f"Falta {CLIENT}")
        print("En Google Cloud Console: APIs → Credenciales → Crear OAuth cliente (Escritorio)")
        print("Descargá el JSON y guardalo como data/google_oauth_client.json")
        return 1
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT), SCOPES)
    creds = flow.run_local_server(port=0)
    TOKEN.write_text(creds.to_json(), encoding="utf-8")
    print(f"OK → {TOKEN}")
    print("Copiá este archivo al servidor (/opt/fletes/data/) y reiniciá fletes-api.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
