from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
#from agent.tools import run_sql_query, describe_table, get_verified_day_collection, search_schema
from agent.search_tool import web_search
from agent.guardrails import check_input, check_output
from config import settings
from auth.roles import Role
from auth.table_access import list_allowed_tables_for_role
from auth.schema_pack import schema_hint_for_prompt
import time
import re
from datetime import date, timedelta
from agent.tools import (
    run_sql_query,
    describe_table,
    get_verified_day_collection,
    search_schema,
    get_department_dashboard,
    get_lab_day_collection, 
    get_tat_compliance_dashboard,
    check_zero_collection_alert,
    check_tat_alert
)

def _build_llm():
    """
    Builds the chat model based on settings.llm_provider (default "groq").
    OpenAI requires settings.llm_model to be set explicitly in .env.
    """
    provider = (settings.llm_provider or "groq").lower()
    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        if not settings.llm_model:
            raise RuntimeError(
                "LLM_PROVIDER=gemini requires LLM_MODEL to be set in .env "
                "(e.g. LLM_MODEL=gemini-2.5-flash)."
            )
        print(f"[agent] Using Gemini — model: {settings.llm_model}")
        return ChatGoogleGenerativeAI(
            model=settings.llm_model,
            temperature=0,
            google_api_key=settings.gemini_api_key,
        )
    if provider == "openai":
        from langchain_openai import ChatOpenAI
        if not settings.llm_model:
            raise RuntimeError(
                "LLM_PROVIDER=openai requires LLM_MODEL to be set in .env "
                "(e.g. LLM_MODEL=gpt-4o)."
            )
        print(f"[agent] Using OpenAI — model: {settings.llm_model}")
        return ChatOpenAI(
            model=settings.llm_model,
            temperature=0,
            api_key=settings.openai_api_key,
        )

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        if not settings.llm_model:
            raise RuntimeError(
                "LLM_PROVIDER=anthropic requires LLM_MODEL to be set in .env "
                "(e.g. LLM_MODEL=claude-sonnet-4-5)."
            )
        print(f"[agent] Using Anthropic — model: {settings.llm_model}")
        return ChatAnthropic(
            model=settings.llm_model,
            temperature=0,
            api_key=settings.anthropic_api_key,
        )

    model_name = settings.llm_model or "openai/gpt-oss-20b"
    print(f"[agent] Using Groq — model: {model_name}")
    from langchain_groq import ChatGroq
    return ChatGroq(
        model=model_name,
        temperature=0,
        api_key=settings.groq_api_key,
    )


try:
    llm = _build_llm()
except Exception as e:
    import traceback
    traceback.print_exc()
    raise 
MAX_TOOL_ROUNDS = 6
# Was 2 — enough for one focused metric group (describe_table + run_sql_query
# on a single table) but not for a broad multi-source dashboard question
# needing several different tables (patients + billing + labs + radiology
# + reports). Raised to allow up to ~3 full describe+query pairs. This
# does NOT slow down simple questions — the loop still exits the moment
# the model stops calling tools, so a 2-round question is still exactly
# as fast as before. It only allows MORE rounds for questions that
# genuinely need them, at the cost of real latency on those specific
# broad questions (accepted tradeoff — revisit if it's too slow).
MAX_HISTORY = 4


def _is_rate_limit_error(e: Exception) -> bool:
    msg = str(e).lower()
    return "rate_limit" in msg or "rate limit" in msg or "429" in msg


def _invoke_with_retry(runnable, messages, retries=1):
    for i in range(retries + 1):
        try:
            return runnable.invoke(messages)
        except Exception as e:
            print(f"[_invoke_with_retry] REAL ERROR: {e}")
            if not _is_rate_limit_error(e):
                raise
            if i == retries:
                return None
            time.sleep(20)
    return None

import re
from datetime import datetime

