from typing import Optional, Dict
from auth.roles import Role

def validate_activation_code_mock(code: str) -> Optional[Dict]:
    """
    Mock validation – replace with real API later.
    Returns role + hospital info.
    """
    mock_data = {
        "ATH-1001": {
            "valid": True,
            "db_name": "hospital_citycare",
            "hospital_name": "City Care Hospital",
            "hospital_id": "HOSP001",
            "role": Role.ADMIN.value,          # ← role comes from backend
            "user_name": "Dr. Admin"
        },
        "ATH-1002": {
            "valid": True,
            "db_name": "hospital_demo",
            "hospital_name": "Demo Hospital",
            "hospital_id": "HOSP002",
            "role": Role.DOCTOR.value,
            "user_name": "Dr. Sharma"
        },
        "ATH-NURSE01": {
            "valid": True,
            "db_name": "hospital_demo",
            "hospital_name": "Demo Hospital",
            "hospital_id": "HOSP002",
            "role": Role.NURSE.value,
            "user_name": "Nurse Priya"
        },
        "ATH-LAB01": {
            "valid": True,
            "db_name": "hospital_demo",
            "hospital_name": "Demo Hospital",
            "hospital_id": "HOSP002",
            "role": Role.LAB_TECH.value,
            "user_name": "Lab Tech Ravi"
        }
    }
    return mock_data.get(code.upper())