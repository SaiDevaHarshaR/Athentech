"""
Real (not no-op) role-based table access control for SQL run by the agent.

Two problems this replaces:
1. The old check did naive substring matching on the raw SQL text, which
   both false-positives (a column named `pharmacy_notes` would trip the
   `pharmacy` table block) and false-negatives (it never actually enforced
   anything for the MSSQL path — the check body was just `pass`).
2. There was no mapping between logical categories ("labs", "pharmacy", ...)
   and the real Sahasra/KonnectLIS physical table names.

Fill in REAL_TABLE_TO_CATEGORY as you learn the actual Sahasra schema.
Any table found in a query that is NOT in this map is denied by default —
safer than silently allowing unknown tables through.
"""

import re
from typing import Set

from auth.roles import Role, get_allowed_tables

# Map: physical table name (lowercase, no schema prefix/brackets) -> logical category.
# Logical categories must match the ones used in auth/roles.py's ROLE_PERMISSIONS
# ("patients", "admissions", "labs", "pharmacy", "wards", "prescriptions",
#  "doctors", "staff", "billing", "inventory").
#
# Populate this as the real Sahasra/KonnectLIS schema is confirmed. Anything
# not listed here is denied by default (see check_query_access below).
#
# IMPORTANT: "KonnectLIS" = Lab Information System. This DB looks like it's
# specifically the lab module, not a full hospital schema — table names
# like mstMethod, mstAntibiotics, mstWorkStations are lab-specific concepts.
# Confirm with AthenTech whether admissions/pharmacy/wards live in a
# separate database before assuming those categories apply here at all.
REAL_TABLE_TO_CATEGORY = {
    # --- demo/SQLite schema ---
    "patients": "patients",
    "admissions": "admissions",

    # --- known real table names, confidence noted ---
    # TODO: confirm all of these against actual Sahasra/KonnectLIS docs or DBA.
    "mstpatientregistration": "patients",       # confident
    "tblclientdocinfo": "patients",             # confident-ish: "client" = patient docs
    "trnmergeddocbilldtls_referral": "billing", # confident-ish: "bill" in the name
    "trnpurchaseorder": "inventory",            # confident: procurement
    "mstlocationusers": "staff",                # confident-ish: users tied to a location

    "trninvoicepayments": "billing",            # confident: payments
    "mstmethod": "labs",                        # confident: lab test methodology
    "mstantibiotics": "labs",                   # likely: used in AST/culture-sensitivity testing
    "mstworkstations": "labs",                  # guess: lab equipment/stations — could also be "inventory"

    # --- admissions (auto-classified, keyword-verified) ---
    "mstappbookingno": "admissions",  # booking number definitions
    "mstappbookingslots": "admissions",  # booking slot schedule

    # --- billing (auto-classified, keyword-verified) ---
    "cc_invoice": "billing",  # invoice records
    "cc_invoicenew": "billing",  # invoice records
    "daycollection_mobileapp": "billing",  # daily collection summary
    "mstappadditionalcharges": "billing",  # additional charge definitions
    "mstccinvestigationrates": "billing",  # pricing for investigations
    "mstdocdeptinvdiscount": "billing",  # invoice discount
    "mstheaderpaytype": "billing",  # payment type header
    "mstinvoicesliptext": "billing",  # invoice slip text
    "mstmemplanswiseadditionalcharges": "billing",  # additional charges
    "mstorgdeptdiscount": "billing",  # department discount rates
    "mstpaymentdetails": "billing",  # payment transaction records
    "msttallyledgermaster": "billing",  # ledger master
    "msttallyledgertypeinfo": "billing",  # ledger type info
    "msttallyregledger": "billing",  # ledger entries
    "msttariffupdations": "billing",  # tariff updates
    "msttariffupdations_storecproc": "billing",  # tariff updates
    "msttempapppaymentdtls": "billing",  # payment details
    "msttemptallyregledger": "billing",  # ledger entries
    "paymentgatewayresponse": "billing",  # payment transaction data
    "tarifftable": "billing",  # tariff rates for services
    "tblappagentassignbill": "billing",  # bill assignment to agent
    "tblapprepocharges": "billing",  # repository charge definitions
    "tblcreditperiodgen": "billing",  # credit period
    "tblinvoicesms": "billing",  # invoice and SMS details
    "tbltempledger": "billing",  # ledger totals
    "tbltempledgerorg": "billing",  # org ledger totals
    "trnacntvoupaymntmodeofcolctndetails": "billing",  # payment mode details
    "trnbillingcycleinvoicegeneration": "billing",  # invoice generation cycle
    "trnbillingcyclerates": "billing",  # billing rates
    "trncc_cshcrypayments": "billing",  # payment records (retry)
    "trncc_cshcrypaymodedetails": "billing",  # payment mode details (retry)
    "trnccinvoicegeneration": "billing",  # invoice generation (retry)
    "trnccpayments": "billing",  # company payments (retry)
    "trnccpayments1": "billing",  # payment summary (retry)
    "trnccpaymodedetails": "billing",  # payment mode info (retry)
    "trncomppayments": "billing",  # company payments (retry)
    "trncomppaymentsrenova": "billing",  # company payments (retry)
    "trncomppaymodedetails": "billing",  # payment mode details
    "trncrbillno": "billing",  # credit bill
    "trncreditsales": "billing",  # credit sales
    "trndelcreditbill": "billing",  # deleted credit bill
    "trnexecutivecashpayment": "billing",  # cash payment transaction (retry)
    "trnexecutivedenomination": "billing",  # cash denomination record (retry)
    "trnhvadditionalcharges": "billing",  # additional charges (retry)
    "trninvoicegeneration": "billing",  # invoice creation data
    "trninvoicetestlog": "billing",  # invoice test log entries
    "trninvpaydetails": "billing",  # invoice payment details
    "trnmergeddocbilldtls": "billing",  # merged document billing
    "trnmodeofcollectionsdet": "billing",  # collection mode details
    "trnpaymntgtacknowledgement": "billing",  # payment acknowledgement record
    "trnpaymodechangelog": "billing",  # payment mode change log
    "trnreferalmgmtbilldtls": "billing",  # referral bill details
    "trnreferalmgmtbilldtls_del": "billing",  # deleted referral bill details
    "trnreferalpartialpayments": "billing",  # partial payments
    "trnreferalpartialpayments_del": "billing",  # deleted partial payments
    "trnreferalpayments": "billing",  # referral payments
    "trnreferalpayments_del": "billing",  # deleted referral payments
    "trnrejbillscancellationlog": "billing",  # rejected bill cancellation log
    "trntariffupdate": "billing",  # tariff update (retry)
    "trntempbranchwisecoll": "billing",  # branch collection summary (retry)
    "trntempdaycollall": "billing",  # daily collection summary (retry)
    "trntempmoncoll": "billing",  # billing monetary collection (retry)
    "trntemprejbills": "billing",  # billing rejected bills (retry)
    "trntempshiftcollecrpt": "billing",  # billing shift collection (retry)
    "trntrackcreditamts": "billing",  # billing credit tracking (retry)
    "trntrackcreditamts_new": "billing",  # credit amount tracking (retry)

    # --- doctors (auto-classified, keyword-verified) ---
    "mstccrefdoctor": "doctors",  # doctor reference
    "mstdoctor": "doctors",  # doctor master
    "mstdoctornew": "doctors",  # doctor master
    "mstdoctorslab": "doctors",  # doctor fee slab
    "mstmapauthdoc": "doctors",  # auth doc mapping
    "mstmapsubauthdoc": "doctors",  # sub auth doc mapping
    "mstrefdocclinicinfo": "doctors",  # clinic info for docs
    "mstrefdoctor": "doctors",  # doctor master data
    "mstrefdoctornew": "doctors",  # doctor master data
    "mstreferalcontacts": "doctors",  # referral contact list
    "mstreferralgroup": "doctors",  # referral group info
    "mstschedule": "doctors",  # doctor schedule slots
    "mstspecialization": "doctors",  # doctor specialization lookup
    "msttimings": "doctors",  # doctor schedule
    "tbltimings": "doctors",  # doctor slot timings
    "trndoctorweeklyoffs": "doctors",  # doctor off days (retry)
    "trnmergeddoctors": "doctors",  # merged doctor records

    # --- inventory (auto-classified, keyword-verified) ---
    "ecomratevsaipl": "inventory",  # price list
    "kompprice": "inventory",  # price list
    "konnectstock": "inventory",  # stock levels
    "leela": "inventory",  # price list
    "mdata": "inventory",  # price list
    "mstappdiseaseinvdtls": "inventory",  # disease inventory details
    "mstconsumptionmaster": "inventory",  # item consumption master
    "mstdis_inv_insert": "inventory",  # inventory insert log
    "mstinvconsumables": "inventory",  # consumable inventory
    "mstinvinventorymap": "inventory",  # inventory mapping
    "mstinvpackages2": "inventory",  # package rates for lab tests
    "mstinvpackageslog": "inventory",  # log of package rates
    "mstinvprecautions": "inventory",  # precautions for inventory items
    "mstinvprecautionslog": "inventory",  # log of inventory precautions
    "mstinvscheduledet": "inventory",  # schedule for inventory items
    "mstitemdeptaccess": "inventory",  # department access to items
    "mstitems": "inventory",  # master list of items
    "mstitemsr": "inventory",  # alternate item list
    "mstitemsubunit": "inventory",  # sub-unit definitions
    "mstitemtraymap": "inventory",  # tray mapping for items
    "mstitemtype": "inventory",  # item type definitions
    "mstitemunit": "inventory",  # unit definitions
    "mstitemunitmapping": "inventory",  # unit mapping
    "mstmachine": "inventory",  # machine inventory
    "mstmachineinvmethodmap": "inventory",  # machine to method mapping
    "mstmachinemaster": "inventory",  # machine master data
    "mstmachinemethodmap": "inventory",  # maps machines to methods
    "mstmachineorg": "inventory",  # machine tariff info
    "mstmachineparameters": "inventory",  # machine parameters
    "mstmachineparameters1": "inventory",  # duplicate machine parameters
    "mstmanufacturers": "inventory",  # manufacturer details
    "mstmedrack": "inventory",  # medication rack
    "mstmedtray": "inventory",  # medication tray
    "mstoutsourceinvmapping": "inventory",  # outsourced inventory mapping
    "mstrack": "inventory",  # storage rack info
    "mstrolroqdeptmapping": "inventory",  # item to department mapping with reorder levels
    "mststoressubdepartment": "inventory",  # store subdepartment mapping
    "mstsubitemtype": "inventory",  # item type master
    "mstsuppliers": "inventory",  # supplier master
    "mstsuppliersregistration": "inventory",  # supplier registration
    "msttempappinvdtls": "inventory",  # temp inventory details
    "msttray": "inventory",  # inventory tray
    "mstunits": "inventory",  # unit master
    "mstuom": "inventory",  # UOM master
    "mstuommapping": "inventory",  # UOM mapping
    "newtariff2019": "inventory",  # inventory tariff data
    "priceupdate": "inventory",  # price update for inventory items
    "priceupdatelog": "inventory",  # log of inventory price changes
    "rackmaster": "inventory",  # rack master for inventory
    "setinventorytypes": "inventory",  # inventory type definitions
    "surendra": "inventory",  # inventory item details
    "tblinvcodes": "inventory",  # inventory codes and rates
    "tblinvtemplates": "inventory",  # inventory templates
    "tblpoinddtls": "inventory",  # purchase order details
    "tblpoindmst": "inventory",  # purchase order master
    "tblshipmentdtls": "inventory",  # shipment details
    "tblshipmentmst": "inventory",  # shipment master
    "trnbranchindentdet": "inventory",  # branch requisition details
    "trnbranchindentpri": "inventory",  # branch requisition primary
    "trnbranchissuedet": "inventory",  # item issue details
    "trnbranchissuepri": "inventory",  # item issue primary
    "trnbranchreturndet": "inventory",  # item return details
    "trnbranchreturnpri": "inventory",  # item return primary
    "trncompmodificationlog": "inventory",  # inventory modification log (retry)
    "trnconsignment": "inventory",  # consignment inventory
    "trnconsignmentdtls": "inventory",  # consignment details
    "trnconsumtiondetails": "inventory",  # item consumption
    "trndailyconsumptiondtls": "inventory",  # daily consumption
    "trndeptconsumptiondet": "inventory",  # department consumption
    "trndeptconsumptionpri": "inventory",  # department consumption header
    "trnformdeptinvmapping": "inventory",  # inventory mapping (retry)
    "trnforminvdeduction": "inventory",  # inventory deduction (retry)
    "trngrnconcession": "inventory",  # GRN concession (retry)
    "trngrndetails": "inventory",  # goods received detail (retry)
    "trngrndetails26feb2020": "inventory",  # GRN details (retry)
    "trngrnfreeqtydetails": "inventory",  # free quantity details (retry)
    "trngrnmaster": "inventory",  # grn master record (retry)
    "trngrnreturns": "inventory",  # grn return master (retry)
    "trngrnreturnsdetails": "inventory",  # grn return detail (retry)
    "trngrntandc": "inventory",  # grn terms conditions (retry)
    "trninventoryconsumption": "inventory",  # inventory consumption (retry)
    "trninventsupplierpaymts": "inventory",  # supplier payments (retry)
    "trnitemtrack": "inventory",  # inventory item tracking
    "trnopeningstock": "inventory",  # opening stock
    "trnpofreeqtydetails": "inventory",  # purchase order free quantity details
    "trnpotandc": "inventory",  # purchase order terms & conditions
    "trnpotermsconditions": "inventory",  # purchase order terms details
    "trnpurchase": "inventory",  # purchase transaction record
    "trnpurchaseorderdtls": "inventory",  # purchase order line items
    "trnpurchaseorderpendingdtls": "inventory",  # pending purchase order lines
    "trnpurchasereturndetails": "inventory",  # purchase return line details
    "trnpurchasereturns": "inventory",  # purchase return header
    "trnpurcpaymnt": "inventory",  # purchase payment record
    "trnpurcpaymntmodeofcolctndetails": "inventory",  # purchase payment collection details
    "trnpurcretpaymntmodeofcolctndetails": "inventory",  # purchase return payment details
    "trnquotation": "inventory",  # quotation header
    "trnquotationdetails": "inventory",  # quotation line items
    "trnquotationfreeqtydetails": "inventory",  # quotation free quantity details
    "trnquotationtandc": "inventory",  # quotation terms & conditions
    "trnquotationtermsconditions": "inventory",  # quotation terms details
    "trnrefgroupinvmapping": "inventory",  # group to inventory mapping
    "trnstock": "inventory",  # stock inventory (retry)
    "trnstock26feb2020": "inventory",  # stock details (retry)
    "trnstockinvconsumption": "inventory",  # stock consumption (retry)
    "trnstocktransfer": "inventory",  # stock transfer (retry)
    "trnstoresledger": "inventory",  # stores ledger (retry)
    "trnstoresmodeofcollectionsdet": "inventory",  # collection mode (retry)
    "trntempinvdet": "inventory",  # inventory detail (retry)

    # --- labs (auto-classified, keyword-verified) ---
    "mstbnprospec": "labs",  # lab test specifications
    "mstccinvpackages": "labs",  # grouping of lab tests
    "mstinvdisease": "labs",  # disease-test mapping
    "mstinvestigationapi": "labs",  # investigation API mapping
    "mstinvestigationconcform": "labs",  # investigation form details
    "mstinvestigationmapping": "labs",  # investigation mapping
    "mstinvestigations": "labs",  # main investigations list
    "mstinvestigationsclubbed": "labs",  # clubbed investigations
    "mstinvestigationsdtls": "labs",  # investigation details
    "mstinvestigationsdtls2019": "labs",  # investigation details 2019
    "mstinvestigationsdtls_pricelog": "labs",  # investigation price log
    "mstinvestigationsdtlsexport": "labs",  # exported investigation details
    "mstinvestigationsdtlslog": "labs",  # investigation details log
    "mstinvestigationsexport": "labs",  # exported investigations
    "mstinvestigationslog": "labs",  # investigation log
    "mstinvpackages": "labs",  # test package catalog
    "mstlabdesc": "labs",  # lab test description
    "mstlabdescshine": "labs",  # lab test description (shine)
    "mstlabdesctemp": "labs",  # lab test description temp
    "mstlabmachine": "labs",  # lab machine details
    "mstlabmachine1": "labs",  # lab machine details (duplicate)
    "mstoltestparamsmapping": "labs",  # maps lab test parameters
    "mstorganismtype": "labs",  # microbiology organism types
    "mstorginvestigationrates": "labs",  # lab investigation rates
    "mstorginvestigationrates1": "labs",  # lab investigation rates
    "mstorginvestigationrates2": "labs",  # lab investigation rates
    "mstorginvestigationrates3": "labs",  # lab investigation rates
    "mstorginvestigationrateslogistics": "labs",  # lab rates logistics
    "mstparametercalculation": "labs",  # parameter calculation rules
    "mstparameterhead": "labs",  # parameter head definitions
    "mstparametertemplate": "labs",  # parameter templates
    "mstparametertemplatelog": "labs",  # parameter template logs
    "mstsampletype": "labs",  # sample type lookup
    "radlabs": "labs",  # lab test rates
    "rajesh_pack": "labs",  # test package details
    "sampletypes": "labs",  # sample type definitions
    "tbla15uploadeddata": "labs",  # uploaded lab test data
    "tblappcart": "labs",  # test cart details
    "tbleqpresults": "labs",  # lab results
    "tbleqpresults1": "labs",  # lab results
    "tblvitrosuploadeddata": "labs",  # lab test uploads
    "traymaster": "labs",  # tray for sample handling
    "trn_samplelogisacknow": "labs",  # sample logistics acknowledgement
    "trn_samplelogisdet": "labs",  # sample logistics details
    "trn_samplelogispri": "labs",  # sample logistics primary
    "trnappsampletracking": "labs",  # sample tracking
    "trnauthdeletiontrack": "labs",  # result entry deletion tracking
    "trnbarcodenomodification": "labs",  # sample barcode changes
    "trncc_clubbed": "labs",  # clubbed lab requests
    "trncc_clubbedparamresult": "labs",  # clubbed param results
    "trncc_clubbedparamresults": "labs",  # clubbed param results mapping
    "trncc_descresult": "labs",  # lab description result (retry)
    "trncc_invlabdet": "labs",  # lab test details (retry)
    "trncc_invstatus": "labs",  # lab status updates (retry)
    "trncc_paramresult": "labs",  # parameter results (retry)
    "trncc_samplelogisacknow": "labs",  # sample acknowledgement (retry)
    "trncc_samplelogisdet": "labs",  # sample logistics details (retry)
    "trncc_samplelogispri": "labs",  # sample logistics primary (retry)
    "trncomptempinvlabpri": "labs",  # lab invoice header
    "trncomptemplabinvdetails": "labs",  # lab invoice details
    "trndescresult": "labs",  # lab result description (retry)
    "trndescresult_audit1": "labs",  # audit description result (retry)
    "trndescresultfiles": "labs",  # result files (retry)
    "trndifferentialcount": "labs",  # lab differential count (retry)
    "trnevolkolab": "labs",  # lab upload status (retry)
    "trnevolkoresults": "labs",  # lab result files (retry)
    "trninvlabdet": "labs",  # lab test billing (retry)
    "trninvlabdetloc16": "labs",  # lab bill detail record
    "trninvlabpri": "labs",  # lab priority info
    "trninvlabprisweeja": "labs",  # lab priority record
    "trnlabreceipts": "labs",  # lab receipt records
    "trnlifeberries": "labs",  # lab bill detail record
    "trnlifeberriespri": "labs",  # lab priority info
    "trnolapilogdtls": "labs",  # lab sample log
    "trnolreportslogdtls": "labs",  # lab report log
    "trnolstatuslogdtls": "labs",  # lab status log
    "trnoutsrcsamplesdtls": "labs",  # outsourced samples
    "trnoutsrcsamplespri": "labs",  # outsourced samples
    "trnparamresult": "labs",  # lab results
    "trnparamunitsloc1": "labs",  # parameter units for lab tests
    "trnpatientresultstemp": "labs",  # temporary patient test results
    "trnrclresponsepkgdtls": "labs",  # lab package response details
    "trnrclresponsestatus": "labs",  # lab response status
    "trnresultwithheld": "labs",  # withheld lab results
    "trnsamplelogisacknow": "labs",  # sample logistics acknowledgement
    "trnsamplelogisdet": "labs",  # sample logistics details
    "trnsamplelogispri": "labs",  # sample logistics primary
    "trnstatustracking": "labs",  # sample status tracking
    "trntempabnormalreport": "labs",  # lab abnormal report (retry)
    "trntempautoauthentication": "labs",  # lab auto authentication (retry)
    "trntempinvlabpri": "labs",  # lab invoice patient data (retry)
    "trntempinvstatus": "labs",  # lab invoice status (retry)
    "trntemplabinvdetails": "labs",  # lab invoice details (retry)

    # --- patients (auto-classified, keyword-verified) ---
    "mstpatientgetdata": "patients",  # patient messaging data
    "mstpatientsourcegetdata": "patients",  # patient source info
    "tbl_patientcalldata": "patients",  # patient call information
    "tblappdeviceregistration": "patients",  # patient device registration
    "trntemppatientrepeatevisits": "patients",  # patient repeat visits (retry)

    # --- pharmacy (auto-classified, keyword-verified) ---
    "mstgeneric": "pharmacy",  # generic drug catalog
    "trndeptpharmaindentdet": "pharmacy",  # pharmacy indent details
    "trndeptpharmaindentpri": "pharmacy",  # pharmacy indent header
    "trndeptpharmaissuedet": "pharmacy",  # pharmacy issue details
    "trndeptpharmaissuedet26feb2020": "pharmacy",  # pharmacy issue details
    "trndeptpharmaissuepri": "pharmacy",  # pharmacy issue header
    "trndeptpharmareturndet": "pharmacy",  # pharmacy return details
    "trndeptpharmareturndet26feb2020": "pharmacy",  # pharmacy return details
    "trndeptpharmareturnpri": "pharmacy",  # pharmacy return header
    "trnoutwards": "pharmacy",  # drug outwards

    # --- staff (auto-classified, keyword-verified) ---
    "mstagentleaves": "staff",  # staff leave records
    "mstagentmaster": "staff",  # staff master
    "mstappagentareamapping": "staff",  # agent area assignments
    "mstappagentassigndispatchorders": "staff",  # agent dispatch assignments
    "mstappagentleaves": "staff",  # agent leave records
    "mstappagentstatus": "staff",  # agent status tracking
    "mstappbms": "staff",  # branch manager info
    "mstdesignation": "staff",  # staff role lookup
    "mstempadvances": "staff",  # employee advance
    "mstempexpenditure": "staff",  # employee expense
    "mstempleaves": "staff",  # employee leave
    "mstempmapping_asm": "staff",  # user-employee mapping
    "mstempmapping_gm": "staff",  # user-employee mapping
    "mstempmapping_rsm": "staff",  # user-employee mapping
    "mstempplans": "staff",  # employee plan
    "mstempschedules": "staff",  # employee schedule
    "mstemptarget": "staff",  # employee target
    "mstemptasks": "staff",  # employee task
    "mstmaptechdoc": "staff",  # tech authorization mapping
    "mstreferencesource": "staff",  # source reference for staff
    "mstrejectreason": "staff",  # rejection reason lookup
    "mstrouteboy": "staff",  # personnel for sample transport
    "mstshifts": "staff",  # shift schedule
    "tbl_callusers": "staff",  # user account information
    "tblagentappdeviceregistration": "staff",  # agent device registration
    "tblappagentnotification": "staff",  # agent notifications
    "tblmobileappreg": "staff",  # user registration
    "trnccusermapping": "staff",  # user mapping (retry)
    "trncertificates": "staff",  # employee certificates (retry)
    "trndeptcomplaint": "staff",  # inter-department complaint
    "trnempmapping": "staff",  # employee mapping (retry)
    "trnrouteboymarkmapping": "staff",  # route boy mapping

    # --- ambiguous / likely system config, not patient data ---
    # Left unmapped on purpose (denied by default) until confirmed:
    # "mstappdocuments" — looks like a doc-type reference table, not patient data
    # "mstroles" — looks like application-level roles, not a clinical category
}

