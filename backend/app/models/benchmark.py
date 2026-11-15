from typing import Any, Optional
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin


class BenchmarkRun(Base, TimestampMixin):
    __tablename__ = "benchmark_runs"

    optimization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("optimizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    repetitions: Mapped[int] = mapped_column(Integer, default=7, nullable=False)
    workload: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    environment: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="queued", nullable=False)

    optimization = relationship("Optimization", back_populates="benchmark_runs")
    benchmark_results = relationship("BenchmarkResult", back_populates="benchmark_run", cascade="all, delete-orphan")
    test_results = relationship("TestResult", back_populates="benchmark_run", cascade="all, delete-orphan")


class BenchmarkResult(Base, TimestampMixin):
    __tablename__ = "benchmark_results"

    benchmark_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("benchmark_runs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    variant: Mapped[str] = mapped_column(String(50), nullable=False)  # original|candidate
    size_n: Mapped[int] = mapped_column(Integer, nullable=False)
    metrics: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)

    benchmark_run = relationship("BenchmarkRun", back_populates="benchmark_results")
