from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext

import os

DEFAULT_SECRET_KEY = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"
APP_ENV = os.environ.get("APP_ENV", "development").lower()
SECRET_KEY = os.environ.get("SECRET_KEY", DEFAULT_SECRET_KEY)
if APP_ENV == "production" and (SECRET_KEY == DEFAULT_SECRET_KEY or SECRET_KEY.startswith("CHANGE_ME")):
    raise RuntimeError("SECRET_KEY must be set to a unique value when APP_ENV=production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "720"))

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from ..database import get_db
from .. import models

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def authenticate_token(token: str, db: Session) -> dict:
    """Décode le JWT et vérifie que l'utilisateur existe encore et est actif."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")
    username: str = payload.get("sub")
    if username is None:
        raise HTTPException(status_code=401, detail="Could not validate credentials")
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return payload

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    return authenticate_token(token, db)

def get_current_user_role(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    payload = get_current_user(token, db)
    role: str = payload.get("role")
    if role is None:
        raise HTTPException(status_code=401, detail="No role found in token")
    return role

def require_roles(*allowed_roles: str):
    def dependency(role: str = Depends(get_current_user_role)):
        if role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Privilèges insuffisants")
        return role
    return dependency

def user_has_permission(db: Session, role_name: str, permission_code: str) -> bool:
    if role_name in ["ADMIN", "SUPER_ADMIN"]:
        return True
    role = db.query(models.Role).filter(models.Role.name == role_name).first()
    if not role:
        return False
    return any(permission.code == permission_code for permission in role.permissions)

def assert_permission(db: Session, current_user: dict, permission_code: str):
    role_name = current_user.get("role")
    if not role_name:
        raise HTTPException(status_code=401, detail="No role found in token")
    if not user_has_permission(db, role_name, permission_code):
        raise HTTPException(status_code=403, detail=f"Permission requise: {permission_code}")

def require_permissions(*permission_codes: str):
    def dependency(
        db: Session = Depends(get_db),
        current_user: dict = Depends(get_current_user),
    ):
        for permission_code in permission_codes:
            assert_permission(db, current_user, permission_code)
        return current_user
    return dependency
