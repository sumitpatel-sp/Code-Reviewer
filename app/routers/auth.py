"""Authentication and profile REST endpoints."""

import logging

from fastapi import APIRouter, HTTPException, Response, status

from app.crud.repository import get_user_repositories
from app.crud.user import create_user, delete_user, get_user_by_email, update_user
from app.dependencies.auth import CurrentUser, DatabaseSession
from app.exceptions.custom_exceptions import ResourceConflictError
from fastapi.security import OAuth2PasswordRequestForm
from typing import Annotated
from fastapi import Depends
from app.schemas.user import TokenResponse, UserCreate, UserResponse, UserUpdate
from app.security import create_access_token, hash_password, verify_password
from app.services.file_service import delete_uploaded_zip


logger = logging.getLogger(__name__)
router = APIRouter(tags=["Authentication"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(user_data: UserCreate, db: DatabaseSession) -> UserResponse:
    """Register an account using a unique email and securely hashed password."""
    if get_user_by_email(db, str(user_data.email)):
        raise ResourceConflictError("An account with this email already exists.")
    user = create_user(db, user_data.name, str(user_data.email), hash_password(user_data.password))
    logger.info("User registered: %s", user.email)
    return UserResponse.model_validate(user)


@router.post("/login", response_model=TokenResponse)
def login(credentials: Annotated[OAuth2PasswordRequestForm, Depends()], db: DatabaseSession) -> TokenResponse:
    """Validate credentials and return a bearer token for protected APIs."""
    user = get_user_by_email(db, str(credentials.username))
    if user is None or not verify_password(credentials.password, user.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")
    logger.info("User logged in: %s", user.email)
    return TokenResponse(access_token=create_access_token(user.email))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(current_user: CurrentUser) -> Response:
    """Log a logout event; clients remove the stateless JWT after this response."""
    logger.info("User logged out: %s", current_user.email)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserResponse)
def get_me(current_user: CurrentUser) -> UserResponse:
    """Return the profile for the authenticated user."""
    return UserResponse.model_validate(current_user)


@router.put("/profile", response_model=UserResponse)
def update_profile(
    user_data: UserUpdate, current_user: CurrentUser, db: DatabaseSession
) -> UserResponse:
    """Update the authenticated user's provided profile fields."""
    changes = user_data.model_dump(exclude_none=True)
    if "email" in changes and changes["email"] != current_user.email:
        if get_user_by_email(db, str(changes["email"])):
            raise ResourceConflictError("An account with this email already exists.")
        changes["email"] = str(changes["email"])
    if "password" in changes:
        changes["password"] = hash_password(changes["password"])
    updated_user = update_user(db, current_user, changes)
    return UserResponse.model_validate(updated_user)


@router.delete("/profile", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(current_user: CurrentUser, db: DatabaseSession) -> Response:
    """Delete the current account, its database records, and stored ZIP files."""
    zip_paths = [repository.zip_path for repository in get_user_repositories(db, current_user.id)]
    delete_user(db, current_user)
    for zip_path in zip_paths:
        delete_uploaded_zip(zip_path)
    logger.info("User deleted account: %s", current_user.email)
    return Response(status_code=status.HTTP_204_NO_CONTENT)