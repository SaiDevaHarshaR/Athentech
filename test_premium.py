from agent.agent import ask_agent

answer = ask_agent(
    question="Show me all patients",
    db_name="hospital_apollo",
    is_premium=True,
    role="doctor",
    hospital_name="Apollo Demo Hospital"
)

print("===== ANSWER =====")
print(answer)