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
import re
import tempfile
import uuid
from datetime import datetime
from io import BytesIO

from jinja2 import Environment, FileSystemLoader, Undefined
from playwright.sync_api import sync_playwright


# ---------------------------------------------------------------------------
# Custom Undefined: never raises, renders as "-no_data", iterates as empty,
# and chains safely through nested attribute access (body.brain.status etc.)
# ---------------------------------------------------------------------------

class NoDataUndefined(Undefined):
    def __str__(self):
        return "Not available"

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
        if line.startswith("```") or line.startswith("{") or '"icon"' in line:
            continue  # raw dashboard-card/list-card JSON leaked in — never show this as a "finding"
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


ORGAN_CATEGORY_ALIASES = {
    "brain": ["neuro", "brain", "cognitive", "mental"],
    "heart": ["heart", "cardiac", "cardiovascular", "lipid"],
    "lungs": ["lung", "respiratory", "pulmonary"],
    "blood": ["blood", "hematology", "hemoglobin", "cbc", "anemia"],
    "bones": ["bone", "skeletal", "calcium", "vitamin", "mineral", "orthop"],
    "metabolism": ["metabolism", "metabolic", "sugar", "glucose", "diabetes", "thyroid", "lipid", "cholesterol", "hormone"],
    "kidney": ["kidney", "renal"],
    "liver": ["liver", "hepatic"],
}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-") or "other"


def _compute_organ_links(all_findings: list) -> dict:
    """
    Body-map boxes jump to the detailed card of the most important finding
    for that organ (abnormal first, then borderline, then any), falling
    back to the map itself when the organ has no matching finding.
    """
    links = {organ: "health-map" for organ in ORGAN_CATEGORY_ALIASES}
    rank = {"attention": 0, "watch": 1}

    for organ, keywords in ORGAN_CATEGORY_ALIASES.items():
        best, best_rank = None, 99
        for finding in all_findings or []:
            category = str(finding.get("category", "") or "").lower()
            anchor = finding.get("anchor")
            if not anchor or not category or not any(kw in category for kw in keywords):
                continue
            r = rank.get(finding.get("status"), 2)
            if r < best_rank:
                best, best_rank = anchor, r
        if best:
            links[organ] = best

    return links


def _compute_radar_chart_svg(all_findings: list) -> str:
    """
    Builds a real SVG radar/spider chart showing % of parameters
    within normal range per body-system category — matching the
    reference report's "Body-System Health Radar" visual. Computed
    entirely in Python (not Jinja2) since it needs real trigonometry
    for the polygon points; Jinja2 has no math functions for this.

    Returns an empty string if there's nothing to chart (e.g. every
    finding has an unrecognized category), so the template can safely
    skip rendering the section at all in that case.
    """
    import math

    # Group findings by category, track normal vs total per category.
    category_totals = {}
    for finding in all_findings or []:
        category = str(finding.get("category", "") or "").strip()
        if not category or category == NO_DATA:
            continue
        status = finding.get("status", "unknown")
        if category not in category_totals:
            category_totals[category] = {"normal": 0, "total": 0}
        category_totals[category]["total"] += 1
        if status == "normal":
            category_totals[category]["normal"] += 1

    if not category_totals:
        return ""

    categories = sorted(category_totals.keys())
    n = len(categories)
    if n < 3:
        # A radar chart with fewer than 3 axes isn't meaningful —
        # falls back to no chart rather than a degenerate shape.
        return ""

    percentages = []
    for cat in categories:
        t = category_totals[cat]
        pct = round((t["normal"] / t["total"]) * 100) if t["total"] else 0
        percentages.append(pct)

    # SVG geometry
    size = 320
    center = size / 2
    max_radius = 110
    angle_step = (2 * math.pi) / n

    def point_at(pct, index):
        angle = (angle_step * index) - (math.pi / 2)  # start at top, clockwise
        r = max_radius * (pct / 100)
        x = center + r * math.cos(angle)
        y = center + r * math.sin(angle)
        return x, y

    def label_point(index, offset=28):
        angle = (angle_step * index) - (math.pi / 2)
        r = max_radius + offset
        x = center + r * math.cos(angle)
        y = center + r * math.sin(angle)
        return x, y

    # Background grid rings (25/50/75/100%)
    grid_rings = ""
    for ring_pct in (25, 50, 75, 100):
        ring_points = [point_at(ring_pct, i) for i in range(n)]
        points_str = " ".join(f"{x:.1f},{y:.1f}" for x, y in ring_points)
        grid_rings += f'<polygon points="{points_str}" fill="none" stroke="#e0e6ea" stroke-width="1" />'

    # Axis lines from center to each outer vertex
    axis_lines = ""
    for i in range(n):
        x, y = point_at(100, i)
        axis_lines += f'<line x1="{center}" y1="{center}" x2="{x:.1f}" y2="{y:.1f}" stroke="#e0e6ea" stroke-width="1" />'

    # Data polygon (actual percentages)
    data_points = [point_at(pct, i) for i, pct in enumerate(percentages)]
    data_points_str = " ".join(f"{x:.1f},{y:.1f}" for x, y in data_points)

    # Labels
    labels_svg = ""
    for i, cat in enumerate(categories):
        lx, ly = label_point(i)
        pct = percentages[i]
        color = "#2e9d57" if pct >= 90 else ("#dba514" if pct >= 70 else "#d83b3b")
        anchor = "middle"
        if lx < center - 10:
            anchor = "end"
        elif lx > center + 10:
            anchor = "start"
        label_text = cat.title()
        labels_svg += (
            f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" '
            f'font-size="10" font-weight="700" fill="#37474f">{label_text}</text>'
            f'<text x="{lx:.1f}" y="{ly + 12:.1f}" text-anchor="{anchor}" '
            f'font-size="9" font-weight="700" fill="{color}">{pct}%</text>'
        )

    svg = f'''
    <svg viewBox="0 0 {size} {size}" width="100%" height="250" xmlns="http://www.w3.org/2000/svg">
        {grid_rings}
        {axis_lines}
        <polygon points="{data_points_str}" fill="#2e9d57" fill-opacity="0.35" stroke="#1e7a40" stroke-width="2" />
        {"".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="#1e7a40" />' for x, y in data_points)}
        {labels_svg}
    </svg>
    '''
    return svg


