"""Offline integration tests for the 1..25 per-tenant AI provider store.
All SQL here runs on throwaway SQLite, never production or client LIS.
"""
import importlib
import sqlite3
import sys
import types
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

class Row:
    def __init__(self,raw):self.values=dict(zip(raw.keys(),raw))
    def __getitem__(self,k):return self.values[k]
    def get(self,k,default=None):return self.values.get(k,default)
    def items(self):return self.values.items()

class Cursor:
    def __init__(self,inner):self.inner=inner
    def execute(self,query,params=()):self.inner.execute(query,params);return self
    def fetchone(self):
        r=self.inner.fetchone();return Row(r) if r is not None else None
    def fetchall(self):return [Row(r) for r in self.inner.fetchall()]

class Conn:
    def __init__(self,path):
        self.db=sqlite3.connect(str(path));self.db.row_factory=sqlite3.Row
    def cursor(self):return Cursor(self.db.cursor())
    def execute(self,q,params=()):return self.cursor().execute(q,params)
    def commit(self):self.db.commit()
    def rollback(self):self.db.rollback()
    def close(self):self.db.close()

@pytest.fixture
def store(tmp_path,monkeypatch):
    path=tmp_path/'admin.sqlite'
    db=sqlite3.connect(path)
    db.executescript('''CREATE TABLE institutions(
      id INTEGER PRIMARY KEY,client_prefix TEXT UNIQUE, llm_provider TEXT, llm_model TEXT,
      llm_api_key TEXT,llm_base_url TEXT,llm_key_status TEXT,llm_key_checked_at TEXT,
      allow_athentech_fallback INTEGER DEFAULT 0);
      CREATE TABLE institution_ai_slots(
       id INTEGER PRIMARY KEY AUTOINCREMENT,institution_id INTEGER,position INTEGER,enabled INTEGER,
       provider TEXT,model TEXT,api_key TEXT,base_url TEXT,key_status TEXT,checked_at TEXT,
       UNIQUE(institution_id,position));
      INSERT INTO institutions(id,client_prefix,llm_provider,llm_model,llm_api_key,allow_athentech_fallback)
      VALUES(1,'H022','groq','groq-model','enc:old-key',0);
      INSERT INTO institutions(id,client_prefix,allow_athentech_fallback) VALUES(2,'H023',0);
    ''')
    db.commit();db.close()
    license_db = types.ModuleType('database.license_db')
    license_db.get_conn=lambda:Conn(path)
    monkeypatch.setitem(sys.modules,'database.license_db',license_db)
    sc = types.ModuleType('auth.secrets_crypto')
    sc.encrypt_secret=lambda k:'enc:'+k
    sc.decrypt_secret=lambda k:(k[4:] if k and k.startswith('enc:') else k)
    monkeypatch.setitem(sys.modules,'auth.secrets_crypto',sc)
    from agent import llm_providers
    monkeypatch.setattr(llm_providers,'provider_info',lambda p:{'id':p} if p in ('groq','openai','gemini','anthropic') else None)
    monkeypatch.setattr(llm_providers,'invalidate',lambda *a:None)
    import auth.institution_ai_slots as slots
    importlib.reload(slots)
    def validate(provider,key,model=None,base_url=None):
        return {'ok':key!='bad-key','message':'The key is invalid' if key=='bad-key' else 'Verified'}
    yield slots,path,validate


def slot(pos,enabled=False,provider='',model='',api_key='',clear_key=False):
    return {'position':pos,'enabled':enabled,'provider':provider,'model':model,
            'api_key':api_key,'clear_key':clear_key}


def all3(s1=None,s2=None,s3=None):
    return [s1 or slot(1,True),s2 or slot(2),s3 or slot(3)]


def test_legacy_single_key_is_imported_without_leaking(store):
    s,path,valid=store
    d=s.public_slots(1)
    assert d['slots'][0]['legacy'] and d['slots'][0]['has_key']
    assert 'api_key' not in str(d)
    assert s.runtime_slots('H022')['providers'][0]['api_key']=='old-key'


def test_multi_slot_atomic_save_encrypts_each_key_and_orders(store):
    s,path,valid=store
    payload=all3(slot(1,True,'groq','groq-model'),slot(2,True,'gemini','flash','gemini-key'))
    result=s.save_slots(1,payload,False,valid)
    assert result['slots'][0]['has_key']
    assert result['slots'][1]['has_key']
    assert result['slots'][2]['enabled'] is False
    assert 'gemini-key' not in str(result)
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT api_key FROM institution_ai_slots WHERE position=2').fetchone()[0]=='enc:gemini-key'
    policy=s.runtime_slots('H022')
    assert [p['provider'] for p in policy['providers']]==['groq','gemini']
    assert [p['api_key'] for p in policy['providers']]==['old-key','gemini-key']


