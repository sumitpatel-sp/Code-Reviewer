"""Repository upload and management REST endpoints."""

import logging
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.crud.report import create_report
from app.crud.repository import (
    create_repository,
    delete_repository,
    get_repository_for_user,
    get_user_repositories,
)
from app.dependencies.auth import CurrentUser, DatabaseSession
from app.exceptions.custom_exceptions import ResourceNotFoundError
from app.langgraph.workflow import build_review_graph
from app.schemas.repository import RepositoryResponse
from app.schemas.report import UploadAnalysisResponse
from app.services.file_service import delete_uploaded_zip, save_uploaded_zip
from app.services.repository_service import (
    delete_extraction_folder,
    extract_repository_zip,
    read_source_files,
)


logger = logging.getLogger(__name__)
router = APIRouter(tags=["Repositories"])


@router.post("/upload", response_model=UploadAnalysisResponse, status_code=status.HTTP_201_CREATED)
async def upload_repository(
    current_user: CurrentUser,
    db: DatabaseSession,
    uploaded_file: UploadFile = File(description="ZIP file containing a source-code project."),
) -> UploadAnalysisResponse:
    """Save a ZIP, run the AI workflow, and persist the repository and report."""
    repository_name, zip_path = await save_uploaded_zip(uploaded_file)
    extraction_path: Path | None = None
    try:
        logger.info("Analysis started for ZIP: %s", repository_name)
        extraction_path = extract_repository_zip(zip_path)
        source_files = read_source_files(extraction_path)
        review_result = build_review_graph().invoke({"source_files": source_files})
        repository = create_repository(db, current_user.id, repository_name, zip_path)
        report = create_report(
            db,
            repository.id,
            review_result["overall_score"],
            review_result["final_summary"],
            review_result,
        )

        # Save the final summary to report.md so it is visible in the project folder.
        try:
            report_path = Path("report.md")
            report_path.write_text(review_result["final_summary"], encoding="utf-8")
            logger.info("Report saved to %s", report_path.resolve())
        except Exception:
            logger.warning("Could not write report.md to disk — results are still in the database.")

        logger.info("Analysis finished for repository ID: %s", repository.id)
        return UploadAnalysisResponse(
            repository_id=repository.id,
            report_id=report.id,
            overall_score=report.overall_score,
            message="Repository uploaded and analyzed successfully.",
        )
    except Exception:
        delete_uploaded_zip(zip_path)
        logger.exception("Repository analysis failed for: %s", repository_name)
        raise
    finally:
        if extraction_path is not None:
            delete_extraction_folder(extraction_path)


@router.get("/repositories", response_model=list[RepositoryResponse])
def list_repositories(current_user: CurrentUser, db: DatabaseSession) -> list[RepositoryResponse]:
    """List repositories uploaded by the current user."""
    repositories = get_user_repositories(db, current_user.id)
    return [RepositoryResponse.model_validate(repository) for repository in repositories]


@router.get("/repository/{repository_id}", response_model=RepositoryResponse)
def get_repository(
    repository_id: int, current_user: CurrentUser, db: DatabaseSession
) -> RepositoryResponse:
    """Return one repository when it belongs to the current user."""
    repository = get_repository_for_user(db, repository_id, current_user.id)
    if repository is None:
        raise ResourceNotFoundError("Repository not found.")
    return RepositoryResponse.model_validate(repository)


@router.delete("/repository/{repository_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_repository(repository_id: int, current_user: CurrentUser, db: DatabaseSession) -> None:
    """Delete one repository, its reports, and its locally stored ZIP file."""
    repository = get_repository_for_user(db, repository_id, current_user.id)
    if repository is None:
        raise ResourceNotFoundError("Repository not found.")
    zip_path = repository.zip_path
    delete_repository(db, repository)
    delete_uploaded_zip(zip_path)
    logger.info("Repository deleted: %s", repository_id)