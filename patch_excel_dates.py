"""Run from app folder. Fixes SQL Server error 241 'Conversion failed when converting date and/or time from character string'
(ISO date strings sent to servers whose language is day-first). Passes real date objects instead. Backups made, idempotent."""
import shutil, sys, time
E={
"reports/day_collection_readonly.py":[
("def _resolve_relative_date(value: str) -> str:",
 'import re as _re_iso\n\n\ndef _iso_to_date(params):\n    """\'YYYY-MM-DD\' strings -> date objects so SQL Server never re-parses them with a day-first DATEFORMAT."""\n    from datetime import date as _d\n    out = []\n    for p in (params if isinstance(params, (tuple, list)) else (params,)):\n        if isinstance(p, str) and _re_iso.fullmatch(r"\\d{4}-\\d{2}-\\d{2}", p):\n            p = _d.fromisoformat(p)\n        out.append(p)\n    return tuple(out)\n\n\ndef _resolve_relative_date(value: str) -> str:'),
("        cursor.execute(sql, params)\n        row = cursor.fetchone()\n        return float(row[0])",
 "        cursor.execute(sql, _iso_to_date(params))\n        row = cursor.fetchone()\n        return float(row[0])"),
],
"reports/excel_export.py":[
("def _period_dates(period_keyword: str):",
 'def _dt(v):\n    """ISO date string -> date object (language-neutral for SQL Server)."""\n    if isinstance(v, str) and len(v) == 10 and v[4] == "-" and v[7] == "-":\n        from datetime import date as _d\n        return _d.fromisoformat(v)\n    return v\n\n\ndef _period_dates(period_keyword: str):'),
("            (date_from, date_to),\n        )\n        rows = cur.fetchall()\n    except Exception as e:\n        conn.close()\n        return {\"error\": f\"Query failed: {e}\"}\n    conn.close()\n    if not rows:\n        return {\"error\": f\"No collection data for {label}.\"}",
 "            (_dt(date_from), _dt(date_to)),\n        )\n        rows = cur.fetchall()\n    except Exception as e:\n        conn.close()\n        return {\"error\": f\"Query failed: {e}\"}\n    conn.close()\n    if not rows:\n        return {\"error\": f\"No collection data for {label}.\"}"),
("(loc_id, date_from, date_to),","(loc_id, _dt(date_from), _dt(date_to)),"),
],
}
out={}
for p,pairs in E.items():
    s=open(p,encoding="utf-8").read()
    if "_iso_to_date" in s or "def _dt(" in s: print("ALREADY APPLIED:",p); continue
    for i,(a,b) in enumerate(pairs,1):
        if s.count(a)!=1: print(f"{p}: anchor {i} found {s.count(a)}x. Nothing changed."); sys.exit(1)
        s=s.replace(a,b)
    if p.endswith("excel_export.py"):
        # remaining plain (date_from, date_to), tuples
        s=s.replace("            (date_from, date_to),\n","            (_dt(date_from), _dt(date_to)),\n")
    out[p]=s
st=time.strftime("%Y%m%d-%H%M%S")
for p,s in out.items():
    shutil.copy2(p,p+".bak-"+st); open(p,"w",encoding="utf-8").write(s)
print("APPLIED:",", ".join(out) or "nothing new")
