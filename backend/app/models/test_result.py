from typing import Any, Optional
from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin


class TestResult(Base, TimestampMixin):
    __tablename__ = "test_results"

    benchmark_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("benchmark_runs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    details: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)

    benchmark_run = relationship("BenchmarkRun", back_populates="test_results")
