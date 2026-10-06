"""
AthenTech company-info mode — full site coverage from athentech.co.in sitemap.
Scrapes once (24h TTL), answers with one LLM call (no tools / no DB).
"""
import re
import time
import requests
from bs4 import BeautifulSoup
from xml.etree import ElementTree as ET

_cache = {
    "pages": {},       # url -> text
    "content": None,   # joined string for LLM
    "fetched_at": 0,
}
_CACHE_TTL_SECONDS = 24 * 60 * 60

_BASE = "https://www.athentech.co.in"
_SITEMAP_URL = f"{_BASE}/sitemap.xml"

# Full fallback if sitemap fetch fails — every <loc> from sitemap.xml (2026-07-13)
_PAGES_FALLBACK = [
    f"{_BASE}/",
    f"{_BASE}/about/",
    f"{_BASE}/about/vision-mission/",
    f"{_BASE}/management/",
    f"{_BASE}/abdm-integrated-his/",
    f"{_BASE}/about/why-choose-us/",
    f"{_BASE}/about/careers/",
    f"{_BASE}/solutions/",
    f"{_BASE}/solutions/hospital-information-system/",
    f"{_BASE}/solutions/laboratory-information-system/",
    f"{_BASE}/solutions/radiology-information-system/",
    f"{_BASE}/solutions/pharmacy-management/",
    f"{_BASE}/solutions/electronic-medical-records/",
    f"{_BASE}/solutions/blood-bank-management/",
    f"{_BASE}/solutions/nursing-station-management/",
    f"{_BASE}/solutions/ot-management/",
    f"{_BASE}/solutions/housekeeping-management/",
    f"{_BASE}/solutions/hr-payroll/",
    f"{_BASE}/solutions/inventory-procurement/",
    f"{_BASE}/solutions/finance-accounts/",
    f"{_BASE}/solutions/mobile-applications/",
    f"{_BASE}/solutions/patient-portal/",
    f"{_BASE}/modules/",
    f"{_BASE}/modules/masters/",
    f"{_BASE}/modules/admin-management/",
    f"{_BASE}/modules/opd-management/",
    f"{_BASE}/modules/ipd-management/",
    f"{_BASE}/modules/insurance-credit-billing/",
    f"{_BASE}/modules/pharmacy-management/",
    f"{_BASE}/modules/laboratory-reporting/",
    f"{_BASE}/modules/radiology-reporting/",
    f"{_BASE}/modules/general-stores/",
    f"{_BASE}/modules/wards-management/",
    f"{_BASE}/modules/er-management/",
    f"{_BASE}/modules/doctor-workstation/",
    f"{_BASE}/modules/cssd-management/",
    f"{_BASE}/modules/ot-management/",
    f"{_BASE}/modules/payroll-management/",
    f"{_BASE}/modules/asset-management/",
    f"{_BASE}/modules/complaints-management/",
    f"{_BASE}/modules/canteen-diet-management/",
    f"{_BASE}/modules/transportation-management/",
    f"{_BASE}/modules/daycare-management/",
    f"{_BASE}/modules/patient-self-service-portal/",
    f"{_BASE}/modules/linen-laundry-management/",
    f"{_BASE}/modules/housekeeping-management/",
    f"{_BASE}/modules/mod-management/",
    f"{_BASE}/modules/e-appointments/",
    f"{_BASE}/modules/procurement-management/",
    f"{_BASE}/modules/log-audit-management/",
    f"{_BASE}/modules/discharge-summary/",
    f"{_BASE}/modules/mis-analysis-reports/",
    f"{_BASE}/modules/mrd-management/",
    f"{_BASE}/modules/emr-management/",
    f"{_BASE}/modules/employee-self-service-portal/",
    f"{_BASE}/modules/blood-bank-management/",
    f"{_BASE}/modules/messaging-integration/",
    f"{_BASE}/modules/android-mobile-apps/",
    f"{_BASE}/modules/touch-screen-kiosk/",
    f"{_BASE}/modules/tv-dashboard-doctor-tokens/",
    f"{_BASE}/modules/tv-dashboard-nursing-stations/",
    f"{_BASE}/modules/tv-dashboard-lab-radiology/",
    f"{_BASE}/modules/tally-erp-integration/",
    f"{_BASE}/modules/lab-machine-interfacing/",
    f"{_BASE}/modules/payment-gateway-integrations/",
    f"{_BASE}/modules/patient-online-reports-wac/",
    f"{_BASE}/industries/",
    f"{_BASE}/industries/multi-specialty-hospitals/",
    f"{_BASE}/industries/diagnostic-centers/",
    f"{_BASE}/industries/medical-colleges/",
    f"{_BASE}/industries/clinics/",
    f"{_BASE}/industries/ivf-centers/",
    f"{_BASE}/industries/corporate-hospitals/",
    f"{_BASE}/industries/government-hospitals/",
    f"{_BASE}/industries/telemedicine-centers/",
    f"{_BASE}/products/",
    f"{_BASE}/products/sahasra-hisgenx/",
    f"{_BASE}/products/sahasra-lis/",
    f"{_BASE}/products/sahasra-ris/",
    f"{_BASE}/products/sahasra-erp/",
    f"{_BASE}/products/campus-360/",
    f"{_BASE}/products/sahasra-mobile-apps/",
    f"{_BASE}/products/compare/",
    f"{_BASE}/features/",
    f"{_BASE}/features/nabh-compliance/",
    f"{_BASE}/features/hl7-integration/",
    f"{_BASE}/features/pacs-integration/",
    f"{_BASE}/features/api-integrations/",
    f"{_BASE}/features/cloud-hosting/",
    f"{_BASE}/features/multi-location-support/",
    f"{_BASE}/features/mobile-access/",
    f"{_BASE}/features/security-audit-trail/",
    f"{_BASE}/features/whatsapp-integration/",
    f"{_BASE}/clients/",
    f"{_BASE}/clients/success-stories/",
    f"{_BASE}/clients/testimonials/",
    f"{_BASE}/clients/case-studies/",
    f"{_BASE}/clients/case-studies/multi-specialty-hospital/",
    f"{_BASE}/clients/case-studies/medical-college-teaching-hospital/",
    f"{_BASE}/clients/case-studies/diagnostic-lab-chain/",
    f"{_BASE}/clients/case-studies/government-hospital/",
    f"{_BASE}/resources/",
    f"{_BASE}/resources/brochures/",
    f"{_BASE}/resources/videos/",
    f"{_BASE}/resources/blog/",
    f"{_BASE}/resources/faqs/",
    f"{_BASE}/resources/downloads/",
    f"{_BASE}/resources/news/",
    f"{_BASE}/resources/events/",
    f"{_BASE}/support/",
    f"{_BASE}/support/raise-a-ticket/",
    f"{_BASE}/support/remote-support/",
    f"{_BASE}/support/training/",
    f"{_BASE}/support/documentation/",
    f"{_BASE}/support/whatsapp-business-setup/",
    f"{_BASE}/contact/",
    f"{_BASE}/contact/request-demo/",
    f"{_BASE}/contact/sales/",
    f"{_BASE}/contact/support/",
    f"{_BASE}/contact/locations/",
    f"{_BASE}/whatsapp-signup/",
    f"{_BASE}/whatsapp-apps/",
    f"{_BASE}/hospital-management-software/",
    f"{_BASE}/his-software/",
    f"{_BASE}/lis-software/",
    f"{_BASE}/emr-software/",
    f"{_BASE}/nabh-hospital-software/",
    f"{_BASE}/abdm-integrated-his/",
    f"{_BASE}/healthcare-erp-software/",
    f"{_BASE}/diagnostic-lab-software/",
    f"{_BASE}/technology/",
    f"{_BASE}/ai-healthcare-platform/",
    f"{_BASE}/privacy-policy/",
    f"{_BASE}/terms-and-conditions/",
    f"{_BASE}/cookies/",
]

