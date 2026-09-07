# Sahasra AI Agent — Internal Runbook

Operational steps for the common tasks an AthenTech admin actually does.
Not user-facing — this is for whoever operates the system day to day.

---

## Add a new hospital

1. Get the hospital's real database connection details from their DBA:
   server address, database name, and a **read-only** SQL login
   (username + password) — never use `sa` or any write-capable login
   for a hospital's live database.
2. Admin Panel → Institute Registry → Add Institution.
3. Fill in:
   - **Institution Name** / **Code** — code becomes part of every
     activation code for this hospital, keep it short and unique.
   - **Database Name** — the exact real database name on their server.
   - **DB Server** — `host,port` format, e.g. `192.168.1.50,1433`.
   - **DB Username** / **DB Password** — the read-only login from
     step 1. Stored encrypted automatically.
4. Save. Generate at least one activation code for them (see below)
   before considering the hospital "live."
5. **Verify before handing over the code** — ask the agent a couple of
   real questions using that code (e.g. "show me all patients",
   "today's collection") to confirm the connection actually works and
   the schema matches what's expected. Don't assume it's fine just
   because the save succeeded.

## Generate an activation code

1. Admin Panel → License Management → Generate License.
2. Pick the institution, the role (admin/doctor/nurse/lab_tech/
   pharmacist/reception/viewer), and enter the requesting person's
   phone number + birth year (these feed into the code itself).
3. The generated code is shown once — copy it immediately, there's no
   "show password" toggle for codes stored this way.
4. Hand the code to the hospital through a secure channel — not an
   unencrypted email or a public Slack channel. It's equivalent to a
   password.

## Rotate a hospital's database password

Needed if: the hospital's DBA rotates their own credentials, or you
suspect a code/credential may have leaked.

1. Get the new password from the hospital's DBA first — don't lock
   yourself out by changing it here before it's actually changed on
   their SQL Server.
2. Admin Panel → Institute Registry → Edit (the institution) → update
   **DB Password** → Save.
3. Test immediately with a real question using that institution's
   activation code, before considering the rotation complete.
4. The old password doesn't need separate cleanup — it's overwritten,
   not kept.

## Revoke vs delete a license

- **Revoke** (License Management → Suspend/Revoke): the code stops
  working, but the record stays for audit history. Use this for normal
  offboarding — someone leaving, a hospital ending their trial, etc.
- **Delete** (🗑 button): the record is gone permanently. Use this only
  for genuine junk — test codes, typos — not for real usage history you
  might need to reference later.

## Deleting an institution

Deletes the institution **and every license tied to it** — there's a
confirmation dialog showing exactly how many licenses will go with it.
This is for cleaning up test/junk institutions, not for offboarding a
real hospital (revoke their licenses individually instead, so the
institution record and audit history stay intact).

## If the agent can't connect to a hospital's database

1. Check the uvicorn console — look for a `[get_hospital_connection]`
   line. It shows whether `server`/`user`/`password` came from the
   institution's own saved values or fell back to the shared `.env`
   defaults. If it says "(fallback .env)" for a hospital that should
   have its own credentials, the institution record is missing them —
   go re-check/re-save them in Edit Institution.
2. If it correctly shows "(per-institution)" but still fails, the
   error itself (also printed to console) usually says why — wrong
   password, database doesn't exist under that name, or the login
   doesn't have permission on that specific database (a DBA-side
   permission issue, not something fixable from the admin panel).
3. `diagnose_institution_connection.py <code>` (in the project root)
   checks the whole chain in one command — what's stored, what
   `validate_license()` returns — without needing browser DevTools.

## Backups

`python backup_licenses_db.py` — run daily (Task Scheduler on Windows).
See the RECOVERY section inside that file for how to restore one if
ever needed. Keep at least the last 14 days.

## Rotating ENCRYPTION_KEY

Don't, unless you have a real reason to — every encrypted secret (every
hospital's DB password, the SMTP password) becomes unreadable the
moment the key changes, and would all need re-entering by hand. If you
must rotate it: decrypt everything under the old key first, then
re-save it all under the new key, rather than just swapping the key and
discovering afterward what broke.