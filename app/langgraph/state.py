"""Shared data that moves between LangGraph code-review nodes."""

from typing import TypedDict


class ReviewState(TypedDict, total=False):
    """Keep the source code and every agent output in one workflow state object."""

    source_files: dict[str, str]
    quality_report: str
    bug_report: str
    security_report: str
    performance_report: str
    refactoring_report: str
    documentation_report: str
    overall_score: float
    final_summary: str