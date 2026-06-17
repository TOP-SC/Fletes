from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AppUser
from app.services.auth_service import get_user_by_token


def get_current_user(
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
    db: Session = Depends(get_db),
) -> AppUser:
    user = get_user_by_token(db, x_auth_token)
    if user is None:
        raise HTTPException(status_code=401, detail="Sesión inválida o expirada")
    return user


def require_super_admin(user: AppUser = Depends(get_current_user)) -> AppUser:
    if not user.is_super_admin:
        raise HTTPException(status_code=403, detail="Solo el super administrador")
    return user
