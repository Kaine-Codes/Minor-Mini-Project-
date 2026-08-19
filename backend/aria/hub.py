"""WebSocket broadcast hub.

The dashboard is push-driven rather than polling: the backend polls the node once, and
fans the result out to every connected client. One HTTP request per interval regardless
of how many browser tabs are open.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import WebSocket

from .models import LiveSnapshot

logger = logging.getLogger(__name__)


class BroadcastHub:
    """Tracks connected dashboard sockets and pushes snapshots to them."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self._last: LiveSnapshot | None = None

    @property
    def client_count(self) -> int:
        return len(self._clients)

    @property
    def last_snapshot(self) -> LiveSnapshot | None:
        """Most recent snapshot, replayed to clients the moment they connect."""
        return self._last

    async def register(self, websocket: WebSocket) -> None:
        """Accept a socket and immediately send the latest snapshot, if there is one."""
        await websocket.accept()
        async with self._lock:
            self._clients.add(websocket)
        if self._last is not None:
            try:
                await websocket.send_text(self._last.model_dump_json())
            except Exception:  # noqa: BLE001 - client vanished mid-handshake
                await self.unregister(websocket)

    async def unregister(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(websocket)

    async def broadcast(self, snapshot: LiveSnapshot) -> None:
        """Send ``snapshot`` to every client, dropping any that error out."""
        self._last = snapshot
        async with self._lock:
            targets = tuple(self._clients)
        if not targets:
            return

        payload = snapshot.model_dump_json()
        results = await asyncio.gather(
            *(client.send_text(payload) for client in targets),
            return_exceptions=True,
        )
        dead = [
            client
            for client, result in zip(targets, results, strict=True)
            if isinstance(result, BaseException)
        ]
        if dead:
            async with self._lock:
                for client in dead:
                    self._clients.discard(client)
            logger.debug("dropped %d dead dashboard socket(s)", len(dead))
