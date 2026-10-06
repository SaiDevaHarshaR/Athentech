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


_OFFLINE_FALLBACK = """
COMPANY
ATHEN TECH India Pvt Ltd (brand: Athentech / Sahasra). Healthcare IT company headquartered in Hyderabad.
Offices: Hyderabad, Bangalore, Vijayawada, Vizag.
Address: Flat No. 102, Shiva Sai Sannidhi, Opp. Sai Baba Temple, Dwarakapuri, Punjagutta, Hyderabad, Telangana 500082.
Sales: +91 970 5480 699 / sales@athentech.co.in
Support / IVR: +91 8096 247 365 / support@athentech.co.in
Website: https://www.athentech.co.in/
Also operates in banking and insurance technology; primary focus is healthcare software.
20+ years experience. 592+ healthcare clients. 18+ districts. 43 integrated modules. 950+ diagnostic report formats. 24x7 support.

MISSION
Provide smart business solutions so customers become more competitive and move to the next level of operational excellence.
VISION
Transform healthcare through technology with strong customer care — innovative process frameworks and reusable knowledge that keep clients ahead.

SCALE / CREDENTIALS
592+ clients | 20+ years | 43 modules | 950+ diagnostic reports | 18+ districts | ABDM (V3) integrated HIS & LIS | Supports NABH, NABL, CAP | HL7, FHIR, DICOM/PACS | ISO 27001 oriented security | Tally ERP, WhatsApp Business API, payment gateways, lab analyzer interfacing.

PRODUCTS (Sahasra suite)
1) Sahasra HISGenX — 43-module web HIMS for nursing homes to super-specialty hospitals. One patient record across front desk, doctors, lab, pharmacy, accounts.
2) Sahasra LIS GenX — Laboratory automation for pathology labs, radiology centres, hospital labs, multi-branch networks. Barcode samples, bi-directional analyzers, auto-validation, TAT monitoring, NABL-ready reports, portal/WhatsApp/SMS delivery.
3) Sahasra RIS — Radiology Information System with PACS, DICOM, tele-radiology.
4) Sahasra ERP — Finance, HR, payroll, procurement, inventory, assets; 250+ MIS reports; Tally integration; multi-location roll-ups.
5) Campus 360 — Medical College & Hospital Information Management (MCHIMS): academics + clinical care.
6) Sahasra Mobile Apps — Doctors, patients, management on Android, iOS, tablets; MD dashboard for branch ops/finance.
Deployment: cloud or on-premise; single site or multi-location.

INDUSTRIES
- Multi-specialty hospitals: full department unification on one platform.
- Diagnostic centers / chains: LIS + RIS + home collection, multi-branch.
- Medical colleges: teaching hospital + academic administration (Campus 360).
- Clinics & polyclinics: lighter affordable HIMS, online or offline.
- IVF & fertility centers: cycle tracking, embryology, fertility EMR.
- Corporate hospital chains: multi-location, central governance.
- Government hospitals: scheme-ready (e.g. Aarogya Sri), audit and compliance.
- Telemedicine centers: teleconsultation, e-prescription, remote diagnostics.

CORE HIS MODULES (examples of the 43)
Masters; Admin Management; OPD (registration, appointments, consult, Rx, billing); IPD (admission, beds, nursing, investigations, billing, discharge); Insurance & Credit / TPA; Pharmacy; Laboratory reporting; Radiology reporting; General Stores; Wards; ER/Emergency; Doctor Workstation / EMR.

NON-CORE MODULES
CSSD; OT management; Payroll; Asset management; Complaints (CMS); Canteen & Diet; Transportation; Day-care; Patient self-service portal; Linen & Laundry; Housekeeping; Manager on Duty (MOD); e-Appointments; Procurement; Log & Audit; Discharge summary; MIS & analytics; MRD; EMR document store; Employee self-service (ESSP); Blood bank.

INTEGRATION MODULES
WhatsApp / SMS / Email messaging; Android MD dashboard; Touch-screen kiosk; TV dashboards (doctor tokens, nursing, lab/radiology); Tally ERP link; Lab machine interfacing; Payment gateways / UPI / POS / printers / barcode / biometric; Patient online reports via Web Access Code (WAC).

PLATFORM THEMES
One patient record end-to-end (registration → consultation → lab → radiology → pharmacy → billing → EMR → discharge).
Practical AI inside existing screens (drafts, alerts, insights).
Live management numbers (volumes, revenue, collections, TAT, occupancy).
Role-based access, encryption, audit trails, backups.
ABDM: ABHA registration/verification, link records, consent-based sharing (HISGenX & LIS GenX V3).

LIS HIGHLIGHTS
Sample-to-signed-report tracking; bi-directional analyzers; rule-based auto-validation; real-time TAT; multi-branch and collection centres; report delivery portal/WhatsApp/SMS/email.

EMR / DOCTOR WORKSTATION
Clinical notes, e-prescriptions, lab/radiology orders, allergies & vitals, results at point of care, ABHA-linked records.

SUPPORT & ENGAGEMENT
Demo on request; WhatsApp Business signup available on site; resources include brochures, FAQs, training, remote support, raise ticket.

DISTRICTS / REGIONS MENTIONED
Hyderabad, Rangareddy, Guntur, Warangal, Mahbubnagar, Nalgonda, Vijayawada, Secunderabad, Chittoor, Anantapur, Krishna, Prakasam, Kurnool, Visakhapatnam (Vizag), West Godavari, Rajahmundry, and broader Andhra Pradesh / Telangana coverage. Offices also in Bangalore and Vijayawada.

SOLUTIONS (solution lines, not only modules)
- Hospital Information System (HIS/HIMS): registration, billing, clinical workflows, pharmacy, lab, radiology, inventory, finance on one platform.
- Laboratory Information System (LIS): sample collection, analyzer integration, QC, reporting, billing, NABL traceability.
- Radiology Information System (RIS): scheduling, reporting, PACS/DICOM imaging workflows.
- Pharmacy management: OPD/IPD/OT/ward pharmacy, procurement, batch/expiry, dispensing, billing.
- Electronic Medical Records (EMR/EHR): history, orders, results at point of care.
- Blood bank: donor, screening, components, storage, cross-match, issue, traceability.
- Nursing station: ward rounds, vitals, medication admin, care plans, shift handover.
- OT management: scheduling, pre-op checklists, consumables, surgical notes, CSSD link.
- Housekeeping: bed turnaround, laundry, sanitation tasks, SLA tracking.
- HR & payroll: staff lifecycle, attendance, biometric, statutory payroll, rosters.
- Inventory & procurement: medical/general stores, indents, PO, GRN, vendors, stock valuation.
- Finance & accounts: credit billing, taxation, MIS, Tally-ready.
- Mobile applications: doctor, patient, management apps (Android & iOS).
- Patient portal: appointments, online reports, e-Rx, payments, teleconsultation.

PLATFORM FEATURES
- NABH / NABL / CAP accreditation support in daily workflows and quality boards.
- HL7 clinical data exchange; FHIR support.
- PACS / DICOM imaging to clinician interface.
- Open APIs (Tally, NMC, biometric, devices, third-party apps).
- Cloud hosting or on-premises (same product).
- Multi-location: hospitals, branches, labs from one console.
- Mobile access and native apps.
- Security: role-based access, encryption, tamper-evident audit trails, backups, DR.

AI HEALTHCARE PLATFORM (Sahasra HISGenX)
Positioned as “Digital Brain of Modern Healthcare.” Unifies HIS, ERP, LIS, RIS, EMR/EHR, pharmacy, finance, analytics, patient engagement and AI on one patient record.
Six platform pillars: (1) one patient record (2) AI inside existing screens (3) cloud or own servers (4) clinical workflows OPD/wards/OT/ER (5) live management numbers (6) security & standards (ABDM, HL7, FHIR, DICOM).
AI capabilities: clinical report auto-drafts; ICD/CPT coding suggestions; revenue intelligence; predictive dashboards (footfall, beds, inventory); voice documentation; clinical decision support (allergies, interactions, protocols).
Architecture layers: Experience (portal, WhatsApp, doctor/nurse apps, kiosks, TV) → Intelligence (AI, predictive analytics, BI) → Clinical/ops core (HIS, LIS, RIS/PACS, EMR, pharmacy, OT, blood bank, ERP) → Data/security foundation (single record, RBAC, ABDM/NABH/NABL, HL7/FHIR/DICOM, cloud/on-prem).
Implementation stance: configuration, training and go-live support done by Athentech (not handed off to random third parties); software alone is not enough without workflow setup.

ABDM (Ayushman Bharat Digital Mission) — V3
Sahasra HISGenX and Sahasra LIS GenX support documentation-based ABDM V3 integration.
Covers: ABHA-enabled registration; ABHA identification & verification; linking hospital/lab records to ABHA; consent-based digital sharing; connected hospital and lab processes.
Front-desk flow: patient provides/creates ABHA → staff verify → demographics auto-fill → consults/labs/discharge linked when finalized → share with other providers on consent.
ABDM is in the core product, not a separate gateway bolt-on. Minimal workflow change. May relate to Digital Health Incentive Scheme eligibility (check official ABDM terms).

WHY ORGANIZATIONS CHOOSE SAHASRA
20+ years healthcare systems; 592+ orgs; 43+ modules; AI-enabled platform; cloud & on-prem; real-time BI; multi-location scale; secure & interoperable; implementation and training in-house.

PATIENT JOURNEY (CONNECTED)
Patient → Registration → Consultation → Lab → Radiology → Pharmacy → Billing → EMR → Discharge — one shared record, no retyping.

ANALYTICS / COMMAND CENTER
Advanced Analytics & BI (revenue, collections, department & payer mix); Ward Command Center (live vitals, overdue alerts); Smart TV dashboards (tokens, nursing, diagnostics); Executive MIS via WhatsApp for management/CXOs.

SUPPORT CHANNELS
Sales demo and pricing; support ticket / remote support / training / documentation; WhatsApp Business signup for healthcare messaging; resources: brochures, videos, blog, FAQs, downloads, news, events.
Hours: Mon–Sat 9:30 AM – 6:30 PM IST; 24×7 critical support.
Contact pages: /contact/, /contact/request-demo/, /contact/sales/, /contact/support/, /contact/locations/.

FAQS (PLATFORM)
What is Sahasra HISGenX? Hospital platform combining HIS, ERP, LIS, RIS, EMR, pharmacy, finance, dashboards and patient apps on one patient record.
Cloud or on-prem? Both, plus hybrid; scales from clinic to multi-campus college/diagnostic chain.
ABDM and NABH? Yes — ABHA/HFR/HPR/consent records; designed for NABH, NABL, CAP with HL7/FHIR/DICOM.
How does AI help staff? Less paperwork via assisted reporting, coding, CDS, voice notes, predictive and executive dashboards.

LEGAL / SITE
Privacy policy, terms and conditions, cookies policy published on athentech.co.in.
Brand names: ATHEN TECH / Athentech; product family Sahasra / Sahasra-Infini.

"""

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