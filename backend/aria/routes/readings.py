"""Live snapshot, history, events, and the dashboard WebSocket."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from ..auth import SessionManager, get_session_manager, require_user
from ..deps import get_events, get_hub, get_poller, get_readings
from ..hub import BroadcastHub
from ..models import ApiResponse, LiveSnapshot
from ..poller import NodePoller
from ..repository import EventRepository, ReadingRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["readings"])


@router.get("/status")
async def read_status(
    _user: str = Depends(require_user),
    poller: NodePoller = Depends(get_poller),
    hub: BroadcastHub = Depends(get_hub),
) -> ApiResponse:
    """Node connectivity plus the most recent reading."""
    snapshot = hub.last_snapshot
    return ApiResponse.ok(
        LiveSnapshot(
            status=poller.status,
            reading=snapshot.reading if snapshot else None,
        ),
        dashboard_clients=hub.client_count,
    )


@router.get("/readings/latest")
async def read_latest(
    _user: str = Depends(require_user),
    readings: ReadingRepository = Depends(get_readings),
) -> ApiResponse:
    return ApiResponse.ok(await readings.latest())


@router.get("/readings/history")
async def read_history(
    _user: str = Depends(require_user),
    readings: ReadingRepository = Depends(get_readings),
    hours: int = Query(default=24, ge=1, le=720),
    limit: int = Query(default=2000, ge=1, le=10_000),
) -> ApiResponse:
    """Historical series for the charts. Always bounded — see repository docstring."""
    rows = await readings.history(hours=hours, limit=limit)
    return ApiResponse.ok(rows, hours=hours, count=len(rows), limit=limit)


@router.get("/events")
async def read_events(
    _user: str = Depends(require_user),
    events: EventRepository = Depends(get_events),
    limit: int = Query(default=50, ge=1, le=500),
) -> ApiResponse:
    return ApiResponse.ok(await events.recent(limit))


@router.get("/stats")
async def read_stats(
    _user: str = Depends(require_user),
    readings: ReadingRepository = Depends(get_readings),
    poller: NodePoller = Depends(get_poller),
) -> ApiResponse:
    return ApiResponse.ok(
        {"stored_readings": await readings.count(), "node": poller.status}
    )


@router.websocket("/live")
async def live_feed(
    websocket: WebSocket,
    sessions: SessionManager = Depends(get_session_manager),
    hub: BroadcastHub = Depends(get_hub),
) -> None:
    """Push snapshots to the dashboard as they are polled.

    Authenticated via the same session cookie as the REST routes — the browser sends it
    on the WebSocket handshake, so an unauthenticated socket is refused before accept().
    """
    if sessions.read(websocket) is None:
        await websocket.close(code=1008, reason="authentication required")
        return

    await hub.register(websocket)
    try:
        while True:
            # The client sends nothing meaningful; this await is how we notice a
            # disconnect. Any received text is ignored by design.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        logger.debug("dashboard socket closed unexpectedly", exc_info=True)
    finally:
        await hub.unregister(websocket)
