from fastapi import APIRouter, Depends, Header, HTTPException
from datetime import datetime
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps_auth import get_current_user, require_super_admin
from app.database import get_db
from app.models import AppUser
from app.services.auth_service import (
    authenticate,
    change_own_password,
    create_session,
    create_user,
    delete_user,
    list_users,
    revoke_session,
    revoke_user_sessions,
    set_password,
    update_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str
    password: str


class LoginOut(BaseModel):
    token: str
    username: str
    is_super_admin: bool


class UserOut(BaseModel):
    username: str
    is_super_admin: bool
    activo: bool
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class UserCreateIn(BaseModel):
    username: str = Field(min_length=2, max_length=40)
    password: str = Field(min_length=6, max_length=120)
    is_super_admin: bool = False


class UserUpdateIn(BaseModel):
    is_super_admin: bool | None = None
    activo: bool | None = None
    password: str | None = Field(default=None, min_length=6, max_length=120)


class PasswordIn(BaseModel):
    password: str = Field(min_length=6, max_length=120)


class ChangeOwnPasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=120)
    new_password: str = Field(min_length=6, max_length=120)


@router.post("/login", response_model=LoginOut)
def login(body: LoginIn, db: Session = Depends(get_db)) -> LoginOut:
    user = authenticate(db, body.username, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")
    token = create_session(db, user)
    return LoginOut(token=token, username=user.username, is_super_admin=user.is_super_admin)


@router.post("/logout")
def logout(
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    if x_auth_token:
        revoke_session(db, x_auth_token)
    return {"message": "Sesión cerrada"}


@router.get("/me", response_model=UserOut)
def me(user: AppUser = Depends(get_current_user)) -> UserOut:
    return user


@router.post("/me/password")
def cambiar_mi_password(
    body: ChangeOwnPasswordIn,
    user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    try:
        change_own_password(db, user.username, body.current_password, body.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"message": "Contraseña actualizada. Volvé a iniciar sesión."}


@router.get("/usuarios", response_model=list[UserOut])
def usuarios(_admin: AppUser = Depends(require_super_admin), db: Session = Depends(get_db)) -> list[UserOut]:
    return list_users(db)


@router.post("/usuarios", response_model=UserOut)
def alta_usuario(
    body: UserCreateIn,
    _admin: AppUser = Depends(require_super_admin),
    db: Session = Depends(get_db),
) -> UserOut:
    try:
        return create_user(
            db,
            body.username,
            body.password,
            is_super_admin=body.is_super_admin,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/usuarios/{username}", response_model=UserOut)
def editar_usuario(
    username: str,
    body: UserUpdateIn,
    admin: AppUser = Depends(require_super_admin),
    db: Session = Depends(get_db),
) -> UserOut:
    if body.is_super_admin is None and body.activo is None and body.password is None:
        raise HTTPException(status_code=400, detail="No hay cambios para aplicar")
    try:
        return update_user(
            db,
            username,
            is_super_admin=body.is_super_admin,
            activo=body.activo,
            password=body.password,
            acting_username=admin.username,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/usuarios/{username}/cerrar-sesiones")
def cerrar_sesiones_usuario(
    username: str,
    _admin: AppUser = Depends(require_super_admin),
    db: Session = Depends(get_db),
) -> dict[str, str | int]:
    uname = username.strip().lower()
    if db.query(AppUser).filter(AppUser.username == uname).first() is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    n = revoke_user_sessions(db, uname)
    return {"message": f"Sesiones cerradas para {uname}", "cerradas": n}


@router.delete("/usuarios/{username}")
def baja_usuario(
    username: str,
    _admin: AppUser = Depends(require_super_admin),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    try:
        delete_user(db, username)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"message": f"Usuario {username.strip().lower()} eliminado"}


@router.put("/usuarios/{username}/password")
def cambiar_password(
    username: str,
    body: PasswordIn,
    _admin: AppUser = Depends(require_super_admin),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    try:
        set_password(db, username, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"message": "Contraseña actualizada"}
