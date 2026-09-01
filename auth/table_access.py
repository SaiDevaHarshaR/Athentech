"""
Real (not no-op) role-based table access control for SQL run by the agent.

Two problems this replaces:
1. The old check did naive substring matching on the raw SQL text, which
   both false-positives (a column named `pharmacy_notes` would trip the
   `pharmacy` table block) and false-negatives (it never actually enforced
   anything for the MSSQL path — the check body was just `pass`).
2. There was no mapping between logical categories ("labs", "pharmacy", ...)
   and the real Sahasra/KonnectLIS physical table names.

Fill in REAL_TABLE_TO_CATEGORY as you learn the actual Sahasra schema.
Any table found in a query that is NOT in this map is denied by default —
safer than silently allowing unknown tables through.
"""

import re
from typing import Set

from auth.roles import Role, get_allowed_tables

# Map: physical table name (lowercase, no schema prefix/brackets) -> logical category.
# Logical categories must match the ones used in auth/roles.py's ROLE_PERMISSIONS
# ("patients", "admissions", "labs", "pharmacy", "wards", "prescriptions",
#  "doctors", "staff", "billing", "inventory").
#
# Populate this as the real Sahasra/KonnectLIS schema is confirmed. Anything
# not listed here is denied by default (see check_query_access below).
#
# IMPORTANT: "KonnectLIS" = Lab Information System. This DB looks like it's
# specifically the lab module, not a full hospital schema — table names
# like mstMethod, mstAntibiotics, mstWorkStations are lab-specific concepts.
# Confirm with AthenTech whether admissions/pharmacy/wards live in a
# separate database before assuming those categories apply here at all.
REAL_TABLE_TO_CATEGORY = {
    # --- demo/SQLite schema ---
    "patients": "patients",
    "admissions": "admissions",

    # --- known real table names, confidence noted ---
    # TODO: confirm all of these against actual Sahasra/KonnectLIS docs or DBA.
    "mstpatientregistration": "patients",       # confident
    "tblclientdocinfo": "patients",             # confident-ish: "client" = patient docs
    "trnmergeddocbilldtls_referral": "billing", # confident-ish: "bill" in the name
    "trnpurchaseorder": "inventory",            # confident: procurement
    "mstlocationusers": "staff",                # confident-ish: users tied to a location

    "trninvoicepayments": "billing",            # confident: payments
    "mstmethod": "labs",                        # confident: lab test methodology
    "mstantibiotics": "labs",                   # likely: used in AST/culture-sensitivity testing
    "mstworkstations": "labs",                  # guess: lab equipment/stations — could also be "inventory"

    # --- ambiguous / likely system config, not patient data ---
    # Left unmapped on purpose (denied by default) until confirmed:
    # "mstappdocuments" — looks like a doc-type reference table, not patient data
    # "mstroles" — looks like application-level roles, not a clinical category
}

_IDENTIFIER = r"\[?[a-zA-Z_][a-zA-Z0-9_]*\]?(?:\.\[?[a-zA-Z_][a-zA-Z0-9_]*\]?)*"
_TABLE_REF_RE = re.compile(
    rf"\b(?:FROM|JOIN)\s+({_IDENTIFIER})",
    re.IGNORECASE,
)


def extract_tables(sql: str) -> Set[str]:
    """
    Pull table identifiers following FROM/JOIN out of a SQL query.
    Strips brackets and schema/db prefixes (e.g. [dbo].[MstPatient] -> mstpatient).
    This is intentionally simple (regex, not a full SQL parser) — good enough
    to gate table-level access, not a substitute for a real SQL parser if the
    query surface grows more complex.
    """
    tables = set()
    for match in _TABLE_REF_RE.finditer(sql):
        raw = match.group(1)
        # Take the last dotted segment (strips schema/db prefixes like dbo. or db.dbo.)
        last_part = raw.split(".")[-1]
        cleaned = last_part.strip("[]").lower()
        if cleaned:
            tables.add(cleaned)
    return tables


def check_table_access(role: Role, table_name: str) -> tuple[bool, str]:
    """
    Same access rule as check_query_access, but for a single bare table
    name rather than a full SQL query — used by the describe_table tool
    so the agent can't fish for column names on tables it can't query.
    """
    cleaned = table_name.strip().strip("[]").lower()
    cleaned = cleaned.split(".")[-1]  # strip schema prefix if given

    category = REAL_TABLE_TO_CATEGORY.get(cleaned)
    if category is None:
        return False, (
            f"Access denied: table '{cleaned}' is not recognized. "
            "Add it to REAL_TABLE_TO_CATEGORY in auth/table_access.py "
            "once its data category is confirmed."
        )
    if category not in get_allowed_tables(role):
        return False, f"Access denied: your role ({role.value}) cannot access '{cleaned}' ({category})."

    return True, cleaned


def list_allowed_tables_for_role(role: Role) -> list:
    """
    Real (physical) table names this role is allowed to touch, based on
    REAL_TABLE_TO_CATEGORY. Used to tell the LLM what actually exists
    for it to query, without dumping the entire schema into the prompt.
    """
    allowed_categories = get_allowed_tables(role)
    return sorted(
        table for table, category in REAL_TABLE_TO_CATEGORY.items()
        if category in allowed_categories
    )


def check_query_access(role: Role, sql: str) -> tuple[bool, str]:
    """
    Returns (allowed, reason). Denies by default if a table can't be
    mapped to a known logical category — better to under-serve than to
    leak a table nobody explicitly allowed.
    """
    allowed_categories = get_allowed_tables(role)
    tables = extract_tables(sql)

    for table in tables:
        category = REAL_TABLE_TO_CATEGORY.get(table)
        if category is None:
            return False, (
                f"Access denied: table '{table}' is not recognized. "
                "Add it to REAL_TABLE_TO_CATEGORY in auth/table_access.py "
                "once its data category is confirmed."
            )
        if category not in allowed_categories:
            return False, f"Access denied: your role ({role.value}) cannot access '{table}' ({category})."

    return True, ""