from agent.agent import ask_agent
from langchain_core.messages import HumanMessage, AIMessage
import time
def test_role(role: str, question: str, activation_code: str = "ATH-1002"):
    print(f"\n{'='*60}")
    print(f"ROLE: {role.upper()}  |  Question: {question}")
    print('='*60)
    
    answer = ask_agent(
        question=question,
        db_name="hospital_demo",
        is_premium=True,
        role=role,
        hospital_name="Demo Hospital"
    )
    print(answer)
    print()


if __name__ == "__main__":
    # ========== DOCTOR TESTS ==========
    test_role("doctor", "Show me all current admissions")
    test_role("doctor", "List all pending lab tests")
    test_role("doctor", "How many beds are available in ICU?")
    test_role("doctor", "Show pharmacy stock of Paracetamol")   # Should be denied

    # ========== NURSE TESTS ==========
    test_role("nurse", "Show all patients in Cardiology ward")
    test_role("nurse", "List patients with pending labs")
    test_role("nurse", "Show full pharmacy inventory")          # Should be denied

    # ========== LAB TECH TESTS ==========
    test_role("lab_tech", "Show all pending lab tests")
    test_role("lab_tech", "Show current admissions")            # Should be denied

    # ========== PHARMACIST TESTS ==========
    test_role("pharmacist", "Show medicines with low stock")
    test_role("pharmacist", "List pending prescriptions")
    test_role("pharmacist", "Show all lab results")             # Should be denied

    # ========== ADMIN TESTS ==========
    test_role("admin", "Give me a complete summary of wards, labs and pharmacy")


def test_role(role: str, question: str, activation_code: str = "ATH-1002"):
    print(f"\n{'='*60}")
    print(f"ROLE: {role.upper()}  |  Question: {question}")
    print('='*60)
    
    answer = ask_agent(
        question=question,
        db_name="hospital_demo",
        is_premium=True,
        role=role,
        hospital_name="Demo Hospital"
    )
    print(answer)
    print()
    time.sleep(3)          # ← wait 3 seconds between calls