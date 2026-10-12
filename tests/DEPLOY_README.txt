AthenTech final delivery - local validation done; live SQL Server validation NOT possible here.

Files in app/ are replacements, retaining their paths. Use deploy_update.ps1 from this delivery folder.
The script backs up existing files, preserves existing client config JSON files, installs missing pinned JSON,
restarts via NSSM, checks /health, and rolls back files upon failure.

IMPORTANT: Existing per-client JSON policy is NOT replaced by deploy script. Review contents on server:
app/config/clients/H022-KonnectLIS.json: {"version":1,"coll_metric":"paid"}
app/config/clients/H023-CentromedLIS.json: {"version":1,"coll_metric":"total"}
Note: this is a provisional mapping confirmed by application conventions, not proof of real cash receipt.

Run after deployment for EACH activation code:
 python smoke_test.py --api https://api.athentech.in --code YOUR_CODE
 python verify_live_exports.py --api https://api.athentech.in --code YOUR_CODE

Note: month export without branch is still intentionally unsupported on the existing 'paid' reconciliation path.
The new XLSX checks verify row fallback for detailed exports and do not prove accounting correctness.
Both H022 and H023 must match independent ledger/SQL queries before production release.

If any issue: .\rollback_update.ps1
