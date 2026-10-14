"""Sahasra operations lite: dependency-free (beyond FastAPI), metadata-only.

Data remains in the local Python process. Never log URLs with path IDs, query
strings, patients, contacts, OTPs, prompts, SQL, institution IDs or API keys.
Independent of Docker/Prometheus/Grafana/Langfuse and disabled by default.
"""
from collections import Counter, deque
from threading import Lock
import os
import time
from fastapi import Depends
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

_START = time.monotonic()
_LOCK = Lock()
_TOTAL = Counter()
_LATENCY = deque(maxlen=2500)
_EVENTS = Counter()

_ALLOWED_EVENTS = frozenset({"b2b_otp", "b2b_query", "report_download", "ai_provider"})
_ALLOWED_RESULTS = frozenset({"success", "failure", "denied", "timeout", "rate_limited"})


def route_group(path: str) -> str:
    """Return only a fixed category. NEVER return raw paths or path parameters."""
    if path == "/health": return "health"
    if path.startswith("/admin/"): return "admin"
    if path.startswith("/public/b2b/") or path.startswith("/b2b/"): return "b2b"
    if path.startswith("/widget") or path.startswith("/static/"): return "widget"
    if path.startswith("/public/"): return "public"
    if path in ("/ask", "/chat") or path.startswith("/chat/"): return "chat"
    if path.startswith("/report") or path.startswith("/reports/"): return "report"
    return "other"


def record_event(kind: str, result: str) -> bool:
    """Future hooks call this with fixed, enumerated values (not user input)."""
    if kind not in _ALLOWED_EVENTS or result not in _ALLOWED_RESULTS:
        return False
    with _LOCK:
        _EVENTS[kind, result] += 1
    return True


def record_http(path: str, status_code: int, seconds: float) -> None:
    if not 100 <= status_code <= 599:
        status_code = 500
    group = route_group(path)
    with _LOCK:
        _TOTAL[group, f"{status_code // 100}xx"] += 1
        _LATENCY.append(min(max(float(seconds), 0), 3600))


def snapshot() -> dict:
    with _LOCK:
        group_counts = sorted(({"group": g, "status": s, "count": n} for (g, s), n in _TOTAL.items()), key=lambda v: (v["group"], v["status"]))
        event_counts = sorted(({"kind": k, "result": r, "count": n} for (k, r), n in _EVENTS.items()), key=lambda v: (v["kind"], v["result"]))
        samples = sorted(_LATENCY)
    count = sum(r["count"] for r in group_counts)
    errors = sum(r["count"] for r in group_counts if r["status"] == "5xx")
    p95 = samples[max(0, min(len(samples) - 1, int((len(samples) - 1) * .95)))] if samples else None
    return {
        "status": "ok", "scope": "single-process", "since_start_seconds": int(time.monotonic() - _START),
        "http_requests": count, "http_5xx": errors,
        "http_p95_seconds": round(p95, 4) if p95 is not None else None,
        "http_groups": group_counts, "backend_events": event_counts,
        "notice": "Event outcomes appear only after explicitly connecting trusted backend hooks; counters reset after restart."
    }


def prometheus_text() -> str:
    """Prometheus 0.0.4 text format, safe labels and process-local counters."""
    s = snapshot()
    lines = [
        "# HELP sahasra_ops_http_requests_total Total requests grouped by safe route and status category.",
        "# TYPE sahasra_ops_http_requests_total counter",
    ]
    for r in s["http_groups"]:
        lines.append(f'sahasra_ops_http_requests_total{{group="{r["group"]}",status="{r["status"]}"}} {r["count"]}')
    lines.extend([
        "# HELP sahasra_ops_uptime_seconds Local process uptime.",
        "# TYPE sahasra_ops_uptime_seconds gauge",
        f'sahasra_ops_uptime_seconds {s["since_start_seconds"]}',
        "# HELP sahasra_ops_http_p95_seconds Rolling sampled HTTP latency p95.",
        "# TYPE sahasra_ops_http_p95_seconds gauge",
        f'sahasra_ops_http_p95_seconds {s["http_p95_seconds"] or 0}',
        "# HELP sahasra_ops_backend_events_total Trusted backend event outcomes.",
        "# TYPE sahasra_ops_backend_events_total counter",
    ])
    for e in s["backend_events"]:
        lines.append(f'sahasra_ops_backend_events_total{{kind="{e["kind"]}",result="{e["result"]}"}} {e["count"]}')
    return "\n".join(lines) + "\n"


