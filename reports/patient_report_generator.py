"""
Generates a genuinely patient-specific Smart Report — the actual feature
"Smart Report" implies: look up ONE real patient, gather whatever real
data exists about them, and have the LLM turn that real data into the
structured findings/action-plan/nutrition content the template expects.

This is different from generate_smart_report()'s content_lines fallback,
which just wraps whatever the last chat answer said (no fresh lookup,
no real per-patient grounding) — that fallback still exists for
non-patient-specific questions (e.g. "revenue this month"), but a
request naming a specific patient should go through THIS path instead.

Honest dependency: how RICH the output is depends on
auth/table_relationships.py's REAL_TABLE_RELATIONSHIPS being populated
(see discover_table_relationships.py). Until that's been run and
reviewed, this can still find and report real patient demographics
(name/age/gender/UHID), but won't have real lab/billing detail to build
genuine findings from — the LLM is explicitly instructed to say
"-no_data" for anything not backed by real retrieved data, not invent
plausible-sounding findings to fill the gaps.
"""

import json
import re

from database.connection import get_hospital_connection
from auth.table_relationships import REAL_TABLE_RELATIONSHIPS
from auth.table_access import REAL_TABLE_TO_CATEGORY
from auth.roles import Role, get_allowed_tables

PATIENT_TABLE = "mstpatientregistration"
MAX_ROWS_PER_RELATED_TABLE = 60


def _get_columns(conn, table_name: str) -> list:
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE LOWER(TABLE_NAME) = ? ORDER BY ORDINAL_POSITION",
        (table_name.lower(),)
    )
    return [row[0] for row in cursor.fetchall()]


def _find_column(columns: list, keywords: list, exclude: list = None) -> str:
    """
    Tries an EXACT match first (case-insensitive whole column name equals
    a keyword) — most reliable, no ambiguity. Only falls back to
    substring matching if nothing matched exactly, and even then skips
    anything containing an excluded word.

    The substring fallback is genuinely risky for short keywords: "age"
    is a substring of "package", "storage", "image", "message",
    "average", "coverage", "usage", "manage", "stage" — a real bug
    found in production where a PACKAGEID column got matched as a
    patient's age (a package ID number displayed as "929641 years").
    Callers should pass those as `exclude` for ambiguity-prone keywords.
    """
    exclude = exclude or []
    columns_lower = {c.lower(): c for c in columns}

    # Tier 1: exact match
    for kw in keywords:
        if kw in columns_lower:
            return columns_lower[kw]

    # Tier 2: substring match, skipping known false-positive containers
    for col in columns:
        lower = col.lower()
        if any(e in lower for e in exclude):
            continue
        if any(k in lower for k in keywords):
            return col

    return None


class PatientNotFound(Exception):
    pass


class PatientAmbiguous(Exception):
    def __init__(self, candidates):
        self.candidates = candidates
        super().__init__(f"{len(candidates)} matching patients found")


def find_patient(identifier: str, db_name: str, db_server: str = None, db_user: str = None, db_password: str = None) -> dict:
    """
    Looks up a patient by UHID (exact-ish match) or name (partial match)
    in the real patient table. Discovers the real column names live
    rather than assuming exact names/casing, same principle as
    describe_table.
    """
    conn = get_hospital_connection(db_name, db_server, db_user, db_password)
    if not conn:
        raise ConnectionError("Could not connect to the hospital database.")

    try:
        columns = _get_columns(conn, PATIENT_TABLE)
        if not columns:
            raise PatientNotFound(f"Could not find columns for {PATIENT_TABLE}.")

        id_col = _find_column(columns, ["id"], exclude=["uhid", "valid", "paid"]) or columns[0]
        uhid_col = _find_column(columns, ["uhid"])
        name_col = _find_column(columns, ["name", "patientname"], exclude=["username", "hospname", "hospitalname", "surname"])
        age_col = _find_column(
            columns, ["age", "patientage", "ageyrs", "age_years"],
            exclude=["package", "storage", "image", "message", "average", "coverage", "usage", "manage", "stage", "damage"]
        )
        dob_col = _find_column(columns, ["dob", "birth"])
        gender_col = _find_column(columns, ["gender", "sex"])
        reg_date_col = _find_column(columns, ["regdate", "registrationdate", "regdt"])

        print(f"[find_patient] Discovered columns: id={id_col}, uhid={uhid_col}, "
              f"name={name_col}, age={age_col}, dob={dob_col}, gender={gender_col}, reg_date={reg_date_col}")

        select_cols = [c for c in [id_col, uhid_col, name_col, age_col, dob_col, gender_col, reg_date_col] if c]

        identifier_clean = identifier.strip()
        cursor = conn.cursor()

        # Try UHID first if it looks like one and the column exists.
        if uhid_col and re.match(r"^[A-Za-z0-9]+$", identifier_clean):
            query = f"SELECT TOP 5 {', '.join(select_cols)} FROM {PATIENT_TABLE} WHERE {uhid_col} = ?"
            cursor.execute(query, (identifier_clean,))
            rows = cursor.fetchall()
            if rows:
                return _row_to_patient_dict(rows[0], select_cols, id_col, uhid_col, name_col, age_col, dob_col, gender_col, reg_date_col)

        # Fall back to name search.
        if name_col:
            query = f"SELECT TOP 5 {', '.join(select_cols)} FROM {PATIENT_TABLE} WHERE {name_col} LIKE ?"
            cursor.execute(query, (f"%{identifier_clean}%",))
            rows = cursor.fetchall()
            if len(rows) == 1:
                return _row_to_patient_dict(rows[0], select_cols, id_col, uhid_col, name_col, age_col, dob_col, gender_col, reg_date_col)
            if len(rows) > 1:
                candidates = [_row_to_patient_dict(r, select_cols, id_col, uhid_col, name_col, age_col, dob_col, gender_col, reg_date_col) for r in rows]
                raise PatientAmbiguous(candidates)

        raise PatientNotFound(f"No patient found matching '{identifier}'.")
    finally:
        conn.close()

def find_alternate_uhids(patient_name: str, canonical_uhid: str, db_name: str, db_server=None, db_user=None, db_password=None) -> list:
    if not patient_name:
        print("[find_alternate_uhids] No patient_name provided, skipping.")
        return []
    conn = get_hospital_connection(db_name, db_server, db_user, db_password)
    if not conn:
        print("[find_alternate_uhids] Could not connect, skipping.")
        return []
    try:
        cursor = conn.cursor()
        normalized_name = " ".join(patient_name.strip().upper().split())  # collapse extra whitespace
        cursor.execute(
            "SELECT DISTINCT UHID, Name FROM trninvlabpri WHERE UPPER(LTRIM(RTRIM(Name))) = ?",
            (normalized_name,),
        )
        rows = cursor.fetchall()
        print(f"[find_alternate_uhids] Searched trninvlabpri.Name LIKE '%{normalized_name}%': {len(rows)} row(s) — {rows}")
        alternates = [r[0] for r in rows if r[0] and r[0] != canonical_uhid]
        print(f"[find_alternate_uhids] {len(alternates)} alternate UHID(s) differ from canonical '{canonical_uhid}': {alternates}")
        return alternates
    except Exception as e:
        print(f"[find_alternate_uhids] Query failed (non-fatal): {e}")
        return []
    finally:
        conn.close()

def _row_to_patient_dict(row, select_cols, id_col, uhid_col, name_col, age_col, dob_col, gender_col, reg_date_col) -> dict:
    row_dict = dict(zip(select_cols, row))

    age_value = row_dict.get(age_col, "-no_data")
    # Safety net independent of the column-detection fix above: if
    # whatever landed here doesn't look like a plausible human age,
    # don't display it as one. Catches this class of bug even against a
    # schema we haven't seen, not just the specific PACKAGEID case found
    # in production.
    if isinstance(age_value, (int, float)) and not (0 <= age_value <= 130):
        print(f"[find_patient] WARNING: age value {age_value} from column '{age_col}' "
              f"is not a plausible age — showing -no_data instead. Check column detection.")
        age_value = "-no_data"

    return {
        "patient_id": row_dict.get(id_col),
        "uhid": row_dict.get(uhid_col, "-no_data"),
        "name": row_dict.get(name_col, "-no_data"),
        "age": age_value,
        "dob": row_dict.get(dob_col, "-no_data"),
        "gender": row_dict.get(gender_col, "-no_data"),
        "registration_date": row_dict.get(reg_date_col, "-no_data"),
    }


def gather_patient_data(patient_id, db_name: str, role: Role, db_server: str = None, db_user: str = None, db_password: str = None, uhid: str = None) -> dict:
    from auth.table_relationships import UHID_TABLE_RELATIONSHIPS

    allowed_categories = get_allowed_tables(role)
    conn = get_hospital_connection(db_name, db_server, db_user, db_password)
    if not conn:
        raise ConnectionError("Could not connect to the hospital database.")

    gathered = {}
    tables_checked = 0
    try:
        for table_name, relationships in REAL_TABLE_RELATIONSHIPS.items():
            category = REAL_TABLE_TO_CATEGORY.get(table_name)
            if category not in allowed_categories:
                continue

            for column, joins_to_table, joins_to_column in relationships:
                if joins_to_table != PATIENT_TABLE:
                    continue
                tables_checked += 1
                try:
                    cursor = conn.cursor()
                    order_col = "DATEOFBILL" if table_name == "trnmodeofcollectionsdet" else ("BILLDATE" if table_name in ("trninvlabdet", "trninvlabpri") else None)
                    order_clause = f" ORDER BY {order_col} DESC" if order_col else ""
                    query = f"SELECT TOP {MAX_ROWS_PER_RELATED_TABLE} * FROM {table_name} WHERE {column} = ?{order_clause}"
                    cursor.execute(query, (patient_id,))
                    col_names = [d[0] for d in cursor.description]
                    rows = cursor.fetchall()
                    print(f"[gather_patient_data] {table_name}.{column} = {patient_id}: {len(rows)} row(s)")
                    if rows:
                        gathered[table_name] = [dict(zip(col_names, r)) for r in rows]
                except Exception as e:
                    print(f"[gather_patient_data] {table_name}.{column} query FAILED (not just empty): {e}")
                    continue

            # UHID fallback — runs for THIS table_name, every iteration of
            # the outer loop, right after its ID-based check above.
            if uhid and table_name not in gathered and table_name in UHID_TABLE_RELATIONSHIPS:
                for column, joins_to_table, joins_to_column in UHID_TABLE_RELATIONSHIPS[table_name]:
                    tables_checked += 1
                    try:
                        cursor = conn.cursor()
                        order_col = "DATEOFBILL" if table_name == "trnmodeofcollectionsdet" else ("BILLDATE" if table_name in ("trninvlabdet", "trninvlabpri") else None)
                        order_clause = f" ORDER BY {order_col} DESC" if order_col else ""
                        query = f"SELECT TOP {MAX_ROWS_PER_RELATED_TABLE} * FROM {table_name} WHERE {column} = ?{order_clause}"
                        cursor.execute(query, (uhid,))
                        col_names = [d[0] for d in cursor.description]
                        rows = cursor.fetchall()
                        print(f"[gather_patient_data] (UHID fallback) {table_name}.{column} = {uhid}: {len(rows)} row(s)")
                        if rows:
                            gathered[table_name] = [dict(zip(col_names, r)) for r in rows]
                    except Exception as e:
                        print(f"[gather_patient_data] (UHID fallback) {table_name}.{column} query FAILED: {e}")
                        continue

        # 2-hop case, runs ONCE after the whole loop finishes (correct
        # placement — outside the loop, at the try block's level):
        # trnparamresult has no direct UHID, only BILLNO, reached via
        # trninvlabdet's BILLNOs (which the loop above should have found).
        if uhid and "trnparamresult" not in gathered and "trninvlabdet" in gathered:
            billnos = list({row.get("BILLNO") for row in gathered["trninvlabdet"] if row.get("BILLNO")})
            if billnos:
                try:
                    cursor = conn.cursor()
                    placeholders = ", ".join("?" for _ in billnos)
                    # Same source the lab's own report print uses (LabReportPrint / GetRptDtls1):
                    # trnParamResult + trnParameter (name, method) + mstUNITS (unit TEXT),
                    # and only tests whose trnInvStatus.STATUS is 'Authenticated' are released.
                    query = (
                        f"SELECT TOP {MAX_ROWS_PER_RELATED_TABLE} A.BILLNO, A.INVCODE, A.PARAMID, B.PARAMNAME, B.METHOD, "
                        f"A.PARAMHEADNAME, A.PVALUE, C.UNITDESC, A.MINVALUE, A.MAXVALUE, A.DESCRIPTION, A.ISBOLD, "
                        f"S.STATUS AS RESULT_STATUS "
                        f"FROM trnParamResult A "
                        f"LEFT JOIN trnParameter B ON A.PARAMID = B.PARAMID "
                        f"LEFT JOIN mstUNITS C ON A.UNITID = C.UNITID "
                        f"LEFT JOIN trnInvStatus S ON S.BILLNO = A.BILLNO AND S.TCODE = A.INVCODE "
                        f"WHERE A.BILLNO IN ({placeholders}) AND A.PVALUE IS NOT NULL AND A.PVALUE <> '' "
                        f"ORDER BY A.BILLNO, A.HEADERID, A.mstPTID"
                    )
                    cursor.execute(query, billnos)
                    col_names = [d[0] for d in cursor.description]
                    all_rows = [dict(zip(col_names, r)) for r in cursor.fetchall()]
                    rows = [r for r in all_rows if str(r.get("RESULT_STATUS") or "").strip().lower() == "authenticated"]
                    print(f"[gather_patient_data] (2-hop via trninvlabdet.BILLNO) trnParamResult: {len(all_rows)} row(s), "
                          f"{len(rows)} authenticated, {len(all_rows) - len(rows)} not yet authenticated (excluded)")
                    if rows:
                        gathered["trnparamresult"] = rows
                    else:
                        # Descriptive (text) reports live in trnDescResult, not trnParamResult — say so in the log.
                        try:
                            cursor.execute(f"SELECT COUNT(*) FROM trnDescResult WHERE BILLNO IN ({placeholders})", billnos)
                            print(f"[gather_patient_data] trnDescResult rows for these bills: {cursor.fetchone()[0]}")
                        except Exception as de:
                            print(f"[gather_patient_data] trnDescResult check failed: {de}")
                except Exception as e:
                    print(f"[gather_patient_data] (2-hop) trnparamresult query FAILED: {e}")
    finally:
        conn.close()

    print(f"[gather_patient_data] Checked {tables_checked} table(s) for patient_id={patient_id}/uhid={uhid}, "
          f"found real data in {len(gathered)} of them.")

    return gathered

def _parse_llm_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    return json.loads(cleaned)


def _bind_for_report(llm):
    """
    Raise the output limit for the long JSON report. `reasoning_effort` is
    only valid on reasoning models (Groq gpt-oss, OpenAI o-series) — sending
    it to Mistral/Gemini/Cohere makes the API reject the call with a 400.
    """
    kwargs = {"max_tokens": 5000}
    cls = type(llm).__name__
    model = str(getattr(llm, "model_name", None) or getattr(llm, "model", "") or "").lower()
    if (cls == "ChatGroq" and "gpt-oss" in model) or (cls == "ChatOpenAI" and model.startswith(("o1", "o3", "o4", "gpt-5"))):
        kwargs["reasoning_effort"] = "low"
    return llm.bind(**kwargs)


def generate_structured_report(patient_info: dict, raw_data: dict, hospital_name: str, llm) -> dict:
    """
    Has the LLM turn real gathered data into the structured JSON
    generate_smart_report() expects. Strictly grounded: told explicitly
    to use "-no_data"/"unknown" for anything not backed by the provided
    raw_data, never to invent findings, scores, or doctor names.
    """
    has_clinical_data = bool(raw_data)
    if not raw_data.get("trnparamresult"):
        print("[generate_structured_report] No authenticated lab results found for this patient — skipping the LLM.")
        return {
            "patient_name": patient_info.get("name"),
            "patient_age": patient_info.get("age"),
            "patient_gender": patient_info.get("gender"),
        }

    # Strip verbose/irrelevant columns before sending to the LLM — a
    # patient with many real results (e.g. 42 rows) can easily exceed
    # any reasonable character budget with full raw rows, silently
    # truncating mid-object and losing most of the real data. Keeping
    # only what the report actually needs lets far more real results
    # fit in the same budget.
    trimmed_results = [
        {
            "test_name": r.get("PARAMNAME") or r.get("PARAMHEADNAME") or r.get("PARAMID"),
            "section": r.get("PARAMHEADNAME"),
            "value": r.get("PVALUE"),
            "min": r.get("MINVALUE"),
            "max": r.get("MAXVALUE"),
            "unit": r.get("UNITDESC") or r.get("UNITID"),
        }
        for r in raw_data.get("trnparamresult", [])
    ][:20]

    prompt = f"""You are producing a structured health report for ONE real patient, based ONLY
on the real data below. Never invent values, findings, doctor names, or
scores not supported by this data.

Patient: {json.dumps(patient_info, default=str)}

Real test results found in the database (empty if none were found — in that case you only have demographic data, and every clinical field below must be "-no_data" or empty; do not invent findings to fill gaps):
{json.dumps({"trnparamresult": trimmed_results}, default=str)[:10000]}

Other related records (billing/administrative, for context only):
{json.dumps({k: v for k, v in raw_data.items() if k != "trnparamresult"}, default=str)[:2000]}

Respond with ONLY a JSON object (no markdown fences, no other text) with
this exact shape:
{{
  "patient_name": "...",
  "patient_age": "...",
  "patient_gender": "...",
  "health_score": "compute this whenever at least one real finding exists: start at 1000, subtract 100 for each finding with status='watch', subtract 250 for each finding with status='attention'. Only use '-no_data' if all_findings is completely empty.",
  "health_summary": "...",
  "body": {{
    "brain": {{"status": "normal|watch|attention|unknown", "label": "..."}},
    "heart": {{"status": "normal|watch|attention|unknown", "label": "..."}},
    "lungs": {{"status": "normal|watch|attention|unknown", "label": "..."}},
    "blood": {{"status": "normal|watch|attention|unknown", "label": "..."}},
    "bones": {{"status": "normal|watch|attention|unknown", "label": "..."}},
    "metabolism": {{"status": "normal|watch|attention|unknown", "label": "..."}},
    "kidney": {{"status": "normal|watch|attention|unknown", "label": "..."}},
    "liver": {{"status": "normal|watch|attention|unknown", "label": "..."}}
  }},
  "priority_findings": [{{"icon": "emoji", "name": "...", "value": "...", "unit": "...", "anchor": "finding-N"}}],
  "all_findings": [{{"anchor": "finding-N", "icon": "emoji", "name": "...", "category": "one of: Metabolic & Diabetes, Cardiovascular & Lipids, Liver Function, Kidney Function, Hematology, Hormones, Tumor Markers, Infection & Immunity, Vitamins & Minerals, Urine Analysis, Other", "value": "...", "unit": "...", "status": "normal|watch|attention|unknown", "label": "...", "range": "use the real min-max from the provided test data (e.g. '14.0-17.0') — REQUIRED whenever min/max values are present in the raw data, omit only if genuinely absent", "percentage": "REQUIRED whenever range is present — a number 0-100 showing where value sits on an extended low-to-high scale (not just min-max): roughly 0=far below range, 15=at the low edge, 50=mid-normal, 85=at the high edge, 100=far above range. Compute proportionally from the real min/max and value, don't just guess a round number.", "zones": "OPTIONAL. Ordered low-to-high list of colored threshold zones, for example [{{'from': null, 'to': 100, 'color': 'green', 'label': '<100'}}, {{'from': 100, 'to': 130, 'color': 'yellow', 'label': '100-129'}}, {{'from': 130, 'to': null, 'color': 'red', 'label': '>=130'}}]. color must be one of green, lightgreen, yellow, orange, red. Use null for an open end. Include this ONLY when the thresholds come from the provided min/max values or from a well-established clinical cut-off you are certain of for that exact test (e.g. LDL, HbA1c, triglycerides, total cholesterol). Otherwise OMIT it entirely — never guess thresholds; the report then draws a low/normal/high bar from the real min-max range.", "simple_explanation": "...", "why_it_matters": "...", "foods": ["..."], "lifestyle": ["..."], "doctor": "-no_data unless a real, non-null doctor name/ID exists in the provided raw_data — do not invent a name", "next_step": "..."}}],
  "category_summaries": {{"<category name exactly as used in all_findings>": "ONE plain sentence summarizing only that category's real findings — no invented values"}},
  "discussion_points": [{{"title": "short topic", "detail": "1-2 plain sentences for the patient to raise with their doctor — only about findings with status watch or attention; empty list if every finding is normal"}}],
  "health_connections": [] if there is nothing genuinely connecting two or more findings, otherwise ["..."],
  "trends": ["..."],
  "action_plan": {{"doctor": "-no_data unless a real, non-null doctor name/ID exists in the provided raw_data", "food": "...", "activity": "...", "followup": "..."}}
}}

Body-map organs come from finding categories: Metabolic & Diabetes/Hormones -> metabolism; Cardiovascular & Lipids -> heart; Hematology -> blood; Liver Function -> liver; Kidney Function -> kidney; Vitamins & Minerals -> bones. Organs with no matching category stay "unknown" / "No tests recorded". For "body":  only set a status other than "unknown" for an organ system that genuinely has a real finding tied to it (matching all_findings' categories). If there's no real data for an organ, leave it "unknown" with label "No tests recorded" — never guess a status for an organ with no real supporting finding.
For "doctor" fields with no real data: use "No referring doctor on record" instead of a generic placeholder. For "interpretation"/"why was it flagged" on a normal/negative finding: use "Not flagged — result was within the normal range" instead of a generic placeholder.
If there is no real clinical data at all (raw records are empty), return
empty lists for priority_findings/all_findings/health_connections/trends,
"-no_data" for health_score, and a health_summary explaining that only
demographic information was available for this patient.
"""

    from agent.agent import _invoke_with_retry
    from langchain_core.messages import HumanMessage
    print(f"[generate_structured_report] Prompt length: {len(prompt)} chars (~{len(prompt)//4} tokens)")
    llm_with_more_tokens = _bind_for_report(llm)
    response = _invoke_with_retry(llm_with_more_tokens, [HumanMessage(content=prompt)], retries=1)
    print(f"[generate_structured_report] response.tool_calls: {getattr(response, 'tool_calls', 'NO TOOL_CALLS ATTR')}")

    if response is None:
        print("[generate_structured_report] _invoke_with_retry returned None (rate-limited after retries, or a real error printed above).")
        return {
            "patient_name": patient_info.get("name"),
            "patient_age": patient_info.get("age"),
            "patient_gender": patient_info.get("gender"),
            "health_summary": "Could not generate detailed findings right now — the AI service is temporarily rate-limited. Please try again in a minute.",
        }

    text = response.content if hasattr(response, "content") else str(response)

    if not text or not text.strip():
        print("[generate_structured_report] LLM returned an EMPTY response despite no exception.")
        return {
            "patient_name": patient_info.get("name"),
            "patient_age": patient_info.get("age"),
            "patient_gender": patient_info.get("gender"),
            "health_summary": "Could not generate detailed findings for this patient right now (AI service returned nothing).",
        }

    try:
        parsed = _parse_llm_json(text)
        findings = parsed.get("all_findings", [])
        parsed["normal_count"] = sum(1 for f in findings if f.get("status") == "normal")
        parsed["borderline_count"] = sum(1 for f in findings if f.get("status") == "watch")
        parsed["abnormal_count"] = sum(1 for f in findings if f.get("status") == "attention")
        print(f"[generate_structured_report] LLM returned body: {parsed.get('body')}")
    except (json.JSONDecodeError, ValueError) as parse_err:
        print(f"[generate_structured_report] JSON PARSE FAILED (attempt 1): {parse_err}")
        print(f"[generate_structured_report] Raw LLM response (first 2000 chars): {text[:2000]}")

        # Real fix for the intermittent "empty report despite real data"
        # bug — a malformed JSON response previously gave up instantly
        # with zero retry, even though has_clinical_data confirms real
        # patient data genuinely exists. One retry catches the common
        # case where a fallback provider briefly returned a truncated
        # or slightly malformed response on the first attempt.
        if has_clinical_data:
            print("[generate_structured_report] Retrying once since real clinical data exists...")
            retry_response = _invoke_with_retry(llm_with_more_tokens, [HumanMessage(content=prompt)], retries=1)
            if retry_response is not None:
                retry_text = retry_response.content if hasattr(retry_response, "content") else str(retry_response)
                try:
                    parsed = _parse_llm_json(retry_text)
                    findings = parsed.get("all_findings", [])
                    parsed["normal_count"] = sum(1 for f in findings if f.get("status") == "normal")
                    parsed["borderline_count"] = sum(1 for f in findings if f.get("status") == "watch")
                    parsed["abnormal_count"] = sum(1 for f in findings if f.get("status") == "attention")
                    print(f"[generate_structured_report] Retry succeeded. body: {parsed.get('body')}")
                    return parsed
                except (json.JSONDecodeError, ValueError) as retry_parse_err:
                    print(f"[generate_structured_report] JSON PARSE FAILED (retry too): {retry_parse_err}")

        parsed = {
            "patient_name": patient_info.get("name"),
            "patient_age": patient_info.get("age"),
            "patient_gender": patient_info.get("gender"),
            "health_summary": "Could not generate detailed findings for this patient right now. Please try generating the report again.",
        }

    return parsed


