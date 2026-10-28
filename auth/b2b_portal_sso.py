"""Signed partner portal SSO, bound to existing CentroMed B2B contacts.
The portal SERVER signs the raw JSON with HMAC-SHA256. Never expose the key to JS.
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()

class Assertion(BaseModel):
    payload: str = Field(min_length=30, max_length=4000)
    signature: str = Field(min_length=64, max_length=64)

class ExchangeCode(BaseModel):
    client: str = Field(min_length=1, max_length=50)
    code: str = Field(min_length=30, max_length=160)


def _config():
    key = os.environ.get('B2B_PORTAL_SSO_SECRET', '')
    client = os.environ.get('B2B_PORTAL_SSO_CLIENT', 'CM').upper()
    if len(key) < 32:
        raise HTTPException(503, 'SSO not configured')
    return key.encode(), client


def initialize_sso():
    from auth.b2b_portal import _admin_conn
    db = _admin_conn()
    try:
        db.execute('''IF OBJECT_ID('dbo.sahasra_b2b_sso_nonce','U') IS NULL
            CREATE TABLE dbo.sahasra_b2b_sso_nonce (
             institution_id INT NOT NULL, nonce_hash CHAR(64) NOT NULL,
             expires_at DATETIME2 NOT NULL,
             CONSTRAINT PK_sahasra_b2b_sso_nonce PRIMARY KEY(institution_id,nonce_hash))''')
        db.execute('''IF OBJECT_ID('dbo.sahasra_b2b_sso_code','U') IS NULL
            CREATE TABLE dbo.sahasra_b2b_sso_code (
             code_hash CHAR(64) PRIMARY KEY, institution_id INT NOT NULL,
             contact_id INT NOT NULL, expires_at DATETIME2 NOT NULL,
             used BIT NOT NULL DEFAULT 0)''')
        db.commit()
    finally:
        db.close()


def verify_assertion(payload, signature, key, now=None):
    expected = hmac.new(key, payload.encode('utf-8'), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature.lower()):
        raise HTTPException(401, 'Invalid SSO signature')
    try:
        data = json.loads(payload)
        issued = int(data['iat'])
        nonce = str(data['nonce'])
        subject = str(data['sub'])
        org = str(data['organisation_code']).upper()
        client = str(data['client']).upper()
        phone = str(data['phone'])
    except (ValueError, TypeError, KeyError):
        raise HTTPException(400, 'Malformed SSO assertion')
    if abs(int(now if now is not None else time.time()) - issued) > 60:
        raise HTTPException(401, 'Expired SSO assertion')
    if not (re.fullmatch(r'[A-Za-z0-9_.-]{1,80}',org) and 16 <= len(nonce) <= 128 and 3 <= len(subject) <= 150):
        raise HTTPException(400, 'Invalid SSO identity')
    return client, org, phone, nonce


@router.post('/integrations/b2b/sso/exchange')
def exchange(body: Assertion):
    from auth import b2b_portal as b
    key, allowed = _config()
    client, org, phone, nonce = verify_assertion(body.payload, body.signature, key)
    if client != allowed:
        raise HTTPException(403, 'SSO client not permitted')
    institution = b._institution_by_prefix(client)
    if not b._b2b_enabled(institution):
        raise HTTPException(403, 'B2B not available')
    contact = b._contact(int(institution['id']), b._phone(phone))
    if not contact or str(contact['organisation_code']).upper() != org:
        raise HTTPException(403, 'SSO user not mapped to an authorized B2B contact')
    if not b._org_name(institution, org):
        raise HTTPException(403, 'Organization missing from LIS')
    code = secrets.token_urlsafe(40)
    db = b._admin_conn()
    now = datetime.utcnow()
    try:
        db.execute('INSERT INTO dbo.sahasra_b2b_sso_nonce (institution_id, nonce_hash, expires_at) VALUES (?,?,?)',
                   (institution['id'], hashlib.sha256((client + ':' + nonce).encode()).hexdigest(), now+timedelta(minutes=3)))
        db.execute('INSERT INTO dbo.sahasra_b2b_sso_code (code_hash,institution_id,contact_id,expires_at) VALUES (?,?,?,?)',
                   (hashlib.sha256(code.encode()).hexdigest(), institution['id'],contact['id'],now+timedelta(seconds=45)))
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(409, 'SSO assertion was already used or could not be processed')
    finally:
        db.close()
    return {'code':code,'expires_in':45}


@router.post('/public/b2b/sso/consume')
def consume(body: ExchangeCode):
    from auth import b2b_portal as b
    _, allowed = _config()
    if body.client.upper() != allowed:
        raise HTTPException(403, 'SSO client not permitted')
    institution = b._institution_by_prefix(allowed)
    if not b._b2b_enabled(institution):
        raise HTTPException(403,'B2B not available')
    db = b._admin_conn()
    try:
        cur = db.cursor()
        row = cur.execute('''UPDATE dbo.sahasra_b2b_sso_code SET used=1 OUTPUT inserted.contact_id
            WHERE code_hash=? AND institution_id=? AND used=0 AND expires_at>SYSUTCDATETIME()''',
            (hashlib.sha256(body.code.encode()).hexdigest(),institution['id'])).fetchone()
        if not row:
            db.rollback()
            raise HTTPException(401,'Invalid or expired code')
        contact_row = cur.execute('''SELECT TOP 1 * FROM dbo.sahasra_b2b_contacts
            WHERE id=? AND institution_id=? AND active=1''',(row[0],institution['id'])).fetchone()
        if not contact_row:
            db.rollback()
            raise HTTPException(403,'Contact disabled')
        contact = b._dict(contact_row)
        token = secrets.token_urlsafe(48)
        cur.execute('''INSERT INTO dbo.sahasra_b2b_sessions
            (token_hash,contact_id,institution_id,expires_at) VALUES (?,?,?,?)''',
            (hashlib.sha256(token.encode()).hexdigest(),contact['id'],institution['id'],
             datetime.utcnow()+timedelta(hours=b.SESSION_HOURS)))
        db.commit()
    finally:
        db.close()
    return {'access_token':token,'expires_in':b.SESSION_HOURS*3600,
            'contact_name':contact['contact_name'],'organisation':contact['organisation_code']}
