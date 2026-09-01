"""
Scans your hospital DB's full schema and has the LLM suggest a category
for every table (patients / admissions / labs / pharmacy / wards /
prescriptions / doctors / staff / billing / inventory / skip), so
extending auth/table_access.py's REAL_TABLE_TO_CATEGORY to hundreds of
tables is a few minutes of scanning a CSV instead of hand-typing every
entry.

This does NOT modify anything live. It only writes review files — a
human decides what actually gets added to REAL_TABLE_TO_CATEGORY.
Nothing becomes queryable by the agent just by running this script.

Usage:
    python auto_classify_tables.py
    (uses your .env MSSQL_* settings, same as dump_schema_tables.py)

Output:
    table_classification_review.csv    <- scan this (sorted by category)
    table_classification_suggested.py  <- ready-to-paste dict, edit before using

Cost note: this makes one Groq API call per batch of ~25 tables. For
700 tables that's roughly ~30 calls, one-time — cheap compared to
hand-documenting each table.
"""

import csv
import json
import re
import sys

from database.connection import get_hospital_connection
from config import settings

CATEGORIES = [
    "patients", "admissions", "labs", "pharmacy", "wards",
    "prescriptions", "doctors", "staff", "billing", "inventory",
]

BATCH_SIZE = 25

# Heuristics for tables that are almost certainly legacy/backup/system,
# not worth spending an LLM call on. Flagged separately in the CSV as
# "skip (heuristic)" rather than classified.
_LEGACY_PATTERNS = [
    re.compile(r"\d{6,8}"),          # embedded date like 15062022 or 05052023
    re.compile(r"_log$", re.I),
    re.compile(r"_audit$", re.I),
    re.compile(r"_backup$", re.I),
    re.compile(r"bak\d*$", re.I),
    re.compile(r"_old$", re.I),
    re.compile(r"_temp$", re.I),
    re.compile(r"^temp", re.I),
]


def is_likely_legacy(table_name: str) -> bool:
    return any(p.search(table_name) for p in _LEGACY_PATTERNS)


def get_full_schema(conn) -> list:
    """Returns [{"table": ..., "row_count": ..., "columns": [...]}, ...] for every user table."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.name AS schema_name, t.name AS table_name
        FROM sys.tables t
        JOIN sys.schemas s ON t.schema_id = s.schema_id
        ORDER BY s.name, t.name
    """)
    tables = cursor.fetchall()

    results = []
    for schema_name, table_name in tables:
        try:
            count_cursor = conn.cursor()
            count_cursor.execute(f"SELECT COUNT(*) FROM [{schema_name}].[{table_name}]")
            row_count = count_cursor.fetchone()[0]
        except Exception:
            row_count = 0

        col_cursor = conn.cursor()
        col_cursor.execute(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_NAME = ? ORDER BY ORDINAL_POSITION",
            (table_name,)
        )
        columns = [row[0] for row in col_cursor.fetchall()]

        results.append({"table": table_name, "row_count": row_count, "columns": columns})

    return results


def build_prompt(batch: list) -> str:
    categories_str = ", ".join(CATEGORIES)
    table_lines = []
    for t in batch:
        cols_preview = ", ".join(t["columns"][:12])
        table_lines.append(f"- {t['table']} (rows: {t['row_count']}) columns: {cols_preview}")

    return f"""You are classifying database tables from a hospital/diagnostic lab
system (Sahasra/KonnectLIS) into business categories, based on table and
column names.

Categories: {categories_str}

For tables that are NOT patient-facing clinical/business data — e.g.
system config, UI menus, SMS templates, app version tracking, API keys,
user session logs — respond with category "skip".

If genuinely unsure, respond with category "uncertain" rather than guessing.

Respond with ONLY a JSON array, no markdown fences, no other text.
Keep "reasoning" to 4 words or fewer — this is a hint for a human
reviewer, not an explanation.
[{{"table": "...", "category": "...", "reasoning": "..."}}, ...]

Tables to classify:
{chr(10).join(table_lines)}
"""


