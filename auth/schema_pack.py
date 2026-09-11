"""
Verified high-value tables for premium answers. Keep tight, confirmed only.
"""

CORE_PATIENT_TABLES = ["mstpatientregistration"]

CONFIRMED_TABLES_FROM_ATHENTECH = [
    "trninvlabpri", "trninvstatus", "mstlocation", "mstsubdepartment",
    "mstinvestigationsdtls", "mstorginvestigationrates", "mstinvpackages",
    "trnparameter", "mstorganisation",
]

KNOWN_OPERATIONAL_TABLES = [
    "mstpatientregistration", "tblclientdocinfo", "mstlocation",
    "trnmodeofcollectionsdet", "trnmodeofcollections", "trninvoicepayments",
    "mstpaymentdetails", "trninvpaydetails", "trnccpayments", "trnccpaymodedetails",
    "trncomppaymodedetails", "trnacntvoupaymntmodeofcolctndetails",
    "trninvoicegeneration", "trnmergeddocbilldtls", "trnmergeddocbilldtls_referral",
    "cc_invoice", "trninvlabdet", "trninvlabpri", "trnparamresult", "mstinvestigations",
    "mstdoctor", "mstrefdoctor", "mstlocationusers", "mstworkstations",
    "trnpurchaseorder", "trnstock",
]

BILLING_COLLECTION_PRIORITY = [
    "trnmodeofcollectionsdet", "trninvoicepayments", "mstpaymentdetails",
]


