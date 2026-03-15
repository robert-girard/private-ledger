from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

import app.config


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "csv"


def _login_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "secret-pass"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_import_preview_detects_profile_and_stores_upload(auth_client: TestClient) -> None:
    headers = _login_headers(auth_client)

    with (FIXTURE_DIR / "td.csv").open("rb") as handle:
        response = auth_client.post(
            "/api/imports/preview",
            headers=headers,
            files={"file": ("td.csv", handle, "text/csv")},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "parsed"
    assert payload["profile_name"] == "td"
    assert payload["row_count"] == 2
    assert payload["preview_rows"][0]["posted_on"] == "2026-03-01"
    assert payload["preview_rows"][0]["amount"] == "-5.45"

    stored_path = Path(payload["stored_path"])
    assert stored_path.exists()
    assert stored_path.read_text(encoding="utf-8") == (FIXTURE_DIR / "td.csv").read_text(encoding="utf-8")
    assert stored_path.is_relative_to(app.config.get_settings().import_storage_dir)


def test_import_preview_returns_manual_mapping_requirement_for_unknown_headers(
    auth_client: TestClient,
) -> None:
    headers = _login_headers(auth_client)

    with (FIXTURE_DIR / "unknown.csv").open("rb") as handle:
        response = auth_client.post(
            "/api/imports/preview",
            headers=headers,
            files={"file": ("unknown.csv", handle, "text/csv")},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "manual_mapping_required"
    assert payload["headers"] == ["Booked On", "Vendor", "Outflow", "Inflow"]
    assert payload["unresolved_columns"] == ["date", "description", "amount"]
    assert payload["preview_rows"] == []


def test_import_preview_supports_manual_mapping(auth_client: TestClient) -> None:
    headers = _login_headers(auth_client)
    mapping = json.dumps(
        {
            "date": "Booked On",
            "description": "Vendor",
            "debit": "Outflow",
            "credit": "Inflow",
        }
    )

    with (FIXTURE_DIR / "unknown.csv").open("rb") as handle:
        response = auth_client.post(
            "/api/imports/preview",
            headers=headers,
            data={"column_mapping": mapping},
            files={"file": ("unknown.csv", handle, "text/csv")},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "parsed"
    assert payload["profile_name"] == "manual"
    assert payload["row_count"] == 1
    assert payload["preview_rows"][0]["posted_on"] == "2026-03-01"
    assert payload["preview_rows"][0]["description"] == "Coffee Shop"
    assert payload["preview_rows"][0]["amount"] == "-5.45"


def test_import_preview_rejects_invalid_manual_mapping(auth_client: TestClient) -> None:
    headers = _login_headers(auth_client)
    mapping = json.dumps(
        {
            "date": "Missing Header",
            "description": "Vendor",
            "amount": "Vendor",
        }
    )

    with (FIXTURE_DIR / "unknown.csv").open("rb") as handle:
        response = auth_client.post(
            "/api/imports/preview",
            headers=headers,
            data={"column_mapping": mapping},
            files={"file": ("unknown.csv", handle, "text/csv")},
        )

    assert response.status_code == 422
    payload = response.json()
    assert payload["detail"]["message"] == "Invalid column mapping."
    assert any("Missing Header" in error for error in payload["detail"]["errors"])
    assert any("only one semantic field" in error for error in payload["detail"]["errors"])
