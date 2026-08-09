"""Saved report retrieval and deletion REST endpoints."""

import logging

from fastapi import APIRouter, Response, status

from app.crud.report import delete_report, get_report_for_user, get_user_reports
from app.dependencies.auth import CurrentUser, DatabaseSession
from app.exceptions.custom_exceptions import ResourceNotFoundError
from app.schemas.report import ReportDetailResponse, ReportResponse


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


@router.delete("/report/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_report(report_id: int, current_user: CurrentUser, db: DatabaseSession) -> Response:
    """Delete one report and its detailed analysis results."""
    report = get_report_for_user(db, report_id, current_user.id)
    if report is None:
        raise ResourceNotFoundError("Report not found.")
    delete_report(db, report)
    logger.info("Report deleted: %s", report_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)