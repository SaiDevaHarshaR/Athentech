import pytest

from auth.license_service import (
    create_institution, update_institution, get_settings, update_settings,
)


def test_create_institution(isolated_db):
    inst = create_institution(name="Test Hosp", client_prefix="thosp", db_name="TestDB")
    assert inst["client_prefix"] == "THOSP"  # uppercased
    assert inst["db_name"] == "TestDB"


def test_update_institution_partial_fields_only(isolated_db):
    inst = create_institution(name="Test Hosp", client_prefix="THOSP", db_name="TestDB")
    updated = update_institution(inst["id"], status="Inactive", city="Testville")
    assert updated["status"] == "Inactive"
    assert updated["city"] == "Testville"
    assert updated["name"] == "Test Hosp"  # untouched field preserved


def test_update_nonexistent_institution_raises(isolated_db):
    with pytest.raises(ValueError):
        update_institution(99999, status="Active")


def test_settings_defaults_match_previous_hardcoded_values(isolated_db):
    s = get_settings()
    assert s["rate_limit_per_minute"] == 300
    assert s["license_validity_days"] == 90
    assert s["normal_mode_enabled"] is True
    assert s["output_redaction_enabled"] is True
    assert s["extra_blocked_patterns"] == []


def test_settings_update_persists(isolated_db):
    update_settings(rate_limit_per_minute=50, extra_blocked_patterns=["foo", "bar"], normal_mode_enabled=False)
    s = get_settings()
    assert s["rate_limit_per_minute"] == 50
    assert s["extra_blocked_patterns"] == ["foo", "bar"]
    assert s["normal_mode_enabled"] is False


def test_smtp_settings_round_trip(isolated_db):
    update_settings(smtp_host="smtp.example.com", smtp_port=587, smtp_user="bot@example.com", alert_email_to="ops@example.com")
    s = get_settings()
    assert s["smtp_host"] == "smtp.example.com"
    assert s["smtp_port"] == 587
    assert s["smtp_user"] == "bot@example.com"
    assert s["alert_email_to"] == "ops@example.com"


def test_settings_update_ignores_none_values(isolated_db):
    update_settings(rate_limit_per_minute=42)
    update_settings(rate_limit_per_minute=None)  # should be a no-op, not reset to a default
    s = get_settings()
    assert s["rate_limit_per_minute"] == 42
