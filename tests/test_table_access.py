from auth.table_access import extract_tables, check_query_access, check_table_access, list_allowed_tables_for_role
from auth.roles import Role


def test_extract_tables_finds_simple_table():
    assert extract_tables("SELECT * FROM patients WHERE age > 50") == {"patients"}


def test_extract_tables_strips_schema_and_brackets():
    sql = "SELECT p.name FROM [dbo].[MstPatientRegistration] p JOIN admissions a ON p.id=a.pid"
    assert extract_tables(sql) == {"admissions", "mstpatientregistration"}


def test_extract_tables_does_not_false_positive_on_column_names():
    # 'pharmacy_notes' is a column, not a table — must not be misidentified as the 'pharmacy' table.
    assert extract_tables("SELECT pharmacy_notes FROM patients") == {"patients"}


def test_viewer_can_access_patients():
    allowed, reason = check_query_access(Role.VIEWER, "SELECT * FROM patients")
    assert allowed is True


def test_viewer_cannot_access_unmapped_table():
    allowed, reason = check_query_access(Role.VIEWER, "SELECT * FROM pharmacy")
    assert allowed is False
    assert "not recognized" in reason


def test_default_deny_unmapped_table_blocks_even_admin():
    # A table that isn't in REAL_TABLE_TO_CATEGORY must be denied for
    # every role, including admin — unmapped tables fail closed.
    allowed, reason = check_query_access(Role.ADMIN, "SELECT * FROM mstRoles")
    assert allowed is False


def test_check_table_access_matches_check_query_access():
    allowed, cleaned = check_table_access(Role.DOCTOR, "mstMethod")
    assert allowed is True
    assert cleaned == "mstmethod"

    denied, reason = check_table_access(Role.RECEPTION, "mstMethod")
    assert denied is False


def test_list_allowed_tables_for_role_reflects_role_permissions():
    doctor_tables = list_allowed_tables_for_role(Role.DOCTOR)
    viewer_tables = list_allowed_tables_for_role(Role.VIEWER)
    # doctor has labs, viewer doesn't — doctor's list should be a superset here
    assert "mstmethod" in doctor_tables
    assert "mstmethod" not in viewer_tables
