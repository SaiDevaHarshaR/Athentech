"""Run from the app folder: python patch_heal.py   (needs agent/heal.py copied to agent/ first)
Adds the Heal flow: button in Needs Review -> proposal (diagnosis, confidence, before/after) -> Guardian 'Heal' tab ->
human approve/reject/revert. Approved guidance is added to the agent prompt for that client only (or all if you choose).
Backups made; all-or-nothing; idempotent."""
import os, shutil, sys, time

if not os.path.exists("agent/heal.py"):
    print("agent/heal.py missing - copy heal.py into the agent folder first"); sys.exit(1)

EDITS = {
"agent/agent.py": [
("### Schema guidance\n{schema_hints}\n",
 "### Schema guidance\n{schema_hints}\n{_heal_notes}"),
("        from datetime import date as _date\n        real_today = _date.today().isoformat()\n",
 "        from datetime import date as _date\n        real_today = _date.today().isoformat()\n"
 "        try:\n            from agent.heal import notes_for as _heal_notes_for\n"
 "            _heal_notes = _heal_notes_for(institution_code, question)\n"
 "        except Exception:\n            _heal_notes = \"\"\n"),
],
"main.py": [
('@app.on_event("startup")\nasync def warm_athentech_cache():',
'''# ---------------- Self-heal (human-approved) ----------------
class HealDecision(BaseModel):
    scope: str = "client"
    note: str = ""
    rule_text: str | None = None


@app.post("/admin/answer-review/{answer_id}/heal")
def api_answer_heal(answer_id: int, admin: str = Depends(require_admin)):
    """Diagnose a flagged answer and create a PENDING fix proposal. Nothing goes live until approved."""
    from agent import heal
    res = heal.create_proposal(answer_id, actor=str(admin))
    if not res or res.get("error"):
        return {"status": "error", "message": (res or {}).get("error", "Could not create a proposal.")}
    return {"status": "success", "proposal_id": res["id"], "confidence": res["confidence"]}


@app.get("/admin/guardian/api/heal")
def api_heal_list(status: str = "", admin: str = Depends(require_admin)):
    from agent import heal
    return {"status": "success", "rows": heal.list_proposals(status or None)}


@app.get("/admin/guardian/api/heal/{pid}")
def api_heal_get(pid: int, admin: str = Depends(require_admin)):
    from agent import heal
    p = heal.get_proposal(pid)
    if not p:
        raise HTTPException(status_code=404, detail="Proposal not found.")
    return {"status": "success", "proposal": p}


@app.post("/admin/guardian/api/heal/{pid}/{action}")
def api_heal_decide(pid: int, action: str, req: HealDecision, admin: str = Depends(require_admin)):
    from agent import heal
    if action not in ("approve", "reject", "revert"):
        raise HTTPException(status_code=404, detail="Unknown action.")
    res = heal.decide(pid, action, actor=str(admin), scope=req.scope, note=req.note, rule_text=req.rule_text)
    if res.get("error"):
        return {"status": "error", "message": res["error"]}
    return {"status": "success", "proposal": res}


@app.on_event("startup")\nasync def warm_athentech_cache():'''),
],
"answer_review.html": [
("      a.appendChild(note); a.appendChild(b); body.appendChild(a);",
 "      a.appendChild(note); a.appendChild(hb); a.appendChild(b); body.appendChild(a);"),

("      var b = el('button', 'btn pri sm', 'Mark resolved'); b.type = 'button';",
 "      var hb = el('button', 'btn sm', '✨ Heal'); hb.type = 'button'; hb.title = 'Diagnose this answer and propose a fix for human review';\n"
 "      hb.addEventListener('click', async function () {\n"
 "        hb.disabled = true; hb.textContent = 'Diagnosing…';\n"
 "        try {\n"
 "          var j = await api('/admin/answer-review/' + r.id + '/heal', { method: 'POST' });\n"
 "          if (j.status === 'success') { toast('Proposal ready — opening Guardian'); setTimeout(function () { location.href = '/admin/guardian/console#heal-' + j.proposal_id; }, 600); }\n"
 "          else { toast(j.message || 'Could not diagnose this answer'); hb.disabled = false; hb.textContent = '✨ Heal'; }\n"
 "        } catch (e) { toast('Heal failed'); hb.disabled = false; hb.textContent = '✨ Heal'; }\n"
 "      });\n"
 "      var b = el('button', 'btn pri sm', 'Mark resolved'); b.type = 'button';"),
],
}

