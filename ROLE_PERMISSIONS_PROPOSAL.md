# Role-Based Access — Proposed Default Policy

**Status: PROPOSED DEFAULT, not a confirmed policy.** AthenTech has said
"for each role, we can't determine what data they can see — tough to
say." This document exists so that open question has a concrete
starting point to react to, instead of staying an unresolved blank.

**These are already live** in `auth/roles.py` — the system needs
*something* configured to function, so this is what's active right now.
**They're also fully editable without touching code** — go to the admin
panel → Roles & Permissions, and adjust which categories each role can
see. Changes apply immediately, no redeploy needed.

## What each role can currently see, and why

| Role | Categories | Reasoning |
|---|---|---|
| **Admin** | Everything | AthenTech staff only, per your confirmation that hospitals don't get admin panel access themselves. |
| **Doctor** | Patients, Admissions, Labs, Wards, Doctors | Needs clinical history and lab results for their own patients, plus referring-doctor info. Does NOT currently see billing/pharmacy/inventory/staff — worth confirming whether doctors should see what a patient was billed. |
| **Nurse** | Patients, Admissions, Wards, Labs | Same clinical scope as doctor, minus referring-doctor data (less relevant to nursing workflow). |
| **Lab Tech** | Patients, Labs, Inventory | Needs patient context for the specimen they're processing, plus reagent/equipment stock — a lab tech plausibly needs to know if a reagent is running low. |
| **Pharmacist** | Patients, Pharmacy, Prescriptions, Inventory | Needs to know what's been prescribed and dispensed, plus medicine stock levels. |
| **Reception** | Patients, Admissions, Billing | **Changed from the previous default** — front-desk staff almost universally handle payment collection in this kind of business, so no billing access didn't match real front-desk work. Worth confirming this is actually accurate for AthenTech's staffing model. |
| **Viewer** | Patients only | Most restrictive — a generic read-only/reporting role with no assumption about what else they should see. Was previously identical to Reception; separated out since "front desk staff" and "generic viewer" are different real-world roles that shouldn't automatically have the same access. |

## Specific open questions worth getting a real answer to

1. **Should doctors see billing data for their own patients?** Common in some systems (context for a consult), not in others (kept separate from clinical staff on purpose).
2. **Should reception see labs/clinical data at all**, or strictly registration + billing? Currently they cannot see labs.
3. **Is "Viewer" meant to be a real role anyone uses**, or just a fallback/default for unrecognized roles? If nobody actually holds this role in practice, it matters less what it can see.
4. **Does AthenTech want role permissions to be per-hospital-configurable**, or the same policy enforced identically across all 700 clients? Right now it's one global policy for everyone — if different hospitals want different rules, that's a bigger feature, not just an admin panel edit.

## How to actually change this

No code needed for the common case (adjusting which categories a role can see) — Admin Panel → Roles & Permissions → pick a role → check/uncheck categories → save. Takes effect on the next question asked, no restart required.

If AthenTech wants a role that doesn't exist yet (e.g. "Front Desk Billing Only" as distinct from general "Reception"), that needs a small code change — ask and it can be added.