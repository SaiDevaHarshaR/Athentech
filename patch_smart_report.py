"""Run from the app folder: python patch_smart_report.py   (backs up each file; all-or-nothing; idempotent)
Fixes blank Smart Report PDFs:
 1) answers shown as cards (collection etc.) were turned into an EMPTY report -> cards are now expanded into real lines
 2) Chromium blank render race -> waits for fonts/text, verifies, retries once
 3) patient report empty although lab data exists -> server retries, then tells the widget (code report_failed_retryable)
 4) widget shows a friendly message with a 'Try again' button instead of a blank PDF."""
import os, shutil, sys, time

EDITS = {
"reports/pdf_generator.py": [
("import copy\nimport os\n", "import copy\nimport json\nimport os\n"),
("import tempfile\nimport uuid\n", "import tempfile\nimport time\nimport uuid\n"),
('''def build_findings_from_content_lines(content_lines: list) -> list:
''', '''def _flatten(obj, out, prefix=""):
    if isinstance(obj, dict):
        label = obj.get("label") or obj.get("title") or obj.get("name")
        val = obj.get("value")
        if label is not None and val is not None and not isinstance(val, (dict, list)):
            out.append(f"{prefix}{label}: {val}")
            return
        for k, v in obj.items():
            if k in ("icon",) or v in (None, "", [], {}):
                continue
            if isinstance(v, (dict, list)):
                _flatten(v, out, prefix)
            else:
                out.append(f"{prefix}{str(k).replace('_', ' ').title()}: {v}" if k not in ("title", "subtitle", "primary") else f"{prefix}{v}")
    elif isinstance(obj, list):
        for it in obj:
            _flatten(it, out, prefix)
    elif obj not in (None, ""):
        out.append(f"{prefix}{obj}")


def expand_cards(content_lines: list) -> list:
    """Chat answers shown as dashboard/list cards arrive as fenced JSON. Turn them into plain readable lines
    so a report built from them is never empty."""
    text = "\\n".join(str(l) for l in (content_lines or []))
    if "```" not in text:
        return list(content_lines or [])

    def repl(m):
        try:
            data = json.loads(m.group(1))
        except Exception:
            return ""
        out = []
        _flatten(data, out)
        return "\\n".join(out)

    text = re.sub(r"```(?:dashboard-card|list-card|search-card)\\s*(\\{.*?\\})\\s*```", repl, text, flags=re.S)
    return [l for l in text.split("\\n") if l.strip()]


def build_findings_from_content_lines(content_lines: list) -> list:
    content_lines = expand_cards(content_lines)
'''),
('''def _render_pdf_with_chromium(html_file_path: str) -> bytes:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(f"file://{html_file_path}")
            pdf_bytes = page.pdf(format="A4", print_background=True, prefer_css_page_size=True)
        finally:
            browser.close()
    return pdf_bytes
''', '''def _render_pdf_with_chromium(html_file_path: str) -> bytes:
    """Render via headless Chromium. A render that races the page load can produce a BLANK pdf, so wait for
    load + fonts, check the page really has text, and retry once before giving up."""
    last = None
    for attempt in (1, 2):
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                try:
                    page = browser.new_page()
                    page.goto(f"file://{html_file_path}", wait_until="load")
                    try:
                        page.evaluate("() => (document.fonts ? document.fonts.ready.then(() => true) : true)")
                    except Exception:
                        pass
                    page.wait_for_timeout(200)
                    n = page.evaluate("() => ((document.body && document.body.innerText) || '').trim().length")
                    if n < 20:
                        raise RuntimeError("rendered page was blank")
                    return page.pdf(format="A4", print_background=True, prefer_css_page_size=True)
                finally:
                    browser.close()
        except Exception as e:
            last = e
            print(f"[pdf] render attempt {attempt} failed: {e}", flush=True)
            time.sleep(0.4)
    raise last
'''),
],
"reports/patient_report_generator.py": [
('''    structured["hospital_name"] = hospital_name

    return structured''', '''    structured["hospital_name"] = hospital_name
    structured["_has_lab_data"] = bool(raw_data.get("trnparamresult"))

    return structured'''),
],
"main.py": [
('''        report_data = await loop.run_in_executor(
            None, _ctx.run, build_patient_report_data, req.patient_identifier, db_name, role, hospital_name, agent_llm,
            db_server, db_user, db_password,
        )
''', '''        for _attempt in (1, 2):
            report_data = await loop.run_in_executor(
                None, _ctx.run, build_patient_report_data, req.patient_identifier, db_name, role, hospital_name, agent_llm,
                db_server, db_user, db_password,
            )
            if report_data.get("all_findings") or not report_data.get("_has_lab_data"):
                break
            print(f"[patient-report] empty report although lab data exists (attempt {_attempt})", flush=True)
        if report_data.get("_has_lab_data") and not report_data.get("all_findings"):
            try:
                guardian.record_event(db_name, "pdf", "smart report empty although lab data exists")
            except Exception:
                pass
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=502, content={
                "code": "report_failed_retryable",
                "detail": "I couldn't build this report just now, even though the patient's results are available. That's my fault, not your data."})
'''),
('''    # generate_smart_report uses Playwright's sync API (launches a real''', '''    from reports.pdf_generator import build_findings_from_content_lines as _bf
    if not _bf(req.content_lines):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=422, content={
            "code": "nothing_to_report",
            "detail": "There is nothing to put in a report yet. Ask a data question first, then request the PDF."})

    # generate_smart_report uses Playwright's sync API (launches a real'''),
],
"widget_files/index.html": [
('''    if (!response.ok) {
      addMessage('Failed to generate PDF.', 'bot');
      return;
    }''', '''    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      addMessage(err.detail || 'Failed to generate PDF.', 'bot');
      return;
    }'''),
('''    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      addMessage(err.detail || 'Failed to generate the patient report.', 'bot');
      return;
    }''', '''    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      if (err.code === 'report_failed_retryable') {
        const m = addMessage((err.detail || "I couldn't build this report.") + '\\n\\nWant me to try again?', 'bot');
        if (m) {
          const b = document.createElement('button');
          b.type = 'button'; b.textContent = 'Try again';
          b.style.cssText = 'display:block;margin-top:10px;padding:8px 16px;border-radius:999px;border:1px solid var(--w-accent,#6a5cf6);background:var(--w-accent-soft,rgba(106,92,246,.15));color:var(--w-accent-ink,#4a3dd1);font:600 13px inherit;cursor:pointer';
          b.onclick = () => { b.disabled = true; b.remove(); downloadPatientReport(patientIdentifier); };
          m.appendChild(b);
        }
        return;
      }
      addMessage(err.detail || 'Failed to generate the patient report.', 'bot');
      return;
    }'''),
],
}
data = {}
for path, pairs in EDITS.items():
    s = open(path, encoding="utf-8").read()
    if "expand_cards" in s or "report_failed_retryable" in s:
        print("ALREADY APPLIED:", path); continue
    for i, (a, b) in enumerate(pairs, 1):
        if s.count(a) != 1:
            print(f"{path}: anchor {i} not found exactly once (found {s.count(a)}). Nothing changed."); sys.exit(1)
        s = s.replace(a, b)
    data[path] = s
stamp = time.strftime("%Y%m%d-%H%M%S")
for path, s in data.items():
    shutil.copy2(path, path + ".bak-" + stamp)
    open(path, "w", encoding="utf-8").write(s)
print("APPLIED:", ", ".join(data) or "nothing new")
