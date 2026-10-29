"""
TrafficVision AI - Authentication
------------------------------------------------
Password hashing (bcrypt) and JWT token creation/verification.
Tokens are short strings the Flutter app stores after login and
sends with future requests to prove who it is.
"""

import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
import bcrypt

from database import User, get_db_session

load_dotenv()

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "insecure-dev-key-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)


def hash_password(plain_password: str) -> str:
    """
    Hashes a plaintext password with bcrypt.
    Uses native bcrypt directly to avoid passlib 1.7.4 bug with bcrypt >= 4.1.0.
    """
    try:
        pwd_bytes = plain_password.encode("utf-8")[:72]
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")
    except Exception:
        return pwd_context.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        pwd_bytes = plain_password.encode("utf-8")[:72]
        hash_bytes = password_hash.encode("utf-8")
        return bcrypt.checkpw(pwd_bytes, hash_bytes)
    except Exception:
        try:
            return pwd_context.verify(plain_password, password_hash)
        except Exception:
            return False


def create_access_token(user_id: int, email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "email": email, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def validate_jwt_token(token: str, db: Session) -> User | None:
    """Helper to validate JWT token string directly and return User or None."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            return None
        user = db.query(User).filter(User.id == int(user_id)).first()
        if user is None or not user.is_active:
            return None
        return user
    except JWTError:
        return None


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    token_query: str | None = Query(None, alias="token"),
    db: Session = Depends(get_db_session),
) -> User:
    """
    FastAPI dependency: extracts and validates token from either Authorization
    header or 'token' query param, returns matching active User row.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    raw_token = token or token_query
    if not raw_token:
        raise credentials_exception

    user = validate_jwt_token(raw_token, db)
    if user is None:
        raise credentials_exception
    return user


def get_admin_user(current_user: User = Depends(get_current_user)) -> User:
    """
    FastAPI dependency: requires the logged in user to be an admin.
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user doesn't have enough privileges"
        )
    return current_user