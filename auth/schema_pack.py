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

    # location master (confirmed replacement for the banned trntempdaycollall workaround)
    "mstlocation",

    # day collection / branch collection — trnmodeofcollectionsdet confirmed
    # live. trntempdaycollall, trntempbranchwisecoll, trntempmoncoll,
    # trntempshiftcollecrpt, daycollection_mobileapp, trnbillingcyclerates
    # are ALL BANNED OUTRIGHT per AthenTech dev team instruction — removed
    # from this list entirely, not just flagged as stale.

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
    # trntempdaycollall, trntempbranchwisecoll, daycollection_mobileapp are
    # ALL BANNED OUTRIGHT per AthenTech dev team instruction — removed
    # entirely, not just deprioritized.
    "trninvoicepayments",
    "mstpaymentdetails",
]


def schema_hint_for_prompt(allowed_tables: list) -> str:
    allowed = set(allowed_tables or [])
    preferred = [t for t in KNOWN_OPERATIONAL_TABLES if t in allowed]
    billing = [t for t in BILLING_COLLECTION_PRIORITY if t in allowed]

    lines = [
        "Preferred tables for common questions:",
        "- BANNED OUTRIGHT (AthenTech dev team instruction — do not use, do not query, do not "
        "reference at all, not even with caveats, not even for location-name lookup): any table "
        "starting with 'trntemp' (trntempdaycollall, trntempabnormalreport, "
        "trntemppatientrepeatevisits, and any other trntemp*-prefixed table), trnbillingcyclerates, "
        "and daycollection_mobileapp. This includes trntempdaycollall's LOCATION/LOCATIONID columns "
        "— even though they were previously confirmed usable for location-name resolution, that "
        "workaround is banned now too. CONFIRMED REPLACEMENT: mstlocation (LOCATIONID, LOCATIONNAME, "
        "ACTIVE — real sample rows verified: LOC01=Kompally, LOC02=Kukatpally, LOC03=Kokapet, "
        "LOC04=Jagtial, LOC10=Srikara-Boduppal). Use mstlocation for ALL location name-to-code "
        "resolution and location listing now — the same pattern as before, just this table instead: "
        "SELECT DISTINCT LOCATIONID, LOCATIONNAME FROM mstlocation WHERE LOCATIONNAME LIKE '%X%'. If "
        "a question would normally use one of the banned tables for anything ELSE (not location "
        "resolution), find a different real table instead — if no alternative exists, say plainly "
        "that this specific thing isn't available. Also: do NOT filter mstorganisation.COMPTYPE by "
        "'L' or 'RL' to separate doctors from hospitals — that assumption is no longer trusted; if a "
        "'doctors only' question can't be answered another way (e.g. via the confirmed mstrefdoctor "
        "join below), say so plainly instead of using COMPTYPE.",
        "- CONFIRMED (real procedure definition obtained): the 'Cash In Hand'/detailed reconciliation "
        "logic lives in dbo.LabDayCollection — a real stored procedure with ~30 SELECT statements, "
        "several calling OTHER stored functions (DUEREC, SEC_CONC, CCDUEAMT, CC_CREDIT, DUERECDtls, "
        "SEC_CONCDtls, ...) not visible from here, plus tables never otherwise seen "
        "(trnVoucherGen, trnCC_InvLabPri, mstCCReg, trnCCPayments, trnCompPayments). This is NOT "
        "reconstructable from raw table queries — do not attempt it, that has repeatedly produced "
        "wrong numbers. Use the get_lab_day_collection TOOL instead (calls this procedure directly, "
        "with @ACTIVITY='Lab') for any 'Cash In Hand'/detailed reconciliation/day collection "
        "breakdown question. CORRECTION to an earlier wrong claim: trnmodeofcollectionsdet.TOTALAMOUNT "
        "DOES exist (the real procedure uses B.TOTALAMOUNT directly) — an earlier note saying it "
        "doesn't exist was itself a guess that turned out wrong; TOTALAMOUNT, STATUS, PREVIOUSBILLNO "
        "are all confirmed real columns on this table.",
        "- CRITICAL, confirmed real bug: get_lab_day_collection is SINGLE-DAY ONLY — a real question "
        "asking for 'this year' reconciliation silently got answered with just TODAY's single-day "
        "figures, with no warning that a whole year was never actually computed. Passing a real, "
        "valid single date when the user asked for a broader period (year/month/quarter) is NOT "
        "correct just because the tool didn't error — you MUST explicitly tell the user this tool "
        "only covers one date, name which date you actually used, and say plainly that the broader "
        "period they asked for isn't supported by this tool. Never silently narrow the scope of what "
        "was asked without saying so in the answer.",
        "- CONFIRMED (AthenTech-given): looking up a specific test/investigation by name "
        "(e.g. 'CBP', 'radiology tests for X') → SELECT * FROM mstInvestigations WHERE INVNAME LIKE "
        "'%X%'. Use this directly — do NOT invent a join through mstoltestparamsmapping/"
        "mstinvestigationconcform or any other table for this, that has already been tried and "
        "returned wrong/empty results.",
        "- day collection for TODAY/THIS MONTH/recent dates → prefer trnmodeofcollectionsdet "
        "(MODE, PAIDAMOUNT, DATEOFBILL, UHID, LOCATIONID) — confirmed to have current live data.",
        "- trntempdaycollall is BANNED OUTRIGHT (see the ban rule above) — this entirely supersedes "
        "any earlier note about using its LOCATION/LOCATIONID columns for location resolution. Use "
        "mstlocation for that now (see the ban rule and the location-resolution rule below).",
        "- payment mode / who paid → trnmodeofcollectionsdet (MODE, PAIDAMOUNT, DATEOFBILL, UHID, LOCATIONID)",
        "- CORRECTED (was wrong before, now confirmed via the real dbo.LabDayCollection procedure "
        "definition): trnmodeofcollectionsdet DOES have TOTALAMOUNT, CONCESSIONAMOUNT, DUEAMOUNT, "
        "STATUS, PREVIOUSBILLNO as real columns — an earlier note claiming TOTALAMOUNT/"
        "CONCESSIONAMOUNT/DUEAMOUNT don't exist was itself an unconfirmed guess that turned out "
        "wrong. Full confirmed set now: MODE, PAIDAMOUNT, TOTALAMOUNT, CONCESSIONAMOUNT, DUEAMOUNT, "
        "DATEOFBILL, UHID, LOCATIONID, TYPE, BILLNO, PATIENTID, STATUS, PREVIOUSBILLNO. STATUS real "
        "values seen in the real procedure: 'P' (paid), 'R' (refund) — full set not independently "
        "confirmed beyond these two. PREVIOUSBILLNO links a DUE PAYMENT/LabRefund row back to the "
        "original bill it relates to.",
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
        "- CONFIRMED (real sample rows): trnparamresult.PVALUE is VARCHAR and holds TWO different "
        "kinds of results — (1) a number stored as text (e.g. '15.4', '7800') with real MINVALUE/"
        "MAXVALUE range columns to compare against for 'abnormal', or (2) pure narrative text (e.g. "
        "'NORMOCYTIC NORMOCHROMIC' — a microscopy/pathology-style descriptive result) with "
        "MINVALUE/MAXVALUE both NULL — there is NO numeric range for these, 'abnormal' cannot be "
        "computed for them at all, they'd need a human to read DESCRIPTION/Note/Advise/TEXT instead. "
        "For 'abnormal result' questions: only attempt the MINVALUE/MAXVALUE comparison, and ONLY "
        "after confirming PVALUE is numeric for that row (e.g. TRY_CAST(PVALUE AS FLOAT) IS NOT NULL "
        "— PVALUE will error on a blind CAST for rows like row 10 above). trnparamresult.Interpretation "
        "is a SEPARATE, narrower thing — confirmed real values are only 'None', 'Intermediate', "
        "'Resistant', 'Sensitive' (antibiotic culture-sensitivity results specifically), NOT a "
        "general positive/abnormal flag for other test types — do not use it for a general "
        "'abnormal finding' question outside microbiology culture results.",
        "- CONFIRMED (real table, columns useful, BUT SEVERELY STALE): trntempabnormalreport exists — "
        "INVNAME, PARAMNAME, PVALUE, MINVALUE, MAXVALUE, DESCRIPTION, BILLNO, BILLDATE, CREATEDATE, "
        "LOCATIONID, ORGNAME, DOCNAME. CONFIRMED via direct MIN/MAX(BILLDATE): its real data range is "
        "17 May 2023 to 28 August 2025 — it STOPPED being updated over a year before the real current "
        "date, same 'trntemp' staleness pattern already confirmed on trntempdaycollall (different "
        "table, same naming convention, same kind of problem). NEVER use this table for 'today'/"
        "'yesterday'/'this month'/'last month'/'this year' or any question about recent activity — "
        "it will always return 0 rows for any of those, which is a real, confirmed data gap, not a "
        "genuine zero. Only usable for a question explicitly about a historical date before ~August "
        "2025. For a RECENT abnormal-result question, say plainly that this table's data stops in "
        "2025 and no recent equivalent has been confirmed yet — do not silently report a confident "
        "zero for what is actually a coverage gap.",
        "- CONFIRMED (real bug found): common lay/short test names do NOT match real INVNAME values "
        "— 'Urinalysis' returned 0 rows because the real stored name is 'Complete Urine Analysis "
        "(CUE)'. Before concluding zero results for a named test, run SELECT DISTINCT INVNAME WHERE "
        "INVNAME LIKE '%<broader keyword>%' first (e.g. '%urine%' not '%urinalysis%') to find the "
        "real name — a lay term returning zero is more likely a naming mismatch than genuine absence.",
        "- CONFIRMED (real sample data): mstorganisation holds BOTH individual referring DOCTORS and "
        "referring HOSPITALS/ORGANIZATIONS mixed in the same table under ORGANISATIONNAME. Real "
        "sample rows: 'A SRINIVAS MBBS (TOOPRAN)' (COMPTYPE='L', doctor-shaped) vs 'AASHRITA "
        "HOSPITAL' / '.HIMIGIRI S.' (COMPTYPE='RL', hospital-shaped). COMPTYPE is very likely the "
        "field that distinguishes them — this directly explains a real confirmed bug where 'top "
        "referring doctors' mixed in hospital names, because nothing filtered by COMPTYPE. Only 2 "
        "sample COMPTYPE values are confirmed so far ('L', 'RL') — the FULL set is NOT confirmed. "
        "MANDATORY, not optional: run SELECT DISTINCT COMPTYPE FROM mstorganisation FIRST, every "
        "time, before filtering by it for a 'doctors only' question — a real answer was already "
        "produced by guessing COMPTYPE='L' worked without checking, which happened to be right by "
        "luck, not verification; don't repeat that shortcut. Other real columns: ORGANISATIONCODE, "
        "CREDITLIMIT, CREDITPERIOD, ISCREDIT, ISINSURANCE, ACTIVE, LOCATIONID, ORGTypeID, CREATEDATE.",
        "- CRITICAL, confirmed real bug: 'top referring doctors' (or 'top' anything) means RANKED BY "
        "VOLUME/COUNT — how many referrals/procedures/bills that doctor is linked to — NOT sorted by "
        "CREATEDATE. A real query used 'ORDER BY CREATEDATE DESC' for 'top referring doctors', which "
        "answers 'most recently added doctor records', a completely different question from 'which "
        "doctors refer the most patients'. 'Top'/'most'/'highest' always means aggregate ranking "
        "(COUNT/SUM + GROUP BY + ORDER BY that count DESC), never recency, unless the question "
        "explicitly asks for recency ('most recently added').",
        "- CONFIRMED (AthenTech-given, real doctor-billing join): trninvlabpri.REFDOCTCODE = "
        "mstrefdoctor.DOCID — this is the real column linking a bill to its referring doctor. Use "
        "this for 'top referring doctors', 'doctor referral volume', 'doctor revenue' questions — "
        "join trninvlabpri to mstrefdoctor via REFDOCTCODE=DOCID, then GROUP BY the doctor and rank "
        "by COUNT/SUM as appropriate. Do NOT use mstorganisation/mstdoctor for this — mstrefdoctor "
        "via REFDOCTCODE is the confirmed real path.",
        "- always call describe_table before SELECT (never guess columns)",
        "- lists: SELECT TOP 10; totals: use SUM/COUNT/AVG over full filtered set (no TOP on aggregates)",
        "- filter by date + branch/location when asked (after you see real column names)",
        "- BANNED FOR LOCATIONS — mstlocationusers is a STAFF/USER ACCOUNTS table (real content: "
        "'DR.G.VIJAY RAMREDDY', 'KM', staff names), NOT a locations table, despite the name. It has "
        "repeatedly caused wrong answers by conflating staff records with actual locations, including "
        "in list-style questions ('which locations have billing records' returning staff names like "
        "'Ajay', 'Dr. Afnija' mixed with codes). NEVER query mstlocationusers for anything "
        "location-related — not for a specific lookup, not for a list of locations, not for any "
        "purpose. Use mstlocation instead every time (see next rule).",
        "- CONFIRMED (do not re-derive): mstlocation has BOTH the location NAME and its real "
        "LOCATIONID code (format 'LOC0X') together, in the same table (columns: LOCATIONID, "
        "LOCATIONNAME, ACTIVE). Use this for ALL location name-to-code resolution and for listing "
        "locations:\n"
        "    -- one specific location:\n"
        "    SELECT ... FROM trnmodeofcollectionsdet\n"
        "    WHERE LOCATIONID IN (SELECT DISTINCT LOCATIONID FROM mstlocation WHERE LOCATIONNAME LIKE '%Kompally%')\n"
        "    -- a list of active locations, WITH real names (not raw codes):\n"
        "    SELECT DISTINCT LOCATIONID, LOCATIONNAME FROM mstlocation WHERE ACTIVE = 1\n"
        "  Real sample rows confirmed: LOC01=Kompally, LOC02=Kukatpally, LOC03=Kokapet, LOC04=Jagtial, "
        "LOC10=Srikara-Boduppal.",
        "- CRITICAL — LOCATIONID vs location NAME are different things in OTHER tables too, do not "
        "confuse them: LOCATIONID (or similar *ID columns) holds a numeric/short CODE, NOT a name — "
        "LIKE-matching a name against an ID column will NEVER match anything. If a location filter "
        "returns 0 rows after resolving correctly via mstlocation, THEN it may be genuinely no "
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
        "- DEPTCODE is a DEPARTMENT, not a LOCATION — never search mstlocation.LOCATIONNAME for a "
        "department name (e.g. LOCATIONNAME LIKE '%Radiology%' is always wrong, Radiology is not a "
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
        "- CRITICAL, confirmed real bug: a 'highest growth' answer labeled a location 'Highest "
        "Growth' while its own displayed number showed ▼56.7% (a DECLINE). The underlying query only "
        "did GROUP BY location+month ORDER BY revenue DESC — that ranks by BIGGEST REVENUE, not "
        "biggest CHANGE, and growth% was never actually computed by the query at all. For a "
        "'growth'/'change'/'increase'/'decrease' question: you MUST compute "
        "(this_period - last_period) / last_period for EACH location separately (two real SUMs, one "
        "per period, per location), then rank by THAT computed value — never rank by raw revenue and "
        "call it growth, and never state a direction (▲/▼) or superlative ('highest') without the "
        "number actually supporting it — check your own computed number agrees with the word you're "
        "about to use before writing it.",
        "- CRITICAL, confirmed real bug: a 'patients with no follow-up' query used NOT EXISTS to find "
        "each patient's MOST RECENT bill — but every patient's most recent bill trivially has no "
        "LATER bill by definition, so this matched essentially all patients, not a meaningful "
        "subset. 'No follow-up' needs an explicit definition before writing SQL: e.g. 'exactly one "
        "bill ever' (COUNT(*) = 1 per UHID) or 'no second bill within N days of the first' — pick a "
        "concrete, stated definition and say what you used, don't silently return a query that "
        "doesn't structurally match the concept asked for.",
        "- CONFIRMED real bug: 'average revenue per patient' computed as AVG(PAIDAMOUNT) — that's the "
        "average PER TRANSACTION, not per patient (a patient with 5 small transactions is weighted "
        "differently than one with 1 large transaction). The correct calculation is "
        "SUM(PAIDAMOUNT) / COUNT(DISTINCT UHID) — always use this form for 'per patient' style "
        "averages, never a bare AVG() on the raw amount column.",
        "- CRITICAL, confirmed real bug: a doctor/billing query joined mstdoctor.DOCID = "
        "trnmodeofcollectionsdet.PATIENTID — a doctor ID joined directly to a PATIENT ID column, a "
        "fabricated join with no basis, plus a fabricated STATUS='Unpaid' value that was never "
        "confirmed to exist. It returned 0 rows, but for the wrong reason (nonsense query, not "
        "genuine absence) — do not treat a 0-row result as meaningful when the join/filter itself "
        "was invented. Use the CONFIRMED real join instead: trninvlabpri.REFDOCTCODE = "
        "mstrefdoctor.DOCID (see above) — do not go back to guessing mstdoctor.DOCID or any other "
        "unconfirmed doctor-billing link now that the real one is known.",
        "- CONFIRMED (do not re-derive): trninvlabdet.TESTSTATUS DOES include 'Sample Rejected' as a "
        "real value (see the full confirmed list above) — a 'test rejection rate' question is "
        "directly answerable via COUNT(CASE WHEN TESTSTATUS='Sample Rejected' THEN 1 END) / COUNT(*) "
        "GROUP BY test name. Do not claim no rejection tracking exists — that was a real confirmed "
        "mistake; the data is right there.",
        "- CRITICAL, confirmed real bug: a 'same test twice within 7 days' query did "
        "'MAX(BILLDATE) - MIN(BILLDATE) <= 7' — subtracting two DATETIME values directly does NOT "
        "reliably give you days in SQL Server, and produced an implausible result (883,002 patients "
        "— clearly wrong for a real repeat-test count). ALWAYS use DATEDIFF(DAY, start, end) <= 7 "
        "for a day-count comparison, never raw subtraction between two datetime columns — this "
        "applies to every date-difference calculation, not just this one query.",
        "- CRITICAL, confirmed real bug, SEPARATE from the one above (the DATEDIFF fix alone did NOT "
        "fix this): the same 'repeat test' query used 'WHERE TCODE IN (SELECT TCODE FROM ... GROUP "
        "BY UHID, TCODE HAVING ...)' — this only checks that the TEST CODE matches something in the "
        "repeat-list, NOT that it's the SAME PATIENT who repeated it. If even one patient repeats a "
        "common test, EVERY patient who ever had that same test even once gets wrongly counted too "
        "(confirmed: still produced 884,179, an implausible number, even after the DATEDIFF fix). "
        "For 'same patient did X within a time window' questions, the subquery/join MUST correlate "
        "on BOTH the patient identifier AND whatever else defines 'the same thing repeated' — never "
        "filter the outer query on only one of the two matched columns from a multi-column GROUP BY. "
        "Correct pattern: JOIN or EXISTS matching on UHID AND TCODE together, not TCODE alone.",
        "- CONFIRMED (real describe_table result): msttallyregledger has columns named 'Dr.Amt' and "
        "'Cr.Amt' — literal periods IN the column name. Writing SELECT Dr.Amt gets parsed as "
        "'table alias Dr, column Amt', not the real column — always bracket-quote these: "
        "SELECT [Dr.Amt], [Cr.Amt].",
        "- CONFIRMED (real row count checked): trnbillingcyclerates has ZERO rows — it is completely "
        "empty. A real 'no billing discrepancies found' answer was produced by comparing against "
        "this table, which was TRIVIALLY true (nothing to compare, not genuine confirmation that "
        "pricing is consistent) — a misleading answer even though the query itself was correct. "
        "NEVER present a comparison/discrepancy-check result as meaningful without confirming the "
        "reference table actually has rows first — if it's empty, say plainly 'no billing rate "
        "reference data is available to check against' instead of 'no discrepancies found', which "
        "implies a real check happened when it didn't.",
        "- CONFIRMED (real date range checked): trntemppatientrepeatevisits only covers "
        "LASTVISITDATE from 1 May 2026 to 2 July 2026 — a narrow ~2-month window, not a long "
        "history and not current either. This is a THIRD 'trntemp'-prefixed table confirmed to have "
        "a real data coverage gap (same naming pattern as trntempdaycollall and "
        "trntempabnormalreport, both already confirmed stale/limited too — treat any 'trntemp*' "
        "table as suspect until its real date range is checked). A 'retention'/'repeat visit' "
        "question spanning a WIDER window than May-July 2026 will silently undercount, since "
        "months outside that range have zero data here regardless of what really happened — do not "
        "trust a low retention/repeat number from this table without checking whether the "
        "question's date range fits entirely within May-July 2026 first.",
        "- GENERAL RULE, confirmed to have happened TWICE now (daycollection_mobileapp, "
        "trnbillingcyclerates): before presenting a 'no X found'/'no discrepancies'/'zero results' "
        "answer for a comparison or existence check against a specific table, verify that table "
        "actually has rows (or rows matching the broader filter, ignoring the specific condition "
        "being checked) — an empty or near-empty table produces a trivially-true zero that looks "
        "identical to a genuine, meaningful zero but means something completely different. State "
        "plainly when a table has no reference data to check against, rather than reporting a clean "
        "'no issues found' that implies a real check happened.",
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
        "final answer — that's a code, not a name a person can use. Resolve it via mstlocation "
        "(LOCATIONID, LOCATIONNAME — confirmed real, e.g. LOC01=Kompally, LOC04=Jagtial) — never "
        "mstlocationusers (banned) or trntempdaycollall (banned). If you truly cannot resolve it, "
        "say the location code plainly as a code (e.g. \"location code LOC04\") rather than "
        "presenting it as if it were already a name.",
        "- GENERAL RULE: your first query returning 0 rows is NOT automatically the final answer. You "
        "have room for several tool calls — use it. Before telling the user 'no data available', ask "
        "yourself what could be wrong with the query itself: wrong table (try another from the "
        "preferred list above), exact-match filter that should be LIKE, wrong date column, or a "
        "column name you guessed instead of confirming with describe_table. Try at least one genuinely "
        "different approach before concluding there's no data. Only report 'no data' after a real "
        "second attempt, not after one query that happened to return nothing.",
        "- CRITICAL, confirmed real bug: a 'best/worst performing branch' ranking labeled a location "
        "with ₹0 collection as 'Worst Performing' — treating a zero from NO RECORDED ACTIVITY as if "
        "it were a genuine low-performance data point. These are not the same thing: a branch with "
        "real transactions that happen to total low is a genuine 'worst performer'; a branch with "
        "ZERO rows at all (no data found, not even a zero-amount row) most likely reflects no "
        "activity recorded yet, a closed location that day, or a lag — not a fair comparison point. "
        "For 'best/worst'/ranking questions: exclude locations with GENUINELY ZERO ROWS (not just a "
        "zero SUM) from the ranking entirely, or list them separately as 'no data' rather than "
        "ranking them as 'worst'. Only compare locations that actually have real recorded activity "
        "for the period asked.",
        "- CRITICAL, confirmed real bug: 'which branch performed best/worst' (or any branch "
        "revenue/collection/performance ranking) used trnbranchissuedet (SUM(IssuedQty * Rate)) — "
        "this is a STOCK/INVENTORY ISSUANCE table, not revenue at all. 'Performance'/'collection'/"
        "'revenue' branch-ranking questions MUST use trnmodeofcollectionsdet (SUM(PAIDAMOUNT), "
        "resolved via mstlocation for the branch name) — the same confirmed table used everywhere "
        "else in this system for collections. Never substitute an inventory/stock table for a "
        "revenue question just because it also has a LOCATIONID-like column and a price field — "
        "check what the table actually represents (inventory movement vs money collected) before "
        "using it for a financial ranking.",
    ]

    if billing:
        lines.append("Billing/collection tables available to this role: " + ", ".join(billing))
    if preferred:
        lines.append("Preferred allowed tables: " + ", ".join(preferred[:25]))
        if len(preferred) > 25:
            lines.append(f"... and {len(preferred) - 25} more preferred matches")

    return "\n".join(lines)