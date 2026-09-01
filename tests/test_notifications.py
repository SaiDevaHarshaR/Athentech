from unittest.mock import patch, MagicMock

from auth.license_service import update_settings, create_institution, create_license
from notifications.email import send_alert_email
from notifications.webhook import send_webhook_alert


def test_email_disabled_does_not_attempt_send(isolated_db):
    update_settings(email_alerts_enabled=False)
    ok, msg = send_alert_email("Test", "body")
    assert ok is False
    assert "disabled" in msg.lower()


def test_email_enabled_but_unconfigured_fails_cleanly(isolated_db):
    update_settings(email_alerts_enabled=True, alert_email_to="admin@test.com")
    ok, msg = send_alert_email("Test", "body")
    assert ok is False
    assert "smtp host" in msg.lower()


def test_email_fully_configured_calls_smtp_correctly(isolated_db):
    update_settings(
        email_alerts_enabled=True, smtp_host="smtp.test.com", smtp_port=587,
        smtp_user="bot@test.com", smtp_password="secret", alert_email_to="admin@test.com",
    )
    with patch("smtplib.SMTP") as mock_smtp:
        instance = MagicMock()
        mock_smtp.return_value.__enter__.return_value = instance
        ok, msg = send_alert_email("License expiring", "ABC-123 expires soon")

        assert ok is True
        mock_smtp.assert_called_once_with("smtp.test.com", 587, timeout=10)
        instance.starttls.assert_called_once()
        instance.login.assert_called_once_with("bot@test.com", "secret")
        assert instance.sendmail.call_args[0][1] == ["admin@test.com"]


def test_email_smtp_failure_is_caught_not_raised(isolated_db):
    update_settings(email_alerts_enabled=True, smtp_host="smtp.test.com", alert_email_to="a@test.com")
    with patch("smtplib.SMTP", side_effect=ConnectionRefusedError("refused")):
        ok, msg = send_alert_email("Test", "body")
        assert ok is False
        assert "refused" in msg.lower() or "connectionrefused" in msg.lower()


def test_webhook_unconfigured_fails_cleanly(isolated_db):
    update_settings(webhook_url="")
    ok, msg = send_webhook_alert("test_event", {"x": 1})
    assert ok is False


def test_webhook_posts_json_to_configured_url(isolated_db):
    update_settings(webhook_url="https://hooks.example.com/alert")
    with patch("urllib.request.urlopen") as mock_open:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_open.return_value.__enter__.return_value = mock_resp

        ok, msg = send_webhook_alert("licenses_expiring", {"count": 2})

        assert ok is True
        req = mock_open.call_args[0][0]
        assert req.full_url == "https://hooks.example.com/alert"
        assert req.get_method() == "POST"


def test_webhook_http_error_is_caught_not_raised(isolated_db):
    import urllib.error
    update_settings(webhook_url="https://hooks.example.com/alert")
    with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError("url", 500, "Server Error", {}, None)):
        ok, msg = send_webhook_alert("test", {})
        assert ok is False
        assert "500" in msg


def test_expiry_checker_finds_only_licenses_in_window(isolated_db):
    from notifications.expiry_checker import get_expiring_licenses

    inst = create_institution(name="ExpiryTest", client_prefix="EXPT", db_name="ExpTestDB")
    soon = create_license(institution_id=inst["id"], role="doctor", phone="9999999999", dob_year="1990", valid_days=3)
    far = create_license(institution_id=inst["id"], role="nurse", phone="8888888888", dob_year="1991", valid_days=60)

    expiring = get_expiring_licenses(days_ahead=7)
    codes = [l["code"] for l in expiring]

    assert soon["code"] in codes
    assert far["code"] not in codes


def test_expiry_checker_once_per_day_guard(isolated_db):
    import notifications.expiry_checker as ec

    inst = create_institution(name="ExpiryTest2", client_prefix="EXPT2", db_name="ExpTestDB2")
    create_license(institution_id=inst["id"], role="doctor", phone="7777777777", dob_year="1990", valid_days=2)

    update_settings(email_alerts_enabled=True, smtp_host="smtp.test.com", smtp_port=587, alert_email_to="a@test.com")
    ec._last_alert_date = None

    with patch("smtplib.SMTP") as mock_smtp:
        instance = MagicMock()
        mock_smtp.return_value.__enter__.return_value = instance

        result1 = ec.check_and_alert(days_ahead=7)
        assert result1["alerts_sent"][0]["success"] is True
        assert mock_smtp.call_count == 1

        result2 = ec.check_and_alert(days_ahead=7)
        assert "skipped" in result2
        assert mock_smtp.call_count == 1  # not called again same day
