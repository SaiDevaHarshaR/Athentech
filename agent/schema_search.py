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
    Returns up to top_n dicts: {"table": ..., "score": ..., "why": ...},
    ranked by relevance to the query.

    allowed_tables: restrict results to this set of real table names
    (role-based access) — pass None to search everything mapped.
    """
    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    profile = _load_profile()

    tables = set(REAL_TABLE_TO_CATEGORY.keys())
    if allowed_tables is not None:
        tables = tables & {t.lower() for t in allowed_tables}

    candidates = []
    for table in tables:
        score = 0
        reasons = []
        category = REAL_TABLE_TO_CATEGORY.get(table, "")
        table_lower = table.lower()

        # Signal 1: table name — substring match, not token match. Real
        # table names are one continuous string with no word separators
        # (e.g. "mstpatientregistration"), so tokenizing them and
        # requiring an exact token match would never find "patient"
        # inside that string at all — found and fixed via a real test
        # before this ever shipped.
        name_matches = [t for t in query_tokens if len(t) >= 3 and t in table_lower]
        if name_matches:
            score += 3 * len(name_matches)
            reasons.append(f"table name matches: {', '.join(sorted(name_matches))}")

        # Signal 2: classified category
        if category and category.lower() in query_tokens:
            score += 2
            reasons.append(f"category: {category}")

        # Signal 3 & 4 (only if this table has been profiled): real
        # column names and, most valuably, real sample VALUES.
        table_profile = profile.get(table)
        if table_profile:
            for col in table_profile.get("columns", []):
                col_name = col.get("column", "")
                col_matches = [t for t in query_tokens if len(t) >= 3 and t in col_name.lower()]
                if col_matches:
                    score += 2
                    reasons.append(f"column name: {col_name}")

                # Real value matches are the strongest signal — but cap
                # this at ONE bonus per column, not one per matching
                # value. Found a real case where this mattered: an
                # OrderId column full of payment-gateway IDs like
                # "order_KSTm1m9bVe5gSf" scored +5 for EVERY one of 15
                # sample rows (all coincidentally prefixed "order_"),
                # totaling +75 and burying a genuinely relevant table
                # that only scored 8. One real match in a column is
                # already a strong signal; more matches in the same
                # column don't make it more relevant, they're usually
                # just that column having lots of rows.
                matching_values = [v for v in (col.get("sample_values") or []) if query_tokens & _tokenize(v)]
                if matching_values:
                    score += 5
                    reasons.append(f"real value '{matching_values[0]}' seen in {col_name}")

        if score > 0:
            candidates.append({"table": table, "score": score, "why": "; ".join(reasons[:3])})

    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates[:top_n]