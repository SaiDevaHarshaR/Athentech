import pytest

from auth.admin_auth import create_admin_token, verify_admin_token
from fastapi import HTTPException


def test_token_round_trips(admin_env):
    token = create_admin_token("admin")
    username = verify_admin_token(token)
    assert username == "admin"


def test_tampered_token_is_rejected(admin_env):
    token = create_admin_token("admin")
    tampered = token[:-2] + "xx"
    with pytest.raises(HTTPException) as exc_info:
        verify_admin_token(tampered)
    assert exc_info.value.status_code == 401


def test_garbage_token_is_rejected(admin_env):
    with pytest.raises(HTTPException):
        verify_admin_token("not-a-real-token")


def test_expired_token_is_rejected(admin_env, monkeypatch):
    import auth.admin_auth as admin_auth_module
    token = create_admin_token("admin")

    # Simulate time passing beyond the TTL.
    monkeypatch.setattr(admin_auth_module, "TOKEN_TTL_SECONDS", -1)
    with pytest.raises(HTTPException) as exc_info:
        verify_admin_token(token)
    assert "expired" in exc_info.value.detail.lower()
