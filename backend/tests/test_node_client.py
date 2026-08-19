"""Node client: discovery across candidate hosts, retry, and response validation.

Uses httpx's MockTransport so the real request path runs against scripted responses —
no network, no hardware, but the actual client logic under test.
"""

from __future__ import annotations

import httpx
import pytest

from aria.config import Settings
from aria.models import ActuatorCommand, NodeConfigUpdate
from aria.node_client import NodeClient, NodeError, NodeUnreachable

HEALTH_BODY = {"ok": True, "node_id": "aria-test", "firmware": "1.0.0", "uptime_ms": 1000}

SENSOR_BODY = {
    "node_id": "aria-test",
    "uptime_ms": 60000,
    "temperature_c": 27.5,
    "humidity_pct": 58.0,
    "gas_raw": 900,
    "gas_pct": 22.0,
    "light_raw": 2000,
    "light_pct": 48.8,
    "motion": False,
    "actuators": {"led": False, "fan": False},
    "edge": {"gas_alarm": False, "warmed_up": True, "mode": "auto"},
}

CONFIG_BODY = {
    "gas_threshold_pct": 60.0,
    "dark_threshold_pct": 25.0,
    "temp_fan_threshold_c": 30.0,
    "motion_light_hold_s": 30,
    "warmup_s": 60,
}


def build_client(
    handler, hosts: tuple[str, ...] = ("primary.local", "192.168.1.50")
) -> NodeClient:
    settings = Settings(
        password_hash="scrypt$aa$bb",
        session_secret="x",
        node_hosts=hosts,
        node_port=80,
    )
    transport = httpx.MockTransport(handler)
    return NodeClient(settings, client=httpx.AsyncClient(transport=transport))


