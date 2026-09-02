"""
Verified high-value tables for premium answers.
Keep this list tight. Expand only after confirmation.
"""

CORE_PATIENT_TABLES = [
    "mstpatientregistration",
]

# Prefer these when the question matches (must also be role-allowed)
KNOWN_OPERATIONAL_TABLES = [
    # patients
    "mstpatientregistration",
    "tblclientdocinfo",

    # day collection / branch collection (best first guesses for "day collection")
    "daycollection_mobileapp",
    "trntempdaycollall",
    "trntempbranchwisecoll",
    "trntempmoncoll",
    "trntempshiftcollecrpt",

    # payments / mode of collection
    "trnmodeofcollectionsdet",
    "trnmodeofcollections",
    "trninvoicepayments",
    "mstpaymentdetails",
    "trninvpaydetails",
    "trnccpayments",
    "trnccpaymodedetails",
    "trncomppaymodedetails",
    "trnacntvoupaymntmodeofcolctndetails",

    # invoices / bills
    "trninvoicegeneration",
    "trnmergeddocbilldtls",
    "trnmergeddocbilldtls_referral",
    "cc_invoice",

    # lab ops
    "trninvlabdet",
    "trninvlabpri",
    "trnparamresult",
    "mstinvestigations",

    # doctors / staff / inventory commonly asked
    "mstdoctor",
    "mstrefdoctor",
    "mstlocationusers",
    "mstworkstations",
    "trnpurchaseorder",
    "trnstock",
]

BILLING_COLLECTION_PRIORITY = [
    "trntempdaycollall",           # primary day collection summary
    "trnmodeofcollectionsdet",     # payment mode line details
    "trntempbranchwisecoll",
    "daycollection_mobileapp",     # may be empty
    "trninvoicepayments",
    "mstpaymentdetails",
]


def schema_hint_for_prompt(allowed_tables: list) -> str:
    allowed = set(allowed_tables or [])
    preferred = [t for t in KNOWN_OPERATIONAL_TABLES if t in allowed]
    billing = [t for t in BILLING_COLLECTION_PRIORITY if t in allowed]

    lines = [
        "Preferred tables for common questions:",
        "- day collection → prefer trntempdaycollall (LOCATION, BILLDATE, TOTALCASH, TOTALUPI, TOTALCREDITCARDS, etc.)",
        "- payment mode / who paid → trnmodeofcollectionsdet (MODE, PAIDAMOUNT, DATEOFBILL, UHID, LOCATIONID)",
        "- daycollection_mobileapp may be empty; fall back to trntempdaycollall",
        "- patients/registration → mstpatientregistration",
        "- day collection / branch collection → try daycollection_mobileapp, trntempdaycollall, trntempbranchwisecoll (if allowed)",
        "- payment mode split (cash/card/upi) → trnmodeofcollectionsdet / pay mode detail tables (if allowed)",
        "- invoice/payments → trninvoicepayments, mstpaymentdetails, trninvpaydetails (if allowed)",
        "- labs → trninvlabdet, trninvlabpri, trnparamresult, mstinvestigations (if allowed)",
        "- always call describe_table before SELECT (never guess columns)",
        "- lists: SELECT TOP 10; totals: use SUM/COUNT/AVG over full filtered set (no TOP on aggregates)",
        "- filter by date + branch/location when asked (after you see real column names)",
        "- if table/metric not allowed or columns unclear: say not available — do not invent numbers",
    ]

    if billing:
        lines.append("Billing/collection tables available to this role: " + ", ".join(billing))
    if preferred:
        lines.append("Preferred allowed tables: " + ", ".join(preferred[:25]))
        if len(preferred) > 25:
            lines.append(f"... and {len(preferred) - 25} more preferred matches")

    return "\n".join(lines)