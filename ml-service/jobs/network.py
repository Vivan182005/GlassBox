"""
"Whole network" search for when a company's own ATS board isn't available.

Sources, in order of reliability:
  1. JSearch (RapidAPI) when RAPIDAPI_KEY is set: aggregates LinkedIn, Naukri,
     Indeed, Glassdoor and Google for Jobs listings.
  2. Web search (DuckDuckGo) for company-specific careers pages and listings
     on Indian job sites.
  3. Prebuilt search links on the major job sites, so the user can always
     continue the search there in one click.
"""
import json
import os
import re
import threading
import time
import warnings
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus, urlparse

import requests

from jobs.boards import india_cities_in, html_to_text

RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "").strip()

# Network listings have no API to re-read them by id, so the description seen
# at search time is kept (memory + disk) for rating and tailoring later.
_STORE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "network_jobs.json")
_STORE_TTL = 7 * 86400
_store_lock = threading.Lock()
_store: Dict[str, Dict[str, Any]] = {}


def _load_store() -> None:
    try:
        with open(_STORE_PATH) as f:
            data = json.load(f)
        cutoff = time.time() - _STORE_TTL
        _store.update({k: v for k, v in data.items() if v.get("seen", 0) > cutoff})
    except (OSError, ValueError):
        pass


_load_store()


def remember(jobs: List[Dict[str, Any]]) -> None:
    now = time.time()
    with _store_lock:
        for j in jobs:
            _store[j["id"]] = {"description": j.get("description") or "", "url": j.get("url"), "seen": now}
        try:
            os.makedirs(os.path.dirname(_STORE_PATH), exist_ok=True)
            with open(_STORE_PATH, "w") as f:
                json.dump(_store, f)
        except OSError:
            pass


def network_description(job_id: str) -> Dict[str, Any]:
    hit = _store.get(job_id)
    if not hit:
        return {"description": "", "url": None, "error": "This listing is no longer cached. Search again to refresh it."}
    return {"description": hit["description"], "url": hit["url"]}


def network_status() -> Dict[str, Any]:
    return {"jsearch": bool(RAPIDAPI_KEY), "jsearch_credits_left": _jsearch_quota["remaining"]}


# A listing whose apply link is a company's own Greenhouse, Lever or Ashby
# board gets that board's id, so its real form can be read and auto-filled.
_BOARD_URLS = [
    ("greenhouse", r"greenhouse\.io/(?:embed/job_app\?for=)?([\w-]+)(?:/jobs/|&token=)(\d+)"),
    ("lever", r"jobs\.(?:eu\.)?lever\.co/([\w.-]+)/([0-9a-f-]{36})"),
    ("ashby", r"jobs\.ashbyhq\.com/([\w.%-]+)/([0-9a-f-]{36})"),
]


def board_id(url: str) -> Optional[str]:
    for ats, pat in _BOARD_URLS:
        m = re.search(pat, url or "", re.I)
        if m:
            return f"{ats}:{m.group(1)}:{m.group(2)}"
    return None


def _min_years(months: Any) -> Optional[float]:
    try:
        return round(float(months) / 12, 1) if months not in (None, "") else None
    except (TypeError, ValueError):
        return None

JOB_SITES = {
    "linkedin.com": "LinkedIn", "naukri.com": "Naukri", "instahyre.com": "Instahyre", "foundit.in": "foundit",
    "indeed.com": "Indeed", "glassdoor.co.in": "Glassdoor", "glassdoor.com": "Glassdoor", "wellfound.com": "Wellfound",
    "cutshort.io": "Cutshort", "iimjobs.com": "iimjobs", "hirist.tech": "hirist", "hirist.com": "hirist",
    "unstop.com": "Unstop", "internshala.com": "Internshala", "apna.co": "apna", "shine.com": "Shine",
}


def web_search(query: str, max_results: int = 10) -> List[Dict[str, str]]:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from duckduckgo_search import DDGS
            return [{"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", "")}
                    for r in DDGS(timeout=10).text(query, max_results=max_results, region="in-en", backend="html")]
    except Exception as e:
        print("web search failed:", str(e)[:120])
        return []


