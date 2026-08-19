"""Dashboard authentication.

Scope note: a single operator account is sufficient here, and is what the project scope
calls for. What is *not* acceptable at any scope is a plaintext or default password, so:

- the password is stored only as a salted **scrypt** hash, supplied by environment
  variable (generate with ``python -m aria.hashpw``);
- the app refuses to start if the hash or session secret is missing, rather than falling
  back to a well-known default;
- comparison is constant-time;
- the session is a signed, HTTP-only cookie with an explicit TTL.

WebAuthn/biometric login is deliberately out of scope — see the project's Future Scope.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, Response, WebSocket, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .config import Settings
from .deps import get_app_settings

logger = logging.getLogger(__name__)

_SCHEME = "scrypt"
# Chosen for a comfortable ~100ms verify on a laptop; raises the cost of offline
# guessing without making login feel slow.
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_DKLEN = 32
_SALT_BYTES = 16


class AuthConfigError(RuntimeError):
    """Auth is misconfigured — missing hash or secret. Raised at startup, not runtime."""


def hash_password(password: str) -> str:
    """Hash ``password`` into a self-describing ``scrypt$salt$hash`` string."""
    if not password:
        raise ValueError("password must not be empty")
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_DKLEN
    )
    return f"{_SCHEME}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    """Constant-time check of ``password`` against an encoded hash."""
    try:
        scheme, salt_hex, digest_hex = encoded.split("$", 2)
        if scheme != _SCHEME:
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (ValueError, AttributeError):
        logger.error("stored password hash is malformed")
        return False

    candidate = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=len(expected),
    )
    return hmac.compare_digest(candidate, expected)


@dataclass(frozen=True)
class SessionManager:
    """Issues and validates signed session cookies."""

    settings: Settings

    @property
    def _serializer(self) -> URLSafeTimedSerializer:
        return URLSafeTimedSerializer(self.settings.session_secret, salt="aria-session")

    def issue(self, response: Response, username: str) -> None:
        token = self._serializer.dumps({"u": username})
        response.set_cookie(
            key=self.settings.session_cookie,
            value=token,
            max_age=self.settings.session_ttl_s,
            httponly=True,
            samesite="lax",
            secure=self.settings.cookie_secure,
            path="/",
        )

    def clear(self, response: Response) -> None:
        response.delete_cookie(self.settings.session_cookie, path="/")

    def read(self, connection: Request | WebSocket) -> str | None:
        """Return the username from a valid session cookie, else ``None``.

        Accepts a WebSocket too: the browser sends cookies on the upgrade handshake, so
        the live feed authenticates exactly like the REST routes.
        """
        token = connection.cookies.get(self.settings.session_cookie)
        if not token:
            return None
        try:
            payload = self._serializer.loads(token, max_age=self.settings.session_ttl_s)
        except (BadSignature, SignatureExpired):
            return None
        username = payload.get("u") if isinstance(payload, dict) else None
        return username if isinstance(username, str) else None


def validate_auth_config(settings: Settings) -> None:
    """Fail fast at startup when auth secrets are absent."""
    missing = [
        name
        for name, value in (
            ("ARIA_PASSWORD_HASH", settings.password_hash),
            ("ARIA_SESSION_SECRET", settings.session_secret),
        )
        if not value
    ]
    if missing:
        raise AuthConfigError(
            f"missing required setting(s): {', '.join(missing)}. "
            "Generate a password hash with `python -m aria.hashpw` and a session "
            "secret with `python -c \"import secrets;print(secrets.token_hex(32))\"`, "
            "then put both in backend/.env (see .env.example)."
        )
    if not settings.password_hash.startswith(f"{_SCHEME}$"):
        raise AuthConfigError(
            "ARIA_PASSWORD_HASH is not a valid scrypt hash — regenerate it with "
            "`python -m aria.hashpw`"
        )


def get_session_manager(settings: Settings = Depends(get_app_settings)) -> SessionManager:
    return SessionManager(settings)


def require_user(
    request: Request,
    sessions: SessionManager = Depends(get_session_manager),
) -> str:
    """FastAPI dependency guarding every non-public route."""
    username = sessions.read(request)
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required"
        )
    return username
