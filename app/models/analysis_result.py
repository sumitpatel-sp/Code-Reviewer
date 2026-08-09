"""SQLAlchemy model containing the detailed output from every AI agent."""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.report import Report


class AnalysisResult(Base):
    """Store the six detailed reports belonging to one final report."""

    __tablename__ = "analysis_results"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    report_id: Mapped[int] = mapped_column(
        ForeignKey("reports.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    quality_report: Mapped[str] = mapped_column(Text, nullable=False)
    security_report: Mapped[str] = mapped_column(Text, nullable=False)
    performance_report: Mapped[str] = mapped_column(Text, nullable=False)
    bug_report: Mapped[str] = mapped_column(Text, nullable=False)
    refactoring_report: Mapped[str] = mapped_column(Text, nullable=False)
    documentation_report: Mapped[str] = mapped_column(Text, nullable=False)

    report: Mapped["Report"] = relationship(back_populates="analysis_result")
