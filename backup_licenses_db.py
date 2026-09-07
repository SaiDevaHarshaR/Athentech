"""
Backs up licenses.db safely (uses SQLite's own backup API, not a raw
file copy — a raw copy while the app is writing to the DB can produce a
corrupted backup; the backup API handles this correctly even with the
app running).

Usage:
    python backup_licenses_db.py
    python backup_licenses_db.py --keep 30   # keep the last 30 backups (default 14)

Recommended: run this daily via Windows Task Scheduler (or cron on
Linux) — see the RECOVERY section at the bottom of this file for what
to do if you ever actually need to restore one.
"""

import argparse
import os
import shutil
import sqlite3
from datetime import datetime

DB_PATH = "licenses.db"
BACKUP_DIR = "backups"


def backup_now() -> str:
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"{DB_PATH} not found — run this from your project root.")

    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"licenses_{timestamp}.db")

    # sqlite3's own backup() API — safe to use even while the live app
    # has the database open, unlike a plain file copy which can grab a
    # half-written page mid-transaction and produce a corrupt backup.
    source = sqlite3.connect(DB_PATH)
    dest = sqlite3.connect(backup_path)
    with dest:
        source.backup(dest)
    source.close()
    dest.close()

    size_kb = os.path.getsize(backup_path) / 1024
    print(f"Backed up to {backup_path} ({size_kb:.1f} KB)")
    return backup_path


def prune_old_backups(keep: int):
    if not os.path.exists(BACKUP_DIR):
        return
    backups = sorted(
        [f for f in os.listdir(BACKUP_DIR) if f.startswith("licenses_") and f.endswith(".db")]
    )
    to_delete = backups[:-keep] if len(backups) > keep else []
    for f in to_delete:
        os.remove(os.path.join(BACKUP_DIR, f))
    if to_delete:
        print(f"Removed {len(to_delete)} old backup(s), kept the {keep} most recent.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", type=int, default=14, help="Number of recent backups to keep (default 14)")
    args = parser.parse_args()

    backup_now()
    prune_old_backups(args.keep)


"""
RECOVERY PROCESS — what to do if licenses.db is ever lost or corrupted:

1. STOP the running service first (nssm stop SahasraAIAgent, or Ctrl+C
   if running directly) — don't restore into a file the app has open.

2. Pick the most recent good backup from the backups/ folder (they're
   timestamped, newest last when sorted alphabetically).

3. Move the broken/missing licenses.db out of the way:
       ren licenses.db licenses.db.broken

4. Copy the backup into place:
       copy backups\\licenses_20260902_140000.db licenses.db

5. Restart the service. Check /admin/institutions and /admin/audit look
   right before considering it done.

6. Any activations/edits made AFTER that backup's timestamp are gone —
   this is why running the backup daily (not weekly) matters for a
   system with real, active hospitals on it.

Encrypted secrets (institution db_password, SMTP password) restore
correctly as long as your .env's ENCRYPTION_KEY hasn't changed since the
backup was taken — if you ever rotate that key, old backups encrypted
under the previous key become unreadable. Keep a copy of retired keys
somewhere safe if you might ever need to restore an old backup.
"""