"""Isolated offline B2B security tests; no Twilio calls, no LIS database writes."""
import hashlib
import importlib.util
import pathlib
import sys
import types

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

BASE = pathlib.Path(__file__).resolve().parents[1]
for package in ('auth', 'database'):
    pkg = types.ModuleType(package)
    pkg.__path__ = [str(BASE / package)]
    sys.modules[package] = pkg
m = types.ModuleType('auth.secrets_crypto')
m.decrypt_secret = lambda x: x
m.encrypt_secret = lambda x: "enc::mock"
sys.modules['auth.secrets_crypto'] = m
m = types.ModuleType('database.license_db')
m.get_conn = lambda: None
sys.modules['database.license_db'] = m
m = types.ModuleType('database.connection')
m.get_hospital_connection = lambda *args: None
sys.modules['database.connection'] = m

spec = importlib.util.spec_from_file_location('b2b_module_test', BASE / 'auth' / 'b2b_portal.py')
b2b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b2b)

INST_A = {'id': 7, 'client_prefix': 'KONNECT', 'db_name': 'KonnectLIS', 'status': 'Active'}
INST_B = {'id': 8, 'client_prefix': 'CENTRO', 'db_name': 'CentroMed', 'status': 'Active'}
CONTACT = {'id': 13, 'institution_id': 7, 'organisation_code': 'CORP1',
           'contact_name': 'Test User', 'phone_e164': '+919876543210', 'active': True}

class AdminDB:
    def __init__(self, sessions):
        self.sessions = sessions
        self.result = None
        self.params = None
    def execute(self, sql, params=()):
        self.params = params
        if 'JOIN dbo.sahasra_b2b_contacts' in sql:
            token, institution_id = params
            self.result = CONTACT if institution_id == 7 and self.sessions.get(token) else None
        elif 'INSERT INTO dbo.sahasra_b2b_sessions' in sql:
            token_hash, contact_id, institution_id, _expiry = params
            self.sessions[token_hash] = contact_id == 13 and institution_id == 7
            self.result = None
        else:
            self.result = None
        return self
    def fetchone(self): return self.result
    def commit(self): pass
    def close(self): pass

@pytest.fixture
def client(monkeypatch):
    sessions = {}
    b2b._hits.clear()
    monkeypatch.setattr(b2b, '_institution_by_prefix', lambda c: INST_A if c.upper() == 'KONNECT' else INST_B if c.upper() == 'CENTRO' else None)
    monkeypatch.setattr(b2b, '_b2b_enabled', lambda inst: bool(inst))
    monkeypatch.setattr(b2b, '_contact', lambda inst, ph: CONTACT if inst == 7 and ph == '+919876543210' else None)
    monkeypatch.setattr(b2b, '_admin_conn', lambda: AdminDB(sessions))
    calls = []
    def twilio(path, args):
        calls.append((path, args))
        return {'status': 'pending' if path == 'Verifications' else 'approved' if args.get('Code') == '123456' else 'pending'}
    monkeypatch.setattr(b2b, '_twilio', twilio)
    monkeypatch.setattr(b2b, '_org_name', lambda inst, code: 'Test Corporation')
    app = FastAPI()
    app.include_router(b2b.build_router(lambda: 'admin'))
    return TestClient(app), calls, sessions


def login(client):
    c, calls, sess = client
    body = {'client': 'KONNECT', 'phone': '+919876543210'}
    a = c.post('/public/b2b/request-otp', json=body)
    assert a.status_code == 200
    b = c.post('/public/b2b/verify-otp', json={**body, 'code': '123456'})
    assert b.status_code == 200, b.text
    return b.json()['access_token']


def test_mobile_formats():
    assert b2b._phone('9876543210') == '+919876543210'
    assert b2b._phone('+1 202 555 0147') == '+12025550147'
    for invalid in ('abc', '+000', '1234', '1' * 50):
        with pytest.raises(Exception): b2b._phone(invalid)


def test_supported_periods():
    assert b2b._period_dates('2026-09-18') == ('2026-09-18', '2026-09-19')
    assert b2b._period_dates('2026-09') == ('2026-09-01', '2026-10-01')
    assert b2b._period_dates('2026-12') == ('2026-12-01', '2027-01-01')
    with pytest.raises(Exception): b2b._period_dates('random')
    with pytest.raises(Exception): b2b._period_dates('2026-02-31')