_MAX_CHARS_PER_PAGE = 2200
# When packing for the LLM: prefer question-relevant pages + core pages
_MAX_LLM_CHARS = 32000

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SahasraAI/1.0; +https://www.athentech.co.in)"
}


def _normalize_url(url: str) -> str:
    url = (url or "").strip()
    if url.startswith("http://"):
        url = "https://" + url[len("http://"):]
    # force www for consistency with our base
    url = url.replace("https://athentech.co.in", "https://www.athentech.co.in")
    if not url.endswith("/") and "?" not in url and "#" not in url:
        # keep file-like paths; most site pages use trailing slash
        if not url.rsplit("/", 1)[-1].count("."):
            url = url + "/"
    return url


def _load_urls_from_sitemap() -> list:
    try:
        resp = requests.get(_SITEMAP_URL, timeout=20, headers=_HEADERS)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        locs = []
        for loc in root.findall(".//sm:loc", ns):
            if loc.text:
                locs.append(_normalize_url(loc.text))
        if not locs:
            # no namespace fallback
            for loc in root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc"):
                if loc.text:
                    locs.append(_normalize_url(loc.text))
        # dedupe preserve order
        seen = set()
        out = []
        for u in locs:
            if u not in seen:
                seen.add(u)
                out.append(u)
        if out:
            print(f"[athentech_info] Sitemap URLs: {len(out)}")
            return out
    except Exception as e:
        print(f"[athentech_info] Sitemap failed: {e} — using fallback list")
    return list(_PAGES_FALLBACK)


