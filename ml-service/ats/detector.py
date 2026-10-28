"""
Company -> ATS detection, with an evidence trail for every step.

  1. Verified registry (data/company_registry.json): boards confirmed live.
  2. Saved result (user-confirmed or a fresh verified result, 90-day TTL).
  3. Live probes of the ATS vendors' public JSON APIs. These answer 404 or an
     empty result for companies that don't exist, so a hit is real. (The old
     code probed HTML pages; jobs.smartrecruiters.com answers 200 for *any*
     name, so every unknown company was "verified" as SmartRecruiters.)
  4. Web fingerprinting: the company's careers pages and search results are
     scanned for ATS URLs and embed scripts.
  5. AI estimate, clearly labelled as unverified.
If nothing is found, the caller falls back to searching the wider network.
"""
import os
import re
import json
import time
import threading
import concurrent.futures as cf
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests

from ats.profiles import ATS_PROFILES, get_profile, public_profile
from core.llm import llm_json
from core.netsafe import safe_get
from jobs.boards import load_registry, fetch_company_jobs, is_india

CACHE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "ats_lookup_cache.json")
TTL_SECONDS = 90 * 86400
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"}
CRAWLER_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; GlassBox/2.0; +https://github.com/Vivan182005/GlassBox)"}
_SUFFIXES = {"pvt", "private", "ltd", "limited", "inc", "llc", "llp", "corp", "corporation", "co", "company", "technologies",
             "technology", "tech", "labs", "india", "software", "solutions", "services", "group", "global", "the", "and"}
_lock = threading.Lock()


# --------------------------------------------------------------------------
# Fingerprints
# --------------------------------------------------------------------------

def detect_from_url(url: str) -> Optional[Dict[str, Any]]:
    u = (url or "").lower()
    if not u:
        return None
    for p in ATS_PROFILES:
        if any(re.search(pat, u) for pat in p["url_patterns"]):
            return p
    return None


def detect_from_html(page: str) -> Optional[Tuple[Dict[str, Any], str]]:
    for p in ATS_PROFILES:
        for sig in p["html_signatures"]:
            m = re.search(sig, page, re.IGNORECASE)
            if m:
                return p, m.group(0)
    return None


# --------------------------------------------------------------------------
# Cache
# --------------------------------------------------------------------------

