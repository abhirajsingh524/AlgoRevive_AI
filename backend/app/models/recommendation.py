from typing import Any, Optional
from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin


class Recommendation(Base, TimestampMixin):
    __tablename__ = "recommendations"

    bottleneck_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("bottlenecks.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    current_algorithm: Mapped[str] = mapped_column(String(100), nullable=False)
    recommended_algorithm: Mapped[str] = mapped_column(String(100), nullable=False)
    alternatives: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    expected_complexity: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    feature_importance: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="rules", nullable=False)  # rules|ml

    bottleneck = relationship("Bottleneck", back_populates="recommendation")
    optimizations = relationship("Optimization", back_populates="recommendation", cascade="all, delete-orphan")