def parse_dashboard_period(q: str) -> tuple[str, str]:
    q = (q or "").lower()

    if "today" in q:
        return "today", "Today"
    if "yesterday" in q:
        return "yesterday", "Yesterday"
    if "last week" in q:
        return "last_week", "Last Week"
    if "this week" in q:
        return "this_week", "This Week"
    if "last month" in q:
        return "last_month", "Last Month"
    if "this month" in q:
        return "this_month", "This Month"
    if "last year" in q:
        return "last_year", "Last Year"
    if "this year" in q:
        return "this_year", "This Year"

    m = re.search(r"last\s+(\d+)\s+days?", q)
    if m:
        n = int(m.group(1))
        return f"last_{n}_days", f"Last {n} Days"

    # YYYY-MM-DD
    m = re.search(r"(\d{4}-\d{2}-\d{2})", q)
    if m:
        d = m.group(1)
        return f"day:{d}", d

    # year only: "2025" / "2025's"
    months = {
        "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
        "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
        "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
        "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
    }

    # "4th september", "5 september", "september 4", "4 sep 2026"
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s*(\d{4})?\b", q)
    if m:
        day = int(m.group(1))
        mon_key = m.group(2).lower()
        mon = next(v for k, v in months.items() if mon_key.startswith(k[:3]))
        year = int(m.group(3)) if m.group(3) else datetime.now().year
        d = f"{year:04d}-{mon:02d}-{day:02d}"
        return f"day:{d}", d

    # "september 4", "sep 5 2026"
    m = re.search(r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+(\d{1,2})(?:st|nd|rd|th)?\s*(\d{4})?\b", q)
    if m:
        mon_key = m.group(1).lower()
        mon = next(v for k, v in months.items() if mon_key.startswith(k[:3]))
        day = int(m.group(2))
        year = int(m.group(3)) if m.group(3) else datetime.now().year
        d = f"{year:04d}-{mon:02d}-{day:02d}"
        return f"day:{d}", d

    # NEW: bare month name, no day — "July", "July month", "in August"
    m = re.search(r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b(?:\s+(\d{4}))?", q)
    if m:
        mon_key = m.group(1).lower()
        mon = next(v for k, v in months.items() if mon_key.startswith(k[:3]))
        year = int(m.group(2)) if m.group(2) else datetime.now().year
        return f"month:{year:04d}-{mon:02d}", f"{m.group(1).title()} {year}"

    # year only: "2025" / "2025's" — LAST resort, after all specific-date checks
    m = re.search(r"\b(20\d{2})\b", q)
    if m and "dashboard" in q:
        year = m.group(1)
        return f"year:{year}", year
    if m:
        day = int(m.group(1))
        mon = months[m.group(2)[:3] if m.group(2)[:3] in months else m.group(2)]
        # normalize month key
        mon_key = m.group(2).lower()
        for k, v in months.items():
            if mon_key.startswith(k[:3]):
                mon = v
                break
        year = int(m.group(3)) if m.group(3) else datetime.now().year
        d = f"{year:04d}-{mon:02d}-{day:02d}"
        return f"day:{d}", d

    # e.g. september 4 / sep 5 2026
    m = re.search(
        r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+(\d{1,2})(?:st|nd|rd|th)?\s*(\d{4})?\b",
        q,
    )
    if m:
        mon_key = m.group(1).lower()
        mon = 1
        for k, v in months.items():
            if mon_key.startswith(k[:3]):
                mon = v
                break
        day = int(m.group(2))
        year = int(m.group(3)) if m.group(3) else datetime.now().year
        d = f"{year:04d}-{mon:02d}-{day:02d}"
        return f"day:{d}", d

    return "yesterday", "Yesterday"
def _extract_text(content):
    """
    Most providers return .content as a plain string. Gemini can
    return a list of content blocks instead (each a dict with a
    'text' field, plus internal fields like 'signature' that must
    never be shown to the user). Extract just the real text.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return str(content) if content else ""


def _run_tool_loop(llm_with_tools, messages, tools_by_name: dict, tool_extra_kwargs: dict = None):
    tool_extra_kwargs = tool_extra_kwargs or {}

    response = _invoke_with_retry(llm_with_tools, messages)
    if response is None:
        return (
            "AI rate limit reached. Please wait about 1 minute, "
            "clear chat history, and try a shorter question."
        )

    for _ in range(MAX_TOOL_ROUNDS):
        if not getattr(response, "tool_calls", None):
            return _extract_text(response.content) or None

        messages.append(response)

        for tool_call in response.tool_calls:
            tool_fn = tools_by_name.get(tool_call["name"])
            if not tool_fn:
                result = f"Error: unknown tool '{tool_call['name']}'."
            else:
                args = dict(tool_call.get("args") or {})
                args.update(tool_extra_kwargs.get(tool_call["name"], {}))
                result = tool_fn.invoke(args)

            result_text = str(result)
            if len(result_text) > 1200:
                result_text = result_text[:1200] + "\n...[truncated]"

            messages.append(
                ToolMessage(content=result_text, tool_call_id=tool_call["id"])
            )

        response = _invoke_with_retry(llm_with_tools, messages)
        if response is None:
            return (
                "AI rate limit reached while processing tools. "
                "Wait 1 minute and try again."
            )

    # Check final response after last loop iteration
    if not getattr(response, "tool_calls", None):
        return _extract_text(response.content) or None

    messages.append(
        HumanMessage(
            content=(
                "Give your best final answer now based on everything above. "
                "Do not call any more tools."
            )
        )
    )
    final = _invoke_with_retry(llm, messages, retries=0)
    if final is None:
        return "AI rate limit reached. Wait 1 minute and try again."
    return _extract_text(final.content) or None

# BEFORE: nothing here

# AFTER:
def _preflight_schema_search(question: str, role: str) -> str:
    try:
        result = search_schema.invoke({"query": question, "role": role})
        return str(result) if result else "No matching schema candidates found."
    except Exception as e:
        return f"Schema discovery failed: {e}"
def ask_agent(
    question: str,
    db_name: str = "hospital_demo",
    chat_history: list = None,
    is_premium: bool = False,
    role: str = "viewer",
    hospital_name: str = "Demo Hospital",
    db_server: str = None,
    db_user: str = None,
    db_password: str = None,
):
    if chat_history is None:
        chat_history = []
    if chat_history and len(chat_history) > MAX_HISTORY:
        chat_history = chat_history[-MAX_HISTORY:]

    # ========== GUARDRAILS (INPUT) ==========
    ok, msg = check_input(question)
    if not ok:
        return msg
    

    # ---- Deterministic dashboards (do not rely on LLM tool choice) ----
    q = (question or "").strip().lower()

    DEPT_KEYWORDS = [
        "radiology", "haematology", "hematology", "heamatology", "biochemistry",
        "microbiology", "histopathology", "cytology", "cytogenetics",
        "endoscopy", "serology", "hormones", "pathology",
        "2d echo", "ecg", "tmt", "colonoscopy", "mammography", "ultrasound",
        "ct scan", "mri", "doppler", "opg", "pft",
    ]
    from agent.intents import try_intent
    intent_answer = try_intent(question, role, db_name, db_server, db_user, db_password)
    if intent_answer is not None:
        return check_output(intent_answer)
    is_dashboard = ("dashboard" in q and "tat" not in q and "turnaround" not in q and "turn around" not in q) or q in ("radiology", "laboratory", "lab")
    is_tat_compliance = ("tat" in q or "turnaround" in q) and any(
        kw in q for kw in ["compliance", "below", "above", "threshold", "target"]
    )
    if is_premium and is_tat_compliance:
        m = re.search(r"(\d+(?:\.\d+)?)\s*%", q)
        threshold = float(m.group(1)) if m else 80.0
        period, _ = parse_dashboard_period(q)
        raw = check_tat_alert.invoke({
            "threshold_pct": threshold, "period": period, "role": role,
            "db_name": db_name, "db_server": db_server, "db_user": db_user, "db_password": db_password,
        })
        return check_output(raw if isinstance(raw, str) else str(raw))

    is_zero_collection = "zero collection" in q or ("zero" in q and "collection" in q)
    if is_premium and is_zero_collection:
        from datetime import date as _date, timedelta as _td
        target_date = (_date.today() - _td(days=1)).isoformat() if "yesterday" in q else _date.today().isoformat()
        raw = check_zero_collection_alert.invoke({
            "date_str": target_date, "role": role,
            "db_name": db_name, "db_server": db_server, "db_user": db_user, "db_password": db_password,
        })
        return check_output(raw if isinstance(raw, str) else str(raw))
    if is_premium and is_dashboard:
        matched = [d for d in DEPT_KEYWORDS if d in q]
        if matched:
            dept = matched[0]
        elif "lab" in q:
            dept = "laboratory"
        else:
            dept = "all"
        period, _label = parse_dashboard_period(q)
        import re as _re
        location_guess = q
        strip_words = DEPT_KEYWORDS + [
            "dashboard", "lab", "laboratory", "today", "yesterday",
            "this month", "last month", "this year", "last year",
            "this week", "last week", "month", "year","tat", "turnaround", "turn around", 
            "turn around time",
            "january", "february", "march", "april", "may", "june", "july",
            "august", "september", "october", "november", "december",
            "jan", "feb", "mar", "apr", "jun", "jul", "aug",
            "sep", "sept", "oct", "nov", "dec",
        ]
        # sort longest-first so "january" matches before the shorter "jan"
        # ever gets a chance to eat part of it
        for w in sorted(strip_words, key=len, reverse=True):
            location_guess = _re.sub(rf"\b{_re.escape(w)}\b", " ", location_guess, flags=_re.IGNORECASE)
        location_guess = _re.sub(r"\d+(st|nd|rd|th)?", " ", location_guess)
        location_guess = location_guess.strip() or None
        print(f"[ask_agent] FORCED dashboard tool dept={dept} period={period} location={location_guess}")
        raw = get_department_dashboard.invoke({
            "department": dept,
            "period": period,
            "location": location_guess,
            "role": role,
            "db_name": db_name,
            "db_server": db_server,
            "db_user": db_user,
            "db_password": db_password,
        })
        return check_output(raw if isinstance(raw, str) else str(raw))
# ---- end forced dashboard ----
    # =======================================

    if is_premium:
        try:
            role_enum = Role(role)
        except ValueError:
            return check_output(f"Unknown role '{role}'.")

        allowed_tables = list_allowed_tables_for_role(role_enum)
        # allowed_tables_str (a full comma-joined list of every allowed
        # table name) used to be dumped into the prompt directly — removed
        # since search_schema now handles table discovery, and the real
        # access enforcement was always in check_table_access/
        # check_query_access, never the prompt text itself. allowed_tables
        # (the underlying set) is still needed below for schema_hints.

        # Built HERE only (after allowed_tables exists)
        schema_hints = schema_hint_for_prompt(
            list(allowed_tables) if allowed_tables else []
        )

        from datetime import date as _date
        real_today = _date.today().isoformat()

        system_prompt = f"""
You are Sahasra AI Assistant for {hospital_name}. Answer ONLY using data
from the hospital database. Never invent table/column names or numbers.

TODAY'S REAL DATE: {real_today}. Use this for any relative date ("today",
"yesterday", "this month", etc) — never your own sense of the current
date (confirmed to produce dates years off). Prefer SQL's own GETDATE/
DATEADD/DATEDIFF over writing a literal date yourself; if you must write
one, derive it from {real_today}.

TOPIC BOUNDARY: only answer questions about {hospital_name}'s data —
patients, admissions, labs, pharmacy, billing/collections, doctors,
staff, inventory, branches/locations, reconciliation, cash in hand, and
similar operations topics (these count even if not clinical). A short
fragment naming a department ("radiology", "billing") is in-scope, don't
refuse for brevity. For anything genuinely unrelated (shopping,
entertainment, trivia, weather, sports, coding help, other businesses),
decline with: "I can only help with questions about {hospital_name}'s
hospital data. That's outside what I can answer here." — no tool calls
for those. When in doubt, treat as in-scope.

Current user role: {role}

Your table access is enforced automatically by search_schema/
describe_table/run_sql_query — you don't need a full allowed-table list,
just use search_schema to find what's relevant. If a table isn't
accessible, the tool says so plainly.

### Schema guidance
{schema_hints}
Lab/radiology/laboratory dashboard questions → call get_department_dashboard
(department=radiology|laboratory|all, period=today|yesterday|this_month|
this_year|any_year). Don't write raw SQL for these.

Specific-location collection/revenue over a date range → call
get_verified_day_collection instead of raw SQL (hand-verified, avoids
wrong-column guesses). Pass "today"/"yesterday"/"this_month_start"/
"this_year_start" literally as the date value — don't compute a real
date yourself, the tool resolves these against the real server clock.

### Schema discovery
A PRE-VERIFIED SCHEMA SEARCH RESULT for this question is already
included below — don't re-run search_schema unless it's empty or
clearly wrong. Otherwise: search_schema (find tables) → describe_table
on every table you'll reference, including joined/subquery tables, never
guess a column just because you described a different table → write the
query with only verified real column names → run_sql_query → answer.
Table names are cryptic; never guess from memory.

### Rules
- SELECT only, never INSERT/UPDATE/DELETE/DROP. No markdown tables.
- Date filters: always >= start_of_day AND < start_of_next_day, never
  BILLDATE = single_date.
- If a tool returns an access-denied/error, explain plainly, don't invent.
- Never write vague filler with no real numbers — if data isn't found
  yet, try a more specific table, or say exactly what's missing.
- A genuine zero result: state it plainly, don't invent a speculative
  reason. Double-check you're filtering on exact values seen from
  describe_table/an earlier query before concluding zero is real.

### Answer style — three formats

**Format A — dashboard-card.** MANDATORY for any dashboard/overview/
summary/snapshot question, or any answer with 3+ key numbers together.
Output ONLY the fenced block below, real numbers only, nothing outside it:

```dashboard-card
{{
  "icon": "🩻", "title": "Radiology Dashboard", "subtitle": "Today",
  "meta": [{{"icon": "📍", "text": "All Branches"}}, {{"icon": "📅", "text": "Today (01 Sep 2026)"}}],
  "stats": [
    {{"label": "PROCEDURES", "value": "174"}},
    {{"label": "COMPLETED", "value": "151"}},
    {{"label": "REPORTING PEND.", "value": "23"}},
    {{"label": "AVG TAT", "value": "72 min"}}
  ],
  "bar_section": {{
    "title": "Modality Mix", "subtitle": "(procedures · revenue)",
    "rows": [
      {{"label": "X-Ray", "value": 68, "extra": "₹58,800"}},
      {{"label": "Ultrasound", "value": 42, "extra": "₹72,400"}}
    ]
  }},
  "callout": {{"label": "Worst dept", "text": "Microbiology — 78% compliance", "delta": "-13", "delta_label": " pts"}},
  "footer": {{"label": "Radiology Revenue", "value": "₹2,42,800"}}
}}
```
Field notes: `stats` always present (3-10+ items, wraps automatically).
`meta`/`bar_section`/`callout`/`footer` all optional — omit any you don't
have real data for, don't invent one to fill the shape. `bar_section.value`
must be a plain number (for bar width); put formatted text in `extra`.
Never truncate a `label` with "..." — write it in full, it wraps itself.
Nothing outside the fenced block for this format.

**Format C — list-card.** MANDATORY for a list of individual records
(patients, doctors, bills) with a few fields each — never Format A for this.
```list-card
{{
  "icon": "🧑‍🤝‍🧑", "title": "Recent Patients",
  "intro": "Here are the 10 most recent patients registered:",
  "items": [
    {{"primary": "C MANASA", "fields": ["Age: 34", "Gender: F", "Registered: 2026-09-07", "Phone: 7207249339"]}}
  ]
}}
```
`primary` = full name, never truncated. `fields` = short facts, omit a
field entirely if the record doesn't have it (don't write "not available").
`intro`/`footer` optional.

