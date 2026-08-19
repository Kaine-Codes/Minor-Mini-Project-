"""FastAPI application factory.

One process serves both the JSON API and the built React dashboard. That is deliberate:
a single thing to start on demo day, no CORS in production, no second port to explain.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
# Starlette's base HTTPException, not FastAPI's subclass: unmatched-route 404s are
# raised by Starlette's router as the base class, so a handler registered only on the
# subclass would miss them and leak the default {"detail": ...} shape.
from starlette.exceptions import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .auth import validate_auth_config
from .config import Settings, get_settings
from .db import Database
from .deps import AppContext
from .hub import BroadcastHub
from .models import ApiResponse
from .node_client import NodeClient
from .poller import NodePoller, RetentionSweeper
from .repository import EventRepository, ReadingRepository
from .routes import auth as auth_routes
from .routes import config as config_routes
from .routes import control as control_routes
from .routes import readings as readings_routes

logger = logging.getLogger(__name__)


def _build_context(settings: Settings, db: Database) -> AppContext:
    readings = ReadingRepository(db)
    events = EventRepository(db)
    node = NodeClient(settings)
    hub = BroadcastHub()
    poller = NodePoller(
        client=node,
        readings=readings,
        events=events,
        hub=hub,
        interval_s=settings.poll_interval_s,
        offline_after_failures=settings.offline_after_failures,
    )
    retention = RetentionSweeper(
        readings=readings,
        events=events,
        retention_days=settings.retention_days,
        interval_s=settings.retention_sweep_interval_s,
    )
    return AppContext(
        readings=readings,
        events=events,
        node=node,
        hub=hub,
        poller=poller,
        retention=retention,
    )


def create_app(settings: Settings | None = None, *, start_workers: bool = True) -> FastAPI:
    """Build the application. ``start_workers=False`` keeps the loops off in tests."""
    resolved = settings or get_settings()
    validate_auth_config(resolved)  # fail fast rather than boot without credentials

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db = Database(resolved.db_path)
        await db.connect()
        context = _build_context(resolved, db)
        app.state.context = context
        app.state.settings = resolved
        logger.info(
            "ARIA %s ready — node candidates=%s, poll=%.1fs, retention=%dd",
            __version__,
            ",".join(resolved.node_hosts),
            resolved.poll_interval_s,
            resolved.retention_days,
        )
        if start_workers:
            context.poller.start()
            context.retention.start()
        try:
            yield
        finally:
            await context.poller.stop()
            await context.retention.stop()
            await context.node.aclose()
            await db.close()

    app = FastAPI(
        title="ARIA — Adaptive Room Intelligence & Automation",
        description=(
            "Local-first room automation. Sensor data and control logic stay on "
            "infrastructure the user owns; no third-party server sees the data."
        ),
        version=__version__,
        lifespan=lifespan,
    )

    # Only needed while the Vite dev server runs on a different port. In production the
    # dashboard is same-origin, so this grants nothing extra.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved.dev_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _register_error_handlers(app)

    app.include_router(auth_routes.router)
    app.include_router(readings_routes.router)
    app.include_router(control_routes.router)
    app.include_router(config_routes.router)

    @app.get("/api/health", tags=["meta"])
    async def health() -> ApiResponse:
        """Backend liveness. Distinct from the node's own /health."""
        return ApiResponse.ok({"ok": True, "version": __version__})

    _mount_dashboard(app, resolved)
    return app


def _register_error_handlers(app: FastAPI) -> None:
    """Force every error through the same envelope as the success responses.

    FastAPI's defaults return ``{"detail": ...}``, which would mean the dashboard needs
    two different parsers depending on whether a call succeeded.
    """

    @app.exception_handler(HTTPException)
    async def _http_error(_request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=ApiResponse.fail(str(exc.detail)).model_dump(),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Flatten pydantic's error list into one readable line per bad field. Field
        # names and constraints are safe to expose; the submitted value is not echoed.
        problems = [
            f"{'.'.join(str(part) for part in err['loc'][1:]) or 'body'}: {err['msg']}"
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=ApiResponse.fail("; ".join(problems) or "invalid request").model_dump(),
        )

    @app.exception_handler(Exception)
    async def _unhandled(_request: Request, exc: Exception) -> JSONResponse:
        # Log the detail server-side, return a generic message so internals do not leak.
        logger.exception("unhandled error: %s", exc)
        return JSONResponse(
            status_code=500,
            content=ApiResponse.fail("internal server error").model_dump(),
        )


def _mount_dashboard(app: FastAPI, settings: Settings) -> None:
    """Serve the built React bundle, if it has been built."""
    dist = settings.static_dir
    index = dist / "index.html"

    if not index.is_file():
        @app.get("/", include_in_schema=False)
        async def missing_dashboard() -> JSONResponse:
            return JSONResponse(
                status_code=503,
                content=ApiResponse.fail(
                    f"dashboard bundle not found at {dist.resolve()} — "
                    "run `npm install && npm run build` in frontend/"
                ).model_dump(),
            )

        logger.warning("dashboard bundle not found at %s; serving API only", dist.resolve())
        return

    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    # response_model=None: the union return type is a Response, not a schema to document.
    @app.get("/{path:path}", include_in_schema=False, response_model=None)
    async def spa(request: Request, path: str) -> FileResponse | JSONResponse:
        """Serve real files where they exist, else index.html for client-side routes."""
        if path.startswith("api/"):
            return JSONResponse(
                status_code=404, content=ApiResponse.fail("unknown API route").model_dump()
            )
        # Resolve and confine to dist, so a crafted path cannot escape the bundle.
        candidate = (dist / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(dist.resolve()):
            return FileResponse(candidate)
        return FileResponse(index)
