"""
Profiles real tables directly against the live database: real columns,
row counts, and actual sample/distinct values for columns that look
like codes or IDs — not category guesses, actual observed content.

This is the tool that would have caught today's real bug in one shot:
two tables (trntempdaycollall, trnmodeofcollectionsdet) both had a
column literally named LOCATIONID, in the same 'LOC0X' string format,
and it took hours of trial and error to discover they don't actually
reference the same registry. Profiling both tables' real LOCATIONID
values side by side would have shown zero overlap immediately.

Usage:
    python profile_schema.py trntempdaycollall trnmodeofcollectionsdet mstpatientregistration
    python profile_schema.py --all-mapped          # profiles every table in table_access.py
    python profile_schema.py --all-mapped --limit 50   # cap how many tables (can be slow otherwise)

Output: schema_profile.json (full detail) and schema_profile_summary.csv
(one row per table, quick skim).
"""

import argparse
import csv
import json
import re

from database.connection import get_hospital_connection
from auth.table_access import REAL_TABLE_TO_CATEGORY

# Columns matching this pattern get their real distinct values sampled —
# these are exactly the columns that caused today's bug (looks like a
# reference/code column, but might not mean what you assume).
_CODE_LIKE_COLUMN = re.compile(r"(id|code|mode|type|status|name|desc)$", re.IGNORECASE)

MAX_SAMPLE_VALUES = 15


def get_columns(conn, table_name: str) -> list:
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE LOWER(TABLE_NAME) = ? ORDER BY ORDINAL_POSITION",
        (table_name.lower(),)
    )
    return cursor.fetchall()


def get_row_count(conn, table_name: str) -> int:
    cursor = conn.cursor()
    try:
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        return cursor.fetchone()[0]
    except Exception as e:
        print(f"  [warn] could not count rows for {table_name}: {e}")
        return -1


def get_sample_values(conn, table_name: str, column_name: str) -> list:
    cursor = conn.cursor()
    try:
        cursor.execute(f"SELECT DISTINCT TOP {MAX_SAMPLE_VALUES} {column_name} FROM {table_name}")
        return [str(r[0]) for r in cursor.fetchall() if r[0] is not None]
    except Exception as e:
        return [f"[error sampling: {e}]"]


def profile_table(conn, table_name: str) -> dict:
    print(f"Profiling {table_name}...")
    columns = get_columns(conn, table_name)
    if not columns:
        return {"table": table_name, "error": "no columns found — check the table name"}

    row_count = get_row_count(conn, table_name)

    column_profiles = []
    for col_name, data_type in columns:
        entry = {"column": col_name, "type": data_type}
        if _CODE_LIKE_COLUMN.search(col_name) and row_count > 0:
            entry["sample_values"] = get_sample_values(conn, table_name, col_name)
        column_profiles.append(entry)

    return {
        "table": table_name,
        "category": REAL_TABLE_TO_CATEGORY.get(table_name.lower(), "(not classified)"),
        "row_count": row_count,
        "columns": column_profiles,
    }


def run(tables: list, db_name: str = None, db_server: str = None, db_user: str = None, db_password: str = None):
    conn = get_hospital_connection(db_name, db_server, db_user, db_password)
    if not conn:
        print("Could not connect to the database. Check your .env MSSQL_* settings.")
        return

    profiles = []
    for table in tables:
        try:
            profiles.append(profile_table(conn, table))
        except Exception as e:
            print(f"  [error] {table}: {e}")
            profiles.append({"table": table, "error": str(e)})

    conn.close()

    with open("schema_profile.json", "w", encoding="utf-8") as f:
        json.dump(profiles, f, indent=2, default=str)

    with open("schema_profile_summary.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["table", "category", "row_count", "column_count", "code_like_columns"])
        for p in profiles:
            if "error" in p:
                writer.writerow([p["table"], "ERROR", "-", "-", p["error"]])
                continue
            code_cols = [c["column"] for c in p["columns"] if "sample_values" in c]
            writer.writerow([p["table"], p["category"], p["row_count"], len(p["columns"]), ", ".join(code_cols)])

    print(f"\nWrote schema_profile.json (full detail, including sample values)")
    print(f"Wrote schema_profile_summary.csv (quick skim — open in Excel)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("tables", nargs="*", help="Specific table names to profile")
    parser.add_argument("--all-mapped", action="store_true", help="Profile every table in table_access.py")
    parser.add_argument("--limit", type=int, default=None, help="Cap the number of tables (with --all-mapped)")
    args = parser.parse_args()

    if args.all_mapped:
        table_list = list(REAL_TABLE_TO_CATEGORY.keys())
        if args.limit:
            table_list = table_list[:args.limit]
    else:
        table_list = args.tables

    if not table_list:
        print("Specify table names, or use --all-mapped. Example:")
        print("  python profile_schema.py trntempdaycollall trnmodeofcollectionsdet")
        exit(1)

    run(table_list)