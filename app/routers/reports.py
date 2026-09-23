"""Saved report retrieval, findings, ML risk, and export REST endpoints."""

import json
import logging
from datetime import datetime

from fastapi import APIRouter, Query, Response, status
from fastapi.responses import JSONResponse

from app.crud.finding import get_findings_for_report
from app.crud.ml_prediction import get_ml_prediction_for_report
from app.crud.report import delete_report, get_report_for_user, get_user_reports
from app.dependencies.auth import CurrentUser, DatabaseSession
from app.exceptions.custom_exceptions import ResourceNotFoundError
from app.schemas.finding import FindingCountBreakdown, ScoreBreakdown
from app.schemas.report import (
    ExportReportResponse,
    FindingDBResponse,
    FindingsListResponse,
    MLPredictionDBResponse,
    ReportDetailResponse,
    ReportResponse,
)


logger = logging.getLogger(__name__)
router = APIRouter(tags=["Reports"])


@router.get("/reports", response_model=list[ReportResponse])
def list_reports(current_user: CurrentUser, db: DatabaseSession) -> list[ReportResponse]:
    """List final reports for repositories owned by the current user."""
    reports = get_user_reports(db, current_user.id)
    return [ReportResponse.model_validate(report) for report in reports]


@router.get("/report/{report_id}", response_model=ReportDetailResponse)
def get_report(
    report_id: int, current_user: CurrentUser, db: DatabaseSession
) -> ReportDetailResponse:
    """Return a final report and every detailed AI agent result."""
    report = get_report_for_user(db, report_id, current_user.id)
    if report is None:
        raise ResourceNotFoundError("Report not found.")
    return ReportDetailResponse.model_validate(report)


@router.get("/report/{report_id}/findings", response_model=FindingsListResponse)
def get_report_findings(
    report_id: int,
    current_user: CurrentUser,
    db: DatabaseSession,
    severity: str | None = Query(default=None, description="Filter by severity: CRITICAL, HIGH, MEDIUM, LOW, INFO"),
    category: str | None = Query(default=None, description="Filter by category (partial match)"),
    agent: str | None = Query(default=None, description="Filter by agent name (partial match)"),
) -> FindingsListResponse:
    """Return structured findings for a report with optional filters."""
    # Verify the report belongs to the user
    report = get_report_for_user(db, report_id, current_user.id)
    if report is None:
        raise ResourceNotFoundError("Report not found.")

    findings = get_findings_for_report(db, report_id, severity=severity, category=category, agent=agent)
    return FindingsListResponse(
        report_id=report_id,
        total=len(findings),
        findings=[FindingDBResponse.model_validate(f) for f in findings],
    )


@router.get("/report/{report_id}/risk", response_model=MLPredictionDBResponse)
def get_report_risk(
    report_id: int, current_user: CurrentUser, db: DatabaseSession
) -> MLPredictionDBResponse:
    """Return the ML risk prediction for a code review."""
    report = get_report_for_user(db, report_id, current_user.id)
    if report is None:
        raise ResourceNotFoundError("Report not found.")

    prediction = get_ml_prediction_for_report(db, report_id)
    if prediction is None:
        raise ResourceNotFoundError("ML risk prediction not available for this report.")

    return MLPredictionDBResponse.model_validate(prediction)


@router.get("/report/{report_id}/export")
def export_report(
    report_id: int,
    current_user: CurrentUser,
    db: DatabaseSession,
    format: str = Query(default="json", description="Export format: json or markdown"),
) -> Response:
    """Export a complete review as JSON or Markdown."""
    report = get_report_for_user(db, report_id, current_user.id)
    if report is None:
        raise ResourceNotFoundError("Report not found.")

    findings = get_findings_for_report(db, report_id)
    ml_pred = get_ml_prediction_for_report(db, report_id)

    if format.lower() == "markdown":
        md = _render_markdown_report(report, findings, ml_pred)
        return Response(
            content=md,
            media_type="text/markdown",
            headers={"Content-Disposition": f"attachment; filename=review_{report_id}.md"},
        )

    # JSON export
    export_data = {
        "report_id": report.id,
        "repository_id": report.repository_id,
        "created_at": report.created_at.isoformat(),
        "overall_score": report.overall_score,
        "scores": {
            "overall": report.overall_score,
            "quality": report.quality_score,
            "security": report.security_score,
            "performance": report.performance_score,
            "maintainability": report.maintainability_score,
            "testing": report.testing_score,
        },
        "finding_counts": {
            "critical": report.critical_count,
            "high": report.high_count,
            "medium": report.medium_count,
            "low": report.low_count,
            "info": report.info_count,
            "total": report.critical_count + report.high_count + report.medium_count + report.low_count + report.info_count,
        },
        "findings": [
            {
                "id": f.finding_id,
                "agent": f.agent,
                "category": f.category,
                "severity": f.severity,
                "confidence": f.confidence,
                "source": f.source,
                "file": f.file,
                "line_start": f.line_start,
                "line_end": f.line_end,
                "title": f.title,
                "description": f.description,
                "impact": f.impact,
                "recommendation": f.recommendation,
                "code_snippet": f.code_snippet,
                "suggested_fix": f.suggested_fix,
            }
            for f in findings
        ],
        "ml_prediction": {
            "defect_probability": ml_pred.defect_probability,
            "maintenance_risk": ml_pred.maintenance_risk,
            "review_priority": ml_pred.review_priority,
            "human_review_recommended": ml_pred.human_review_recommended,
            "top_risk_factors": json.loads(ml_pred.top_risk_factors or "[]"),
            "model_used": ml_pred.model_used,
            "disclaimer": ml_pred.disclaimer,
        } if ml_pred else None,
        "final_narrative": report.summary,
    }
    return JSONResponse(
        content=export_data,
        headers={"Content-Disposition": f"attachment; filename=review_{report_id}.json"},
    )


