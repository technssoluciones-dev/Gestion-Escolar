from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import User

bearer = HTTPBearer(auto_error=False)
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def create_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.token_minutes)
    return jwt.encode({"sub": str(user_id), "exp": expire}, settings.secret_key, algorithm=ALGORITHM)


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    error = HTTPException(status.HTTP_401_UNAUTHORIZED, "No autenticado")
    if creds is None:
        raise error
    try:
        payload = jwt.decode(creds.credentials, settings.secret_key, algorithms=[ALGORITHM])
        user = db.get(User, int(payload["sub"]))
    except (jwt.PyJWTError, KeyError, ValueError):
        raise error
    if user is None or not user.is_active:
        raise error
    return user


def require_roles(*roles: str):
    """Dependencia que exige uno de los roles indicados."""

    def dependency(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "No tienes permisos para esta acción"
            )
        return user

    return dependency


# Personal del colegio: puede entrar al panel.
require_staff = require_roles("admin", "secretaria", "profesor")
# Administración: gestión de usuarios.
require_admin = require_roles("admin")
# Secretaría y administración: datos maestros, admisiones y pagos.
require_management = require_roles("admin", "secretaria")
# Personal docente y administrativo: asistencia y notas.
require_academic = require_roles("admin", "secretaria", "profesor")
# Portal de apoderados y estudiantes.
require_portal = require_roles("apoderado", "estudiante")
