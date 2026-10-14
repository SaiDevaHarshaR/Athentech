"""Stage 7B guarded dispatcher; invokes EXISTING authenticated, organization-scoped tools.

No free-form SQL, database writes, API usage or report release bypass.
"""
from __future__ import annotations
from fastapi import HTTPException
from auth.b2b_intent_engine import parse_question


def _json_rows(rows):
    return [{"bill_no": b, "bill_date": dt, "billed_amount": amount, "status": st}
            for b, dt, amount, st in rows]


def handle_question(*, question, default_period, inst, organisation_code,
                    rows_for_org, summary_for_org, allowed_statuses=None):
    """Called ONLY after _auth_session has succeeded.

    allowed_statuses: reviewed LIS-specific literal invoice STATUS values, e.g.
    {'pending': ['P'], 'completed': ['C']}. No guesses or wildcards.
    """
    d = parse_question(question)
    period = d.period or default_period
    if d.intent == "forbidden":
        return {"status":"success", "intent":d.intent, "answer":"I can only access your verified organization's records."}
    if d.intent == "clarify":
        return {"status":"success", "intent":d.intent, "answer":d.note}
    if d.intent == "patient_report":
        return {"status":"success", "intent":d.intent,
                "answer":"Clinical PDF downloads require separate patient/report release permission. Please use the laboratory's approved report workflow."}
    if d.intent == "unsupported_clinical_status":
        return {"status":"success", "intent":d.intent,
                "answer":"Sample and investigation status queries are not enabled until this LIS's status codes and organization-scoped joins are validated."}
    if d.intent == "excel":
        return {"status":"success", "intent":d.intent, "action":"download_excel", "period":period,
                "answer":"You can download your organization's authorized billing Excel statement."}
    if d.intent == "overview":
        s = summary_for_org(inst, organisation_code, period)
        return {"status":"success", "intent":d.intent, "period":period, "summary":s,
                "answer":f"For {period}: {s['bills']} invoices, billed value INR {s['billed_total']:,.2f}. Billed value is not collected cash."}
    if d.intent in ("bills", "invoice_status"):
        rows = rows_for_org(inst, organisation_code, period, max_rows=500)
        if d.intent == "invoice_status":
            mapping = (allowed_statuses or {}).get(d.status_filter, [])
            if not mapping:
                return {"status":"success", "intent":"status_mapping_required", "period":period,
                        "answer":f"The laboratory has not yet approved which invoice statuses mean '{d.status_filter}'. Showing all invoices would be misleading, so no results were returned."}
            allowed = {v.casefold() for v in mapping if isinstance(v,str) and v.strip()}
            if not allowed:
                raise HTTPException(422, "Invoice status configuration is invalid.")
            rows = [r for r in rows if str(r[3]).strip().casefold() in allowed]
        listed = rows[:20]
        return {"status":"success", "intent":d.intent, "period":period,
                "bills":_json_rows(listed), "has_more":len(rows)>20,
                "answer":f"Showing {len(listed)} authorized invoice records for {period}."}
    return {"status":"success", "intent":"help", "answer":
            "Try: How many invoices this month? Show invoices. Download Excel. "
            "Pending invoice queries require an approved LIS status mapping."}
