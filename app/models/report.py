"""SQLAlchemy model for a final code-review report."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base

if TYPE_CHECKING:
    from app.models.analysis_result import AnalysisResult
    from app.models.repository import Repository


class Report(Base):
    """Store a report's overall score, summary, and detailed agent result."""

    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    repository_id: Mapped[int] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    repository: Mapped["Repository"] = relationship(back_populates="reports")
    analysis_result: Mapped["AnalysisResult | None"] = relationship(
        back_populates="report", cascade="all, delete-orphan", uselist=False
    )
