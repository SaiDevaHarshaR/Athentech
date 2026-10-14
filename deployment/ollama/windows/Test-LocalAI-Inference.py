"""Optional synthetic-only benchmark, never runs without --run. No PHI or LIS access."""
import argparse
import json
import time
import urllib.request
from urllib.parse import urlsplit


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run', action='store_true', help='Explicitly permit local synthetic inference')
    p.add_argument('--model', choices=['qwen3:4b', 'qwen3:8b'], default='qwen3:4b')
    p.add_argument('--timeout', type=int, default=120)
    a = p.parse_args()
    if not a.run:
        print('DRY RUN: would POST one synthetic question to loopback Ollama. No request made.')
        return
    url = 'http://127.0.0.1:11434/api/chat'
    assert urlsplit(url).hostname == '127.0.0.1'
    payload = json.dumps({'model': a.model, 'stream': False, 'keep_alive': '30s',
                          'options': {'num_ctx': 2048, 'num_predict': 60, 'num_thread': 8},
                          'messages': [{'role': 'user', 'content': 'Reply with exactly the word READY.'}]}).encode()
    request = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'}, method='POST')
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=a.timeout) as response:
        obj = json.load(response)
    print(json.dumps({'model': a.model, 'elapsed_seconds': round(time.perf_counter()-started,2),
                      'prompt_eval_count': obj.get('prompt_eval_count'), 'eval_count': obj.get('eval_count'),
                      'done': obj.get('done')}, indent=2))
    # Intentionally never display response text or prompts, even synthetic ones.


if __name__ == '__main__':
    main()
