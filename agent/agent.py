from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from agent.tools import run_sql_query
from agent.search_tool import web_search
from agent.guardrails import check_input, check_output
from config import settings
from auth.roles import Role, get_allowed_tables

llm = ChatGroq(
    model="openai/gpt-oss-20b",
    temperature=0,
    api_key=settings.groq_api_key
)

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
        allowed_tables = ', '.join(sorted(get_allowed_tables(Role(role))))

        system_prompt = f"""
You are Sahasra AI Assistant for {hospital_name}.
You can ONLY answer using data from the hospital database.
Never invent any information.

Current user role: {role}
Allowed tables for this role: {allowed_tables}

You have a tool called "run_sql_query".
You MUST use this tool to answer any question about patients or admissions.

### Exact Database Schema (use ONLY these columns):

Table: patients
- uhid
- patient_name
- age
- gender
- registration_date

Table: admissions
- admission_id
- uhid
- admission_date
- department
- doctor_name
- status

### Rules:
- Only write SELECT queries
- Use ONLY the columns listed above
- Do NOT use ward_id, bed_number, phone, blood_group or any other column
- Always use the tool when data is needed
- Format the final answer with bullet points and emojis
- Never use markdown tables
"""

        llm_with_tools = llm.bind_tools([run_sql_query])

        messages = [SystemMessage(content=system_prompt)]
        messages.extend(chat_history)
        messages.append(HumanMessage(
            content=f"Database: {db_name}\nRole: {role}\n\nUser Question: {question}"
        ))

        response = llm_with_tools.invoke(messages)

        if response.tool_calls:
            result = None
            for tool_call in response.tool_calls:
                if tool_call["name"] == "run_sql_query":
                    args = tool_call["args"]
                    args["role"] = role
                    args["db_name"] = db_name

                    result = run_sql_query.invoke(args)

                    messages.append(response)
                    messages.append(ToolMessage(
                        content=str(result),
                        tool_call_id=tool_call["id"]
                    ))

            messages.append(HumanMessage(
                content="Based on the tool result above, give a clear and helpful final answer. Use bullet points and emojis. Do not mention that you received data."
            ))

            final = llm_with_tools.invoke(messages)
            answer = final.content if final.content else str(result)
        else:
            answer = response.content if response.content else "I could not find relevant data."

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
- After getting search results, give a clean, helpful summary.
- Use bullet points and light emojis.
- Never invent doctor names.
- Never use markdown tables.
"""
        llm_with_tools = llm.bind_tools([web_search])
        messages = [SystemMessage(content=normal_prompt)]
        messages.extend(chat_history)
        messages.append(HumanMessage(content=question))

        response = llm_with_tools.invoke(messages)

        if response.tool_calls:
            for tool_call in response.tool_calls:
                if tool_call["name"] == "web_search":
                    result = web_search.invoke(tool_call["args"])
                    messages.append(response)
                    messages.append(ToolMessage(
                        content=str(result),
                        tool_call_id=tool_call["id"]
                    ))
            final = llm_with_tools.invoke(messages)
            answer = final.content if final.content else "No relevant information found."
        else:
            answer = response.content if response.content else "I could not find an answer."

        # ========== GUARDRAILS (OUTPUT) ==========
        return check_output(answer)
        # ========================================