CATEGORY_SUBTITLES = {
    "metabolic & diabetes": "Blood sugar control markers",
    "cardiovascular & lipids": "Cholesterol, triglycerides & heart-risk markers",
    "liver function": "Liver enzymes, proteins & bilirubin",
    "kidney function": "Creatinine, electrolytes & waste clearance",
    "hematology": "Blood counts & iron status",
    "hormones": "Thyroid & hormone levels",
    "tumor markers": "Screening markers",
    "infection & immunity": "Infection screens & inflammation markers",
    "vitamins & minerals": "Micronutrient status",
    "urine analysis": "Complete urine examination",
}

_STATUS_WORD = {"normal": "Normal", "watch": "Borderline", "attention": "Abnormal", "unknown": "Info"}


def _build_donut_svg(normal: int, watch: int, attention: int, pct: int) -> str:
    """Donut ring drawn with stroke-dasharray arcs (no trigonometry needed)."""
    total = normal + watch + attention
    radius = 80
    circumference = 2 * 3.141592653589793 * radius
    parts = [(normal, "#2ecc71"), (watch, "#f1c40f"), (attention, "#e74c3c")]

    arcs = ""
    offset = 0.0
    if total:
        for count, color in parts:
            if not count:
                continue
            length = circumference * (count / total)
            arcs += (
                f'<circle cx="100" cy="100" r="{radius}" fill="none" stroke="{color}" '
                f'stroke-width="24" stroke-dasharray="{length:.2f} {circumference - length:.2f}" '
                f'stroke-dashoffset="{-offset:.2f}" transform="rotate(-90 100 100)" />'
            )
            offset += length
    else:
        arcs = f'<circle cx="100" cy="100" r="{radius}" fill="none" stroke="#e0e6ea" stroke-width="24" />'

    return (
        f'<svg viewBox="0 0 200 200" width="190" height="190" xmlns="http://www.w3.org/2000/svg">'
        f'{arcs}'
        f'<text x="100" y="104" text-anchor="middle" font-size="34" font-weight="700" fill="#0f2f24">{pct}%</text>'
        f'<text x="100" y="124" text-anchor="middle" font-size="11" fill="#607d8b">Within Range</text>'
        f'</svg>'
    )


_ZONE_HEX = {
    "green": "#2e9d57", "lightgreen": "#8bc34a", "yellow": "#dba514",
    "orange": "#e67e22", "red": "#d83b3b",
}

