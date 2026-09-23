"""Pydantic schemas for report lists, details, upload results, and structured findings."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, model_validator

from app.schemas.finding import (
    AgentSummary,
    FindingCountBreakdown,
    FindingSchema,
    MLPredictionSchema,
    ScoreBreakdown,
)


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
    quality_score: float = 0.0
    security_score: float = 0.0
    performance_score: float = 0.0
    maintainability_score: float = 0.0
    testing_score: float = 0.0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    info_count: int = 0
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
    quality_score: float = 0.0
    security_score: float = 0.0
    performance_score: float = 0.0
    maintainability_score: float = 0.0
    testing_score: float = 0.0
    finding_count: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    ml_risk_priority: Optional[str] = None
    ml_defect_probability: Optional[float] = None
    human_review_recommended: Optional[bool] = None
    message: str


class FindingDBResponse(BaseModel):
    """Structured finding returned from the database."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    report_id: int
    finding_id: str
    agent: str
    category: str
    severity: str
    confidence: int
    source: str
    file: Optional[str] = None
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    title: str
    description: str
    impact: str
    recommendation: str
    code_snippet: Optional[str] = None
    suggested_fix: Optional[str] = None
    merged_from: Optional[list[str]] = None

    @model_validator(mode="before")
    @classmethod
    def parse_merged_from(cls, values):
        """Parse merged_from from JSON string if needed."""
        if hasattr(values, "__dict__"):
            # SQLAlchemy model instance
            raw = getattr(values, "merged_from", None)
            if isinstance(raw, str):
                try:
                    values.__dict__["merged_from"] = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    values.__dict__["merged_from"] = []
        return values


class FindingsListResponse(BaseModel):
    """Paginated list of structured findings for a report."""

    report_id: int
    total: int
    findings: list[FindingDBResponse]


class MLPredictionDBResponse(BaseModel):
    """ML risk prediction returned from the database."""

    model_config = ConfigDict(from_attributes=True)

    report_id: int
    defect_probability: float
    maintenance_risk: float
    review_priority: str
    human_review_recommended: bool
    top_risk_factors: list[str] = []
    shap_values: dict[str, float] = {}
    model_version: str
    model_used: str
    disclaimer: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def parse_json_fields(cls, values):
        """Parse top_risk_factors and shap_values from JSON strings."""
        if hasattr(values, "__dict__"):
            for field in ("top_risk_factors", "shap_values"):
                raw = getattr(values, field, None)
                if isinstance(raw, str):
                    try:
                        values.__dict__[field] = json.loads(raw)
                    except (json.JSONDecodeError, TypeError):
                        values.__dict__[field] = [] if field == "top_risk_factors" else {}
        return values


class ExportReportResponse(BaseModel):
    """Full structured export of a code review."""

    report_id: int
    repository_id: int
    created_at: datetime
    overall_score: float
    scores: ScoreBreakdown
    finding_counts: FindingCountBreakdown
    findings: list[FindingDBResponse]
    ml_prediction: Optional[MLPredictionDBResponse] = None
    final_narrative: str