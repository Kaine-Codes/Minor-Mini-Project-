"""Auth: hashing, session tokens, and startup validation."""

from __future__ import annotations

import pytest

from aria.auth import (
    AuthConfigError,
    SessionManager,
    hash_password,
    validate_auth_config,
    verify_password,
)
from aria.config import Settings

from .conftest import TEST_PASSWORD


class TestPasswordHashing:
    def test_verifies_correct_password(self) -> None:
        assert verify_password(TEST_PASSWORD, hash_password(TEST_PASSWORD))

    def test_rejects_wrong_password(self) -> None:
        assert not verify_password("wrong", hash_password(TEST_PASSWORD))

    def test_salted_so_same_password_hashes_differently(self) -> None:
        first = hash_password(TEST_PASSWORD)
        second = hash_password(TEST_PASSWORD)
        assert first != second
        assert verify_password(TEST_PASSWORD, first)
        assert verify_password(TEST_PASSWORD, second)

    def test_never_stores_the_plaintext(self) -> None:
        assert TEST_PASSWORD not in hash_password(TEST_PASSWORD)

    def test_rejects_empty_password(self) -> None:
        with pytest.raises(ValueError):
            hash_password("")

    @pytest.mark.parametrize(
        "malformed",
        ["", "not-a-hash", "scrypt$onlyonepart", "bcrypt$aa$bb", "scrypt$zz$zz"],
    )
    def test_malformed_hash_fails_closed(self, malformed: str) -> None:
        # A corrupt stored hash must deny access, never accidentally allow it.
        assert not verify_password(TEST_PASSWORD, malformed)


class TestAuthConfigValidation:
    def test_accepts_valid_config(self, settings: Settings) -> None:
        validate_auth_config(settings)  # must not raise

    def test_rejects_missing_password_hash(self, settings: Settings) -> None:
        with pytest.raises(AuthConfigError, match="ARIA_PASSWORD_HASH"):
            validate_auth_config(settings.model_copy(update={"password_hash": ""}))

    def test_rejects_missing_session_secret(self, settings: Settings) -> None:
        with pytest.raises(AuthConfigError, match="ARIA_SESSION_SECRET"):
            validate_auth_config(settings.model_copy(update={"session_secret": ""}))

    def test_rejects_plaintext_password_in_hash_field(self, settings: Settings) -> None:
        # Guards the likely mistake of pasting the password where the hash belongs.
        with pytest.raises(AuthConfigError, match="not a valid scrypt hash"):
            validate_auth_config(settings.model_copy(update={"password_hash": "hunter2"}))


class _StubConnection:
    """Minimal stand-in exposing just the `.cookies` SessionManager.read needs."""

    def __init__(self, cookies: dict[str, str]) -> None:
        self.cookies = cookies


class TestSessionManager:
    def test_round_trips_a_valid_token(self, settings: Settings) -> None:
        manager = SessionManager(settings)
        token = manager._serializer.dumps({"u": "admin"})
        assert manager.read(_StubConnection({settings.session_cookie: token})) == "admin"

    def test_no_cookie_means_no_user(self, settings: Settings) -> None:
        assert SessionManager(settings).read(_StubConnection({})) is None

    def test_rejects_tampered_token(self, settings: Settings) -> None:
        manager = SessionManager(settings)
        token = manager._serializer.dumps({"u": "admin"})
        tampered = token[:-4] + "AAAA"
        assert manager.read(_StubConnection({settings.session_cookie: tampered})) is None

    def test_rejects_token_signed_with_another_secret(self, settings: Settings) -> None:
        forged = SessionManager(
            settings.model_copy(update={"session_secret": "a-different-secret"})
        )._serializer.dumps({"u": "admin"})
        assert SessionManager(settings).read(
            _StubConnection({settings.session_cookie: forged})
        ) is None

    def test_rejects_expired_token(self, settings: Settings) -> None:
        # TTL of 0 means any token is already past its lifetime.
        expiring = settings.model_copy(update={"session_ttl_s": 300})
        manager = SessionManager(expiring)
        token = manager._serializer.dumps({"u": "admin"})
        zero_ttl = SessionManager(settings.model_copy(update={"session_ttl_s": -1}))
        assert zero_ttl.read(_StubConnection({settings.session_cookie: token})) is None
