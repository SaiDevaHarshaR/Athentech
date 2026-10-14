"""Create a local, dependency-free HTML view from Sahasra's authenticated Prometheus endpoint.

Runs on the same host. No listening server, no patient-level data, no external calls.
Requires existing Stage 3 metrics endpoint to be enabled and a bearer token in an
environment variable. Does not save the token or raw metric labels.
"""
import argparse
import datetime as dt
import html
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

METRICS = (
    'sahasra_http_requests_total',
    'sahasra_http_request_seconds_count',
    'sahasra_b2b_requests_total',
    'sahasra_ai_provider_attempts_total',
    'sahasra_b2b_otp_outcomes_total',
)
SERIES = re.compile(r'^([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{[^}]*\})?\s+([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?|Inf|NaN)(?:\s+\S+)?$')

def summarize(text):
    """Aggregate only explicitly approved metric names; discard all labels."""
    values = {name: 0.0 for name in METRICS}
    for line in text.splitlines():
        if not line or line.startswith('#'):
            continue
        match = SERIES.match(line.strip())
        if not match or match.group(1) not in values:
            continue
        try:
            val = float(match.group(2))
        except ValueError:
            continue
        if 0 <= val < 1e20:
            values[match.group(1)] += val
    return values

def validate_target(url):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost') or parsed.username or parsed.password or parsed.path != '/internal/metrics' or parsed.query or parsed.fragment:
        raise ValueError('Only http://127.0.0.1:PORT/internal/metrics is permitted')
    return url

def fetch(url, token):
    if len(token) < 32:
        raise ValueError('SAHASRA_METRICS_TOKEN must be set (32+ characters)')
    request = urllib.request.Request(validate_target(url), headers={'Authorization': 'Bearer ' + token, 'Accept': 'text/plain'})
    with urllib.request.urlopen(request, timeout=5) as response:
        data = response.read(2_000_001)
        if len(data) > 2_000_000:
            raise ValueError('Metrics response too large')
        return data.decode('utf-8', 'replace')

def render(values, stamped):
    labels = [
        ('HTTP requests', 'sahasra_http_requests_total'),
        ('Timed API requests', 'sahasra_http_request_seconds_count'),
        ('B2B requests', 'sahasra_b2b_requests_total'),
        ('AI provider attempts', 'sahasra_ai_provider_attempts_total'),
        ('OTP outcome events', 'sahasra_b2b_otp_outcomes_total'),
    ]
    cards = '\n'.join('<article><span>' + html.escape(label) + '</span><strong>' + format(values[key], ',.0f') + '</strong></article>' for label, key in labels)
    return '''<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Sahasra • Operations Snapshot</title><style>
    :root{font-family:system-ui,-apple-system,Segoe UI,sans-serif;color:#e7eefc;background:#0b1220}body{margin:0}main{max-width:1100px;margin:auto;padding:52px 26px}header{display:flex;align-items:center;gap:15px}b.logo{background:linear-gradient(135deg,#437efa,#8b5cf6);padding:14px;border-radius:14px}h1{font-size:clamp(26px,3vw,39px);margin:0}p{color:#98a9c3}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:16px;margin-top:35px}article{background:#162238;border:1px solid #293b54;border-radius:17px;padding:24px;display:flex;flex-direction:column;gap:18px}article span{color:#9db2cf;font-size:14px}article strong{font-size:35px;letter-spacing:-1px}.note{margin-top:34px;background:#121f32;padding:20px;border-radius:14px;border:1px solid #293b54}small{color:#899cb7}</style></head><body><main><header><b class="logo">✦</b><div><h1>Sahasra Operations Snapshot</h1><p>Local, metadata-only overview • ''' + html.escape(stamped) + ''' UTC</p></div></header><section class="grid">''' + cards + '''</section><section class="note"><b>Privacy-first monitoring</b><p>Only aggregate counters are shown. No patient, mobile, organization, API-key or message data is saved. Counters reset with process restarts. This is not Grafana or a live dashboard.</p><small>For technical staff only • Store and view locally</small></section></main></body></html>'''

def main(argv=None):
    parser = argparse.ArgumentParser(description='Create a local HTML operations snapshot; no service installation')
    parser.add_argument('--url', default='http://127.0.0.1:8000/internal/metrics')
    parser.add_argument('--output', default='Sahasra_Operations_Snapshot.html')
    options = parser.parse_args(argv)
    try:
        text = fetch(options.url, os.environ.get('SAHASRA_METRICS_TOKEN', ''))
        report = render(summarize(text), dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M:%S'))
        output = Path(options.output).resolve()
        output.write_text(report, encoding='utf-8')
        print('Snapshot saved:', output)
        return 0
    except (ValueError, OSError, urllib.error.URLError) as exc:
        print('Snapshot unavailable:', type(exc).__name__, str(exc).splitlines()[0][:150], file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
