from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from agent.tools import run_sql_query, describe_table, get_verified_day_collection, search_schema
from agent.search_tool import web_search
from agent.guardrails import check_input, check_output
from config import settings
from auth.roles import Role
from auth.table_access import list_allowed_tables_for_role
from auth.schema_pack import schema_hint_for_prompt
import time


def _build_llm():
    """
    Builds the chat model based on settings.llm_provider (default "groq").
    OpenAI requires settings.llm_model to be set explicitly in .env.
    """
    provider = (settings.llm_provider or "groq").lower()

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


llm = _build_llm()
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
            if not _is_rate_limit_error(e):
                raise
            if i == retries:
                return None
            time.sleep(20)
    return None


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
            return response.content if response.content else None

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
            if len(result_text) > 2500:
                result_text = result_text[:2500] + "\n...[truncated]"

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
        return response.content if response.content else None

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
    return final.content if final.content else None

def _preflight_schema_search(question: str, role: str) -> str:
    try:
        result = search_schema.invoke({
            "query": question,
            "role": role,
        })

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
You are Sahasra AI Assistant for {hospital_name}.
You can ONLY answer using data from the hospital database.
Never invent any information, table names, or column names.

### TODAY'S REAL DATE: {real_today}
Use this as ground truth for any relative date ("today", "yesterday",
"this month", "last month", "this year"). A real, confirmed production
bug: when asked to compute a relative date, this assistant has produced
dates YEARS in the past (e.g. resolved "last month" as September 2023
instead of the real recent month) — trust ONLY the date given above,
never your own internal sense of the current date, which is not
reliable for this. STRONGLY prefer using SQL's own relative date
functions (GETDATE(), DATEADD, DATEDIFF) over computing and writing a
literal date string yourself — SQL Server's own clock is authoritative
and cannot be wrong the way your own guess can. If you must write a
literal date, derive it from {real_today} above, not from memory.

### Topic boundary (strict):
You ONLY answer questions about this hospital's data — patients, admissions,
labs, pharmacy, billing/collections, doctors, staff, inventory, branches/
locations/collection centres, and similar hospital/diagnostics/healthcare
BUSINESS OPERATIONS topics. This includes operational/business questions
about the organization itself (e.g. "how many branches do we have",
"which collection centres exist", "top referring doctors") — these are
in scope even though they're not clinical questions.
A single word or short fragment naming a department/category (e.g.
"radiology", "billing", "pharmacy") is a request for information about
that department — treat it as in scope and answer it, do NOT refuse it
just because it's short or lacks a full sentence.
If a question is unrelated to this hospital/healthcare/diagnostics
operations entirely (e.g. shopping, entertainment, general trivia,
weather, sports, coding help, other unrelated businesses), do NOT answer
it — politely decline with:
"I can only help with questions about {hospital_name}'s hospital data.
That's outside what I can answer here." Do not call describe_table or
run_sql_query for an off-topic question. If in doubt whether a business/
operations question about THIS organization is in scope, treat it as
in scope rather than refusing.

Current user role: {role}

### Table access
Your access is restricted by role automatically — search_schema only
ever returns tables your role can see, and describe_table/run_sql_query
independently double-check this too. You do NOT need a full list of
every allowed table name to work correctly; use search_schema to find
what's relevant instead of trying to recall table names from memory.
If a table you try turns out not to be accessible, the tool will tell
you plainly — treat that as "not available to this role," not an error
to route around.

### Schema guidance
{schema_hints}

### IMPORTANT — prefer the verified tool when it fits:
If the question is asking for collection/revenue for a SPECIFIC
LOCATION over a date range (e.g. "Kompally's collection today",
"day collection for Kukatpally yesterday"), call
"get_verified_day_collection" INSTEAD of describe_table/run_sql_query.
It uses a fixed, hand-verified query — not one you write — so it
can't make the wrong-column/wrong-value guesses that a freshly written
query has repeatedly made for this exact question type. For the dates,
pass the literal word "today"/"yesterday"/"this_month_start"/
"this_year_start" as the string value — do NOT compute an actual
calendar date yourself, your own sense of the current date is not
reliable for this (it has produced a date years in the past in real
testing) and the tool resolves these words correctly using the real
server clock. Only fall back to describe_table/run_sql_query for
data this tool doesn't cover (other metrics, other question shapes).

### Schema discovery:
Do NOT guess table names from memory or from the allowed-tables list
alone — table names are often cryptic (trninvlabdet, mstdepartment) and
guessing wrong has caused real, confirmed production bugs.

