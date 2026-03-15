from __future__ import annotations

from fastapi.testclient import TestClient


def test_login_returns_access_and_refresh_tokens(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "secret-pass"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["access_token"]
    assert payload["refresh_token"]
    assert payload["user"]["email"] == "admin@example.com"


def test_refresh_rotates_token_and_revokes_previous_token(auth_client: TestClient) -> None:
    login_response = auth_client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "secret-pass"},
    )
    refresh_token = login_response.json()["refresh_token"]

    refresh_response = auth_client.post("/api/auth/refresh", json={"refresh_token": refresh_token})

    assert refresh_response.status_code == 200
    rotated_refresh_token = refresh_response.json()["refresh_token"]
    assert rotated_refresh_token != refresh_token

    revoked_response = auth_client.post("/api/auth/refresh", json={"refresh_token": refresh_token})

    assert revoked_response.status_code == 401
    assert revoked_response.json()["detail"] == "Refresh token has been revoked."


def test_logout_revokes_refresh_token(auth_client: TestClient) -> None:
    login_response = auth_client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "secret-pass"},
    )
    refresh_token = login_response.json()["refresh_token"]

    logout_response = auth_client.post("/api/auth/logout", json={"refresh_token": refresh_token})
    revoked_response = auth_client.post("/api/auth/refresh", json={"refresh_token": refresh_token})

    assert logout_response.status_code == 204
    assert revoked_response.status_code == 401
    assert revoked_response.json()["detail"] == "Refresh token has been revoked."
