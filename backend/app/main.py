from __future__ import annotations

from collections.abc import AsyncIterator
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.api.auth import router as auth_router
from app.api.ledger import router as ledger_router
from app.config import get_settings
from app.db.migrations import initialize_database

@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    initialize_database(get_settings().database_url)
    yield


app = FastAPI(title="Private Ledger", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(ledger_router)


@app.middleware("http")
async def add_security_headers(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    response = await call_next(request)
    settings = get_settings()
    response.headers["Content-Security-Policy"] = settings.content_security_policy
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response


@app.get("/api/health")
def healthcheck() -> JSONResponse:
    return JSONResponse({"status": "ok"})


def _frontend_dist() -> Path:
    return get_settings().frontend_dist_dir


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
