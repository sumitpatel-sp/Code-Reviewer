"""SQLAlchemy model for storing one structured code-review finding."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.report import Report


class Finding(Base):
    """Store one structured finding produced by an agent or static analysis tool."""

    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    report_id: Mapped[int] = mapped_column(
        ForeignKey("reports.id", ondelete="CASCADE"), nullable=False, index=True
    )

    finding_id: Mapped[str] = mapped_column(String(100), nullable=False)
    agent: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="ai_detected")

    file: Mapped[str | None] = mapped_column(String(500), nullable=True)
    line_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    line_end: Mapped[int | None] = mapped_column(Integer, nullable=True)

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    impact: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    code_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggested_fix: Mapped[str | None] = mapped_column(Text, nullable=True)
    merged_from: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list of IDs

    report: Mapped["Report"] = relationship(back_populates="findings")
