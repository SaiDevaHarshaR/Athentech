from cryptography.fernet import Fernet

import config
from auth.secrets_crypto import encrypt_secret, decrypt_secret, is_encrypted


def _fresh_key(monkeypatch):
    monkeypatch.setattr(config.settings, "encryption_key", Fernet.generate_key().decode())


def test_encrypt_then_decrypt_round_trips(monkeypatch):
    _fresh_key(monkeypatch)
    plaintext = "Amrpp#2981J##"
    encrypted = encrypt_secret(plaintext)
    assert encrypted != plaintext
    assert is_encrypted(encrypted)
    assert decrypt_secret(encrypted) == plaintext


def test_empty_and_none_pass_through_unchanged(monkeypatch):
    _fresh_key(monkeypatch)
    assert encrypt_secret("") == ""
    assert encrypt_secret(None) is None
    assert decrypt_secret("") == ""


def test_legacy_plaintext_decrypts_transparently(monkeypatch):
    _fresh_key(monkeypatch)
    legacy = "old-password-saved-before-encryption-existed"
    assert decrypt_secret(legacy) == legacy


def test_double_encryption_is_prevented(monkeypatch):
    _fresh_key(monkeypatch)
    once = encrypt_secret("secret123")
    twice = encrypt_secret(once)
    assert once == twice
    assert decrypt_secret(twice) == "secret123"


def test_wrong_key_fails_loudly(monkeypatch):
    _fresh_key(monkeypatch)
    encrypted = encrypt_secret("secret123")

    monkeypatch.setattr(config.settings, "encryption_key", Fernet.generate_key().decode())
    try:
        decrypt_secret(encrypted)
        assert False, "should have raised"
    except RuntimeError:
        pass


def test_institution_password_never_stored_in_plaintext(monkeypatch, isolated_db):
    _fresh_key(monkeypatch)
    from auth.license_service import create_institution, get_conn

    inst = create_institution(
        name="Secure Test Hosp", client_prefix="SEC", db_name="SecDB",
        db_password="RealPassword#123",
    )

    conn = get_conn()
    row = conn.execute("SELECT db_password FROM institutions WHERE id = ?", (inst["id"],)).fetchone()
    conn.close()

    assert "RealPassword#123" not in row["db_password"]
    assert row["db_password"].startswith("enc::")
    assert "db_password" not in inst  # never returned to the caller either


def test_validate_license_decrypts_password_for_real_use(monkeypatch, isolated_db):
    _fresh_key(monkeypatch)
    from auth.license_service import create_institution, create_license, validate_license

    inst = create_institution(
        name="Secure Test Hosp 2", client_prefix="SEC2", db_name="SecDB2",
        db_password="RealPassword#456",
    )
    lic = create_license(institution_id=inst["id"], role="admin", phone="9999999999", dob_year="1990")

    result = validate_license(lic["code"])
    assert result["db_password"] == "RealPassword#456"


def test_blank_smtp_password_on_update_does_not_wipe_existing(monkeypatch, isolated_db):
    _fresh_key(monkeypatch)
    from auth.license_service import update_settings, get_settings

    update_settings(smtp_host="smtp.gmail.com", smtp_password="MyRealAppPassword")
    assert get_settings()["smtp_password"] == "MyRealAppPassword"

    update_settings(smtp_host="smtp.gmail.com", smtp_password="")
    assert get_settings()["smtp_password"] == "MyRealAppPassword"