@router.get("/health", tags=["Health"])
def health_check(db: DatabaseSession) -> dict:
    """Detailed health check verifying API and database connectivity."""
    try:
        db.execute(__import__("sqlalchemy").text("SELECT 1"))
        db_status = "healthy"
    except Exception:
        db_status = "unhealthy"
    return {
        "status": "healthy",
        "database": db_status,
        "version": "2.0.0",
        "features": ["multi-agent-review", "static-analysis", "ml-risk-prediction", "structured-findings"],
    }


@router.delete("/report/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_report(report_id: int, current_user: CurrentUser, db: DatabaseSession) -> Response:
    """Delete one report and its detailed analysis results."""
    report = get_report_for_user(db, report_id, current_user.id)
    if report is None:
        raise ResourceNotFoundError("Report not found.")
    delete_report(db, report)
    logger.info("Report deleted: %s", report_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _render_markdown_report(report, findings, ml_pred) -> str:
    """Render a complete Markdown report from database objects."""
    lines = [
        "# AI Code Review Report",
        "",
        f"**Report ID:** {report.id}",
        f"**Date:** {report.created_at.strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "---",
        "",
        "## 1. Executive Summary",
        "",
        f"| Metric | Score |",
        f"|--------|-------|",
        f"| Overall | {report.overall_score:.0f} / 100 |",
        f"| Quality | {report.quality_score:.0f} / 100 |",
        f"| Security | {report.security_score:.0f} / 100 |",
        f"| Performance | {report.performance_score:.0f} / 100 |",
        f"| Maintainability | {report.maintainability_score:.0f} / 100 |",
        f"| Testing | {report.testing_score:.0f} / 100 |",
        "",
        "### Issue Counts",
        "",
        f"| Severity | Count |",
        f"|----------|-------|",
        f"| 🔴 Critical | {report.critical_count} |",
        f"| 🟠 High | {report.high_count} |",
        f"| 🟡 Medium | {report.medium_count} |",
        f"| 🟢 Low | {report.low_count} |",
        f"| ℹ️ Info | {report.info_count} |",
        "",
        "---",
        "",
    ]

    if ml_pred:
        risk_factors = json.loads(ml_pred.top_risk_factors or "[]")
        lines += [
            "## 2. ML Code Risk Prediction",
            "",
            f"> ⚠️ {ml_pred.disclaimer}",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Defect Probability | {ml_pred.defect_probability*100:.1f}% |",
            f"| Maintenance Risk | {ml_pred.maintenance_risk*100:.1f}% |",
            f"| Review Priority | {ml_pred.review_priority} |",
            f"| Human Review Recommended | {'✅ Yes' if ml_pred.human_review_recommended else '❌ No'} |",
            "",
            "**Top Risk Factors:**",
        ]
        for factor in risk_factors:
            lines.append(f"- {factor}")
        lines += ["", "---", ""]

    lines += ["## 3. Findings", ""]
    severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
    sorted_findings = sorted(findings, key=lambda f: severity_order.get(f.severity, 5))

    for f in sorted_findings:
        badge = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢", "INFO": "ℹ️"}.get(f.severity, "⚪")
        lines += [
            f"### {badge} [{f.severity}] {f.title}",
            "",
            f"**Agent:** {f.agent}  ",
            f"**Category:** {f.category}  ",
            f"**Confidence:** {f.confidence}%  ",
        ]
        if f.file:
            loc = f"Lines {f.line_start}–{f.line_end}" if f.line_start else "unknown line"
            lines.append(f"**Location:** `{f.file}` ({loc})  ")
        lines += [
            "",
            f"**Description:** {f.description}",
            "",
            f"**Impact:** {f.impact}",
            "",
            f"**Recommendation:** {f.recommendation}",
        ]
        if f.code_snippet:
            lines += ["", "**Code:**", "```", f.code_snippet, "```"]
        if f.suggested_fix:
            lines += ["", "**Suggested Fix (AI-generated):**", "```", f.suggested_fix, "```"]
        lines += ["", "---", ""]

    lines += ["## 4. Full Analysis", "", report.summary]
    return "\n".join(lines)