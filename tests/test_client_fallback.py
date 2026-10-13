"""Test the production _invoke_with_retry AST without requiring LangChain.
Check that client-owned rate limits never invoke AthenTech models.
"""
import ast
import contextvars
from pathlib import Path
import sys
import types

ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/'agent/agent.py').read_text()
fn=next(x for x in ast.parse(source).body if isinstance(x,ast.FunctionDef) and x.name=='_invoke_with_retry')
code=compile(ast.Module(body=[fn],type_ignores=[]),'agent/agent.py','exec')

class RateLimit(Exception):pass
class Fake:
    def __init__(self,value=None,fail=None):self.value=value;self.fail=fail;self.calls=0
    def invoke(self,m):
        self.calls+=1
        if self.fail:raise self.fail
        return self.value
    def bind_tools(self,tools):return self


def function(own,chain,shared):
    chip=types.ModuleType('agent.chip_health')
    chip.NO_LLM=types.SimpleNamespace(get=lambda:False)
    chip.NeedsLLM=RuntimeError
    sys.modules['agent.chip_health']=chip
    state=contextvars.ContextVar('own',default=own)
    client=contextvars.ContextVar('clientchain',default=chain)
    index=contextvars.ContextVar('index',default=0)
    import time
    env={'_OWN_KEY':state,'_OWN_CLIENT_CHAIN':client,'_OWN_CLIENT_INDEX':index,
         '_get_provider_chain':lambda:shared,
         '_is_rate_limit_error':lambda e:isinstance(e,RateLimit),
         '_extract_retry_seconds':lambda *a:10,
         'mark_exhausted':lambda *a,**kw:None,
         'is_exhausted':lambda *a:False,
         'time':types.SimpleNamespace(sleep=lambda x:None)}
    exec(code,env)
    return env['_invoke_with_retry'],index


def test_second_client_provider_answers_without_shared_fallback():
    first=Fake(fail=RateLimit('429'));second=Fake('client-second');shared=Fake('athentech')
    invoke,idx=function(True,[('client-1',first),('client-2',second)],[('shared',shared)])
    assert invoke(first,['q'],fallback_tools=['report'])=='client-second'
    assert (first.calls,second.calls,shared.calls)==(1,1,0)
    assert idx.get()==1
    assert invoke(first,['next'],fallback_tools=['report'])=='client-second'
    assert first.calls==1


def test_all_client_providers_fail_closed():
    first=Fake(fail=RateLimit('429'))
    second=Fake(fail=RuntimeError('billing'))
    shared=Fake('NEVER')
    invoke,_=function(True,[('first',first),('second',second)],[('shared',shared)])
    try:invoke(first,[])
    except RuntimeError as e:assert 'billing' in str(e)
    else:assert False
    assert shared.calls==0


def test_shared_fallback_still_works_when_explicitly_authorized():
    primary=Fake(fail=RateLimit('429'));secondary=Fake('shared-fallback')
    invoke,_=function(False,[],[('groq',primary),('openai',secondary)])
    assert invoke(primary,[],retries=0,current_provider='groq')=='shared-fallback'
    assert secondary.calls==1
