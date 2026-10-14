"""Local CPU Ollama policy. Hostname and institution permission are SERVER-controlled.
No client-entered URL, no external provider calls, and no access to LIS databases.
"""
import os
import re
from urllib.parse import urlsplit
import requests

PROVIDER = 'ollama_local'
MODELS = ('qwen3:4b', 'qwen3:8b')

class LocalAIUnavailable(RuntimeError):
    pass

def permitted(client_prefix):
    allow = {p.strip().upper() for p in os.getenv('SAHASRA_OLLAMA_ALLOWED_INSTITUTIONS','').split(',') if p.strip()}
    return (os.getenv('SAHASRA_OLLAMA_ENABLED') == '1' and
            bool(client_prefix) and client_prefix.upper() in allow)

def base_url():
    """Loopback-only endpoint; on Windows Server run Ollama outside IIS.
    If a Linux VM is used later, deploy an explicitly authenticated proxy rather
    than changing this to a publicly accessible host.
    """
    url = os.getenv('SAHASRA_OLLAMA_BASE_URL','http://127.0.0.1:11434/v1').rstrip('/')
    p = urlsplit(url)
    if (p.scheme != 'http' or p.hostname not in ('127.0.0.1','localhost') or p.port != 11434
            or p.path != '/v1' or p.username or p.password or p.query or p.fragment):
        raise LocalAIUnavailable('Ollama must use the fixed loopback endpoint :11434/v1')
    return 'http://127.0.0.1:11434/v1'

def assert_allowed(client_prefix, model):
    if not permitted(client_prefix):
        raise LocalAIUnavailable('Local AI is disabled or institution is not allowlisted')
    if model not in MODELS:
        raise LocalAIUnavailable('Select approved local model qwen3:4b or qwen3:8b')
    return base_url()

def check_health(client_prefix, model, timeout=3):
    """Admin-side readiness test only, never a credential validator."""
    try:
        assert_allowed(client_prefix, model)
        response=requests.get('http://127.0.0.1:11434/api/tags',timeout=timeout,allow_redirects=False)
        response.raise_for_status()
        available={item.get('name') for item in response.json().get('models',[]) if isinstance(item,dict)}
        return {'ok':model in available,'code':'ready' if model in available else 'not_pulled',
                'message':'Local model available' if model in available else 'Local model not downloaded yet'}
    except (requests.RequestException,ValueError,LocalAIUnavailable) as exc:
        return {'ok':False,'code':'unavailable','message':'Local Ollama not ready or institution not authorized'}
