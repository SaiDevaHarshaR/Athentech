"""Run from app folder. Fixes: heading alone on a page, near-empty pages in Smart Report. Edits reports/templates/smart_report.html + styles.css (backups made)."""
import shutil, sys, time
t="reports/templates/smart_report.html"; c="reports/templates/styles.css"
s=open(t,encoding="utf-8").read(); css=open(c,encoding="utf-8").read()
if "layout polish" in css: print("ALREADY APPLIED"); sys.exit(0)
P='<div class="page-break"></div>\n\n<!-- =========================================================\n     '
subs=[(P+"FINDINGS NEEDING ATTENTION",), (P+"BODY-SYSTEM RESULT PAGES",)]
for (a,) in subs:
    if s.count(a)!=1: print("anchor not found:",a[-40:]); sys.exit(1)
a3='========================================================= -->\n\n<div class="page-break"></div>\n\n<div class="section-heading">\n\n    <div class="section-icon">\n        🎯'
if s.count(a3)!=1: print("anchor not found: action plan"); sys.exit(1)
st=time.strftime("%Y%m%d-%H%M%S")
shutil.copy2(t,t+".bak-"+st); shutil.copy2(c,c+".bak-"+st)
for (a,) in subs: s=s.replace(a,a.replace('page-break','soft-break'))
s=s.replace(a3,a3.replace('page-break','soft-break'))
css+='''

/* ---- layout polish: no orphan headings, no near-empty pages ---- */
.soft-break { height: 6px; }
.section-heading, .sr-h2, .sr-pagehead { break-after: avoid; page-break-after: avoid; }
.radar-chart-container svg { max-height: 210px; }
.body-map { padding: 9px; margin-bottom: 8px; }
'''
open(t,"w",encoding="utf-8").write(s); open(c,"w",encoding="utf-8").write(css); print("APPLIED")
