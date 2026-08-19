"""Data access for readings and events (repository pattern).

Routes and the poller depend on these classes, never on ``sqlite3`` directly, so the
storage engine stays swappable and the API layer is trivial to test with a fake.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from .db import Database
from .models import SensorReading, StoredReading

_READING_COLUMNS = (
    "id, recorded_at, node_id, temperature_c, humidity_pct, "
    "gas_pct, light_pct, motion, led, fan, gas_alarm, mode"
)


def utc_now_iso() -> str:
    """Current UTC time as a second-resolution ISO-8601 string."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _to_stored(row: sqlite3.Row) -> StoredReading:
    return StoredReading(
        id=row["id"],
        recorded_at=row["recorded_at"],
        node_id=row["node_id"],
        temperature_c=row["temperature_c"],
        humidity_pct=row["humidity_pct"],
        gas_pct=row["gas_pct"],
        light_pct=row["light_pct"],
        motion=bool(row["motion"]),
        led=bool(row["led"]),
        fan=bool(row["fan"]),
        gas_alarm=bool(row["gas_alarm"]),
        mode="manual" if row["mode"] == "manual" else "auto",
    )


class ReadingRepository:
    """Persistence for sensor samples."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(
        self, reading: SensorReading, *, recorded_at: str | None = None
    ) -> StoredReading:
        """Insert one sample and return it with its assigned id and timestamp."""
        stamp = recorded_at or utc_now_iso()

        def _insert(conn: sqlite3.Connection) -> int:
            cursor = conn.execute(
                """
                INSERT INTO readings (
                    recorded_at, node_id, temperature_c, humidity_pct,
                    gas_raw, gas_pct, light_raw, light_pct,
                    motion, led, fan, gas_alarm, mode
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    stamp,
                    reading.node_id,
                    reading.temperature_c,
                    reading.humidity_pct,
                    reading.gas_raw,
                    reading.gas_pct,
                    reading.light_raw,
                    reading.light_pct,
                    int(reading.motion),
                    int(reading.actuators.led),
                    int(reading.actuators.fan),
                    int(reading.edge.gas_alarm),
                    reading.edge.mode,
                ),
            )
            return int(cursor.lastrowid or 0)

        new_id = await self._db.run(_insert)
        return StoredReading(
            id=new_id,
            recorded_at=stamp,
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

    async def latest(self) -> StoredReading | None:
        def _query(conn: sqlite3.Connection) -> sqlite3.Row | None:
            return conn.execute(
                f"SELECT {_READING_COLUMNS} FROM readings ORDER BY id DESC LIMIT 1"
            ).fetchone()

        row = await self._db.run(_query)
        return _to_stored(row) if row is not None else None

    async def history(self, *, hours: int = 24, limit: int = 2000) -> list[StoredReading]:
        """Readings from the last ``hours``, oldest first, capped at ``limit`` rows.

        The cap is mandatory — an unbounded query would happily return a fortnight of
        5-second samples and stall the chart.
        """
        since = (
            datetime.now(timezone.utc) - timedelta(hours=hours)
        ).replace(microsecond=0).isoformat()

        def _query(conn: sqlite3.Connection) -> list[sqlite3.Row]:
            # Take the newest N within the window, then flip to chronological order
            # so Chart.js receives a left-to-right time series.
            return conn.execute(
                f"""
                SELECT * FROM (
                    SELECT {_READING_COLUMNS}
                    FROM readings
                    WHERE recorded_at >= ?
                    ORDER BY recorded_at DESC
                    LIMIT ?
                ) ORDER BY recorded_at ASC
                """,
                (since, limit),
            ).fetchall()

        rows = await self._db.run(_query)
        return [_to_stored(row) for row in rows]

    async def count(self) -> int:
        def _query(conn: sqlite3.Connection) -> int:
            return int(conn.execute("SELECT COUNT(*) FROM readings").fetchone()[0])

        return await self._db.run(_query)

    async def purge_older_than(self, days: int) -> int:
        """Delete readings older than ``days``. Returns the number of rows removed."""
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=days)
        ).replace(microsecond=0).isoformat()

        def _delete(conn: sqlite3.Connection) -> int:
            cursor = conn.execute("DELETE FROM readings WHERE recorded_at < ?", (cutoff,))
            return cursor.rowcount if cursor.rowcount > 0 else 0

        return await self._db.run(_delete)


class EventRepository:
    """Persistence for discrete events (alarms, node up/down, manual commands)."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(
        self, kind: str, detail: str | None = None, *, occurred_at: str | None = None
    ) -> None:
        """Record an event. ``occurred_at`` is injectable to keep retention testable."""
        stamp = occurred_at or utc_now_iso()

        def _insert(conn: sqlite3.Connection) -> None:
            conn.execute(
                "INSERT INTO events (occurred_at, kind, detail) VALUES (?, ?, ?)",
                (stamp, kind, detail),
            )

        await self._db.run(_insert)

    async def recent(self, limit: int = 50) -> list[dict[str, object]]:
        capped = max(1, min(limit, 500))

        def _query(conn: sqlite3.Connection) -> list[sqlite3.Row]:
            return conn.execute(
                "SELECT id, occurred_at, kind, detail FROM events "
                "ORDER BY id DESC LIMIT ?",
                (capped,),
            ).fetchall()

        rows = await self._db.run(_query)
        return [dict(row) for row in rows]

    async def purge_older_than(self, days: int) -> int:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=days)
        ).replace(microsecond=0).isoformat()

        def _delete(conn: sqlite3.Connection) -> int:
            cursor = conn.execute("DELETE FROM events WHERE occurred_at < ?", (cutoff,))
            return cursor.rowcount if cursor.rowcount > 0 else 0

        return await self._db.run(_delete)
