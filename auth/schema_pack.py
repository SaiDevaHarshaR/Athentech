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
        "- trntempdaycollall's own COLLECTION AMOUNT COLUMNS (TOTALCASH, TOTALUPI, GTOTALCREDITS etc.) "
        "are CONFIRMED STALE as of Sept 2026 (empirically tested: has no rows even for yesterday's "
        "date, last real amount data was around July 2026). Never use trntempdaycollall's amount "
        "columns for a current/recent date question — use trnmodeofcollectionsdet's PAIDAMOUNT "
        "instead for actual money totals. HOWEVER, trntempdaycollall's LOCATION and LOCATIONID "
        "columns are still fine to use for resolving a location NAME to its code — the location list "
        "itself doesn't go stale the way daily amounts do (see the location-resolution rule below). "
        "Don't confuse these two different uses of the same table.",
        "- payment mode / who paid → trnmodeofcollectionsdet (MODE, PAIDAMOUNT, DATEOFBILL, UHID, LOCATIONID)",
        "- daycollection_mobileapp may be empty; try trnmodeofcollectionsdet instead",
        "- patients/registration → mstpatientregistration",
        "- payment mode split (cash/card/upi) → trnmodeofcollectionsdet / pay mode detail tables (if allowed)",
        "- invoice/payments → trninvoicepayments, mstpaymentdetails, trninvpaydetails (if allowed)",
        "- labs → trninvlabdet, trninvlabpri, trnparamresult, mstinvestigations (if allowed)",
        "- always call describe_table before SELECT (never guess columns)",
        "- lists: SELECT TOP 10; totals: use SUM/COUNT/AVG over full filtered set (no TOP on aggregates)",
        "- filter by date + branch/location when asked (after you see real column names)",
        "- BANNED FOR LOCATIONS — mstlocationusers is a STAFF/USER ACCOUNTS table (real content: "
        "'DR.G.VIJAY RAMREDDY', 'KM', staff names), NOT a locations table, despite the name. It has "
        "repeatedly caused wrong answers by conflating staff records with actual locations, including "
        "in list-style questions ('which locations have billing records' returning staff names like "
        "'Ajay', 'Dr. Afnija' mixed with codes). NEVER query mstlocationusers for anything "
        "location-related — not for a specific lookup, not for a list of locations, not for any "
        "purpose. Use trntempdaycollall instead every time (see next rule).",
        "- CONFIRMED (do not re-derive): trntempdaycollall has BOTH the location NAME and its real "
        "LOCATIONID code (format 'LOC0X') together, in the same table. Use this for ALL location "
        "name-to-code resolution and for listing locations:\n"
        "    -- one specific location:\n"
        "    SELECT ... FROM trnmodeofcollectionsdet\n"
        "    WHERE LOCATIONID IN (SELECT DISTINCT LOCATIONID FROM trntempdaycollall WHERE LOCATION LIKE '%Kompally%')\n"
        "    -- a list of active locations, WITH real names (not raw codes):\n"
        "    SELECT DISTINCT LOCATION, LOCATIONID FROM trntempdaycollall\n"
        "  Confirmed via a direct value-overlap check: trntempdaycollall.LOCATIONID and "
        "trnmodeofcollectionsdet.LOCATIONID share ~91-97% real overlap — they are the same registry. "
        "A small number of codes may exist on only one side (data drift) — that's expected, not a bug.",
        "- CRITICAL — LOCATIONID vs location NAME are different things in OTHER tables too, do not "
        "confuse them: LOCATIONID (or similar *ID columns) holds a numeric/short CODE, NOT a name — "
        "LIKE-matching a name against an ID column will NEVER match anything. If a location filter "
        "returns 0 rows after resolving correctly via trntempdaycollall, THEN it may be genuinely no "
        "data — but also sanity-check by trying WITHOUT the date filter first. If that ALSO returns 0 "
        "rows, check MAX(DATEOFBILL) for that specific resolved code before concluding it's a bug — a "
        "real, confirmed case exists where one location's feed into trnmodeofcollectionsdet stopped "
        "entirely years ago (last record 2023) while other locations' feeds continued normally. That's "
        "a real data fact about that specific location, not a resolution error — report it as such "
        "(e.g. 'this location's most recent record here is from 2023') rather than a generic "
        "'no data/lag' message once you've confirmed this pattern.",
        "- if table/metric not allowed or columns unclear: say not available — do not invent numbers",
        "- CONFIRMED (do not re-derive): trninvlabdet.DEPTCODE is a NUMERIC code, not a name — "
        "'Radiology' etc. is never the literal stored value, confirmed via a real profile of the "
        "table (values look like '1','2','9','26','28'...). The real department NAME lives in "
        "mstdepartment (DEPARTMENTID, DEPARTMENTNAME — confirmed 9 real rows including literally "
        "'Radiology'). mstlabdesc is EMPTY (0 rows) — do not use it for this, it was tried and "
        "confirmed useless. Resolve every department filter through mstdepartment:\n"
        "    SELECT ... FROM trninvlabdet\n"
        "    WHERE DEPTCODE = (SELECT DEPARTMENTID FROM mstdepartment WHERE DEPARTMENTNAME LIKE '%Radiology%')\n"
        "  Never write DEPTCODE = 'Radiology' or any other department name directly — always resolve "
        "through mstdepartment first, same principle as the location fix above. Note: mstdepartment "
        "only has 9 broad department rows while DEPTCODE's full range goes higher (up to ~40) — those "
        "higher values are likely more granular sub-codes not covered by this table; that's fine for "
        "broad departments like Radiology (which resolves through mstdepartment correctly), just don't "
        "assume mstdepartment covers every possible DEPTCODE value for narrower sub-categories.",
        "- DEPTCODE is a DEPARTMENT, not a LOCATION — never search trntempdaycollall.LOCATION for a "
        "department name (e.g. LOCATION LIKE '%Radiology%' is always wrong, Radiology is not a "
        "branch/location, that was a real confirmed mistake in production).",
        "- CONFIRMED (do not re-derive): trninvlabdet.TESTSTATUS real values are exactly: "
        "'', 'Acknowledged', 'Cancelled', 'Pending', 'Registered', 'Result Entry', 'Sample Collected', "
        "'Sample Rejected'. There is NO 'Completed' value — a query filtering or counting "
        "TESTSTATUS = 'Completed' will always return 0/nothing, a real confirmed bug in production. "
        "For 'completed' style questions, treat 'Result Entry' and/or 'Acknowledged' as the "
        "equivalent of done (results have been entered/confirmed) — verify which is right for the "
        "specific question rather than assuming.",
        "- GENERAL RULE, more important than any single column above — this is the actual repeating "
        "pattern found in production, not a one-off: for ANY column that looks like a status/type/"
        "mode/category (ends in STATUS, TYPE, MODE, or similar — e.g. STATUS, TESTSTATUS, PATTYPE, "
        "REGSTATUS, CASHIERSTATUS), NEVER assume a plausible-sounding English word (like 'Completed', "
        "'Active', 'Approved') is the literal stored value. These systems commonly use short codes "
        "('A', 'RE', 'Pen'), abbreviations, or specific capitalization that don't match plain English "
        "guesses. If you haven't already seen a column's real distinct values earlier in this "
        "conversation, run SELECT DISTINCT <column> first before filtering on it — this one habit "
        "prevents the majority of wrong-answer bugs found in this system, across any table, not just "
        "the specific ones documented above.",
        "- if a query for a CURRENT/recent date returns 0 rows or all-zero aggregates, do not report "
        "that as a confident zero — say plainly that no data was found for that filter and it may "
        "reflect a data lag rather than genuinely zero activity.",
        "- when a result is grouped/reported BY LOCATION, never show a raw code like 'LOC04' as the "
        "final answer — that's a code, not a name a person can use. Resolve it via trntempdaycollall "
        "(never mstlocationusers, banned above) before presenting the answer. If you truly cannot "
        "resolve it, say the location code plainly as a code (e.g. \"location code LOC04\") rather "
        "than presenting it as if it were already a name.",
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