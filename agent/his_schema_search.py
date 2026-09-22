"""
HIS equivalent of agent/schema_search.py's search_schema tool. LIS has
this already; HIS didn't, meaning a HIS question that doesn't already
name a specific table (e.g. "show me lab requests" instead of
"describe tblPatReqHdr") had no way to find the real table name.

Built from the confirmed reference table AthenTech's own developers
provided directly — real table names, real TTYPE codes, real
master/detail pairs. Not guessed, not reverse-engineered.
"""

from langchain_core.tools import tool

# (table_name, category, keywords, description) — keywords matched
# against the user's question, case-insensitively, substring match.
_HIS_SCHEMA = [
    ("tblpatinfo", "op", ["patient", "registration", "register"],
     "OP patient registration (TTYPE=4, filter on ENTRYDATE)"),
    ("tblOPRegistration", "op", ["consultation", "op registration", "opd"],
     "OP consultation (TTYPE=0, filter on REGDT)"),
    ("tblTransServicesMst", "op", ["procedure", "service", "services master"],
     "OP procedure/service master (TTYPE=3, filter on BILLDT)"),
    ("tblTransServicesDtls", "op", ["procedure detail", "service detail"],
     "OP procedure/service line items (TTYPE=3)"),
    ("tblOPPAYDTLS", "op", ["op payment", "op collection", "op paid"],
     "OP payment details (CONFIRMED: has BOTH BILLDT and DTPAID as separate real columns — "
     "likely bill date vs actual payment date, not the same thing; be explicit which one a "
     "question needs, e.g. 'when was this billed' vs 'when was this actually paid')"),
    ("tblOPConcessions", "op", ["op concession", "op discount"], "OP concessions"),
    ("tblOPRefunds", "op", ["op refund"], "OP refunds"),
    ("tblOPCancellation", "op", ["op cancel", "op cancellation", "cancelled patients", "cancellation"],
     "OP cancellations"),
    ("tblOPServices", "op", ["op services master", "service catalog"], "OP services master catalog"),

    ("tblIPRegistration", "ip", ["ip admission", "inpatient admission", "admitted"],
     "IP admission record (filter on REGDT)"),
    ("tblIpBedsDtl", "ip", ["bed allotment", "bed assignment"],
     "Bed allotment/assignment (filter on ALLOTDT)"),
    ("tblIPAdvances", "ip", ["ip advance"], "IP advances (TTYPE=0, filter on BILLDT)"),
    ("tblIPTransServicesMst", "ip", ["ip procedure", "ip service"],
     "IP procedure/service master (TTYPE=1, filter on BILLDT)"),
    ("tblIPFinalBillMst", "ip", ["ip final bill", "ip cash bill", "discharge bill"],
     "IP cash final bill MASTER — the bill record (ToalAmount, ADVANCEAMT, CONCAMT), NOT "
     "the payment/collection table. TTYPE=21, filter on BILLDT."),
    ("tblIPPAYDTLS", "ip", ["ip payment", "ip collection", "ip paid", "ip cash payment"],
     "IP actual PAYMENT table (CONFIRMED: AMTPAID, DTPAID, BILLDT, TTYPE — this is what "
     "ip_revenue actually queries for TTYPE=21, not tblIPFinalBillMst)"),
    ("tblIPCorpFinalBillMst", "ip", ["ip insurance bill", "ip corporate bill", "ip credit bill"],
     "IP insurance/corporate final bill master (TTYPE=25, filter on BILLDT)"),
    ("tblIPConcessions", "ip", ["ip concession"], "IP concessions (NOT for advances/admission)"),
    ("tblIPFinalRefunds", "ip", ["ip refund"], "IP refunds"),
    ("tblIPCancellation", "ip", ["ip cancel", "cancelled patients", "cancellation"], "IP cancellations"),
    ("tblIpBeds", "ip", ["bed master", "bed list", "total beds"], "Bed master"),
    ("tblIpRooms", "ip", ["room"], "Room master (CONFIRMED: ROOMID, ROOMNO, FLOORID, ROOMTYPEID, ACTIVE)"),
    ("tblIpRoomType", "ip", ["room type"], "Room type master (CONFIRMED: ROOMTYPEID, ROOMTYPE, RoomRent, isSingle, isDouble, IsOT)"),
    ("tblIPFloors", "ip", ["floor"], "Floor master (CONFIRMED: FLOORID, FLOORNO, ACTIVE)"),
    ("tblIPCorpAMTTRANS", "ip", ["ip insurance amount", "ip corporate amount"], "IP insurance/corporate amount transactions"),
    ("tblIPCorpConcessions", "ip", ["ip insurance concession", "ip corporate concession"],
     "IP insurance/corporate concessions (NOT for advances/admission)"),

    ("tblPatReqHdr", "lab", ["lab request", "investigation request", "test request"],
     "Lab request header (filter on REQDT)"),
    ("tblPatReqTransDet", "lab", ["lab request item", "investigation line"],
     "Lab request line items (filter on REQDT)"),
    ("tblAmountTrans", "lab", ["lab amount"], "Lab amount transactions"),
    ("tblPatReqPymtDet", "lab", ["lab payment"], "Lab payment details"),
    ("tblConcessions", "lab", ["lab concession"], "Lab concessions"),
    ("tblRefunds", "lab", ["lab refund"], "Lab refunds"),
    ("tblCancellation", "lab", ["lab cancel"], "Lab cancellations"),
    ("tblDept", "lab", ["department", "dept"], "Department (sub-level)"),
    ("tblMainDept", "lab", ["main department"], "Department (top level)"),
    ("tblInvMst", "lab", ["investigation master", "test master", "test catalog"],
     "Investigation/test master"),

    ("tblPharmPurchaseMst", "pharmacy", ["grn", "goods received", "pharmacy purchase"],
     "Pharmacy purchase/GRN master (CONFIRMED: PurchID, PurchDate, SupplierId, TOTALAMT, NETAMT, TTYPE=0)"),
    ("tblPharmSalesMst", "pharmacy", ["pharmacy sale", "op pharmacy sale", "medicine sale"],
     "OP pharmacy sales master (TTYPE=2, filter on SALEDT)"),
    ("tblPharmipSalesMst", "pharmacy", ["ip pharmacy sale", "ip medicine sale"],
     "IP pharmacy sales master (TTYPE=4, filter on SALEDT)"),
    ("tblPharmAmountTrans", "pharmacy", ["pharmacy amount", "pharmacy payment"],
     "Pharmacy amount transactions (filter on BILLDT)"),
    ("tblPharmDepts", "pharmacy", ["pharmacy department"], "Pharmacy department master"),
    ("tblPharmMedicines", "pharmacy", ["medicine master", "drug master"], "Medicine master catalog"),
    ("tblPharmDeptIssueMst", "pharmacy", ["pharmacy issue", "department issue"],
     "Inter-department pharmacy issue (filter on ISSUEDT)"),
    ("tblPharmDeptMedDtls", "pharmacy", ["stock", "low stock", "medicine stock", "inventory"],
     "Pharmacy stock (CONFIRMED via SSMS: MEDID, BATCHNO, CURRQTY, EXPDT — NO medicine name column, "
     "must JOIN tblPharmMedicines ON MEDID for the name. Reorder threshold is NOT here either — "
     "it's tblPharmMedicines.ROL (Reorder Level), joined the same way)"),
    ("tblPharmMedicines", "pharmacy", ["medicine master", "drug master", "reorder level"],
     "Medicine master (CONFIRMED: MEDNM, GENERICNM, ROL=Reorder Level, ROQ=Reorder Qty — "
     "join to tblPharmDeptMedDtls.MEDID for actual current stock quantity)"),
    ("tblPharmaTrack", "pharmacy", ["stock adjustment"], "Stock adjustments (separate from stock levels)"),

    ("tblHOSPDTLS", "general", ["branch", "location", "hospital list"], "Branch/location master (LCODE, LocName)"),
    ("tblDoctorInfo", "general", ["doctor"], "Doctor master"),
    ("tblDocAppointments", "general", ["appointment"], "Doctor appointments"),
    ("tblVoucherGeneration", "general", ["voucher", "expenditure", "expense"],
     "Expenditure vouchers (credit/debit, filter on VoucherDt)"),
    ("tblAccountHeader", "general", ["account header"], "Account header master (joins to vouchers)"),
]


@tool
def his_search_schema(query: str) -> str:
    """
    Search the confirmed HIS table reference by keyword, to find real
    table names before calling his_describe_table/his_run_sql_query.
    Built from a reference AthenTech's own developers provided
    directly, not guessed. Call this FIRST whenever a HIS question
    doesn't already name a specific tblXxx table.
    """
    q = query.lower()
    scored = []
    for table, category, keywords, desc in _HIS_SCHEMA:
        score = sum(1 for kw in keywords if kw in q)
        if table.lower() in q:
            score += 5  # exact table name mention, strong signal
        if score > 0:
            scored.append((score, table, category, desc))

    if not scored:
        return (
            f"No HIS tables matched '{query}' by keyword. This doesn't mean no "
            "data exists — this reference is not exhaustive. Try a different "
            "keyword, or use his_describe_table directly if you already suspect "
            "a real table name."
        )

    scored.sort(reverse=True)
    lines = [f"HIS tables relevant to '{query}', ranked by relevance:"]
    for score, table, category, desc in scored[:8]:
        lines.append(f"• {table} ({category}) — {desc}")
    return "\n".join(lines)