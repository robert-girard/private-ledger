from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Migration:
    version: str
    path: Path


def migrations_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "migrations"


def database_path_from_url(database_url: str) -> str:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError(f"Unsupported database URL: {database_url}")

    raw_path = database_url.removeprefix(prefix)
    return ":memory:" if raw_path == ":memory:" else str(Path(raw_path))


def available_migrations(directory: Path | None = None) -> list[Migration]:
    selected_dir = directory or migrations_dir()
    return [
        Migration(version=path.stem, path=path)
        for path in sorted(selected_dir.glob("*.sql"))
    ]


def initialize_database(database_url: str, directory: Path | None = None) -> None:
    db_path = database_path_from_url(database_url)
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
              version TEXT PRIMARY KEY,
              applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        applied_versions = {
            row[0] for row in connection.execute("SELECT version FROM schema_migrations")
        }

        for migration in available_migrations(directory):
            if migration.version in applied_versions:
                continue

            connection.executescript(migration.path.read_text())
            connection.execute(
                "INSERT INTO schema_migrations (version) VALUES (?)",
                (migration.version,),
            )
        connection.commit()
