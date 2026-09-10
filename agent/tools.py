from langchain_core.tools import tool
import re
import threading
from database.connection import get_hospital_connection
from auth.roles import Role
from auth.table_access import check_query_access, check_table_access
from auth.table_relationships import get_relationships_for_table
import threading
# Per-request schema cache: {table_name: {real column names}}, populated
# by describe_table and reused by run_sql_query's validator so it
# doesn't redundantly re-query INFORMATION_SCHEMA for a table this same
# conversation just looked up seconds ago.
#
# Tried two other approaches first, both proven broken by direct testing
# before this shipped:
#   1. A plain dict tool argument — LangChain's tool .invoke() (the real
#      path the LLM tool-calling loop uses) re-serializes arguments
#      through a Pydantic schema, which does not preserve a mutable
#      dict reference back to the caller. Mutations inside the tool
#      never became visible outside it.
#   2. A contextvars.ContextVar — reads worked, but a .set() call made
#      INSIDE one .invoke() call didn't propagate back out to a
#      subsequent .invoke() call either (consistent with LangChain
#      running each invocation via a copied context internally).
# threading.local() was tested directly and confirmed to work: writes
# made inside one tool's .invoke() ARE visible to a later tool's
# .invoke() call, as long as both run on the same thread — true here,
# confirmed directly, since .invoke() doesn't switch threads.
_local = threading.local()


def get_request_schema_cache() -> dict:
    """Returns the current thread's schema cache, creating a fresh one
    if none exists yet. Call reset_request_schema_cache() at the start
    of each new request/conversation to avoid a later request on the
    same worker thread seeing a stale cache from an earlier one."""
    if not hasattr(_local, "schema_cache"):
        _local.schema_cache = {}
    return _local.schema_cache


def reset_request_schema_cache() -> None:
    """Call this once at the start of handling each new user request —
    ask_agent does this — so this thread's cache doesn't leak stale
    entries into an unrelated later request that happens to reuse the
    same worker thread (a real risk: web frameworks commonly run
    requests on a thread pool, reusing threads across different,
    unrelated requests)."""
    _local.schema_cache = {}


