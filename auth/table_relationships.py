"""
Reviewed table relationships (see discover_table_relationships.py) — the
human-approved subset of what that tool found. Used by describe_table
(agent/tools.py) to tell the agent how to actually join tables, instead
of it guessing join columns on every multi-table question.

Fill this in after reviewing table_relationships_review.csv. Format:
    "<table_name>": [("<column>", "<joins_to_table>", "<joins_to_column>"), ...]

Example, once reviewed:
    "trninvoicepayments": [("PatientID", "mstpatientregistration", "ID")],
"""

REAL_TABLE_RELATIONSHIPS = {
    # Populate from your reviewed table_relationships_review.csv
}


def get_relationships_for_table(table_name: str) -> list:
    """Returns [(column, joins_to_table, joins_to_column), ...] for a table, or []."""
    return REAL_TABLE_RELATIONSHIPS.get(table_name.lower(), [])