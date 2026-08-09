"""Unit tests for password hashing and JSON Web Tokens."""

from app.security import create_access_token, get_token_subject, hash_password, verify_password


def test_password_hash_is_not_plain_text() -> None:
    """A stored password must be hashed and still be verifiable."""
    password_hash = hash_password("safe-password-123")
    assert password_hash != "safe-password-123"
    assert verify_password("safe-password-123", password_hash)


def test_access_token_contains_user_email() -> None:
    """A created token should decode to the user email stored as its subject."""
    token = create_access_token("ada@example.com")
    assert get_token_subject(token) == "ada@example.com"


def test_invalid_access_token_returns_none() -> None:
    """An altered token must not be accepted as authenticated data."""
    assert get_token_subject("not-a-valid-token") is None