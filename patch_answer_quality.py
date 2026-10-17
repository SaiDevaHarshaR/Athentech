"""Run from the app folder: python patch_answer_quality.py  (backs up agent/agent.py; all-or-nothing; idempotent)
1) never leak raw DB/driver errors to users  2) LLM gets actionable error hints (schema check)
3) identical repeat tool calls are served from cache (saves rounds/tokens, avoids loops)
4) truncated tool output tells the model not to total/rank from partial rows."""
import shutil, sys, time
P = "agent/agent.py"
s = open(P, encoding="utf-8").read()
if "def _safe_err(" in s:
    print("ALREADY APPLIED"); sys.exit(0)
PAIRS = [
("""_BAD_TOOL = re.compile(r"^(error|query failed|query rejected|tool error|unsupported|could not connect)", re.I)
""",
"""_BAD_TOOL = re.compile(r"^(error|query failed|query rejected|tool error|unsupported|could not connect)", re.I)


def _safe_err(text, limit=160):
    \"\"\"Driver/server details never reach the user: strip ODBC prefixes, hosts/IPs, codes, paths.\"\"\"
    t = str(text or "")
    t = re.sub(r"\\[(?:Microsoft|ODBC|SQL Server|MySQL|unixODBC)[^\\]]*\\]", "", t, flags=re.I)
    t = re.sub(r"\\b\\d{1,3}(?:\\.\\d{1,3}){3}(?::\\d+)?\\b", "[host]", t)
    t = re.sub(r"\\b[\\w-]+(?:\\.[\\w-]+)+(?:,\\d+|:\\d+)?\\b", lambda m: m.group(0) if re.fullmatch(r"\\w+\\.\\w+", m.group(0)) else "[host]", t)
    t = re.sub(r"(?i)\\b(?:pwd|password|uid|user|server)\\s*=\\s*[^;\\s]+", "", t)
    t = re.sub(r"(?i)\\bfor user\\s+'[^']*'", "for the database user", t)
    t = re.sub(r"\\s+", " ", re.sub(r"^(tool error|error|query failed)\\s*:?\\s*", "", t.strip(), flags=re.I)).strip(" :;-")
    return t[:limit] or "database error"


def _tool_error_text(e):
    \"\"\"What the MODEL sees for a failed tool: sanitized + a concrete next step.\"\"\"
    msg = _safe_err(e, 300)
    low = msg.lower()
    if "invalid column" in low or "invalid object" in low or "unknown column" in low or "doesn't exist" in low:
        msg += " -> Check the real table/column names with the schema tool before retrying; do not guess names."
    elif "timeout" in low or "timed out" in low:
        msg += " -> Narrow the date range or add a branch filter, then retry once."
    elif "conversion failed" in low or "syntax" in low:
        msg += " -> Fix the query syntax / date format (use YYYY-MM-DD) and retry once."
    return "Tool error: " + msg
"""),
("""                f"({bad_results[-1][:160].strip()}). Please rephrase with one branch or one month, \"""",
 """                f"({_safe_err(bad_results[-1])}). Please rephrase with one branch or one month, \""""),
("""    ok_results, bad_results, tools_used = [], [], []
    verified = []
    t_loop = time.time()""",
"""    ok_results, bad_results, tools_used = [], [], []
    verified = []
    _seen = {}
    t_loop = time.time()"""),
("""                args = dict(tool_call.get("args") or {})
                _cn("note_tool_call", tool_call["name"], dict(args))
                args.update(tool_extra_kwargs.get(tool_call["name"], {}))
                try:
                    result = tool_fn.invoke(args)
                except Exception as e:
                    print(f"[_run_tool_loop] tool {tool_call['name']} failed: {e}")
                    result = f"Tool error: {e}\"""",
"""                args = dict(tool_call.get("args") or {})
                _cn("note_tool_call", tool_call["name"], dict(args))
                try:
                    _key = tool_call["name"] + "|" + json.dumps(args, sort_keys=True, default=str)
                except Exception:
                    _key = None
                args.update(tool_extra_kwargs.get(tool_call["name"], {}))
                if _key is not None and _key in _seen:
                    result = ("(This exact query already ran; reuse the result below instead of repeating it.)\\n"
                              + _seen[_key])
                else:
                    try:
                        result = tool_fn.invoke(args)
                        if _key is not None and not _BAD_TOOL.match(str(result).strip()):
                            _seen[_key] = str(result)[:3000]
                    except Exception as e:
                        print(f"[_run_tool_loop] tool {tool_call['name']} failed: {e}")
                        result = _tool_error_text(e)"""),
("""                result_text = result_text[:900] + "\\n...[truncated]\"""",
"""                result_text = (result_text[:900] + "\\n...[truncated: this is only PART of the rows. "
                               "Do NOT state totals, rankings or 'top N' from these rows; "
                               "run an aggregate query (SUM/COUNT/GROUP BY/TOP) instead.]")"""),
]
if "import json" not in s and "\nimport json" not in s:
    PAIRS.insert(0, ("import time\nimport re\n", "import json\nimport time\nimport re\n"))
for i, (a, b) in enumerate(PAIRS, 1):
    if s.count(a) != 1:
        print(f"ANCHOR {i} not found exactly once (found {s.count(a)}). Nothing changed."); sys.exit(1)
    s = s.replace(a, b)
bak = P + ".bak-" + time.strftime("%Y%m%d-%H%M%S")
shutil.copy2(P, bak)
open(P, "w", encoding="utf-8").write(s)
print("APPLIED. backup:", bak)