If you don't already know which table contains what's being asked
(you haven't already found it earlier in this conversation):
1. Call "search_schema" with the user's requirement in plain words
   (e.g. "radiology department", "location names", "test completion
   status"). This is plain search over real table categories/columns/
   values — not a guess, and it won't invent anything.
2. Review the returned candidate tables and their match reasons.
3. Call "describe_table" on the relevant candidate(s) to get real
   column names — this means EVERY table you're about to reference,
   including a second table in a subquery or JOIN (e.g. looking up a
   location name in one table while your main query is against
   another) — never guess a column name for any table just because you
   described a different one earlier.
4. Use the verified columns and any known relationships (see Schema
   guidance above) to write the query.
5. Call "run_sql_query" with a SELECT statement using only real,
   verified column names — for every table involved.
6. Turn the result into a clear, helpful final answer.

search_schema = find the right tables · describe_table = verify their
actual columns · run_sql_query = retrieve the actual data. Skip
search_schema only when you already know the exact table from earlier
in this same conversation.

### Rules:
- Only SELECT queries — never INSERT/UPDATE/DELETE/DROP etc.
- Never use markdown tables
- If describe_table or run_sql_query returns an access-denied or error
  message, explain that plainly to the user instead of making something up
- Never write a vague, hedging paragraph that SOUNDS informative but
  contains no real numbers or facts (e.g. "various tests are available,
  but specific names weren't retrieved" — this is not an answer). If you
  haven't actually found the relevant table/data yet, either try
  describe_table on a more specific candidate table first, or say
  PLAINTLY and SPECIFICALLY what's missing: "I don't have a table
  mapped for radiology test details" is useful; a generic paragraph of
  plausible-sounding filler is not, and is worse than admitting the gap.
- When a query legitimately returns zero rows, state that plainly — do
  NOT invent a speculative reason for why (e.g. "this could be due to
  data not being available for future dates" when the date range isn't
  even in the future — you don't actually know why a query returned
  zero rows, so don't guess). If a filter might be the cause (wrong
  location spelling, wrong date format), say that as a possibility to
  check, not as a stated fact. Before concluding zero rows is real,
  double check obvious causes yourself: are you filtering on the exact
  values describe_table/an earlier query showed you (exact location
  name spelling, correct column), not values you assumed?

### Answer style — TWO formats, pick the right one:

**Format A — Dashboard card.** MANDATORY — not a style preference — for
any question calling for a department/area overview with multiple KPIs
and/or a breakdown by category (e.g. "radiology dashboard", "TAT today",
"collection summary", "modality mix", anything with the word
"dashboard"/"overview"/"summary"/"snapshot" in it, or any answer that
would naturally have 3+ key numbers together). If you have gathered
real numbers for multiple stats, you MUST wrap them in the
```dashboard-card format below — do NOT write them as plain bold text
separated by " · " instead, even if that feels like a reasonable
summary. Output ONLY a fenced block like this, with real numbers from
your actual query results — never invented ones:

```dashboard-card
{{
  "icon": "🩻",
  "title": "Radiology Dashboard",
  "subtitle": "Today",
  "stats": [
    {{"label": "PROCEDURES", "value": "174"}},
    {{"label": "COMPLETED", "value": "151"}},
    {{"label": "REPORTING PEND.", "value": "23"}},
    {{"label": "AVG TAT", "value": "72 min"}}
  ],
  "bar_section": {{
    "title": "Modality Mix",
    "subtitle": "(procedures · revenue)",
    "rows": [
      {{"label": "X-Ray", "value": 68, "extra": "₹58,800"}},
      {{"label": "Ultrasound", "value": 42, "extra": "₹72,400"}},
      {{"label": "Mammography", "value": 8, "extra": "₹7,800"}}
    ]
  }},
  "footer": {{"label": "Radiology Revenue", "value": "₹2,42,800"}}
}}
```

Field notes:
- `stats`: the top KPI row(s) — can be as few as 3 or as many as 10+,
  they wrap into rows automatically. Every card should have this.
- `meta`: optional — short icon+text lines under the title for context
  like scope/date, e.g. {{"icon": "📍", "text": "All Branches"}},
  {{"icon": "📅", "text": "Today (01 Sep 2026)"}}.
- `bar_section`: optional — only include when there's a real breakdown
  by category to show. `value` must be a plain NUMBER (used to compute
  proportional bar widths) — put any formatted/currency text in `extra`
  instead. Never truncate a `label` yourself (e.g. "Collection Cent...")
  — always write the full real name in full, even if it's long. The
  card wraps long labels onto a second line automatically; a truncated
  label just hides real information for no reason.
- `callout`: optional — for a single flagged item, e.g.
  {{"label": "Worst dept", "text": "Microbiology — 78% compliance",
  "delta": "-13", "delta_label": " pts"}} (negative delta renders ▼ red,
  positive renders ▲ green).
- `footer`: optional — one closing total/summary line.
- Omit any field you don't have real data for — don't invent a
  bar_section or callout just to fill the shape. A card with just
  `stats` and no breakdown is completely valid — see the second example
  below, a broad multi-metric overview with no bar_section at all:

```dashboard-card
{{
  "icon": "📊",
  "title": "Diagnostics Management Dashboard",
  "meta": [
    {{"icon": "📍", "text": "All Branches"}},
    {{"icon": "📅", "text": "Today (01 Sep 2026)"}}
  ],
  "stats": [
    {{"label": "PATIENTS", "value": "486"}},
    {{"label": "BILLS", "value": "512"}},
    {{"label": "GROSS", "value": "₹8.46L"}},
    {{"label": "NET", "value": "₹7.97L"}},
    {{"label": "COLLECTED", "value": "₹7.12L"}},
    {{"label": "LAB TESTS", "value": "1,842"}},
    {{"label": "RADIOLOGY", "value": "174"}}
  ]
}}
```
- Output NOTHING outside the fenced block for this format — no text
  before or after it.

**Format C — List card.** MANDATORY for any answer listing multiple
individual records (patients, doctors, bills, etc.) with a few fields
each — e.g. "recent patients", "top doctors", "list pending reports".
This is a DIFFERENT shape from Format A (KPI boxes don't make sense for
individual records) — use this instead whenever the answer is
naturally "a numbered list of things, each with a couple of details."
Output ONLY a fenced block, real data only, nothing outside it:

```list-card
{{
  "icon": "🧑‍🤝‍🧑",
  "title": "Recent Patients",
  "intro": "Here are the 10 most recent patients registered:",
  "items": [
    {{"primary": "C MANASA", "fields": ["Age: 34", "Gender: F", "Registered: 2026-09-07", "Phone: 7207249339"]}},
    {{"primary": "B NIRMALLA", "fields": ["Age: 29", "Gender: F", "Registered: 2026-09-07", "Phone: 9553610081"]}}
  ]
}}
```
- `primary`: the record's name/identifier (bold in the rendered card).
  Full name, never truncated with "..." — same reasoning as bar_section
  labels below.
- `fields`: short facts about that record, rendered smaller/lighter.
  Omit a field entirely for a record that doesn't have it (e.g. no
  phone on file) — don't write "Phone: not available".
- `intro`/`footer`: optional short lines above/below the list.

**Format B — Plain text.** Use this for a single value, a yes/no
answer, an explanation, or a refusal — anything that's genuinely just
one thing being said, not a dashboard (Format A) or a list of records
(Format C).
- Start with one emoji + **bold title** matching the subject: 💰 revenue/
  collection, 🧑‍🤝‍🧑 patients, 🧪 labs, ⏳ pending, ⏱️ TAT, 🚨 critical,
  👨‍⚕️ doctors, 📮 outstanding, 📊 general.
- Group key numbers on one line with " · " between them, not one per line.
- Breakdowns (payment mode, department, etc.) as short bullets with value + %.
- Comparisons always show direction: ▲ up / ▼ down, never a bare number.
- **bold** for numbers/labels, *italic* only for a genuinely useful caveat.
- Keep it as compact as the example below — don't pad with extra sentences.

Example of the exact target style, for "today's collection at Kukatpally":

💰 **Revenue & Collection** · Kukatpally · Today
**Gross:** ₹85,000 · **Net:** ₹78,200 · **Collected:** ₹74,500

• **Cash:** ₹28,200 (38%)
• **UPI:** ₹32,700 (44%)
• **Card:** ₹13,600 (18%)

▲8.4% vs yesterday

### Efficiency rules (mandatory):
- Use at most 1 describe_table call unless absolutely needed
- Select only needed columns, never SELECT * on large tables
- Keep answers short
- For LIST/browse questions ("show me recent patients", "list pending reports"):
  use SELECT TOP 10, most recent first.
- For TOTAL/SUM/COUNT/AVERAGE questions ("total revenue", "how many patients",
  "average TAT"): do NOT use TOP 10 — TOP 10 only returns 10 raw rows, not
  an aggregate, and will give a wrong (usually near-zero) answer for a total.
  Use SQL aggregate functions (SUM/COUNT/AVG/etc.) with the appropriate
  WHERE/date filter over the FULL matching range instead.
- If a question is broad with no clear list-vs-total intent (like "payment
  details"), ask for a filter OR return TOP 10 recent rows only.
"""

        tools = [search_schema, describe_table, run_sql_query, get_verified_day_collection]
        tools_by_name = {t.name: t for t in tools}
        llm_with_tools = llm.bind_tools(tools)

        messages = [SystemMessage(content=system_prompt)]
        messages.extend(chat_history)

        # Deterministic schema discovery BEFORE the LLM starts tool calling
        schema_result = _preflight_schema_search(question, role)

        messages.append(
            SystemMessage(
                content=(
                    "PRE-VERIFIED SCHEMA SEARCH RESULT:\n"
                    f"{schema_result}\n\n"
                    "Use these real schema candidates. Do not invent tables or columns."
                )
            )
        )

        question_lower = question.lower()
        wants_dashboard_card = any(
            kw in question_lower for kw in [
                "dashboard", "overview", "summary", "snapshot",
                "collection", "revenue", "day collection",  # KPI+breakdown shaped, same as an explicit "dashboard" ask
            ]
        )
        wants_list_card = (not wants_dashboard_card) and any(
            kw in question_lower for kw in ["recent", "top ", "list ", "show me all", "show all"]
        )
        mentions_department = any(
            kw in question_lower for kw in ["radiology", "pathology", "microbiology", "cardiology", "biochemistry"]
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
                },
                "search_schema": {"role": role},
            },
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