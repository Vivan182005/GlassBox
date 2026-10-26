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
import os
import re
import warnings
from typing import Any, Dict, List
from urllib.parse import quote_plus, urlparse

import requests

from jobs.boards import india_cities_in, html_to_text

RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "").strip()

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


def jsearch(query: str, city: str = "", pages: int = 2) -> List[Dict[str, Any]]:
    """Live aggregated listings via JSearch; empty when RAPIDAPI_KEY isn't set."""
    if not RAPIDAPI_KEY:
        return []
    from ats.detector import detect_from_url
    headers = {"X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": "jsearch.p.rapidapi.com"}
    out: List[Dict[str, Any]] = []
    try:
        r = requests.get("https://jsearch.p.rapidapi.com/search", headers=headers, timeout=20, params={
            "query": f"{query} in {city or 'India'}", "page": "1", "num_pages": str(pages),
            "country": "in", "date_posted": "month",
        })
        r.raise_for_status()
        for j in r.json().get("data") or []:
            apply = j.get("job_apply_link") or j.get("job_google_link") or ""
            ats = detect_from_url(apply)
            loc = ", ".join(p for p in [j.get("job_city"), j.get("job_state"), j.get("job_country")] if p)
            out.append({
                "id": f"jsearch:{j.get('job_id')}",
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
                "ats_id": ats["id"] if ats else None,
                "ats_name": ats["name"] if ats else None,
                "source": "network",
                "via": j.get("job_publisher") or "JSearch",
            })
    except Exception as e:
        print("JSearch failed:", str(e)[:160])
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
