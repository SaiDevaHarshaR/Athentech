from database.connection import get_hospital_connection

c = get_hospital_connection(
    "H023-CentromedLIS",
    "cs2.athentech.in,52434",
    "lisapp_prod",
    "Proc_Amrpp#2981J#@!",
)

cur = c.cursor()

with open("centromed_financial_schema.txt", "w", encoding="utf-8") as f:

    # 1. Tables/views with financial-looking names
    cur.execute("""
    SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE
    FROM INFORMATION_SCHEMA.TABLES
    WHERE
        TABLE_NAME LIKE '%bill%'
        OR TABLE_NAME LIKE '%payment%'
        OR TABLE_NAME LIKE '%collection%'
        OR TABLE_NAME LIKE '%receipt%'
        OR TABLE_NAME LIKE '%revenue%'
        OR TABLE_NAME LIKE '%amount%'
        OR TABLE_NAME LIKE '%invoice%'
        OR TABLE_NAME LIKE '%transaction%'
        OR TABLE_NAME LIKE '%refund%'
        OR TABLE_NAME LIKE '%discount%'
        OR TABLE_NAME LIKE '%concession%'
        OR TABLE_NAME LIKE '%cash%'
        OR TABLE_NAME LIKE '%charge%'
        OR TABLE_NAME LIKE '%due%'
    ORDER BY TABLE_SCHEMA, TABLE_NAME
    """)

    tables = cur.fetchall()

    f.write("========== FINANCIAL TABLES ==========\n")
    for r in tables:
        f.write(f"{r[0]}.{r[1]} | {r[2]}\n")

    # 2. Financial-looking columns across the DB
    cur.execute("""
    SELECT
        TABLE_SCHEMA,
        TABLE_NAME,
        COLUMN_NAME,
        DATA_TYPE,
        CHARACTER_MAXIMUM_LENGTH,
        NUMERIC_PRECISION,
        NUMERIC_SCALE
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE
        COLUMN_NAME LIKE '%amount%'
        OR COLUMN_NAME LIKE '%paid%'
        OR COLUMN_NAME LIKE '%total%'
        OR COLUMN_NAME LIKE '%due%'
        OR COLUMN_NAME LIKE '%balance%'
        OR COLUMN_NAME LIKE '%discount%'
        OR COLUMN_NAME LIKE '%concession%'
        OR COLUMN_NAME LIKE '%charge%'
        OR COLUMN_NAME LIKE '%price%'
        OR COLUMN_NAME LIKE '%rate%'
        OR COLUMN_NAME LIKE '%tax%'
        OR COLUMN_NAME LIKE '%gst%'
        OR COLUMN_NAME LIKE '%payment%'
        OR COLUMN_NAME LIKE '%collection%'
        OR COLUMN_NAME LIKE '%refund%'
        OR COLUMN_NAME LIKE '%revenue%'
        OR COLUMN_NAME LIKE '%bill%'
    ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION
    """)

    columns = cur.fetchall()

    f.write("\n========== FINANCIAL COLUMNS ==========\n")
    for r in columns:
        f.write(
            f"{r[0]}.{r[1]}.{r[2]} | "
            f"type={r[3]} | max={r[4]} | "
            f"precision={r[5]} | scale={r[6]}\n"
        )

    # 3. Detailed data for the most important known collection table
    f.write("\n========== trnMODEOFCOLLECTIONSDET ==========\n")

    cur.execute("""
    SELECT COLUMN_NAME, DATA_TYPE
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = 'trnMODEOFCOLLECTIONSDET'
    ORDER BY ORDINAL_POSITION
    """)

    for r in cur.fetchall():
        f.write(f"{r[0]} | {r[1]}\n")

    cur.execute("""
    SELECT TOP 100 *
    FROM trnMODEOFCOLLECTIONSDET
    ORDER BY DATEOFBILL DESC
    """)

    rows = cur.fetchall()
    f.write("\n--- SAMPLE ROWS ---\n")
    f.write(str([d[0] for d in cur.description]) + "\n")

    for r in rows:
        f.write(str(tuple(r)) + "\n")

    # 4. Aggregate financial behavior
    f.write("\n========== COLLECTION AGGREGATES ==========\n")

    cur.execute("""
    SELECT
        MODE,
        TYPE,
        STATUS,
        LOCATIONID,
        COUNT(*) AS CNT,
        SUM(TOTALAMOUNT) AS TOTAL_AMOUNT,
        SUM(PAIDAMOUNT) AS PAID_AMOUNT,
        SUM(DUEAMOUNT) AS DUE_AMOUNT,
        SUM(CONCESSIONAMOUNT) AS CONCESSION_AMOUNT,
        SUM(REGAMOUNT) AS REG_AMOUNT
    FROM trnMODEOFCOLLECTIONSDET
    WHERE DATEOFBILL >= DATEADD(day, -7, CAST(GETDATE() AS date))
    GROUP BY MODE, TYPE, STATUS, LOCATIONID
    ORDER BY LOCATIONID, MODE, TYPE, STATUS
    """)

    f.write(
        "MODE | TYPE | STATUS | LOCATION | COUNT | "
        "TOTAL | PAID | DUE | CONCESSION | REG\n"
    )

    for r in cur.fetchall():
        f.write(str(tuple(r)) + "\n")

c.close()

print("DONE")
print("Created: centromed_financial_schema.txt")
