"""Run from the app folder AFTER patch_smart_report.py. Fixes cover page printing ~80% + white (page shrunk by one overlong value)."""
import shutil, sys, time
p = "reports/pdf_generator.py"
s = open(p, encoding="utf-8").read()
if "Clamp it." in s: print("ALREADY APPLIED"); sys.exit(0)
a = "                    page.wait_for_timeout(200)\n"
if s.count(a) != 1: print("anchor not found - run patch_smart_report.py first"); sys.exit(1)
b = '''                    # One overlong value makes Chromium shrink the WHOLE page (cover looks ~80% + white). Clamp it.
                    page.add_style_tag(content="html,body{max-width:210mm !important;overflow-x:hidden !important}"
                                               "body *{overflow-wrap:anywhere;word-break:break-word;min-width:0}"
                                               ".sr-cover{overflow:hidden !important}")
''' + a
shutil.copy2(p, p + ".bak-" + time.strftime("%Y%m%d-%H%M%S"))
open(p, "w", encoding="utf-8").write(s.replace(a, b)); print("APPLIED")
