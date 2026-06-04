"""FailProbe REST API application.

Wires together the route modules, CORS, lifespan-driven DB initialization, a
standardized error envelope, and optional API-key auth. The API is a thin HTTP
layer: it imports behavior from the ``failprobe`` package and contains no
business logic of its own.
"""

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from failprobe.storage import init_db
from api.routes import compare, eval, failures, golden, review, runs

VERSION = "0.2.0"

# Paths that never require an API key (and never need the DB).
_AUTH_EXEMPT = frozenset({"/health", "/docs", "/redoc", "/openapi.json"})

# CORS origins: the Next.js dashboard (3000) and the Streamlit dashboard (8501).
_CORS_ORIGINS = ["http://localhost:3000", "http://localhost:8501"]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create database tables on startup (idempotent)."""
    await init_db()
    yield


app = FastAPI(title="FailProbe API", version=VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def api_key_auth(request: Request, call_next):
    """Require ``X-API-Key`` on non-exempt routes when an API key is configured.

    Auth is disabled entirely unless ``FAILPROBE_API_KEY`` is set in the
    environment. When set, any non-exempt request missing or mismatching the
    ``X-API-Key`` header is rejected with the standard 401 error envelope.
    """
    api_key = os.environ.get("FAILPROBE_API_KEY")
    if api_key and request.url.path not in _AUTH_EXEMPT:
        if request.headers.get("X-API-Key") != api_key:
            return JSONResponse(
                status_code=401,
                content={
                    "error": "unauthorized",
                    "message": "Invalid or missing API key",
                    "status_code": 401,
                },
            )
    return await call_next(request)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Render every HTTPException as ``{error, message, status_code}``.

    When a route raises with a ``dict`` detail it is expected to carry ``error``
    and ``message`` keys; a plain-string detail is wrapped with a generic slug.
    """
    detail = exc.detail
    if isinstance(detail, dict):
        error = detail.get("error", "error")
        message = detail.get("message", "")
    else:
        error = "http_error"
        message = str(detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": error, "message": message, "status_code": exc.status_code},
    )


@app.get("/health", tags=["health"])
async def health() -> dict:
    """Liveness probe; works without a database connection."""
    return {"status": "ok", "version": VERSION}


app.include_router(runs.router)
app.include_router(failures.router)
app.include_router(eval.router)
app.include_router(compare.router)
app.include_router(golden.router)
app.include_router(review.router)
