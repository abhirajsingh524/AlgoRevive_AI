from typing import Generator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("db")

connect_args = {"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
if "postgresql" in settings.DATABASE_URL:
    connect_args["connect_timeout"] = 2

try:
    engine = create_engine(
        settings.DATABASE_URL,
        connect_args=connect_args,
        pool_pre_ping=True,
        echo=False,
    )
    with engine.connect():
        pass
except Exception as e:
    logger.warning(
        f"Could not connect to primary database ({e}); falling back to local SQLite database."
    )
    engine = create_engine(
        "sqlite:///algorevive.db",
        connect_args={"check_same_thread": False},
    )
    from app.db.base import Base

    Base.metadata.create_all(bind=engine)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_health() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False
