from typing import Optional
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin


class Repository(Base, TimestampMixin):
    __tablename__ = "repositories"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    version_label: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)  # zip|files
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="uploaded", nullable=False)  # uploaded|ingested|failed
    file_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_loc: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    project = relationship("Project", back_populates="repositories")
    files = relationship("File", back_populates="repository", cascade="all, delete-orphan")
    functions = relationship("Function", back_populates="repository", cascade="all, delete-orphan")
    analysis_runs = relationship("AnalysisRun", back_populates="repository", cascade="all, delete-orphan")
