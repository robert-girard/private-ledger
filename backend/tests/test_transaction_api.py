from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select

import app.db.session
from app.db.models import Import, Merchant, Transaction, User


def _auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "secret-pass"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _seed_transactions() -> tuple[list[str], str]:
    with app.db.session.SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == "admin@example.com"))
        assert user is not None
        coffee = Merchant(raw_name="COFFEE SHOP", display_name="Coffee Shop", category="Dining", status="reviewed")
        salary = Merchant(raw_name="PAYROLL INC", display_name="Payroll Inc", category="Income", status="reviewed")
        session.add_all([coffee, salary])
        session.flush()
        import_one = Import(user_id=user.id, source_filename="march.csv", source_bank="td", import_status="complete", row_count=2)
        import_two = Import(user_id=user.id, source_filename="april.csv", source_bank="rbc", import_status="complete", row_count=1)
        session.add_all([import_one, import_two])
        session.flush()
        items = [
            Transaction(
                user_id=user.id,
                import_id=import_one.id,
                merchant_id=coffee.id,
                posted_on=date(2026, 3, 1),
                description="COFFEE SHOP",
                normalized_description="coffee shop",
                amount=Decimal("-5.45"),
                currency="CAD",
                category=None,
                dedupe_hash="tx-dedupe-1",
            ),
            Transaction(
                user_id=user.id,
                import_id=import_one.id,
                merchant_id=salary.id,
                posted_on=date(2026, 3, 2),
                description="PAYROLL INC",
                normalized_description="payroll inc",
                amount=Decimal("1500.00"),
                currency="CAD",
                category="Income",
                dedupe_hash="tx-dedupe-2",
            ),
            Transaction(
                user_id=user.id,
                import_id=import_two.id,
                merchant_id=coffee.id,
                posted_on=date(2026, 4, 1),
                description="COFFEE SHOP",
                normalized_description="coffee shop",
                amount=Decimal("-8.50"),
                currency="CAD",
                category="Dining",
                dedupe_hash="tx-dedupe-3",
            ),
        ]
        session.add_all(items)
        session.commit()
        return [item.id for item in items], coffee.id


def test_transaction_filters_updates_bulk_actions_and_export(auth_client: TestClient) -> None:
    headers = _auth_headers(auth_client)
    transaction_ids, coffee_merchant_id = _seed_transactions()

    uncategorized = auth_client.get("/api/transactions", headers=headers, params={"uncategorized_only": "true"})
    assert uncategorized.status_code == 200
    assert [item["description"] for item in uncategorized.json()] == ["COFFEE SHOP"]

    filtered = auth_client.get(
        "/api/transactions",
        headers=headers,
        params={"merchant_id": coffee_merchant_id, "start_date": "2026-04-01", "amount_min": "-10.00"},
    )
    assert filtered.status_code == 200
    assert len(filtered.json()) == 1
    assert filtered.json()[0]["import_source"] == "april.csv"

    patch_response = auth_client.patch(
        f"/api/transactions/{transaction_ids[0]}",
        headers=headers,
        json={"category": "Coffee"},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["category"] == "Coffee"

    bulk_category = auth_client.post(
        "/api/transactions/bulk-category",
        headers=headers,
        json={"transaction_ids": transaction_ids[1:], "category": "Reviewed"},
    )
    assert bulk_category.status_code == 200
    assert bulk_category.json()["updated_count"] == 2

    export_response = auth_client.get(
        "/api/transactions/export",
        headers=headers,
        params={"category": "Reviewed"},
    )
    assert export_response.status_code == 200
    assert "PAYROLL INC" in export_response.text
    assert "april.csv" in export_response.text

    delete_response = auth_client.post(
        "/api/transactions/bulk-delete",
        headers=headers,
        json={"transaction_ids": [transaction_ids[2]]},
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted_count"] == 1

    remaining = auth_client.get("/api/transactions", headers=headers)
    assert remaining.status_code == 200
    assert len(remaining.json()) == 2
