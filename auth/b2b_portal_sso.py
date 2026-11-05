"""Read-only, stateless CentroMed portal SSO adapter.
No DDL/DML, no persistent state, no test registration or auto-provisioning.
A signed portal assertion is exchanged for a short-lived signed bearer token.
Replay of an assertion within its validity window cannot be prevented without state;
portal must authenticate every exchange, use HTTPS and keep assertions private.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import time
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()

class Assertion(BaseModel):
    payload: str = Field(min_length=30, max_length=4000)
    signature: str = Field(min_length=64, max_length=64)

def _settings():
    value = os.environ.get('B2B_PORTAL_SSO_SECRET', '')
    if len(value) < 32:
        raise HTTPException(503, 'SSO is not configured')
    return value.encode(), os.environ.get('B2B_PORTAL_SSO_CLIENT', 'CM').upper()

def _b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')

def _unb64(data):
    return base64.urlsafe_b64decode(data + '=' * (-len(data) % 4))

def verify_assertion(payload, signature, key, now=None):
    mac = hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(mac, signature.lower()):
        raise HTTPException(401, 'Invalid portal signature')
    try:
        data = json.loads(payload)
        client = str(data['client']).upper()
        org = str(data['organisation_code']).upper()
        phone = str(data['phone'])
        sub = str(data['sub'])
        issued = int(data['iat'])
    except (ValueError, TypeError, KeyError):
        raise HTTPException(400, 'Malformed portal assertion')
    t = int(time.time() if now is None else now)
    if not (t - 30 <= issued <= t + 30):
        raise HTTPException(401, 'Expired portal assertion')
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', org) or not 3 <= len(sub) <= 150:
        raise HTTPException(400, 'Invalid portal identity')
    return client, org, phone, sub

def _sign_claims(claims, key):
    data = _b64(json.dumps(claims, separators=(',', ':'), sort_keys=True).encode())
    mac = _b64(hmac.new(key, data.encode(), hashlib.sha256).digest())
    return 'sso1.' + data + '.' + mac

def _decode_claims(token, key, now=None):
    try:
        version, data, signature = token.split('.')
        if version != 'sso1' or len(token) > 3000:
            raise ValueError('bad version')
        expected = _b64(hmac.new(key, data.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError('invalid signature')
        claims = json.loads(_unb64(data))
        t = int(time.time() if now is None else now)
        if int(claims['exp']) <= t or int(claims['iat']) > t + 30:
            raise ValueError('expired')
        return claims
    except (ValueError, KeyError, TypeError, UnicodeError, json.JSONDecodeError):
        raise HTTPException(401, 'Invalid or expired SSO session')

@router.post('/integrations/b2b/sso/exchange')
def exchange(body: Assertion):
    from auth import b2b_portal as b
    key, allowed = _settings()
    client, org, phone, sub = verify_assertion(body.payload, body.signature, key)
    if client != allowed:
        raise HTTPException(403, 'Client not enabled for portal SSO')
    inst = b._institution_by_prefix(client)
    if not b._b2b_enabled(inst):
        raise HTTPException(403, 'B2B unavailable')
    contact = b._contact(int(inst['id']), b._phone(phone))
    if not contact or str(contact['organisation_code']).upper() != org:
        raise HTTPException(403, 'Contact not mapped to this organisation')
    if not b._org_name(inst, org):
        raise HTTPException(403, 'Organisation does not exist in LIS')
    t = int(time.time())
    token = _sign_claims({'inst': int(inst['id']), 'client': client,
                          'contact': int(contact['id']), 'org': org,
                          'sub_hash': hashlib.sha256(sub.encode()).hexdigest(),
                          'iat': t, 'exp': t + 120}, key)
    return {'status':'success', 'access_token':token, 'expires_in':120,
            'contact_name':contact['contact_name'], 'organisation':org}

def verify_session(token, client):
    """Hook called by b2b_portal._session for SSO-prefixed tokens. SELECT only."""
    from auth import b2b_portal as b
    key, allowed = _settings()
    claims = _decode_claims(token, key)
    if client.upper() != allowed or claims.get('client') != allowed:
        raise HTTPException(403, 'Wrong portal client')
    inst = b._institution_by_prefix(client)
    if not b._b2b_enabled(inst) or int(inst['id']) != int(claims['inst']):
        raise HTTPException(403, 'B2B unavailable')
    conn = b._admin_conn()
    try:
        row = conn.execute('''SELECT TOP 1 * FROM dbo.sahasra_b2b_contacts
            WHERE id=? AND institution_id=? AND organisation_code=? AND active=1''',
            (int(claims['contact']), int(inst['id']), claims['org'])).fetchone()
        contact = b._dict(row)
    finally:
        conn.close()
    if not contact:
        raise HTTPException(401, 'Contact disabled or organisation changed')
    return inst, contact

def initialize_sso():
    return None
