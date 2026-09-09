"""
Verified high-value tables for premium answers.
Keep this list tight. Expand only after confirmation.
"""

CORE_PATIENT_TABLES = [
    "mstpatientregistration",
]

# Prefer these when the question matches (must also be role-allowed)
CONFIRMED_TABLES_FROM_ATHENTECH = [
    # Verified by AthenTech directly — not guesses, use these first.
    "trninvlabpri",       # PRIMARY financial table (TOTALCHARGES, PAIDAMOUNT, CONCESSIONAMT,
                           # CREDITAMOUNT, RefundAmt, STATUS, BILLNO) — prefer over trninvlabdet for financial totals
    "trninvstatus",       # investigation STATUS by BILLNO/PKGCODE — check this before assuming
                           # TESTSTATUS on trninvlabdet is the only status source
    "mstlocation",        # dedicated location master table — check this before trntempdaycollall workaround
    "mstsubdepartment",   # SubDepartmentID — more granular than mstdepartment; likely explains why
                           # DEPTCODE values go higher than mstdepartment's 9 rows cover. Confirmed:
                           # SubDepartmentID unique per SubDeptName (e.g. 15=ENDOSCOPY, 17=HAEMATOLOGY).
                           # Joins: DEPARTMENTID=DEPARTMENTID, LOCATIONID=LocationID to mstdepartment.
    "mstinvestigationsdtls", "mstorginvestigationrates",  # investigation rates, paying-location / org-location wise
    "mstinvpackages",     # PACKAGECODE + LOCATIONID
    "trnparameter",       # test parameter definitions
    "mstorganisation",    # ORGANISATIONCODE — client/company master
]
# Refunds: trnmodeofcollectionsdet WHERE TYPE = 'LabRefund' (TYPE column,
# distinct from MODE) — confirmed real value, not a guess.

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
        "- CONFIRMED (AthenTech-given): looking up a specific test/investigation by name "
        "(e.g. 'CBP', 'radiology tests for X') → SELECT * FROM mstInvestigations WHERE INVNAME LIKE "
        "'%X%'. Use this directly — do NOT invent a join through mstoltestparamsmapping/"
        "mstinvestigationconcform or any other table for this, that has already been tried and "
        "returned wrong/empty results.",
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
        "- CONFIRMED: trnmodeofcollectionsdet's real columns are MODE, PAIDAMOUNT, DATEOFBILL, UHID, "
        "LOCATIONID, TYPE, BILLNO, PATIENTID — that's the full confirmed set. TOTALAMOUNT, "
        "CONCESSIONAMOUNT, DUEAMOUNT do NOT exist on this table (guessed in production, never "
        "confirmed) — if a broader billed/concession/due figure is needed, describe_table on "
        "trninvlabpri instead (confirmed real columns: TOTALCHARGES, PAIDAMOUNT, CONCESSIONAMT, "
        "CREDITAMOUNT, RefundAmt).",
        "- trntempbranchwisecoll is UNPROFILED — do not assume column names like GrossAmount, "
        "NetReceivedAmount, nrCash, nrCC, nrChqUPI, ReceivedAmount exist on it (guessed in production, "
        "never confirmed). describe_table it first before using it for anything.",
        "- CONFIRMED (do not re-derive): daycollection_mobileapp is NOT empty for recent months — "
        "confirmed real, non-empty columns: ID, GRANDTOTAL, TOTALCASH, TOTALCREDITS, DUES, "
        "CONCESSIONS, CARDTOTAL, CHEQUETOTAL, REFUNDS, PREVREFUNDS, EXPTOTAL, COREBUSINESSCASH, "
        "PREVDUECASH, PREVDUECARD, PREVDUECHEQUE, PREVDUEDD, TOTALCASHREC, COREBUSINESS, "
        "PAIDBUSINESS, TOTALLABCLIENTS, CCCASH, CCCARD, CCCONCESSION, TOTALBUSINESS_CC, "
        "PAIDBUSINESS_CC, REPORTDATE, DATE, LOCATIONID. Column names look promising for detailed "
        "cash-reconciliation questions (PAIDBUSINESS matches 'Total Paid Business' exactly, "
        "TOTALCASHREC is a plausible candidate for 'Total Cash In Hand', PREVDUECASH/CARD/CHEQUE/DD "
        "look like 'Total Previous Due Received' broken out by mode) — BUT this table has since been "
        "confirmed NOT reliably usable: BOTH LOCATIONID and DATE are NULL for every single row "
        "(confirmed via SELECT DISTINCT LOCATIONID → 0 rows, and MIN(DATE)/MAX(DATE) → NULL even "
        "with CONVERT to text). This means it CANNOT be filtered by location or by date at all — any "
        "such filter will always return 0 rows, and an earlier answer that looked correct for 'this "
        "month' was very likely an accidental unfiltered full-table aggregate, not genuinely "
        "date-scoped data — do not trust that as confirmed-correct. Do NOT use this table for "
        "anything requiring a specific date range or location. If a detailed reconciliation report "
        "is asked for, say plainly this table doesn't support the needed filtering, and offer the "
        "mode-of-payment breakdown from trnmodeofcollectionsdet instead — do not silently fall back "
        "to an unfiltered aggregate and present it as if it answered the actual question asked.",
        "- patients/registration → mstpatientregistration",
        "- payment mode split (cash/card/upi) → trnmodeofcollectionsdet / pay mode detail tables (if allowed)",
        "- invoice/payments → trninvoicepayments, mstpaymentdetails, trninvpaydetails (if allowed)",
        "- labs → trninvlabdet, trninvlabpri, trnparamresult, mstinvestigations (if allowed)",
        "- CONFIRMED (real sample data): mstorganisation holds BOTH individual referring DOCTORS and "
        "referring HOSPITALS/ORGANIZATIONS mixed in the same table under ORGANISATIONNAME. Real "
        "sample rows: 'A SRINIVAS MBBS (TOOPRAN)' (COMPTYPE='L', doctor-shaped) vs 'AASHRITA "
        "HOSPITAL' / '.HIMIGIRI S.' (COMPTYPE='RL', hospital-shaped). COMPTYPE is very likely the "
        "field that distinguishes them — this directly explains a real confirmed bug where 'top "
        "referring doctors' mixed in hospital names, because nothing filtered by COMPTYPE. Only 2 "
        "sample COMPTYPE values are confirmed so far ('L', 'RL') — the FULL set is NOT confirmed. "
        "Before filtering by COMPTYPE for a 'doctors only' question, run SELECT DISTINCT COMPTYPE "
        "FROM mstorganisation first to see every real value and confirm which one(s) mean individual "
        "doctor — do not assume 'L' alone covers all doctors without checking. Other real columns: "
        "ORGANISATIONCODE, CREDITLIMIT, CREDITPERIOD, ISCREDIT, ISINSURANCE, ACTIVE, LOCATIONID, "
        "ORGTypeID.",
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
        "table (values look like '1','2','9','26','28'...). This code can reference EITHER "
        "mstdepartment (broad, only 9 rows, IDs 1-9) OR mstsubdepartment (granular, IDs up to 80+, "
        "e.g. SubDepartmentID=17 is HAEMATOLOGY, 33 is RADIOLOGY PROCEDURE CHARGES) — DEPTCODE's full "
        "range (up to ~83) matches mstsubdepartment's range, not mstdepartment's. For a SPECIFIC named "
        "department/section (Haematology, Biochemistry, Microbiology, Endoscopy, etc.) that isn't one "
        "of mstdepartment's 9 broad names, resolve through mstsubdepartment FIRST:\n"
        "    SELECT ... FROM trninvlabdet\n"
        "    WHERE DEPTCODE = (SELECT SubDepartmentID FROM mstsubdepartment WHERE SubDeptName LIKE '%Haematology%')\n"
        "  Only fall back to mstdepartment for genuinely broad terms (Radiology, Lab, Pathology) where "
        "mstdepartment already has a direct row. mstlabdesc is EMPTY (0 rows) — never use it, confirmed "
        "useless. Never write DEPTCODE = 'SomeName' directly in either case.",
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
        "- CONFIRMED (AthenTech-given, more authoritative than TESTSTATUS above): trninvstatus.STATUS "
        "real values, in order: 'Registered' (1st, sample registered) → 'Sample Collected' (2nd) → "
        "'Acknowledged' (3rd) → 'Authenticated' (4th, means it reached the doctor — NOT the final "
        "step, just doctor review). 'Result Entry' (a trninvlabdet.TESTSTATUS value, not this column) "
        "means the sample's result was entered — that's closer to lab-side completion than "
        "'Authenticated' is. Plus terminal states 'Cancelled', 'Pending', 'Refunded', 'Sample "
        "Rejected'. Do NOT assume any one of these values means 'fully done' — which value counts as "
        "'completed' depends on the specific question (lab-side done vs doctor-reviewed vs fully "
        "closed) and hasn't been confirmed generically. If unsure which stage a 'completed' question "
        "means, say what you counted plainly (e.g. 'results entered: N') rather than labeling it "
        "'completed' as if that were settled.",
        "- CONFIRMED (AthenTech-given): trnmodeofcollectionsdet.MODE real values: 'Cash', 'CHEQUE', "
        "'CONCESSION', 'CREDITCARD', 'DD', 'online', 'UPI'. Note 'CONCESSION' is itself a MODE value, "
        "not a separate concept — a naive SUM(PAIDAMOUNT) across all modes for 'total collected' may "
        "need to exclude MODE='CONCESSION' depending on the question (concessions aren't real cash "
        "collected).",
        "- CONFIRMED (AthenTech-given): trnmodeofcollectionsdet.TYPE real values: 'DUE PAYMENT', "
        "'LabConcession2', 'LabRefund', 'Membership', 'OPLAB'. This is a SEPARATE column from MODE — "
        "use both together for precise breakdowns. Strong lead for reconciliation-style reports (e.g. "
        "a 'Cash In Hand' report a user showed with separate 'Total Cash Bill', 'Total Previous Due "
        "Received', 'Total Refund' line items): 'Total Previous Due Received' is very likely "
        "TYPE='DUE PAYMENT', 'Total Refund' is very likely TYPE='LabRefund'. This is a lead, not yet "
        "a confirmed formula for the full reconciliation — don't present a computed 'Cash In Hand' "
        "figure as confirmed-correct until the exact formula (which TYPEs add vs subtract) is verified.",
        "- CRITICAL, SEVERE real bug confirmed in production: DATEPART(YEAR, GETDATE()) = 2026 AND "
        "DATEPART(MONTH, GETDATE()) = 4 was used to try to filter for 'April 2026' data — this is "
        "WRONG. GETDATE() returns the REAL CURRENT date (today), not the transaction date — that "
        "filter checks 'is today currently in April 2026', not 'did this row happen in April 2026'. "
        "Since GETDATE() reflects the actual current date, a query like this returns nothing for any "
        "month except whichever one happens to be the real current month right now — completely "
        "ignoring the month the user actually asked about. NEVER compare DATEPART(..., GETDATE()) to "
        "a hardcoded target year/month. To filter by a period, filter the table's own date COLUMN "
        "directly: WHERE DATEOFBILL >= '2026-04-01' AND DATEOFBILL < '2026-05-01' (or the equivalent "
        "real date column for that table) — GETDATE() only belongs in a query when you actually mean "
        "'today', never as a stand-in for a date the user specified.",
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
        "- CONFIRMED real bug: AVG(DATEDIFF(...)) for turnaround time (TAT) calculations can be "
        "destroyed by a small number of corrupted/outlier records (e.g. a BILLDATE stored as some "
        "old default date, creating a gap of years instead of minutes/hours). Confirmed in production: "
        "an 'average TAT' came back as 23,002,736 minutes (~44 years) — not a real answer. When "
        "computing AVG TAT, exclude implausible outliers from the calculation, e.g.: "
        "AVG(CASE WHEN DATEDIFF(MINUTE, BILLDATE, CREATEDATE) BETWEEN 0 AND 10080 THEN "
        "DATEDIFF(MINUTE, BILLDATE, CREATEDATE) END) — the 10080 bound is 7 days in minutes, a "
        "generous upper limit for a real TAT; adjust if a narrower bound makes sense for the specific "
        "question, but never report a raw unbounded AVG that could be silently wrecked by bad data. "
        "CRITICAL SCOPE — this CASE WHEN filter belongs ONLY inside the AVG() function itself, exactly "
        "as shown. Do NOT add a WHERE clause filtering out these outlier records from the whole query "
        "— that would also wrongly shrink PROCEDURES/COMPLETED/PENDING counts (undercounting real "
        "work, not just fixing a skewed average). A record with a bad date should still count as a "
        "real procedure/completed/pending — it should just not corrupt the TAT average specifically. "
        "This was a real mistake found in production: fixing the average also silently shrank the "
        "procedure counts by hundreds when it shouldn't have touched them at all.",
        "- CONFIRMED real bug: a curated location tool (get_verified_day_collection) requires ONE "
        "specific location — if the user asks for 'all branches'/'all locations'/a combined total "
        "across every location, do NOT call that tool with location_keyword='all' (this was tried in "
        "production and matched multiple real locations that coincidentally contain 'all' as a "
        "substring — Kompally, Kukatpally, etc. — a real, confusing false-positive). For an "
        "ALL-LOCATIONS-COMBINED question, use describe_table/run_sql_query instead, with NO location "
        "filter in the WHERE clause at all.",
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