"""HTTP client for the ESP32 node — the only module that talks to hardware.

Implements the client half of ``docs/CONTRACT.md``. The node is a plain HTTP server on
the LAN advertising itself as ``aria.local``; this client discovers a working host from
an ordered candidate list and remembers it.

Why redundant candidates: mDNS resolution of ``.local`` works natively on macOS
(Bonjour) and on Linux with Avahi, but a stray router or a locked-down campus network
can break it. Falling back to a static IP means demo day does not depend on a single
discovery mechanism.
"""

from __future__ import annotations

import logging
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from .config import Settings
from .models import (
    ActuatorCommand,
    ActuatorStateWithMode,
    NodeConfig,
    NodeConfigUpdate,
    NodeHealth,
    SensorReading,
)

logger = logging.getLogger(__name__)

ModelT = TypeVar("ModelT", bound=BaseModel)


class NodeError(RuntimeError):
    """The node was unreachable, timed out, or returned something unusable."""


class NodeUnreachable(NodeError):
    """No candidate host answered."""


class NodeClient:
    """Talks to the node, caching whichever candidate host is currently answering."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client or httpx.AsyncClient(timeout=settings.node_timeout_s)
        self._owns_client = client is None
        self._active_host: str | None = None

    @property
    def active_host(self) -> str | None:
        """The host that last answered successfully, if any."""
        return self._active_host

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    # --- discovery ---------------------------------------------------------- #

    def _candidates(self) -> list[str]:
        """Cached host first, then the configured list, without duplicates."""
        ordered = list(self._settings.node_hosts)
        if self._active_host:
            ordered = [self._active_host] + [
                h for h in ordered if h != self._active_host
            ]
        return ordered

    async def discover(self) -> str:
        """Return the first candidate host answering ``GET /health``.

        Raises :class:`NodeUnreachable` when none do.
        """
        errors: list[str] = []
        for host in self._candidates():
            url = f"{self._settings.node_base_url(host)}/health"
            try:
                response = await self._client.get(url)
                response.raise_for_status()
                NodeHealth.model_validate(response.json())
            except (httpx.HTTPError, ValidationError, ValueError) as exc:
                errors.append(f"{host}: {type(exc).__name__}")
                continue
            if self._active_host != host:
                logger.info("ARIA node reachable at %s", host)
            self._active_host = host
            return host

        self._active_host = None
        raise NodeUnreachable(
            "no ARIA node answered on any candidate host ("
            + "; ".join(errors)
            + ")"
        )

    # --- request plumbing --------------------------------------------------- #

    async def _request(
        self, method: str, path: str, *, json: dict[str, object] | None = None
    ) -> object:
        """Issue one request against the active host, rediscovering once on failure."""
        host = self._active_host or await self.discover()
        url = f"{self._settings.node_base_url(host)}{path}"
        try:
            response = await self._client.request(method, url, json=json)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            # The node may have rebooted onto a new address. Rediscover and retry once
            # before declaring failure, so a DHCP lease change is self-healing.
            self._active_host = None
            retry_host = await self.discover()
            retry_url = f"{self._settings.node_base_url(retry_host)}{path}"
            try:
                response = await self._client.request(method, retry_url, json=json)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as retry_exc:
                raise NodeError(
                    f"{method} {path} failed: {retry_exc!r} (first attempt: {exc!r})"
                ) from retry_exc
        except ValueError as exc:  # malformed JSON body
            raise NodeError(f"{method} {path} returned invalid JSON: {exc}") from exc

    # --- contract methods --------------------------------------------------- #

    async def health(self) -> NodeHealth:
        return self._validate(NodeHealth, await self._request("GET", "/health"))

    async def sensors(self) -> SensorReading:
        return self._validate(SensorReading, await self._request("GET", "/sensors"))

    async def set_actuators(self, command: ActuatorCommand) -> ActuatorStateWithMode:
        payload = command.as_payload()
        if not payload:
            raise NodeError("actuator command was empty")
        return self._validate(
            ActuatorStateWithMode, await self._request("POST", "/actuators", json=payload)
        )

    async def get_config(self) -> NodeConfig:
        return self._validate(NodeConfig, await self._request("GET", "/config"))

    async def set_config(self, update: NodeConfigUpdate) -> NodeConfig:
        payload = update.as_payload()
        if not payload:
            raise NodeError("config update was empty")
        return self._validate(
            NodeConfig, await self._request("POST", "/config", json=payload)
        )

    @staticmethod
    def _validate(model: type[ModelT], payload: object) -> ModelT:
        """Never trust the node's response shape — validate before it goes anywhere."""
        try:
            return model.model_validate(payload)
        except ValidationError as exc:
            raise NodeError(f"node response failed validation: {exc}") from exc
