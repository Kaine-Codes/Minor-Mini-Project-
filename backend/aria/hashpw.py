"""Generate the credentials ARIA needs in ``backend/.env``.

    python -m aria.hashpw

Prompts for a password (without echoing it) and prints both the scrypt hash and a fresh
session secret, ready to paste.
"""

from __future__ import annotations

import getpass
import secrets
import sys

from .auth import hash_password


def main() -> int:
    password = getpass.getpass("Dashboard password: ")
    if not password:
        print("error: password must not be empty", file=sys.stderr)
        return 1
    if password != getpass.getpass("Confirm password: "):
        print("error: passwords did not match", file=sys.stderr)
        return 1
    if len(password) < 8:
        print("warning: shorter than 8 characters — consider a longer one", file=sys.stderr)

    print("\n# Paste these into backend/.env\n")
    print(f"ARIA_PASSWORD_HASH={hash_password(password)}")
    print(f"ARIA_SESSION_SECRET={secrets.token_hex(32)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
