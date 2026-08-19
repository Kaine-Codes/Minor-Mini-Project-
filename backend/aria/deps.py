"""Dependency accessors for the objects built once during app startup.

Routes ask for these rather than reaching into ``app.state`` themselves, which keeps the
route signatures explicit and makes them trivial to override in tests.
"""

from __future__ import annotations

from dataclasses import dataclass

from starlette.requests import HTTPConnection

from .config import Settings
from .hub import BroadcastHub
from .node_client import NodeClient
from .poller import NodePoller, RetentionSweeper
from .repository import EventRepository, ReadingRepository


@dataclass
class AppContext:
    """Everything with a lifetime tied to the application."""

    readings: ReadingRepository
    events: EventRepository
    node: NodeClient
    hub: BroadcastHub
    poller: NodePoller
    retention: RetentionSweeper


# Annotated as HTTPConnection, the common base of Request and WebSocket, so the same
# accessors work for both the REST routes and the live-feed socket.
def get_context(connection: HTTPConnection) -> AppContext:
    context = getattr(connection.app.state, "context", None)
    if context is None:
        raise RuntimeError("application context is not initialised")
    return context


def get_readings(connection: HTTPConnection) -> ReadingRepository:
    return get_context(connection).readings


def get_events(connection: HTTPConnection) -> EventRepository:
    return get_context(connection).events


def get_node(connection: HTTPConnection) -> NodeClient:
    return get_context(connection).node


def get_hub(connection: HTTPConnection) -> BroadcastHub:
    return get_context(connection).hub


def get_poller(connection: HTTPConnection) -> NodePoller:
    return get_context(connection).poller


def get_app_settings(connection: HTTPConnection) -> Settings:
    """The Settings this app was built with.

    Routes must read config from here rather than calling ``get_settings()`` again:
    otherwise ``create_app(settings)`` would validate one configuration and then serve
    a different one loaded from the environment.
    """
    settings = getattr(connection.app.state, "settings", None)
    if settings is None:
        raise RuntimeError("application settings are not initialised")
    return settings
