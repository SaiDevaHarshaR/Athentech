"""
Verified high-value tables for premium answers.
Keep this list tight. Expand only after DBA confirmation.
"""

# Always lowercase for matching
CORE_PATIENT_TABLES = [
    "mstpatientregistration",
]

# From your known working set
KNOWN_OPERATIONAL_TABLES = [
    "mstpatientregistration",
    "tblclientdocinfo",
    "mstlocationusers",
    "mstworkstations",
    "trnpurchaseorder",
    "trnmodeofcollections",
    "trnmodeofcollectionsdet",
    "trninvlabdet",
    "trninvlabpri",
]

# Billing/collections candidates — confirm names with:
# SELECT name FROM sys.tables WHERE name LIKE '%collect%' OR name LIKE '%bill%' OR name LIKE '%receipt%' OR name LIKE '%pay%'
BILLING_CANDIDATE_HINTS = [
    "collect",
    "bill",
    "receipt",
    "payment",
    "paymode",
    "modeofcollection",
]

def schema_hint_for_prompt(allowed_tables: list[str]) -> str:
    """Short stable hint injected into premium system prompt."""
    preferred = [t for t in KNOWN_OPERATIONAL_TABLES if t in set(allowed_tables)]
    lines = [
        "Preferred tables for common questions:",
        "- patients/registration → mstpatientregistration",
        "- collections/pay mode details → trnmodeofcollections / trnmodeofcollectionsdet (if allowed)",
        "- always describe_table before SELECT",
        "- always SELECT TOP 20 (or TOP 10 for lists)",
        "- for day collection: filter by date + location/branch columns after describe_table",
        "- if table/metric not in allowed list: say not available, do not invent",
    ]
    if preferred:
        lines.append("Currently preferred allowed tables: " + ", ".join(preferred))
    return "\n".join(lines)