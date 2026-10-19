-- Run in SSMS against ANY client's LIS database (Konnect, KonAcc, Centromed ...). Lists what the B2B assistant needs but this DB lacks.
-- Empty result = every B2B answer works for this client. Rows = those answers will fall back to the AI for that topic.
SET NOCOUNT ON;
DECLARE @need TABLE (t sysname, c sysname);
INSERT INTO @need VALUES
('mstOrganisation','ORGANISATIONCODE'),('mstOrganisation','ORGANISATIONNAME'),('mstOrganisation','CREDITLIMIT'),('mstOrganisation','ISCREDIT'),('mstOrganisation','CREDITPERIOD'),
('mstOrganisation','GRACEPERIOD'),('mstOrganisation','BILLINGCYCLE'),('mstOrganisation','STARTDATE'),('mstOrganisation','ENDDATE'),('mstOrganisation','ACTIVE'),
('mstOrganisation','GRADE'),('mstOrganisation','GRADEPERCENTAGE'),('mstOrganisation','CONTACTPERSON'),
('mstOrgInvestigationRates','INVCODE'),('mstOrgInvestigationRates','ORGCODE'),('mstOrgInvestigationRates','ACTIVE'),('mstOrgInvestigationRates','RATE'),('mstOrgInvestigationRates','IsPackage'),
('mstInvPackages','ORGCODE'),('mstInvPackages','PACKAGECODE'),('mstInvPackages','TESTCODE'),('mstInvPackages','PACKAGERATE'),('mstInvPackages','ACTIVE'),
('mstInvestigations','INVCODE'),('mstInvestigations','INVNAME'),('mstInvestigations','ShortName'),('mstInvestigations','SAMPLETYPE'),('mstInvestigations','TATTIME'),('mstInvestigations','TATTYPE'),
('mstInvestigations','REPTIME'),('mstInvestigations','REPTIMETYPE'),('mstInvestigations','PATIENTPROCEDURE'),('mstInvestigations','IsFasting'),('mstInvestigations','OUTSOURCEID'),
('mstInvestigations','ISPACKAGE'),('mstInvestigations','ACTIVE'),
('trnInvStatus','ID'),('trnInvStatus','BILLNO'),('trnInvStatus','TCODE'),('trnInvStatus','STATUS'),('trnInvStatus','SAMPLECOLLECTEDDATE'),('trnInvStatus','ACKNOWLEDGEDDATE'),
('trnInvStatus','RESULTENTRYDATE'),('trnInvStatus','AUTHENTICATEDATE'),
('trnSampleLogisAcknow','BILLNO'),('trnSampleLogisAcknow','INVCODE'),('trnSampleLogisAcknow','SAMPLETYPE'),('trnSampleLogisAcknow','REASON'),('trnSampleLogisAcknow','REMARKS'),('trnSampleLogisAcknow','ACKDATE'),
('mstRejectReason','REJECTID'),('mstRejectReason','REJECTDESC'),
('trnInvoiceGeneration','INVOICENO'),('trnInvoiceGeneration','INVOICENODT'),('trnInvoiceGeneration','ORGCODE'),('trnInvoiceGeneration','FromDate'),('trnInvoiceGeneration','ToDate'),
('trnInvoiceGeneration','TotAmt'),('trnInvoiceGeneration','PaidAmt'),('trnInvoiceGeneration','DueAmt'),
('trnDelCreditBill','BILLNO'),('trnDelCreditBill','ORGCODE'),('trnDelCreditBill','RATE'),('trnDelCreditBill','REASON'),('trnDelCreditBill','DELETEDATE'),
('trnCompPayments','CompPayID'),('trnCompPayments','ORGCODE'),('trnCompPayments','PayDate'),('trnCompPayments','PaidAmt'),('trnCompPayments','BalAmt'),('trnCompPayments','Concession'),
('trnCompPayments','TDS'),('trnCompPayments','Mode'),('trnCompPayments','Active'),
('trnINVLABPRI','BILLNO'),('trnINVLABPRI','BILLDATE'),('trnINVLABPRI','ORGANISATIONCODE'),('trnINVLABPRI','TOTALCHARGES'),('trnINVLABPRI','LocationId'),
('trnINVLABDET','BILLNO'),('mstlocation','LOCATIONID'),('mstlocation','LOCATIONNAME');
SELECT n.t AS [table], CASE WHEN o.object_id IS NULL THEN '(whole table missing)' ELSE n.c END AS [missing]
FROM @need n
LEFT JOIN sys.objects o ON o.name = n.t AND o.type = 'U'
LEFT JOIN sys.columns c ON c.object_id = o.object_id AND c.name = n.c
WHERE o.object_id IS NULL OR c.column_id IS NULL
GROUP BY n.t, CASE WHEN o.object_id IS NULL THEN '(whole table missing)' ELSE n.c END
ORDER BY n.t;
