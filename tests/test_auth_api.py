"""Integration tests for registration, login, and protected profile access."""

from fastapi.testclient import TestClient


def test_register_login_and_get_current_user(client: TestClient) -> None:
    """A new user can register, receive a token, and access the /me endpoint."""
    registration_response = client.post(
        "/register",
        json={
            "name": "Ada Lovelace",
            "email": "ada@example.com",
            "password": "safe-password-123",
        },
    )
    assert registration_response.status_code == 201
    assert registration_response.json()["email"] == "ada@example.com"

    login_response = client.post(
        "/login",
        data={"username": "ada@example.com", "password": "safe-password-123"},
    )
    assert login_response.status_code == 200
    access_token = login_response.json()["access_token"]

    profile_response = client.get("/me", headers={"Authorization": f"Bearer {access_token}"})
    assert profile_response.status_code == 200
    assert profile_response.json()["name"] == "Ada Lovelace"


def test_login_rejects_wrong_password(client: TestClient) -> None:
    """Login must not issue a token when a password does not match."""
    client.post(
        "/register",
        json={
            "name": "Ada Lovelace",
            "email": "ada@example.com",
            "password": "safe-password-123",
        },
    )
    response = client.post(
        "/login",
        data={"username": "ada@example.com", "password": "wrong-password-123"},
    )
    assert response.status_code == 401