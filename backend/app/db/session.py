from pathlib import Path
from typing import Generator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("db")

REPO_ROOT = Path(__file__).resolve().parents[3]
CANONICAL_DB_FILE = (REPO_ROOT / "algorevive.db").resolve()
CANONICAL_SQLITE_URL = f"sqlite:///{CANONICAL_DB_FILE.as_posix()}"

db_url = settings.DATABASE_URL
if db_url.startswith("sqlite:///") and not db_url.startswith("sqlite:///:memory:"):
    path_part = db_url.replace("sqlite:///", "")
    if not Path(path_part).is_absolute() and not (len(path_part) > 1 and path_part[1] == ":"):
        db_url = CANONICAL_SQLITE_URL

connect_args = {"check_same_thread": False} if "sqlite" in db_url else {}
if "postgresql" in db_url:
    connect_args["connect_timeout"] = 2

try:
    engine = create_engine(
        db_url,
        connect_args=connect_args,
        pool_pre_ping=True,
        echo=False,
    )
    with engine.connect():
        pass
except Exception as e:
    logger.warning(
        f"Could not connect to primary database ({e}); falling back to local SQLite database at {CANONICAL_SQLITE_URL}."
    )
    engine = create_engine(
        CANONICAL_SQLITE_URL,
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
