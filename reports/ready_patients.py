"""Premium Smart Report helpers (READ-ONLY): list patients whose results are authenticated, and build a report for one bill.
Used when UHID is blank (e.g. Centromed): the identifier is 'BILL:<billno>'."""
import re
from database.connection import get_hospital_connection

_BILL_OK = re.compile(r"^[A-Za-z0-9_\-/]{3,40}$")


def list_ready(db_name, db_server=None, db_user=None, db_password=None, days=7, limit=30):
    days = max(1, min(int(days or 7), 60)); limit = max(1, min(int(limit or 30), 100))
    conn = get_hospital_connection(db_name, db_server, db_user, db_password)
    if not conn:
        raise ConnectionError("Could not connect to the hospital database.")
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT TOP {limit} P.BILLNO, MAX(P.Name) AS PNAME, MAX(P.BILLDATE) AS BDATE, COUNT(*) AS TOTAL, "
            "SUM(CASE WHEN LOWER(LTRIM(RTRIM(S.STATUS)))='authenticated' THEN 1 ELSE 0 END) AS READY "
            "FROM trnINVLABPRI P JOIN trnInvStatus S ON S.BILLNO = P.BILLNO "
            "WHERE P.BILLDATE >= DATEADD(day, -?, CAST(GETDATE() AS date)) "
            "GROUP BY P.BILLNO "
            "HAVING SUM(CASE WHEN LOWER(LTRIM(RTRIM(S.STATUS)))='authenticated' THEN 1 ELSE 0 END) > 0 "
            "ORDER BY MAX(P.BILLDATE) DESC, P.BILLNO DESC", (days,))
        out = []
        for r in cur.fetchall():
            out.append({"billno": str(r[0]).strip(), "name": str(r[1] or "").strip(),
                        "date": str(r[2])[:10], "total": int(r[3]), "ready": int(r[4])})
        return out
    finally:
        conn.close()


def _bill_data(billno, db_name, db_server, db_user, db_password):
    from reports.patient_report_generator import PatientNotFound
    if not _BILL_OK.match(billno or ""):
        raise PatientNotFound("Invalid bill number.")
    conn = get_hospital_connection(db_name, db_server, db_user, db_password)
    if not conn:
        raise ConnectionError("Could not connect to the hospital database.")
    try:
        cur = conn.cursor()
        cur.execute("SELECT TOP 1 * FROM trnINVLABPRI WHERE BILLNO = ?", (billno,))
        cols = [d[0] for d in cur.description]
        row = cur.fetchone()
        if not row:
            raise PatientNotFound("No bill " + billno)
        pri = dict(zip(cols, row))
        low = {k.lower(): v for k, v in pri.items()}
        def pick(*names):
            for n in names:
                v = low.get(n)
                if v not in (None, ""):
                    return v
            return "-no_data"
        info = {"patient_id": pick("patientid", "uhid") if pick("patientid", "uhid") != "-no_data" else billno,
                "uhid": pick("uhid"), "name": pick("name", "patientname"),
                "age": pick("age", "patientage"), "dob": "-no_data", "gender": pick("gender", "sex"),
                "registration_date": str(pick("billdate"))[:10]}
        cur.execute(
            "SELECT TOP 400 A.BILLNO, A.INVCODE, A.PARAMID, B.PARAMNAME, B.METHOD, A.PARAMHEADNAME, A.PVALUE, C.UNITDESC, "
            "A.MINVALUE, A.MAXVALUE, A.DESCRIPTION, A.ISBOLD, S.STATUS AS RESULT_STATUS "
            "FROM trnParamResult A LEFT JOIN trnParameter B ON A.PARAMID = B.PARAMID "
            "LEFT JOIN mstUNITS C ON A.UNITID = C.UNITID "
            "LEFT JOIN trnInvStatus S ON S.BILLNO = A.BILLNO AND S.TCODE = A.INVCODE "
            "WHERE A.BILLNO = ? AND A.PVALUE IS NOT NULL AND A.PVALUE <> '' ORDER BY A.HEADERID, A.mstPTID", (billno,))
        c2 = [d[0] for d in cur.description]
        rows = [dict(zip(c2, r)) for r in cur.fetchall()]
        rows = [r for r in rows if str(r.get("RESULT_STATUS") or "").strip().lower() == "authenticated"]
        return info, ({"trnparamresult": rows} if rows else {})
    finally:
        conn.close()


def build_any(identifier, db_name, role, hospital_name, llm, db_server=None, db_user=None, db_password=None):
    from reports import patient_report_generator as g
    ident = (identifier or "").strip()
    if not ident.upper().startswith("BILL:"):
        return g.build_patient_report_data(identifier, db_name, role, hospital_name, llm, db_server, db_user, db_password)
    info, raw = _bill_data(ident[5:].strip(), db_name, db_server, db_user, db_password)
    structured = g.generate_structured_report(info, raw, hospital_name, llm)
    structured.setdefault("patient_name", info.get("name"))
    structured.setdefault("patient_age", info.get("age"))
    structured.setdefault("patient_gender", info.get("gender"))
    structured["hospital_name"] = hospital_name
    structured["_has_lab_data"] = bool(raw.get("trnparamresult"))
    return structured
