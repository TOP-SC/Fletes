"""Autenticación local — usuarios de la app Streamlit."""

from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import AppUser, AuthSession

SUPER_ADMIN_USERNAME = "top"
SUPER_ADMIN_DEFAULT_PASSWORD = "Mafalda.2026"
SESSION_TTL_DAYS = 7
_PBKDF2_ITERS = 260_000
_USERNAME_RE = re.compile(r"^[a-zA-Z0-9._-]{2,40}$")


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), _PBKDF2_ITERS
    )
    return f"pbkdf2_sha256${_PBKDF2_ITERS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters_s, salt, digest_hex = stored.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        iters = int(iters_s)
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("utf-8"), iters
        )
        return secrets.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def ensure_super_admin(db: Session) -> None:
    user = db.query(AppUser).filter(AppUser.username == SUPER_ADMIN_USERNAME).first()
    if user is None:
        db.add(
            AppUser(
                username=SUPER_ADMIN_USERNAME,
                password_hash=hash_password(SUPER_ADMIN_DEFAULT_PASSWORD),
                is_super_admin=True,
                activo=True,
            )
        )
        db.commit()
        return
    changed = False
    if not user.is_super_admin:
        user.is_super_admin = True
        changed = True
    if not user.activo:
        user.activo = True
        changed = True
    if changed:
        db.commit()


def authenticate(db: Session, username: str, password: str) -> AppUser | None:
    uname = (username or "").strip().lower()
    user = db.query(AppUser).filter(AppUser.username == uname, AppUser.activo.is_(True)).first()
    if user is None or not verify_password(password, user.password_hash):
        return None
    return user


def create_session(db: Session, user: AppUser) -> str:
    token = secrets.token_urlsafe(48)
    expires = datetime.utcnow() + timedelta(days=SESSION_TTL_DAYS)
    db.add(AuthSession(token=token, username=user.username, expires_at=expires))
    db.commit()
    return token


def revoke_session(db: Session, token: str) -> None:
    row = db.query(AuthSession).filter(AuthSession.token == token).first()
    if row:
        db.delete(row)
        db.commit()


def get_user_by_token(db: Session, token: str | None) -> AppUser | None:
    if not token:
        return None
    now = datetime.utcnow()
    session = (
        db.query(AuthSession)
        .filter(AuthSession.token == token, AuthSession.expires_at > now)
        .first()
    )
    if session is None:
        return None
    return (
        db.query(AppUser)
        .filter(AppUser.username == session.username, AppUser.activo.is_(True))
        .first()
    )


def list_users(db: Session) -> list[AppUser]:
    return db.query(AppUser).order_by(AppUser.username).all()


def create_user(db: Session, username: str, password: str, *, is_super_admin: bool = False) -> AppUser:
    uname = username.strip().lower()
    if not _USERNAME_RE.match(uname):
        raise ValueError("Usuario inválido (2–40 caracteres: letras, números, . _ -)")
    if len(password or "") < 6:
        raise ValueError("La contraseña debe tener al menos 6 caracteres")
    if db.query(AppUser).filter(AppUser.username == uname).first():
        raise ValueError(f"El usuario «{uname}» ya existe")
    user = AppUser(
        username=uname,
        password_hash=hash_password(password),
        is_super_admin=is_super_admin,
        activo=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def delete_user(db: Session, username: str) -> None:
    uname = username.strip().lower()
    if uname == SUPER_ADMIN_USERNAME:
        raise ValueError("No se puede eliminar al super administrador")
    user = db.query(AppUser).filter(AppUser.username == uname).first()
    if user is None:
        raise ValueError("Usuario no encontrado")
    db.query(AuthSession).filter(AuthSession.username == uname).delete()
    db.delete(user)
    db.commit()


def revoke_user_sessions(db: Session, username: str) -> int:
    """Cierra todas las sesiones de un usuario (p. ej. tras cambio de clave)."""
    uname = username.strip().lower()
    n = db.query(AuthSession).filter(AuthSession.username == uname).delete()
    db.commit()
    return n


def set_password(db: Session, username: str, password: str) -> None:
    if len(password or "") < 6:
        raise ValueError("La contraseña debe tener al menos 6 caracteres")
    user = db.query(AppUser).filter(AppUser.username == username.strip().lower()).first()
    if user is None:
        raise ValueError("Usuario no encontrado")
    user.password_hash = hash_password(password)
    db.commit()
    revoke_user_sessions(db, user.username)


def change_own_password(db: Session, username: str, current_password: str, new_password: str) -> None:
    user = authenticate(db, username, current_password)
    if user is None:
        raise ValueError("La contraseña actual no es correcta")
    if len(new_password or "") < 6:
        raise ValueError("La nueva contraseña debe tener al menos 6 caracteres")
    user.password_hash = hash_password(new_password)
    db.commit()
    revoke_user_sessions(db, user.username)


def update_user(
    db: Session,
    username: str,
    *,
    is_super_admin: bool | None = None,
    activo: bool | None = None,
    password: str | None = None,
    acting_username: str | None = None,
) -> AppUser:
    uname = username.strip().lower()
    actor = (acting_username or "").strip().lower()
    user = db.query(AppUser).filter(AppUser.username == uname).first()
    if user is None:
        raise ValueError("Usuario no encontrado")

    if uname == SUPER_ADMIN_USERNAME:
        if is_super_admin is False:
            raise ValueError("No se puede quitar el rol super admin al usuario principal")
        if activo is False:
            raise ValueError("No se puede desactivar al super administrador principal")

    if actor and actor == uname:
        if is_super_admin is False:
            raise ValueError("No podés quitarte el rol de super administrador a vos mismo")
        if activo is False:
            raise ValueError("No podés desactivarte a vos mismo")

    if is_super_admin is False and user.is_super_admin:
        otros = (
            db.query(AppUser)
            .filter(AppUser.is_super_admin.is_(True), AppUser.activo.is_(True), AppUser.username != uname)
            .count()
        )
        if otros < 1:
            raise ValueError("Debe quedar al menos un super administrador activo")

    if is_super_admin is not None:
        user.is_super_admin = is_super_admin
    if activo is not None:
        user.activo = activo
        if not activo:
            revoke_user_sessions(db, uname)
    if password is not None:
        if len(password) < 6:
            raise ValueError("La contraseña debe tener al menos 6 caracteres")
        user.password_hash = hash_password(password)
        revoke_user_sessions(db, uname)

    db.commit()
    db.refresh(user)
    return user
