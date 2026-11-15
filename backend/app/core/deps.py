from typing import Generator
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.storage import StorageService, get_storage_service


def get_database() -> Generator[Session, None, None]:
    yield from get_db()


def get_storage() -> StorageService:
    return get_storage_service()
