from __future__ import annotations

import sqlite3
from pathlib import Path

from app.db.migrations import initialize_database


def table_names(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    return {row[0] for row in rows}


def test_initialize_database_creates_baseline_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "private-ledger.db"

    initialize_database(f"sqlite:///{db_path}")

    assert table_names(db_path) >= {
        "budgets",
        "imports",
        "merchant_aliases",
        "merchants",
        "refresh_token_blocklist",
        "schema_migrations",
        "subscriptions",
        "transactions",
        "users",
    }


def test_initialize_database_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "private-ledger.db"
    database_url = f"sqlite:///{db_path}"

    initialize_database(database_url)
    initialize_database(database_url)

    with sqlite3.connect(db_path) as connection:
        versions = connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()

    assert versions == [("0001_baseline",)]
