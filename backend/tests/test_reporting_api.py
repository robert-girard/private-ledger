from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select

import app.db.session
from app.db.models import Budget, Merchant, Transaction, User


def _auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "secret-pass"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _seed_reporting_data() -> None:
    with app.db.session.SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == "admin@example.com"))
        assert user is not None

        salary = Merchant(raw_name="PAYROLL", display_name="Payroll", category="Income", status="reviewed")
        grocery = Merchant(raw_name="FRESH MART", display_name="Fresh Mart", category="Groceries", status="reviewed")
        dining = Merchant(raw_name="NOODLE BAR", display_name="Noodle Bar", category="Dining", status="reviewed")
        transfer = Merchant(
            raw_name="CHEQUING TRANSFER",
            display_name="Internal Transfer",
            category=None,
            status="reviewed",
            is_transfer=True,
        )
        session.add_all([salary, grocery, dining, transfer])
        session.flush()

        session.add_all(
            [
                Budget(
                    user_id=user.id,
                    month_start=date(2026, 2, 1),
                    category="Groceries",
                    planned_amount=Decimal("150.00"),
                    spent_amount=Decimal("0.00"),
                    is_active=False,
                ),
                Budget(
                    user_id=user.id,
                    month_start=date(2026, 3, 1),
                    category="Dining",
                    planned_amount=Decimal("90.00"),
                    spent_amount=Decimal("0.00"),
                    is_active=True,
                ),
                Budget(
                    user_id=user.id,
                    month_start=date(2026, 3, 1),
                    category="Groceries",
                    planned_amount=Decimal("160.00"),
                    spent_amount=Decimal("0.00"),
                    is_active=True,
                ),
            ]
        )

        rows = [
            (salary, date(2026, 2, 1), "2800.00", "Income", "report-dedupe-1"),
            (grocery, date(2026, 2, 3), "-120.00", "Groceries", "report-dedupe-2"),
            (dining, date(2026, 2, 10), "-45.00", "Dining", "report-dedupe-3"),
            (transfer, date(2026, 2, 12), "-500.00", None, "report-dedupe-4"),
            (salary, date(2026, 3, 1), "2900.00", "Income", "report-dedupe-5"),
            (grocery, date(2026, 3, 4), "-135.00", "Groceries", "report-dedupe-6"),
            (dining, date(2026, 3, 5), "-55.00", "Dining", "report-dedupe-7"),
            (dining, date(2026, 3, 20), "-20.00", None, "report-dedupe-8"),
            (transfer, date(2026, 3, 22), "500.00", None, "report-dedupe-9"),
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


def test_reporting_endpoints_apply_date_filters_and_aggregate_categories(auth_client: TestClient) -> None:
    headers = _auth_headers(auth_client)
    _seed_reporting_data()

    summary_response = auth_client.get(
        "/api/reports/summary",
        headers=headers,
        params={"start_date": "2026-03-01", "end_date": "2026-03-31"},
    )
    assert summary_response.status_code == 200
    assert summary_response.json() == {
        "start_date": "2026-03-01",
        "end_date": "2026-03-31",
        "income_total": "2900.00",
        "expense_total": "210.00",
        "net_total": "2690.00",
    }

    money_flow_response = auth_client.get(
        "/api/reports/money-flow",
        headers=headers,
        params={"start_date": "2026-02-01", "end_date": "2026-03-31"},
    )
    assert money_flow_response.status_code == 200
    money_flow = money_flow_response.json()
    assert {"direction": "income", "category": "Income", "amount": "5700.00"} in money_flow
    assert {"direction": "expense", "category": "Groceries", "amount": "255.00"} in money_flow
    assert all(item["amount"] != "1000.00" for item in money_flow)

    category_breakdown_response = auth_client.get(
        "/api/reports/category-breakdown",
        headers=headers,
        params={"start_date": "2026-03-01", "end_date": "2026-03-31"},
    )
    assert category_breakdown_response.status_code == 200
    category_breakdown = category_breakdown_response.json()
    assert category_breakdown == [
        {"category": "Groceries", "amount": "135.00", "transaction_count": 1, "share": "0.64"},
        {"category": "Dining", "amount": "55.00", "transaction_count": 1, "share": "0.26"},
        {"category": "Uncategorized", "amount": "20.00", "transaction_count": 1, "share": "0.10"},
    ]

    monthly_trend_response = auth_client.get("/api/reports/monthly-trend", headers=headers)
    assert monthly_trend_response.status_code == 200
    assert monthly_trend_response.json() == [
        {"month_start": "2026-02-01", "income_total": "2800.00", "expense_total": "165.00", "net_total": "2635.00"},
        {"month_start": "2026-03-01", "income_total": "2900.00", "expense_total": "210.00", "net_total": "2690.00"},
    ]

    budget_vs_actual_response = auth_client.get(
        "/api/reports/budget-vs-actual",
        headers=headers,
        params={"start_date": "2026-03-01", "end_date": "2026-03-31"},
    )
    assert budget_vs_actual_response.status_code == 200
    assert budget_vs_actual_response.json() == [
        {
            "month_start": "2026-03-01",
            "category": "Dining",
            "planned_amount": "90.00",
            "actual_amount": "55.00",
            "variance_amount": "35.00",
        },
        {
            "month_start": "2026-03-01",
            "category": "Groceries",
            "planned_amount": "160.00",
            "actual_amount": "135.00",
            "variance_amount": "25.00",
        },
    ]

    top_merchants_response = auth_client.get(
        "/api/reports/top-merchants",
        headers=headers,
        params={"start_date": "2026-02-01", "end_date": "2026-03-31", "limit": 2},
    )
    assert top_merchants_response.status_code == 200
    assert top_merchants_response.json() == [
        {
            "merchant_id": top_merchants_response.json()[0]["merchant_id"],
            "merchant_name": "Fresh Mart",
            "category": "Groceries",
            "amount": "255.00",
            "transaction_count": 2,
        },
        {
            "merchant_id": top_merchants_response.json()[1]["merchant_id"],
            "merchant_name": "Noodle Bar",
            "category": "Dining",
            "amount": "120.00",
            "transaction_count": 3,
        },
    ]

    export_response = auth_client.get(
        "/api/reports/top-merchants/export",
        headers=headers,
        params={"start_date": "2026-02-01", "end_date": "2026-03-31", "limit": 2},
    )
    assert export_response.status_code == 200
    assert "merchant_id,merchant_name,category,amount,transaction_count" in export_response.text
    assert "Fresh Mart" in export_response.text
    assert "Noodle Bar" in export_response.text


def test_reporting_rejects_invalid_date_ranges(auth_client: TestClient) -> None:
    headers = _auth_headers(auth_client)
    response = auth_client.get(
        "/api/reports/summary",
        headers=headers,
        params={"start_date": "2026-04-01", "end_date": "2026-03-01"},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "start_date must be on or before end_date."
