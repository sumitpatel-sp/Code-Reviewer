"""Pydantic schemas for report lists, details, and upload results."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AnalysisResultResponse(BaseModel):
    """Return the detailed output produced by each specialized AI agent."""

    model_config = ConfigDict(from_attributes=True)

    quality_report: str
    security_report: str
    performance_report: str
    bug_report: str
    refactoring_report: str
    documentation_report: str


class ReportResponse(BaseModel):
    """Return concise metadata for a saved code-review report."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    repository_id: int
    overall_score: float
    summary: str
    created_at: datetime


class ReportDetailResponse(ReportResponse):
    """Return a final report together with every specialized agent result."""

    analysis_result: AnalysisResultResponse | None = None


class UploadAnalysisResponse(BaseModel):
    """Confirm that an uploaded repository was analyzed and saved."""

    repository_id: int
    report_id: int
    overall_score: float
    message: str