GUARD_SECTION = r"""<section class="section hidden" id="healView"><div class="page-head"><div><div class="kicker">Self-heal · human approved</div><h1>Fix flagged answers, safely.</h1><p>Nothing here goes live until you approve it. Every change shows its evidence, the AI's confidence, a before / after, and can be reverted in one click.</p></div></div><div class="heal-filters" id="healFilters"><button class="btn small primary" data-hs="pending">Pending</button><button class="btn small" data-hs="approved">Live</button><button class="btn small" data-hs="rejected">Rejected</button><button class="btn small" data-hs="reverted">Reverted</button><button class="btn small" data-hs="">All</button></div><div id="healNotice" class="hidden" style="margin:10px 0;color:var(--error);font-weight:700"></div><div id="healList"></div><div id="healDetail"></div></section>
"""
GUARD_JS = r"""
/* ---- Heal (human-approved self-repair) ---- */
let healStatus='pending';
function healPill(st){const c={pending:'#b6782a',approved:'#176f58',rejected:'#77827b',reverted:'#b84d41'}[st]||'#77827b';const p=make('span','pill',st==='approved'?'live':st);p.style.cssText='background:'+c+'1a;color:'+c+';border:1px solid '+c+'55;padding:2px 9px;border-radius:99px;font-size:11px;font-weight:800;text-transform:uppercase';return p}
function healSection(title){const d=make('div');d.style.cssText='margin:16px 0 6px;font-size:11px;letter-spacing:.12em;font-weight:800;color:#54826d;text-transform:uppercase';d.textContent=title;return d}
function healBox(){const d=make('div');d.style.cssText='background:#fff;border:1px solid var(--line);border-radius:12px;padding:12px 14px;font-size:13px;line-height:1.5;white-space:pre-wrap;word-break:break-word;max-height:260px;overflow:auto';return d}
async function healLoad(status){if(status!==undefined)healStatus=status;document.querySelectorAll('#healFilters [data-hs]').forEach(b=>b.classList.toggle('primary',b.dataset.hs===healStatus));const box=$('healList');box.replaceChildren(make('p','',' Loading…'));try{const d=await request('/heal'+(healStatus?'?status='+healStatus:''));box.replaceChildren();if(!d.rows.length){box.appendChild(make('p','','Nothing here. Use the ✨ Heal button on a flagged answer in Answer Review.'));return}for(const r of d.rows){const row=make('button','btn');row.type='button';row.style.cssText='width:100%;justify-content:space-between;margin:6px 0;text-align:left;white-space:normal';const l=make('span','','#'+r.id+' · '+r.client+' · '+(r.cause||'')+' — '+String(r.diagnosis||'').slice(0,110));row.append(l,make('span','',r.confidence+'%'),healPill(r.status));row.onclick=()=>healOpen(r.id);box.appendChild(row)}}catch(e){box.replaceChildren(make('p','',e.message))}}
async function healOpen(id){const det=$('healDetail');det.replaceChildren(make('p','','Loading proposal…'));try{const p=(await request('/heal/'+id)).proposal;det.replaceChildren();const head=make('div');head.style.cssText='display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:18px';head.append(make('h2','','Proposal #'+p.id),healPill(p.status),make('span','',p.client+' · '+p.created_ts+' UTC'));det.appendChild(head);
const conf=make('div');conf.style.cssText='display:flex;align-items:center;gap:12px;margin:10px 0';const bar=make('div');bar.style.cssText='flex:0 0 220px;height:10px;background:#e5e9e5;border-radius:9px;overflow:hidden';const fill=make('div');const cc=p.confidence>=70?'#176f58':p.confidence>=45?'#b6782a':'#b84d41';fill.style.cssText='height:100%;width:'+p.confidence+'%;background:'+cc;bar.appendChild(fill);conf.append(make('b','','AI confidence '+p.confidence+'%'),bar,make('span','','risk: '+p.risk));det.appendChild(conf);if(p.confidence_why)det.appendChild(make('div','','Why: '+p.confidence_why));
det.appendChild(healSection('Diagnosis · '+(p.cause||'')));const dg=healBox();dg.textContent=p.diagnosis||'—';det.appendChild(dg);
det.appendChild(healSection('Proposed guidance (added to the AI prompt — edit if needed)'));const ta=make('textarea');ta.value=p.rule_text||'';ta.maxLength=400;ta.disabled=p.status!=='pending';ta.style.cssText='width:100%;min-height:76px;border:1px solid var(--line);border-radius:12px;padding:10px;font:inherit';det.appendChild(ta);
if(p.example_sql){det.appendChild(healSection('Example query (read-only, tested on this client)'));const q=healBox();q.style.fontFamily='monospace';q.textContent=p.example_sql;det.appendChild(q)}
const cols=make('div');cols.style.cssText='display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px';const b=p.before_json||{},a=p.after_json||{};
const L=make('div');L.appendChild(healSection('Before (flagged answer)'));const lb=healBox();lb.textContent='Question: '+(b.question||'')+'\n\nAnswer: '+(b.answer_preview||'(not stored)')+'\n\nScore: '+(b.score??'—')+'\nReasons: '+((b.reasons||[]).join('; ')||'—')+(b.vote_note?'\nUser note: '+b.vote_note:'')+'\n\nSQL:\n'+((b.sql||[]).join('\n\n')||'—');L.appendChild(lb);
const R=make('div');R.appendChild(healSection('After (preview with the fix — not live)'));const rb=healBox();rb.textContent=(a.answer_preview||a.answer_error||'No preview was produced.')+(a.example_sql_test?'\n\nExample query test: '+(a.example_sql_test.ok?('OK, '+a.example_sql_test.n+' row(s)'):('FAILED: '+a.example_sql_test.error)):'');R.appendChild(rb);cols.append(L,R);det.appendChild(cols);
const act=make('div');act.style.cssText='display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:18px 0';const sel=make('select');sel.style.cssText='border:1px solid var(--line);border-radius:10px;padding:10px';[['client','This client only (recommended)'],['global','ALL clients (affects everyone)']].forEach(([v,t])=>{const o=make('option','',t);o.value=v;sel.appendChild(o)});const note=make('input');note.placeholder='Note (optional)';note.maxLength=300;note.style.cssText='flex:1;min-width:180px;border:1px solid var(--line);border-radius:10px;padding:10px';
const send=async(action)=>{await run(async()=>{const r=await request('/heal/'+p.id+'/'+action,{method:'POST',body:JSON.stringify({scope:sel.value,note:note.value,rule_text:action==='approve'?ta.value:null})});if(r.status!=='success')throw Error(r.message||'Failed');healLoad();healOpen(p.id)},'healNotice')};
if(p.status==='pending'){const ok=make('button','btn primary','Approve & go live');ok.onclick=()=>{if(sel.value==='global'&&!confirm('This applies to EVERY client. Continue?'))return;send('approve')};const no=make('button','btn','Reject');no.onclick=()=>send('reject');act.append(sel,note,ok,no)}else if(p.status==='approved'){const rv=make('button','btn','↩ Revert (remove from AI prompt now)');rv.onclick=()=>send('revert');act.append(note,rv,make('span','','Live for: '+(p.scope==='global'?'ALL clients':p.client)))}det.appendChild(act);
det.appendChild(healSection('Audit trail'));const au=healBox();au.textContent=(p.events||[]).map(e=>e.ts+'  '+e.actor+'  '+e.action+'  '+(e.detail||'')).join('\n')||'—';det.appendChild(au);det.scrollIntoView({behavior:'smooth',block:'start'})}catch(e){det.replaceChildren(make('p','',e.message))}}
document.addEventListener('click',e=>{const b=e.target.closest&&e.target.closest('#healFilters [data-hs]');if(b)healLoad(b.dataset.hs)});
"""

