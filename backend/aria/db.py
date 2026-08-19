"""SQLite connection management and schema.

Deliberately stdlib-only. Writes are low-frequency (one row per poll interval), so a
single serialised connection is ample; all access is pushed to a worker thread so the
event loop never blocks on disk.
"""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

T = TypeVar("T")

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at    TEXT    NOT NULL,          -- ISO-8601 UTC
    node_id        TEXT    NOT NULL,
    temperature_c  REAL,                      -- nullable: DHT22 reads fail
    humidity_pct   REAL,
    gas_raw        INTEGER NOT NULL,
    gas_pct        REAL    NOT NULL,
    light_raw      INTEGER NOT NULL,
    light_pct      REAL    NOT NULL,
    motion         INTEGER NOT NULL,
    led            INTEGER NOT NULL,
    fan            INTEGER NOT NULL,
    gas_alarm      INTEGER NOT NULL,
    mode           TEXT    NOT NULL DEFAULT 'auto'  -- 'auto' | 'manual'
);

-- Every query is either "recent readings" or "purge older than X", both ordered by
-- time. Without this index the retention sweep degrades into a full table scan.
CREATE INDEX IF NOT EXISTS idx_readings_recorded_at
    ON readings (recorded_at DESC);

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at TEXT NOT NULL,
    kind        TEXT NOT NULL,   -- e.g. 'gas_alarm', 'node_offline', 'command'
    detail      TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_occurred_at
    ON events (occurred_at DESC);
"""


class Database:
    """Owns the SQLite connection and serialises access to it."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._conn: sqlite3.Connection | None = None
        self._lock = asyncio.Lock()

    @property
    def path(self) -> Path:
        return self._path

    async def connect(self) -> None:
        """Open the connection, apply pragmas, and create the schema."""
        if self._conn is not None:
            return
        if self._path.parent != Path(""):
            self._path.parent.mkdir(parents=True, exist_ok=True)

        def _open() -> sqlite3.Connection:
            conn = sqlite3.connect(
                self._path,
                check_same_thread=False,
                isolation_level=None,  # autocommit; we manage transactions explicitly
            )
            conn.row_factory = sqlite3.Row
            # WAL lets the dashboard read history while the poller is writing.
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.executescript(SCHEMA)
            return conn

        self._conn = await asyncio.to_thread(_open)

    async def close(self) -> None:
        conn, self._conn = self._conn, None
        if conn is not None:
            await asyncio.to_thread(conn.close)

    async def run(self, fn: Callable[[sqlite3.Connection], T]) -> T:
        """Execute ``fn`` against the connection on a worker thread, under the lock."""
        if self._conn is None:
            raise RuntimeError("Database.connect() must be awaited before use")
        conn = self._conn
        async with self._lock:
            return await asyncio.to_thread(fn, conn)