def _load_cache() -> Dict[str, Any]:
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(key: str, value: Dict[str, Any]) -> None:
    with _lock:
        cache = _load_cache()
        cache[key] = value
        try:
            with open(CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(cache, f, indent=1)
        except Exception as e:
            print("ATS cache write failed:", e)


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _base_tokens(name: str) -> List[str]:
    toks = re.findall(r"[a-z0-9]+", (name or "").lower())
    core = [t for t in toks if t not in _SUFFIXES]
    return core or toks


def _slug_variants(name: str) -> List[str]:
    toks = re.findall(r"[a-z0-9]+", (name or "").lower())
    core = _base_tokens(name)
    variants = ["".join(core), "-".join(core), "".join(toks), "-".join(toks)]
    if len(core) > 1:
        variants.append(core[0])
    seen, out = set(), []
    for v in variants:
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out[:5]


def _similar(a: str, b: str) -> bool:
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return False
    return a in b or b in a or SequenceMatcher(None, a, b).ratio() > 0.75


# --------------------------------------------------------------------------
# Step 3: live vendor API probes
# --------------------------------------------------------------------------

def _probe(ats: str, slug: str, company: str) -> Optional[Dict[str, Any]]:
    try:
        if ats == "greenhouse":
            r = requests.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", headers=HEADERS, timeout=8)
            if r.status_code != 200:
                return None
            jobs = r.json().get("jobs", [])
            meta = requests.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}", headers=HEADERS, timeout=8).json()
            board_name = meta.get("name") or slug
            india = sum(1 for j in jobs if is_india((j.get("location") or {}).get("name", "")))
            url = f"https://job-boards.greenhouse.io/{slug}"
        elif ats == "lever":
            r = requests.get(f"https://api.lever.co/v0/postings/{slug}?mode=json", headers=HEADERS, timeout=8)
            if r.status_code != 200 or not isinstance(r.json(), list):
                return None
            jobs = r.json()
            board_name = slug
            india = sum(1 for j in jobs if j.get("country") == "IN" or is_india((j.get("categories") or {}).get("location", "")))
            url = f"https://jobs.lever.co/{slug}"
        elif ats == "ashby":
            r = requests.get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}", headers=HEADERS, timeout=8)
            if r.status_code != 200:
                return None
            jobs = r.json().get("jobs", [])
            board_name = slug
            india = sum(1 for j in jobs if is_india(j.get("location", "")))
            url = f"https://jobs.ashbyhq.com/{slug}"
        elif ats == "smartrecruiters":
            r = requests.get(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings", params={"limit": 1}, headers=HEADERS, timeout=8)
            if r.status_code != 200:
                return None
            data = r.json()
            if not data.get("totalFound"):
                return None
            board_name = ((data.get("content") or [{}])[0].get("company") or {}).get("name") or slug
            jobs = [None] * data["totalFound"]
            india = requests.get(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings", params={"limit": 1, "country": "in"},
                                 headers=HEADERS, timeout=8).json().get("totalFound", 0)
            url = f"https://jobs.smartrecruiters.com/{slug}"
        elif ats in _TENANT_PAGES:
            return _probe_tenant(ats, slug, company)
        else:
            return None
    except Exception:
        return None
    if ats in ("greenhouse", "smartrecruiters") and not _similar(board_name, company):
        return None
    return {"ats": ats, "slug": slug, "board_name": board_name, "total_jobs": len(jobs), "india_jobs": india, "url": url}


# Hosted careers sites of ATS vendors common in India. Each answers an unknown
# tenant with a recognisable "not found" page, so a different answer is a hit.
_TENANT_PAGES = {
    "darwinbox": ("https://{slug}.darwinbox.in/ms/candidate/careers", lambda url, body: bool(re.search(r"<title>\s*[^<\s]", body))),
    "keka": ("https://{slug}.keka.com/careers/", lambda url, body: "TenantNotFound" not in url and "keka" in body.lower()),
    "zoho_recruit": ("https://{slug}.zohorecruit.in/jobs/Careers", lambda url, body: "cl-error-block" not in body and "zoho" in body.lower()),
    "freshteam": ("https://{slug}.freshteam.com/jobs", lambda url, body: "invalid-domain-wrapper" not in body),
    "icims": ("https://careers-{slug}.icims.com/jobs", lambda url, body: True),
}


def _probe_tenant(ats: str, slug: str, company: str) -> Optional[Dict[str, Any]]:
    template, is_live = _TENANT_PAGES[ats]
    # A crawler user agent gets the server-rendered page, which names the tenant;
    # browsers get an identical JavaScript shell for real and unknown tenants.
    r = safe_get(template.format(slug=slug), headers=CRAWLER_HEADERS, timeout=8)
    if r.status_code != 200 or not is_live(r.url, r.text):
        return None
    title = re.search(r"<title>\s*([^<\s][^<]{0,119})", r.text)
    board_name = title.group(1).strip() if title else slug
    if ats == "darwinbox" and not _similar(board_name, company):
        return None
    return {"ats": ats, "slug": slug, "board_name": board_name, "total_jobs": None, "india_jobs": None, "url": r.url}


def _probe_all(company: str) -> List[Dict[str, Any]]:
    vendors = ("greenhouse", "lever", "ashby", "smartrecruiters") + tuple(_TENANT_PAGES)
    tasks = [(ats, slug) for slug in _slug_variants(company)[:3] for ats in vendors]
    hits = []
    with cf.ThreadPoolExecutor(max_workers=12) as ex:
        for res in ex.map(lambda t: _probe(t[0], t[1], company), tasks):
            if res:
                hits.append(res)
    hits.sort(key=lambda h: (h["india_jobs"] or 0, h["total_jobs"] or 0), reverse=True)
    return hits


# --------------------------------------------------------------------------
# Step 4: web fingerprinting
# --------------------------------------------------------------------------

def _fetch(url: str) -> Tuple[str, str]:
    try:
        r = safe_get(url, headers=HEADERS, timeout=7)
        if r.status_code < 400 and "html" in r.headers.get("content-type", "html"):
            return r.url, r.text[:600_000]
    except Exception:
        pass
    return "", ""


def _scan_page(url: str) -> Optional[Dict[str, Any]]:
    """Returns {"profile", "url", "how"} on a hit, {"profile": None, "url"} when the
    page loaded but showed no ATS, and None when it couldn't be loaded."""
    final_url, body = _fetch(url)
    if not body:
        return None
    hit = detect_from_url(final_url)
    if hit:
        return {"profile": hit, "url": final_url, "how": f"careers page redirects to {urlparse(final_url).hostname}"}
    for href in re.findall(r"""(?:href|src|action)\s*=\s*["']([^"']+)["']""", body, re.IGNORECASE):
        absolute = urljoin(final_url, href)
        hit = detect_from_url(absolute)
        if hit:
            return {"profile": hit, "url": absolute, "how": f"careers page links to {urlparse(absolute).hostname}"}
    sig = detect_from_html(body)
    if sig:
        return {"profile": sig[0], "url": final_url, "how": f"page embeds '{sig[1]}'"}
    return {"profile": None, "url": final_url}


def _web_fingerprint(company: str, evidence: List[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, str]], Optional[str]]:
    from jobs.network import web_search, site_of
    base = _base_tokens(company)
    joined = "".join(base)
    results = web_search(f"{company} careers jobs", max_results=12) + web_search(f"{company} careers apply", max_results=8)

    listings, seen = [], set()
    for r in results:
        label = site_of(r["url"])
        if label and r["url"] not in seen:
            seen.add(r["url"])
            listings.append({"title": r["title"], "url": r["url"], "source": label})

    for r in results:
        hit = detect_from_url(r["url"])
        if hit:
            evidence.append({"step": "Web fingerprint", "outcome": "hit", "detail": f"Search result points to a {hit['name']} job board", "url": r["url"]})
            return {"profile": hit, "url": r["url"], "how": "search result is an ATS-hosted job page"}, listings, r["url"]

    candidates = []
    for r in results:
        host = urlparse(r["url"]).hostname or ""
        path = urlparse(r["url"]).path.lower()
        if not site_of(r["url"]) and any(t in host for t in base if len(t) > 2) and re.search(r"career|job|join|hiring|work-with", path + host):
            candidates.append(r["url"])
    for guess in (f"https://www.{joined}.com/careers", f"https://{joined}.com/careers", f"https://careers.{joined}.com",
                  f"https://www.{joined}.in/careers", f"https://{joined}.in/careers", f"https://www.{joined}.com/jobs"):
        candidates.append(guess)
    candidates = list(dict.fromkeys(candidates))[:9]

    careers_url = None
    with cf.ThreadPoolExecutor(max_workers=9) as ex:
        scans = list(ex.map(_scan_page, candidates))
    for res in scans:
        if res and res["profile"]:
            evidence.append({"step": "Web fingerprint", "outcome": "hit", "detail": f"{res['profile']['name']} detected: {res['how']}", "url": res["url"]})
            return res, listings, res["url"]
        if res and not careers_url:
            careers_url = res["url"]
    evidence.append({"step": "Web fingerprint", "outcome": "miss",
                     "detail": f"Scanned {len(candidates)} careers pages and {len(results)} search results; no ATS script or link found",
                     "url": careers_url})
    return None, listings, careers_url


