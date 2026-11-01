import os

import pytest

from backend.admin.security import (
    PASSWORD_MIN,
    hash_password,
    make_session,
    read_session,
    role_allowed,
    session_serializer,
    verify_password,
)


def test_hash_password_round_trip_and_wrong_password():
    encoded = hash_password("a-strong-password")

    assert encoded.startswith("scrypt$")
    assert verify_password("a-strong-password", encoded)
    assert not verify_password("wrong-password", encoded)


def test_hash_password_rejects_short_password():
    with pytest.raises(ValueError, match=str(PASSWORD_MIN)):
        hash_password("short")


def test_verify_password_rejects_malformed_hash():
    assert not verify_password("anything", "not-a-password-hash")


def test_session_requires_secret(monkeypatch):
    monkeypatch.delenv("CET_ADMIN_SESSION_SECRET", raising=False)

    with pytest.raises(RuntimeError, match="CET_ADMIN_SESSION_SECRET"):
        session_serializer()


def test_session_round_trip(monkeypatch):
    monkeypatch.setenv("CET_ADMIN_SESSION_SECRET", "test-only-secret")

    token = make_session(42, "DATA_ADMIN", auth_version=7)
    assert read_session(token) == {"uid": 42, "role": "DATA_ADMIN", "av": 7}
    assert read_session("invalid-session") is None


def test_role_allowed():
    assert role_allowed("DATA_ADMIN", {"SUPER_ADMIN", "DATA_ADMIN"})
    assert not role_allowed("READ_ONLY", {"SUPER_ADMIN", "DATA_ADMIN"})
