"""Pydantic schemas for structured code-review findings and ML risk predictions."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class Severity(str, Enum):
    """Ordered severity levels for code-review findings."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class FindingSource(str, Enum):
    """Identifies whether a finding came from static analysis or an AI agent."""

    STATIC_ANALYSIS = "static_analysis"
    AI_DETECTED = "ai_detected"
    AI_SUSPECTED = "ai_suspected"


class FindingSchema(BaseModel):
    """One structured code-review finding produced by an agent or static tool."""

    id: str = Field(description="Unique identifier for this finding.")
    agent: str = Field(description="Name of the agent or tool that produced this finding.")
    category: str = Field(description="High-level category, e.g. Security, Quality, Bug.")
    severity: Severity
    confidence: int = Field(ge=0, le=100, description="Confidence 0–100 that this issue exists.")
    source: FindingSource = FindingSource.AI_DETECTED

    # Location — nullable when the agent cannot reliably determine them
    file: Optional[str] = Field(default=None, description="Relative file path.")
    line_start: Optional[int] = Field(default=None, description="First line of the issue, or null.")
    line_end: Optional[int] = Field(default=None, description="Last line of the issue, or null.")

    # Content
    title: str
    description: str
    impact: str
    recommendation: str
    code_snippet: Optional[str] = Field(default=None, description="Relevant code, or null.")
    suggested_fix: Optional[str] = Field(default=None, description="AI-suggested fix, or null.")

    # Deduplication metadata
    merged_from: list[str] = Field(
        default_factory=list,
        description="IDs of original findings that were merged into this one.",
    )


class MLPredictionSchema(BaseModel):
    """ML-based code risk prediction for one review."""

    defect_probability: float = Field(ge=0.0, le=1.0)
    maintenance_risk: float = Field(ge=0.0, le=1.0)
    review_priority: str  # HIGH / MEDIUM / LOW
    human_review_recommended: bool
    top_risk_factors: list[str]
    shap_values: dict[str, float] = Field(
        default_factory=dict,
        description="SHAP feature importance values for explainability.",
    )
    model_version: str = "1.0"
    disclaimer: str = (
        "Risk prediction indicates statistical likelihood based on code metrics. "
        "It does not guarantee the presence or absence of defects."
    )


class AgentSummary(BaseModel):
    """Execution summary for one agent in the workflow."""

    agent_name: str
    finding_count: int
    execution_time_seconds: Optional[float] = None
    status: str = "completed"


class ScoreBreakdown(BaseModel):
    """Granular scores produced by the final report agent."""

    overall: float = Field(ge=0, le=100)
    quality: float = Field(ge=0, le=100)
    security: float = Field(ge=0, le=100)
    performance: float = Field(ge=0, le=100)
    maintainability: float = Field(ge=0, le=100)
    testing: float = Field(ge=0, le=100)


class FindingCountBreakdown(BaseModel):
    """Counts of findings grouped by severity."""

    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    info: int = 0
    total: int = 0


# ── API response schemas ──────────────────────────────────────────────────────

class FindingResponse(FindingSchema):
    """Finding as returned from the REST API (includes database ID)."""

    model_config = ConfigDict(from_attributes=True)

    db_id: Optional[int] = Field(default=None, description="Database row ID.")
    report_id: int


class MLPredictionResponse(MLPredictionSchema):
    """ML prediction as returned from the REST API."""

    model_config = ConfigDict(from_attributes=True)

    report_id: int


class FindingsListResponse(BaseModel):
    """Paginated list of findings for a report."""

    report_id: int
    total: int
    findings: list[FindingSchema]


class ReportSummaryResponse(BaseModel):
    """Rich summary returned at the top level of a report."""

    model_config = ConfigDict(from_attributes=True)

    report_id: int
    repository_name: str
    scores: ScoreBreakdown
    finding_counts: FindingCountBreakdown
    agent_summaries: list[AgentSummary]
    top_issues: list[FindingSchema]
    ml_prediction: Optional[MLPredictionSchema] = None
    final_narrative: str
    files_reviewed: int