def _fetch_page_text(url: str) -> str:
    try:
        resp = requests.get(url, timeout=15, headers=_HEADERS, allow_redirects=True)
        if resp.status_code == 404:
            return ""
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(
            ["script", "style", "nav", "footer", "header", "noscript", "iframe", "form", "svg"]
        ):
            tag.decompose()
        root = soup.find("main") or soup.find("article") or soup.body or soup
        text = root.get_text(separator=" ", strip=True)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:_MAX_CHARS_PER_PAGE]
    except Exception as e:
        print(f"[athentech_info] Fail {url}: {e}")
        return ""


def refresh_athentech_cache(force: bool = False) -> str:
    """
    Scrape every sitemap page into memory. Call on startup optional;
    otherwise first about-us question triggers this (can take 1–3 min).
    """
    now = time.time()
    if (
        not force
        and _cache["content"]
        and (now - _cache["fetched_at"]) < _CACHE_TTL_SECONDS
    ):
        return _cache["content"]

    urls = _load_urls_from_sitemap()
    pages = {}
    for i, url in enumerate(urls, 1):
        text = _fetch_page_text(url)
        if text and len(text) >= 60:
            pages[url] = text
        if i % 20 == 0:
            print(f"[athentech_info] Scraped {i}/{len(urls)}…")
        time.sleep(0.15)  # be polite to their server

    _cache["pages"] = pages
    _cache["fetched_at"] = now
    # Full dump kept for selection; joined is not forced into one giant string forever
    joined = "\n\n".join(f"--- {u} ---\n{t}" for u, t in pages.items())
    _cache["content"] = joined
    print(f"[athentech_info] Done: {len(pages)} pages, {len(joined)} chars total")
    return joined


