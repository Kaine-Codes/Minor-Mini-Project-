"""Login / logout / session introspection."""

from __future__ import annotations

import asyncio
import logging
import secrets

from fastapi import APIRouter, Depends, Request, Response, status

from ..auth import (
    SessionManager,
    get_session_manager,
    require_user,
    verify_password,
)
from ..config import Settings
from ..deps import get_app_settings
from ..models import ApiResponse, LoginRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
async def login(
    body: LoginRequest,
    response: Response,
    settings: Settings = Depends(get_app_settings),
    sessions: SessionManager = Depends(get_session_manager),
) -> ApiResponse:
    """Exchange credentials for a signed session cookie."""
    # Compare both factors before answering, and always pay the hash cost, so a wrong
    # username is not distinguishable from a wrong password by timing or by message.
    username_ok = secrets.compare_digest(body.username, settings.username)
    password_ok = verify_password(body.password, settings.password_hash)

    if not (username_ok and password_ok):
        # Small fixed delay to blunt rapid online guessing on a LAN-exposed dashboard.
        await asyncio.sleep(0.5)
        logger.warning("failed login attempt for username=%r", body.username)
        response.status_code = status.HTTP_401_UNAUTHORIZED
        return ApiResponse.fail("invalid username or password")

    sessions.issue(response, settings.username)
    return ApiResponse.ok({"username": settings.username})


@router.post("/logout")
async def logout(
    response: Response,
    sessions: SessionManager = Depends(get_session_manager),
) -> ApiResponse:
    sessions.clear(response)
    return ApiResponse.ok({"logged_out": True})


@router.get("/session")
async def read_session(
    request: Request,
    sessions: SessionManager = Depends(get_session_manager),
) -> ApiResponse:
    """Unauthenticated probe so the dashboard can decide what to render on load."""
    username = sessions.read(request)
    return ApiResponse.ok({"authenticated": username is not None, "username": username})


@router.get("/me")
async def read_me(username: str = Depends(require_user)) -> ApiResponse:
    return ApiResponse.ok({"username": username})