# --------------------------------------------------------------------------
# Step 5: AI estimate
# --------------------------------------------------------------------------

def _ai_estimate(company: str) -> Optional[Dict[str, Any]]:
    ids = ", ".join(p["id"] for p in ATS_PROFILES)
    data = llm_json(
        "You are an HR-tech analyst. Given a company (assume its India operations), say which applicant tracking "
        f"system it most likely uses. Allowed ats_id values: {ids}, unknown. Also give its careers page URL if you know it. "
        'Return JSON: {"ats_id": "...", "careers_url": "https://... or null", "confidence": "medium|low", "reasoning": "one line"}',
        f"Company: {company}", max_tokens=300)
    if not data:
        return None
    return data


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def _registry_hit(company: str) -> Optional[Dict[str, Any]]:
    key = _norm(company)
    core = "".join(_base_tokens(company))
    for c in load_registry():
        if key in (_norm(c["name"]), _norm(c["slug"])) or (core and core == _norm(c["name"])):
            return c
    return None


def _result(company: str, status: str, profile: Optional[Dict[str, Any]], confidence: float, method: str,
            evidence: List[Dict[str, Any]], **extra) -> Dict[str, Any]:
    return {
        "company": company, "status": status, "ats": public_profile(profile) if profile else None,
        "confidence": round(confidence, 2), "method": method, "evidence": evidence,
        "checked_at": time.time(), **extra,
    }


