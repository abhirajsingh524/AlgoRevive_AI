from typing import Any, Optional
from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin


class Function(Base, TimestampMixin):
    __tablename__ = "functions"

    file_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("files.id", ondelete="CASCADE"), index=True, nullable=False
    )
    repository_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("repositories.id", ondelete="CASCADE"), index=True, nullable=False
    )
    qualified_name: Mapped[str] = mapped_column(String(500), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    lineno: Mapped[int] = mapped_column(Integer, nullable=False)
    end_lineno: Mapped[int] = mapped_column(Integer, nullable=False)
    params: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    complexity_class: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    complexity_rank: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    loop_depth: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    has_recursion: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    patterns: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    severity: Mapped[str] = mapped_column(String(50), default="LOW", nullable=False)
    metrics: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)

    file = relationship("File", back_populates="functions")
    repository = relationship("Repository", back_populates="functions")
    bottlenecks = relationship("Bottleneck", back_populates="function", cascade="all, delete-orphan")
