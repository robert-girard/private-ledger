from __future__ import annotations

from fastapi.testclient import TestClient

import app.config


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


def test_login_locks_after_repeated_failed_attempts(auth_client: TestClient) -> None:
    app.config.settings = app.config.Settings(
        **{
            **app.config.settings.__dict__,
            "auth_lockout_threshold": 2,
            "auth_lockout_window_seconds": 60,
            "auth_lockout_duration_seconds": 120,
        }
    )

    first_response = auth_client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "wrong-pass"},
    )
    second_response = auth_client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "wrong-pass"},
    )
    locked_response = auth_client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "secret-pass"},
    )

    assert first_response.status_code == 401
    assert second_response.status_code == 423
    assert second_response.headers["retry-after"] == "120"
    assert locked_response.status_code == 423


def test_login_rate_limit_rejects_excess_attempts(auth_client: TestClient) -> None:
    app.config.settings = app.config.Settings(
        **{
            **app.config.settings.__dict__,
            "login_rate_limit_max_attempts": 2,
            "login_rate_limit_window_seconds": 60,
        }
    )

    first_response = auth_client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "secret-pass"},
    )
    second_response = auth_client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "secret-pass"},
    )
    third_response = auth_client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "secret-pass"},
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert third_response.status_code == 429
    assert third_response.headers["retry-after"]


def test_refresh_rate_limit_rejects_excess_attempts(auth_client: TestClient) -> None:
    app.config.settings = app.config.Settings(
        **{
            **app.config.settings.__dict__,
            "refresh_rate_limit_max_attempts": 1,
            "refresh_rate_limit_window_seconds": 60,
        }
    )

    login_response = auth_client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "secret-pass"},
    )
    refresh_token = login_response.json()["refresh_token"]

    first_refresh = auth_client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    second_refresh = auth_client.post("/api/auth/refresh", json={"refresh_token": refresh_token})

    assert first_refresh.status_code == 200
    assert second_refresh.status_code == 429
    assert second_refresh.headers["retry-after"]
