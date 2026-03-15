from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.config import settings

app = FastAPI(title="Private Ledger")


@app.get("/api/health")
def healthcheck() -> JSONResponse:
    return JSONResponse({"status": "ok"})


def _frontend_dist() -> Path:
    return settings.frontend_dist_dir


if (_frontend_dist() / "assets").exists():
    app.mount(
        "/assets",
        StaticFiles(directory=_frontend_dist() / "assets"),
        name="frontend-assets",
    )


@app.get("/", include_in_schema=False, response_model=None)
@app.get("/{full_path:path}", include_in_schema=False, response_model=None)
def frontend_app(full_path: str = "") -> Response:
    if full_path.startswith("api/"):
        return JSONResponse({"detail": "Not Found"}, status_code=404)

    index_file = _frontend_dist() / "index.html"
    if index_file.exists():
        return FileResponse(index_file)

    return JSONResponse(
        {
            "message": "Frontend assets have not been built yet.",
            "expectedPath": str(index_file),
        },
        status_code=503,
    )