_DASHBOARD = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Sahasra Operations Lite</title><style>
:root{color-scheme:dark;font-family:Inter,system-ui,Segoe UI,sans-serif}*{box-sizing:border-box}body{background:#0b1020;color:#eaf0fc;margin:0}header{border-bottom:1px solid #29344a;padding:24px 5%}h1{margin:0;font-size:25px}main{max-width:1120px;margin:25px auto;padding:0 18px}.sub{color:#9aaecb;font-size:13px;line-height:1.6}.card{border:1px solid #2b3852;background:#161f33;border-radius:15px;padding:18px;margin:10px 0}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}.value{font-size:30px;font-weight:750;margin:6px 0}input{max-width:570px;width:100%;padding:12px;color:#fff;background:#11182a;border:1px solid #61718e;border-radius:8px}button{padding:12px 17px;color:#fff;font-weight:bold;background:#496deb;border:0;border-radius:9px;cursor:pointer}table{width:100%;border-collapse:collapse;font-size:13px}td,th{text-align:left;border-bottom:1px solid #36425b;padding:9px}
</style></head><body><header><h1>◈ Sahasra Operations Lite</h1><div class="sub">Python-only diagnostics • Metadata-only • No external monitoring server</div></header><main><div class="card"><p class="sub">Paste your existing Sahasra admin Bearer token to view metrics. This page stores no token and sends it only to this Sahasra server.</p><input id="token" type="password" autocomplete="off" placeholder="Sahasra administrator Bearer token"> <button id="run">Load metrics</button><p id="note" class="sub">Awaiting authentication</p></div><section id="kpis" class="grid"></section><div class="card"><h3>HTTP route categories</h3><div id="routes" class="sub">No readings yet</div></div><div class="card"><h3>Backend events</h3><div id="events" class="sub">Only explicitly connected events appear here</div></div><div class="sub">This is not Grafana or Langfuse. Single-process counters reset on restart.</div></main><script>
const e=x=>String(x).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function table(xs,columns){if(!xs.length)return 'No recorded events';return '<table><thead><tr>'+columns.map(c=>'<th>'+e(c)+'</th>').join('')+'</tr></thead><tbody>'+xs.map(x=>'<tr>'+columns.map(c=>'<td>'+e(x[c]??'')+'</td>').join('')+'</tr>').join('')+'</tbody></table>'}
document.getElementById('run').onclick=async()=>{const t=document.getElementById('token').value.trim();if(!t)return;try{const r=await fetch('/admin/ops-lite/summary',{headers:{Authorization:'Bearer '+t},cache:'no-store'});if(!r.ok)throw new Error('HTTP '+r.status+' — check administrator session');const d=await r.json();document.getElementById('kpis').innerHTML=[['HTTP requests',d.http_requests],['Server 5xx errors',d.http_5xx],['Rolling p95',d.http_p95_seconds===null?'N/A':d.http_p95_seconds+' s'],['Uptime',d.since_start_seconds+' s']].map(k=>'<div class="card"><div class="sub">'+e(k[0])+'</div><div class="value">'+e(k[1])+'</div></div>').join('');document.getElementById('routes').innerHTML=table(d.http_groups,['group','status','count']);document.getElementById('events').innerHTML=table(d.backend_events,['kind','result','count']);document.getElementById('note').textContent='Live counters retrieved. No prompts, names or phone numbers are collected.';}catch(err){document.getElementById('note').textContent=err.message;}};
</script></body></html>"""


def install(app, require_admin):
    """Register only when explicitly opted-in; don't alter existing routes."""
    if os.getenv("SAHASRA_OPS_LITE_ENABLED", "0").lower() not in ("1", "true", "yes"):
        return False

    @app.middleware("http")
    async def sahasra_ops_lite_middleware(request, call_next):
        path = request.url.path
        if path.startswith("/admin/ops-lite/") or path == "/internal/ops-lite":
            return await call_next(request)
        started = time.perf_counter()
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        except Exception:
            status = 500
            raise
        finally:
            record_http(path, status, time.perf_counter() - started)

    @app.get("/internal/ops-lite", include_in_schema=False)
    async def ops_lite_dashboard():
        return HTMLResponse(_DASHBOARD, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"})

    @app.get("/admin/ops-lite/summary", include_in_schema=False)
    async def ops_lite_summary(_admin=Depends(require_admin)):
        return JSONResponse(snapshot(), headers={"Cache-Control": "no-store"})

    @app.get("/admin/ops-lite/prometheus", include_in_schema=False)
    async def ops_lite_prometheus(_admin=Depends(require_admin)):
        return PlainTextResponse(prometheus_text(), media_type="text/plain; version=0.0.4; charset=utf-8", headers={"Cache-Control": "no-store"})

    return True
