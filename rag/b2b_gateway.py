"""B2B RAG gateway: STRICTLY session-derived scope.

The existing B2B verification/router must call this only AFTER validating the
session and contact and binding their institution and organization to server
records. This module provides no public B2B endpoint and no bypass to OTP.
"""
from rag.store import retrieve, safe_context


def approved_b2b_context(*, verified_session: dict, question: str) -> str:
    if not verified_session or verified_session.get('verified') is not True:
        raise PermissionError('Verified B2B session required')
    institution = verified_session.get('institution_prefix')
    organization = verified_session.get('organization_code')
    if not institution or not organization:
        raise PermissionError('Verified institution and organization required')
    # Caller must construct verified_session entirely from a validated server-side
    # session; do not pass JSON/body/query params or LLM-generated identifiers.
    hits = retrieve(institution=institution, audience='b2b', organization=organization,
                    question=question)
    return safe_context(hits)
