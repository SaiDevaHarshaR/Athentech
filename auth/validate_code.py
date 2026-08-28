import requests
from typing import Optional

def validate_activation_code(code: str) -> Optional[dict]:
    """
    Returns:
    {
        "valid": True,
        "db_name": "hospital_citycare",
        "hospital_name": "City Care Hospital",
        "hospital_id": "HOSP123"
    }
    or None if invalid
    """
    try:
        # Replace with real API later
        response = requests.post(
            "https://api.athentech.in/ai/validate-code",   # ← Ask them for real URL
            json={"activation_code": code},
            timeout=8
        )

        if response.status_code == 200:
            data = response.json()
            if data.get("valid"):
                return data
        return None

    except Exception as e:
        print("Activation code validation failed:", str(e))
        return None

def validate_activation_code_mock(code: str):
    mock_data = {
        "ATH-1001": {
            "valid": True,
            "db_name": "hospital_citycare",
            "hospital_name": "City Care Hospital",
            "hospital_id": "HOSP001"
        },
        "ATH-1002": {
            "valid": True,
            "db_name": "hospital_demo",
            "hospital_name": "Demo Hospital",
            "hospital_id": "HOSP002"
        }
    }
    return mock_data.get(code)