from enum import Enum
from typing import Dict, Set

class Role(str, Enum):
    ADMIN = "admin"
    DOCTOR = "doctor"
    NURSE = "nurse"
    LAB_TECH = "lab_tech"
    PHARMACIST = "pharmacist"
    RECEPTION = "reception"
    VIEWER = "viewer"


ROLE_PERMISSIONS: Dict[Role, Set[str]] = {
    Role.ADMIN: {
        "patients", "admissions", "labs", "pharmacy", "wards",
        "prescriptions", "doctors", "staff", "billing", "inventory"
    },
    Role.DOCTOR: {
        "patients", "admissions", "labs", "wards"
    },
    Role.NURSE: {
        "patients", "admissions", "wards", "labs"
    },
    Role.LAB_TECH: {
        "patients", "labs"
    },
    Role.PHARMACIST: {
        "patients", "pharmacy", "prescriptions"
    },
    Role.RECEPTION: {
        "patients", "admissions"
    },
    Role.VIEWER: {
        "patients", "admissions"
    }
}


def get_allowed_tables(role: Role) -> Set[str]:
    return ROLE_PERMISSIONS.get(role, set())


def can_access_table(role: Role, table_name: str) -> bool:
    return table_name.lower() in get_allowed_tables(role)