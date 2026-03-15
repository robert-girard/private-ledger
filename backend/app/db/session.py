from __future__ import annotations

import sqlite3
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings


def _sqlite_path(database_url: str) -> Path:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError(f"Unsupported database URL: {database_url}")

    raw_path = database_url.removeprefix(prefix)
    return Path(raw_path)


def create_engine_for_url(database_url: str) -> Engine:
    sqlite_path = _sqlite_path(database_url)
    if sqlite_path != Path(":memory:"):
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False},
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection: sqlite3.Connection, _connection_record: object) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    return engine


engine = create_engine_for_url(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
