"""Password hashing and JWT token helpers for authentication."""

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import get_settings


# bcrypt is a slow password hash, which makes stolen passwords harder to crack.
password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
settings = get_settings()


def hash_password(password: str) -> str:
    """Convert a plain-text password into a safe value for database storage."""
    return password_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check whether a plain-text password matches its stored hash."""
    return password_context.verify(plain_password, hashed_password)


def create_access_token(subject: str) -> str:
    """Create a signed JWT that identifies one user for a limited time."""
    expiry_time = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    token_data: dict[str, Any] = {"sub": subject, "exp": expiry_time}
    return jwt.encode(token_data, settings.secret_key, algorithm=settings.algorithm)


def get_token_subject(token: str) -> str | None:
    """Return the user email in a valid token, or None when it is invalid."""
    try:
        token_data = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        subject = token_data.get("sub")
        return subject if isinstance(subject, str) else None
    except JWTError:
        return None