def parse_llm_response(text: str) -> list:
    """Strips markdown code fences if present, then parses JSON. Raises on failure."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    return json.loads(cleaned)


def classify_batch(llm, batch: list) -> list:
    prompt = build_prompt(batch)
    response = llm.invoke(prompt)
    text = response.content if hasattr(response, "content") else str(response)

    try:
        return parse_llm_response(text)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"  WARNING: could not parse LLM response for this batch ({e}). Marking as 'uncertain'.")
        return [{"table": t["table"], "category": "uncertain", "reasoning": "LLM response unparseable"} for t in batch]


def run():
    conn = get_hospital_connection()
    if not conn:
        print("Could not connect to the database. Check your .env MSSQL_* settings.")
        sys.exit(1)

    print("Fetching full schema (tables, row counts, columns)...")
    schema = get_full_schema(conn)
    conn.close()
    print(f"Found {len(schema)} tables.\n")

    heuristic_skip = [t for t in schema if is_likely_legacy(t["table"])]
    to_classify = [t for t in schema if not is_likely_legacy(t["table"])]
    print(f"{len(heuristic_skip)} tables auto-flagged as legacy/backup (skipped, no LLM call needed)")
    print(f"{len(to_classify)} tables to classify via LLM in batches of {BATCH_SIZE}\n")

    from langchain_groq import ChatGroq
    # max_tokens set explicitly: without it, a batch of 25 tables with
    # reasoning text can get cut off mid-JSON by Groq's default cap,
    # which is exactly what produced the "unterminated string" warnings.
    llm = ChatGroq(model="openai/gpt-oss-20b", temperature=0, api_key=settings.groq_api_key, max_tokens=4000)

    all_results = []
    for i in range(0, len(to_classify), BATCH_SIZE):
        batch = to_classify[i:i + BATCH_SIZE]
        print(f"Classifying batch {i // BATCH_SIZE + 1} ({len(batch)} tables)...")
        results = classify_batch(llm, batch)

        by_table = {r.get("table"): r for r in results if isinstance(r, dict) and r.get("table")}
        for t in batch:
            r = by_table.get(t["table"])
            all_results.append({
                "table": t["table"],
                "row_count": t["row_count"],
                "category": r["category"] if r else "uncertain",
                "reasoning": r.get("reasoning", "") if r else "not returned by LLM",
            })

    for t in heuristic_skip:
        all_results.append({
            "table": t["table"], "row_count": t["row_count"],
            "category": "skip", "reasoning": "heuristic: looks like a dated/backup/log table",
        })

    all_results.sort(key=lambda r: (r["category"], -r["row_count"]))

    with open("table_classification_review.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["table", "row_count", "category", "reasoning"])
        writer.writeheader()
        writer.writerows(all_results)

    with open("table_classification_suggested.py", "w", encoding="utf-8") as f:
        f.write('"""\nAuto-generated by auto_classify_tables.py — REVIEW BEFORE USE.\n')
        f.write('Delete/edit rows you disagree with, then merge the ones you keep\n')
        f.write('into REAL_TABLE_TO_CATEGORY in auth/table_access.py.\n"""\n\n')
        f.write("SUGGESTED_TABLE_TO_CATEGORY = {\n")
        for r in all_results:
            if r["category"] in CATEGORIES:  # only real categories, not skip/uncertain
                f.write(f'    "{r["table"].lower()}": "{r["category"]}",  # {r["reasoning"]}\n')
        f.write("}\n")

    counts = {}
    for r in all_results:
        counts[r["category"]] = counts.get(r["category"], 0) + 1

    print("\nDone. Summary:")
    for cat, count in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")
    print("\nWrote table_classification_review.csv (scan this)")
    print("Wrote table_classification_suggested.py (ready-to-paste dict, review first)")


if __name__ == "__main__":
    run()