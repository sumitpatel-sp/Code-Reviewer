"""Shared isolated database setup for API tests."""

import os

# Set required configuration before importing application modules.
os.environ.setdefault("MYSQL_HOST", "localhost")
os.environ.setdefault("MYSQL_DATABASE", "test_database")
os.environ.setdefault("MYSQL_USER", "test_user")
os.environ.setdefault("MYSQL_PASSWORD", "test_password")
os.environ.setdefault("MYSQL_ROOT_PASSWORD", "test_root_password")
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-long-enough")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app


TEST_ENGINE = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=TEST_ENGINE)


@pytest.fixture()
def client() -> TestClient:
    """Provide a clean FastAPI test client backed by an in-memory database."""
    Base.metadata.create_all(bind=TEST_ENGINE)

    def override_get_db():
        """Yield one isolated database session for each test request."""
        database_session: Session = TestingSessionLocal()
        try:
            yield database_session
        finally:
            database_session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=TEST_ENGINE)