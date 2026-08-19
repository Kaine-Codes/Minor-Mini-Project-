"""Validation at the boundary — the models are the gate untrusted data must pass."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from aria.models import (
    ActuatorCommand,
    ApiResponse,
    NodeConfig,
    NodeConfigUpdate,
    SensorReading,
)

from .conftest import make_reading


class TestSensorReading:
    def test_accepts_a_valid_payload(self) -> None:
        assert make_reading().node_id == "aria-test"

    def test_allows_null_dht_values(self) -> None:
        reading = make_reading(temperature_c=None, humidity_pct=None)
        assert reading.temperature_c is None

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("gas_raw", 5000),      # beyond 12-bit ADC range
            ("gas_raw", -1),
            ("gas_pct", 101.0),
            ("light_pct", -0.5),
            ("humidity_pct", 120.0),
            ("temperature_c", 500.0),
            ("uptime_ms", -1),
        ],
    )
    def test_rejects_out_of_range_values(self, field: str, value: object) -> None:
        # A miswired sensor or a corrupted response must be refused, not stored.
        with pytest.raises(ValidationError):
            make_reading(**{field: value})

    def test_rejects_empty_node_id(self) -> None:
        with pytest.raises(ValidationError):
            make_reading(node_id="")

    def test_rejects_unknown_fields(self) -> None:
        # extra="forbid" catches a firmware/backend contract drift immediately rather
        # than silently ignoring a renamed field.
        with pytest.raises(ValidationError):
            SensorReading.model_validate(
                {**make_reading().model_dump(), "unexpected_field": 1}
            )

    def test_is_immutable(self) -> None:
        with pytest.raises(ValidationError):
            make_reading().node_id = "changed"  # type: ignore[misc]


class TestActuatorCommand:
    def test_payload_omits_unset_fields(self) -> None:
        assert ActuatorCommand(led=True).as_payload() == {"led": True}

    def test_empty_command_yields_empty_payload(self) -> None:
        assert ActuatorCommand().as_payload() == {}

    def test_rejects_invalid_mode(self) -> None:
        with pytest.raises(ValidationError):
            ActuatorCommand(mode="turbo")  # type: ignore[arg-type]

    def test_accepts_both_valid_modes(self) -> None:
        assert ActuatorCommand(mode="auto").mode == "auto"
        assert ActuatorCommand(mode="manual").mode == "manual"


class TestNodeConfig:
    def test_accepts_in_range_values(self) -> None:
        config = NodeConfig(
            gas_threshold_pct=60.0,
            dark_threshold_pct=25.0,
            temp_fan_threshold_c=30.0,
            motion_light_hold_s=30,
            warmup_s=60,
        )
        assert config.gas_threshold_pct == 60.0

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("gas_threshold_pct", 101.0),
            ("gas_threshold_pct", -1.0),
            ("temp_fan_threshold_c", 61.0),
            ("motion_light_hold_s", 4),      # below the 5 s floor
            ("motion_light_hold_s", 3601),
            ("warmup_s", 601),
        ],
    )
    def test_update_rejects_out_of_range(self, field: str, value: object) -> None:
        with pytest.raises(ValidationError):
            NodeConfigUpdate(**{field: value})

    def test_partial_update_payload(self) -> None:
        assert NodeConfigUpdate(gas_threshold_pct=55.0).as_payload() == {
            "gas_threshold_pct": 55.0
        }

    def test_empty_update_payload(self) -> None:
        assert NodeConfigUpdate().as_payload() == {}


class TestApiResponse:
    def test_ok_marks_success(self) -> None:
        response = ApiResponse.ok({"x": 1})
        assert response.success is True
        assert response.error is None

    def test_ok_attaches_meta(self) -> None:
        assert ApiResponse.ok([], count=0).meta == {"count": 0}

    def test_ok_without_meta_leaves_it_null(self) -> None:
        assert ApiResponse.ok({"x": 1}).meta is None

    def test_fail_marks_failure(self) -> None:
        response = ApiResponse.fail("nope")
        assert response.success is False
        assert response.data is None
        assert response.error == "nope"
