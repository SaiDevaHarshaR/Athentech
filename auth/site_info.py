"""Website knowledge for white-label public (B2C) chat.

Reads the client's own public website (BeautifulSoup), keeps it for 12 hours, and gives the assistant the few pages that
match the visitor's question plus the contact details found on the site. Public pages only, no login, no client database.
Never raises into the caller: any failure returns "" (the assistant then says it does not have that detail).
"""
from __future__ import annotations

import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlparse

TTL = 12 * 3600
MAX_PAGES = 30
PAGE_CHARS = 3500
CONTEXT_CHARS = 6000
_UA = {"User-Agent": "Mozilla/5.0 (compatible; SahasraAssistant/1.0; +https://www.athentech.co.in)"}
_SKIP_EXT = re.compile(r"\.(pdf|jpe?g|png|gif|svg|webp|zip|docx?|xlsx?|mp4|mp3|css|js|ico)(\?|$)", re.I)
_PRIORITY = ("contact", "about", "service", "test", "package", "location", "branch", "centre", "center", "timing", "home-collection", "faq", "prepar")
_STOP = set("the a an is are of to for in on at do you your we our what how can i me my and or with about please tell".split())

_cache: dict = {}        # site -> {"at": ts, "pages": {url: text}, "facts": str}
_lock = threading.Lock()
_busy: set = set()


def normalize(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    if not re.match(r"^https?://", u, re.I):
        u = "https://" + u
    p = urlparse(u)
    if not p.netloc or "." not in p.netloc:
        return ""
    return "%s://%s/" % (p.scheme.lower(), p.netloc.lower())


def _get(url: str, timeout: int = 8):
    import requests
    r = requests.get(url, headers=_UA, timeout=timeout)
    r.raise_for_status()
    return r


def _text(html: str) -> str:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript", "svg", "iframe", "form"]):
        t.decompose()
    title = (soup.title.get_text(" ", strip=True) if soup.title else "")
    body = soup.get_text(" ", strip=True)
    body = re.sub(r"\s+", " ", body)
    return (title + " | " + body).strip(" |")[:PAGE_CHARS]


def _links(html: str, base: str) -> list:
    from bs4 import BeautifulSoup
    host = urlparse(base).netloc.replace("www.", "")
    out = []
    for a in BeautifulSoup(html, "html.parser").find_all("a", href=True):
        u = urljoin(base, a["href"]).split("#")[0]
        p = urlparse(u)
        if p.scheme in ("http", "https") and p.netloc.replace("www.", "") == host and not _SKIP_EXT.search(u) and u not in out:
            out.append(u)
    return out


def _sitemap(base: str) -> list:
    try:
        x = _get(base + "sitemap.xml").text
        host = urlparse(base).netloc.replace("www.", "")
        urls = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", x)
        return [u for u in urls if urlparse(u).netloc.replace("www.", "") == host and not _SKIP_EXT.search(u) and not u.endswith(".xml")]
    except Exception:
        return []


def _facts(pages: dict) -> str:
    blob = " ".join(pages.values())
    phones = []
    for m in re.finditer(r"(?<!\d)(\+?91[\s-]?)?([6-9]\d{4}[\s-]?\d{5}|0\d{2,4}[\s-]?\d{6,8}|1800[\s-]?\d{3}[\s-]?\d{4})(?!\d)", blob):
        v = re.sub(r"\s+", " ", m.group(0)).strip()
        if v not in phones:
            phones.append(v)
    emails = []
    for m in re.finditer(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", blob):
        if m.group(0).lower() not in [e.lower() for e in emails]:
            emails.append(m.group(0))
    out = []
    if phones:
        out.append("Phone numbers on the website: " + ", ".join(phones[:6]))
    if emails:
        out.append("Emails on the website: " + ", ".join(emails[:4]))
    return "\n".join(out)


def _build(site: str) -> dict:
    home = _get(site).text
    urls = [site]
    for u in _sitemap(site) + _links(home, site):
        if u.rstrip("/") not in [x.rstrip("/") for x in urls]:
            urls.append(u)
    urls = sorted(urls[1:], key=lambda u: (0 if any(k in u.lower() for k in _PRIORITY) else 1)) 
    urls = [site] + urls[:MAX_PAGES - 1]
    pages = {site: _text(home)}

    def one(u):
        try:
            return u, _text(_get(u).text)
        except Exception:
            return u, ""
    with ThreadPoolExecutor(max_workers=6) as ex:
        for u, t in ex.map(one, urls[1:]):
            if t and len(t) > 80:
                pages[u] = t
    return {"at": time.time(), "pages": pages, "facts": _facts(pages)}


def refresh(url: str, force: bool = False) -> bool:
    site = normalize(url)
    if not site:
        return False
    with _lock:
        cur = _cache.get(site)
        if cur and not force and time.time() - cur["at"] < TTL:
            return True
        if site in _busy:
            return bool(cur)
        _busy.add(site)
    try:
        data = _build(site)
        with _lock:
            _cache[site] = data
        return True
    except Exception as e:
        print("[site_info] could not read %s: %s" % (site, type(e).__name__), flush=True)
        return bool(_cache.get(site))
    finally:
        with _lock:
            _busy.discard(site)


def _words(q: str) -> list:
    return [w for w in re.findall(r"[a-z0-9]{3,}", (q or "").lower()) if w not in _STOP]


def context_for(url: str, question: str) -> str:
    """Text the assistant may use for this question ('' when the site cannot be read)."""
    try:
        site = normalize(url)
        if not site:
            return ""
        cur = _cache.get(site)
        if not cur or time.time() - cur["at"] > TTL:
            if cur:      # stale copy is fine for this answer; refresh in the background
                threading.Thread(target=refresh, args=(site, True), daemon=True).start()
            else:
                refresh(site)
                cur = _cache.get(site)
        if not cur:
            return ""
        ws = _words(question)
        scored = []
        for u, t in cur["pages"].items():
            low = (u + " " + t).lower()
            s = sum(low.count(w) for w in ws) + (3 if any(k in u.lower() for k in ("contact", "about")) else 0) + (5 if u == site else 0)
            scored.append((s, u, t))
        scored.sort(key=lambda x: -x[0])
        out, used = [], 0
        for s, u, t in scored:
            if used >= CONTEXT_CHARS:
                break
            chunk = t[:max(600, min(PAGE_CHARS, CONTEXT_CHARS - used))]
            out.append("[%s] %s" % (u, chunk))
            used += len(chunk)
        facts = cur.get("facts") or ""
        return (facts + "\n\n" if facts else "") + "\n\n".join(out)
    except Exception:
        return ""


def status(url: str) -> dict:
    site = normalize(url)
    cur = _cache.get(site) if site else None
    return {"site": site, "pages": len(cur["pages"]) if cur else 0, "age_min": int((time.time() - cur["at"]) / 60) if cur else None}
