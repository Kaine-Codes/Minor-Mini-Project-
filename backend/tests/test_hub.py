"""Broadcast hub: fan-out, snapshot replay, and dropping dead sockets."""

from __future__ import annotations

from aria.hub import BroadcastHub
from aria.models import LiveSnapshot, NodeStatus

from .conftest import make_reading


class FakeSocket:
    """Stands in for a Starlette WebSocket, recording what it was sent."""

    def __init__(self, *, fail_on_send: bool = False) -> None:
        self.sent: list[str] = []
        self.accepted = False
        self.fail_on_send = fail_on_send

    async def accept(self) -> None:
        self.accepted = True

    async def send_text(self, payload: str) -> None:
        if self.fail_on_send:
            raise RuntimeError("socket closed")
        self.sent.append(payload)


def snapshot(online: bool = True) -> LiveSnapshot:
    reading = make_reading()
    stored = None
    if online:
        from aria.models import StoredReading

        stored = StoredReading(
            id=1,
            recorded_at="2026-01-01T00:00:00+00:00",
            node_id=reading.node_id,
            temperature_c=reading.temperature_c,
            humidity_pct=reading.humidity_pct,
            gas_pct=reading.gas_pct,
            light_pct=reading.light_pct,
            motion=reading.motion,
            led=reading.actuators.led,
            fan=reading.actuators.fan,
            gas_alarm=reading.edge.gas_alarm,
            mode=reading.edge.mode,
        )
    return LiveSnapshot(status=NodeStatus(online=online), reading=stored)


class TestRegistration:
    async def test_accepts_and_counts_a_client(self, hub: BroadcastHub) -> None:
        socket = FakeSocket()
        await hub.register(socket)  # type: ignore[arg-type]

        assert socket.accepted is True
        assert hub.client_count == 1

    async def test_replays_the_last_snapshot_on_connect(self, hub: BroadcastHub) -> None:
        # A tab opened between polls should render immediately rather than sit blank
        # until the next interval elapses.
        await hub.broadcast(snapshot())
        socket = FakeSocket()
        await hub.register(socket)  # type: ignore[arg-type]

        assert len(socket.sent) == 1

    async def test_no_replay_when_nothing_polled_yet(self, hub: BroadcastHub) -> None:
        socket = FakeSocket()
        await hub.register(socket)  # type: ignore[arg-type]
        assert socket.sent == []

    async def test_unregister_removes_the_client(self, hub: BroadcastHub) -> None:
        socket = FakeSocket()
        await hub.register(socket)  # type: ignore[arg-type]
        await hub.unregister(socket)  # type: ignore[arg-type]
        assert hub.client_count == 0

    async def test_unregister_is_idempotent(self, hub: BroadcastHub) -> None:
        socket = FakeSocket()
        await hub.unregister(socket)  # type: ignore[arg-type]
        await hub.unregister(socket)  # type: ignore[arg-type]
        assert hub.client_count == 0

    async def test_client_failing_during_replay_is_dropped(self, hub: BroadcastHub) -> None:
        await hub.broadcast(snapshot())
        socket = FakeSocket(fail_on_send=True)
        await hub.register(socket)  # type: ignore[arg-type]

        assert hub.client_count == 0


class TestBroadcast:
    async def test_sends_to_every_client(self, hub: BroadcastHub) -> None:
        sockets = [FakeSocket() for _ in range(3)]
        for socket in sockets:
            await hub.register(socket)  # type: ignore[arg-type]

        await hub.broadcast(snapshot())

        assert all(len(socket.sent) == 1 for socket in sockets)

    async def test_records_the_last_snapshot(self, hub: BroadcastHub) -> None:
        await hub.broadcast(snapshot(online=False))
        assert hub.last_snapshot is not None
        assert hub.last_snapshot.status.online is False

    async def test_broadcast_with_no_clients_is_harmless(self, hub: BroadcastHub) -> None:
        await hub.broadcast(snapshot())
        assert hub.client_count == 0
        assert hub.last_snapshot is not None

    async def test_drops_dead_clients_and_keeps_the_rest(self, hub: BroadcastHub) -> None:
        healthy = FakeSocket()
        dead = FakeSocket(fail_on_send=True)
        await hub.register(healthy)  # type: ignore[arg-type]
        await hub.register(dead)  # type: ignore[arg-type]

        await hub.broadcast(snapshot())

        # One browser tab closing must not stop the others receiving updates.
        assert hub.client_count == 1
        assert len(healthy.sent) == 1

    async def test_serialises_the_snapshot_as_json(self, hub: BroadcastHub) -> None:
        import json

        socket = FakeSocket()
        await hub.register(socket)  # type: ignore[arg-type]
        await hub.broadcast(snapshot())

        payload = json.loads(socket.sent[0])
        assert payload["status"]["online"] is True
        assert payload["reading"]["node_id"] == "aria-test"
