"""
Proves the role-based table access control works end-to-end against the
real KonnectLIS test database — without going through the LLM (the agent's
prompt doesn't know this real schema yet, that's separate follow-up work).

This calls agent.tools.run_sql_query directly with hand-written SQL and a
few different roles, and checks whether ALLOW/DENY matches what
auth/roles.py + auth/table_access.py say it should.

Run:
    python test_role_access.py
"""

from agent.tools import run_sql_query

# (role, sql, expected_allowed, note)
CASES = [
    (
        "viewer",
        "SELECT TOP 5 * FROM trnPurchaseOrder",
        False,
        "viewer's allowed categories are patients/admissions only — inventory should be denied",
    ),
    (
        "admin",
        "SELECT TOP 5 * FROM trnPurchaseOrder",
        True,
        "admin has every category including inventory — should be allowed",
    ),
    (
        "reception",
        "SELECT TOP 5 * FROM mstMethod",
        False,
        "reception doesn't have labs — should be denied",
    ),
    (
        "doctor",
        "SELECT TOP 5 * FROM mstMethod",
        True,
        "doctor has labs — should be allowed",
    ),
    (
        "admin",
        "SELECT TOP 5 * FROM mstRoles",
        False,
        "mstRoles isn't in REAL_TABLE_TO_CATEGORY yet — should be denied even for admin (default-deny for unmapped tables)",
    ),
]


def main():
    print(f"{'ROLE':<10} {'EXPECTED':<10} {'RESULT':<10} NOTE")
    print("-" * 90)

    all_passed = True

    for role, sql, expected_allowed, note in CASES:
        result = run_sql_query.invoke({"query": sql, "role": role, "db_name": None})

        is_denied = result.startswith("Access denied") or result.startswith("Access Denied")
        actually_allowed = not is_denied

        passed = actually_allowed == expected_allowed
        all_passed = all_passed and passed

        status = "PASS" if passed else "FAIL"
        expected_str = "ALLOW" if expected_allowed else "DENY"
        actual_str = "ALLOW" if actually_allowed else "DENY"

        print(f"{role:<10} {expected_str:<10} {actual_str:<10} [{status}] {note}")
        if not passed or is_denied:
            print(f"           -> {result[:200]}")

    print("\n" + ("ALL PASSED" if all_passed else "SOME FAILED — see above"))


if __name__ == "__main__":
    main()