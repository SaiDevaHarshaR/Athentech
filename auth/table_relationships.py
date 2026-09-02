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
    # Populated from table_relationships_review.csv — the 8 tables that
    # directly link to the patient table (mstpatientregistration).
    # trninvlabdetloc16 and trninvlabprisweeja look like a location-
    # specific or personal dev/backup copy (unusual suffixes) rather than
    # the main table — included anyway since a redundant join isn't
    # harmful, just worth a look if duplicate rows show up in reports.
    "trninvlabdet": [("PATID", "mstpatientregistration", "ID")],
    "trninvlabdetloc16": [("PATID", "mstpatientregistration", "ID")],
    "trninvlabpri": [("PATIENTID", "mstpatientregistration", "ID")],
    "trninvlabprisweeja": [("PATIENTID", "mstpatientregistration", "ID")],
    "trnlifeberries": [("PATID", "mstpatientregistration", "ID")],
    "trnlifeberriespri": [("PATIENTID", "mstpatientregistration", "ID")],
    "trnmodeofcollectionsdet": [("PATIENTID", "mstpatientregistration", "ID")],
    "trntempinvstatus": [("PATIENTID", "mstpatientregistration", "ID")],


   
    # Patient core
    "mstpatientregistration": [],


    # ---- BILLING / COLLECTIONS (EDIT TO REAL NAMES) ----
    # Example patterns common in LIS/HIS — verify in your DB:
    "trnmodeofcollections": [("PATIENTID", "mstpatientregistration", "ID")],
    "trnmodeofcollectionsdet": [("PATIENTID", "mstpatientregistration", "ID")],
    # Add real receipt/bill tables when confirmed, e.g.:
    # "trnbillheader": [("PATIENTID", "mstpatientregistration", "ID")],
    # "trnbilldetail": [("BILLID", "trnbillheader", "ID")],
    # "trnreceipt": [("PATIENTID", "mstpatientregistration", "ID")],


}


def get_relationships_for_table(table_name: str) -> list:
    """Returns [(column, joins_to_table, joins_to_column), ...] for a table, or []."""
    return REAL_TABLE_RELATIONSHIPS.get(table_name.lower(), [])