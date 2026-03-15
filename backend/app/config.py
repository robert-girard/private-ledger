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
    login_rate_limit_window_seconds: int
    login_rate_limit_max_attempts: int
    refresh_rate_limit_window_seconds: int
    refresh_rate_limit_max_attempts: int
    auth_lockout_threshold: int
    auth_lockout_window_seconds: int
    auth_lockout_duration_seconds: int
    content_security_policy: str
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
    login_rate_limit_window_seconds=int(os.getenv("LOGIN_RATE_LIMIT_WINDOW_SECONDS", "60")),
    login_rate_limit_max_attempts=int(os.getenv("LOGIN_RATE_LIMIT_MAX_ATTEMPTS", "5")),
    refresh_rate_limit_window_seconds=int(os.getenv("REFRESH_RATE_LIMIT_WINDOW_SECONDS", "60")),
    refresh_rate_limit_max_attempts=int(os.getenv("REFRESH_RATE_LIMIT_MAX_ATTEMPTS", "10")),
    auth_lockout_threshold=int(os.getenv("AUTH_LOCKOUT_THRESHOLD", "3")),
    auth_lockout_window_seconds=int(os.getenv("AUTH_LOCKOUT_WINDOW_SECONDS", "300")),
    auth_lockout_duration_seconds=int(os.getenv("AUTH_LOCKOUT_DURATION_SECONDS", "300")),
    content_security_policy=os.getenv(
        "CONTENT_SECURITY_POLICY",
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'",
    ),
    frontend_dist_dir=Path(__file__).resolve().parents[2] / "frontend" / "dist",
)


def get_settings() -> Settings:
    return settings