def lookup_company(company: str, use_cache: bool = True) -> Dict[str, Any]:
    company = (company or "").strip()
    if not company:
        return _result("", "not_found", None, 0.0, "none", [{"step": "Input", "outcome": "miss", "detail": "No company name given"}])
    key = _norm(company)
    evidence: List[Dict[str, Any]] = []

    reg = _registry_hit(company)
    if reg:
        evidence.append({"step": "Verified registry", "outcome": "hit",
                         "detail": f"{reg['name']} posts its jobs on {get_profile(reg['ats'])['name']} (board '{reg['slug']}')"})
        return _result(reg["name"], "verified", get_profile(reg["ats"]), 0.99, "registry", evidence,
                       board={"ats": reg["ats"], "slug": reg["slug"], "registry": True}, domain=reg.get("domain"))
    evidence.append({"step": "Verified registry", "outcome": "miss", "detail": "Not one of the pre-verified companies"})

    if use_cache:
        cached = _load_cache().get(key)
        ttl = TTL_SECONDS if cached and cached.get("status") == "verified" else 7 * 86400
        if cached and (cached.get("method") == "user_confirmed" or time.time() - cached.get("checked_at", 0) < ttl):
            cached["cached"] = True
            return cached

    probes = _probe_all(company)
    if probes:
        best = probes[0]
        profile = get_profile(best["ats"])
        counts = (f" with {best['total_jobs']} openings ({best['india_jobs']} in India)" if best["total_jobs"] is not None else "")
        evidence.append({"step": "Live ATS probe", "outcome": "hit",
                         "detail": f"{profile['name']} careers site for '{best['board_name']}' is live{counts}",
                         "url": best["url"]})
        res = _result(company, "verified", profile, 0.95, "api_probe", evidence, board=best, careers_url=best["url"])
        _save_cache(key, res)
        return res
    evidence.append({"step": "Live ATS probe", "outcome": "miss",
                     "detail": "No Greenhouse, Lever, Ashby, SmartRecruiters, Darwinbox, Keka, Zoho Recruit, Freshteam or iCIMS site under this name"})

    web_hit, listings, careers_url = _web_fingerprint(company, evidence)
    if web_hit:
        res = _result(company, "verified", web_hit["profile"], 0.88, "web_fingerprint", evidence,
                      careers_url=web_hit["url"], network_listings=listings)
        _save_cache(key, res)
        return res

    est = _ai_estimate(company)
    if est and est.get("careers_url"):
        scanned = _scan_page(est["careers_url"])
        if scanned and scanned["profile"]:
            evidence.append({"step": "AI lead, verified", "outcome": "hit",
                             "detail": f"Careers URL suggested by AI; the page confirms {scanned['profile']['name']} ({scanned['how']})",
                             "url": scanned["url"]})
            res = _result(company, "verified", scanned["profile"], 0.85, "web_fingerprint", evidence,
                          careers_url=scanned["url"], network_listings=listings)
            _save_cache(key, res)
            return res
    if est and est.get("ats_id") and est["ats_id"] != "unknown":
        profile = get_profile(est["ats_id"])
        evidence.append({"step": "AI estimate", "outcome": "estimate",
                         "detail": f"Unverified guess: {profile['name']}. {est.get('reasoning', '')}".strip()})
        res = _result(company, "estimate", profile, 0.4 if est.get("confidence") == "low" else 0.55, "ai_estimate", evidence,
                      careers_url=careers_url or est.get("careers_url"), network_listings=listings)
        _save_cache(key, res)
        return res

    evidence.append({"step": "AI estimate", "outcome": "miss", "detail": "No confident estimate available"})
    res = _result(company, "not_found", None, 0.0, "none", evidence, careers_url=careers_url, network_listings=listings)
    _save_cache(key, res)
    return res


def confirm_company_ats(company: str, ats_id: str) -> Dict[str, Any]:
    from ats.profiles import PROFILE_BY_ID
    company = company.strip()[:120]
    if not _norm(company) or (ats_id or "").lower() not in PROFILE_BY_ID:
        raise ValueError("Unknown company or ATS.")
    profile = get_profile(ats_id)
    res = _result(company, "verified", profile, 1.0, "user_confirmed",
                  [{"step": "User confirmation", "outcome": "hit", "detail": f"Confirmed as {profile['name']} by a user"}])
    # The cache is shared by every user, so a confirmation can fill a gap but
    # never overwrite an ATS that was found on the company's real job board.
    prior = _load_cache().get(_norm(company)) or {}
    if prior.get("status") == "verified" and prior.get("method") not in ("user_confirmed", None):
        return prior
    _save_cache(_norm(company), res)
    return res


def company_board_jobs(lookup: Dict[str, Any], queries: List[str]) -> List[Dict[str, Any]]:
    """India openings from the company's own board, when we know where it is."""
    board = lookup.get("board") or {}
    if not board.get("slug") or board.get("ats") not in ("greenhouse", "lever", "ashby", "smartrecruiters", "workday"):
        return []
    company = next((c for c in load_registry() if c["slug"] == board["slug"] and c["ats"] == board["ats"]), None)
    if not company:
        company = {"name": lookup["company"], "slug": board["slug"], "ats": board["ats"], "domain": lookup.get("domain")}
    try:
        return fetch_company_jobs(company, queries)
    except Exception as e:
        print("company board fetch failed:", e)
        return []
