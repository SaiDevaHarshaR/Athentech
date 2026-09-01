import pytest

from auth.admin_service import (
    list_admins, create_admin, verify_admin_login, set_admin_status,
    change_admin_password, admin_exists,
)


def test_create_and_login_admin(isolated_db):
    create_admin("priya", "realpassword123", "Priya Sharma")
    assert admin_exists("priya")
    assert verify_admin_login("priya", "realpassword123") is True
    assert verify_admin_login("priya", "wrongpassword") is False


def test_duplicate_username_rejected(isolated_db):
    create_admin("priya", "realpassword123", "Priya Sharma")
    with pytest.raises(ValueError):
        create_admin("priya", "anotherpass123", "Someone Else")


def test_short_password_rejected(isolated_db):
    with pytest.raises(ValueError):
        create_admin("shortpw", "abc", "Short")


def test_deactivated_admin_cannot_login(isolated_db):
    create_admin("priya", "realpassword123", "Priya Sharma")
    set_admin_status("priya", "Inactive")
    assert verify_admin_login("priya", "realpassword123") is False


def test_reactivated_admin_can_login_again(isolated_db):
    create_admin("priya", "realpassword123", "Priya Sharma")
    set_admin_status("priya", "Inactive")
    set_admin_status("priya", "Active")
    assert verify_admin_login("priya", "realpassword123") is True


def test_password_change(isolated_db):
    create_admin("priya", "oldpassword123", "Priya Sharma")
    change_admin_password("priya", "newpassword456")
    assert verify_admin_login("priya", "oldpassword123") is False
    assert verify_admin_login("priya", "newpassword456") is True


def test_last_login_stamped_on_success(isolated_db):
    create_admin("priya", "realpassword123", "Priya Sharma")
    before = [a for a in list_admins() if a["username"] == "priya"][0]
    assert before["last_login_at"] is None

    verify_admin_login("priya", "realpassword123")

    after = [a for a in list_admins() if a["username"] == "priya"][0]
    assert after["last_login_at"] is not None


def test_password_hash_never_exposed_in_list(isolated_db):
    create_admin("priya", "realpassword123", "Priya Sharma")
    for admin in list_admins():
        assert "password_hash" not in admin
