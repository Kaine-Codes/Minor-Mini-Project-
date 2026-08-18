"""
ARIA Backend - Database layer (SQLite)

Handles schema creation, inserts, queries, and the data-retention
cleanup job (delete readings older than RETENTION_DAYS).
"""

import sqlite3
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager

DB_PATH = "aria.db"
RETENTION_DAYS = 7  # tune as needed


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                temperature REAL,
                humidity REAL,
                gas_raw INTEGER,
                light_raw INTEGER,
                motion INTEGER,
                vibration INTEGER,
                local_gas_override INTEGER
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS commands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                led INTEGER DEFAULT 0,
                fan INTEGER DEFAULT 0,
                updated_at TEXT
            )
        """)
        # Ensure a single row exists in commands (id=1) that the ESP32 polls
        row = conn.execute("SELECT * FROM commands WHERE id = 1").fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO commands (id, led, fan, updated_at) VALUES (1, 0, 0, ?)",
                (datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),)
            )
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            )
        """)
        
        # Run basic migrations to add missing columns in case of older DB schemas
        columns = [col[1] for col in conn.execute("PRAGMA table_info(readings)").fetchall()]
        if 'vibration' not in columns:
            conn.execute("ALTER TABLE readings ADD COLUMN vibration INTEGER DEFAULT 0")
        if 'local_gas_override' not in columns:
            conn.execute("ALTER TABLE readings ADD COLUMN local_gas_override INTEGER DEFAULT 0")


def insert_reading(data: dict):
    with get_db() as conn:
        conn.execute("""
            INSERT INTO readings
                (timestamp, temperature, humidity, gas_raw, light_raw, motion, vibration, local_gas_override)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            data.get("temperature"),
            data.get("humidity"),
            data.get("gas_raw"),
            data.get("light_raw"),
            1 if data.get("motion") else 0,
            1 if data.get("vibration") else 0,
            1 if data.get("local_gas_override") else 0,
        ))


def get_latest_reading():
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM readings ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None


def get_history(limit: int = 200):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM readings ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in reversed(rows)]


def get_commands():
    with get_db() as conn:
        row = conn.execute("SELECT * FROM commands WHERE id = 1").fetchone()
        return dict(row) if row else {"led": 0, "fan": 0}


def set_commands(led=None, fan=None):
    with get_db() as conn:
        current = conn.execute("SELECT * FROM commands WHERE id = 1").fetchone()
        new_led = current["led"] if led is None else (1 if led else 0)
        new_fan = current["fan"] if fan is None else (1 if fan else 0)
        conn.execute(
            "UPDATE commands SET led = ?, fan = ?, updated_at = ? WHERE id = 1",
            (new_led, new_fan, datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"))
        )


def cleanup_old_readings():
    """Deletes readings older than RETENTION_DAYS. Call periodically."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    with get_db() as conn:
        conn.execute("DELETE FROM readings WHERE timestamp < ?", (cutoff,))
