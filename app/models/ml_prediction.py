"""SQLAlchemy model for ML code risk prediction results."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.report import Report


class MLPrediction(Base):
    """Store ML risk prediction results for one code review."""

    __tablename__ = "ml_predictions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    report_id: Mapped[int] = mapped_column(
        ForeignKey("reports.id", ondelete="CASCADE"), unique=True, nullable=False
    )

    defect_probability: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    maintenance_risk: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    review_priority: Mapped[str] = mapped_column(String(20), nullable=False, default="UNKNOWN")
    human_review_recommended: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    top_risk_factors: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    shap_values: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON dict
    model_version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0")
    model_used: Mapped[str] = mapped_column(String(50), nullable=False, default="heuristic_fallback")
    disclaimer: Mapped[str | None] = mapped_column(Text, nullable=True)

    report: Mapped["Report"] = relationship(back_populates="ml_prediction")
