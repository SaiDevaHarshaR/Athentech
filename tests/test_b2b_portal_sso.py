import hashlib
import hmac
import json
import time
import pytest
from fastapi import HTTPException
from auth.b2b_portal_sso import verify_assertion, _sign_claims, _decode_claims
KEY = b'only-for-tests-use-a-real-secret-in-env-123456'

def fixture():
    p = json.dumps({'client':'CM','organisation_code':'COMP0108','phone':'+919876543210',
                    'sub':'portal-account-1','iat':int(time.time())}, separators=(',',':'))
    return p, hmac.new(KEY, p.encode(), hashlib.sha256).hexdigest()

def test_valid():
    p, s = fixture()
    assert verify_assertion(p, s, KEY)[1] == 'COMP0108'

def test_tamper():
    p, s = fixture()
    with pytest.raises(HTTPException):
        verify_assertion(p.replace('COMP0108','COMP9999'), s, KEY)

def test_expired_assertion():
    p, s = fixture()
    with pytest.raises(HTTPException):
        verify_assertion(p, s, KEY, now=int(time.time())+120)

def test_token_expiration_and_tamper():
    t = int(time.time())
    token = _sign_claims({'client':'CM','iat':t,'exp':t+120},KEY)
    assert _decode_claims(token,KEY,now=t)['client'] == 'CM'
    with pytest.raises(HTTPException): _decode_claims(token,KEY,now=t+121)
    with pytest.raises(HTTPException): _decode_claims(token+'x',KEY,now=t)
