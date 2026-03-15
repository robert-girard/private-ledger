from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    app_host: str
    app_port: int
    frontend_dist_dir: Path


settings = Settings(
    app_host=os.getenv("APP_HOST", "0.0.0.0"),
    app_port=int(os.getenv("APP_PORT", "8000")),
    frontend_dist_dir=Path(__file__).resolve().parents[2] / "frontend" / "dist",
)
