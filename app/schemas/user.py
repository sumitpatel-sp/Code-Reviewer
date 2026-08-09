"""Pydantic schemas for user registration, login, and profile data."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    """Validate the details needed to create an account."""

    name: str = Field(min_length=2, max_length=100, examples=["Ada Lovelace"])
    email: EmailStr = Field(examples=["ada@example.com"])
    password: str = Field(min_length=8, max_length=128, examples=["safe-password-123"])


class UserLogin(BaseModel):
    """Validate the credentials submitted during login."""

    email: EmailStr = Field(examples=["ada@example.com"])
    password: str = Field(min_length=8, max_length=128, examples=["safe-password-123"])


class UserUpdate(BaseModel):
    """Validate optional profile fields that a logged-in user may change."""

    name: str | None = Field(default=None, min_length=2, max_length=100)
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserResponse(BaseModel):
    """Return safe user data without ever exposing the password hash."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: EmailStr
    created_at: datetime


class TokenResponse(BaseModel):
    """Return a JWT in the standard bearer-token response format."""

    access_token: str
    token_type: str = "bearer"
