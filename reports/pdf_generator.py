"""
Generates the Smart Health Report PDF using reports/templates/smart_report.html
(the real "AI health interpretation" template — not the old plain placeholder).

Design goal: missing data should NEVER crash PDF generation. Any field the
template expects but wasn't supplied renders as "-no_data" instead of
raising, and any list the template expects to loop over defaults to an
empty list instead of erroring on iteration.

Two ways this gets used:
1. Structured mode: caller supplies patient_name, health_score, body map,
   all_findings, etc. directly (see DEFAULT_REPORT_DATA below for the
   full shape). This is what a "real" Smart Report eventually needs —
   the agent producing genuinely structured findings, not just text.
2. Fallback mode: caller only has plain text lines (what the chat agent
   returns today). build_findings_from_content_lines() turns those into
   lightweight "finding" entries so /generate-pdf still produces a real,
   populated report right now, without needing the bigger "LLM outputs
   structured JSON findings" feature built first.
"""

import copy
import os
import uuid
from datetime import datetime
from io import BytesIO

from jinja2 import Environment, FileSystemLoader, Undefined
from xhtml2pdf import pisa


# ---------------------------------------------------------------------------
# Custom Undefined: never raises, renders as "-no_data", iterates as empty,
# and chains safely through nested attribute access (body.brain.status etc.)
# ---------------------------------------------------------------------------

class NoDataUndefined(Undefined):
    def __str__(self):
        return "-no_data"

    def __iter__(self):
        return iter([])

    def __bool__(self):
        return False

    def __getattr__(self, name):
        # Allow further chaining (e.g. body.brain.status) without raising.
        return NoDataUndefined(name=name)

    def __getitem__(self, key):
        return NoDataUndefined(name=str(key))


# ---------------------------------------------------------------------------
# Full default shape of everything smart_report.html can render. Any field
# the caller doesn't supply falls back to these — text fields become
# "-no_data" strings (visible placeholder, matches the Undefined behaviour
# above so both "missing key entirely" and "key present but empty" look the
# same to the reader), and list fields default to [] so the template's
# {% for %} loops and {% if %} guards behave safely either way.
# ---------------------------------------------------------------------------

NO_DATA = "-no_data"

_BODY_PART_DEFAULT = {"status": "unknown", "label": NO_DATA}

DEFAULT_REPORT_DATA = {
    "report_title": "SAHASRA AI REPORT",
    "hospital_name": NO_DATA,
    "user_role": NO_DATA,
    "activation_code": "",

    "patient_name": NO_DATA,
    "patient_age": NO_DATA,
    "patient_gender": NO_DATA,

    "health_score": NO_DATA,
    "health_summary": NO_DATA,

    "body": {
        "brain": dict(_BODY_PART_DEFAULT),
        "heart": dict(_BODY_PART_DEFAULT),
        "lungs": dict(_BODY_PART_DEFAULT),
        "blood": dict(_BODY_PART_DEFAULT),
        "bones": dict(_BODY_PART_DEFAULT),
        "metabolism": dict(_BODY_PART_DEFAULT),
        "kidney": dict(_BODY_PART_DEFAULT),
        "liver": dict(_BODY_PART_DEFAULT),
    },

    "normal_count": 0,
    "borderline_count": 0,
    "abnormal_count": 0,

    "priority_findings": [],
    "all_findings": [],
    "health_connections": [],
    "trends": [],

    "action_plan": {
        "doctor": "",
        "food": "",
        "activity": "",
        "followup": "",
    },
}


def _deep_merge(defaults: dict, override: dict) -> dict:
    """Recursively merges `override` onto a copy of `defaults`. Only
    touches keys that exist in `override` — everything else keeps its
    default. None/"" values in `override` are treated as "not provided"
    for string fields (they become "-no_data" too), so a caller passing
    patient_name=None behaves the same as not passing it at all."""
    result = copy.deepcopy(defaults)

    for key, value in override.items():
        if key not in result:
            result[key] = value
            continue

        if isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        elif value is None or value == "":
            # keep the default (already "-no_data" or [] as appropriate)
            continue
        else:
            result[key] = value

    return result


def build_findings_from_content_lines(content_lines: list) -> list:
    """
    Fallback adapter: turns the agent's plain-text bullet lines into
    lightweight 'finding' entries so the Smart Report template has
    something real to render even before structured findings exist.
    Every field the template might reference is present (as "-no_data"
    where we don't have real data) so nothing downstream needs special
    casing for this fallback path.
    """
    findings = []
    for i, line in enumerate(content_lines or []):
        line = (line or "").strip()
        if not line:
            continue
        findings.append({
            "anchor": f"finding-{i}",
            "icon": "📋",
            "name": line[:60] if line else NO_DATA,
            "category": NO_DATA,
            "value": "",
            "unit": "",
            "status": "unknown",
            "label": NO_DATA,
            "range": "",
            "percentage": "",
            "simple_explanation": line or NO_DATA,
            "why_it_matters": NO_DATA,
            "interpretation": NO_DATA,
            "foods": [],
            "lifestyle": [],
            "doctor": "",
            "next_step": "",
        })
    return findings


def _resolve_asset_path(uri: str, rel: str = None) -> str:
    """
    xhtml2pdf needs an absolute filesystem path for relative <link>/<img>
    references (it can't resolve "report.css" on its own from an HTML
    string that has no base URL). This maps any relative asset reference
    in the template to the reports/templates/ folder.
    """
    if uri.startswith(("http://", "https://", "data:")):
        return uri
    if os.path.isabs(uri) and os.path.exists(uri):
        return uri
    return os.path.join(_template_dir(), uri.lstrip("/"))


def generate_smart_report(data: dict) -> BytesIO:
    data = data or {}

    # Fallback: if the caller only gave us plain content_lines and no
    # structured all_findings, turn those lines into findings so the
    # report isn't just an empty shell.
    if data.get("content_lines") and not data.get("all_findings"):
        data = dict(data)
        data["all_findings"] = build_findings_from_content_lines(data["content_lines"])

    merged = _deep_merge(DEFAULT_REPORT_DATA, data)

    merged.setdefault("report_date", datetime.now().strftime("%d/%m/%Y %H:%M"))
    merged.setdefault("report_id", str(uuid.uuid4())[:8].upper())

    env = Environment(
        loader=FileSystemLoader(_template_dir()),
        undefined=NoDataUndefined,
    )
    template = env.get_template("smart_report.html")

    html_content = template.render(**merged)

    pdf_file = BytesIO()
    pisa_status = pisa.CreatePDF(
        html_content,
        dest=pdf_file,
        link_callback=_resolve_asset_path,
    )

    if pisa_status.err:
        raise Exception("Error creating PDF")

    pdf_file.seek(0)
    return pdf_file


def _template_dir() -> str:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, "templates")