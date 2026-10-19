-- READ-ONLY (SELECT only). Run in SSMS against one client's LIS database. Finds where that lab keeps its CLIENTS (organisations / companies /
-- B2B customers), what columns they have, and whether they hold data. Paste the 5 result grids back.
SET NOCOUNT ON;

-- 1) Tables whose NAME looks client / organisation related (with row counts)
SELECT t.name AS table_name, SUM(p.rows) AS row_count
FROM sys.tables t JOIN sys.partitions p ON p.object_id = t.object_id AND p.index_id IN (0,1)
WHERE t.name LIKE '%org%' OR t.name LIKE '%client%' OR t.name LIKE '%compan%' OR t.name LIKE '%corp%' OR t.name LIKE '%party%'
   OR t.name LIKE '%b2b%' OR t.name LIKE '%customer%' OR t.name LIKE '%institut%' OR t.name LIKE '%tpa%' OR t.name LIKE '%insur%'
   OR t.name LIKE '%credit%' OR t.name LIKE '%invoice%' OR t.name LIKE '%rate%' OR t.name LIKE '%contract%'
GROUP BY t.name ORDER BY SUM(p.rows) DESC, t.name;

-- 2) Tables that CARRY a client/organisation column (these are the per-client transaction tables), with row counts
SELECT c.TABLE_NAME AS table_name, STRING_AGG(c.COLUMN_NAME, ', ') AS org_like_columns, MAX(r.row_count) AS row_count
FROM INFORMATION_SCHEMA.COLUMNS c
JOIN (SELECT t.name, SUM(p.rows) AS row_count FROM sys.tables t JOIN sys.partitions p ON p.object_id = t.object_id AND p.index_id IN (0,1) GROUP BY t.name) r
  ON r.name = c.TABLE_NAME
WHERE c.COLUMN_NAME LIKE '%ORG%' OR c.COLUMN_NAME LIKE '%CLIENT%' OR c.COLUMN_NAME LIKE '%COMPANY%' OR c.COLUMN_NAME LIKE '%CORP%'
   OR c.COLUMN_NAME LIKE '%PARTY%' OR c.COLUMN_NAME LIKE '%CUSTOMER%' OR c.COLUMN_NAME LIKE '%TPA%'
GROUP BY c.TABLE_NAME ORDER BY MAX(r.row_count) DESC, c.TABLE_NAME;

-- 3) Full column list (schema) of every table found in 1) or 2)
SELECT c.TABLE_NAME, c.ORDINAL_POSITION AS pos, c.COLUMN_NAME, c.DATA_TYPE, c.CHARACTER_MAXIMUM_LENGTH AS len, c.IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS c
WHERE c.TABLE_NAME IN (
  SELECT t.name FROM sys.tables t WHERE t.name LIKE '%org%' OR t.name LIKE '%client%' OR t.name LIKE '%compan%' OR t.name LIKE '%corp%' OR t.name LIKE '%party%'
     OR t.name LIKE '%b2b%' OR t.name LIKE '%customer%' OR t.name LIKE '%tpa%' OR t.name LIKE '%invoice%' OR t.name LIKE '%contract%'
  UNION
  SELECT TABLE_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE COLUMN_NAME LIKE '%ORGANISATIONCODE%' OR COLUMN_NAME LIKE '%ORGCODE%' OR COLUMN_NAME LIKE '%CLIENTCODE%')
ORDER BY c.TABLE_NAME, c.ORDINAL_POSITION;

-- 4) The client master (Sahasra: mstOrganisation): how many clients, how many active, how many billed in the last 90 days
IF OBJECT_ID('mstOrganisation','U') IS NOT NULL
SELECT COUNT(*) AS total_clients, SUM(CASE WHEN ACTIVE = 1 THEN 1 ELSE 0 END) AS active_clients,
       (SELECT COUNT(DISTINCT p.ORGANISATIONCODE) FROM trnINVLABPRI p WHERE p.BILLDATE >= DATEADD(day,-90,GETDATE()) AND p.ORGANISATIONCODE IS NOT NULL AND p.ORGANISATIONCODE <> '') AS clients_billed_90d
FROM mstOrganisation;

-- 5) Top 25 clients by bills in the last 90 days (name, code, bills, billed value) - shows real data exists per client
IF OBJECT_ID('mstOrganisation','U') IS NOT NULL AND OBJECT_ID('trnINVLABPRI','U') IS NOT NULL
SELECT TOP 25 p.ORGANISATIONCODE AS org_code, o.ORGANISATIONNAME AS org_name, COUNT(DISTINCT p.BILLNO) AS bills_90d,
       CAST(SUM(ISNULL(p.TOTALCHARGES,0)) AS DECIMAL(18,2)) AS billed_90d
FROM trnINVLABPRI p LEFT JOIN mstOrganisation o ON o.ORGANISATIONCODE COLLATE DATABASE_DEFAULT = p.ORGANISATIONCODE COLLATE DATABASE_DEFAULT
WHERE p.BILLDATE >= DATEADD(day,-90,GETDATE()) AND p.ORGANISATIONCODE IS NOT NULL AND p.ORGANISATIONCODE <> ''
GROUP BY p.ORGANISATIONCODE, o.ORGANISATIONNAME ORDER BY COUNT(DISTINCT p.BILLNO) DESC;
