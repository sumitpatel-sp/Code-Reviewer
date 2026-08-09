"""Pydantic schemas for uploaded repository data."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RepositoryResponse(BaseModel):
    """Return repository metadata without exposing its private stored ZIP path."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    repository_name: str
    uploaded_at: datetime