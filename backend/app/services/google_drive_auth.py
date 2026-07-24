"""Autenticación Google Drive para planillas Cross (sin «Cualquiera con el enlace»).

Prioridad:
  1. OAuth usuario (token guardado) — ve lo mismo que ese usuario/grupo SommierCenter
  2. Service Account — hay que compartir cada planilla con el mail ``…@….iam.gserviceaccount.com``
  3. Anónimo (export público) — fallback

Variables / archivos (prefijo env ``FLETES_``):
  - ``google_service_account_file`` → JSON de cuenta de servicio
    default: ``data/google_service_account.json``
  - ``google_oauth_token_file`` → token OAuth (script ``scripts/google_oauth_setup.py``)
    default: ``data/google_oauth_token.json``
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import DATA_DIR, settings

_SCOPES = ("https://www.googleapis.com/auth/drive.readonly",)
_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _path_sa() -> Path:
    raw = (getattr(settings, "google_service_account_file", None) or "").strip()
    if raw:
        p = Path(raw)
        return p if p.is_absolute() else (DATA_DIR / p)
    return DATA_DIR / "google_service_account.json"


def _path_oauth() -> Path:
    raw = (getattr(settings, "google_oauth_token_file", None) or "").strip()
    if raw:
        p = Path(raw)
        return p if p.is_absolute() else (DATA_DIR / p)
    return DATA_DIR / "google_oauth_token.json"


def drive_auth_status() -> dict[str, Any]:
    """Estado de credenciales (para UI / health)."""
    sa = _path_sa()
    oa = _path_oauth()
    out: dict[str, Any] = {
        "service_account_file": str(sa),
        "service_account_present": sa.is_file(),
        "service_account_email": None,
        "oauth_token_file": str(oa),
        "oauth_token_present": oa.is_file(),
        "modo_preferido": "anonimo",
    }
    if oa.is_file():
        out["modo_preferido"] = "oauth_usuario"
    elif sa.is_file():
        out["modo_preferido"] = "service_account"
        try:
            data = json.loads(sa.read_text(encoding="utf-8"))
            out["service_account_email"] = data.get("client_email")
        except Exception:
            pass
    return out


def _creds_oauth():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    path = _path_oauth()
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    creds = Credentials.from_authorized_user_info(data, scopes=list(_SCOPES))
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        path.write_text(creds.to_json(), encoding="utf-8")
    return creds if creds and creds.valid else None


def _creds_service_account():
    from google.oauth2 import service_account

    path = _path_sa()
    if not path.is_file():
        return None
    return service_account.Credentials.from_service_account_file(
        str(path), scopes=list(_SCOPES)
    )


@lru_cache(maxsize=1)
def _cached_sa_email() -> str | None:
    st = drive_auth_status()
    return st.get("service_account_email")


def get_drive_credentials():
    """Credenciales válidas o None (usar anónimo)."""
    try:
        creds = _creds_oauth()
        if creds:
            return creds, "oauth_usuario"
    except Exception:
        pass
    try:
        creds = _creds_service_account()
        if creds:
            return creds, "service_account"
    except Exception:
        pass
    return None, "anonimo"


def _bearer_token(creds) -> str:
    from google.auth.transport.requests import Request

    if not creds.valid:
        creds.refresh(Request())
    if not creds.token:
        raise ValueError("Google Drive: no se obtuvo access token")
    return str(creds.token)


def descargar_xlsx_autenticado(
    file_id: str,
    *,
    timeout: float = 300.0,
) -> tuple[bytes, str]:
    """
    Descarga un Google Sheet / archivo Drive como .xlsx con credenciales.
    Devuelve (bytes, modo_auth).
    """
    import httpx

    creds, modo = get_drive_credentials()
    if creds is None:
        raise ValueError("Sin credenciales Google configuradas")

    token = _bearer_token(creds)
    headers = {"Authorization": f"Bearer {token}"}
    params_common = {"supportsAllDrives": "true"}

    # 1) Export Sheets → xlsx
    export_url = f"https://www.googleapis.com/drive/v3/files/{file_id}/export"
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        r = client.get(
            export_url,
            params={**params_common, "mimeType": _XLSX_MIME},
            headers=headers,
        )
        if r.status_code == 200 and r.content[:2] == b"PK":
            return r.content, modo

        # 2) Archivo binario ya subido como xlsx
        if r.status_code in (403, 400):
            r2 = client.get(
                f"https://www.googleapis.com/drive/v3/files/{file_id}",
                params={**params_common, "alt": "media"},
                headers=headers,
            )
            if r2.status_code == 200 and r2.content[:2] == b"PK":
                return r2.content, modo
            detail = (r2.text or r.text or "")[:300]
            raise ValueError(
                f"Drive auth HTTP {r2.status_code}: no se pudo exportar "
                f"{file_id}. ¿Compartida la planilla con la cuenta de servicio? "
                f"{detail}"
            )

        detail = (r.text or "")[:300]
        raise ValueError(f"Drive auth HTTP {r.status_code}: {detail}")


def clear_drive_creds_cache() -> None:
    _cached_sa_email.cache_clear()