def schema_hint_for_prompt(allowed_tables: list) -> str:
    allowed = set(allowed_tables or [])
    preferred = [t for t in KNOWN_OPERATIONAL_TABLES if t in allowed]
    billing = [t for t in BILLING_COLLECTION_PRIORITY if t in allowed]

    lines = [
        "CONFIRMED FACTS — treat as verified, do not re-derive:",
        "BANNED: trntemp*-tables, trnbillingcyclerates (0 rows), "
        "daycollection_mobileapp (LOCATIONID/DATE always NULL), mstlocationusers "
        "(staff, not locations). Find another table or say unavailable.",
        "Don't filter mstorganisation.COMPTYPE for doctors (untrusted) — use "
        "mstrefdoctor join instead (see Doctors below).",
        "Location: mstlocation(LOCATIONID,LOCATIONNAME,ACTIVE). LOC01=Kompally, "
        "LOC02=Kukatpally, LOC03=Kokapet, LOC04=Jagtial, LOC10=Srikara-Boduppal. "
        "Always resolve LOC0X codes to names in the final answer. "
        "get_verified_day_collection needs ONE location, never 'all' — for "
        "all-locations use run_sql_query with no location filter.",
        "trnmodeofcollectionsdet cols: MODE,PAIDAMOUNT,TOTALAMOUNT,"
        "CONCESSIONAMOUNT,DUEAMOUNT,DATEOFBILL,UHID,LOCATIONID,TYPE,BILLNO,"
        "PATIENTID,STATUS('P'=paid,'R'=refund),PREVIOUSBILLNO. MODE: "
        "Cash/CHEQUE/CONCESSION/CREDITCARD/DD/online/UPI (casing inconsistent, "
        "GROUP BY UPPER(LTRIM(RTRIM(MODE)))). TYPE: 'DUE PAYMENT'/"
        "'LabConcession2'/'LabRefund'/'Membership'/'OPLAB'. Live/current table, "
        "prefer over banned trntemp tables.",
        "'Cash In Hand'/reconciliation logic lives ONLY in stored procedure "
        "dbo.LabDayCollection — not reconstructable from raw tables. Use "
        "get_lab_day_collection tool. SINGLE-DAY ONLY — for a broader period, "
        "state that plainly and name the date used, never silently narrow scope.",
        "Test lookup: SELECT * FROM mstInvestigations WHERE INVNAME LIKE '%X%'. "
        "Lay/short names rarely match real INVNAME ('Urinalysis'→'Complete "
        "Urine Analysis (CUE)'; 'MRI'/'CT'/'X-Ray' exact match fails, use LIKE). "
        "Always broaden LIKE and check DISTINCT INVNAME before concluding zero. "
        "For standalone-vs-package: a combo has multiple names joined by '/' or "
        "',' — read each row, don't assume.",
        "trninvlabdet.DEPTCODE is numeric → mstsubdepartment (up to 80+, use IN "
        "not =) for specific depts, or mstdepartment (9 rows) for broad terms. "
        "mstlabdesc is empty, never use. Radiology = SubDept 33,80 only (78 is "
        "'Radiology Store', inventory, exclude). 'Completed radiology' = "
        "trninvstatus.STATUS='Authenticated' via BILLNO, not TESTSTATUS. "
        "mstInvestigations.DEPARTMENTID does NOT match mstsubdepartment — no "
        "real lookup confirmed, don't filter by it.",
        "trninvlabdet.TESTSTATUS: '',Acknowledged,Cancelled,Pending,Registered,"
        "Result Entry,Sample Collected,Sample Rejected — NO 'Completed'. Use "
        "Result Entry/Acknowledged as closest equivalent. trninvstatus.STATUS "
        "(more authoritative): Registered→Sample Collected→Acknowledged→"
        "Authenticated(reached doctor, not necessarily final)→Cancelled/"
        "Refunded/Sample Rejected — no value means universally 'done', state "
        "which stage you counted. Any STATUS/TYPE/MODE column: never assume an "
        "English value, SELECT DISTINCT first if unseen.",
        "trnparamresult.PVALUE is text: numeric-string (compare MINVALUE/"
        "MAXVALUE after TRY_CAST) or narrative (MIN/MAX NULL, no abnormal check "
        "possible). Interpretation = culture-sensitivity only, not general "
        "abnormal flag. Patient results join: trnINVLABDET(BILLNO,BILLDATE,"
        "TCODE)→trnINVLABPRI(BILLNO,Name/Phone)→mstInvestigations(TCODE="
        "INVCODE,INVNAME)→trnParamResult(BILLNO,results).",
        "mstorganisation mixes doctors+hospitals, don't use for doctors-only. "
        "Real doctor-billing join: trninvlabpri.REFDOCTCODE=mstrefdoctor.DOCID "
        "— never invent mstdoctor.DOCID=PATIENTID. 'Top'/'most' = ranked by "
        "volume/COUNT/SUM, never CREATEDATE/recency.",
        "Never compare DATEPART(x,GETDATE()) to a hardcoded year/month — filter "
        "the real date column instead. 'Growth' = COMPUTED "
        "(this-last)/last per entity, never raw-revenue ranking; verify "
        "direction (▲/▼) matches the number. 'No follow-up' needs an explicit "
        "definition (NOT EXISTS on latest bill matches everyone trivially) — "
        "state which definition used. Per-patient average = SUM/"
        "COUNT(DISTINCT UHID), never bare AVG(). Date diffs: DATEDIFF(DAY,a,b), "
        "never raw subtraction. Multi-column correlation (e.g. UHID+TCODE) must "
        "match ALL columns together, not just one from a multi-col GROUP BY.",
        "'TAT compliance'/'% within SLA'/'below X%' questions: use the "
        "check_tat_alert or get_tat_compliance_dashboard TOOL, never compute "
        "from raw SQL. The 10080-minute bound below is an OUTLIER-EXCLUSION "
        "safety limit for a plain average, NOT a real SLA — it has nothing to "
        "do with compliance %. Real compliance = per-test TATTIME/TATTYPE (the "
        "tool handles this) vs actual TAT, never a fixed 7-day window.",
        "Plain 'average TAT' (no compliance/SLA/threshold wording): ONLY "
        "trnparamresult.BILLDATE→CREATEDATE (trninvlabdet has no "
        "CREATEDATE; never REFUNDDATE). Bound outliers INSIDE AVG's CASE WHEN "
        "(never WHERE), CAST BIGINT: AVG(CAST(CASE WHEN DATEDIFF(MINUTE,"
        "BILLDATE,CREATEDATE) BETWEEN 0 AND 10080 THEN DATEDIFF(MINUTE,"
        "BILLDATE,CREATEDATE) END AS BIGINT)).",
        "'Best/worst': ZERO ROWS ≠ zero sum, likely no data, exclude or list "
        "separately. Branch revenue ranking uses trnmodeofcollectionsdet, never "
        "inventory tables. 0-row result ≠ final answer, try another table "
        "first. Empty reference table → 'no X found' is misleading. "
        "TESTSTATUS DOES include 'Sample Rejected', rejection-rate is answerable.",
        "always call describe_table before SELECT (never guess columns)",
        "lists: SELECT TOP 10; totals: SUM/COUNT/AVG over full filtered set",
        "filter by date + branch/location when asked, after seeing real columns",
        "if table/metric not allowed or unclear: say not available, never invent numbers",
    ]

    if billing:
        lines.append("Billing/collection tables available: " + ", ".join(billing))
    if preferred:
        lines.append("Preferred allowed tables: " + ", ".join(preferred[:12]))
        if len(preferred) > 12:
            lines.append(f"... and {len(preferred) - 12} more")

    return "\n".join(lines)