from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select

import app.db.session
from app.db.models import Merchant, Subscription, Transaction, User


def _auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "secret-pass"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _seed_subscription_history() -> tuple[str, str, str]:
    with app.db.session.SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == "admin@example.com"))
        assert user is not None

        monthly_merchant = Merchant(
            raw_name="NETFLIX",
            display_name="Netflix",
            category="Streaming",
            status="reviewed",
        )
        annual_merchant = Merchant(
            raw_name="TENANT INSURANCE",
            display_name="Tenant Insurance",
            category="Insurance",
            status="reviewed",
        )
        variable_merchant = Merchant(
            raw_name="HYDRO ONE",
            display_name="Hydro One",
            category="Utilities",
            status="reviewed",
        )
        manual_merchant = Merchant(
            raw_name="CITY GYM",
            display_name="City Gym",
            category="Fitness",
            status="reviewed",
        )
        session.add_all([monthly_merchant, annual_merchant, variable_merchant, manual_merchant])
        session.flush()

        transactions = [
            Transaction(
                user_id=user.id,
                merchant_id=monthly_merchant.id,
                posted_on=date(2026, 1, 5),
                description="NETFLIX",
                normalized_description="netflix",
                amount=Decimal("-15.99"),
                currency="CAD",
                category="Streaming",
                dedupe_hash="subscription-dedupe-1",
            ),
            Transaction(
                user_id=user.id,
                merchant_id=monthly_merchant.id,
                posted_on=date(2026, 2, 5),
                description="NETFLIX",
                normalized_description="netflix",
                amount=Decimal("-15.99"),
                currency="CAD",
                category="Streaming",
                dedupe_hash="subscription-dedupe-2",
            ),
            Transaction(
                user_id=user.id,
                merchant_id=monthly_merchant.id,
                posted_on=date(2026, 3, 5),
                description="NETFLIX",
                normalized_description="netflix",
                amount=Decimal("-15.99"),
                currency="CAD",
                category="Streaming",
                dedupe_hash="subscription-dedupe-3",
            ),
            Transaction(
                user_id=user.id,
                merchant_id=annual_merchant.id,
                posted_on=date(2025, 4, 15),
                description="TENANT INSURANCE",
                normalized_description="tenant insurance",
                amount=Decimal("-120.00"),
                currency="CAD",
                category="Insurance",
                dedupe_hash="subscription-dedupe-4",
            ),
            Transaction(
                user_id=user.id,
                merchant_id=annual_merchant.id,
                posted_on=date(2026, 4, 14),
                description="TENANT INSURANCE",
                normalized_description="tenant insurance",
                amount=Decimal("-120.00"),
                currency="CAD",
                category="Insurance",
                dedupe_hash="subscription-dedupe-5",
            ),
            Transaction(
                user_id=user.id,
                merchant_id=variable_merchant.id,
                posted_on=date(2026, 1, 10),
                description="HYDRO ONE",
                normalized_description="hydro one",
                amount=Decimal("-40.00"),
                currency="CAD",
                category="Utilities",
                dedupe_hash="subscription-dedupe-6",
            ),
            Transaction(
                user_id=user.id,
                merchant_id=variable_merchant.id,
                posted_on=date(2026, 2, 10),
                description="HYDRO ONE",
                normalized_description="hydro one",
                amount=Decimal("-45.00"),
                currency="CAD",
                category="Utilities",
                dedupe_hash="subscription-dedupe-7",
            ),
            Transaction(
                user_id=user.id,
                merchant_id=variable_merchant.id,
                posted_on=date(2026, 3, 10),
                description="HYDRO ONE",
                normalized_description="hydro one",
                amount=Decimal("-50.00"),
                currency="CAD",
                category="Utilities",
                dedupe_hash="subscription-dedupe-8",
            ),
            Transaction(
                user_id=user.id,
                merchant_id=manual_merchant.id,
                posted_on=date(2026, 3, 3),
                description="CITY GYM",
                normalized_description="city gym",
                amount=Decimal("-60.00"),
                currency="CAD",
                category="Fitness",
                dedupe_hash="subscription-dedupe-9",
            ),
            Transaction(
                user_id=user.id,
                merchant_id=manual_merchant.id,
                posted_on=date(2026, 3, 15),
                description="PAYROLL",
                normalized_description="payroll",
                amount=Decimal("2400.00"),
                currency="CAD",
                category="Income",
                dedupe_hash="subscription-dedupe-10",
            ),
        ]
        session.add_all(transactions)
        session.commit()
        return monthly_merchant.id, annual_merchant.id, manual_merchant.id


