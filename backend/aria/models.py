"""Pydantic schemas.

These mirror ``docs/CONTRACT.md`` exactly and are the validation boundary for every
byte that arrives from the node or from a dashboard client. Nothing untrusted reaches
the database or the node without passing through here first.

All models are frozen — reading or updating produces a new object rather than mutating
an existing one.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ActuatorMode = Literal["auto", "manual"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


# --------------------------------------------------------------------------- #
# Node -> backend
# --------------------------------------------------------------------------- #


class ActuatorState(_Frozen):
    """Current actuator states as reported by the node."""

    led: bool
    fan: bool


class EdgeState(_Frozen):
    """Status of the node's local (edge-first) automation."""

    gas_alarm: bool
    warmed_up: bool
    mode: ActuatorMode = "auto"


class SensorReading(_Frozen):
    """One `GET /sensors` response.

    ``temperature_c`` / ``humidity_pct`` are nullable because DHT22 reads fail
    intermittently; a failed read must not poison the whole sample.
    """

    node_id: str = Field(min_length=1, max_length=64)
    uptime_ms: int = Field(ge=0)
    temperature_c: float | None = Field(default=None, ge=-40.0, le=125.0)
    humidity_pct: float | None = Field(default=None, ge=0.0, le=100.0)
    gas_raw: int = Field(ge=0, le=4095)
    gas_pct: float = Field(ge=0.0, le=100.0)
    light_raw: int = Field(ge=0, le=4095)
    light_pct: float = Field(ge=0.0, le=100.0)
    motion: bool
    actuators: ActuatorState
    edge: EdgeState


class NodeHealth(_Frozen):
    """`GET /health` response."""

    ok: bool
    node_id: str = Field(min_length=1, max_length=64)
    firmware: str = "unknown"
    uptime_ms: int = Field(default=0, ge=0)


class NodeConfig(_Frozen):
    """Thresholds the node enforces locally. Ranges match CONTRACT.md."""

    gas_threshold_pct: float = Field(ge=0.0, le=100.0)
    dark_threshold_pct: float = Field(ge=0.0, le=100.0)
    temp_fan_threshold_c: float = Field(ge=0.0, le=60.0)
    motion_light_hold_s: int = Field(ge=5, le=3600)
    warmup_s: int = Field(ge=0, le=600)


# --------------------------------------------------------------------------- #
# Dashboard -> backend (partial updates)
# --------------------------------------------------------------------------- #


class ActuatorCommand(_Frozen):
    """Manual override. All fields optional — omitted keys are left unchanged."""

    led: bool | None = None
    fan: bool | None = None
    mode: ActuatorMode | None = None

    def as_payload(self) -> dict[str, object]:
        """Only the fields actually supplied, ready to forward to the node."""
        return self.model_dump(exclude_none=True)


class ActuatorStateWithMode(_Frozen):
    """`POST /actuators` response from the node."""

    led: bool
    fan: bool
    mode: ActuatorMode


class NodeConfigUpdate(_Frozen):
    """Partial threshold update. Ranges mirror :class:`NodeConfig`."""

    gas_threshold_pct: float | None = Field(default=None, ge=0.0, le=100.0)
    dark_threshold_pct: float | None = Field(default=None, ge=0.0, le=100.0)
    temp_fan_threshold_c: float | None = Field(default=None, ge=0.0, le=60.0)
    motion_light_hold_s: int | None = Field(default=None, ge=5, le=3600)
    warmup_s: int | None = Field(default=None, ge=0, le=600)

    def as_payload(self) -> dict[str, object]:
        return self.model_dump(exclude_none=True)


class LoginRequest(_Frozen):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


# --------------------------------------------------------------------------- #
# Backend -> dashboard
# --------------------------------------------------------------------------- #


class StoredReading(_Frozen):
    """A reading as persisted, with the server-side timestamp attached."""

    id: int
    recorded_at: str  # ISO-8601 UTC
    node_id: str
    temperature_c: float | None
    humidity_pct: float | None
    gas_pct: float
    light_pct: float
    motion: bool
    led: bool
    fan: bool
    gas_alarm: bool
    mode: ActuatorMode


class NodeStatus(_Frozen):
    """Connectivity view of the node, independent of sensor values."""

    online: bool
    host: str | None = None
    firmware: str | None = None
    consecutive_failures: int = 0
    last_error: str | None = None
    last_seen_at: str | None = None


class LiveSnapshot(_Frozen):
    """What the dashboard receives over the WebSocket on every poll tick."""

    status: NodeStatus
    reading: StoredReading | None = None


class ApiResponse(_Frozen):
    """Consistent response envelope (success flag, data, error, optional meta)."""

    success: bool
    data: object | None = None
    error: str | None = None
    meta: dict[str, object] | None = None

    @classmethod
    def ok(cls, data: object = None, **meta: object) -> "ApiResponse":
        return cls(success=True, data=data, meta=meta or None)

    @classmethod
    def fail(cls, error: str) -> "ApiResponse":
        return cls(success=False, error=error)
