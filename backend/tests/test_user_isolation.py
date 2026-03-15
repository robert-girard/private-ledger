from __future__ import annotations

from collections.abc import Generator
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.config
import app.db.session
import app.main
from app.config import Settings
from app.db.migrations import initialize_database
from app.db.models import Budget, Import, Merchant, MerchantAlias, Subscription, Transaction, User
from app.db.session import configure_session_factory
from app.security.passwords import hash_password
from app.services.users import BootstrapAdminInput, bootstrap_initial_admin


@pytest.fixture()
def isolation_client(tmp_path: Path) -> Generator[TestClient, None, None]:
    database_url = f"sqlite:///{tmp_path / 'isolation.db'}"
    original_settings = app.config.settings
    test_settings = Settings(
        app_host="127.0.0.1",
        app_port=8000,
        database_url=database_url,
        import_storage_dir=tmp_path / "imports-temp",
        password_pepper="test-pepper",
        auth_secret_key="test-auth-secret",
        access_token_ttl_minutes=15,
        refresh_token_ttl_days=14,
        login_rate_limit_window_seconds=60,
        login_rate_limit_max_attempts=5,
        refresh_rate_limit_window_seconds=60,
        refresh_rate_limit_max_attempts=10,
        auth_lockout_threshold=3,
        auth_lockout_window_seconds=300,
        auth_lockout_duration_seconds=300,
        content_security_policy="default-src 'self'",
        frontend_dist_dir=Path("frontend/dist"),
    )

    app.config.settings = test_settings
    initialize_database(database_url)
    configure_session_factory(database_url)

    with app.db.session.SessionLocal() as session:
        user_one = bootstrap_initial_admin(
            session=session,
            admin=BootstrapAdminInput(
                email="user-one@example.com",
                display_name="User One",
                password="secret-pass",
            ),
            pepper=test_settings.password_pepper,
        )
        second_password = hash_password(password="second-pass", pepper=test_settings.password_pepper)
        user_two = User(
            email="user-two@example.com",
            display_name="User Two",
            password_hash=second_password.password_hash,
            password_salt=second_password.password_salt,
            is_admin=False,
            is_active=True,
        )
        merchant = Merchant(
            raw_name="RAW COFFEE",
            display_name="Raw Coffee",
            category="Dining",
            status="reviewed",
            is_transfer=False,
        )
        session.add_all(
            [
                user_two,
                merchant,
            ]
        )
        session.flush()

        alias = MerchantAlias(
            merchant_id=merchant.id,
            alias="RAW COFFEE TORONTO",
            normalized_alias="raw coffee toronto",
        )
        import_one = Import(
            user_id=user_one.id,
            source_filename="one.csv",
            source_bank="RBC",
            import_status="complete",
            row_count=1,
        )
        import_two = Import(
            user_id=user_two.id,
            source_filename="two.csv",
            source_bank="TD",
            import_status="complete",
            row_count=1,
        )
        session.add_all([alias, import_one, import_two])
        session.flush()

        transaction_one = Transaction(
            user_id=user_one.id,
            import_id=import_one.id,
            merchant_id=merchant.id,
            posted_on=date(2026, 3, 1),
            description="Coffee One",
            normalized_description="coffee one",
            amount=Decimal("12.34"),
            currency="CAD",
            category="Dining",
            dedupe_hash="user-one-hash",
        )
        transaction_two = Transaction(
            user_id=user_two.id,
            import_id=import_two.id,
            merchant_id=merchant.id,
            posted_on=date(2026, 3, 2),
            description="Coffee Two",
            normalized_description="coffee two",
            amount=Decimal("45.67"),
            currency="CAD",
            category="Dining",
            dedupe_hash="user-two-hash",
        )
        subscription_one = Subscription(
            user_id=user_one.id,
            merchant_id=merchant.id,
            display_name="Coffee Club",
            category="Dining",
            interval="monthly",
            amount=Decimal("9.99"),
            is_active=True,
        )
        subscription_two = Subscription(
            user_id=user_two.id,
            merchant_id=merchant.id,
            display_name="Tea Club",
            category="Dining",
            interval="monthly",
            amount=Decimal("19.99"),
            is_active=True,
        )
        budget_one = Budget(
            user_id=user_one.id,
            month_start=date(2026, 3, 1),
            category="Dining",
            planned_amount=Decimal("200.00"),
            spent_amount=Decimal("12.34"),
            is_active=True,
        )
        budget_two = Budget(
            user_id=user_two.id,
            month_start=date(2026, 3, 1),
            category="Dining",
            planned_amount=Decimal("100.00"),
            spent_amount=Decimal("45.67"),
            is_active=True,
        )
        session.add_all(
            [
                transaction_one,
                transaction_two,
                subscription_one,
                subscription_two,
                budget_one,
                budget_two,
            ]
        )
        session.commit()

    with TestClient(app.main.app) as client:
        yield client

    app.config.settings = original_settings
    configure_session_factory(original_settings.database_url)


