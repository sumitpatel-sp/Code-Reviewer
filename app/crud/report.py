"""Direct database operations for final reports and detailed agent results."""

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.analysis_result import AnalysisResult
from app.models.report import Report
from app.models.repository import Repository


def create_report(
    db: Session,
    repository_id: int,
    overall_score: float,
    summary: str,
    agent_reports: dict[str, str],
) -> Report:
    """Save one final report together with all six agent reports."""
    report = Report(
        repository_id=repository_id,
        overall_score=overall_score,
        summary=summary,
    )
    report.analysis_result = AnalysisResult(
        quality_report=agent_reports["quality_report"],
        security_report=agent_reports["security_report"],
        performance_report=agent_reports["performance_report"],
        bug_report=agent_reports["bug_report"],
        refactoring_report=agent_reports["refactoring_report"],
        documentation_report=agent_reports["documentation_report"],
    )
    db.add(report)
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
        .options(selectinload(Report.analysis_result))
        .where(Report.id == report_id, Repository.user_id == user_id)
    )
    return db.scalar(statement)


def delete_report(db: Session, report: Report) -> None:
    """Delete a final report and its one-to-one analysis result."""
    db.delete(report)
    db.commit()