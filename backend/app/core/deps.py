from typing import Generator
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.core.errors import AppException
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User
from app.services.storage import StorageService, get_storage_service

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def get_database() -> Generator[Session, None, None]:
    yield from get_db()


def get_storage() -> StorageService:
    return get_storage_service()


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_database),
) -> User:
    if not token:
        raise AppException(
            status_code=401,
            detail="Not authenticated",
            code="UNAUTHORIZED",
        )
    payload = decode_access_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise AppException(
            status_code=401,
            detail="Could not validate credentials",
            code="UNAUTHORIZED",
        )
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise AppException(
            status_code=401,
            detail="User not found",
            code="UNAUTHORIZED",
        )
    if not user.is_active:
        raise AppException(
            status_code=403,
            detail="Inactive user",
            code="USER_INACTIVE",
        )
    return user
