"""
Discovers likely JOIN relationships between your mapped tables (the
ones in REAL_TABLE_TO_CATEGORY) using two signal sources:

1. Real foreign key constraints, if your DB declares any (many legacy
   schemas don't enforce these even when the relationship is real).
2. Naming-convention matching: a column like "PatientID" in one table
   very likely joins to the primary-key-like column of a table about
   patients — this is standard practice in exactly this kind of legacy
   schema, and needs no LLM call, just string matching against real
   column metadata.

This does NOT modify anything live. It writes a review file — a human
decides what's real before it's ever used to guide the agent's SQL.

Usage:
    python discover_table_relationships.py
    (uses your .env MSSQL_* settings)

Output:
    table_relationships_review.csv
"""

import csv
import re

from database.connection import get_hospital_connection
from auth.table_access import REAL_TABLE_TO_CATEGORY

MAPPED_TABLES = set(REAL_TABLE_TO_CATEGORY.keys())


def get_real_foreign_keys(conn) -> list:
    """Actual declared FK constraints, if any exist."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            fk_tab.name AS from_table,
            fk_col.name AS from_column,
            pk_tab.name AS to_table,
            pk_col.name AS to_column
        FROM sys.foreign_keys fk
        JOIN sys.foreign_key_columns fkc ON fkc.constraint_object_id = fk.object_id
        JOIN sys.tables fk_tab ON fk_tab.object_id = fkc.parent_object_id
        JOIN sys.columns fk_col ON fk_col.object_id = fkc.parent_object_id AND fk_col.column_id = fkc.parent_column_id
        JOIN sys.tables pk_tab ON pk_tab.object_id = fkc.referenced_object_id
        JOIN sys.columns pk_col ON pk_col.object_id = fkc.referenced_object_id AND pk_col.column_id = fkc.referenced_column_id
    """)
    return [
        {"from_table": r[0], "from_column": r[1], "to_table": r[2], "to_column": r[3], "source": "real_fk", "confidence": "high"}
        for r in cursor.fetchall()
    ]


def get_columns_for_tables(conn, table_names: list) -> dict:
    """{table_name_lower: [column_names]} for the given tables."""
    result = {}
    for table_name in table_names:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_NAME = ? ORDER BY ORDINAL_POSITION",
            (table_name,)
        )
        cols = [row[0] for row in cursor.fetchall()]
        if cols:
            result[table_name.lower()] = cols
    return result


_ID_SUFFIX_RE = re.compile(r"^(.*?)(id)$", re.IGNORECASE)


def _pk_like_columns(columns: list) -> list:
    """Columns on a table that look like its own primary key."""
    return [c for c in columns if c.lower() in ("id", "pk", "recid") or
            (c.lower().endswith("id") and len(c) <= 6)]


def find_heuristic_relationships(columns_by_table: dict) -> list:
    """
    For every column ending in 'ID' (e.g. PatientID), check if the
    prefix ('Patient') matches another table's name or category —
    that's a strong signal of an intended join, even with no real FK
    constraint declared.
    """
    candidates = []
    table_names = list(columns_by_table.keys())

    for from_table, columns in columns_by_table.items():
        for col in columns:
            m = _ID_SUFFIX_RE.match(col)
            if not m:
                continue
            prefix = m.group(1).lower().strip("_")
            if not prefix or len(prefix) < 3:
                continue  # too short to mean anything ("ID" alone, etc.)

            for to_table in table_names:
                if to_table == from_table:
                    continue
                # Table name contains the prefix (e.g. "patient" in "mstpatientregistration")
                if prefix in to_table:
                    pk_cols = _pk_like_columns(columns_by_table[to_table])
                    to_col = pk_cols[0] if pk_cols else "ID"
                    candidates.append({
                        "from_table": from_table, "from_column": col,
                        "to_table": to_table, "to_column": to_col,
                        "source": "heuristic_name_match", "confidence": "medium",
                    })

    return candidates


def run():
    conn = get_hospital_connection()
    if not conn:
        print("Could not connect to the database. Check your .env MSSQL_* settings.")
        return

    print("Checking for real foreign key constraints...")
    real_fks = get_real_foreign_keys(conn)
    print(f"Found {len(real_fks)} real FK constraints.\n")

    print(f"Fetching columns for {len(MAPPED_TABLES)} mapped tables...")
    columns_by_table = get_columns_for_tables(conn, list(MAPPED_TABLES))
    conn.close()
    print(f"Got columns for {len(columns_by_table)} tables.\n")

    print("Finding naming-convention matches...")
    heuristic = find_heuristic_relationships(columns_by_table)
    print(f"Found {len(heuristic)} heuristic candidates.\n")

    # Real FKs win over heuristic guesses for the same from_table/from_column pair.
    real_pairs = {(r["from_table"].lower(), r["from_column"].lower()) for r in real_fks}
    heuristic = [h for h in heuristic if (h["from_table"], h["from_column"].lower()) not in real_pairs]

    all_results = real_fks + heuristic
    all_results.sort(key=lambda r: (r["confidence"] != "high", r["from_table"], r["from_column"]))

    with open("table_relationships_review.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["from_table", "from_column", "to_table", "to_column", "source", "confidence"])
        writer.writeheader()
        writer.writerows(all_results)

    print(f"Wrote {len(all_results)} candidate relationships to table_relationships_review.csv")
    print(f"  {len(real_fks)} from real FK constraints (high confidence)")
    print(f"  {len(heuristic)} from naming-convention matching (review these)")


if __name__ == "__main__":
    run()