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


def _seed_merchant_data() -> tuple[str, str]:
    with app.db.session.SessionLocal() as session:
        merchant_one = Merchant(
            raw_name="COFFEE SHOP",
            display_name="Coffee Shop",
            category="Dining",
            status="unreviewed",
            is_transfer=False,
        )
        merchant_two = Merchant(
            raw_name="PAYROLL INC",
            display_name="Payroll Inc",
            category="Income",
            status="reviewed",
            is_transfer=False,
        )
        session.add_all([merchant_one, merchant_two])
        session.flush()

        user = session.scalar(select(User).where(User.email == "admin@example.com"))
        assert user is not None

        source_import = Import(
            user_id=user.id,
            source_filename="seed.csv",
            source_bank="td",
            import_status="complete",
            row_count=3,
        )
        session.add(source_import)
        session.flush()

        session.add_all(
            [
                Transaction(
                    user_id=user.id,
                    import_id=source_import.id,
                    merchant_id=merchant_one.id,
                    posted_on=date(2026, 3, 1),
                    description="COFFEE SHOP",
                    normalized_description="coffee shop",
                    amount=Decimal("-5.45"),
                    currency="CAD",
                    category=None,
                    dedupe_hash="merchant-dedupe-1",
                ),
                Transaction(
                    user_id=user.id,
                    import_id=source_import.id,
                    merchant_id=merchant_one.id,
                    posted_on=date(2026, 3, 2),
                    description="COFFEE SHOP TORONTO",
                    normalized_description="coffee shop toronto",
                    amount=Decimal("-7.00"),
                    currency="CAD",
                    category=None,
                    dedupe_hash="merchant-dedupe-2",
                ),
                Transaction(
                    user_id=user.id,
                    import_id=source_import.id,
                    merchant_id=merchant_two.id,
                    posted_on=date(2026, 3, 3),
                    description="PAYROLL INC",
                    normalized_description="payroll inc",
                    amount=Decimal("1500.00"),
                    currency="CAD",
                    category="Income",
                    dedupe_hash="merchant-dedupe-3",
                ),
            ]
        )
        session.commit()
        return merchant_one.id, merchant_two.id


def test_merchant_management_actions(auth_client: TestClient) -> None:
    headers = _auth_headers(auth_client)
    merchant_one_id, merchant_two_id = _seed_merchant_data()

    list_response = auth_client.get("/api/merchants", headers=headers)
    assert list_response.status_code == 200
    merchants = list_response.json()
    assert merchants[0]["transaction_count"] >= 1

    update_response = auth_client.patch(
        f"/api/merchants/{merchant_one_id}",
        headers=headers,
        json={
            "display_name": "Daily Coffee",
            "category": "Cafe",
            "status": "reviewed",
            "is_transfer": False,
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["display_name"] == "Daily Coffee"
    assert update_response.json()["category"] == "Cafe"

    alias_response = auth_client.post(
        f"/api/merchants/{merchant_one_id}/aliases",
        headers=headers,
        json={"alias": "COFFEE SHOP TORONTO"},
    )
    assert alias_response.status_code == 201

    recategorize_response = auth_client.post(
        f"/api/merchants/{merchant_one_id}/recategorize",
        headers=headers,
    )
    assert recategorize_response.status_code == 200
    assert recategorize_response.json()["updated_count"] == 2

    bulk_category_response = auth_client.post(
        "/api/merchants/bulk-category",
        headers=headers,
        json={"merchant_ids": [merchant_one_id, merchant_two_id], "category": "Reviewed"},
    )
    assert bulk_category_response.status_code == 200
    assert bulk_category_response.json()["updated_count"] == 2

    merge_response = auth_client.post(
        f"/api/merchants/{merchant_two_id}/merge",
        headers=headers,
        json={"target_merchant_id": merchant_one_id},
    )
    assert merge_response.status_code == 200

    aliases_list = auth_client.get("/api/merchant-aliases", headers=headers)
    assert aliases_list.status_code == 200
    alias_id = aliases_list.json()[0]["id"]

    delete_alias = auth_client.delete(f"/api/merchant-aliases/{alias_id}", headers=headers)
    assert delete_alias.status_code == 204

    merchants_after_merge = auth_client.get("/api/merchants", headers=headers)
    assert merchants_after_merge.status_code == 200
    assert len(merchants_after_merge.json()) == 1

    transactions = auth_client.get("/api/transactions", headers=headers)
    assert transactions.status_code == 200
    assert all(item["merchant_id"] == merchant_one_id for item in transactions.json())
