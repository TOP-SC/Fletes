"""Autenticación Google Drive para planillas Cross (sin cambiar permisos de los Sheets).

Prioridad:
  1. OAuth usuario (token en data/google_oauth_token.json)
     → ve lo mismo que ese @sommiercenter.com (grupo SommierCenter incluido)
  2. Service Account (opcional; habría que compartir cada archivo con el robot)
  3. Anónimo (export público) — solo planillas «Cualquiera con el enlace»

Setup OAuth (una vez, en tu PC):
  1. Google Cloud Console → proyecto → habilitar «Google Drive API»
  2. Pantalla de consentimiento OAuth: tipo **Interna** (Workspace SommierCenter)
  3. Credenciales → Crear → ID de cliente OAuth → **Aplicación de escritorio**
  4. Descargar JSON → ``data/google_oauth_client.json``
  5. ``python backend/scripts/google_oauth_setup.py``  (entrar con tu mail)
  6. Copiar ``data/google_oauth_token.json`` al server ``/opt/fletes/data/``
  7. Reiniciar fletes-api
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import DATA_DIR, settings

_SCOPES = (
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
)
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


def _oauth_email_from_token(creds) -> str | None:
    """Best-effort: mail del usuario OAuth (para mostrar en UI)."""
    try:
        import httpx
        from google.auth.transport.requests import Request

        if not creds.valid:
            creds.refresh(Request())
        token = creds.token
        if not token:
            return None
        r = httpx.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15.0,
        )
        if r.status_code == 200:
            return (r.json() or {}).get("email")
    except Exception:
        return None
    return None


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
        "oauth_user_email": None,
        "oauth_token_valido": False,
        "modo_preferido": "anonimo",
        "puede_leer_grupo_sommier": False,
        "mensaje": (
            "Sin Google conectado: solo baja planillas públicas "
            "(«Cualquiera con el enlace»). Cross 3/4 del grupo SommierCenter fallan."
        ),
    }
    try:
        creds = _creds_oauth()
        if creds:
            out["modo_preferido"] = "oauth_usuario"
            out["oauth_token_valido"] = True
            out["puede_leer_grupo_sommier"] = True
            out["oauth_user_email"] = _oauth_email_from_token(creds)
            mail = out["oauth_user_email"] or "(usuario Google)"
            out["mensaje"] = (
                f"Google conectado como {mail}. "
                "Actualizar usa esa cuenta (lee lo del grupo SommierCenter)."
            )
            return out
    except Exception as exc:
        out["mensaje"] = f"Token OAuth presente pero inválido: {exc}"

    if oa.is_file() and not out["oauth_token_valido"]:
        out["modo_preferido"] = "oauth_usuario"
        out["mensaje"] = (
            "Hay google_oauth_token.json pero no es válido. "
            "Volvé a correr google_oauth_setup.py con tu mail @sommiercenter.com."
        )
        return out

    if sa.is_file():
        out["modo_preferido"] = "service_account"
        try:
            data = json.loads(sa.read_text(encoding="utf-8"))
            out["service_account_email"] = data.get("client_email")
        except Exception:
            pass
        out["mensaje"] = (
            f"Service account {out.get('service_account_email') or ''}: "
            "solo lee archivos compartidos explícitamente con ese mail robot."
        )
        return out

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

    export_url = f"https://www.googleapis.com/drive/v3/files/{file_id}/export"
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        r = client.get(
            export_url,
            params={**params_common, "mimeType": _XLSX_MIME},
            headers=headers,
        )
        if r.status_code == 200 and r.content[:2] == b"PK":
            return r.content, modo

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
                f"{file_id}. ¿Tu usuario Google tiene acceso de Lector a esa planilla? "
                f"{detail}"
            )

        detail = (r.text or "")[:300]
        raise ValueError(f"Drive auth HTTP {r.status_code}: {detail}")


def clear_drive_creds_cache() -> None:
    _cached_sa_email.cache_clear()
