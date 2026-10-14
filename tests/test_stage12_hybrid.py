"""Offline, no model downloads/API calls/SQL writes."""
import importlib
import os
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_classification_local_vs_complex():
    from agent.hybrid_router import classify
    assert classify('How many invoices this month?').tier == 'routine'
    assert classify('What are your opening hours?').tier == 'routine'
    assert classify('ఈ నెల ఎన్ని బిల్లులు?').tier == 'routine'
    assert classify('Compare revenue trends across departments').tier == 'complex'
    assert classify('Why is the collection reconciliation different?').tier == 'complex'
    assert classify('something obscure and unrecognized').tier == 'complex'
    assert classify('How many invoices and explain the variance?').tier == 'complex'


def test_off_by_default(monkeypatch):
    from agent.hybrid_router import route_chain
    monkeypatch.delenv('SAHASRA_HYBRID_ROUTING_ENABLED', raising=False)
    chain = [('ollama_local', object()), ('groq#slot2', object())]
    assert route_chain('compare trends', chain) is chain


def test_routine_never_auto_escalates_to_cloud(monkeypatch):
    from agent.hybrid_router import route_chain, HybridRouteUnavailable
    monkeypatch.setenv('SAHASRA_HYBRID_ROUTING_ENABLED', '1')
    monkeypatch.setenv('SAHASRA_HYBRID_COMPLEX_CLOUD_ENABLED', '1')
    local, cloud = object(), object()
    assert route_chain('How many invoices?', [('ollama_local', local), ('groq#slot2', cloud)]) == [('ollama_local', local)]
    with pytest.raises(HybridRouteUnavailable, match='No cloud provider was contacted'):
        route_chain('How many invoices?', [('groq', cloud)])


def test_complex_no_unapproved_provider(monkeypatch):
    from agent.hybrid_router import route_chain, HybridRouteUnavailable
    monkeypatch.setenv('SAHASRA_HYBRID_ROUTING_ENABLED', '1')
    monkeypatch.delenv('SAHASRA_HYBRID_COMPLEX_CLOUD_ENABLED', raising=False)
    with pytest.raises(HybridRouteUnavailable, match='disabled'):
        route_chain('Compare and analyze trends', [('groq', object())])
    monkeypatch.setenv('SAHASRA_HYBRID_COMPLEX_CLOUD_ENABLED', '1')
    with pytest.raises(HybridRouteUnavailable, match='No institution-approved cloud'):
        route_chain('Compare and analyze trends', [('ollama_local', object())])


def test_complex_uses_only_institution_owned_cloud(monkeypatch):
    from agent.hybrid_router import route_chain
    monkeypatch.setenv('SAHASRA_HYBRID_ROUTING_ENABLED', '1')
    monkeypatch.setenv('SAHASRA_HYBRID_COMPLEX_CLOUD_ENABLED', '1')
    chain = [('ollama_local', object()), ('openai#slot2', object()), ('groq#slot3', object())]
    assert [p for p, _ in route_chain('Why are collections not balanced?', chain)] == ['openai#slot2','groq#slot3']


def test_local_classifier_opt_in_and_untrusted_output(monkeypatch):
    from auth.b2b_local_intent import refine_ambiguous
    monkeypatch.delenv('SAHASRA_B2B_LOCAL_INTENT_ENABLED', raising=False)
    assert refine_ambiguous('something unknown', 'KLIS') == 'help'
    monkeypatch.setenv('SAHASRA_B2B_LOCAL_INTENT_ENABLED', '1')
    import agent.ollama_local as local
    monkeypatch.setattr(local, 'assert_allowed', lambda c, m: 'http://127.0.0.1:11434/v1')
    import urllib.request
    class Reply:
        def __init__(self, answer): self.answer = answer
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, *args): return self.answer
    def fake_request(req, timeout):
        assert req.full_url == 'http://127.0.0.1:11434/api/chat'
        return Reply(b'{"message":{"content":"run_sql_query"}}')
    monkeypatch.setattr(urllib.request, 'urlopen', fake_request)
    assert refine_ambiguous('anything', 'KLIS') == 'help'  # tool instruction rejected
    monkeypatch.setattr(urllib.request, 'urlopen', lambda *a, **kw: Reply(b'{"message":{"content":"bills"}}'))
    assert refine_ambiguous('show our invoices in short', 'KLIS') == 'bills'