def _access_token(client: TestClient, email: str, password: str) -> str:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_current_user_and_user_scoped_lists_only_return_owned_records(
    isolation_client: TestClient,
) -> None:
    access_token = _access_token(isolation_client, "user-one@example.com", "secret-pass")
    headers = _auth_headers(access_token)

    me_response = isolation_client.get("/api/me", headers=headers)
    transactions_response = isolation_client.get("/api/transactions", headers=headers)
    imports_response = isolation_client.get("/api/imports", headers=headers)
    subscriptions_response = isolation_client.get("/api/subscriptions", headers=headers)
    budgets_response = isolation_client.get("/api/budgets", headers=headers)
    merchants_response = isolation_client.get("/api/merchants", headers=headers)
    aliases_response = isolation_client.get("/api/merchant-aliases", headers=headers)

    assert me_response.status_code == 200
    assert me_response.json()["email"] == "user-one@example.com"
    assert [item["description"] for item in transactions_response.json()] == ["Coffee One"]
    assert [item["source_filename"] for item in imports_response.json()] == ["one.csv"]
    assert [item["display_name"] for item in subscriptions_response.json()] == ["Coffee Club"]
    assert [item["planned_amount"] for item in budgets_response.json()] == ["200.00"]
    assert [item["display_name"] for item in merchants_response.json()] == ["Raw Coffee"]
    assert [item["alias"] for item in aliases_response.json()] == ["RAW COFFEE TORONTO"]


def test_cross_user_detail_access_is_rejected(isolation_client: TestClient) -> None:
    access_token = _access_token(isolation_client, "user-one@example.com", "secret-pass")
    headers = _auth_headers(access_token)

    other_user_tx = isolation_client.post(
        "/api/auth/login",
        json={"email": "user-two@example.com", "password": "second-pass"},
    )
    assert other_user_tx.status_code == 200

    user_two_headers = _auth_headers(other_user_tx.json()["access_token"])
    transaction_id = isolation_client.get("/api/transactions", headers=user_two_headers).json()[0]["id"]
    import_id = isolation_client.get("/api/imports", headers=user_two_headers).json()[0]["id"]
    subscription_id = isolation_client.get("/api/subscriptions", headers=user_two_headers).json()[0]["id"]
    budget_id = isolation_client.get("/api/budgets", headers=user_two_headers).json()[0]["id"]

    assert isolation_client.get(f"/api/transactions/{transaction_id}", headers=headers).status_code == 404
    assert isolation_client.get(f"/api/imports/{import_id}", headers=headers).status_code == 404
    assert isolation_client.get(f"/api/subscriptions/{subscription_id}", headers=headers).status_code == 404
    assert isolation_client.get(f"/api/budgets/{budget_id}", headers=headers).status_code == 404


def test_access_token_is_required_for_scoped_routes(isolation_client: TestClient) -> None:
    response = isolation_client.get("/api/transactions")

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required."
