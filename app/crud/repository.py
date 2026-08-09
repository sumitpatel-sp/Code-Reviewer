"""Direct database operations for uploaded repositories."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.repository import Repository


def create_repository(
    db: Session, user_id: int, repository_name: str, zip_path: str
) -> Repository:
    """Save metadata for one ZIP file uploaded by a user."""
    repository = Repository(
        user_id=user_id,
        repository_name=repository_name,
        zip_path=zip_path,
    )
    db.add(repository)
    db.commit()
    db.refresh(repository)
    return repository


def get_user_repositories(db: Session, user_id: int) -> list[Repository]:
    """Return a user's repositories from newest upload to oldest."""
    statement = (
        select(Repository)
        .where(Repository.user_id == user_id)
        .order_by(Repository.uploaded_at.desc())
    )
    return list(db.scalars(statement))


def get_repository_for_user(
    db: Session, repository_id: int, user_id: int
) -> Repository | None:
    """Return one repository only when it belongs to the current user."""
    statement = select(Repository).where(
        Repository.id == repository_id,
        Repository.user_id == user_id,
    )
    return db.scalar(statement)


def delete_repository(db: Session, repository: Repository) -> None:
    """Delete a repository record and cascade-delete its reports."""
    db.delete(repository)
    db.commit()