"""Portable offline Stage13 tests. No network, credentials, SQL Server, or real patient data."""
import importlib.util
from pathlib import Path
import sys

import pytest

BASE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('stage13_patch', BASE / 'apply_stage13.py')
patcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patcher)


@pytest.fixture(scope='module')
def baseline():
    # Exact sections used by the version-guarded patcher, no production sources.
    main = 'from fastapi import FastAPI\napp = FastAPI(title="Sahasra AI Agent")\n'
    provider = '''import re
_CREDIT = re.compile(r"insufficient_quota|resource_exhausted|credit balance", re.I)
_BADKEY = re.compile(r"invalid api key", re.I)
_BADMODEL = re.compile(r"model not found", re.I)
_ACCESS = re.compile(r"access denied", re.I)
MESSAGES = {
    "no_credits": "The provider reports insufficient credits or quota. Check the account billing and quotas.",
    "rate_limited": "The provider is rate-limiting requests. Wait for its retry window, then test again.",
}
def _classify(status, body, provider_code="", provider_type=""):
    text = " ".join((str(body or ""), str(provider_code or ""), str(provider_type or "")))
    if status in (200, 201):
        return "ok"
    if status == 402 or _CREDIT.search(text):
        return "no_credits"
    if status == 429:
        return "rate_limited"
    if status == 401 or _BADKEY.search(text):
        return "invalid_key"
    if _BADMODEL.search(text):
        return "bad_model"
    if status == 403 or _ACCESS.search(text):
        return "access_denied"
    if status == 404:
        return "endpoint_missing"
    if status >= 500:
        return "provider_error"
    return "bad_request"
def classify_runtime_error(exc):
    text = f"{type(exc).__name__}: {exc}"
    st = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
    if _CREDIT.search(text):
        return "no_credits"
    if st == 429 or re.search(r"\\b429\\b|rate.?limit|too many requests", text, re.I):
        return "rate_limited"
    if st == 401 or _BADKEY.search(text):
        return "invalid_key"
    if st == 403:
        return "access_denied"
    if _BADMODEL.search(text):
        return "bad_model"
    return None
'''
    agent = '''_BYOK_USER_MESSAGES = {
    "no_credits": "Your AI provider account has no credits or tokens left. Please top up the provider account (or ask your administrator to update the key).",
    "rate_limited": "Your AI provider is rate-limiting the key right now. Please try again in a minute.",
}
_OWN_KEY = object()
def _extract_retry_seconds(error_message: str, provider_name: str = "groq") -> int:
    return _PROVIDER_FALLBACK_TTL.get(provider_name, 26 * 60 * 60) # unknown — conservative fallback
'''
    return {'main.py':main, 'agent/llm_providers.py':provider, 'agent/agent.py':agent}


def test_main_registers_once(baseline):
    once = patcher.change_main(baseline['main.py'])
    assert once.count('app.middleware("http")(metrics_middleware)') == 1
    assert patcher.change_main(once) == once


def test_unknown_main_fails_closed():
    with pytest.raises(ValueError):
        patcher.change_main('application = custom_factory()')


def test_provider_429_classification(baseline):
    patched = patcher.change_provider(baseline['agent/llm_providers.py'])
    assert patcher.change_provider(patched) == patched
    env = {}
    exec(compile(patched, '<test-provider-fixture>', 'exec'), env)
    classify = env['classify_runtime_error']
    cases = [
        ('429 RESOURCE_EXHAUSTED', 'rate_limited'),
        ('429 RESOURCE_EXHAUSTED daily quota exceeded', 'quota_exhausted'),
        ('429 rate limit RPM exceeded', 'rate_limited'),
        ('429 insufficient_quota', 'no_credits'),
        ('401 invalid api key', 'invalid_key'),
        ('429 per day usage reached', 'quota_exhausted'),
    ]
    for err, expected in cases:
        assert classify(RuntimeError(err)) == expected, err
    assert env['_classify'](429, 'RESOURCE_EXHAUSTED') == 'rate_limited'
    assert env['_classify'](429, 'RESOURCE_EXHAUSTED daily limit') == 'quota_exhausted'


def test_agent_explanations_and_ttl(baseline):
    patched = patcher.change_agent(baseline['agent/agent.py'])
    assert patcher.change_agent(patched) == patched
    assert 'Please try again in a minute' not in patched
    assert 'quota_exhausted' in patched
    assert 'return 300  # ambiguous 429' in patched


def test_apply_idempotent_and_backups(tmp_path, baseline):
    for rel, data in baseline.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(data, encoding='utf-8')
    assert len(patcher.patch(tmp_path, BASE, dry_run=True)) == 5
    changes = patcher.patch(tmp_path, BASE)
    assert len(changes) == 5
    assert (tmp_path / 'observability' / 'metrics.py').exists()
    assert list((tmp_path / 'agent').glob('*.before_stage13_*.bak'))
    assert patcher.patch(tmp_path, BASE, dry_run=True) == []


@pytest.fixture(scope='module')
def metrics_module():
    spec = importlib.util.spec_from_file_location('stage13_metrics', BASE / 'observability' / 'metrics.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_metrics_privacy_bounded_routes(metrics_module):
    m = metrics_module
    assert m._route('/public/b2b/patient-report/BILL123') == 'b2b_pdf_download'
    assert m._route('/public/b2b/patient-report/BILL999') == 'b2b_pdf_download'
    assert m._route('/patient/PRIVATEID') == 'other'
    assert m._route('/admin/institutions/15') == 'admin_other'
    assert 'INSTITUTION' not in str(m._HTTP._labelnames).upper()


def test_metrics_fail_closed(monkeypatch, metrics_module):
    class Request:
        headers = {'authorization':'Bearer test'}
    monkeypatch.setenv('SAHASRA_METRICS_ENABLED','1')
    monkeypatch.setenv('SAHASRA_METRICS_TOKEN','short')
    assert not metrics_module._authenticated(Request())
    monkeypatch.setenv('SAHASRA_METRICS_ENABLED','0')
    monkeypatch.setenv('SAHASRA_METRICS_TOKEN','x'*40)
    assert not metrics_module._authenticated(Request())


def test_existing_metrics_never_overwritten(tmp_path, baseline):
    for rel, data in baseline.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(data)
    existing = tmp_path / 'observability' / 'metrics.py'
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_text('# existing metrics code\n')
    patcher.patch(tmp_path, BASE)
    assert existing.read_text() == '# existing metrics code\n'
