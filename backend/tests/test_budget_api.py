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


def _seed_budget_history() -> date:
    with app.db.session.SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == "admin@example.com"))
        assert user is not None

        netflix = Merchant(raw_name="NETFLIX", display_name="Netflix", category="Streaming", status="reviewed")
        insurance = Merchant(
            raw_name="TENANT INSURANCE",
            display_name="Tenant Insurance",
            category="Insurance",
            status="reviewed",
        )
        grocery = Merchant(raw_name="FRESH MART", display_name="Fresh Mart", category="Groceries", status="reviewed")
        dining = Merchant(raw_name="NOODLE BAR", display_name="Noodle Bar", category="Dining", status="reviewed")
        transfer = Merchant(
            raw_name="E-TRANSFER",
            display_name="Internal Transfer",
            category=None,
            status="reviewed",
            is_transfer=True,
        )
        session.add_all([netflix, insurance, grocery, dining, transfer])
        session.flush()

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
                    last_charged_on=date(2026, 3, 5),
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
                    last_charged_on=date(2026, 4, 14),
                    next_expected_on=date(2027, 4, 14),
                ),
            ]
        )

        rows = [
            (grocery, date(2026, 1, 7), "-100.00", "Groceries", "budget-dedupe-1"),
            (grocery, date(2026, 2, 7), "-140.00", "Groceries", "budget-dedupe-2"),
            (grocery, date(2026, 3, 7), "-120.00", "Groceries", "budget-dedupe-3"),
            (dining, date(2026, 2, 12), "-60.00", "Dining", "budget-dedupe-4"),
            (dining, date(2026, 3, 15), "-90.00", "Dining", "budget-dedupe-5"),
            (netflix, date(2026, 1, 5), "-15.99", "Streaming", "budget-dedupe-6"),
            (netflix, date(2026, 2, 5), "-15.99", "Streaming", "budget-dedupe-7"),
            (netflix, date(2026, 3, 5), "-15.99", "Streaming", "budget-dedupe-8"),
            (transfer, date(2026, 3, 20), "-250.00", None, "budget-dedupe-9"),
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
    return date(2026, 4, 1)


def test_budget_generation_uses_active_subscriptions_and_variable_history(auth_client: TestClient) -> None:
    headers = _auth_headers(auth_client)
    month_start = _seed_budget_history()

    response = auth_client.post("/api/budgets/generate", headers=headers, json={"month_start": month_start.isoformat()})
    assert response.status_code == 200
    payload = response.json()
    assert payload["month_start"] == "2026-04-01"

    recommendations = {item["category"]: item for item in payload["recommendations"]}
    assert recommendations["Streaming"]["source_type"] == "subscription"
    assert recommendations["Streaming"]["planned_amount"] == "15.99"
    assert recommendations["Streaming"]["subscription_names"] == ["Netflix"]
    assert recommendations["Insurance"]["planned_amount"] == "120.00"
    assert recommendations["Groceries"]["source_type"] == "variable"
    assert recommendations["Groceries"]["planned_amount"] == "120.00"
    assert recommendations["Groceries"]["months_used"] == 3
    assert recommendations["Dining"]["planned_amount"] == "75.00"
    assert recommendations["Dining"]["months_used"] == 2
    assert "Internal Transfer" not in recommendations

    with app.db.session.SessionLocal() as session:
        budgets = session.scalars(select(Budget).where(Budget.month_start == month_start).order_by(Budget.category.asc())).all()
        assert [budget.category for budget in budgets] == ["Dining", "Groceries", "Insurance", "Streaming"]
        assert all(budget.is_active is False for budget in budgets)


def test_budget_activation_toggles_month_state(auth_client: TestClient) -> None:
    headers = _auth_headers(auth_client)
    month_start = _seed_budget_history()

    generate_response = auth_client.post("/api/budgets/generate", headers=headers, json={"month_start": month_start.isoformat()})
    assert generate_response.status_code == 200

    with app.db.session.SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == "admin@example.com"))
        assert user is not None
        session.add(
            Budget(
                user_id=user.id,
                month_start=date(2026, 3, 1),
                category="Legacy",
                planned_amount=Decimal("300.00"),
                spent_amount=Decimal("50.00"),
                is_active=True,
            )
        )
        session.commit()

    activate_response = auth_client.post("/api/budgets/activate", headers=headers, json={"month_start": month_start.isoformat()})
    assert activate_response.status_code == 200
    activated = activate_response.json()
    assert activated["activated_count"] == 4
    assert all(item["is_active"] is True for item in activated["budgets"])

    with app.db.session.SessionLocal() as session:
        active_budgets = session.scalars(select(Budget).where(Budget.is_active.is_(True)).order_by(Budget.month_start.asc())).all()
        assert {budget.month_start for budget in active_budgets} == {date(2026, 4, 1)}
