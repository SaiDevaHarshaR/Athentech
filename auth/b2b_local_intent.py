"""Optional local-only classification for authenticated B2B queries.

Only used AFTER _auth_session; no SQL, report, ID or organization parameters
are sent to the model. Its output is parsed to a strict allowlist and cannot
trigger report release or change the organization's authorization scope.
"""
import json
import os
import urllib.request

_ALLOWED = {'overview', 'bills', 'excel', 'help'}


def refine_ambiguous(question, client_prefix, timeout=8):
    if os.getenv('SAHASRA_B2B_LOCAL_INTENT_ENABLED', '0') != '1':
        return 'help'
    from agent.ollama_local import assert_allowed
    try:
        assert_allowed(client_prefix, 'qwen3:4b')
        # A local-only request. No client data or admin credentials included.
        req = urllib.request.Request(
            'http://127.0.0.1:11434/api/chat',
            data=json.dumps({
                'model':'qwen3:4b', 'stream':False,
                'think':False,
                'messages':[
                    {'role':'system','content':(
                        'Classify a laboratory business question into exactly one word: '
                        'overview, bills, excel, help. Never answer the question. '
                        'If uncertain, reply help. No SQL, names or explanations.')},
                    {'role':'user','content':str(question or '')[:700]},
                ],
                'options':{'temperature':0,'num_predict':14,'num_ctx':512},
            }).encode('utf-8'),
            headers={'Content-Type':'application/json'},
            method='POST',
        )
        with urllib.request.urlopen(req,timeout=timeout) as response:
            payload=json.load(response)
        answer=str(payload.get('message',{}).get('content','')).strip().lower()
        return answer if answer in _ALLOWED else 'help'
    except Exception:
        return 'help'  # fail closed to deterministic help, never cloud
