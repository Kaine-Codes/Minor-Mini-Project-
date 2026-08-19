"""Threshold configuration.

This is what completes the edge-first story: the thresholds live and are enforced on the
node, but remain editable from the dashboard, and the node persists them to NVS so they
survive a reboot and keep working with this server switched off.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Response, status

from ..auth import require_user
from ..deps import get_events, get_node
from ..models import ApiResponse, NodeConfigUpdate
from ..node_client import NodeClient, NodeError, NodeUnreachable
from ..repository import EventRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("")
async def read_config(
    response: Response,
    _user: str = Depends(require_user),
    node: NodeClient = Depends(get_node),
) -> ApiResponse:
    try:
        return ApiResponse.ok(await node.get_config())
    except NodeUnreachable as exc:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ApiResponse.fail(f"node unreachable: {exc}")
    except NodeError as exc:
        response.status_code = status.HTTP_502_BAD_GATEWAY
        return ApiResponse.fail(f"node error: {exc}")


@router.post("")
async def update_config(
    update: NodeConfigUpdate,
    response: Response,
    user: str = Depends(require_user),
    node: NodeClient = Depends(get_node),
    events: EventRepository = Depends(get_events),
) -> ApiResponse:
    """Partial threshold update, validated here and again on the node."""
    payload = update.as_payload()
    if not payload:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return ApiResponse.fail("provide at least one threshold to update")

    try:
        new_config = await node.set_config(update)
    except NodeUnreachable as exc:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ApiResponse.fail(f"node unreachable: {exc}")
    except NodeError as exc:
        response.status_code = status.HTTP_502_BAD_GATEWAY
        return ApiResponse.fail(f"node rejected config: {exc}")

    await events.create("config", f"{user} updated {payload}")
    logger.info("config update from %s: %s", user, payload)
    return ApiResponse.ok(new_config)
