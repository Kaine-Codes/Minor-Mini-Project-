"""Manual actuator control (dashboard -> backend -> node)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Response, status

from ..auth import require_user
from ..deps import get_events, get_node
from ..models import ActuatorCommand, ApiResponse
from ..node_client import NodeClient, NodeError, NodeUnreachable
from ..repository import EventRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/actuators", tags=["control"])


@router.get("")
async def read_actuators(
    response: Response,
    _user: str = Depends(require_user),
    node: NodeClient = Depends(get_node),
) -> ApiResponse:
    """Read actuator state straight from the node (not from the last stored sample)."""
    try:
        reading = await node.sensors()
    except NodeUnreachable as exc:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ApiResponse.fail(f"node unreachable: {exc}")
    except NodeError as exc:
        response.status_code = status.HTTP_502_BAD_GATEWAY
        return ApiResponse.fail(f"node error: {exc}")

    return ApiResponse.ok(
        {
            "led": reading.actuators.led,
            "fan": reading.actuators.fan,
            "mode": reading.edge.mode,
        }
    )


@router.post("")
async def set_actuators(
    command: ActuatorCommand,
    response: Response,
    user: str = Depends(require_user),
    node: NodeClient = Depends(get_node),
    events: EventRepository = Depends(get_events),
) -> ApiResponse:
    """Apply a manual override.

    The node still refuses to honour anything that conflicts with an active gas alarm —
    that rule is enforced on the node, not here, so it holds even with this server down.
    """
    payload = command.as_payload()
    if not payload:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return ApiResponse.fail("provide at least one of: led, fan, mode")

    try:
        new_state = await node.set_actuators(command)
    except NodeUnreachable as exc:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ApiResponse.fail(f"node unreachable: {exc}")
    except NodeError as exc:
        response.status_code = status.HTTP_502_BAD_GATEWAY
        return ApiResponse.fail(f"node rejected command: {exc}")

    await events.create("command", f"{user} set {payload}")
    logger.info("actuator command from %s: %s", user, payload)
    return ApiResponse.ok(new_state)