_RANGE_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*(?:-|\u2013|to)\s*(-?\d+(?:\.\d+)?)")


def _parse_number(raw):
    """Best-effort numeric parse; returns None instead of raising."""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    match = re.search(r"-?\d+(?:\.\d+)?", str(raw).replace(",", ""))
    return float(match.group(0)) if match else None


def _fmt_num(x: float) -> str:
    return f"{x:g}"


def _build_zone_bar(finding: dict):
    """
    Builds a real threshold-zone bar for one finding.

    Zones come from, in order of preference:
      1. finding["zones"] — ordered low-to-high list the LLM supplied
         ({from, to, color, label}; null = open end)
      2. the finding's own reference range ("14.0-17.0") turned into
         low (red) / normal (green) / high (red) zones — real thresholds,
         not a decorative bar.
    Segment widths are proportional to the real numeric span of each zone
    and the marker is placed at the true position of the measured value.
    Returns None when there is no numeric value or fewer than 2 zones, so
    the template can fall back gracefully.
    """
    value = _parse_number(finding.get("value"))
    if value is None:
        return None

    zones = []
    raw_zones = finding.get("zones")
    if isinstance(raw_zones, list):
        for z in raw_zones:
            if not isinstance(z, dict):
                continue
            color = str(z.get("color", "")).lower().replace(" ", "")
            if color not in _ZONE_HEX:
                continue
            lo, hi = _parse_number(z.get("from")), _parse_number(z.get("to"))
            if lo is None and hi is None:
                continue
            zones.append({"lo": lo, "hi": hi, "color": color, "label": str(z.get("label") or "")})

    if len(zones) < 2:
        m = _RANGE_RE.search(str(finding.get("range") or ""))
        if m:
            a, b = float(m.group(1)), float(m.group(2))
            if a < b:
                normal_zone = {"lo": a, "hi": b, "color": "green", "label": f"{_fmt_num(a)}-{_fmt_num(b)}"}
                high_zone = {"lo": b, "hi": None, "color": "red", "label": f">{_fmt_num(b)}"}
                if a <= 0:
                    # a range that starts at zero (e.g. "0-200") has no meaningful "low" zone
                    zones = [normal_zone, high_zone]
                else:
                    zones = [{"lo": None, "hi": a, "color": "red", "label": f"<{_fmt_num(a)}"}, normal_zone, high_zone]

    if len(zones) < 2:
        return None

    finite = [x for z in zones for x in (z["lo"], z["hi"]) if x is not None] + [value]
    lo_b, hi_b = min(finite), max(finite)
    span = (hi_b - lo_b) or max(abs(hi_b), 1.0)
    pad = span * 0.25
    lo_eff, hi_eff = lo_b - pad, hi_b + pad

    for z in zones:
        z["start"] = z["lo"] if z["lo"] is not None else lo_eff
        z["end"] = z["hi"] if z["hi"] is not None else hi_eff
    zones = [z for z in zones if z["end"] > z["start"]]
    zones.sort(key=lambda z: z["start"])
    if len(zones) < 2:
        return None

    total = sum(z["end"] - z["start"] for z in zones)
    cum, marker, segments = 0.0, None, []
    for z in zones:
        pct = (z["end"] - z["start"]) / total * 100
        if marker is None and z["start"] <= value <= z["end"]:
            marker = cum + (value - z["start"]) / (z["end"] - z["start"]) * pct
        label = z["label"]
        if not label:
            if z["lo"] is None:
                label = f"<{_fmt_num(z['hi'])}"
            elif z["hi"] is None:
                label = f">={_fmt_num(z['lo'])}"
            else:
                label = f"{_fmt_num(z['lo'])}-{_fmt_num(z['hi'])}"
        segments.append({"pct": round(pct, 2), "hex": _ZONE_HEX[z["color"]], "label": label})
        cum += pct

    if marker is None:
        marker = 2.0 if value < zones[0]["start"] else 98.0
    return {"segments": segments, "marker": round(min(max(marker, 2.0), 98.0), 2)}