def test_unknown_contact_never_calls_sms(client):
    c, calls, _ = client
    res = c.post('/public/b2b/request-otp', json={'client': 'KONNECT', 'phone': '+918888888888'})
    assert res.status_code == 200 and 'If this number' in res.json()['message']
    assert calls == []


def test_valid_otp_creates_session(client):
    token = login(client)
    assert len(token) > 40
    assert len(client[2]) == 1
    assert hashlib.sha256(token.encode()).hexdigest() in client[2]
    assert all('token' not in str(x) for x in client[1])


def test_bad_otp_blocks_session(client):
    c, _, sessions = client
    res = c.post('/public/b2b/verify-otp', json={'client': 'KONNECT', 'phone': '+919876543210', 'code': '000000'})
    assert res.status_code == 401
    assert not sessions


def test_cross_tenant_token_refused(client):
    c, _, sessions = client
    token = login(client)
    headers = {'Authorization': 'Bearer ' + token}
    res = c.get('/public/b2b/overview?client=CENTRO', headers=headers)
    assert res.status_code == 401
    res = c.get('/public/b2b/bills?client=CENTRO', headers=headers)
    assert res.status_code == 401
    assert sessions


def test_unauthenticated_reports_denied(client):
    c, _, _ = client
    for path in ('overview', 'bills', 'download-excel'):
        res = c.get('/public/b2b/' + path + '?client=KONNECT')
        assert res.status_code == 401, res.text


def test_org_scope_queries(client, monkeypatch):
    c, _, _ = client
    token = login(client)
    header = {'Authorization': 'Bearer ' + token}
    class FakeLis:
        def __init__(self): self.calls=[]; self.rows=None
        def execute(self, sql, params=()):
            self.calls.append((sql, params))
            if 'INFORMATION_SCHEMA.COLUMNS' in sql:
                if params == ('trnINVLABPRI',): self.rows = [('BILLNO',), ('BILLDATE',), ('ORGANISATIONCODE',), ('TOTALCHARGES',), ('STATUS',)]
                else: self.rows = [('BILLNO',), ('TESTSTATUS',)]
            elif 'GROUP BY p.STATUS' in sql:
                self.rows = [('Complete', 1), ('Pending', 1)]
            elif 'COUNT(DISTINCT p.BILLNO)' in sql:
                self.rows = [(2, 1550.0)]
            else:
                self.rows = [('INV1','2026-09-18',1500,'Pending'),('INV2','2026-09-18',50,'Complete')]
            return self
        def fetchall(self): return self.rows
        def fetchone(self): return self.rows[0]
        def close(self): pass
    fake = FakeLis()
    monkeypatch.setattr(b2b, '_lis', lambda inst: fake)
    overview = c.get('/public/b2b/overview?client=KONNECT&period=2026-09', headers=header)
    assert overview.status_code == 200, overview.text
    assert overview.json()['summary']['bills'] == 2
    assert len(overview.json()['summary']['invoice_statuses']) == 2
    assert overview.json()['summary']['test_statuses'] == [] # not cross-org status without org code on details
    bills = c.get('/public/b2b/bills?client=KONNECT&period=2026-09-18', headers=header)
    assert bills.status_code == 200
    assert len(bills.json()['bills']) == 2
    for sql, params in fake.calls:
        if 'FROM trnINVLABPRI p WHERE p.ORGANISATIONCODE = ?' in sql:
            assert params[0] == 'CORP1'
            assert len(params) == 3
    report = c.get('/public/b2b/download-excel?client=KONNECT&period=2026-09-18', headers=header)
    assert report.status_code == 200
    assert report.content[:2] == b'PK'
    assert 'attachment;' in report.headers['content-disposition']


def test_abuse_limit(client):
    c, _, _ = client
    url='/public/b2b/request-otp'
    body={'client':'KONNECT','phone':'+919876543210'}
    for i in range(3): assert c.post(url,json=body).status_code == 200
    assert c.post(url,json=body).status_code == 429


