"""
Answers ONE specific, high-value question directly: do two columns in
different tables actually share the same value registry, or do they
just look similar (same format, same name) while meaning different
things?

This is exactly the question that cost hours today: trntempdaycollall
and trnmodeofcollectionsdet both have a LOCATIONID column in 'LOC0X'
format — but they turned out to be two unrelated registries. This
script checks real overlap directly instead of assuming format
similarity means the same thing.

Usage:
    python check_column_overlap.py trntempdaycollall LOCATIONID trnmodeofcollectionsdet LOCATIONID

Output: a real percentage — 0% overlap means "these do NOT reference
the same thing, despite the shared name/format." High overlap (close
to 100%) means they likely do.
"""

import sys

from database.connection import get_hospital_connection


def get_distinct_values(conn, table: str, column: str) -> set:
    cursor = conn.cursor()
    cursor.execute(f"SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL")
    return {str(r[0]) for r in cursor.fetchall()}


def check_overlap(table_a: str, column_a: str, table_b: str, column_b: str, db_name: str = None):
    conn = get_hospital_connection(db_name)
    if not conn:
        print("Could not connect to the database.")
        return

    print(f"Fetching distinct values: {table_a}.{column_a} ...")
    values_a = get_distinct_values(conn, table_a, column_a)
    print(f"  {len(values_a)} distinct value(s)")

    print(f"Fetching distinct values: {table_b}.{column_b} ...")
    values_b = get_distinct_values(conn, table_b, column_b)
    print(f"  {len(values_b)} distinct value(s)")

    conn.close()

    if not values_a or not values_b:
        print("\nOne side has no values at all — can't compare.")
        return

    overlap = values_a & values_b
    only_in_a = values_a - values_b
    only_in_b = values_b - values_a

    overlap_pct_of_a = 100 * len(overlap) / len(values_a)
    overlap_pct_of_b = 100 * len(overlap) / len(values_b)

    print()
    print("=" * 70)
    print(f"OVERLAP: {len(overlap)} value(s) appear in both")
    print(f"  {overlap_pct_of_a:.1f}% of {table_a}.{column_a}'s values also appear in {table_b}.{column_b}")
    print(f"  {overlap_pct_of_b:.1f}% of {table_b}.{column_b}'s values also appear in {table_a}.{column_a}")
    print()

    if overlap_pct_of_a < 10 and overlap_pct_of_b < 10:
        print("CONCLUSION: These almost certainly do NOT reference the same registry,")
        print("despite matching names/formats. Do not assume a value resolved from one")
        print("table can be used to filter the other.")
    elif overlap_pct_of_a > 80 and overlap_pct_of_b > 80:
        print("CONCLUSION: High overlap — likely the same registry, BUT this alone isn't")
        print("100% proof. Short/reused code formats (like LOC01-LOC33) could coincidentally")
        print("overlap heavily even between two independently-assigned schemes. Spot-check")
        print("a few real rows sharing a code across both tables (e.g. do the dates/amounts")
        print("for a shared code plausibly belong to the same real branch?) before fully")
        print("trusting this without a manual look.")
    else:
        print("CONCLUSION: Partial overlap — inconclusive. Could mean one table has a")
        print("subset of the other's scope (e.g. active vs all locations), or could")
        print("mean they're genuinely different things that happen to share some")
        print("values by coincidence. Worth a closer manual look.")

    print("=" * 70)
    print(f"\nSample values only in {table_a}.{column_a} (first 10):", list(only_in_a)[:10])
    print(f"Sample values only in {table_b}.{column_b} (first 10):", list(only_in_b)[:10])


if __name__ == "__main__":
    if len(sys.argv) != 5:
        print("Usage: python check_column_overlap.py <table_a> <column_a> <table_b> <column_b>")
        print("Example: python check_column_overlap.py trntempdaycollall LOCATIONID trnmodeofcollectionsdet LOCATIONID")
        sys.exit(1)

    check_overlap(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])