def test_subscription_detection_persists_monthly_annual_and_variable_patterns(auth_client: TestClient) -> None:
    headers = _auth_headers(auth_client)
    monthly_merchant_id, annual_merchant_id, _ = _seed_subscription_history()

    detect_response = auth_client.post("/api/subscriptions/detect", headers=headers)
    assert detect_response.status_code == 200
    payload = detect_response.json()
    assert payload["detected_count"] == 3

    subscriptions_by_name = {item["display_name"]: item for item in payload["subscriptions"]}
    assert subscriptions_by_name["Netflix"]["interval"] == "monthly"
    assert subscriptions_by_name["Netflix"]["amount"] == "15.99"
    assert subscriptions_by_name["Netflix"]["merchant_id"] == monthly_merchant_id
    assert subscriptions_by_name["Tenant Insurance"]["interval"] == "annual"
    assert subscriptions_by_name["Tenant Insurance"]["merchant_id"] == annual_merchant_id
    assert subscriptions_by_name["Hydro One"]["interval"] == "variable"
    assert subscriptions_by_name["Hydro One"]["amount"] == "45.00"

    repeat_detect = auth_client.post("/api/subscriptions/detect", headers=headers)
    assert repeat_detect.status_code == 200
    assert repeat_detect.json()["detected_count"] == 3

    list_response = auth_client.get("/api/subscriptions", headers=headers)
    assert list_response.status_code == 200
    assert len(list_response.json()) == 3

    netflix_id = subscriptions_by_name["Netflix"]["id"]
    detail_response = auth_client.get(f"/api/subscriptions/{netflix_id}", headers=headers)
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["recent_match_transaction_id"] is not None
    assert [item["posted_on"] for item in detail["recent_matches"]] == ["2026-03-05", "2026-02-05", "2026-01-05"]

    with app.db.session.SessionLocal() as session:
        persisted = session.scalars(select(Subscription).order_by(Subscription.display_name.asc())).all()
        assert [item.display_name for item in persisted] == ["Hydro One", "Netflix", "Tenant Insurance"]


def test_manual_subscription_create_and_update(auth_client: TestClient) -> None:
    headers = _auth_headers(auth_client)
    _, _, manual_merchant_id = _seed_subscription_history()

    create_response = auth_client.post(
        "/api/subscriptions",
        headers=headers,
        json={
            "display_name": "Gym Membership",
            "category": "Fitness",
            "interval": "monthly",
            "amount": "60.00",
            "is_active": False,
            "merchant_id": manual_merchant_id,
            "last_charged_on": "2026-03-03",
            "next_expected_on": "2026-04-02",
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["merchant_id"] == manual_merchant_id
    assert created["is_active"] is False

    update_response = auth_client.patch(
        f"/api/subscriptions/{created['id']}",
        headers=headers,
        json={
            "display_name": "City Gym Membership",
            "category": "Health",
            "interval": "annual",
            "amount": "600.00",
            "is_active": True,
            "merchant_id": manual_merchant_id,
            "last_charged_on": "2026-03-03",
            "next_expected_on": "2027-03-03",
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["display_name"] == "City Gym Membership"
    assert updated["category"] == "Health"
    assert updated["interval"] == "annual"
    assert updated["amount"] == "600.00"
    assert updated["is_active"] is True

    detail_response = auth_client.get(f"/api/subscriptions/{created['id']}", headers=headers)
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["recent_matches"][0]["description"] == "CITY GYM"
