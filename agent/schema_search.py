"""
Deterministic (non-LLM, plain Python) schema search: given a natural-
language query like "radiology tests", returns the real tables most
likely to be relevant — ranked using signals we already have:

1. Table name itself (weak signal — names are often cryptic, like
   trninvlabdet, so this alone isn't enough)
2. The table's classified category (auth/table_access.py)
3. Real column names, IF the table has been profiled (schema_profile.json)
4. Real SAMPLE VALUES, IF profiled — the strongest signal by far. E.g.
   searching "radiology" matches mstdepartment because its
   DEPARTMENTNAME column's real sample values literally contain
   "Radiology" — this is exactly the grounding that would have caught
   a real production bug (DEPTCODE = 'Radiology' assumed instead of
   verified) much faster than guessing from table names alone.

Works with zero profiling done (falls back to name + category matching
only) and gets progressively better as schema_profile.json covers more
tables — see profile_schema.py to expand it.
"""

import json
import os
import re

from auth.table_access import REAL_TABLE_TO_CATEGORY
_PROFILE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "schema_profile.json")

_BANNED_TABLES = {
    "trntempdaycollall", "trntempabnormalreport", "trntemppatientrepeatevisits",
    "trntempbranchwisecoll", "trntempmoncoll", "trntempshiftcollecrpt",
    "trnbillingcyclerates", "daycollection_mobileapp",
}
def _load_profile() -> dict:
    """{table_name_lower: profile_dict}, or {} if not generated yet —
    search still works without this, just with a weaker signal."""
    if not os.path.exists(_PROFILE_PATH):
        return {}
    try:
        with open(_PROFILE_PATH, "r", encoding="utf-8") as f:
            profiles = json.load(f)
        return {p["table"].lower(): p for p in profiles if "table" in p and "error" not in p}
    except Exception:
        return {}


def _tokenize(text: str) -> set:
    text = str(text).lower()

    # Normalize common healthcare/business terminology
    synonyms = {
        "laboratory": "labs",
        "laboratories": "labs",
        "lab": "labs",
        "tests": "test",
        "investigations": "investigation",
        "diagnostics": "diagnostic",
        "radiology": "radiology",
        "patients": "patient",
        "bills": "bill",
        "collections": "collection",
        "reports": "report",
        "departments": "department",
        "doctors": "doctor",
        "physicians": "doctor",
        "branches": "branch",
        "locations": "location",
        "revenue": "collection",
        "payments": "payment",
    }

    tokens = set(re.findall(r"[a-z]+", text))

    normalized = set(tokens)

    for token in tokens:
        normalized.add(synonyms.get(token, token))

    return normalized

def search_schema(query: str, allowed_tables: set = None, top_n: int = 8) -> list:
    """
    Deterministic schema search.

    Uses:
      1. semantic synonyms
      2. table-name matches
      3. category matches
      4. real column-name matches
      5. real profiled sample-value matches

    No LLM is involved.
    """

    query_tokens = _tokenize(query)

    if not query_tokens:
        return []

    profile = _load_profile()

    tables = set(REAL_TABLE_TO_CATEGORY.keys())

    if allowed_tables is not None:
        allowed_lower = {t.lower() for t in allowed_tables}
        tables &= allowed_lower

    candidates = []

    for table in tables:
        score = 0
        reasons = []

        category = REAL_TABLE_TO_CATEGORY.get(table, "")
        table_lower = table.lower()

        # ---------------------------------------------------------
        # 1. Physical table name
        # ---------------------------------------------------------
        name_matches = [
            token
            for token in query_tokens
            if len(token) >= 3 and token in table_lower
        ]

        if name_matches:
            score += 3 * len(name_matches)
            reasons.append(
                f"table name matches: {', '.join(sorted(name_matches))}"
            )

        # ---------------------------------------------------------
        # 2. Logical category
        # ---------------------------------------------------------
        category_lower = category.lower()

        category_matches = [
            token
            for token in query_tokens
            if len(token) >= 3 and (
                token == category_lower
                or token in category_lower
                or category_lower in token
            )
        ]

        if category_matches:
            score += 6
            reasons.append(f"category: {category}")

        # ---------------------------------------------------------
        # 3 + 4. Real schema profile
        # ---------------------------------------------------------
        table_profile = profile.get(table)

        if table_profile:
            for col in table_profile.get("columns", []):
                col_name = col.get("column", "")
                col_lower = col_name.lower()

                # Real column-name match
                col_matches = [
                    token
                    for token in query_tokens
                    if len(token) >= 3 and token in col_lower
                ]

                if col_matches:
                    score += 2 * len(col_matches)
                    reasons.append(f"column name: {col_name}")

                # Real sample-value match
                matching_values = [
                    value
                    for value in (col.get("sample_values") or [])
                    if query_tokens & _tokenize(value)
                ]

                if matching_values:
                    score += 5
                    reasons.append(
                        f"real value '{matching_values[0]}' seen in {col_name}"
                    )

        if score > 0:
            candidates.append(
                {
                    "table": table,
                    "score": score,
                    "why": "; ".join(reasons[:4]),
                }
            )

    candidates.sort(
        key=lambda item: (-item["score"], item["table"])
    )

    return candidates[:top_n]