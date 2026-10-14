"""Explicit, fail-closed hybrid model selection for Sahasra.

No external classifier, SQL, network request, or secrets. Matching is deliberately
conservative: ambiguous questions require a configured complex-query provider.
Choosing a route never authorizes a provider. Existing BYOK slots, local allowlist,
and AthenTech shared-fallback consent remain the authorization authority.
"""
import os
import re
from dataclasses import dataclass

_LOCAL = "ollama_local"
_COMPLEX = re.compile(
    r"\b(?:why|root\s+cause|analy[sz]e|analysis|predict|prediction|forecast|"
    r"trend|compare|comparison|correlation|reconcil(?:e|iation)|variance|"
    r"explain\s+(?:the\s+)?(?:difference|discrepancy)|investigate|"
    r"optimi[sz]e|strategy|diagnos(?:e|is)|interpret(?:ation)?|"
    r"multi[- ]?step|across\s+(?:branches|departments)|complex)\b|"
    r"విశ్లేషణ|तुलना|विश्लेषण|कारण",
    re.I,
)
_ROUTINE = re.compile(
    r"\b(?:hello|hi|help|faq|hours|timings?|preparation|"
    r"location|address|services?|test\s+price|"
    r"how\s+many|count|status|pending|completed|today|yesterday|"
    r"this\s+month|last\s+month|invoice|invoices|bill|bills|"
    r"download|report|reports|sample|samples|appointment)\b|"
    r"ఎన్ని|ఈ\s*నెల|పెండింగ్|రిపోర్ట్|कितने|इस\s*महीने|रिपोर्ट|लंबित",
    re.I,
)


class HybridRouteUnavailable(RuntimeError):
    """Required, explicitly authorized tier has not been configured."""


@dataclass(frozen=True)
class Decision:
    tier: str
    reason: str


def enabled():
    return os.getenv('SAHASRA_HYBRID_ROUTING_ENABLED', '0') == '1'


def classify(question):
    """No model call: prevents unapproved paid charges just to classify a query."""
    text = str(question or '')[:1600]
    if _COMPLEX.search(text):
        return Decision('complex', 'analysis_keywords')
    if _ROUTINE.search(text):
        return Decision('routine', 'routine_keywords')
    return Decision('complex', 'ambiguous_requires_review')


def route_chain(question, own_chain):
    """Choose ONLY providers already approved and built for this institution.

    Client-owned cloud failover stays inside the cloud tier. Local failures never
    cause automatic cloud calls, and cloud failures never go to local/shared AI.
    """
    if not enabled():
        return own_chain
    decision = classify(question)
    # Never assume cloud consent merely because a key exists if hybrid cloud
    # processing is administratively disabled. Stage 12 defaults to free-only.
    if decision.tier == 'complex' and os.getenv('SAHASRA_HYBRID_COMPLEX_CLOUD_ENABLED', '0') != '1':
        raise HybridRouteUnavailable('Complex AI requests are disabled by the administrator. No cloud provider was contacted.')
    if decision.tier == 'routine':
        candidates = [item for item in own_chain if item[0].split('#')[0] == _LOCAL]
        if not candidates:
            raise HybridRouteUnavailable('Local Qwen3 is not enabled for this institution. No cloud provider was contacted.')
    else:
        candidates = [item for item in own_chain if item[0].split('#')[0] != _LOCAL]
        if not candidates:
            raise HybridRouteUnavailable('No institution-approved cloud model is configured for complex requests. No shared AI was contacted.')
    return candidates
