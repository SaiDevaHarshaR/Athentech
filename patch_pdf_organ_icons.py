import re,shutil,sys,time
t="reports/templates/smart_report.html"
s=open(t,encoding="utf-8").read()
if "organ-svg" in s: print("ALREADY APPLIED"); sys.exit(0)
SV={
"🫁":'<svg class="organ-svg" viewBox="0 0 48 48" width="26" height="26"><path d="M22 6v14c-4 0-6 2-9 8-3 7-5 12-3 13 3 2 12 1 12-6V20z" fill="#f48fb1" stroke="#c2185b" stroke-width="1.5" stroke-linejoin="round"/><path d="M26 6v14c4 0 6 2 9 8 3 7 5 12 3 13-3 2-12 1-12-6V20z" fill="#f48fb1" stroke="#c2185b" stroke-width="1.5" stroke-linejoin="round"/><path d="M24 4v16M24 14l-6 5M24 14l6 5" stroke="#8d6e63" stroke-width="2" fill="none" stroke-linecap="round"/></svg>',
"🫘":'<svg class="organ-svg" viewBox="0 0 48 48" width="26" height="26"><path d="M20 8C10 8 6 18 8 28c2 9 9 13 14 10 4-3 0-8 0-12s5-5 4-11c-1-5-3-7-6-7z" fill="#e57373" stroke="#b71c1c" stroke-width="1.5" stroke-linejoin="round"/><path d="M34 12c5 2 7 8 6 14-1 7-6 11-10 9-3-2-1-6-1-9s-3-6-2-10c1-3 4-5 7-4z" fill="#ef9a9a" stroke="#b71c1c" stroke-width="1.5" stroke-linejoin="round"/></svg>',
}
LIVER='<svg class="organ-svg" viewBox="0 0 48 48" width="26" height="26"><path d="M4 18c0-5 6-8 16-8 14 0 24 4 24 14 0 8-8 14-18 14-9 0-14-4-18-8-3-3-4-7-4-12z" fill="#a1522b" stroke="#5d2a12" stroke-width="1.5" stroke-linejoin="round"/><path d="M22 11c0 6 2 11 8 14" stroke="#5d2a12" stroke-width="1.5" fill="none" stroke-linecap="round"/><ellipse cx="30" cy="34" rx="4" ry="3" fill="#7cb342" stroke="#33691e" stroke-width="1.2"/></svg>'
pat=lambda e:re.compile(r'(<div class="body-icon">\s*)'+e+r'(\s*</div>)')
n=0
for e,sv in (("🫁",SV["🫁"]),("🫘",SV["🫘"]),("🫀",LIVER)):
    s,k=pat(e).subn(lambda m:m.group(1)+sv+m.group(2),s); n+=k
if n!=3: print("anchors found:",n,"expected 3; nothing changed"); sys.exit(1)
shutil.copy2(t,t+".bak-"+time.strftime("%Y%m%d-%H%M%S"))
open(t,"w",encoding="utf-8").write(s); print("APPLIED")
