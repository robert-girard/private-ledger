from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    app_host: str
    app_port: int
    database_url: str
    import_storage_dir: Path
    password_pepper: str
    auth_secret_key: str
    access_token_ttl_minutes: int
    refresh_token_ttl_days: int
    frontend_dist_dir: Path


settings = Settings(
    app_host=os.getenv("APP_HOST", "0.0.0.0"),
    app_port=int(os.getenv("APP_PORT", "8000")),
    database_url=os.getenv(
        "DATABASE_URL",
        f"sqlite:///{(Path(__file__).resolve().parents[2] / 'data' / 'private-ledger.db')}",
    ),
    import_storage_dir=Path(
        os.getenv(
            "IMPORT_STORAGE_DIR",
            str(Path(__file__).resolve().parents[2] / "data" / "imports-temp"),
        )
    ),
    password_pepper=os.getenv("PASSWORD_PEPPER", "development-only-pepper"),
    auth_secret_key=os.getenv("AUTH_SECRET_KEY", "development-auth-secret"),
    access_token_ttl_minutes=int(os.getenv("ACCESS_TOKEN_TTL_MINUTES", "15")),
    refresh_token_ttl_days=int(os.getenv("REFRESH_TOKEN_TTL_DAYS", "14")),
    frontend_dist_dir=Path(__file__).resolve().parents[2] / "frontend" / "dist",
)


def get_settings() -> Settings:
    return settings