def site_of(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    for domain, label in JOB_SITES.items():
        if host == domain or host.endswith("." + domain):
            return label
    return ""


def search_links(keywords: str, city: str = "") -> List[Dict[str, str]]:
    q = quote_plus(keywords)
    loc = quote_plus(f"{city}, India" if city else "India")
    slug = re.sub(r"[^a-z0-9]+", "-", keywords.lower()).strip("-")
    city_slug = re.sub(r"[^a-z0-9]+", "-", (city or "").lower()).strip("-")
    naukri = f"https://www.naukri.com/{slug}-jobs" + (f"-in-{city_slug}" if city_slug else "")
    return [
        {"label": "LinkedIn", "url": f"https://www.linkedin.com/jobs/search/?keywords={q}&location={loc}"},
        {"label": "Naukri", "url": naukri},
        {"label": "Indeed", "url": f"https://in.indeed.com/jobs?q={q}&l={quote_plus(city or 'India')}"},
        {"label": "Instahyre", "url": f"https://www.instahyre.com/search-jobs/?search={q}"},
        {"label": "Wellfound", "url": f"https://wellfound.com/jobs?query={q}"},
        {"label": "foundit", "url": f"https://www.foundit.in/srp/results?query={q}&locations={quote_plus(city or 'India')}"},
    ]


_JSEARCH_AGE = {1: "today", 3: "3days", 7: "week", 30: "month"}

# The free JSearch plan has a small monthly allowance, so identical searches
# reuse results for a few hours, and searching pauses when RapidAPI reports the
# allowance nearly spent (rechecked once a day, since it renews monthly).
_JSEARCH_TTL = 6 * 3600
_JSEARCH_RESERVE = 5
_jsearch_cache: Dict[tuple, tuple] = {}
_jsearch_quota = {"remaining": None, "checked": 0.0}


def jsearch(query: str, city: str = "", pages: int = 2, max_age_days: Optional[int] = None,
            internships: bool = False) -> List[Dict[str, Any]]:
    """Live aggregated listings via JSearch; empty when RAPIDAPI_KEY isn't set."""
    if not RAPIDAPI_KEY:
        return []
    from ats.detector import detect_from_url
    from ats.profiles import get_profile
    headers = {"X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": "jsearch.p.rapidapi.com"}
    age = next((v for d, v in sorted(_JSEARCH_AGE.items()) if max_age_days and max_age_days <= d), "month")
    params = {"query": f"{query} in {city or 'India'}", "num_pages": str(pages), "country": "in", "date_posted": age}
    if internships:
        params["employment_types"] = "INTERN"
    key = tuple(sorted(params.items()))
    hit = _jsearch_cache.get(key)
    if hit and time.time() - hit[0] < _JSEARCH_TTL:
        return [dict(j) for j in hit[1]]
    low = _jsearch_quota["remaining"] is not None and _jsearch_quota["remaining"] <= _JSEARCH_RESERVE
    if low and time.time() - _jsearch_quota["checked"] < 86400:
        return []
    out: List[Dict[str, Any]] = []
    try:
        r = requests.get("https://jsearch.p.rapidapi.com/search-v2", headers=headers, timeout=25, params=params)
        left = r.headers.get("x-ratelimit-requests-remaining")
        if left and left.isdigit():
            _jsearch_quota.update(remaining=int(left), checked=time.time())
        r.raise_for_status()
        data = r.json().get("data") or {}
        # search-v2 returns {"jobs": [...], "cursor": ...}; the retired /search returned the list itself.
        for j in data.get("jobs") or [] if isinstance(data, dict) else data:
            options = [o.get("apply_link") for o in j.get("apply_options") or [] if o.get("apply_link")]
            apply = j.get("job_apply_link") or j.get("job_google_link") or ""
            # Prefer the company's own ATS link when one of the apply options is it.
            board = next((board_id(u) for u in [apply, *options] if board_id(u)), None)
            if board:
                apply = next(u for u in [apply, *options] if board_id(u) == board)
            ats = detect_from_url(apply)
            if board:
                ats = get_profile(board.split(":")[0])
            loc = ", ".join(p for p in [j.get("job_city"), j.get("job_state"), j.get("job_country")] if p)
            exp = j.get("job_required_experience") or {}
            out.append({
                "id": board or f"jsearch:{j.get('job_id')}",
                "title": j.get("job_title") or "",
                "company": j.get("employer_name") or "",
                "domain": (urlparse(j.get("employer_website") or "").hostname or "").replace("www.", "") or None,
                "location": loc or "India",
                "cities": india_cities_in(loc),
                "remote": bool(j.get("job_is_remote")),
                "posted_at": j.get("job_posted_at_datetime_utc"),
                "posted_days": None,
                "url": apply,
                "description": html_to_text(j.get("job_description") or ""),
                "listed_min_years": _min_years(exp.get("required_experience_in_months")),
                "ats_id": ats["id"] if ats else None,
                "ats_name": ats["name"] if ats else None,
                "source": "network",
                "via": j.get("job_publisher") or "JSearch",
            })
    except Exception as e:
        print("JSearch failed:", str(e)[:160])
        return out
    _jsearch_cache[key] = (time.time(), [dict(j) for j in out])
    remember([j for j in out if j["id"].startswith("jsearch:")])
    return out


def company_listings(company: str, role: str = "") -> List[Dict[str, str]]:
    """Listings for a company on Indian job sites, found via web search."""
    results = web_search(f"{company} {role} jobs India".strip(), max_results=15)
    seen, out = set(), []
    for r in results:
        label = site_of(r["url"])
        if label and r["url"] not in seen:
            seen.add(r["url"])
            out.append({"title": r["title"], "url": r["url"], "source": label, "snippet": r["snippet"][:200]})
    return out
