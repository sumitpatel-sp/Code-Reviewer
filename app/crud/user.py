"""Direct database operations for user accounts."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


def get_user_by_email(db: Session, email: str) -> User | None:
    """Find one user by email address."""
    statement = select(User).where(User.email == email)
    return db.scalar(statement)


def get_user_by_id(db: Session, user_id: int) -> User | None:
    """Find one user by primary key."""
    return db.get(User, user_id)


def create_user(db: Session, name: str, email: str, password_hash: str) -> User:
    """Save a new user whose password has already been safely hashed."""
    user = User(name=name, email=email, password=password_hash)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_user(db: Session, user: User, changes: dict[str, str]) -> User:
    """Apply already-validated profile changes to an existing user."""
    for field_name, value in changes.items():
        setattr(user, field_name, value)
    db.commit()
    db.refresh(user)
    return user


def delete_user(db: Session, user: User) -> None:
    """Delete a user and cascade-delete database records they own."""
    db.delete(user)
    db.commit()