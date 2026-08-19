"""Shared fixtures.

Tests never touch real hardware or the real node. A :class:`FakeNodeClient` stands in
for the ESP32, so every test is deterministic and runs offline.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from aria.auth import hash_password
from aria.config import Settings
from aria.db import Database
from aria.hub import BroadcastHub
from aria.models import (
    ActuatorCommand,
    ActuatorState,
    ActuatorStateWithMode,
    EdgeState,
    NodeConfig,
    NodeConfigUpdate,
    NodeHealth,
    SensorReading,
)
from aria.node_client import NodeError, NodeUnreachable
from aria.repository import EventRepository, ReadingRepository

TEST_PASSWORD = "test-password-123"


def make_reading(**overrides: object) -> SensorReading:
    """A valid reading, with any field overridable per test."""
    payload: dict[str, object] = {
        "node_id": "aria-test",
        "uptime_ms": 60_000,
        "temperature_c": 27.5,
        "humidity_pct": 58.0,
        "gas_raw": 900,
        "gas_pct": 22.0,
        "light_raw": 2000,
        "light_pct": 48.8,
        "motion": False,
        "actuators": ActuatorState(led=False, fan=False),
        "edge": EdgeState(gas_alarm=False, warmed_up=True, mode="auto"),
    }
    payload.update(overrides)
    return SensorReading.model_validate(payload)


class FakeNodeClient:
    """In-memory stand-in for :class:`aria.node_client.NodeClient`."""

    def __init__(self) -> None:
        self.active_host: str | None = "fake.local"
        self.reading = make_reading()
        self.config = NodeConfig(
            gas_threshold_pct=60.0,
            dark_threshold_pct=25.0,
            temp_fan_threshold_c=30.0,
            motion_light_hold_s=30,
            warmup_s=60,
        )
        self.mode = "auto"
        self.led = False
        self.fan = False
        # Test controls
        self.fail_with: Exception | None = None
        self.sensors_calls = 0
        self.commands: list[dict[str, object]] = []

    def _guard(self) -> None:
        if self.fail_with is not None:
            raise self.fail_with

    async def health(self) -> NodeHealth:
        self._guard()
        return NodeHealth(ok=True, node_id="aria-test", firmware="test-1.0", uptime_ms=60_000)

    async def sensors(self) -> SensorReading:
        self._guard()
        self.sensors_calls += 1
        return self.reading

    async def set_actuators(self, command: ActuatorCommand) -> ActuatorStateWithMode:
        self._guard()
        payload = command.as_payload()
        if not payload:
            raise NodeError("actuator command was empty")
        self.commands.append(payload)
        if "mode" in payload:
            self.mode = str(payload["mode"])
        if "led" in payload:
            self.led = bool(payload["led"])
        if "fan" in payload:
            self.fan = bool(payload["fan"])
        # Mirror the node's safety rule: an active alarm overrides any command.
        if self.reading.edge.gas_alarm:
            self.led = True
            self.fan = True
        return ActuatorStateWithMode(led=self.led, fan=self.fan, mode=self.mode)  # type: ignore[arg-type]

    async def get_config(self) -> NodeConfig:
        self._guard()
        return self.config

    async def set_config(self, update: NodeConfigUpdate) -> NodeConfig:
        self._guard()
        payload = update.as_payload()
        if not payload:
            raise NodeError("config update was empty")
        self.config = self.config.model_copy(update=payload)
        return self.config

    async def aclose(self) -> None:
        return None

    def go_offline(self) -> None:
        self.fail_with = NodeUnreachable("no ARIA node answered on any candidate host")

    def come_online(self) -> None:
        self.fail_with = None


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings pointed at a temp database, with valid auth secrets."""
    return Settings(
        db_path=tmp_path / "test.db",
        password_hash=hash_password(TEST_PASSWORD),
        session_secret="test-session-secret-not-for-real-use",
        username="admin",
        node_hosts=("fake.local",),
        poll_interval_s=1.0,
        offline_after_failures=3,
        retention_days=7,
        static_dir=tmp_path / "no-dashboard",
    )


@pytest.fixture
async def database(settings: Settings):
    db = Database(settings.db_path)
    await db.connect()
    yield db
    await db.close()


@pytest.fixture
def readings(database: Database) -> ReadingRepository:
    return ReadingRepository(database)


@pytest.fixture
def events(database: Database) -> EventRepository:
    return EventRepository(database)


@pytest.fixture
def hub() -> BroadcastHub:
    return BroadcastHub()


@pytest.fixture
def fake_node() -> FakeNodeClient:
    return FakeNodeClient()


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """Stop a cached Settings singleton leaking between tests."""
    from aria.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
    for key in [k for k in os.environ if k.startswith("ARIA_")]:
        del os.environ[key]
