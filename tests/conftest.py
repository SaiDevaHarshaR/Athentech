import os
import sys

import pytest

# Make the project root importable regardless of where pytest is invoked from.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("GROQ_API_KEY", "test-key-not-used")
os.environ.setdefault("TAVILY_API_KEY", "test-key-not-used")


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """
    Gives each test its own throwaway licenses.db and audit log in a temp
    directory — tests never touch your real data, and never see each
    other's state.
    """
    monkeypatch.chdir(tmp_path)
    os.makedirs("audit", exist_ok=True)

    from database.license_db import init_license_db, seed_demo_institutions
    init_license_db()
    seed_demo_institutions()

    yield tmp_path


@pytest.fixture
def admin_env(monkeypatch):
    """Sets up a bootstrap admin credential in config.settings for tests that need auth."""
    import hashlib
    from config import settings as app_settings

    monkeypatch.setattr(app_settings, "admin_username", "admin")
    monkeypatch.setattr(app_settings, "admin_password_hash", hashlib.sha256(b"bootpass123").hexdigest())
    monkeypatch.setattr(app_settings, "admin_secret_key", "test-secret-key-for-pytest")
    yield
