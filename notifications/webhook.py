"""
Actually calls the webhook URL the Settings page has been promising.
Uses urllib (stdlib) rather than adding a `requests` dependency for one
simple POST.
"""

import json
import urllib.request
import urllib.error


def send_webhook_alert(event: str, payload: dict) -> tuple[bool, str]:
    """
    Returns (success, message). Never raises — a misconfigured or down
    webhook endpoint should not crash whatever triggered the alert.
    """
    from auth.license_service import get_settings
    s = get_settings()

    url = s.get("webhook_url")
    if not url:
        return False, "No webhook URL configured in Settings."

    body = json.dumps({"event": event, "data": payload}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return True, f"Webhook responded with status {resp.status}"
    except urllib.error.HTTPError as e:
        return False, f"Webhook returned HTTP {e.code}: {e.reason}"
    except Exception as e:
        return False, f"Failed to call webhook: {type(e).__name__}: {e}"
