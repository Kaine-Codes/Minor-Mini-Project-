"""Storage: persistence, bounded history queries, and the retention policy."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aria.models import ActuatorState, EdgeState
from aria.repository import EventRepository, ReadingRepository, utc_now_iso

from .conftest import make_reading


def iso_days_ago(days: float) -> str:
    return (
        datetime.now(timezone.utc) - timedelta(days=days)
    ).replace(microsecond=0).isoformat()


class TestReadingPersistence:
    async def test_stores_and_returns_latest(self, readings: ReadingRepository) -> None:
        stored = await readings.create(make_reading(gas_pct=33.0))
        assert stored.id > 0
        latest = await readings.latest()
        assert latest is not None
        assert latest.gas_pct == 33.0

    async def test_latest_is_none_when_empty(self, readings: ReadingRepository) -> None:
        assert await readings.latest() is None

    async def test_preserves_null_temperature(self, readings: ReadingRepository) -> None:
        # A failed DHT22 read must persist as NULL, not as 0.0 — otherwise the chart
        # shows a phantom drop to freezing.
        stored = await readings.create(
            make_reading(temperature_c=None, humidity_pct=None)
        )
        assert stored.temperature_c is None
        fetched = await readings.latest()
        assert fetched is not None
        assert fetched.temperature_c is None
        assert fetched.humidity_pct is None

    async def test_round_trips_actuator_and_alarm_state(
        self, readings: ReadingRepository
    ) -> None:
        await readings.create(
            make_reading(
                actuators=ActuatorState(led=True, fan=True),
                edge=EdgeState(gas_alarm=True, warmed_up=True, mode="manual"),
            )
        )
        latest = await readings.latest()
        assert latest is not None
        assert (latest.led, latest.fan, latest.gas_alarm, latest.mode) == (
            True,
            True,
            True,
            "manual",
        )

    async def test_counts_rows(self, readings: ReadingRepository) -> None:
        for _ in range(4):
            await readings.create(make_reading())
        assert await readings.count() == 4


class TestHistory:
    async def test_returns_chronological_order(self, readings: ReadingRepository) -> None:
        for pct in (10.0, 20.0, 30.0):
            await readings.create(make_reading(gas_pct=pct))
        rows = await readings.history(hours=24)
        assert [row.gas_pct for row in rows] == [10.0, 20.0, 30.0]

    async def test_excludes_rows_outside_the_window(
        self, readings: ReadingRepository
    ) -> None:
        await readings.create(make_reading(gas_pct=1.0), recorded_at=iso_days_ago(3))
        await readings.create(make_reading(gas_pct=2.0))
        rows = await readings.history(hours=1)
        assert [row.gas_pct for row in rows] == [2.0]

    async def test_respects_the_limit(self, readings: ReadingRepository) -> None:
        for pct in range(10):
            await readings.create(make_reading(gas_pct=float(pct)))
        rows = await readings.history(hours=24, limit=3)
        assert len(rows) == 3

    async def test_limit_keeps_the_newest_rows(self, readings: ReadingRepository) -> None:
        # Truncation must drop the oldest samples, so a capped query still shows "now".
        for pct in range(6):
            await readings.create(
                make_reading(gas_pct=float(pct)),
                recorded_at=(
                    datetime.now(timezone.utc) - timedelta(minutes=10 - pct)
                ).replace(microsecond=0).isoformat(),
            )
        rows = await readings.history(hours=24, limit=2)
        assert [row.gas_pct for row in rows] == [4.0, 5.0]


class TestRetention:
    async def test_purges_only_expired_rows(self, readings: ReadingRepository) -> None:
        await readings.create(make_reading(gas_pct=1.0), recorded_at=iso_days_ago(30))
        await readings.create(make_reading(gas_pct=2.0), recorded_at=iso_days_ago(20))
        await readings.create(make_reading(gas_pct=3.0))

        purged = await readings.purge_older_than(14)

        assert purged == 2
        assert await readings.count() == 1
        remaining = await readings.latest()
        assert remaining is not None
        assert remaining.gas_pct == 3.0

    async def test_purge_is_a_noop_when_nothing_expired(
        self, readings: ReadingRepository
    ) -> None:
        await readings.create(make_reading())
        assert await readings.purge_older_than(14) == 0
        assert await readings.count() == 1

    async def test_purge_on_empty_table(self, readings: ReadingRepository) -> None:
        assert await readings.purge_older_than(14) == 0


class TestEvents:
    async def test_records_and_reads_back_newest_first(
        self, events: EventRepository
    ) -> None:
        await events.create("node_online", "host=fake.local")
        await events.create("gas_alarm", "threshold exceeded")
        recent = await events.recent()
        assert [row["kind"] for row in recent] == ["gas_alarm", "node_online"]

    async def test_detail_is_optional(self, events: EventRepository) -> None:
        await events.create("command")
        assert (await events.recent())[0]["detail"] is None

    async def test_limit_is_capped(self, events: EventRepository) -> None:
        for index in range(5):
            await events.create("command", str(index))
        # An absurd limit must be clamped rather than passed to SQLite verbatim.
        assert len(await events.recent(limit=10_000)) == 5

    async def test_purges_expired_events(self, events: EventRepository) -> None:
        await events.create("old", occurred_at=iso_days_ago(30))
        await events.create("fresh")

        assert await events.purge_older_than(14) == 1
        assert [row["kind"] for row in await events.recent()] == ["fresh"]


class TestTimestamps:
    def test_utc_now_iso_is_second_resolution_utc(self) -> None:
        stamp = utc_now_iso()
        parsed = datetime.fromisoformat(stamp)
        assert parsed.tzinfo is not None
        assert parsed.microsecond == 0
