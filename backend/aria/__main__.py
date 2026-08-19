"""Entry point:  python -m aria   (or the ``aria`` console script).

Uses uvicorn's factory mode so :func:`aria.main.create_app` runs its startup validation
before the server binds — a missing password hash fails immediately with a clear
message rather than booting an unprotected dashboard.
"""

from __future__ import annotations

import logging
import sys

import uvicorn

from .auth import AuthConfigError
from .config import get_settings
from .main import create_app


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    settings = get_settings()

    try:
        create_app(settings)  # validate before binding the port
    except AuthConfigError as exc:
        print(f"\nARIA cannot start:\n  {exc}\n", file=sys.stderr)
        return 1

    uvicorn.run(
        "aria.main:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
