from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.migrations import initialize_database
from app.db.models import User
from app.security.passwords import hash_password, verify_password
from app.services.users import BootstrapAdminError, BootstrapAdminInput, bootstrap_initial_admin


def session_for_database(tmp_path: Path) -> Session:
    db_path = tmp_path / "private-ledger.db"
    initialize_database(f"sqlite:///{db_path}")
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    session_factory = sessionmaker(bind=engine, future=True)
    return session_factory()


def test_hash_password_uses_salt_and_pepper() -> None:
    record = hash_password(password="correct horse battery staple", pepper="pepper")

    assert record.password_hash
    assert record.password_salt
    assert verify_password(
        password="correct horse battery staple",
        pepper="pepper",
        password_hash=record.password_hash,
        password_salt=record.password_salt,
    )
    assert not verify_password(
        password="wrong password",
        pepper="pepper",
        password_hash=record.password_hash,
        password_salt=record.password_salt,
    )
    assert not verify_password(
        password="correct horse battery staple",
        pepper="different-pepper",
        password_hash=record.password_hash,
        password_salt=record.password_salt,
    )


def test_bootstrap_initial_admin_persists_password_material(tmp_path: Path) -> None:
    with session_for_database(tmp_path) as session:
        user = bootstrap_initial_admin(
            session=session,
            admin=BootstrapAdminInput(
                email="admin@example.com",
                display_name="Admin",
                password="super-secret",
            ),
            pepper="pepper",
        )

        stored_user = session.scalar(select(User).where(User.id == user.id))

    assert stored_user is not None
    assert stored_user.is_admin is True
    assert stored_user.password_hash is not None
    assert stored_user.password_salt is not None
    assert verify_password(
        password="super-secret",
        pepper="pepper",
        password_hash=stored_user.password_hash,
        password_salt=stored_user.password_salt,
    )


def test_bootstrap_initial_admin_rejects_existing_users(tmp_path: Path) -> None:
    with session_for_database(tmp_path) as session:
        bootstrap_initial_admin(
            session=session,
            admin=BootstrapAdminInput(
                email="admin@example.com",
                display_name="Admin",
                password="super-secret",
            ),
            pepper="pepper",
        )

        with pytest.raises(BootstrapAdminError):
            bootstrap_initial_admin(
                session=session,
                admin=BootstrapAdminInput(
                    email="second@example.com",
                    display_name="Second Admin",
                    password="another-secret",
                ),
                pepper="pepper",
            )


def test_security_headers_are_attached_to_api_responses(auth_client: TestClient) -> None:
    response = auth_client.get("/api/health")

    assert response.status_code == 200
    assert response.headers["content-security-policy"] == "default-src 'self'"
    assert response.headers["strict-transport-security"] == "max-age=63072000; includeSubDomains"
