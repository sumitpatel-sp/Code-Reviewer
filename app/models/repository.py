"""SQLAlchemy model representing an uploaded project ZIP file."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base

if TYPE_CHECKING:
    from app.models.report import Report
    from app.models.user import User


class Repository(Base):
    """Store an uploaded ZIP path and the reports generated from it."""

    __tablename__ = "repositories"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    repository_name: Mapped[str] = mapped_column(String(255), nullable=False)
    zip_path: Mapped[str] = mapped_column(String(500), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="repositories")
    reports: Mapped[list["Report"]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )
