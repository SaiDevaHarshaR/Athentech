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
MAX_ROWS_PER_RELATED_TABLE = 20


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


def find_patient(identifier: str, db_name: str) -> dict:
    """
    Looks up a patient by UHID (exact-ish match) or name (partial match)
    in the real patient table. Discovers the real column names live
    rather than assuming exact names/casing, same principle as
    describe_table.
    """
    conn = get_hospital_connection(db_name)
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


def gather_patient_data(patient_id, db_name: str, role: Role) -> dict:
    """
    Uses REAL_TABLE_RELATIONSHIPS to find every mapped, role-permitted
    table with a known join back to the patient table, and pulls a
    bounded number of real rows for this specific patient from each.

    Returns {} for tables if REAL_TABLE_RELATIONSHIPS hasn't been
    populated yet (see discover_table_relationships.py) — this function
    only ever reports what it can actually find, never fabricates
    relationships that haven't been confirmed.
    """
    allowed_categories = get_allowed_tables(role)
    conn = get_hospital_connection(db_name)
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
                    query = f"SELECT TOP {MAX_ROWS_PER_RELATED_TABLE} * FROM {table_name} WHERE {column} = ?"
                    cursor.execute(query, (patient_id,))
                    col_names = [d[0] for d in cursor.description]
                    rows = cursor.fetchall()
                    print(f"[gather_patient_data] {table_name}.{column} = {patient_id}: {len(rows)} row(s)")
                    if rows:
                        gathered[table_name] = [dict(zip(col_names, r)) for r in rows]
                except Exception as e:
                    # Previously silently skipped with no visibility at all —
                    # a genuine SQL error (e.g. a type mismatch between
                    # patient_id and the join column) looked identical to
                    # "no data exists" with nothing printed either way.
                    print(f"[gather_patient_data] {table_name}.{column} query FAILED (not just empty): {e}")
                    continue
    finally:
        conn.close()

    print(f"[gather_patient_data] Checked {tables_checked} table(s) for patient_id={patient_id}, "
          f"found real data in {len(gathered)} of them.")

    return gathered


def _parse_llm_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    return json.loads(cleaned)


def generate_structured_report(patient_info: dict, raw_data: dict, hospital_name: str, llm) -> dict:
    """
    Has the LLM turn real gathered data into the structured JSON
    generate_smart_report() expects. Strictly grounded: told explicitly
    to use "-no_data"/"unknown" for anything not backed by the provided
    raw_data, never to invent findings, scores, or doctor names.
    """
    has_clinical_data = bool(raw_data)

    prompt = f"""You are producing a structured health report for ONE real patient, based ONLY
on the real data below. Never invent values, findings, doctor names, or
scores not supported by this data.

Patient: {json.dumps(patient_info, default=str)}

Real related records found in the database (empty if none were found —
in that case you only have demographic data, and every clinical field
below must be "-no_data" or empty; do not invent findings to fill gaps):
{json.dumps(raw_data, default=str)[:6000]}

Respond with ONLY a JSON object (no markdown fences, no other text) with
this exact shape:
{{
  "patient_name": "...",
  "patient_age": "...",
  "patient_gender": "...",
  "health_score": "-no_data or a number 0-1000 ONLY if genuinely computable from real data",
  "health_summary": "...",
  "priority_findings": [{{"icon": "emoji", "name": "...", "value": "...", "unit": "...", "anchor": "finding-N"}}],
  "all_findings": [{{"anchor": "finding-N", "icon": "emoji", "name": "...", "category": "one of: Brain, Heart, Lungs, Blood, Bones, Metabolism, Kidney, Liver", "value": "...", "unit": "...", "status": "normal|watch|attention|unknown", "label": "...", "simple_explanation": "...", "why_it_matters": "...", "foods": ["..."], "lifestyle": ["..."], "doctor": "...", "next_step": "..."}}],
  "health_connections": ["..."],
  "trends": ["..."],
  "action_plan": {{"doctor": "...", "food": "...", "activity": "...", "followup": "..."}}
}}

If there is no real clinical data at all (raw records are empty), return
empty lists for priority_findings/all_findings/health_connections/trends,
"-no_data" for health_score, and a health_summary explaining that only
demographic information was available for this patient.
"""

    response = llm.invoke(prompt)
    text = response.content if hasattr(response, "content") else str(response)

    try:
        parsed = _parse_llm_json(text)
    except (json.JSONDecodeError, ValueError):
        # Fail safe: demographic-only report rather than a crash or a
        # made-up structure if the LLM's output couldn't be parsed.
        parsed = {
            "patient_name": patient_info.get("name"),
            "patient_age": patient_info.get("age"),
            "patient_gender": patient_info.get("gender"),
            "health_summary": "Could not generate detailed findings for this patient right now.",
        }

    return parsed


def build_patient_report_data(patient_identifier: str, db_name: str, role: str, hospital_name: str, llm) -> dict:
    """
    Full pipeline: find the patient -> gather their real related data ->
    have the LLM structure it -> return data ready for
    reports.pdf_generator.generate_smart_report().
    """
    role_enum = Role(role)

    patient_info = find_patient(patient_identifier, db_name)
    raw_data = gather_patient_data(patient_info["patient_id"], db_name, role_enum)
    structured = generate_structured_report(patient_info, raw_data, hospital_name, llm)

    structured.setdefault("patient_name", patient_info.get("name"))
    structured.setdefault("patient_age", patient_info.get("age"))
    structured.setdefault("patient_gender", patient_info.get("gender"))
    structured["hospital_name"] = hospital_name

    return structured