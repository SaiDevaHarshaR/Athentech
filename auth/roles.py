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


# DEFAULT role permissions — a reasonable starting point, NOT a confirmed
# policy from AthenTech. "For each role, we can't determine what data
# they can see — tough to say" is a real open question on their end;
# this is a documented proposal to review, not an assumption to trust
# blindly. See ROLE_PERMISSIONS_PROPOSAL.md for the reasoning behind
# each role, and change these via the admin panel's Roles & Permissions
# page once AthenTech actually confirms a policy — no code change or
# redeploy needed for that, it's a live-editable setting.
ROLE_PERMISSIONS: Dict[Role, Set[str]] = {
    Role.ADMIN: {
        "patients", "admissions", "labs", "pharmacy", "wards",
        "prescriptions", "doctors", "staff", "billing", "inventory"
    },
    Role.DOCTOR: {
        "patients", "admissions", "labs", "wards", "doctors"
    },
    Role.NURSE: {
        "patients", "admissions", "wards", "labs"
    },
    Role.LAB_TECH: {
        "patients", "labs", "inventory"
    },
    Role.PHARMACIST: {
        "patients", "pharmacy", "prescriptions", "inventory"
    },
    Role.RECEPTION: {
        "patients", "admissions", "billing"
    },
    Role.VIEWER: {
        "patients"
    }
}


def get_allowed_tables(role: Role) -> Set[str]:
    return ROLE_PERMISSIONS.get(role, set())


def can_access_table(role: Role, table_name: str) -> bool:
    return table_name.lower() in get_allowed_tables(role)