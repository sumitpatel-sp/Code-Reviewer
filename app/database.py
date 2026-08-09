"""SQLAlchemy database engine, session factory, and model base class."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


settings = get_settings()

# pool_pre_ping checks connections before use and avoids stale MySQL connections.
engine = create_engine(settings.database_url, pool_pre_ping=True)

# Each API request receives its own database session from this factory.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Parent class that every SQLAlchemy model will inherit from."""


def get_db() -> Generator[Session, None, None]:
    """Yield one database session and close it after the request is complete."""
    database_session = SessionLocal()
    try:
        yield database_session
    finally:
        database_session.close()
