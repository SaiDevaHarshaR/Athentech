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

    # day collection / branch collection — trnmodeofcollectionsdet confirmed
    # live; trntempdaycollall confirmed STALE as of Sept 2026 (see
    # BILLING_COLLECTION_PRIORITY below for the full explanation)
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
    "trnmodeofcollectionsdet",     # confirmed live/current — prefer this for "today"/"this month"/recent dates
    "trntempdaycollall",           # CONFIRMED STALE as of Sept 2026 — has no data even for "yesterday" in
                                    # live testing, last real data seen was ~July 2026. Only useful for
                                    # historical date ranges before it stopped updating, never for current/recent.
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
        "- day collection for TODAY/THIS MONTH/recent dates → prefer trnmodeofcollectionsdet "
        "(MODE, PAIDAMOUNT, DATEOFBILL, UHID, LOCATIONID) — confirmed to have current live data.",
        "- trntempdaycollall is CONFIRMED STALE as of Sept 2026 (empirically tested: has no rows even "
        "for yesterday's date, last real data was around July 2026). Only use it for a question "
        "explicitly asking about a historical date before ~August 2026 — never for \"today\"/\"this "
        "month\"/\"recent\". If a query against it returns 0 rows for a current/recent date, that is "
        "very likely this staleness, not a real zero — say so plainly rather than reporting a "
        "confident zero, and try trnmodeofcollectionsdet instead if you haven't already.",
        "- payment mode / who paid → trnmodeofcollectionsdet (MODE, PAIDAMOUNT, DATEOFBILL, UHID, LOCATIONID)",
        "- daycollection_mobileapp may be empty; try trnmodeofcollectionsdet instead",
        "- patients/registration → mstpatientregistration",
        "- payment mode split (cash/card/upi) → trnmodeofcollectionsdet / pay mode detail tables (if allowed)",
        "- invoice/payments → trninvoicepayments, mstpaymentdetails, trninvpaydetails (if allowed)",
        "- labs → trninvlabdet, trninvlabpri, trnparamresult, mstinvestigations (if allowed)",
        "- always call describe_table before SELECT (never guess columns)",
        "- lists: SELECT TOP 10; totals: use SUM/COUNT/AVG over full filtered set (no TOP on aggregates)",
        "- filter by date + branch/location when asked (after you see real column names)",
        "- CONFIRMED (do not re-derive, do not guess a different column): in mstlocationusers, the "
        "location NAME lives in the UserId column (not Id — Id is a numeric key, comparing it to a "
        "name string will error). Example, confirmed working: to filter trnmodeofcollectionsdet by "
        "'Kompally':\n"
        "    SELECT ... FROM trnmodeofcollectionsdet\n"
        "    WHERE LOCATIONID IN (SELECT Id FROM mstlocationusers WHERE UserId LIKE '%Kompally%')\n"
        "    AND DATEOFBILL = ...\n"
        "  Use UserId LIKE for the name lookup every time — do not try Id, LOCATIONID, or any other "
        "column on mstlocationusers for name matching, that has already been tried and confirmed wrong.",
        "- CRITICAL — LOCATIONID vs location NAME are different things in OTHER tables too, do not "
        "confuse them: LOCATIONID (or similar *ID columns) holds a numeric/short CODE, NOT a name — "
        "LIKE-matching a name against an ID column will NEVER match anything. If the table you're "
        "querying only has a LOCATIONID column (no text name column), resolve via mstlocationusers "
        "as shown above. If the table DOES have a text location name column directly (e.g. "
        "trntempdaycollall.LOCATION), just LIKE-match that column directly, no resolution step needed. "
        "If a location filter returns 0 rows after doing this correctly, THEN it may be genuinely no "
        "data (or the earlier data-lag issue) — but check whether you matched a code against a name "
        "before concluding that. If a resolved location ID query returns 0 rows for TODAY, also "
        "sanity-check by trying WITHOUT the date filter first — if that also returns 0 rows, the ID "
        "itself is likely wrong (e.g. a duplicate/similarly-named location matched instead), not a "
        "genuine no-data-today situation.",
        "- if table/metric not allowed or columns unclear: say not available — do not invent numbers",
        "- if a query for a CURRENT/recent date returns 0 rows or all-zero aggregates, do not report "
        "that as a confident zero — say plainly that no data was found for that filter and it may "
        "reflect a data lag rather than genuinely zero activity.",
        "- when a result is grouped/reported BY LOCATION, never show a raw code like 'LOC04' as the "
        "final answer — that's a code, not a name a person can use. If your query grouped by a "
        "LOCATIONID column, describe_table on mstlocationusers (or join to it) to resolve the real "
        "location name before presenting the answer. If you truly cannot resolve it, say the location "
        "code plainly as a code (e.g. \"location code LOC04\") rather than presenting it as if it were "
        "already a name.",
        "- GENERAL RULE: your first query returning 0 rows is NOT automatically the final answer. You "
        "have room for several tool calls — use it. Before telling the user 'no data available', ask "
        "yourself what could be wrong with the query itself: wrong table (try another from the "
        "preferred list above), exact-match filter that should be LIKE, wrong date column, or a "
        "column name you guessed instead of confirming with describe_table. Try at least one genuinely "
        "different approach before concluding there's no data. Only report 'no data' after a real "
        "second attempt, not after one query that happened to return nothing.",
    ]

    if billing:
        lines.append("Billing/collection tables available to this role: " + ", ".join(billing))
    if preferred:
        lines.append("Preferred allowed tables: " + ", ".join(preferred[:25]))
        if len(preferred) > 25:
            lines.append(f"... and {len(preferred) - 25} more preferred matches")

    return "\n".join(lines)