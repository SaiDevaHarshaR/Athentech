"""
Reviewed join hints used by describe_table.
Only include joins you trust. Wrong joins are worse than none.

mstlocationusers joins were removed from the original bulk-discovered
set (286 of them) — confirmed this session to be a STAFF/USER table,
not a locations table (real content: doctor/staff names). Every join
pointing at it was wrong. The remaining bulk-discovered joins (58,
not proven wrong but not independently verified either) were kept.
AthenTech-confirmed relationships (department/sub-department,
financial chain, investigation chain) are merged in on top and
take priority for any table appearing in both sets.
"""

REAL_TABLE_RELATIONSHIPS = {
    "mstappdiseaseinvdtls": [("DiseaseId", "mstinvdisease", "ID")],
    "mstempplans": [("PlanId", "mstmemplanswiseadditionalcharges", "ID")],
    "mstinvestigations": [("OUTSOURCEID", "mstoutsourceinvmapping", "ID"), ("INVCODE", "mstinvestigationsdtls", "INVCODE"), ("INVCODE", "mstorginvestigationrates", "INVCODE"), ("CREATEUSERID", "mstinvestigationsdtls", "CREATEUSERID"), ("CREATEUSERID", "mstorginvestigationrates", "CREATEUSERID"), ("CREATEUSERID", "mstinvpackages", "CREATEUSERID"), ("LOCATIONID", "mstinvestigationsdtls", "LOCATIONID"), ("LOCATIONID", "mstorginvestigationrates", "LOCATIONID"), ("LOCATIONID", "mstinvpackages", "LOCATIONID")],
    "mstinvestigationsclubbed": [("OUTSOURCEID", "mstoutsourceinvmapping", "ID")],
    "mstinvestigationsdtls": [("INVCODE", "mstorginvestigationrates", "INVCODE")],
    "mstinvestigationsexport": [("OUTSOURCEID", "mstoutsourceinvmapping", "ID")],
    "mstinvestigationslog": [("OUTSOURCEID", "mstoutsourceinvmapping", "ID")],
    "mstmapauthdoc": [("SPECIALIZATIONID", "mstspecialization", "ID")],
    "mstmapsubauthdoc": [("SPECIALIZATIONID", "mstspecialization", "ID")],
    "mstmemplanswiseadditionalcharges": [("ChargeID", "mstappadditionalcharges", "ID")],
    "mstoltestparamsmapping": [("HEADERID", "mstheaderpaytype", "ID")],
    "mstparametertemplate": [("HEADERID", "mstheaderpaytype", "ID")],
    "mstparametertemplatelog": [("HEADERID", "mstheaderpaytype", "ID")],
    "mstpaymentdetails": [("OrderId", "mstappagentassigndispatchorders", "ID")],
    "mstrefdoctor": [("GROUPID", "mstreferralgroup", "ID")],
    "mstreferralgroup": [("GROUPID", "trnrefgroupinvmapping", "ID")],
    "mstrouteboy": [("RouteBoyID", "trnrouteboymarkmapping", "ID")],
    "mstsubdepartment": [("DEPARTMENTID", "mstdepartment", "DEPARTMENTID"), ("LOCATIONID", "mstdepartment", "LocationID")],
    "msttallyregledger": [("AutoId", "trntempautoauthentication", "ID")],
    "msttempappinvdtls": [("OrderId", "mstappagentassigndispatchorders", "ID")],
    "msttempapppaymentdtls": [("OrderId", "mstappagentassigndispatchorders", "ID")],
    "msttemptallyregledger": [("AutoId", "trntempautoauthentication", "ID")],
    "msttimings": [("SlotId", "mstappbookingslots", "ID")],
    "mstuom": [("UOMID", "mstuommapping", "ID")],
    "mstuommapping": [("UOMID", "mstuom", "ID")],
    "priceupdatelog": [("PRICEUPDATEID", "priceupdate", "ID")],
    "tblagentappdeviceregistration": [("deviceRegId", "tblappdeviceregistration", "id")],
    "tblappagentassignbill": [("areaId", "mstappagentareamapping", "id")],
    "tblappdeviceregistration": [("deviceRegId", "tblagentappdeviceregistration", "id")],
    "tbltimings": [("SlotId", "mstappbookingslots", "ID")],
    "trnappsampletracking": [("TrackingId", "trnstatustracking", "ID")],
    "trncc_paramresult": [("HEADERID", "mstheaderpaytype", "ID")],
    "trncomppaymodedetails": [("TRANSID", "trnstocktransfer", "ID")],
    "trndailyconsumptiondtls": [("WORKSTATIONID", "mstworkstations", "ID")],
    "trndeptconsumptionpri": [("WorkStationID", "mstworkstations", "ID")],
    "trnexecutivecashpayment": [("TransId", "trnstocktransfer", "ID")],
    "trnexecutivedenomination": [("TransId", "trnstocktransfer", "ID")],
    "trnformdeptinvmapping": [("FormID", "mstinvestigationconcform", "ID")],
    "trnforminvdeduction": [("WorkStationID", "mstworkstations", "ID")],
    "trngrnreturnsdetails": [("GrnRetId", "trngrnreturns", "ID")],
    "trninventoryconsumption": [("WorkStationID", "mstworkstations", "ID"), ("ConsumptionId", "mstconsumptionmaster", "ID")],
    "trninvlabdet": [("PATID", "mstpatientregistration", "ID"), ("BILLNO", "trninvlabpri", "BILLNO"), ("UHID", "trninvlabpri", "UHID")],
    "trninvlabdetloc16": [("PATID", "mstpatientregistration", "ID")],
    "trninvlabpri": [("PATIENTID", "mstpatientregistration", "ID")],
    "trninvlabprisweeja": [("PATIENTID", "mstpatientregistration", "ID")],
    "trninvoicepayments": [("TRANSID", "trnstocktransfer", "ID")],
    "trninvstatus": [("BILLNO", "trninvlabdet", "BILLNO"), ("BILLNO", "trninvlabpri", "BILLNO"), ("UHID", "trninvlabdet", "UHID"), ("UHID", "trninvlabpri", "UHID")],
    "trnlifeberries": [("PATID", "mstpatientregistration", "ID")],
    "trnlifeberriespri": [("PATIENTID", "mstpatientregistration", "ID")],
    "trnmodeofcollections": [("PATIENTID", "mstpatientregistration", "ID")],
    "trnmodeofcollectionsdet": [("PATIENTID", "mstpatientregistration", "ID"), ("BILLNO", "trninvstatus", "BILLNO"), ("BILLNO", "trninvlabdet", "BILLNO"), ("BILLNO", "trninvlabpri", "BILLNO"), ("UHID", "trninvstatus", "UHID"), ("UHID", "trninvlabdet", "UHID"), ("UHID", "trninvlabpri", "UHID")],
    "trnoutsrcsamplesdtls": [("OutSourceId", "mstoutsourceinvmapping", "ID")],
    "trnoutsrcsamplespri": [("OutSourceId", "mstoutsourceinvmapping", "ID")],
    "trnparamresult": [("HEADERID", "mstheaderpaytype", "ID"), ("OrganismTypeID", "mstorganismtype", "ID")],
    "trnpatientresultstemp": [("AutoID", "trntempautoauthentication", "ID")],
    "trnrefgroupinvmapping": [("GROUPID", "mstreferralgroup", "ID")],
    "trnrouteboymarkmapping": [("RouteBoyID", "mstrouteboy", "ID")],
    "trntempinvstatus": [("PATIENTID", "mstpatientregistration", "ID")],
    "trntempmoncoll": [("CASHPAID", "trnexecutivecashpayment", "ID")],
}


def get_relationships_for_table(table_name: str) -> list:
    """Returns [(column, joins_to_table, joins_to_column), ...] or []."""
    return REAL_TABLE_RELATIONSHIPS.get(table_name.strip().lower(), [])