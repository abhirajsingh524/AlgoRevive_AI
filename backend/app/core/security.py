from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
import bcrypt
import jwt
from app.core.config import settings
from app.core.errors import AppException


def validate_password_strength(password: str) -> None:
    encoded = password.encode("utf-8")
    if len(password) < 8 or len(encoded) > 72:
        raise AppException(
            status_code=400,
            detail="Password must be between 8 characters and 72 bytes",
            code="INVALID_PASSWORD",
        )


def hash_password(password: str) -> str:
    validate_password_strength(password)
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception:
        return False


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "iat": now})
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm="HS256")


def decode_access_token(token: str) -> Dict[str, Any]:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise AppException(
            status_code=401,
            detail="Token has expired",
            code="TOKEN_EXPIRED",
        )
    except jwt.PyJWTError:
        raise AppException(
            status_code=401,
            detail="Invalid token",
            code="UNAUTHORIZED",
        )
