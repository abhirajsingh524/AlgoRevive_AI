from typing import Any, Optional
from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin


class Bottleneck(Base, TimestampMixin):
    __tablename__ = "bottlenecks"

    analysis_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    function_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("functions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    static_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    runtime_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    call_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    runtime_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    memory_peak_kb: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    impact_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    severity: Mapped[str] = mapped_column(String(50), nullable=False)  # LOW|MEDIUM|HIGH|CRITICAL
    evidence: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)

    analysis_run = relationship("AnalysisRun", back_populates="bottlenecks")
    function = relationship("Function", back_populates="bottlenecks")
    recommendation = relationship("Recommendation", back_populates="bottleneck", uselist=False, cascade="all, delete-orphan")