def build_patient_report_data(patient_identifier: str, db_name: str, role: str, hospital_name: str, llm, db_server: str = None, db_user: str = None, db_password: str = None) -> dict:
    """
    Full pipeline: find the patient -> gather their real related data ->
    have the LLM structure it -> return data ready for
    reports.pdf_generator.generate_smart_report().
    """
    role_enum = Role(role)

    patient_info = find_patient(patient_identifier, db_name, db_server, db_user, db_password)
    alternate_uhids = find_alternate_uhids(patient_info.get("name"), patient_info.get("uhid"), db_name, db_server, db_user, db_password)
    raw_data = gather_patient_data(patient_info["patient_id"], db_name, role_enum, db_server, db_user, db_password, uhid=patient_info.get("uhid"))
    for alt_uhid in alternate_uhids:
        alt_data = gather_patient_data(patient_info["patient_id"], db_name, role_enum, db_server, db_user, db_password, uhid=alt_uhid)
        for table, rows in alt_data.items():
            if table not in raw_data:
                raw_data[table] = rows
            else:
                raw_data[table].extend(rows)
    structured = generate_structured_report(patient_info, raw_data, hospital_name, llm)

    structured.setdefault("patient_name", patient_info.get("name"))
    structured.setdefault("patient_age", patient_info.get("age"))
    structured.setdefault("patient_gender", patient_info.get("gender"))
    structured["hospital_name"] = hospital_name

    return structured