"""
TOTP-based second factor — genuinely free, open standard (RFC 6238),
works with ANY authenticator app (Google Authenticator, Microsoft
Authenticator, Authy, etc.), not locked to one vendor despite the
common name "Google Authenticator."

Requires: pip install pyotp qrcode[pil]  (both free, open-source,
no external API calls at all — everything happens locally).

Per-license secret, same "per code" scope as the email OTP system —
whoever has the activation code scans the QR once, then everyone
using that code enters the same rotating 6-digit number.
"""

import base64
import io

import pyotp
import qrcode


def generate_totp_secret() -> str:
    """Real, random base32 secret — call once per license, store it
    in the licenses table (new totp_secret column)."""
    return pyotp.random_base32()


def generate_qr_code_data_uri(secret: str, hospital_name: str, code: str) -> str:
    """
    Builds a real, scannable QR code (as a base64 PNG data URI, so it
    can be dropped straight into an <img src="..."> tag with no file
    to host). The label shown in the authenticator app is
    "hospital_name (code)" so multiple licenses don't look identical
    in someone's app.
    """
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=code, issuer_name=f"Sahasra AI — {hospital_name}")

    qr = qrcode.QRCode(box_size=6, border=2)
    qr.add_data(uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{encoded}"


def verify_totp_code(secret: str, code: str) -> bool:
    """
    valid_window=1 allows the immediately-previous and next 30-second
    codes too — real-world clock drift between the phone and server
    is common enough that a zero-tolerance check would cause
    confusing, hard-to-debug false rejections.
    """
    if not secret or not code:
        return False
    totp = pyotp.TOTP(secret)
    return totp.verify(code.strip(), valid_window=1)