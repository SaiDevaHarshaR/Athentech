ROLE_PREFIX = {
    "admin": "ADMIN",
    "doctor": "DOC",
    "nurse": "NURSE",
    "lab_tech": "LAB",
    "pharmacist": "PHARM",
    "reception": "RECEP",
    "viewer": "VIEW"
}

def normalize_phone(phone: str) -> str:
    digits = "".join([c for c in str(phone) if c.isdigit()])
    return digits

def make_unique_id(phone: str, dob_year: str) -> str:
    """
    Unique part:
    - 2 to 3 digits from phone
    - 2 digits from DOB year
    No random.
    """
    phone_digits = normalize_phone(phone)
    year = str(dob_year).strip()

    if len(phone_digits) < 3:
        raise ValueError("Phone must have at least 3 digits")

    if len(year) < 2:
        raise ValueError("DOB year invalid")

    # Use last 3 phone digits + last 2 of year
    phone_part = phone_digits[-3:]   # 3 digits from phone
    year_part = year[-2:]            # 2 digits from DOB year

    return f"{phone_part}{year_part}"

def generate_activation_code(client_prefix: str, role: str, phone: str, dob_year: str) -> str:
    role_key = role.strip().lower().replace(" ", "_")
    role_prefix = ROLE_PREFIX.get(role_key)
    if not role_prefix:
        raise ValueError(f"Unsupported role: {role}")

    unique = make_unique_id(phone, dob_year)
    client = client_prefix.strip().upper()

    # Final format: CLIENT-ROLE-UNIQUE
    return f"{client}-{role_prefix}-{unique}"