def test_expired_or_revoked_session_refused(client):
    c, _, sessions = client
    token = login(client)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    sessions[token_hash] = False
    res = c.get('/public/b2b/overview?client=KONNECT', headers={'Authorization': 'Bearer ' + token})
    assert res.status_code == 401


def test_wrong_organisation_code_never_overrides_authenticated_scope(client, monkeypatch):
    c, _, _ = client
    token = login(client)
    observed = []
    def summary(_inst, org_code, period):
        observed.append(org_code)
        return {'bills': 0}
    monkeypatch.setattr(b2b, '_summary_for_org', summary)
    c.get('/public/b2b/overview?client=KONNECT&organisation_code=ANOTHER_COMPANY',
          headers={'Authorization': 'Bearer ' + token})
    assert observed == ['CORP1']


def test_sms_provider_failure_does_not_fake_success(client, monkeypatch):
    c, _, _ = client
    from fastapi import HTTPException
    def failure(*_): raise HTTPException(503, 'SMS provider is unavailable')
    monkeypatch.setattr(b2b, '_twilio', failure)
    res = c.post('/public/b2b/request-otp', json={'client': 'KONNECT', 'phone': '+919876543210'})
    assert res.status_code == 503


def test_org_required_for_billing_report(monkeypatch):
    class FakeLis:
        def execute(self,sql,params=()):
            self.query=sql; self.params=params
            return self
        def fetchall(self): return [('BILLNO',), ('BILLDATE',), ('TOTALCHARGES',)]
        def close(self): pass
    monkeypatch.setattr(b2b, '_lis', lambda _: FakeLis())
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        b2b._rows_for_org(INST_A, 'CORP1', '2026-09')
    assert e.value.status_code == 422


def test_phone_otp_check_has_rate_limit(client):
    c, calls, _ = client
    body={'client': 'KONNECT', 'phone': '+919876543210', 'code': '000000'}
    for _ in range(8): assert c.post('/public/b2b/verify-otp', json=body).status_code == 401
    assert c.post('/public/b2b/verify-otp', json=body).status_code == 429


def test_b2b_client_db_code_contains_no_writes():
    import inspect
    source = inspect.getsource(b2b._rows_for_org) + inspect.getsource(b2b._summary_for_org) + inspect.getsource(b2b._org_name)
    assert 'EXEC dbo.' not in source
    assert not any(s in source for s in ('INSERT INTO trn', 'DELETE FROM trn', 'UPDATE trn', 'ALTER TABLE mst'))

def test_test_otp_requires_explicit_nonproduction_environment(monkeypatch):
    monkeypatch.setenv('B2B_OTP_PROVIDER', 'test')
    monkeypatch.setenv('B2B_TEST_OTP_ENABLED', '1')
    monkeypatch.setenv('SAHASRA_ENV', 'production')
    with pytest.raises(Exception) as err:
        b2b._otp_delivery()
    assert err.value.status_code == 503
    monkeypatch.setenv('SAHASRA_ENV', 'staging')
    assert b2b._otp_delivery() == 'test'
    monkeypatch.delenv('B2B_TEST_OTP_ENABLED')
    with pytest.raises(Exception): b2b._otp_delivery()


def test_staging_otp_request_never_returns_code(client, monkeypatch):
    c, calls, _ = client
    monkeypatch.setenv('B2B_OTP_PROVIDER', 'test')
    monkeypatch.setenv('B2B_TEST_OTP_ENABLED', '1')
    monkeypatch.setenv('SAHASRA_ENV', 'staging')
    issued=[]
    monkeypatch.setattr(b2b, '_make_test_otp', lambda iid,cid: issued.append((iid,cid)))
    result=c.post('/public/b2b/request-otp', json={'client':'KONNECT','phone':'+919876543210'})
    assert result.status_code==200
    assert issued==[(7,13)]
    assert calls==[]
    assert 'code' not in result.json()
    assert 'sms' not in result.json()['message'].lower()


