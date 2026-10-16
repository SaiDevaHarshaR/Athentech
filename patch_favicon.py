"""Run from app folder. Adds the favicon to the Answer Review + Guardian consoles (serves /Favicon.ico from the app folder)."""
import shutil, sys, time, re, os
LINK='<link rel="icon" type="image/x-icon" href="/Favicon.ico">'
st=time.strftime("%Y%m%d-%H%M%S")
if not os.path.exists("Favicon.ico"): print("Favicon.ico not in app folder"); sys.exit(1)
mp=open("main.py",encoding="utf-8").read()
anchor='@app.get("/admin/answer-review/console", include_in_schema=False)'
route='''@app.get("/Favicon.ico", include_in_schema=False)
@app.get("/favicon.ico", include_in_schema=False)
def _favicon():
    from fastapi.responses import FileResponse
    return FileResponse(os.path.join(os.path.dirname(__file__), "Favicon.ico"), media_type="image/x-icon",
                        headers={"Cache-Control": "public, max-age=86400"})


'''
new={}
if "def _favicon" not in mp:
    if mp.count(anchor)!=1: print("main.py anchor not found"); sys.exit(1)
    new["main.py"]=mp.replace(anchor,route+anchor)
for f in ("answer_review.html","guardian_console.html"):
    s=open(f,encoding="utf-8").read()
    if "/Favicon.ico" in s: continue
    s2,n=re.subn(r"(<title>.*?</title>)",lambda m:m.group(1)+"\n"+LINK,s,count=1,flags=re.S)
    if n!=1: print(f,"no <title> found"); sys.exit(1)
    new[f]=s2
for f,s in new.items():
    shutil.copy2(f,f+".bak-"+st); open(f,"w",encoding="utf-8").write(s)
print("APPLIED:",", ".join(new) or "ALREADY APPLIED")