def test_b2b_status_request_never_returns_all_rows():
    from auth.b2b_intent_engine import parse_question
    d = parse_question('Show pending invoices')
    assert d.intent == 'invoice_status' and d.status_filter == 'pending'
    assert parse_question('Download patient report PDF').intent == 'patient_report'
    assert parse_question('Show another company invoices').intent == 'forbidden'


def test_provider_tier_does_not_use_athentech_when_any_slot_exists(monkeypatch):
    from agent import llm_providers as providers
    from agent.hybrid_router import HybridRouteUnavailable
    monkeypatch.setattr(providers, 'institution_ai_policy', lambda name, provider_tier=None: {
        'providers': [], 'allow_athentech_fallback': True, 'had_active_slots': True,
    })
    providers.invalidate()
    with pytest.raises(HybridRouteUnavailable):
        providers.institution_chain('KLIS', provider_tier='complex')
    providers.invalidate()
    with pytest.raises(HybridRouteUnavailable):
        providers.institution_chain('KLIS', provider_tier='routine')


def test_provider_tier_builds_only_provided_models(monkeypatch):
    from agent import llm_providers as providers
    from agent.hybrid_router import HybridRouteUnavailable
    def policy(client_prefix, provider_tier=None):
        owned=[{'position':1, 'provider':'ollama_local','api_key':'local-no-external-key','model':'qwen3:4b','base_url':None},
               {'position':2, 'provider':'groq','api_key':'fake-owned-secret','model':'test','base_url':None}]
        return {'providers':[s for s in owned if (s['provider']=='ollama_local') == (provider_tier=='routine')],
                'allow_athentech_fallback': True, 'had_active_slots':True}
    monkeypatch.setattr(providers,'institution_ai_policy',policy)
    seen=[]
    def fake_build(provider, api_key, model=None, base_url=None, client_prefix=None):
        seen.append(provider)
        return object()
    monkeypatch.setattr(providers,'build_chat_model',fake_build)
    providers.invalidate()
    assert [p for p,_ in providers.institution_chain('KLIS',provider_tier='routine')] == ['ollama_local']
    assert seen == ['ollama_local']
    assert [p for p,_ in providers.institution_chain('KLIS',provider_tier='complex')] == ['groq#slot2']
    assert seen == ['ollama_local','groq']


def test_b2b_rag_requires_flag_and_local_opt_in(monkeypatch):
    from auth.b2b_local_answer import approved_faq_answer
    monkeypatch.delenv('SAHASRA_B2B_RAG_ENABLED', raising=False)
    assert approved_faq_answer(question='hours', inst={'client_prefix':'KLIS'}, organization_code='ORG1') is None
    monkeypatch.setenv('SAHASRA_B2B_RAG_ENABLED', '1')
    import agent.ollama_local as local
    from agent.ollama_local import LocalAIUnavailable
    monkeypatch.setattr(local, 'assert_allowed', lambda *a: (_ for _ in ()).throw(LocalAIUnavailable('unauthorized')))
    assert approved_faq_answer(question='hours', inst={'client_prefix':'KLIS'}, organization_code='ORG1') is None


def test_b2b_rag_organization_isolation(monkeypatch, tmp_path):
    from rag.store import ingest_approved_text
    from auth.b2b_local_answer import approved_faq_answer
    import agent.ollama_local as local
    monkeypatch.setenv('SAHASRA_B2B_RAG_ENABLED', '1')
    monkeypatch.setenv('SAHASRA_RAG_STORE', str(tmp_path))
    monkeypatch.setattr(local, 'assert_allowed', lambda *a: 'http://127.0.0.1:11434/v1')
    ingest_approved_text(institution='KLIS', audience='b2b',organization='ORG1',
        title='Office hours',text='Our organization opens at 9 in the morning.',approver='Test Admin')
    # Searching for an ORG1-only document while authorized as ORG2 must not
    # contact an inference service at all.
    import auth.b2b_local_answer as module
    monkeypatch.setattr(module, 'urlopen', lambda *a, **kw: pytest.fail('model contacted for another org'))
    result = approved_faq_answer(question='morning opens',inst={'client_prefix':'KLIS'},organization_code='ORG2')
    assert result is None


def test_b2b_local_classifier_never_sends_to_cloud(monkeypatch):
    from auth.b2b_local_intent import refine_ambiguous
    import agent.ollama_local as local
    monkeypatch.setenv('SAHASRA_B2B_LOCAL_INTENT_ENABLED', '1')
    monkeypatch.setattr(local,'assert_allowed', lambda a, b: (_ for _ in ()).throw(RuntimeError('not allowed')))
    assert refine_ambiguous('Please list recent invoices', 'WRONG') == 'help'
