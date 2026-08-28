from agent.agent import ask_agent
from langchain_core.messages import HumanMessage, AIMessage

print("===== FIRST QUESTION =====")
question1 = "Show me all patients with their age and gender"
answer1 = ask_agent(question1)
print(answer1)

print("\n===== FOLLOW-UP QUESTION =====")
# Now we pass the previous conversation as history
history = [
    HumanMessage(content=question1),
    AIMessage(content=answer1)
]

question2 = "Who among them is the oldest?"
answer2 = ask_agent(question2, chat_history=history)
print(answer2)