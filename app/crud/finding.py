"""CRUD operations for structured code-review findings."""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.models.finding import Finding
from app.schemas.finding import FindingSchema


def create_findings(db: Session, report_id: int, findings: list[FindingSchema]) -> list[Finding]:
    """Persist all structured findings for a review to the database."""
    db_findings = []
    for f in findings:
        db_finding = Finding(
            report_id=report_id,
            finding_id=f.id,
            agent=f.agent,
            category=f.category,
            severity=f.severity.value,
            confidence=f.confidence,
            source=f.source.value,
            file=f.file,
            line_start=f.line_start,
            line_end=f.line_end,
            title=f.title,
            description=f.description,
            impact=f.impact,
            recommendation=f.recommendation,
            code_snippet=f.code_snippet,
            suggested_fix=f.suggested_fix,
            merged_from=json.dumps(f.merged_from) if f.merged_from else None,
        )
        db.add(db_finding)
        db_findings.append(db_finding)
    db.flush()
    return db_findings


def get_findings_for_report(
    db: Session,
    report_id: int,
    severity: str | None = None,
    category: str | None = None,
    agent: str | None = None,
) -> list[Finding]:
    """Return findings for a report with optional filters."""
    query = db.query(Finding).filter(Finding.report_id == report_id)
    if severity:
        query = query.filter(Finding.severity == severity.upper())
    if category:
        query = query.filter(Finding.category.ilike(f"%{category}%"))
    if agent:
        query = query.filter(Finding.agent.ilike(f"%{agent}%"))
    return query.order_by(Finding.confidence.desc()).all()
