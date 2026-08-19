"""Background poll loop: node -> database -> dashboard.

Owns the only periodic read of the node. Each tick it fetches ``GET /sensors``,
persists the sample, logs notable transitions as events, and broadcasts a snapshot to
connected dashboards.

Note what this loop is *not* responsible for: the safety-critical gas response. That
runs on the node itself and keeps working with this process stopped. If the poller dies,
ARIA loses logging and remote control — not its automation.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from .hub import BroadcastHub
from .models import LiveSnapshot, NodeStatus, StoredReading
from .node_client import NodeClient, NodeError
from .repository import EventRepository, ReadingRepository, utc_now_iso

logger = logging.getLogger(__name__)


class NodePoller:
    """Periodically samples the node and fans results out."""

    def __init__(
        self,
        *,
        client: NodeClient,
        readings: ReadingRepository,
        events: EventRepository,
        hub: BroadcastHub,
        interval_s: float,
        offline_after_failures: int,
    ) -> None:
        self._client = client
        self._readings = readings
        self._events = events
        self._hub = hub
        self._interval_s = interval_s
        self._offline_after = offline_after_failures

        self._task: asyncio.Task[None] | None = None
        self._failures = 0
        self._last_error: str | None = None
        self._last_seen_at: str | None = None
        self._firmware: str | None = None
        self._was_online = False
        self._gas_alarm_active = False

    # --- lifecycle ---------------------------------------------------------- #

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="aria-poller")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    # --- status ------------------------------------------------------------- #

    @property
    def status(self) -> NodeStatus:
        """Current connectivity view, safe to expose over the API."""
        return NodeStatus(
            online=self._failures < self._offline_after and self._was_online,
            host=self._client.active_host,
            firmware=self._firmware,
            consecutive_failures=self._failures,
            last_error=self._last_error,
            last_seen_at=self._last_seen_at,
        )

    # --- loop --------------------------------------------------------------- #

    async def _run(self) -> None:
        logger.info("poller started (every %.1fs)", self._interval_s)
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                logger.info("poller stopped")
                raise
            except Exception:  # noqa: BLE001 - the loop must outlive any single tick
                logger.exception("unexpected error in poll tick")
            await asyncio.sleep(self._interval_s)

    async def tick(self) -> StoredReading | None:
        """One poll cycle. Returns the stored reading, or ``None`` if the node failed.

        Separated from :meth:`_run` so tests can drive a single cycle deterministically.
        """
        try:
            reading = await self._client.sensors()
        except NodeError as exc:
            await self._handle_failure(str(exc))
            return None

        self._failures = 0
        self._last_error = None
        self._last_seen_at = utc_now_iso()
        if not self._was_online:
            self._was_online = True
            await self._events.create("node_online", f"host={self._client.active_host}")
            with contextlib.suppress(NodeError):
                self._firmware = (await self._client.health()).firmware

        stored = await self._readings.create(reading)
        await self._record_alarm_transition(reading.edge.gas_alarm)
        await self._hub.broadcast(LiveSnapshot(status=self.status, reading=stored))
        return stored

    async def _handle_failure(self, message: str) -> None:
        self._failures += 1
        self._last_error = message
        if self._was_online and self._failures >= self._offline_after:
            self._was_online = False
            await self._events.create("node_offline", message)
            logger.warning("node offline after %d failures: %s", self._failures, message)
        await self._hub.broadcast(
            LiveSnapshot(status=self.status, reading=self._last_reading_of(self._hub))
        )

    async def _record_alarm_transition(self, alarm: bool) -> None:
        """Log only the edges, so the events table records alarms not every sample."""
        if alarm == self._gas_alarm_active:
            return
        self._gas_alarm_active = alarm
        await self._events.create(
            "gas_alarm" if alarm else "gas_alarm_cleared",
            "edge threshold exceeded on node" if alarm else "gas level back under threshold",
        )

    @staticmethod
    def _last_reading_of(hub: BroadcastHub) -> StoredReading | None:
        """Keep the last known reading visible while the node is unreachable."""
        snapshot = hub.last_snapshot
        return snapshot.reading if snapshot is not None else None


class RetentionSweeper:
    """Enforces the delete-after-N-days policy on a timer.

    Without this, a 5-second sample rate writes roughly 17k rows a day and grows without
    bound. Downsampling to hourly averages is the better long-term answer and is listed
    as future scope; a time-based delete is enough for this build.
    """

    def __init__(
        self,
        *,
        readings: ReadingRepository,
        events: EventRepository,
        retention_days: int,
        interval_s: float,
    ) -> None:
        self._readings = readings
        self._events = events
        self._retention_days = retention_days
        self._interval_s = interval_s
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="aria-retention")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def sweep(self) -> int:
        """Purge expired rows from both tables. Returns total rows deleted."""
        purged = await self._readings.purge_older_than(self._retention_days)
        purged += await self._events.purge_older_than(self._retention_days)
        if purged:
            logger.info("retention sweep removed %d row(s)", purged)
        return purged

    async def _run(self) -> None:
        while True:
            try:
                await self.sweep()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("retention sweep failed")
            await asyncio.sleep(self._interval_s)
