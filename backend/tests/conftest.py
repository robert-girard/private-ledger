from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.config
import app.db.session
import app.main
from app.config import Settings
from app.db.migrations import initialize_database
from app.db.session import configure_session_factory
from app.services.users import BootstrapAdminInput, bootstrap_initial_admin


@pytest.fixture()
def auth_client(tmp_path: Path) -> Generator[TestClient, None, None]:
    database_url = f"sqlite:///{tmp_path / 'auth.db'}"
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
        frontend_dist_dir=Path("frontend/dist"),
    )

    app.config.settings = test_settings
    initialize_database(database_url)
    configure_session_factory(database_url)

    with app.db.session.SessionLocal() as session:
        bootstrap_initial_admin(
            session=session,
            admin=BootstrapAdminInput(
                email="admin@example.com",
                display_name="Admin",
                password="secret-pass",
            ),
            pepper=test_settings.password_pepper,
        )

    with TestClient(app.main.app) as client:
        yield client

    app.config.settings = original_settings
    configure_session_factory(original_settings.database_url)
