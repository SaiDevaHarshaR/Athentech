"""Check per-institution Excel export data without displaying patient records or credentials.

Usage: python diagnose_collection_excel.py <ACTIVATION_CODE>
Requires the same .env, ODBC driver and SQL Server connectivity as the API.
"""
import sys

from auth.license_service import validate_license
from reports.excel_export import _period_dates
from reports.collection_compat import collection_mode_data


def main():
    if len(sys.argv) != 2:
        print("Usage: python diagnose_collection_excel.py <ACTIVATION_CODE>")
        return 2
    license_info = validate_license(sys.argv[1])
    if not license_info.get("valid"):
        print("Activation code is invalid or expired.")
        return 1

    kwargs = {
        "db_name": license_info.get("db_name"),
        "db_server": license_info.get("db_server"),
        "db_user": license_info.get("db_user"),
        "db_password": license_info.get("db_password"),
    }
    print("Institution:", license_info.get("hospital_name") or license_info.get("db_name"))
    print("Diagnostic uses read-only queries; no patient details are displayed.")
    any_error = False
    for period in ("today", "yesterday", "this_month"):
        start, end, label = _period_dates(period)
        result = collection_mode_data(start, end, **kwargs)
        print(f"\n{label} ({start} to {end}, exclusive)")
        if "error" in result:
            print("ERROR:", result["error"])
            any_error = True
            continue
        print("Selected amount column:", result["amount_column"])
        print("Metric:", result["metric"])
        print("WARNING:", result["warning"])
        print("Grouped branch/mode rows:", len(result["rows"]))
        print("Grand total:", round(sum(row[2] for row in result["rows"]), 2))
    return 1 if any_error else 0


if __name__ == "__main__":
    sys.exit(main())
