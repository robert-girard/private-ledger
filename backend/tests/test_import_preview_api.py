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


def test_commit_import_inserts_transactions_and_creates_merchants(auth_client: TestClient) -> None:
    headers = _login_headers(auth_client)

    with (FIXTURE_DIR / "td.csv").open("rb") as handle:
        preview_response = auth_client.post(
            "/api/imports/preview",
            headers=headers,
            files={"file": ("td.csv", handle, "text/csv")},
        )

    import_id = preview_response.json()["import_id"]
    commit_response = auth_client.post(f"/api/imports/{import_id}/commit", headers=headers, json={})

    assert commit_response.status_code == 200
    payload = commit_response.json()
    assert payload["status"] == "complete"
    assert payload["inserted_count"] == 2
    assert payload["skipped_count"] == 0
    assert payload["failed_count"] == 0

    transactions_response = auth_client.get("/api/transactions", headers=headers)
    merchants_response = auth_client.get("/api/merchants", headers=headers)
    import_response = auth_client.get(f"/api/imports/{import_id}", headers=headers)

    assert transactions_response.status_code == 200
    transactions = transactions_response.json()
    assert [item["description"] for item in transactions] == ["PAYROLL", "COFFEE SHOP"]
    coffee_transaction = next(item for item in transactions if item["description"] == "COFFEE SHOP")
    assert coffee_transaction["normalized_description"] == "coffee shop"
    assert coffee_transaction["amount"] == "-5.45"

    assert merchants_response.status_code == 200
    assert [item["raw_name"] for item in merchants_response.json()] == ["COFFEE SHOP", "PAYROLL"]

    assert import_response.status_code == 200
    assert import_response.json()["import_status"] == "complete"
    assert import_response.json()["imported_at"] is not None


def test_commit_import_skips_duplicate_rows_from_overlapping_import(auth_client: TestClient) -> None:
    headers = _login_headers(auth_client)

    with (FIXTURE_DIR / "td.csv").open("rb") as first_handle:
        first_preview = auth_client.post(
            "/api/imports/preview",
            headers=headers,
            files={"file": ("td.csv", first_handle, "text/csv")},
        )
    first_import_id = first_preview.json()["import_id"]
    first_commit = auth_client.post(f"/api/imports/{first_import_id}/commit", headers=headers, json={})

    with (FIXTURE_DIR / "td.csv").open("rb") as second_handle:
        second_preview = auth_client.post(
            "/api/imports/preview",
            headers=headers,
            files={"file": ("td.csv", second_handle, "text/csv")},
        )
    second_import_id = second_preview.json()["import_id"]
    second_commit = auth_client.post(f"/api/imports/{second_import_id}/commit", headers=headers, json={})

    assert first_commit.status_code == 200
    assert second_commit.status_code == 200
    assert second_commit.json()["inserted_count"] == 0
    assert second_commit.json()["skipped_count"] == 2
    assert second_commit.json()["failed_count"] == 0

    transactions_response = auth_client.get("/api/transactions", headers=headers)
    merchants_response = auth_client.get("/api/merchants", headers=headers)

    assert len(transactions_response.json()) == 2
    assert len(merchants_response.json()) == 2
