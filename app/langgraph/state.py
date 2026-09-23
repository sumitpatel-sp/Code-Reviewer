"""Shared data that moves between LangGraph code-review nodes."""

from typing import Any, Optional, TypedDict


class ReviewState(TypedDict, total=False):
    """Keep the source code and every agent output in one workflow state object."""

    # Input
    source_files: dict[str, str]

    # Path to the extracted ZIP temp directory — used by the Semgrep node only.
    # The LangGraph router's finally-block remains solely responsible for
    # deleting this directory after the full workflow completes.
    extraction_path: Optional[str]

    # Agent narrative reports (preserved from original system)
    quality_report: str
    bug_report: str
    security_report: str
    performance_report: str
    refactoring_report: str
    documentation_report: str
    final_summary: str

    # Structured findings (accumulated across all agents)
    findings: list[dict[str, Any]]

    # Static analysis results
    static_analysis_results: dict[str, Any]

    # ML feature vector
    ml_features: dict[str, float]

    # ML risk prediction result
    ml_risk_prediction: dict[str, Any]

    # Scores
    overall_score: float
    quality_score: float
    security_score: float
    performance_score: float
    maintainability_score: float
    testing_score: float

    # Execution timing per agent (name → seconds)
    agent_timing: dict[str, float]