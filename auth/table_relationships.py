"""
Reviewed join hints used by describe_table.
Only include joins you trust. Wrong joins are worse than none.
"""

REAL_TABLE_RELATIONSHIPS = {
    # Patient core
    "mstpatientregistration": [],

    # Lab ↔ patient (confirmed)
    "trninvlabdet": [("PATID", "mstpatientregistration", "ID")],
    "trninvlabdetloc16": [("PATID", "mstpatientregistration", "ID")],
    "trninvlabpri": [("PATIENTID", "mstpatientregistration", "ID")],
    "trninvlabprisweeja": [("PATIENTID", "mstpatientregistration", "ID")],
    "trnlifeberries": [("PATID", "mstpatientregistration", "ID")],
    "trnlifeberriespri": [("PATIENTID", "mstpatientregistration", "ID")],
    "trntempinvstatus": [("PATIENTID", "mstpatientregistration", "ID")],

    # Collections ↔ patient (confirmed pattern)
    "trnmodeofcollectionsdet": [("PATIENTID", "mstpatientregistration", "ID")],
    "trnmodeofcollections": [("PATIENTID", "mstpatientregistration", "ID")],

    # Likely patient-linked billing (VERIFY column names with describe_table before relying)
    # Keep empty until you confirm column names — prevents bad joins.
    "trninvoicepayments": [],
    "mstpaymentdetails": [],
    "trninvpaydetails": [],
    "trnmergeddocbilldtls": [],
    "trnmergeddocbilldtls_referral": [],
    "daycollection_mobileapp": [],
    "trntempdaycollall": [],
    "trntempbranchwisecoll": [],
}


def get_relationships_for_table(table_name: str) -> list:
    """Returns [(column, joins_to_table, joins_to_column), ...] or []."""
    return REAL_TABLE_RELATIONSHIPS.get(table_name.strip().lower(), [])