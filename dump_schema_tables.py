"""
Stage 1 schema discovery: list every table in the database with an
approximate row count, so we can figure out which ones actually matter
(vs. empty/legacy/system tables) before pulling full column details.

Run:
    python dump_schema_tables.py

Uses the same connection settings as your .env (MSSQL_SERVER,
MSSQL_DATABASE, MSSQL_USER, MSSQL_PASSWORD) via config.py, and the same
driver fallback as database/connection.py.

Outputs:
    schema_tables.json   (machine-readable)
    schema_tables.csv     (open in Excel to eyeball / sort by row count)
"""

import csv
import json

from database.connection import get_hospital_connection


def main():
    conn = get_hospital_connection()
    if not conn:
        print("Could not connect. Check your .env MSSQL_* settings.")
        return

    cursor = conn.cursor()

    # All user tables (excludes system tables) with schema name.
    cursor.execute("""
        SELECT s.name AS schema_name, t.name AS table_name
        FROM sys.tables t
        JOIN sys.schemas s ON t.schema_id = s.schema_id
        ORDER BY s.name, t.name
    """)
    tables = cursor.fetchall()
    print(f"Found {len(tables)} tables. Getting row counts (this may take a bit)...\n")

    results = []
    for schema_name, table_name in tables:
        full_name = f"[{schema_name}].[{table_name}]"
        try:
            count_cursor = conn.cursor()
            count_cursor.execute(f"SELECT COUNT(*) FROM {full_name}")
            row_count = count_cursor.fetchone()[0]
        except Exception as e:
            row_count = f"ERROR: {e}"

        results.append({
            "schema": schema_name,
            "table": table_name,
            "row_count": row_count,
        })
        print(f"{full_name:<60} {row_count}")

    with open("schema_tables.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    with open("schema_tables.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["schema", "table", "row_count"])
        writer.writeheader()
        writer.writerows(results)

    conn.close()
    print(f"\nWrote schema_tables.json and schema_tables.csv ({len(results)} tables).")


if __name__ == "__main__":
    main()