from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select

import app.db.session
from app.db.models import Budget, Merchant, Subscription, Transaction, User


def _auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "secret-pass"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _seed_dashboard_data() -> None:
    with app.db.session.SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == "admin@example.com"))
        assert user is not None

        grocery = Merchant(raw_name="FRESH MART", display_name="Fresh Mart", category="Groceries", status="reviewed")
        dining = Merchant(raw_name="NOODLE BAR", display_name="Noodle Bar", category="Dining", status="reviewed")
        netflix = Merchant(raw_name="NETFLIX", display_name="Netflix", category="Streaming", status="reviewed")
        insurance = Merchant(
            raw_name="TENANT INSURANCE",
            display_name="Tenant Insurance",
            category="Insurance",
            status="reviewed",
        )
        transfer = Merchant(
            raw_name="E-TRANSFER",
            display_name="Internal Transfer",
            category=None,
            status="unreviewed",
            is_transfer=True,
        )
        session.add_all([grocery, dining, netflix, insurance, transfer])
        session.flush()

        session.add_all(
            [
                Budget(
                    user_id=user.id,
                    month_start=date(2026, 4, 1),
                    category="Groceries",
                    planned_amount=Decimal("125.00"),
                    spent_amount=Decimal("0.00"),
                    is_active=True,
                ),
                Budget(
                    user_id=user.id,
                    month_start=date(2026, 4, 1),
                    category="Dining",
                    planned_amount=Decimal("75.00"),
                    spent_amount=Decimal("0.00"),
                    is_active=True,
                ),
                Budget(
                    user_id=user.id,
                    month_start=date(2026, 4, 1),
                    category="Insurance",
                    planned_amount=Decimal("120.00"),
                    spent_amount=Decimal("0.00"),
                    is_active=True,
                ),
                Budget(
                    user_id=user.id,
                    month_start=date(2026, 4, 1),
                    category="Streaming",
                    planned_amount=Decimal("15.99"),
                    spent_amount=Decimal("0.00"),
                    is_active=True,
                ),
            ]
        )

        session.add_all(
            [
                Subscription(
                    user_id=user.id,
                    merchant_id=netflix.id,
                    display_name="Netflix",
                    category="Streaming",
                    interval="monthly",
                    amount=Decimal("15.99"),
                    is_active=True,
                    next_expected_on=date(2026, 4, 4),
                ),
                Subscription(
                    user_id=user.id,
                    merchant_id=insurance.id,
                    display_name="Tenant Insurance",
                    category="Insurance",
                    interval="annual",
                    amount=Decimal("120.00"),
                    is_active=True,
                    next_expected_on=date(2026, 4, 14),
                ),
            ]
        )

        rows = [
            (grocery, date(2026, 4, 10), "-120.00", "Groceries", "dashboard-dedupe-1"),
            (dining, date(2026, 4, 5), "-30.00", "Dining", "dashboard-dedupe-2"),
            (transfer, date(2026, 4, 12), "-200.00", None, "dashboard-dedupe-3"),
            (netflix, date(2026, 4, 4), "-15.99", "Streaming", "dashboard-dedupe-4"),
            (insurance, date(2026, 4, 14), "-120.00", "Insurance", "dashboard-dedupe-5"),
            (grocery, date(2026, 4, 1), "2500.00", "Income", "dashboard-dedupe-6"),
        ]
        for merchant, posted_on, amount, category, dedupe_hash in rows:
            session.add(
                Transaction(
                    user_id=user.id,
                    merchant_id=merchant.id,
                    posted_on=posted_on,
                    description=merchant.raw_name,
                    normalized_description=merchant.raw_name.lower(),
                    amount=Decimal(amount),
                    currency="CAD",
                    category=category,
                    dedupe_hash=dedupe_hash,
                )
            )
        session.commit()


def test_dashboard_summary_burn_down_and_attention(auth_client: TestClient) -> None:
    headers = _auth_headers(auth_client)
    _seed_dashboard_data()

    summary_response = auth_client.get("/api/dashboard/summary", headers=headers)
    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["month_start"] == "2026-04-01"
    assert summary["total_budgeted"] == "335.99"
    assert summary["spent_to_date"] == "285.99"
    assert summary["projected_month_end"] == "612.84"

    burn_down_response = auth_client.get("/api/dashboard/burn-down", headers=headers)
    assert burn_down_response.status_code == 200
    burn_down = {item["category"]: item for item in burn_down_response.json()}
    assert burn_down["Groceries"]["status"] == "warning"
    assert burn_down["Groceries"]["spent_amount"] == "120.00"
    assert burn_down["Dining"]["status"] == "safe"
    assert burn_down["Insurance"]["status"] == "over"

    attention_response = auth_client.get("/api/dashboard/attention", headers=headers)
    assert attention_response.status_code == 200
    attention = attention_response.json()
    assert [item["display_name"] for item in attention["upcoming_subscriptions"]] == ["Netflix", "Tenant Insurance"]
    assert all(item["merchant_name"] != "Internal Transfer" for item in attention["recent_transactions"])
    assert attention["unreviewed_merchant_count"] == 1
