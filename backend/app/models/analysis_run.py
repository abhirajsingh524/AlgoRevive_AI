from datetime import datetime
from typing import Any, Optional
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin


class AnalysisRun(Base, TimestampMixin):
    __tablename__ = "analysis_runs"

    repository_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("repositories.id", ondelete="CASCADE"), index=True, nullable=False
    )
    requested_by: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    status: Mapped[str] = mapped_column(String(50), default="queued", nullable=False)  # queued|running|completed|failed
    stage: Mapped[str] = mapped_column(String(50), default="queued", nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    config: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    workload_spec: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    workload_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    environment: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    repository = relationship("Repository", back_populates="analysis_runs")
    bottlenecks = relationship("Bottleneck", back_populates="analysis_run", cascade="all, delete-orphan")