def _normalize_priority_findings(merged: dict, findings: list) -> list:
    """
    Priority list with REAL anchors only. The LLM's own list is kept when
    each entry can be matched (by name) to an actual finding — its anchor
    is then taken from that finding, never trusted blindly. Otherwise the
    list is derived from the abnormal/borderline findings.
    """
    by_name = {str(f.get("name", "")).strip().lower(): f for f in findings}
    result = []
    raw = merged.get("priority_findings")
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            match = by_name.get(str(item.get("name", "")).strip().lower())
            if match and match.get("anchor"):
                result.append({
                    "icon": match.get("icon") or item.get("icon") or "",
                    "name": match.get("name"), "value": match.get("value"),
                    "unit": match.get("unit"), "anchor": match["anchor"],
                })
    if not result:
        flagged = [f for f in findings if f.get("status") == "attention"] + \
                  [f for f in findings if f.get("status") == "watch"]
        for f in flagged:
            if f.get("anchor"):
                result.append({"icon": f.get("icon") or "", "name": f.get("name"),
                               "value": f.get("value"), "unit": f.get("unit"), "anchor": f["anchor"]})
    return result[:8]


def _prepare_report_context(merged: dict) -> None:
    """
    Derives everything the merged layout needs from the real findings:
    counts, per-body-system groups, attention/borderline lists, the
    "everything else" summary, discussion points and the closing text.
    Anything the LLM supplied (category_summaries, discussion_points)
    is used as-is; otherwise a plain, strictly data-derived fallback is
    built so no section is ever invented or left half-empty.
    """
    findings = merged.get("all_findings") or []

    for f in findings:
        f["badge_text"] = f.get("label") or _STATUS_WORD.get(f.get("status"), "Info")
        f["zone_class"] = {"normal": "green", "watch": "yellow", "attention": "red"}.get(f.get("status"), "green")
        f["zone_bar"] = _build_zone_bar(f)

    normal = [f for f in findings if f.get("status") == "normal"]
    watch = [f for f in findings if f.get("status") == "watch"]
    attention = [f for f in findings if f.get("status") == "attention"]
    total = len(findings)
    pct = round(len(normal) / total * 100) if total else 0

    merged["normal_count"] = len(normal)
    merged["borderline_count"] = len(watch)
    merged["abnormal_count"] = len(attention)
    merged["total_parameters"] = total
    merged["pct_within_range"] = pct
    merged["donut_svg"] = _build_donut_svg(len(normal), len(watch), len(attention), pct)
    merged["attention_findings"] = attention
    merged["borderline_findings"] = watch
    merged["non_normal_findings"] = attention + watch
    # Detail cards for EVERY finding, most important first.
    merged["detail_findings"] = attention + watch + [f for f in findings if f.get("status") not in ("attention", "watch")]
    merged["priority_findings"] = _normalize_priority_findings(merged, findings)

    # --- body-system groups, in order of first appearance ---
    summaries_raw = merged.get("category_summaries") or {}
    summaries = {str(k).strip().lower(): v for k, v in summaries_raw.items()} if isinstance(summaries_raw, dict) else {}

    groups, order = {}, []
    for f in findings:
        raw = str(f.get("category") or "").strip()
        name = raw if raw and raw != NO_DATA else "Other Results"
        if name not in groups:
            groups[name] = []
            order.append(name)
        groups[name].append(f)

    categories = []
    for name in order:
        items = groups[name]
        n_norm = sum(1 for f in items if f.get("status") == "normal")
        n_watch = sum(1 for f in items if f.get("status") == "watch")
        n_att = sum(1 for f in items if f.get("status") == "attention")
        takeaway = summaries.get(name.lower())
        if not takeaway:
            if n_norm == len(items):
                takeaway = f"All {len(items)} parameters in this group are within the normal range."
            else:
                flagged = ", ".join(f.get("name", "") for f in items if f.get("status") in ("watch", "attention"))
                takeaway = f"{n_att + n_watch} of {len(items)} parameters need monitoring or attention: {flagged}."
        categories.append({
            "name": name,
            "slug": _slug(name),
            "subtitle": CATEGORY_SUBTITLES.get(name.lower(), ""),
            "findings": items,
            "normal": n_norm, "watch": n_watch, "attention": n_att,
            "takeaway": takeaway,
        })
    merged["categories"] = categories

    # --- "everything else" paragraph, strictly from the normal findings ---
    names = [f.get("name", "") for f in normal if f.get("name")]
    if names:
        shown = names[:30]
        extra = len(names) - len(shown)
        text = ", ".join(shown) + (f" and {extra} more" if extra > 0 else "")
        merged["everything_else"] = (
            f"{len(names)} parameters came back within normal limits, including: {text}."
        )
    else:
        merged["everything_else"] = ""

    # --- doctor discussion points ---
    points = merged.get("discussion_points")
    if not (isinstance(points, list) and points):
        points = []
        for f in (attention + watch)[:5]:
            detail = f.get("next_step") or f.get("simple_explanation") or ""
            if detail and detail != NO_DATA:
                points.append({"title": f.get("name", ""), "detail": detail})
        followup = (merged.get("action_plan") or {}).get("followup")
        if followup and followup != NO_DATA and len(points) < 5:
            points.append({"title": "Routine follow-up", "detail": followup})
    merged["discussion_points"] = points[:5]

    # --- referring doctor (never invented) ---
    doctor = (merged.get("action_plan") or {}).get("doctor") or ""
    merged["referring_doctor"] = "" if (not doctor or "no referring doctor" in doctor.lower() or doctor == NO_DATA) else doctor

    # --- closing summary ---
    merged["closing_summary"] = (
        f"This report covers {total} parameters across {len(categories)} body-system group"
        f"{'s' if len(categories) != 1 else ''}. Of these, {len(normal)} were within the normal range, "
        f"{len(watch)} borderline and {len(attention)} abnormal — an overall result of {pct}% within normal range."
    ) if total else ""


