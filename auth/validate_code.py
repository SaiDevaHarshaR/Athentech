def validate_activation_code_mock(code: str):
    codes = {
        # City Care Hospital
        "ATH-ADMIN-001": {
            "valid": True,
            "role": "admin",
            "db_name": "hospital_demo",
            "hospital_name": "City Care Hospital"
        },
        "ATH-DOC-001": {
            "valid": True,
            "role": "doctor",
            "db_name": "hospital_demo",
            "hospital_name": "City Care Hospital"
        },
        "ATH-NURSE-001": {
            "valid": True,
            "role": "nurse",
            "db_name": "hospital_demo",
            "hospital_name": "City Care Hospital"
        },

        # Apollo Demo Hospital
        "ATH-ADMIN-002": {
            "valid": True,
            "role": "admin",
            "db_name": "hospital_apollo",
            "hospital_name": "Apollo Demo Hospital"
        },
        "ATH-DOC-002": {
            "valid": True,
            "role": "doctor",
            "db_name": "hospital_apollo",
            "hospital_name": "Apollo Demo Hospital"
        },

        # Generic viewer
        "ATH-1001": {
            "valid": True,
            "role": "viewer",
            "db_name": "hospital_demo",
            "hospital_name": "City Care Hospital"
        }
    }

    return codes.get(code.upper())