_IDENTIFIER = r"\[?[a-zA-Z_][a-zA-Z0-9_]*\]?(?:\.\[?[a-zA-Z_][a-zA-Z0-9_]*\]?)*"
_TABLE_REF_RE = re.compile(
    rf"\b(?:FROM|JOIN)\s+({_IDENTIFIER})",
    re.IGNORECASE,
)


def extract_tables(sql: str) -> Set[str]:
    """
    Pull table identifiers following FROM/JOIN out of a SQL query.
    Strips brackets and schema/db prefixes (e.g. [dbo].[MstPatient] -> mstpatient).
    This is intentionally simple (regex, not a full SQL parser) — good enough
    to gate table-level access, not a substitute for a real SQL parser if the
    query surface grows more complex.
    """
    tables = set()
    for match in _TABLE_REF_RE.finditer(sql):
        raw = match.group(1)
        # Take the last dotted segment (strips schema/db prefixes like dbo. or db.dbo.)
        last_part = raw.split(".")[-1]
        cleaned = last_part.strip("[]").lower()
        if cleaned:
            tables.add(cleaned)
    return tables


def check_table_access(role: Role, table_name: str) -> tuple[bool, str]:
    """
    Same access rule as check_query_access, but for a single bare table
    name rather than a full SQL query — used by the describe_table tool
    so the agent can't fish for column names on tables it can't query.
    """
    cleaned = table_name.strip().strip("[]").lower()
    cleaned = cleaned.split(".")[-1]  # strip schema prefix if given

    category = REAL_TABLE_TO_CATEGORY.get(cleaned)
    if category is None:
        return False, (
            f"Access denied: table '{cleaned}' is not recognized. "
            "Add it to REAL_TABLE_TO_CATEGORY in auth/table_access.py "
            "once its data category is confirmed."
        )
    if category not in get_allowed_tables(role):
        return False, f"Access denied: your role ({role.value}) cannot access '{cleaned}' ({category})."

    return True, cleaned


def list_allowed_tables_for_role(role: Role) -> list:
    """
    Real (physical) table names this role is allowed to touch, based on
    REAL_TABLE_TO_CATEGORY. Used to tell the LLM what actually exists
    for it to query, without dumping the entire schema into the prompt.
    """
    allowed_categories = get_allowed_tables(role)
    return sorted(
        table for table, category in REAL_TABLE_TO_CATEGORY.items()
        if category in allowed_categories
    )


def check_query_access(role: Role, sql: str) -> tuple[bool, str]:
    """
    Returns (allowed, reason). Denies by default if a table can't be
    mapped to a known logical category — better to under-serve than to
    leak a table nobody explicitly allowed.
    """
    allowed_categories = get_allowed_tables(role)
    tables = extract_tables(sql)

    for table in tables:
        category = REAL_TABLE_TO_CATEGORY.get(table)
        if category is None:
            return False, (
                f"Access denied: table '{table}' is not recognized. "
                "Add it to REAL_TABLE_TO_CATEGORY in auth/table_access.py "
                "once its data category is confirmed."
            )
        if category not in allowed_categories:
            return False, f"Access denied: your role ({role.value}) cannot access '{table}' ({category})."

    return True, ""