def generate_smart_report(data: dict) -> BytesIO:
    """
    Renders via a real headless Chromium browser (Playwright) instead of
    xhtml2pdf. xhtml2pdf could not render emoji fonts or CSS grid/flexbox
    layouts at all — a hard limitation of that library, not something
    fixable with more CSS tuning. A real browser engine renders exactly
    what you'd see viewing the HTML normally: real emoji, real layout.

    As a side effect this also makes the old xhtml2pdf-specific
    _add_link_targets() workaround unnecessary — real browsers already
    treat id="..." as a valid link target for <a href="#id">, so internal
    jump-links (View details, Back to Health Map) work natively.
    """
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
    merged["organ_links"] = _compute_organ_links(merged.get("all_findings"))
    merged["radar_chart_svg"] = _compute_radar_chart_svg(merged.get("all_findings"))
    _prepare_report_context(merged)

    if not merged.get("all_findings"):
        # No real clinical data at all — a full 3-page template of empty
        # organ boxes is worse than useless, it looks broken. Render a
        # short, honest one-page notice instead.
        html_content = f"""
        <html><head><meta charset="utf-8"></head>
        <body style="font-family: sans-serif; padding: 60px; text-align: center;">
          <h1 style="color:#333;">Sahasra AI Report</h1>
          <p style="color:#666; font-size:14px;">{merged.get('hospital_name','')}</p>
          <h2 style="margin-top:50px;">{merged.get('patient_name','')}</h2>
          <p>{merged.get('patient_age','')} years &middot; {merged.get('patient_gender','')}</p>
          <div style="margin-top:60px; font-size:18px; color:#444;">
            No lab or imaging results are on record for this patient yet.<br>
            Once tests are completed, a full health report will be available here.
          </div>
          <p style="margin-top:80px; font-size:11px; color:#999;">Report ID: {merged.get('report_id','')} &middot; {merged.get('report_date','')}</p>
        </body></html>
        """
    else:
        env = Environment(
            loader=FileSystemLoader(_template_dir()),
            undefined=NoDataUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        template = env.get_template("smart_report.html")
        html_content = template.render(**merged)

    # Written to a temp file INSIDE the templates folder so relative
    # asset references (styles.css) resolve naturally via a real
    # file:// base URL — no custom path-resolution hack needed, unlike
    # the old xhtml2pdf link_callback approach.
    fd, temp_path = tempfile.mkstemp(suffix=".html", dir=_template_dir())
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(html_content)

        pdf_bytes = _render_pdf_with_chromium(temp_path)
    finally:
        os.remove(temp_path)

    pdf_file = BytesIO(pdf_bytes)
    pdf_file.seek(0)
    return pdf_file


def _render_pdf_with_chromium(html_file_path: str) -> bytes:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(f"file://{html_file_path}")
            pdf_bytes = page.pdf(format="A4", print_background=True, prefer_css_page_size=True)
        finally:
            browser.close()
    return pdf_bytes


def _template_dir() -> str:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, "templates")