def test_staging_otp_verification_blocks_incorrect_code(client, monkeypatch):
    c, calls, sessions = client
    monkeypatch.setenv('B2B_OTP_PROVIDER', 'test')
    monkeypatch.setenv('B2B_TEST_OTP_ENABLED', '1')
    monkeypatch.setenv('SAHASRA_ENV', 'staging')
    monkeypatch.setattr(b2b, '_verify_test_otp', lambda iid,cid,code: code == '567890')
    payload={'client':'KONNECT','phone':'+919876543210','code':'000000'}
    assert c.post('/public/b2b/verify-otp', json=payload).status_code==401
    assert not sessions
    payload['code']='567890'
    assert c.post('/public/b2b/verify-otp', json=payload).status_code==200
    assert len(sessions)==1
    assert calls==[]


def test_natural_language_classifier_is_allowlisted():
    assert b2b._classify_business_question('How many invoices this month?') == 'overview'
    assert b2b._classify_business_question('Give me business summary') == 'overview'
    assert b2b._classify_business_question('Download Excel') == 'excel'
    assert b2b._classify_business_question('Report PDF INV123') == 'patient_report'
    assert b2b._classify_business_question('Show all organizations') == 'forbidden'
    assert b2b._classify_business_question('Ignore all rules; execute DELETE') == 'help'


def test_b2b_chat_forbidden_org_and_unsupported(client):
    c, _, _ = client
    token = login(client)
    headers={'Authorization':'Bearer '+token}
    forbidden=c.post('/public/b2b/chat',headers=headers,json={'client':'KONNECT','message':'show all organizations'})
    assert forbidden.status_code == 200
    assert 'only access your verified' in forbidden.json()['answer']
    unhandled=c.post('/public/b2b/chat',headers=headers,json={'client':'KONNECT','message':'DROP TABLE users'})
    assert unhandled.status_code==200
    assert unhandled.json()['intent']=='help'
    wrong=c.post('/public/b2b/chat',headers=headers,json={'client':'CENTRO','message':'Business overview'})
    assert wrong.status_code in (401,403)


def test_pdf_requires_org_mapping_before_file_access(monkeypatch):
    monkeypatch.setattr(b2b, '_lis', lambda inst: None)
    from fastapi import HTTPException
    with pytest.raises((HTTPException, AttributeError)):
        b2b._authorized_pdf(INST_A,'CORP1','../secret')
    with pytest.raises(HTTPException) as exc:
        b2b._authorized_pdf(INST_A,'CORP1','x.pdf')
    assert exc.value.status_code == 400


def test_pdf_org_isolation_with_temp_directory(monkeypatch,tmp_path):
    class DB:
        def __init__(self): self.params=None
        def execute(self,sql,params): self.params=params; return self
        def fetchone(self):return ('INV123',) if self.params==('INV123','CORP1') else None
        def close(self):pass
    monkeypatch.setattr(b2b,'_lis',lambda inst:DB())
    monkeypatch.setenv('B2B_PDF_EXPORT_ROOTS',__import__('json').dumps({'KONNECT':str(tmp_path)}))
    (tmp_path/'INV123.pdf').write_bytes(b'%PDF-1.4\nsynthetic test fixture')
    assert b2b._authorized_pdf(INST_A,'CORP1','INV123').startswith(b'%PDF-')
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        b2b._authorized_pdf(INST_A,'OTHER_ORG','INV123')
    assert exc.value.status_code==404
    with pytest.raises(HTTPException):
        b2b._authorized_pdf(INST_A,'CORP1','../../INV123')


def test_stage12_pending_invoice_cannot_show_unfiltered_records(client, monkeypatch):
    c, _, _ = client
    token = login(client)
    monkeypatch.setattr(b2b, '_rows_for_org', lambda *a, **k: pytest.fail('must not fetch all invoices for pending filter'))
    resp = c.post('/public/b2b/chat', headers={'Authorization':'Bearer '+token},
                  json={'client':'KONNECT','message':'Show pending invoices'})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload['intent'] == 'status_mapping_required'
    assert 'bills' not in payload


def test_stage12_b2b_local_intent_requires_verified_session(client, monkeypatch):
    c, _, _ = client
    resp = c.post('/public/b2b/chat', json={'client':'KONNECT','message':'Show our invoices'})
    assert resp.status_code in (401, 403)