def _select_context_for_question(question: str) -> str:
    """
    Pack the most relevant pages into the LLM budget so 130 pages
    do not all dump into one prompt. Always include home + about + contact.
    """
    pages = _cache.get("pages") or {}
    if not pages:
        refresh_athentech_cache()
        pages = _cache.get("pages") or {}
    if not pages:
        return ""

    q = (question or "").lower()
    always = [
        f"{_BASE}/",
        f"{_BASE}/about/",
        f"{_BASE}/contact/",
        f"{_BASE}/products/",
        f"{_BASE}/ai-healthcare-platform/",
    ]

    scored = []
    for url, text in pages.items():
        score = 0
        path = url.lower()
        # keyword hits in URL path
        for token in re.findall(r"[a-z0-9]{3,}", q):
            if token in path:
                score += 5
            if token in text.lower()[:800]:
                score += 2
        # category boosts
        if "module" in q and "/modules/" in path:
            score += 8
        if any(w in q for w in ("product", "his", "lis", "ris", "erp", "campus")) and "/products/" in path:
            score += 8
        if any(w in q for w in ("industry", "hospital", "diagnostic", "college", "clinic", "ivf")) and "/industries/" in path:
            score += 8
        if any(w in q for w in ("feature", "nabh", "hl7", "pacs", "cloud", "whatsapp", "abdm")) and (
            "/features/" in path or "abdm" in path
        ):
            score += 8
        if any(w in q for w in ("client", "case", "testimonial", "success")) and "/clients/" in path:
            score += 8
        if any(w in q for w in ("support", "ticket", "training", "remote")) and "/support/" in path:
            score += 8
        if any(w in q for w in ("contact", "sales", "demo", "location", "phone", "email")) and "/contact/" in path:
            score += 10
        if url in always or _normalize_url(url) in always:
            score += 15
        scored.append((score, url, text))

    scored.sort(key=lambda x: (-x[0], x[1]))

    pieces = []
    total = 0
    for score, url, text in scored:
        if score <= 0 and total > 8000:
            continue
        block = f"--- {url} ---\n{text}"
        if total + len(block) > _MAX_LLM_CHARS:
            continue
        pieces.append(block)
        total += len(block)
        if total >= _MAX_LLM_CHARS:
            break

    return "\n\n".join(pieces)


def get_athentech_context(question: str = "") -> str:
    now = time.time()
    if not _cache["pages"] or (now - _cache["fetched_at"]) >= _CACHE_TTL_SECONDS:
        refresh_athentech_cache()
    if question:
        return _select_context_for_question(question)
    return _cache.get("content") or ""




def answer_athentech_question(question: str, llm) -> str:
    from langchain_core.messages import HumanMessage, SystemMessage

    context = ""
    try:
        context = get_athentech_context(question) or ""
    except Exception as e:
        print(f"[athentech_info] context error: {e}")

    if not context or len(context) < 80:
        context = _OFFLINE_FALLBACK
        print("[athentech_info] using offline fallback (site unreachable from this server)")

    system_prompt = f"""You answer ONLY about AthenTech using the website content below.
Never invent facts. If it is not in the content, say so in one short plain line.

OUTPUT RULES (same as Sahasra chat cards — mandatory):
- Lists (modules, products, features, industries, clients, solutions): output ONLY a list-card fenced block. Nothing outside it.
- Overview / counts / highlights with a few key facts: output ONLY a dashboard-card fenced block.
- Single short fact: one emoji + **bold title** + 1–2 lines. No padding.

**list-card** (use for "modules", product lists, feature lists):
```list-card
{{
  "icon": "🏥",
  "title": "Sahasra Modules",
  "intro": "Integrated modules on the Sahasra platform:",
  "items": [
    {{"primary": "Hospital Information System (HIS)", "fields": ["OPD, IPD, billing, wards, OT"]}},
    {{"primary": "Laboratory Information System (LIS)", "fields": ["Sample tracking, TAT, analyzers"]}}
  ],
  "footer": "More: athentech.co.in · Sales +91 970 5480 699"
}}
-primary = module/product name only (short).
-fields = 1 short line each, max 2 fields.
-Cap at 12–15 items. Group the rest as one item: "Other modules" with field "See website for full list".
-No markdown headings, no ###, no long paragraphs.

dashboard-card (use for company snapshot / contact / highlights):
{{
  "icon": "🏢",
  "title": "AthenTech",
  "subtitle": "Healthcare IT",
  "meta": [{{"icon": "🌐", "text": "athentech.co.in"}}],
  "stats": [
    {{"label": "FOCUS", "value": "HIS / LIS"}},
    {{"label": "PRODUCT", "value": "Sahasra"}}
  ],
  "footer": {{"label": "Sales", "value": "+91 970 5480 699"}}
}}

Be compact. No sales fluff. No repeating the same point.
ATHENTECH WEBSITE CONTENT:
{context}
"""
    messages = [
    SystemMessage(content=system_prompt),
    HumanMessage(content=question),
    ]
    response = llm.invoke(messages)
    text = response.content if hasattr(response, "content") else str(response)
    return (text or "").strip()
    


def clear_athentech_cache() -> None:
    _cache["pages"] = {}
    _cache["content"] = None
    _cache["fetched_at"] = 0