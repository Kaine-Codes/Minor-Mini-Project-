"""Application settings.

Every tunable lives here and is overridable by environment variable (prefix ``ARIA_``)
so nothing operational is hardcoded at a call site.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# NoDecode stops pydantic-settings from trying to JSON-parse these before our own
# validator runs, so plain comma-separated env values work as intended.
CsvTuple = Annotated[tuple[str, ...], NoDecode]


class Settings(BaseSettings):
    """Runtime configuration, read from the environment and/or a ``.env`` file."""

    model_config = SettingsConfigDict(
        env_prefix="ARIA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Node discovery -----------------------------------------------------
    # Tried in order; the first host answering GET /health is cached and reused.
    # Redundant candidates exist so demo day does not hinge on mDNS alone.
    node_hosts: CsvTuple = ("aria.local", "192.168.1.50")
    node_port: int = 80
    node_timeout_s: float = 3.0

    # --- Polling ------------------------------------------------------------
    poll_interval_s: float = Field(default=5.0, ge=1.0, le=300.0)
    # Consecutive poll failures before the node is reported offline.
    offline_after_failures: int = Field(default=3, ge=1)

    # --- Storage ------------------------------------------------------------
    db_path: Path = Path("aria.db")
    retention_days: int = Field(default=14, ge=1, le=3650)
    retention_sweep_interval_s: float = Field(default=3600.0, ge=60.0)

    # --- Auth ---------------------------------------------------------------
    # Required. Generate with:  python -m aria.hashpw
    password_hash: str = ""
    username: str = "admin"
    session_secret: str = ""
    session_ttl_s: int = Field(default=7 * 24 * 3600, ge=300)
    session_cookie: str = "aria_session"
    # Cookie Secure flag. Off by default: the LAN/Tailscale demo is plain HTTP.
    cookie_secure: bool = False

    # --- Serving ------------------------------------------------------------
    host: str = "0.0.0.0"
    port: int = 8000
    # Directory holding the built React bundle (frontend/dist).
    static_dir: Path = Path("../frontend/dist")
    # Dashboard origin during development (Vite dev server) for CORS.
    dev_origins: CsvTuple = ("http://localhost:5173", "http://127.0.0.1:5173")

    @field_validator("node_hosts", "dev_origins", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        """Allow ``ARIA_NODE_HOSTS=aria.local,192.168.1.50`` in the environment."""
        if isinstance(value, str):
            return tuple(part.strip() for part in value.split(",") if part.strip())
        return value

    def node_base_url(self, host: str) -> str:
        """Base URL for a given candidate host."""
        return f"http://{host}:{self.node_port}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
