"""Aggregate-only operational overview, backed by existing Prometheus counters.
Never exposes paths, exception strings, tenant names, patient content or secrets.
This module does not itself provide a public route: use an admin-authenticated route.
"""
from datetime import datetime, timezone
from prometheus_client import REGISTRY

_NAMES = {
    'sahasra_http_requests_total': 'http_requests',
    'sahasra_b2b_requests_total': 'b2b_requests',
    'sahasra_ai_provider_attempts_total': 'ai_attempts',
    'sahasra_b2b_otp_outcomes_total': 'otp_outcomes',
    'sahasra_http_request_seconds_count': 'timed_requests',
    'sahasra_http_request_seconds_sum': 'total_request_seconds',
}

def summary():
    result = {name: 0 for name in _NAMES.values()}
    response_classes = {f'{n}xx': 0 for n in (2, 3, 4, 5)}
    provider_results = {n: 0 for n in ('success', 'error', 'timeout', 'rate_limited', 'quota_exhausted', 'invalid_key')}
    for family in REGISTRY.collect():
        for sample in family.samples:
            if sample.name not in _NAMES:
                continue
            if any(k in sample.labels for k in ('patient', 'uhid', 'phone', 'message', 'institution', 'client')):
                continue
            try:
                val = float(sample.value)
            except (TypeError, ValueError):
                continue
            if val < 0 or val != val or val == float('inf'):
                continue
            result[_NAMES[sample.name]] += val
            if sample.name == 'sahasra_http_requests_total':
                cls = sample.labels.get('status_class')
                if cls in response_classes:
                    response_classes[cls] += val
            if sample.name == 'sahasra_ai_provider_attempts_total':
                outcome = sample.labels.get('result')
                if outcome in provider_results:
                    provider_results[outcome] += val
    count = result.pop('timed_requests')
    seconds = result.pop('total_request_seconds')
    result['mean_request_ms'] = round(1000 * seconds / count, 1) if count else None
    result['http_status_classes'] = response_classes
    result['provider_outcomes'] = provider_results
    result['process_only'] = True
    result['generated_at_utc'] = datetime.now(timezone.utc).isoformat()
    return result
