"""
Una sola vez: conectar Google Drive con tu mail @sommiercenter.com.

Así la app baja Cross 3/4 sin pedir «Cualquiera con el enlace»
(usa tu acceso de grupo SommierCenter).

Pasos previos (Google Cloud Console, ~5 min):
  1. https://console.cloud.google.com/ → proyecto (nuevo o existente)
  2. APIs y servicios → Biblioteca → «Google Drive API» → Habilitar
  3. Pantalla de consentimiento OAuth → Interno (Workspace) → scopes Drive readonly
  4. Credenciales → Crear credenciales → ID de cliente OAuth
     → Tipo: Aplicación de escritorio → Crear → Descargar JSON
  5. Guardar el JSON como:
       Fletes/data/google_oauth_client.json

Luego, en esta PC (con navegador):
  cd backend
  pip install google-auth google-auth-oauthlib google-auth-httplib2
  python scripts/google_oauth_setup.py

Abrí el navegador, entró con juan.billiot@sommiercenter.com (o el mail que tenga
acceso a las planillas), aceptá solo lectura de Drive.

Genera: data/google_oauth_token.json
Copiá ese archivo al server:
  scp data/google_oauth_token.json top@10.20.2.166:/opt/fletes/data/
  ssh top@10.20.2.166 "sudo systemctl restart fletes-api"

En la app: Configuración → Cross → debería decir «Google conectado».
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# backend/ es ROOT; data/ está en el repo (hermano de backend) o backend/data
DATA_CANDIDATES = [
    ROOT.parent / "data",
    ROOT / "data",
]
SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]


def _data_dir() -> Path:
    for d in DATA_CANDIDATES:
        if d.is_dir():
            return d
    d = ROOT.parent / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def main() -> int:
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("Instalá: pip install google-auth-oauthlib google-auth google-auth-httplib2")
        return 1

    data = _data_dir()
    client = data / "google_oauth_client.json"
    token = data / "google_oauth_token.json"

    if not client.is_file():
        print(f"Falta {client}")
        print()
        print("En Google Cloud Console:")
        print("  APIs → Credenciales → Crear OAuth cliente (Aplicación de escritorio)")
        print("Descargá el JSON y guardalo como data/google_oauth_client.json")
        return 1

    print("Se va a abrir el navegador. Entrá con tu mail @sommiercenter.com")
    print("(solo permiso de LECTURA de Drive — no modifica archivos).")
    print()
    flow = InstalledAppFlow.from_client_secrets_file(str(client), SCOPES)
    creds = flow.run_local_server(port=0)
    token.write_text(creds.to_json(), encoding="utf-8")
    print()
    print(f"OK → {token}")
    print()
    print("Siguiente: copiá el token al server y reiniciá la API:")
    print(f'  scp "{token}" top@10.20.2.166:/opt/fletes/data/google_oauth_token.json')
    print("  ssh top@10.20.2.166 \"sudo systemctl restart fletes-api\"")
    print()
    print("No hace falta cambiar permisos de Cross 3/4 en Drive.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