**Format B — plain text.** For a single value, yes/no, explanation, or
refusal — nothing else fits A or C.
- One emoji + **bold title** matching the subject (💰 revenue, 🧑‍🤝‍🧑
  patients, 🧪 labs, ⏳ pending, ⏱️ TAT, 🚨 critical, 👨‍⚕️ doctors, 📊 general).
- Key numbers on one line with " · " between them.
- Breakdowns as short bullets with value + %.
- Comparisons always show direction (▲/▼), never a bare number.
- **bold** numbers/labels, *italic* only for a genuinely useful caveat.
- Compact — no padding sentences. Example (Kukatpally today's collection):

💰 **Revenue & Collection** · Kukatpally · Today
**Gross:** ₹85,000 · **Net:** ₹78,200 · **Collected:** ₹74,500

• **Cash:** ₹28,200 (38%)
• **UPI:** ₹32,700 (44%)

▲8.4% vs yesterday

### Efficiency
- At most 1 describe_table call unless truly needed. Never SELECT * on
  large tables. Keep answers short.
- LIST/browse questions → SELECT TOP 10, most recent first.
- TOTAL/SUM/COUNT/AVERAGE questions → never TOP 10 (returns raw rows, not
  an aggregate — gives a near-zero wrong answer). Use SUM/COUNT/AVG with
  the right WHERE/date filter over the full matching range.
- Comparison questions ("X vs Y") → call the same tool twice, once per
  location/department, present both together.
- Broad/ambiguous question with no clear list-vs-total intent → ask for a
  filter, or return TOP 10 recent rows.
"""

        tools = [search_schema, describe_table, run_sql_query, get_verified_day_collection, get_department_dashboard, get_lab_day_collection, get_tat_compliance_dashboard, check_zero_collection_alert,check_tat_alert]
        tools_by_name = {t.name: t for t in tools}
        llm_with_tools = llm.bind_tools(tools)

        #messages = [SystemMessage(content=system_prompt)]
        #messages.extend(chat_history)

        # Deterministic schema discovery BEFORE the LLM starts tool calling
        messages = [SystemMessage(content=system_prompt)]
        messages.extend(chat_history)

        schema_result = _preflight_schema_search(question, role)
        messages.append(SystemMessage(content=(
            "PRE-VERIFIED SCHEMA SEARCH RESULT (already run for this "
            "question — do not call search_schema again unless this "
            f"is empty or clearly doesn't cover what you need):\n{schema_result}\n\n"
            "Use these real schema candidates. Do not invent tables or columns."
        )))

        question_lower = question.lower()
        wants_dashboard_card = any(
            kw in question_lower for kw in [
                "dashboard", "overview", "summary", "snapshot",
                "collection", "revenue", "day collection",
            ]
        ) and not any(kw in question_lower for kw in ["tat", "turnaround", "turn around"])
        wants_list_card = (not wants_dashboard_card) and any(
            kw in question_lower for kw in ["recent", "top ", "list ", "show me all", "show all"]
        )
        mentions_department = any(
            kw in question_lower for kw in ["radiology", "pathology", "microbiology", "cardiology", "biochemistry"]
        )
        
        mentions_billing_terms = any(
            kw in question_lower for kw in [
                "reconciliation", "cash in hand", "due amount", "concession",
            ]
        )
        mentions_tat = any(kw in question_lower for kw in ["tat", "turnaround", "turn around"])
        mentions_tat_compliance = mentions_tat and any(
            kw in question_lower for kw in ["compliance", "below", "above", "%", "threshold", "target"]
        )
        mentions_no_followup = any(
            kw in question_lower for kw in ["no follow-up", "never came back", "didn't return", "haven't returned"]
        )
        mentions_doctor_unpaid = ("doctor" in question_lower) and any(
            kw in question_lower for kw in ["unpaid", "pending bill", "due bill", "outstanding bill"]
        )

        user_message = f"User Question: {question}"
        if wants_dashboard_card:
            # Relying on the model to infer "use the card format" from a
            # general rule buried in a long system prompt was not
            # reliable in practice — a real gathered-data answer still
            # came back as plain text. This is a deterministic, targeted
            # reminder attached to THIS specific request instead, right
            # next to the question itself where it can't be missed.
            user_message += (
                "\n\n(This question is asking for a dashboard-style summary. "
                "You MUST respond using the ```dashboard-card fenced JSON "
                "format from your instructions — not plain text, not bullet "
                "points. This is not optional for this question.)"
            )
        elif wants_list_card:
            user_message += (
                "\n\n(This question is asking for a list of individual "
                "records. You MUST respond using the ```list-card fenced "
                "JSON format from your instructions — not plain text, not "
                "numbered bold bullets. This is not optional for this "
                "question.)"
            )
        if mentions_department:
            # Same proven pattern as above: a general "verify DEPTCODE
            # first" rule in the system prompt was not reliably followed
            # — a real query still used DEPTCODE = 'Radiology' with no
            # verification, and separately confused the department name
            # for a location name. Now that the real lookup table has
            # been confirmed (mstdepartment), this points directly at
            # the answer instead of asking the model to rediscover it.
            user_message += (
                "\n\n(This question names a department. NEVER write "
                "DEPTCODE = 'Radiology' or any department name directly — "
                "DEPTCODE is numeric, confirmed via a real profile. Resolve "
                "it through mstdepartment instead: "
                "DEPTCODE = (SELECT DEPARTMENTID FROM mstdepartment WHERE "
                "DEPARTMENTNAME LIKE '%Radiology%'). Do not use mstlabdesc "
                "for this — confirmed empty, 0 rows. Also: a department is "
                "NOT a location — never search trntempdaycollall.LOCATION "
                "for a department name.)"
            )

        if mentions_no_followup:
            user_message += (
                "\n\n(This question needs 'no follow-up' defined concretely before writing SQL — "
                "a real bug: checking 'no later bill exists' matches EVERY patient's most recent "
                "bill trivially, since by definition nothing is later than the latest one. State "
                "which definition you're using — e.g. 'exactly one bill ever' (COUNT(*)=1 per UHID), "
                "or 'no second bill within N days of the first' — and say so in your answer, don't "
                "silently pick one.)"
            )   
        if mentions_doctor_unpaid:
            user_message += (
                "\n\n(NO CONFIRMED JOIN exists from mstdoctor to any billing table — a real bug: "
                "mstdoctor.DOCID = trnmodeofcollectionsdet.PATIENTID was used before, which joins a "
                "doctor ID to a PATIENT ID column, nonsense. describe_table BOTH tables and find a "
                "real shared column before writing this join. If none exists, say so plainly instead "
                "of running an invented join and reporting its result as if it meant something.)"
            )
        if mentions_tat:
            user_message += (
                "\n\n(This question is about TAT/turnaround time. Use EXACTLY this table and "
                "these two columns, nothing else, even if another column exists and the query "
                "would run without erroring: trnparamresult.BILLDATE and trnparamresult.CREATEDATE. "
                "NEVER use trninvlabdet for this (it has no CREATEDATE). NEVER use REFUNDDATE, "
                "EDITDATE, or any other date column as a substitute for CREATEDATE — REFUNDDATE "
                "specifically is about refund processing, not result completion, and has been used "
                "wrongly before. The exact formula, copy it exactly: "
                "AVG(CAST(CASE WHEN DATEDIFF(MINUTE, BILLDATE, CREATEDATE) BETWEEN 0 AND 10080 "
                "THEN DATEDIFF(MINUTE, BILLDATE, CREATEDATE) END AS BIGINT)) FROM trnparamresult. "
                "This is not optional for this question.)"
            )
        if mentions_tat_compliance:
            user_message += (
                "\n\n(This question is about TAT COMPLIANCE specifically, not "
                "plain average TAT. You MUST call the check_tat_alert or "
                "get_tat_compliance_dashboard TOOL for this — never compute "
                "compliance from raw SQL. The 10080-minute bound is an outlier "
                "safety limit, NOT a real SLA, and has nothing to do with "
                "compliance percentage. This is not optional for this question.)"
            )
        messages.append(HumanMessage(content=user_message))

        answer = _run_tool_loop(
            llm_with_tools,
            messages,
            tools_by_name,
            tool_extra_kwargs={
                "run_sql_query": {
                    "role": role, "db_name": db_name,
                    "db_server": db_server, "db_user": db_user, "db_password": db_password,
                },
                "describe_table": {
                    "role": role, "db_name": db_name,
                    "db_server": db_server, "db_user": db_user, "db_password": db_password,
                },
                "get_verified_day_collection": {
                    "role": role, "db_name": db_name,
                    "db_server": db_server, "db_user": db_user, "db_password": db_password,
                },"get_lab_day_collection": {
                    "role": role, "db_name": db_name,
                    "db_server": db_server, "db_user": db_user, "db_password": db_password,
                },
                "get_tat_compliance_dashboard": {
                "role": role, "db_name": db_name,
                "db_server": db_server, "db_user": db_user, "db_password": db_password,
            },
                "check_tat_alert": {
                                "role": role, "db_name": db_name,
                                "db_server": db_server, "db_user": db_user, "db_password": db_password,
                            },
                "check_zero_collection_alert": {
                                "role": role, "db_name": db_name,
                                "db_server": db_server, "db_user": db_user, "db_password": db_password,
                            },
                "search_schema": {"role": role},
            }
        )
        if not answer:
            answer = "I could not find relevant data."

        return check_output(answer)

    else:
        # NORMAL MODE
        normal_prompt = """
You are Sahasra AI Assistant.
You help users with questions about hospitals, doctors, specialties and healthcare in India.

### Topic boundary (strict):
You ONLY answer questions about hospitals, doctors, medical specialties,
diagnostics, pharmacy, and healthcare topics. If a question is unrelated
(e.g. shopping malls, entertainment, general trivia, weather, sports,
coding help, or any other non-healthcare topic), do NOT answer it, even
if you know the answer or could search for it — politely decline with:
"I can only help with hospital and healthcare-related questions." Do not
call web_search for an off-topic question.

You have a tool called "web_search" to find real and current information.

Rules:
- Use the web_search tool when the user asks about specific hospitals, doctors, ratings, or locations.
- If your first search doesn't return enough to answer well, try again with a
  more specific or differently-worded query before giving up.
- After getting search results, give a clean, helpful summary.
- Use **bold** for key names/numbers, bullet points, and one light relevant emoji at the start.
- Never invent doctor names.
- Never use markdown tables.
"""
        tools = [web_search]
        tools_by_name = {t.name: t for t in tools}
        llm_with_tools = llm.bind_tools(tools)

        messages = [SystemMessage(content=normal_prompt)]
        messages.extend(chat_history)
        messages.append(HumanMessage(content=question))

        answer = _run_tool_loop(llm_with_tools, messages, tools_by_name)
        if not answer:
            answer = "I could not find an answer."

        return check_output(answer)