class TestDiscovery:
    async def test_uses_the_first_responding_host(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=HEALTH_BODY)

        client = build_client(handler)
        assert await client.discover() == "primary.local"
        assert client.active_host == "primary.local"
        await client.aclose()

    async def test_falls_back_to_the_next_candidate(self) -> None:
        # This is the mDNS-failure path: aria.local does not resolve, so the static IP
        # fallback must take over rather than the node being declared dead.
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "primary.local":
                raise httpx.ConnectError("name not resolved", request=request)
            return httpx.Response(200, json=HEALTH_BODY)

        client = build_client(handler)
        assert await client.discover() == "192.168.1.50"
        await client.aclose()

    async def test_raises_when_no_candidate_answers(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused", request=request)

        client = build_client(handler)
        with pytest.raises(NodeUnreachable, match="no ARIA node answered"):
            await client.discover()
        assert client.active_host is None
        await client.aclose()

    async def test_error_names_every_tried_host(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused", request=request)

        client = build_client(handler)
        with pytest.raises(NodeUnreachable) as exc:
            await client.discover()
        assert "primary.local" in str(exc.value)
        assert "192.168.1.50" in str(exc.value)
        await client.aclose()

    async def test_rejects_a_host_serving_the_wrong_shape(self) -> None:
        # Something else on the LAN answering port 80 must not be mistaken for the node.
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "primary.local":
                return httpx.Response(200, json={"totally": "unrelated service"})
            return httpx.Response(200, json=HEALTH_BODY)

        client = build_client(handler)
        assert await client.discover() == "192.168.1.50"
        await client.aclose()

    async def test_prefers_the_cached_host_on_later_calls(self) -> None:
        attempts: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            attempts.append(request.url.host)
            if request.url.host == "primary.local":
                raise httpx.ConnectError("down", request=request)
            return httpx.Response(200, json=HEALTH_BODY)

        client = build_client(handler)
        await client.discover()
        attempts.clear()
        await client.discover()

        # The known-good host is tried first, so a dead primary is not re-probed
        # on every single request.
        assert attempts[0] == "192.168.1.50"
        await client.aclose()


class TestRequests:
    async def test_reads_sensors(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/health":
                return httpx.Response(200, json=HEALTH_BODY)
            return httpx.Response(200, json=SENSOR_BODY)

        client = build_client(handler)
        reading = await client.sensors()
        assert reading.gas_pct == 22.0
        assert reading.edge.warmed_up is True
        await client.aclose()

    async def test_rediscovers_and_retries_once_on_failure(self) -> None:
        # Simulates the node rebooting onto a different DHCP address mid-session.
        state = {"sensor_calls": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/health":
                return httpx.Response(200, json=HEALTH_BODY)
            state["sensor_calls"] += 1
            if state["sensor_calls"] == 1:
                raise httpx.ConnectError("dropped", request=request)
            return httpx.Response(200, json=SENSOR_BODY)

        client = build_client(handler)
        reading = await client.sensors()  # must succeed via the retry
        assert reading.node_id == "aria-test"
        assert state["sensor_calls"] == 2
        await client.aclose()

    async def test_raises_when_the_retry_also_fails(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/health":
                return httpx.Response(200, json=HEALTH_BODY)
            raise httpx.ConnectError("still down", request=request)

        client = build_client(handler)
        with pytest.raises(NodeError):
            await client.sensors()
        await client.aclose()

    async def test_rejects_an_invalid_sensor_payload(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/health":
                return httpx.Response(200, json=HEALTH_BODY)
            # gas_raw beyond the 12-bit ADC range: a miswired or buggy node.
            return httpx.Response(200, json={**SENSOR_BODY, "gas_raw": 99999})

        client = build_client(handler)
        with pytest.raises(NodeError, match="failed validation"):
            await client.sensors()
        await client.aclose()

    async def test_rejects_non_json_body(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/health":
                return httpx.Response(200, json=HEALTH_BODY)
            return httpx.Response(200, text="<html>not json</html>")

        client = build_client(handler)
        with pytest.raises(NodeError):
            await client.sensors()
        await client.aclose()

    async def test_sets_actuators(self) -> None:
        captured: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/health":
                return httpx.Response(200, json=HEALTH_BODY)
            captured["content"] = request.content.decode()
            return httpx.Response(200, json={"led": True, "fan": False, "mode": "manual"})

        client = build_client(handler)
        state = await client.set_actuators(ActuatorCommand(led=True, mode="manual"))
        assert state.led is True
        assert state.mode == "manual"
        assert "led" in str(captured["content"])
        await client.aclose()

    async def test_empty_actuator_command_is_refused_before_sending(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            pytest.fail("no request should be made for an empty command")

        client = build_client(handler)
        with pytest.raises(NodeError, match="empty"):
            await client.set_actuators(ActuatorCommand())
        await client.aclose()

    async def test_gets_config(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/health":
                return httpx.Response(200, json=HEALTH_BODY)
            return httpx.Response(200, json=CONFIG_BODY)

        client = build_client(handler)
        assert (await client.get_config()).gas_threshold_pct == 60.0
        await client.aclose()

    async def test_sets_config_sends_only_changed_fields(self) -> None:
        captured: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/health":
                return httpx.Response(200, json=HEALTH_BODY)
            if request.method == "POST":
                captured["body"] = request.content.decode()
                return httpx.Response(200, json={**CONFIG_BODY, "gas_threshold_pct": 45.0})
            return httpx.Response(200, json=CONFIG_BODY)

        client = build_client(handler)
        config = await client.set_config(NodeConfigUpdate(gas_threshold_pct=45.0))

        assert config.gas_threshold_pct == 45.0
        body = str(captured["body"])
        assert "gas_threshold_pct" in body
        assert "dark_threshold_pct" not in body  # unchanged fields are not sent
        await client.aclose()

    async def test_empty_config_update_is_refused_before_sending(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            pytest.fail("no request should be made for an empty update")

        client = build_client(handler)
        with pytest.raises(NodeError, match="empty"):
            await client.set_config(NodeConfigUpdate())
        await client.aclose()

    async def test_reads_health(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=HEALTH_BODY)

        client = build_client(handler)
        assert (await client.health()).firmware == "1.0.0"
        await client.aclose()

    async def test_http_error_status_is_treated_as_failure(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/health":
                return httpx.Response(200, json=HEALTH_BODY)
            return httpx.Response(500, json={"error": "node exploded"})

        client = build_client(handler)
        with pytest.raises(NodeError):
            await client.sensors()
        await client.aclose()
