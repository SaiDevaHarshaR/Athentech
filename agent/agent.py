from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from agent.tools import run_sql_query
from agent.search_tool import web_search
from agent.prompts import SYSTEM_PROMPT
from config import settings

llm = ChatGroq(
    model="openai/gpt-oss-20b",
    temperature=0,
    api_key=settings.groq_api_key
)

# Tools
db_tool = run_sql_query
search_tool = web_search

def ask_agent(question: str, db_name: str = "hospital_demo", chat_history: list = None, is_premium: bool = False):
    if chat_history is None:
        chat_history = []

    if is_premium:
        # ========== PREMIUM MODE (Database only) ==========
        llm_with_tools = llm.bind_tools([db_tool])
        
        messages = [SystemMessage(content=SYSTEM_PROMPT)]
        for msg in chat_history:
            messages.append(msg)

        full_question = f"Database: {db_name}\n\nUser Question: {question}"
        messages.append(HumanMessage(content=full_question))

        response = llm_with_tools.invoke(messages)

        if response.tool_calls:
            for tool_call in response.tool_calls:
                if tool_call["name"] == "run_sql_query":
                    result = db_tool.invoke(tool_call["args"])
                    messages.append(response)
                    messages.append({
                        "role": "tool",
                        "content": result,
                        "tool_call_id": tool_call["id"]
                    })
                    final = llm_with_tools.invoke(messages)
                    return final.content

        return response.content

    else:
        # ========== NORMAL MODE (Web Search) ==========
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

        llm_with_tools = llm.bind_tools([search_tool])

        messages = [SystemMessage(content=normal_prompt)]
        for msg in chat_history:
            messages.append(msg)

        messages.append(HumanMessage(content=question))

        response = llm_with_tools.invoke(messages)

        if response.tool_calls:
            for tool_call in response.tool_calls:
                if tool_call["name"] == "web_search":
                    result = search_tool.invoke(tool_call["args"])
                    messages.append(response)
                    messages.append({
                        "role": "tool",
                        "content": result,
                        "tool_call_id": tool_call["id"]
                    })
                    final = llm_with_tools.invoke(messages)
                    return final.content

        return response.content