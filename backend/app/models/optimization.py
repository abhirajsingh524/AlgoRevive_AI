from typing import Any, Optional
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin


class Optimization(Base, TimestampMixin):
    __tablename__ = "optimizations"

    recommendation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("recommendations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    mode: Mapped[str] = mapped_column(String(50), default="template", nullable=False)  # template|llm
    template_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    candidate_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    patch: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), default="generated", nullable=False
    )  # generated|validating|benchmarking|completed|failed
    decision: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # ACCEPT|REVIEW|REJECT|null
    decision_reason: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    human_review: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    recommendation = relationship("Recommendation", back_populates="optimizations")
    benchmark_runs = relationship("BenchmarkRun", back_populates="optimization", cascade="all, delete-orphan")
