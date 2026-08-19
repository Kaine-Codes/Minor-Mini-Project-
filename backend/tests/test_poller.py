"""The poll loop: persistence, offline detection, alarm events, and retention."""

from __future__ import annotations

from aria.hub import BroadcastHub
from aria.models import ActuatorState, EdgeState
from aria.node_client import NodeError
from aria.poller import NodePoller, RetentionSweeper
from aria.repository import EventRepository, ReadingRepository

from .conftest import FakeNodeClient, make_reading


def build_poller(
    fake_node: FakeNodeClient,
    readings: ReadingRepository,
    events: EventRepository,
    hub: BroadcastHub,
    *,
    offline_after: int = 3,
) -> NodePoller:
    return NodePoller(
        client=fake_node,  # type: ignore[arg-type]
        readings=readings,
        events=events,
        hub=hub,
        interval_s=0.01,
        offline_after_failures=offline_after,
    )


class TestSuccessfulTick:
    async def test_persists_the_reading(self, fake_node, readings, events, hub) -> None:
        poller = build_poller(fake_node, readings, events, hub)
        stored = await poller.tick()

        assert stored is not None
        assert await readings.count() == 1

    async def test_reports_online_and_records_the_event(
        self, fake_node, readings, events, hub
    ) -> None:
        poller = build_poller(fake_node, readings, events, hub)
        await poller.tick()

        assert poller.status.online is True
        assert poller.status.consecutive_failures == 0
        assert any(row["kind"] == "node_online" for row in await events.recent())

    async def test_broadcasts_a_snapshot(self, fake_node, readings, events, hub) -> None:
        poller = build_poller(fake_node, readings, events, hub)
        await poller.tick()

        snapshot = hub.last_snapshot
        assert snapshot is not None
        assert snapshot.reading is not None
        assert snapshot.status.online is True

    async def test_online_event_logged_once_not_every_tick(
        self, fake_node, readings, events, hub
    ) -> None:
        poller = build_poller(fake_node, readings, events, hub)
        for _ in range(4):
            await poller.tick()

        online_events = [row for row in await events.recent() if row["kind"] == "node_online"]
        assert len(online_events) == 1


class TestFailureHandling:
    async def test_failed_tick_stores_nothing(self, fake_node, readings, events, hub) -> None:
        fake_node.go_offline()
        poller = build_poller(fake_node, readings, events, hub)

        assert await poller.tick() is None
        assert await readings.count() == 0

    async def test_stays_online_until_the_failure_threshold(
        self, fake_node, readings, events, hub
    ) -> None:
        poller = build_poller(fake_node, readings, events, hub, offline_after=3)
        await poller.tick()  # establish online

        fake_node.go_offline()
        await poller.tick()
        await poller.tick()
        # Two failures with a threshold of three: a single dropped packet or a brief
        # WiFi hiccup must not flip the dashboard to "offline".
        assert poller.status.online is True

        await poller.tick()
        assert poller.status.online is False

    async def test_records_offline_event_once(self, fake_node, readings, events, hub) -> None:
        poller = build_poller(fake_node, readings, events, hub, offline_after=1)
        await poller.tick()

        fake_node.go_offline()
        for _ in range(4):
            await poller.tick()

        offline = [row for row in await events.recent() if row["kind"] == "node_offline"]
        assert len(offline) == 1

    async def test_retains_last_reading_while_offline(
        self, fake_node, readings, events, hub
    ) -> None:
        poller = build_poller(fake_node, readings, events, hub, offline_after=1)
        await poller.tick()
        original = hub.last_snapshot
        assert original is not None and original.reading is not None
        original_id = original.reading.id

        fake_node.go_offline()
        await poller.tick()

        # The dashboard should keep showing the last known values, flagged as stale,
        # rather than blanking every tile.
        snapshot = hub.last_snapshot
        assert snapshot is not None
        assert snapshot.status.online is False
        assert snapshot.reading is not None
        assert snapshot.reading.id == original_id

    async def test_recovers_after_the_node_returns(
        self, fake_node, readings, events, hub
    ) -> None:
        poller = build_poller(fake_node, readings, events, hub, offline_after=1)
        await poller.tick()
        fake_node.go_offline()
        await poller.tick()
        assert poller.status.online is False

        fake_node.come_online()
        await poller.tick()

        assert poller.status.online is True
        assert poller.status.consecutive_failures == 0

    async def test_surfaces_the_error_message(self, fake_node, readings, events, hub) -> None:
        fake_node.fail_with = NodeError("boom")
        poller = build_poller(fake_node, readings, events, hub)
        await poller.tick()

        assert poller.status.last_error is not None
        assert "boom" in poller.status.last_error


class TestAlarmEvents:
    async def test_logs_only_alarm_transitions(
        self, fake_node, readings, events, hub
    ) -> None:
        poller = build_poller(fake_node, readings, events, hub)

        alarm = make_reading(
            actuators=ActuatorState(led=True, fan=True),
            edge=EdgeState(gas_alarm=True, warmed_up=True, mode="auto"),
        )
        fake_node.reading = alarm
        await poller.tick()
        await poller.tick()
        await poller.tick()

        # Three alarming samples, one alarm event — the log records incidents, not
        # every sample taken during one.
        raised = [row for row in await events.recent() if row["kind"] == "gas_alarm"]
        assert len(raised) == 1

    async def test_logs_the_clear_transition(self, fake_node, readings, events, hub) -> None:
        poller = build_poller(fake_node, readings, events, hub)
        fake_node.reading = make_reading(
            edge=EdgeState(gas_alarm=True, warmed_up=True, mode="auto")
        )
        await poller.tick()

        fake_node.reading = make_reading()
        await poller.tick()

        kinds = [row["kind"] for row in await events.recent()]
        assert "gas_alarm_cleared" in kinds


class TestRetentionSweeper:
    async def test_sweep_removes_expired_rows(self, readings, events) -> None:
        from datetime import datetime, timedelta, timezone

        old = (datetime.now(timezone.utc) - timedelta(days=30)).replace(
            microsecond=0
        ).isoformat()
        await readings.create(make_reading(), recorded_at=old)
        await events.create("command", "x", occurred_at=old)
        sweeper = RetentionSweeper(
            readings=readings, events=events, retention_days=14, interval_s=3600
        )

        assert await sweeper.sweep() == 2
        assert await readings.count() == 0

    async def test_sweep_keeps_fresh_rows(self, readings, events) -> None:
        await readings.create(make_reading())
        sweeper = RetentionSweeper(
            readings=readings, events=events, retention_days=14, interval_s=3600
        )

        assert await sweeper.sweep() == 0
        assert await readings.count() == 1

    async def test_stop_is_safe_when_never_started(self, readings, events) -> None:
        sweeper = RetentionSweeper(
            readings=readings, events=events, retention_days=1, interval_s=1
        )
        await sweeper.stop()  # must not raise
