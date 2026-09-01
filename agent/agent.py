from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage

from agent.tools import run_sql_query, describe_table
from agent.search_tool import web_search
from agent.guardrails import check_input, check_output
from config import settings
from auth.roles import Role
from auth.table_access import list_allowed_tables_for_role

llm = ChatGroq(
    model="openai/gpt-oss-20b",
    temperature=0,
    api_key=settings.groq_api_key
)

MAX_TOOL_ROUNDS = 5  # a chain like describe_table -> run_sql_query, or web_search -> web_search again, gets a few rounds before we force an answer


def _run_tool_loop(llm_with_tools, messages, tools_by_name: dict, tool_extra_kwargs: dict = None):
    """
    Repeatedly invokes the LLM and executes any tool calls it makes,
    feeding results back in, until it stops calling tools or we hit
    MAX_TOOL_ROUNDS. Used by BOTH premium mode (describe_table ->
    run_sql_query can chain) and normal mode (web_search can get called
    more than once for a follow-up search).

    Previously normal mode only ever handled a single round: if the model
    called web_search a second time instead of writing a final answer,
    `final.content` would be empty (it's a tool-call response, not text)
    and the code silently fell back to "No relevant information found" —
    even when the first search had already returned real results. This
    unified loop fixes that for both modes at once.

    tool_extra_kwargs: {tool_name: {kwarg: value}} — extra arguments
    forced onto specific tools' calls (e.g. role/db_name for the SQL
    tools, which must come from the validated license, never from
    whatever the LLM put in its tool-call args). Tools not listed get
    called with exactly the args the LLM provided — needed because
    web_search's signature doesn't accept role/db_name at all.
    """
    tool_extra_kwargs = tool_extra_kwargs or {}
    response = llm_with_tools.invoke(messages)

    for _ in range(MAX_TOOL_ROUNDS):
        if not response.tool_calls:
            return response.content if response.content else None

        messages.append(response)
        for tool_call in response.tool_calls:
            tool_fn = tools_by_name.get(tool_call["name"])
            if not tool_fn:
                result = f"Error: unknown tool '{tool_call['name']}'."
            else:
                args = dict(tool_call["args"])
                args.update(tool_extra_kwargs.get(tool_call["name"], {}))
                result = tool_fn.invoke(args)

            messages.append(ToolMessage(content=str(result), tool_call_id=tool_call["id"]))

        response = llm_with_tools.invoke(messages)

    # Hit the round limit — ask once more for a final answer with no more tool use.
    messages.append(HumanMessage(
        content="Give your best final answer now based on everything above. Do not call any more tools."
    ))
    final = llm.invoke(messages)
    return final.content if final.content else None


def ask_agent(
    question: str,
    db_name: str = "hospital_demo",
    chat_history: list = None,
    is_premium: bool = False,
    role: str = "viewer",
    hospital_name: str = "Demo Hospital"
):
    if chat_history is None:
        chat_history = []

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
        allowed_tables_str = ", ".join(allowed_tables) if allowed_tables else "(none mapped yet)"

        system_prompt = f"""
You are Sahasra AI Assistant for {hospital_name}.
You can ONLY answer using data from the hospital database.
Never invent any information, table names, or column names.

Current user role: {role}

### Tables you are allowed to query (real table names):
{allowed_tables_str}

Any table not in that list will be rejected — do not attempt to query it,
and tell the user plainly if what they're asking about isn't available
to their role or isn't in the system yet.

### How to answer a data question:
1. Pick the relevant table(s) from the allowed list above.
2. Call "describe_table" on each one FIRST to get its real column names —
   never guess column names, they will not match a generic/demo schema.
3. Call "run_sql_query" with a SELECT statement using only the real
   column names describe_table gave you.
4. Turn the result into a clear, helpful final answer.

### Rules:
- Only SELECT queries — never INSERT/UPDATE/DELETE/DROP etc.
- Format the final answer with bullet points and emojis
- Never use markdown tables
- If describe_table or run_sql_query returns an access-denied or error
  message, explain that plainly to the user instead of making something up
"""

        tools = [describe_table, run_sql_query]
        tools_by_name = {t.name: t for t in tools}
        llm_with_tools = llm.bind_tools(tools)

        messages = [SystemMessage(content=system_prompt)]
        messages.extend(chat_history)
        messages.append(HumanMessage(content=f"User Question: {question}"))

        answer = _run_tool_loop(
            llm_with_tools, messages, tools_by_name,
            tool_extra_kwargs={
                "run_sql_query": {"role": role, "db_name": db_name},
                "describe_table": {"role": role, "db_name": db_name},
            }
        )
        if not answer:
            answer = "I could not find relevant data."

        # ========== GUARDRAILS (OUTPUT) ==========
        return check_output(answer)
        # ========================================

    else:
        # NORMAL MODE
        normal_prompt = """
You are Sahasra AI Assistant.
You help users with questions about hospitals, doctors, specialties and healthcare in India.

You have a tool called "web_search" to find real and current information.

Rules:
- Use the web_search tool when the user asks about specific hospitals, doctors, ratings, or locations.
- If your first search doesn't return enough to answer well, try again with a
  more specific or differently-worded query before giving up.
- After getting search results, give a clean, helpful summary.
- Use bullet points and light emojis.
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

        # ========== GUARDRAILS (OUTPUT) ==========
        return check_output(answer)
        # ========================================