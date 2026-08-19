"""API integration tests.

The app is built with workers disabled and the node client swapped for a fake, so these
exercise real routing, real auth and the real response envelope without hardware.
"""

from __future__ import annotations

import httpx
import pytest
from asgi_lifespan import LifespanManager

from aria.config import Settings
from aria.main import create_app

from .conftest import TEST_PASSWORD, FakeNodeClient, make_reading
from aria.models import ActuatorState, EdgeState


@pytest.fixture
async def client(settings: Settings, fake_node: FakeNodeClient):
    """An HTTP client against the real app, with the node faked out."""
    app = create_app(settings, start_workers=False)
    async with LifespanManager(app):
        app.state.context.node = fake_node  # type: ignore[assignment]
        app.state.context.poller._client = fake_node  # type: ignore[assignment]
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as http_client:
            http_client.app_state = app.state  # type: ignore[attr-defined]
            yield http_client


async def login(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/auth/login", json={"username": "admin", "password": TEST_PASSWORD}
    )
    assert response.status_code == 200


class TestHealth:
    async def test_health_is_public(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["success"] is True


class TestAuthRoutes:
    async def test_login_succeeds_with_correct_credentials(
        self, client: httpx.AsyncClient
    ) -> None:
        response = await client.post(
            "/api/auth/login", json={"username": "admin", "password": TEST_PASSWORD}
        )
        assert response.status_code == 200
        assert response.cookies.get("aria_session") is not None

    async def test_login_fails_with_wrong_password(self, client: httpx.AsyncClient) -> None:
        response = await client.post(
            "/api/auth/login", json={"username": "admin", "password": "nope"}
        )
        assert response.status_code == 401
        assert response.json()["success"] is False

    async def test_login_fails_with_wrong_username(self, client: httpx.AsyncClient) -> None:
        response = await client.post(
            "/api/auth/login", json={"username": "root", "password": TEST_PASSWORD}
        )
        assert response.status_code == 401

    async def test_error_message_does_not_reveal_which_factor_was_wrong(
        self, client: httpx.AsyncClient
    ) -> None:
        bad_user = await client.post(
            "/api/auth/login", json={"username": "root", "password": TEST_PASSWORD}
        )
        bad_pass = await client.post(
            "/api/auth/login", json={"username": "admin", "password": "nope"}
        )
        assert bad_user.json()["error"] == bad_pass.json()["error"]

    async def test_session_probe_is_public(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/auth/session")
        assert response.status_code == 200
        assert response.json()["data"]["authenticated"] is False

    async def test_session_reports_authenticated_after_login(
        self, client: httpx.AsyncClient
    ) -> None:
        await login(client)
        response = await client.get("/api/auth/session")
        assert response.json()["data"]["authenticated"] is True

    async def test_logout_clears_access(self, client: httpx.AsyncClient) -> None:
        await login(client)
        assert (await client.get("/api/status")).status_code == 200

        await client.post("/api/auth/logout")
        assert (await client.get("/api/status")).status_code == 401


class TestAuthorization:
    @pytest.mark.parametrize(
        "path",
        [
            "/api/status",
            "/api/readings/latest",
            "/api/readings/history",
            "/api/events",
            "/api/stats",
            "/api/actuators",
            "/api/config",
        ],
    )
    async def test_protected_routes_require_auth(
        self, client: httpx.AsyncClient, path: str
    ) -> None:
        response = await client.get(path)
        assert response.status_code == 401
        assert response.json()["success"] is False

    @pytest.mark.parametrize("path", ["/api/actuators", "/api/config"])
    async def test_protected_posts_require_auth(
        self, client: httpx.AsyncClient, path: str
    ) -> None:
        assert (await client.post(path, json={})).status_code == 401


class TestReadings:
    async def test_status_returns_envelope(self, client: httpx.AsyncClient) -> None:
        await login(client)
        body = (await client.get("/api/status")).json()
        assert body["success"] is True
        assert "status" in body["data"]

    async def test_history_is_empty_before_any_poll(self, client: httpx.AsyncClient) -> None:
        await login(client)
        body = (await client.get("/api/readings/history")).json()
        assert body["data"] == []
        assert body["meta"]["count"] == 0

    async def test_history_returns_polled_data(self, client: httpx.AsyncClient) -> None:
        await login(client)
        await client.app_state.context.poller.tick()  # type: ignore[attr-defined]

        body = (await client.get("/api/readings/history")).json()
        assert body["meta"]["count"] == 1

    @pytest.mark.parametrize("query", ["hours=0", "hours=721", "limit=0", "limit=99999"])
    async def test_history_rejects_out_of_range_query(
        self, client: httpx.AsyncClient, query: str
    ) -> None:
        await login(client)
        response = await client.get(f"/api/readings/history?{query}")
        assert response.status_code == 422
        assert response.json()["success"] is False


class TestActuatorRoutes:
    async def test_reads_actuator_state(self, client: httpx.AsyncClient) -> None:
        await login(client)
        body = (await client.get("/api/actuators")).json()
        assert set(body["data"]) == {"led", "fan", "mode"}

    async def test_sets_actuator_state(self, client: httpx.AsyncClient) -> None:
        await login(client)
        body = (await client.post("/api/actuators", json={"led": True})).json()
        assert body["success"] is True
        assert body["data"]["led"] is True

    async def test_empty_command_is_rejected(self, client: httpx.AsyncClient) -> None:
        await login(client)
        response = await client.post("/api/actuators", json={})
        assert response.status_code == 400
        assert "at least one" in response.json()["error"]

    async def test_unknown_field_is_rejected(self, client: httpx.AsyncClient) -> None:
        await login(client)
        response = await client.post("/api/actuators", json={"laser": True})
        assert response.status_code == 422

    async def test_invalid_mode_is_rejected(self, client: httpx.AsyncClient) -> None:
        await login(client)
        response = await client.post("/api/actuators", json={"mode": "turbo"})
        assert response.status_code == 422

    async def test_command_is_recorded_as_an_event(self, client: httpx.AsyncClient) -> None:
        await login(client)
        await client.post("/api/actuators", json={"led": True})

        events = (await client.get("/api/events")).json()["data"]
        assert any(row["kind"] == "command" for row in events)

    async def test_alarm_overrides_a_manual_off_command(
        self, client: httpx.AsyncClient, fake_node: FakeNodeClient
    ) -> None:
        await login(client)
        fake_node.reading = make_reading(
            actuators=ActuatorState(led=True, fan=True),
            edge=EdgeState(gas_alarm=True, warmed_up=True, mode="auto"),
        )

        body = (await client.post("/api/actuators", json={"fan": False})).json()

        # The node must refuse to let the network switch the fan off mid-alarm, and the
        # response must report the state actually in effect.
        assert body["data"]["fan"] is True

    async def test_returns_503_when_node_unreachable(
        self, client: httpx.AsyncClient, fake_node: FakeNodeClient
    ) -> None:
        await login(client)
        fake_node.go_offline()

        response = await client.post("/api/actuators", json={"led": True})
        assert response.status_code == 503
        assert response.json()["success"] is False


class TestConfigRoutes:
    async def test_reads_config(self, client: httpx.AsyncClient) -> None:
        await login(client)
        body = (await client.get("/api/config")).json()
        assert body["data"]["gas_threshold_pct"] == 60.0

    async def test_updates_config(self, client: httpx.AsyncClient) -> None:
        await login(client)
        body = (await client.post("/api/config", json={"gas_threshold_pct": 45.0})).json()
        assert body["data"]["gas_threshold_pct"] == 45.0

    async def test_partial_update_leaves_other_fields_alone(
        self, client: httpx.AsyncClient
    ) -> None:
        await login(client)
        body = (await client.post("/api/config", json={"gas_threshold_pct": 45.0})).json()
        assert body["data"]["dark_threshold_pct"] == 25.0

    async def test_empty_update_is_rejected(self, client: httpx.AsyncClient) -> None:
        await login(client)
        response = await client.post("/api/config", json={})
        assert response.status_code == 400

    @pytest.mark.parametrize(
        "payload",
        [
            {"gas_threshold_pct": 500},
            {"motion_light_hold_s": 1},
            {"temp_fan_threshold_c": -5},
            {"warmup_s": 9999},
        ],
    )
    async def test_out_of_range_update_is_rejected(
        self, client: httpx.AsyncClient, payload: dict[str, object]
    ) -> None:
        await login(client)
        response = await client.post("/api/config", json=payload)
        assert response.status_code == 422
        assert response.json()["success"] is False

    async def test_config_change_is_recorded_as_an_event(
        self, client: httpx.AsyncClient
    ) -> None:
        await login(client)
        await client.post("/api/config", json={"gas_threshold_pct": 45.0})

        events = (await client.get("/api/events")).json()["data"]
        assert any(row["kind"] == "config" for row in events)

    async def test_returns_503_when_node_unreachable(
        self, client: httpx.AsyncClient, fake_node: FakeNodeClient
    ) -> None:
        await login(client)
        fake_node.go_offline()

        assert (await client.get("/api/config")).status_code == 503


class TestErrorEnvelope:
    async def test_unknown_api_route_is_enveloped(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/does-not-exist")
        assert response.status_code == 404
        assert response.json()["success"] is False

    async def test_validation_errors_use_the_envelope(
        self, client: httpx.AsyncClient
    ) -> None:
        # Not FastAPI's default {"detail": [...]}: the dashboard parses one shape only.
        await login(client)
        body = (await client.post("/api/config", json={"gas_threshold_pct": 500})).json()
        assert set(body) == {"success", "data", "error", "meta"}
        assert isinstance(body["error"], str)