def test_new_key_invalid_does_not_change_anything(store):
    s,path,valid=store
    before=s.runtime_slots('H022')
    with pytest.raises(ValueError,match='invalid'):
        s.save_slots(1,all3(slot(1,True,'groq','groq-model'),slot(2,True,'openai','a','bad-key')),True,valid)
    assert s.runtime_slots('H022')==before


def test_existing_saved_keys_survive_blank_key_update(store):
    s,path,valid=store
    payload=all3(slot(1,True,'groq','groq-model'),slot(2,True,'gemini','flash','new-key'))
    s.save_slots(1,payload,False,valid)
    payload[1]['api_key']=''
    s.save_slots(1,payload,False,valid)
    assert s.runtime_slots('H022')['providers'][1]['api_key']=='new-key'


def test_disable_secondary_keeps_key_not_used(store):
    s,path,valid=store
    payload=all3(slot(1,True,'groq','groq-model'),slot(2,True,'gemini','flash','new-key'))
    s.save_slots(1,payload,False,valid)
    payload[1]['api_key']='';payload[1]['enabled']=False
    s.save_slots(1,payload,False,valid)
    assert len(s.runtime_slots('H022')['providers'])==1
    assert s.public_slots(1)['slots'][1]['has_key'] is True


def test_clear_primary_only_secondary_kept(store):
    s,path,valid=store
    payload=all3(slot(1,True,'groq','groq-model'),slot(2,True,'gemini','flash','new-key'))
    s.save_slots(1,payload,False,valid)
    payload[0]['clear_key']=True;payload[1]['api_key']=''
    s.save_slots(1,payload,False,valid)
    data=s.runtime_slots('H022')
    assert [p['provider'] for p in data['providers']]==['gemini']
    assert s.public_slots(1)['slots'][0]['has_key'] is False


def test_explicit_fallback_only_without_an_active_key(store):
    s,path,valid=store
    s.save_slots(2,all3(),False,valid)
    assert s.runtime_slots('H023')=={'providers':[],'allow_athentech_fallback':False}
    s.save_slots(2,all3(),True,valid)
    assert s.runtime_slots('H023')=={'providers':[],'allow_athentech_fallback':True}
    s.save_slots(2,all3(slot(1,True,'openai','mini','own-key')),True,valid)
    assert len(s.runtime_slots('H023')['providers'])==1


def test_primary_is_always_mandatory(store):
    s,path,valid=store
    with pytest.raises(ValueError,match='Provider 1'):
        s.save_slots(2,all3(slot(1,False)),True,valid)


def test_failed_update_rolls_back_all_provider_changes(store):
    s,path,valid=store
    s.save_slots(1,all3(slot(1,True,'groq','groq-model')),False,valid)
    before=s.runtime_slots('H022')
    with sqlite3.connect(path) as db:
        db.execute('''CREATE TRIGGER fail_update BEFORE UPDATE ON institutions
                       BEGIN SELECT RAISE(ABORT,'blocked'); END;''');db.commit()
    with pytest.raises(sqlite3.IntegrityError):
        s.save_slots(1,all3(slot(1,True,'groq','groq-model'),slot(2,True,'gemini','flash','key2')),True,valid)
    assert s.runtime_slots('H022')==before


def test_revalidate_slot_updates_only_selected_status(store):
    s,path,valid=store
    s.save_slots(1,all3(slot(1,True,'groq','groq-model'),slot(2,True,'gemini','flash','key2')),False,valid)
    checked=s.revalidate_slot(1,2,valid)
    assert checked['ok'] is True
    assert s.public_slots(1)['slots'][1]['key_status']=='valid'


def test_change_model_revalidates_with_existing_saved_key(store):
    s,path,valid=store
    payload=all3(slot(1,True,'groq','groq-model'))
    payload[0]['model']='new-model'
    called=[]
    def recording(*args): called.append(args);return valid(*args)
    s.save_slots(1,payload,False,recording)
    assert called[0][1]=='old-key'
    assert called[0][2]=='new-model'
    assert s.runtime_slots('H022')['providers'][0]['model']=='new-model'


def test_change_provider_requires_new_key_even_if_saved(store):
    s,path,valid=store
    with pytest.raises(ValueError,match='new key'):
        s.save_slots(1,all3(slot(1,True,'openai','gpt-4o-mini')),False,valid)
    assert s.runtime_slots('H022')['providers'][0]['provider']=='groq'