@tool
def describe_table(
    table_name: str,
    role: str = "viewer",
    db_name: str = None,
    db_server: str = None,
    db_user: str = None,
    db_password: str = None,
) -> str:
    """
    Look up the real column names and data types for a specific hospital
    database table. Call this BEFORE writing a SELECT query for a table
    you haven't queried yet in this conversation — do not guess column
    names, they will not match a demo/generic schema.
    """
    try:
        role_enum = Role(role)
    except ValueError:
        return f"Error: unknown role '{role}'."

    allowed, result = check_table_access(role_enum, table_name)
    if not allowed:
        return result
    clean_table_name = result

    conn = get_hospital_connection(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: Could not connect to the hospital database."

    try:
        query = (
            "SELECT COLUMN_NAME, DATA_TYPE "
            "FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE LOWER(TABLE_NAME) = ? "
            "ORDER BY ORDINAL_POSITION"
        )
        cursor = conn.cursor()
        cursor.execute(query, (clean_table_name,))
        rows = cursor.fetchall()

        if not rows:
            return f"No columns found for table '{clean_table_name}' — check the table name."

        # Share the real columns with run_sql_query's validator, so it
        # doesn't need to re-query INFORMATION_SCHEMA for a table this
        # same conversation already looked up seconds ago — that
        # redundant round-trip was a real, measurable latency cost on
        # every single run_sql_query call.
        get_request_schema_cache()[clean_table_name] = {col.lower() for col, _ in rows}

        lines = [f"Columns for {clean_table_name}:"]
        for col_name, data_type in rows:
            lines.append(f"• {col_name} ({data_type})")

        relationships = get_relationships_for_table(clean_table_name)
        if relationships:
            lines.append("\nKnown joins:")
            for col, to_table, to_col in relationships:
                lines.append(f"• {clean_table_name}.{col} = {to_table}.{to_col}")

        return "\n".join(lines)

    except Exception as e:
        return f"Failed to describe table: {str(e)}"
    finally:
        try:
            conn.close()
        except Exception:
            pass

def _validate_sql_columns(cursor, query: str) -> tuple[bool, str]:
    """
    Validate table-qualified column references against the real MSSQL schema.

    This intentionally validates the references that can be resolved
    unambiguously. If a table/alias cannot be resolved safely, the query
    is rejected instead of guessing.

    Uses the per-request schema cache (see get_request_schema_cache) —
    populated by describe_table earlier in this same request — checked
    FIRST for each table, only falling back to a real database
    round-trip if a table isn't already cached. This matters: this
    validator used to always hit the database once per referenced
    table, on every single call, even when describe_table had just
    fetched the exact same columns seconds earlier in the same
    conversation — a real, measurable, avoidable latency cost.
    """
    schema_cache = get_request_schema_cache()

    table_pattern = re.compile(
        r"\b(?:FROM|JOIN)\s+"
        r"(?:(?:\[[^\]]+\]|[A-Za-z_][A-Za-z0-9_]*)\.)*"
        r"(?:\[([^\]]+)\]|([A-Za-z_][A-Za-z0-9_]*))"
        r"(?:\s+(?:AS\s+)?([A-Za-z_][A-Za-z0-9_]*))?",
        re.IGNORECASE,
    )

    table_matches = table_pattern.findall(query)

    if not table_matches:
        return True, ""

    table_info = {}
    aliases = {}

    for bracketed_name, plain_name, alias in table_matches:
        table_name = bracketed_name or plain_name
        clean_table = table_name.strip("[]").lower()

        if clean_table in schema_cache:
            columns = schema_cache[clean_table]
        else:
            cursor.execute(
                """
                SELECT COLUMN_NAME
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE LOWER(TABLE_NAME) = ?
                """,
                (clean_table,),
            )

            columns = {
                row[0].lower()
                for row in cursor.fetchall()
            }
            # Populate the cache so a second reference to the same
            # table later in this SAME query (or a retry) doesn't
            # trigger yet another round-trip either.
            schema_cache[clean_table] = columns

        if not columns:
            return (
                False,
                f"Could not verify schema for table '{clean_table}'. "
                "Query rejected rather than guessing."
            )

        table_info[clean_table] = columns

        aliases[clean_table] = clean_table

        if alias:
            aliases[alias.lower()] = clean_table

    # ---------------------------------------------------------
    # Validate qualified references:
    #
    # t.CREATEDATE
    # trninvlabdet.BILLDATE
    # ---------------------------------------------------------
    qualified_refs = re.findall(
        r"\b([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\b",
        query,
    )

    invalid = []

    for qualifier, column in qualified_refs:
        qualifier_lower = qualifier.lower()
        column_lower = column.lower()

        table = aliases.get(qualifier_lower)

        # Could be dbo.Table, database.Table, etc.
        # Those are not column references.
        if not table:
            continue

        if column_lower not in table_info[table]:
            valid_columns = ", ".join(
                sorted(table_info[table])
            )

            invalid.append(
                f"{qualifier}.{column} "
                f"(valid columns: {valid_columns})"
            )

    if invalid:
        return (
            False,
            "INVALID COLUMN REFERENCE(S): "
            + "; ".join(invalid)
            + ". Do NOT retry the same SQL. "
              "Use the verified schema and regenerate the query."
        )

    return True, ""
@tool
def run_sql_query(
    query: str,
    role: str = "viewer",
    db_name: str = None,
    db_server: str = None,
    db_user: str = None,
    db_password: str = None,
) -> str:
    """
    Execute a SELECT SQL query on the real hospital MSSQL database.
    Only SELECT queries are allowed. Access is restricted based on user role.
    """
    query = query.strip()

    print(f"[run_sql_query] role={role} db={db_name}\nSQL: {query}")

    if not query.lower().startswith("select"):
        return "Error: Only SELECT queries are allowed."

    banned = [" insert ", " update ", " delete ", " drop ", " alter ", " truncate ", " exec ", " merge ", " xp_"]
    qpad = f" {query.lower()} "
    if any(b in qpad for b in banned):
        return "Error: Only read-only SELECT is allowed."
    bad_date_eq = re.search(
    r"\b(BILLDATE|DATEOFBILL|REGDATE|CREATEDATE)\s*=\s*(CONVERT\s*\(\s*date|CAST\s*\(\s*GETDATE|DATEADD\s*\(|')",
    query,
    re.IGNORECASE,
    )
    if bad_date_eq:
        return (
            "Query rejected: do not filter datetime columns with '='. "
            "Use range: col >= DATEADD(DAY, -1, CAST(GETDATE() AS DATE)) "
            "AND col < CAST(GETDATE() AS DATE) for yesterday."
        )

    try:
        role_enum = Role(role)
    except ValueError:
        return f"Error: unknown role '{role}'."

    allowed, reason = check_query_access(role_enum, query)
    if not allowed:
        return reason

    conn = get_hospital_connection(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: Could not connect to the hospital database."

    try:
        cursor = conn.cursor()

        # Validate referenced columns against the REAL MSSQL schema
        # before executing the generated SQL. Reuses the per-request
        # schema cache (populated by describe_table earlier this
        # request) instead of always re-querying INFORMATION_SCHEMA.
        valid, validation_error = _validate_sql_columns(cursor, query)

        if not valid:
            print(f"[run_sql_query] SCHEMA VALIDATION FAILED: {validation_error}")
            return f"Query rejected before execution: {validation_error}"

        cursor.execute(query)

        if not cursor.description:
            print("[run_sql_query] returned 0 row(s)")
            return "No data found for this query."

        columns = [c[0] for c in cursor.description]
        rows = cursor.fetchmany(50)

        print(f"[run_sql_query] returned {len(rows)} row(s)")

        if not rows:
            return "No data found for this query."

        lines = []
        for row in rows:
            item = [f"{columns[i]}: {row[i]}" for i in range(len(columns))]
            lines.append("• " + " | ".join(item))

        return "\n".join(lines)

    except Exception as e:
        print(f"[run_sql_query] FAILED: {e}")
        return f"Query failed: {str(e)}"
    finally:
        try:
            conn.close()
        except Exception:
            pass

@tool
def get_department_dashboard(
    department: str,
    period: str,
    location: str = None,
    role: str = "viewer",
    db_name: str = None,
    db_server: str = None,
    db_user: str = None,
    db_password: str = None,
) -> str:
    """
    Fixed lab/radiology dashboard. Use this INSTEAD of writing SQL for
    questions like "yesterday's radiology dashboard" or "lab dashboard today".

    department: "radiology" | "laboratory" | "all" | a specific sub-department(haematology, biochemistry, microbiology, etc.)
    period: "yesterday" | "today" | "this_month | "this_year" | "any_year" | "any_date"
    """
    department = (department or "all").strip().lower()
    period = (period or "yesterday").strip().lower()

    SUB_DEPARTMENTS = [
        "haematology", "hematology", "biochemistry", "microbiology",
        "histopathology", "cytology", "cytogenetics", "endoscopy",
        "serology", "hormones", "pathology", "cardiology",
    ]
    if department not in ("radiology", "laboratory", "all") and department not in SUB_DEPARTMENTS:
        return "Error: unknown department."

    # Date range (half-open) — never BILLDATE = date

    if period == "today":
        date_sql = (
            "BILLDATE >= CAST(GETDATE() AS DATE) "
            "AND BILLDATE < DATEADD(DAY, 1, CAST(GETDATE() AS DATE))"
        )
        period_label = "Today"

    elif period == "yesterday":
        date_sql = (
            "BILLDATE >= CAST(DATEADD(DAY, -1, GETDATE()) AS DATE) "
            "AND BILLDATE < CAST(GETDATE() AS DATE)"
        )
        period_label = "Yesterday"

    elif period == "this_week":
        # week starting Monday
        date_sql = (
            "BILLDATE >= DATEADD(DAY, 1-DATEPART(WEEKDAY, GETDATE()), CAST(GETDATE() AS DATE)) "
            "AND BILLDATE < DATEADD(DAY, 1, CAST(GETDATE() AS DATE))"
        )
        period_label = "This Week"

    elif period == "last_week":
        date_sql = (
            "BILLDATE >= DATEADD(DAY, 1-DATEPART(WEEKDAY, GETDATE())-7, CAST(GETDATE() AS DATE)) "
            "AND BILLDATE < DATEADD(DAY, 1-DATEPART(WEEKDAY, GETDATE()), CAST(GETDATE() AS DATE))"
        )
        period_label = "Last Week"

    elif period == "this_month":
        date_sql = (
            "BILLDATE >= DATEADD(MONTH, DATEDIFF(MONTH, 0, GETDATE()), 0) "
            "AND BILLDATE < DATEADD(MONTH, DATEDIFF(MONTH, 0, GETDATE()) + 1, 0)"
        )
        period_label = "This Month"

    elif period == "last_month":
        date_sql = (
            "BILLDATE >= DATEADD(MONTH, DATEDIFF(MONTH, 0, GETDATE()) - 1, 0) "
            "AND BILLDATE < DATEADD(MONTH, DATEDIFF(MONTH, 0, GETDATE()), 0)"
        )
        period_label = "Last Month"


    elif period == "this_year":
        date_sql = (
            "BILLDATE >= DATEADD(YEAR, DATEDIFF(YEAR, 0, GETDATE()), 0) "
            "AND BILLDATE < DATEADD(YEAR, DATEDIFF(YEAR, 0, GETDATE()) + 1, 0)"
        )
        period_label = "This Year"

    elif period == "last_year":
        date_sql = (
            "BILLDATE >= DATEADD(YEAR, DATEDIFF(YEAR, 0, GETDATE()) - 1, 0) "
            "AND BILLDATE < DATEADD(YEAR, DATEDIFF(YEAR, 0, GETDATE()), 0)"
        )
        period_label = "Last Year"

    elif period.startswith("last_") and period.endswith("_days"):
        n = int(period.split("_")[1])
        date_sql = (
            f"BILLDATE >= CAST(DATEADD(DAY, -{n}, GETDATE()) AS DATE) "
            f"AND BILLDATE < DATEADD(DAY, 1, CAST(GETDATE() AS DATE))"
        )
        period_label = f"Last {n} Days"

    elif period.startswith("day:"):
        d = period.split(":", 1)[1]
        date_sql = (
            f"BILLDATE >= '{d}' AND BILLDATE < DATEADD(DAY, 1, CAST('{d}' AS DATE))"
        )
        period_label = d

    elif period.startswith("year:"):
        year = period.split(":", 1)[1]
        date_sql = (
            f"BILLDATE >= '{year}-01-01' "
            f"AND BILLDATE < '{int(year)+1}-01-01'"
        )
        period_label = year
    elif period.startswith("month:"):
        ym = period.split(":", 1)[1]  # "2026-07"
        y, m = ym.split("-")
        date_sql = (
            f"BILLDATE >= '{ym}-01' "
            f"AND BILLDATE < DATEADD(MONTH, 1, '{ym}-01')"
        )
        period_label = ym

    else:
        return f"Error: unsupported period '{period}'."

    # Dept filter
    # laboratory / all → no DEPTCODE filter (trninvlabdet is lab work; "Laboratory" name often missing)
    # radiology → resolve via mstdepartment
    if department == "radiology":
        dept_sql = (
            "AND DEPTCODE IN ("
            "SELECT SubDepartmentID FROM mstsubdepartment "
            "WHERE SubDeptName LIKE '%Radiology%'"
            ")"
        )
        title = "Radiology Dashboard"
        icon = "🩻"
    elif department == "laboratory":
        dept_sql = ""
        title = "Laboratory Dashboard"
        icon = "🧪"
    elif department in SUB_DEPARTMENTS:
        dept_sql = (
            f"AND DEPTCODE IN ("
            f"SELECT SubDepartmentID FROM mstsubdepartment "
            f"WHERE SubDeptName LIKE '%{department}%'"
            f")"
        )
        title = f"{department.title()} Dashboard"
        icon = "🧫"
    else:
        dept_sql = ""
        title = "Lab Operations Dashboard"
        icon = "📊"

    if department == "radiology":
        completed_join = (
            "LEFT JOIN (SELECT DISTINCT BILLNO FROM trninvstatus "
            "WHERE STATUS = 'Authenticated') auth "
            "ON auth.BILLNO = trninvlabdet.BILLNO"
        )
        completed_select = "COUNT(DISTINCT auth.BILLNO) AS COMPLETED,"
    else:
        completed_join = ""
        completed_select = (
            "SUM(CASE WHEN TESTSTATUS IN ('Result Entry', 'Acknowledged') "
            "THEN 1 ELSE 0 END) AS COMPLETED,"
        )

    location_sql = ""
    if location:
        from reports.curated_queries import resolve_location_id
        loc_id, loc_matched = resolve_location_id(location, db_name, db_server, db_user, db_password)
        if loc_id is None:
            return f"No location found matching '{location}'."
        if loc_id == "AMBIGUOUS":
            return f"Multiple locations match '{location}': {', '.join(loc_matched)}. Ask which one they mean."
        location_sql = f"AND LOCATIONID = '{loc_id}'"
        title = f"{title} · {loc_matched}"

    sql = f"""
SELECT
    COUNT(*) AS PROCEDURES,
    {completed_select}
    SUM(CASE WHEN TESTSTATUS = 'Pending' THEN 1 ELSE 0 END) AS PENDING
FROM trninvlabdet
{completed_join}
WHERE {date_sql}
{dept_sql}
{location_sql}
""".strip()

    try:
        role_enum = Role(role)
    except ValueError:
        return f"Error: unknown role '{role}'."

    allowed, reason = check_query_access(role_enum, sql)
    if not allowed:
        return reason

    conn = get_hospital_connection(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: Could not connect to the hospital database."

    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        row = cursor.fetchone()
        if not row:
            return f"No data found for {title} · {period_label}."

        procedures = int(row[0] or 0)
        completed = int(row[1] or 0)
        pending = int(row[2] or 0)

        if procedures == 0:
            return f"No procedures found for {title} · {period_label} (filter returned 0 rows)."

        import json
        card = {
            "icon": icon,
            "title": title,
            "subtitle": period_label,
            "stats": [
                {"label": "PROCEDURES", "value": f"{procedures:,}"},
                {"label": "COMPLETED", "value": f"{completed:,}"},
                {"label": "PENDING", "value": f"{pending:,}"},
            ],
        }
        return "```dashboard-card\n" + json.dumps(card) + "\n```"
    except Exception as e:
        print(f"[get_department_dashboard] FAILED: {e}")
        return f"Dashboard query failed: {e}"
    finally:
        try:
            conn.close()
        except Exception:
            pass
@tool
def get_verified_day_collection(
    location_keyword: str,
    date_from: str,
    date_to: str,
    role: str = "viewer",
    db_name: str = None,
    db_server: str = None,
    db_user: str = None,
    db_password: str = None,
) -> str:
    """
    Day collection for ONE SPECIFIC location and date range, using a
    FIXED, hand-verified query — not one you write yourself. Use this
    INSTEAD of run_sql_query when the question names one specific
    location — it's guaranteed correct where a freshly-written query
    has repeatedly guessed wrong column/value names for this pattern.

    DO NOT use this tool for "all branches"/"all locations"/a combined
    total across every location — it always requires ONE specific
    location_keyword. A real bug: passing "all" as the keyword matched
    multiple real locations that coincidentally contain "all" as a
    substring (Kompally, Kukatpally, etc.) — a confusing false
    positive. For an ALL-LOCATIONS-COMBINED question, use
    describe_table/run_sql_query instead with no location filter.

    date_from and date_to: pass a real 'YYYY-MM-DD' string, OR pass the
    literal word "today", "yesterday", "this_month_start", or
    "this_year_start" and let the tool resolve it. DO NOT compute the
    actual calendar date yourself for these — your own sense of "today's
    date" is not reliable for this and has caused real wrong answers
    (a date years in the past) in production. Just pass the word "today"
    or "yesterday" literally as the string value.
    location_keyword: the distinctive part of ONE specific location's
    name from the question (e.g. "Kompally") — partial match, don't
    need the exact full stored name.
    """
    from reports.curated_queries import get_day_collection

    if role not in ("admin", "doctor", "reception"):
        # Same billing-category gate as the rest of the system —
        # this tool bypasses check_query_access's SQL text parsing
        # (there's no SQL text to parse, it's fixed), so the role
        # check has to happen explicitly here instead.
        return "Error: your role does not have access to billing/collection data."

    result = get_day_collection(location_keyword, date_from, date_to, db_name, db_server, db_user, db_password)

    if "error" in result:
        return f"Error: {result['error']}"

    if result.get("ambiguous"):
        candidates = ", ".join(result["candidates"])
        return (
            f"Multiple locations match '{location_keyword}': {candidates}. "
            "Ask the user which one they mean rather than guessing."
        )

    if result.get("no_data"):
        return (
            f"No collection records found for {result['location']} between "
            f"{result['date_from']} and {result['date_to']}. This is a real "
            f"query result (not a guessed wrong column), so this is either "
            f"genuinely no activity in that window, or a data lag — say so "
            f"plainly, don't invent a reason."
        )

    lines = [f"Location: {result['location']} | {result['date_from']} to {result['date_to']}"]
    lines.append(f"Total: {result['total']}")
    for b in result["breakdown"]:
        lines.append(f"  {b['mode']}: {b['amount']}")
    if result.get("had_null_amounts"):
        lines.append(
            "NOTE: some matching transaction(s) had a NULL PAIDAMOUNT, not a real 0 — "
            "this means transactions/bills exist for this location and date range, but "
            "the payment amount itself wasn't recorded as a number. Mention this "
            "distinction to the user rather than just saying the total was zero — "
            "e.g. 'records exist but payment amounts weren't recorded' is more accurate "
            "than 'no activity'."
        )
    return "\n".join(lines)


@tool
def search_schema(query: str, role: str = "viewer") -> str:
    """
    Search the hospital database schema for tables relevant to the
    user's question, using real table categories, real column names,
    and real sample values — not guessing from cryptic table names
    alone (e.g. trninvlabdet, mstdepartment). Call this FIRST whenever
    you're not already certain which table(s) are relevant, before
    describe_table. This is plain search, not another AI step — it
    won't invent anything, just rank real known tables by relevance.
    """
    from agent.schema_search import search_schema as _search
    from auth.roles import Role
    from auth.table_access import list_allowed_tables_for_role

    try:
        role_enum = Role(role)
    except ValueError:
        return f"Error: unknown role '{role}'."

    allowed = set(list_allowed_tables_for_role(role_enum))
    results = _search(query, allowed_tables=allowed)

    if not results:
        return (
            f"No tables matched '{query}' by name, category, or known column/value content. "
            "This doesn't mean no data exists — it may just mean this table hasn't been "
            "profiled yet (see profile_schema.py), or genuinely isn't in the allowed set for "
            "this role. Try describe_table on a table you already suspect, or say plainly that "
            "you couldn't find a clearly relevant table."
        )

    lines = [f"Tables relevant to '{query}', ranked by relevance:"]
    for r in results:
        lines.append(f"• {r['table']} (score {r['score']}) — {r['why']}")
    return "\n".join(lines)

@tool
def get_lab_day_collection(
    location_keyword: str,
    bill_date: str,
    date_to: str = None,
    role: str = "viewer",
    db_name: str = None,
    db_server: str = None,
    db_user: str = None,
    db_password: str = None,
) -> str:
    """
    Real, authoritative cash/concession/due/refund reconciliation for
    ONE location and ONE date — calls dbo.LabDayCollection directly
    (the actual stored procedure AthenTech's own report screens use),
    not a reconstruction from raw tables. Use this INSTEAD of writing
    SQL for any "Cash In Hand"/detailed reconciliation/day collection
    breakdown question — reconstructing this from raw tables has
    repeatedly produced wrong numbers; this calls the real source.

    location_keyword: a location NAME (e.g. "Jagtial", "Kompally") —
    resolved to its real LOC0X code automatically via mstlocation, the
    confirmed dedicated location master table. Partial match is fine.
    bill_date: 'YYYY-MM-DD' — a real date, not "today"/"yesterday".
    """
    from reports.curated_queries import resolve_location_id
    from reports.lab_day_collection import call_lab_day_collection

    if role not in ("admin", "doctor", "reception"):
        return "Error: your role does not have access to billing/collection data."

    location_id, matched = resolve_location_id(location_keyword, db_name, db_server, db_user, db_password)
    if location_id is None:
        return f"Error: no location found matching '{location_keyword}'."
    if location_id == "AMBIGUOUS":
        return f"Multiple locations match '{location_keyword}': {', '.join(matched)}. Ask which one they mean."

    if date_to and date_to != bill_date:
        from reports.lab_day_collection import call_lab_day_collection_range
        result = call_lab_day_collection_range(location_id, bill_date, date_to, db_name, db_server, db_user, db_password)
        if "error" in result:
            return f"Error: {result['error']}"
        lines = [f"Real reconciliation totals for {matched} ({location_id}), {bill_date} to {date_to} "
                 f"({result['days_with_data']}/{result['days_checked']} days had activity):"]
        for label, total in result["totals"].items():
            if total:
                lines.append(f"  {label}: {total:,.2f}")
        return "\n".join(lines)

    result = call_lab_day_collection(location_id, bill_date, db_name, db_server, db_user, db_password)
    if "error" in result:
        return f"Error: {result['error']}"
    lines = [f"Real reconciliation figures for {matched} ({location_id}) on {bill_date} (from dbo.LabDayCollection):"]
    for label, row in result["labeled_results"].items():
        if row:
            lines.append(f"  {label}: {row}")
    return "\n".join(lines)