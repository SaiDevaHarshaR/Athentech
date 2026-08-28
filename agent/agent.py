from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.tools import tool
from agent.tools import run_sql_query
from agent.prompts import SYSTEM_PROMPT
from config import settings
import json

# Initialize LLM
llm = ChatGroq(
    model="openai/gpt-oss-20b",
    temperature=0,
    api_key=settings.groq_api_key
)

# Bind the tool
llm_with_tools = llm.bind_tools([run_sql_query])

def ask_agent(question: str, db_name: str = "hospital_demo", chat_history: list = None):
    if chat_history is None:
        chat_history = []

    messages = [SystemMessage(content=SYSTEM_PROMPT)]
    
    # Add previous chat history
    for msg in chat_history:
        messages.append(msg)

    # Add current question
    full_question = f"Database name is: {db_name}\n\nQuestion: {question}"
    messages.append(HumanMessage(content=full_question))

    # First call to LLM
    response = llm_with_tools.invoke(messages)

    # If the model wants to call a tool
    if response.tool_calls:
        for tool_call in response.tool_calls:
            if tool_call["name"] == "run_sql_query":
                # Run the SQL tool
                sql_result = run_sql_query.invoke(tool_call["args"])
                
                # Add tool result back to conversation
                messages.append(response)
                messages.append({
                    "role": "tool",
                    "content": sql_result,
                    "tool_call_id": tool_call["id"]
                })

                # Get final answer
                final_response = llm_with_tools.invoke(messages)
                return final_response.content

    # If no tool was needed
    return response.content