EDITS["guardian_console.html"] = [
("<button data-view=\"help\">Help / How to use</button>", "<button data-view=\"heal\">Heal</button><button data-view=\"help\">Help / How to use</button>"),
("<section class=\"section hidden\" id=\"helpView\">", GUARD_SECTION + "<section class=\"section hidden\" id=\"helpView\">"),
("for(const id of ['overview','diagnostics','playbooks','help'])", "for(const id of ['overview','diagnostics','playbooks','heal','help'])"),
("async function login(){", GUARD_JS + "async function login(){"),
("if(window.location.hash.startsWith('#help-')){", "if(window.location.hash.startsWith('#heal')){go('heal');healLoad();const hid=parseInt(window.location.hash.slice(6),10);if(hid)healOpen(hid)}else if(window.location.hash.startsWith('#help-')){"),
]

done = {}
for path, pairs in EDITS.items():
    s = open(path, encoding="utf-8").read()
    marker = {"agent/agent.py": "_heal_notes", "main.py": "api_answer_heal", "answer_review.html": "Diagnosing", "guardian_console.html": "healView"}[path]
    if marker in s:
        print("ALREADY APPLIED:", path); continue
    for i, (a, b) in enumerate(pairs, 1):
        if s.count(a) != 1:
            print(f"{path}: anchor {i} found {s.count(a)}x. Nothing changed."); sys.exit(1)
        s = s.replace(a, b)
    done[path] = s
st = time.strftime("%Y%m%d-%H%M%S")
for p, s in done.items():
    shutil.copy2(p, p + ".bak-" + st); open(p, "w", encoding="utf-8").write(s)
print("APPLIED:", ", ".join(done) or "nothing new")
