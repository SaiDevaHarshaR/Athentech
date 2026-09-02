from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from agent.tools import run_sql_query, describe_table
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
        return ChatOpenAI(
            model=settings.llm_model,
            temperature=0,
            api_key=settings.openai_api_key,
        )

    from langchain_groq import ChatGroq
    return ChatGroq(
        model=settings.llm_model or "openai/gpt-oss-20b",
        temperature=0,
        api_key=settings.groq_api_key,
    )


llm = _build_llm()
MAX_TOOL_ROUNDS = 2
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


def ask_agent(
    question: str,
    db_name: str = "hospital_demo",
    chat_history: list = None,
    is_premium: bool = False,
    role: str = "viewer",
    hospital_name: str = "Demo Hospital",
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
        allowed_tables_str = (
            ", ".join(allowed_tables) if allowed_tables else "(none mapped yet)"
        )

        # Built HERE only (after allowed_tables exists)
        schema_hints = schema_hint_for_prompt(
            list(allowed_tables) if allowed_tables else []
        )

        system_prompt = f"""
You are Sahasra AI Assistant for {hospital_name}.
You can ONLY answer using data from the hospital database.
Never invent any information, table names, or column names.

### Topic boundary (strict):
You ONLY answer questions about this hospital's data — patients, admissions,
labs, pharmacy, billing/collections, doctors, staff, inventory, branches/
locations/collection centres, and similar hospital/diagnostics/healthcare
BUSINESS OPERATIONS topics. This includes operational/business questions
about the organization itself (e.g. "how many branches do we have",
"which collection centres exist", "top referring doctors") — these are
in scope even though they're not clinical questions.
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

### Tables you are allowed to query (real table names):
{allowed_tables_str}

Any table not in that list will be rejected — do not attempt to query it,
and tell the user plainly if what they're asking about isn't available
to their role or isn't in the system yet.

### Schema guidance
{schema_hints}

### How to answer a data question:
1. Pick the relevant table(s) from the allowed list above.
2. Call "describe_table" on each one FIRST to get its real column names —
   never guess column names, they will not match a generic/demo schema.
3. Call "run_sql_query" with a SELECT statement using only the real
   column names describe_table gave you.
4. Turn the result into a clear, helpful final answer.

### Rules:
- Only SELECT queries — never INSERT/UPDATE/DELETE/DROP etc.
- Never use markdown tables
- If describe_table or run_sql_query returns an access-denied or error
  message, explain that plainly to the user instead of making something up

### Answer style (match this exactly):
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

        tools = [describe_table, run_sql_query]
        tools_by_name = {t.name: t for t in tools}
        llm_with_tools = llm.bind_tools(tools)

        messages = [SystemMessage(content=system_prompt)]
        messages.extend(chat_history)
        messages.append(HumanMessage(content=f"User Question: {question}"))

        answer = _run_tool_loop(
            llm_with_tools,
            messages,
            tools_by_name,
            tool_extra_kwargs={
                "run_sql_query": {"role": role, "db_name": db_name},
                "describe_table": {"role": role, "db_name": db_name},
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