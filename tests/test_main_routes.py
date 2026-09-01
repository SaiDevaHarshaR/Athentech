"""
End-to-end tests against the real FastAPI app via TestClient. Unlike the
other test files, these share one isolated app/DB for the whole module
(FastAPI apps have module-level startup side effects — seeding the DB,
starting the background expiry-check thread — that only make sense to
run once), so each test uses unique names/codes to avoid colliding with
other tests in this file rather than assuming a pristine DB each time.
"""

import hashlib
import os

import pytest


@pytest.fixture(scope="module")
def client(tmp_path_factory, monkeypatch_module):
    tmp_path = tmp_path_factory.mktemp("main_routes_test")
    monkeypatch_module.chdir(tmp_path)
    os.makedirs("audit", exist_ok=True)

    # config.settings is a singleton read from the environment once, at
    # first import — which may have already happened (env vars set here
    # would be too late). Patch the already-instantiated object directly
    # instead, same as the admin_env fixture in conftest.py does.
    from config import settings as app_settings
    monkeypatch_module.setattr(app_settings, "admin_username", "admin")
    monkeypatch_module.setattr(app_settings, "admin_password_hash", hashlib.sha256(b"bootpass123").hexdigest())
    monkeypatch_module.setattr(app_settings, "admin_secret_key", "test-secret-key")
    monkeypatch_module.setattr(app_settings, "groq_api_key", "fake")
    monkeypatch_module.setattr(app_settings, "tavily_api_key", "fake")

    from fastapi.testclient import TestClient
    import main as main_module
    return TestClient(main_module.app)


@pytest.fixture(scope="module")
def monkeypatch_module():
    # pytest's built-in monkeypatch fixture is function-scoped; this gives
    # the same capability at module scope for the shared `client` fixture above.
    from _pytest.monkeypatch import MonkeyPatch
    mp = MonkeyPatch()
    yield mp
    mp.undo()


@pytest.fixture(scope="module")
def admin_headers(client):
    r = client.post("/admin/login", json={"username": "admin", "password": "bootpass123"})
    assert r.status_code == 200
    token = r.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_unauthenticated_admin_route_is_blocked(client):
    r = client.get("/admin/settings")
    assert r.status_code == 401


def test_login_succeeds_with_correct_credentials(client):
    r = client.post("/admin/login", json={"username": "admin", "password": "bootpass123"})
    assert r.status_code == 200
    assert "token" in r.json()


def test_login_fails_with_wrong_password(client):
    r = client.post("/admin/login", json={"username": "admin", "password": "wrongpassword"})
    assert r.status_code == 401


def test_settings_get_and_put_round_trip(client, admin_headers):
    r = client.get("/admin/settings", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["settings"]["rate_limit_per_minute"] == 300

    r2 = client.put("/admin/settings", headers=admin_headers, json={"rate_limit_per_minute": 42})
    assert r2.json()["settings"]["rate_limit_per_minute"] == 42
    assert r2.json()["settings"]["license_validity_days"] == 90  # untouched field preserved


def test_institution_create_then_patch(client, admin_headers):
    r = client.post("/admin/institutions", headers=admin_headers,
                     json={"name": "Route Test Hosp", "client_prefix": "RTHOSP", "db_name": "RouteTestDB"})
    assert r.status_code == 200
    inst_id = r.json()["institution"]["id"]

    r2 = client.patch(f"/admin/institutions/{inst_id}", headers=admin_headers, json={"status": "Inactive"})
    assert r2.json()["institution"]["status"] == "Inactive"
    assert r2.json()["institution"]["name"] == "Route Test Hosp"


def test_multi_admin_create_and_deactivate(client, admin_headers):
    r = client.post("/admin/users", headers=admin_headers,
                     json={"username": "route_test_admin", "password": "realpassword123", "display_name": "Route Test"})
    assert r.status_code == 200
    assert r.json()["status"] == "success"

    r2 = client.post("/admin/login", json={"username": "route_test_admin", "password": "realpassword123"})
    assert r2.status_code == 200

    r3 = client.post("/admin/users/route_test_admin/status", headers=admin_headers, json={"status": "Inactive"})
    assert r3.json()["status"] == "success"

    r4 = client.post("/admin/login", json={"username": "route_test_admin", "password": "realpassword123"})
    assert r4.status_code == 401


def test_admin_actions_are_attributed_in_audit_log(client, admin_headers):
    client.post("/admin/institutions", headers=admin_headers,
                json={"name": "Audit Attribution Test", "client_prefix": "AUDATT", "db_name": "AuditTestDB"})

    r = client.get("/admin/audit", headers=admin_headers)
    events = r.json()["events"]
    matching = [e for e in events if e["event"] == "admin_action" and "Audit Attribution Test" in (e.get("question") or "")]
    assert len(matching) == 1
    assert matching[0]["meta"]["actor"] == "admin"


def test_notification_test_endpoint_does_not_crash_when_unconfigured(client, admin_headers):
    r = client.post("/admin/notifications/test", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["email"]["success"] is False
    assert r.json()["webhook"]["success"] is False


def test_ask_with_invalid_activation_code_logs_failure_event(client, admin_headers):
    r = client.post("/ask", json={"question": "hi", "activation_code": "TOTALLY-FAKE-CODE"})
    assert r.status_code == 200
    assert r.json()["status"] == "error"

    r2 = client.get("/admin/audit", headers=admin_headers)
    events = r2.json()["events"]
    invalid_attempts = [e for e in events if e["event"] == "invalid_code_attempt" and e.get("code") == "TOTALLY-FAKE-CODE"]
    assert len(invalid_attempts) == 1
