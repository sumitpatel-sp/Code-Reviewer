"""Direct database operations for final reports and detailed agent results."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.analysis_result import AnalysisResult
from app.models.finding import Finding
from app.models.ml_prediction import MLPrediction
from app.models.report import Report
from app.models.repository import Repository
from app.schemas.finding import FindingSchema, Severity


def _count_by_severity(findings: list[FindingSchema]) -> dict[str, int]:
    """Count findings grouped by severity."""
    counts = {s.value: 0 for s in Severity}
    for f in findings:
        counts[f.severity.value] = counts.get(f.severity.value, 0) + 1
    return counts


def create_report(
    db: Session,
    repository_id: int,
    overall_score: float,
    summary: str,
    agent_reports: dict,
    findings: list[FindingSchema] | None = None,
    ml_prediction: dict | None = None,
) -> Report:
    """Save one final report together with all agent reports, findings, and ML prediction."""
    severity_counts = _count_by_severity(findings or [])

    report = Report(
        repository_id=repository_id,
        overall_score=overall_score,
        summary=summary,
        quality_score=agent_reports.get("quality_score", 0.0),
        security_score=agent_reports.get("security_score", 0.0),
        performance_score=agent_reports.get("performance_score", 0.0),
        maintainability_score=agent_reports.get("maintainability_score", 0.0),
        testing_score=agent_reports.get("testing_score", 0.0),
        critical_count=severity_counts.get("CRITICAL", 0),
        high_count=severity_counts.get("HIGH", 0),
        medium_count=severity_counts.get("MEDIUM", 0),
        low_count=severity_counts.get("LOW", 0),
        info_count=severity_counts.get("INFO", 0),
    )

    # Detailed agent narrative reports (original 6 agents)
    report.analysis_result = AnalysisResult(
        quality_report=agent_reports.get("quality_report", ""),
        security_report=agent_reports.get("security_report", ""),
        performance_report=agent_reports.get("performance_report", ""),
        bug_report=agent_reports.get("bug_report", ""),
        refactoring_report=agent_reports.get("refactoring_report", ""),
        documentation_report=agent_reports.get("documentation_report", ""),
    )

    db.add(report)
    db.flush()  # get the report.id

    # Persist structured findings
    if findings:
        from app.crud.finding import create_findings
        create_findings(db, report.id, findings)

    # Persist ML prediction
    if ml_prediction:
        from app.crud.ml_prediction import create_ml_prediction
        create_ml_prediction(db, report.id, ml_prediction)

    db.commit()
    db.refresh(report)
    return report


def get_user_reports(db: Session, user_id: int) -> list[Report]:
    """Return all reports for repositories owned by one user."""
    statement = (
        select(Report)
        .join(Repository)
        .where(Repository.user_id == user_id)
        .order_by(Report.created_at.desc())
    )
    return list(db.scalars(statement))


def get_report_for_user(db: Session, report_id: int, user_id: int) -> Report | None:
    """Return a detailed report only when its repository belongs to the user."""
    statement = (
        select(Report)
        .join(Repository)
        .options(
            selectinload(Report.analysis_result),
            selectinload(Report.findings),
            selectinload(Report.ml_prediction),
        )
        .where(Report.id == report_id, Repository.user_id == user_id)
    )
    return db.scalar(statement)


def delete_report(db: Session, report: Report) -> None:
    """Delete a final report and its associated data."""
    db.delete(report)
    db.commit()