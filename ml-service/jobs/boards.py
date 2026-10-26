"""
Live job-board connectors for the public posting APIs that ATS vendors expose
for each customer's careers page (Greenhouse, Lever, Ashby, SmartRecruiters,
Workday). Because every job is read straight from the company's own ATS, the
ATS behind each posting is known for certain, with no guessing.

The companies scanned are listed in data/company_registry.json; each entry
was verified to have live India postings when the registry was built.
"""
import os
import re
import json
import html
import time
import threading
import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests

from ats.profiles import get_profile

REGISTRY_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "company_registry.json")
WORKDAY_INDIA_ID = "c4f78be1a8f14da0ab49ce1162348a5e"
HEADERS = {"User-Agent": "Mozilla/5.0 (GlassBox job scanner)", "Accept": "application/json"}
BOARD_TTL = 30 * 60

INDIA_CITIES: Dict[str, List[str]] = {
    "Bengaluru": ["bengaluru", "bangalore", "blr"],
    "Hyderabad": ["hyderabad", "secunderabad"],
    "Pune": ["pune"],
    "Mumbai": ["mumbai", "navi mumbai", "thane", "bombay"],
    "Delhi NCR": ["delhi", "new delhi", "gurgaon", "gurugram", "noida", "greater noida", "faridabad", "ghaziabad", "ncr"],
    "Chennai": ["chennai", "madras"],
    "Kolkata": ["kolkata", "calcutta"],
    "Ahmedabad": ["ahmedabad", "gandhinagar", "gift city"],
    "Jaipur": ["jaipur"],
    "Kochi": ["kochi", "cochin", "trivandrum", "thiruvananthapuram"],
    "Coimbatore": ["coimbatore"],
    "Chandigarh": ["chandigarh", "mohali", "panchkula"],
    "Indore": ["indore"],
    "Mysuru": ["mysore", "mysuru"],
}
_INDIA_RE = re.compile(r"\bindia\b|" +"|".join(re.escape(a) for al in INDIA_CITIES.values() for a in al), re.IGNORECASE)
_REMOTE_RE = re.compile(r"remote|work from home|wfh|anywhere", re.IGNORECASE)

_session = requests.Session()
_session.headers.update(HEADERS)
_cache: Dict[str, Tuple[float, Any]] = {}
_cache_lock = threading.Lock()


def load_registry() -> List[Dict[str, Any]]:
    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["companies"]


def _cached(key: str, ttl: float, fn):
    with _cache_lock:
        hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    value = fn()
    with _cache_lock:
        _cache[key] = (time.time(), value)
    return value


def html_to_text(raw: str) -> str:
    if not raw:
        return ""
    text = html.unescape(raw)
    text = re.sub(r"(?i)<\s*(br|/p|/div|/li|/h\d|/tr)\s*/?>", "\n", text)
    text = re.sub(r"(?i)<\s*li[^>]*>", "\n• ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def india_cities_in(location: str) -> List[str]:
    loc = (location or "").lower()
    return [city for city, aliases in INDIA_CITIES.items() if any(re.search(r"\b" + re.escape(a) + r"\b", loc) for a in aliases)]


def is_india(location: str) -> bool:
    return bool(_INDIA_RE.search(location or ""))


def _posted_label(iso: Optional[str]) -> Tuple[Optional[str], Optional[int]]:
    if not iso:
        return None, None
    try:
        dt = _parse_iso(iso)
        days = (datetime.datetime.now(datetime.timezone.utc) - dt).days
        return dt.isoformat(), max(days, 0)
    except Exception:
        return None, None


def _parse_iso(iso: Any) -> datetime.datetime:
    if isinstance(iso, (int, float)):  # epoch milliseconds (Lever)
        return datetime.datetime.fromtimestamp(iso / 1000, tz=datetime.timezone.utc)
    dt = datetime.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=datetime.timezone.utc)


def posted_hours(job: Dict[str, Any]) -> Optional[float]:
    """Hours since posting when the board gives a timestamp; None when it only
    gives a day count (Workday's "Posted Today")."""
    if not job.get("posted_at"):
        return None
    try:
        return max(0.0, (datetime.datetime.now(datetime.timezone.utc) - _parse_iso(job["posted_at"])).total_seconds() / 3600)
    except Exception:
        return None


def _job(company: Dict[str, Any], job_id: str, title: str, location: str, url: str,
         posted_iso: Optional[str] = None, posted_days: Optional[int] = None, department: Optional[str] = None,
         description: Optional[str] = None, remote: bool = False, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    profile = get_profile(company["ats"])
    if posted_days is None:
        posted_iso, posted_days = _posted_label(posted_iso)
    return {
        "id": f"{company['ats']}:{company['slug']}:{job_id}",
        "ats_id": company["ats"],
        "ats_name": profile["name"],
        "company": company["name"],
        "company_slug": company["slug"],
        "domain": company.get("domain"),
        "title": (title or "").strip(),
        "location": (location or "").strip() or "India",
        "cities": india_cities_in(location) or [],
        "remote": remote or bool(_REMOTE_RE.search(location or "")),
        "posted_at": posted_iso,
        "posted_days": posted_days,
        "department": department,
        "url": url,
        "description": description,
        "source": "company_ats",
        **(extra or {}),
    }


# --------------------------------------------------------------------------
# Greenhouse
# --------------------------------------------------------------------------

def _greenhouse_list(company: Dict[str, Any]) -> List[Dict[str, Any]]:
    r = _session.get(f"https://boards-api.greenhouse.io/v1/boards/{company['slug']}/jobs", timeout=15)
    r.raise_for_status()
    out = []
    for j in r.json().get("jobs", []):
        loc = (j.get("location") or {}).get("name", "")
        offices = " ".join(o.get("name", "") for o in j.get("offices", []) or [])
        if not is_india(f"{loc} {offices}"):
            continue
        out.append(_job(company, str(j["id"]), j.get("title"), loc, j.get("absolute_url"),
                        posted_iso=j.get("first_published") or j.get("updated_at")))
    return out


def _greenhouse_detail(company: Dict[str, Any], job_id: str) -> str:
    r = _session.get(f"https://boards-api.greenhouse.io/v1/boards/{company['slug']}/jobs/{job_id}", timeout=15)
    r.raise_for_status()
    return html_to_text(r.json().get("content", ""))


# --------------------------------------------------------------------------
# Lever
# --------------------------------------------------------------------------

def _lever_text(j: Dict[str, Any]) -> str:
    parts = [j.get("openingPlain") or "", j.get("descriptionPlain") or html_to_text(j.get("description") or "")]
    for lst in j.get("lists") or []:
        parts.append((lst.get("text") or "") + "\n" + html_to_text(lst.get("content") or ""))
    parts.append(j.get("additionalPlain") or "")
    return "\n\n".join(p for p in parts if p.strip()).strip()


def _lever_list(company: Dict[str, Any]) -> List[Dict[str, Any]]:
    r = _session.get(f"https://api.lever.co/v0/postings/{company['slug']}?mode=json", timeout=15)
    r.raise_for_status()
    out = []
    for j in r.json():
        cats = j.get("categories") or {}
        loc = ", ".join([cats.get("location") or ""] + [l for l in (cats.get("allLocations") or []) if l != cats.get("location")]).strip(", ")
        if not (j.get("country") == "IN" or is_india(loc)):
            continue
        created = j.get("createdAt")
        iso = datetime.datetime.fromtimestamp(created / 1000, tz=datetime.timezone.utc).isoformat() if created else None
        out.append(_job(company, j["id"], j.get("text"), loc.title() if loc.islower() else loc, j.get("hostedUrl"),
                        posted_iso=iso, department=cats.get("department") or cats.get("team"),
                        description=_lever_text(j), remote=(j.get("workplaceType") == "remote")))
    return out


# --------------------------------------------------------------------------
# Ashby
# --------------------------------------------------------------------------

def _ashby_list(company: Dict[str, Any]) -> List[Dict[str, Any]]:
    r = _session.get(f"https://api.ashbyhq.com/posting-api/job-board/{company['slug']}", timeout=15)
    r.raise_for_status()
    out = []
    for j in r.json().get("jobs", []):
        if j.get("isListed") is False:
            continue
        locs = [j.get("location") or ""] + [s.get("location", "") for s in j.get("secondaryLocations") or []]
        country = ((j.get("address") or {}).get("postalAddress") or {}).get("addressCountry") or ""
        loc_str = ", ".join(l for l in locs if l)
        if not is_india(f"{loc_str} {country}"):
            continue
        out.append(_job(company, j["id"], j.get("title"), loc_str or country, j.get("jobUrl"),
                        posted_iso=j.get("publishedAt"), department=j.get("department"),
                        description=j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml") or ""),
                        remote=bool(j.get("isRemote"))))
    return out


# --------------------------------------------------------------------------
# SmartRecruiters
# --------------------------------------------------------------------------

def _smartrecruiters_list(company: Dict[str, Any], query: str = "") -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    offset = 0
    while offset < (100 if query else 300):
        params = {"country": "in", "limit": 100, "offset": offset}
        if query:
            params["q"] = query
        r = _session.get(f"https://api.smartrecruiters.com/v1/companies/{company['slug']}/postings", params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        for j in data.get("content", []):
            loc = j.get("location") or {}
            loc_str = ", ".join(p for p in [(loc.get("city") or "").title(), loc.get("region") or "", "India"] if p)
            out.append(_job(company, str(j["id"]), j.get("name"), loc_str,
                            f"https://jobs.smartrecruiters.com/{company['slug']}/{j['id']}",
                            posted_iso=j.get("releasedDate"), department=(j.get("function") or {}).get("label"),
                            remote=bool(loc.get("remote"))))
        offset += 100
        if offset >= data.get("totalFound", 0):
            break
    return out


def _smartrecruiters_detail(company: Dict[str, Any], job_id: str) -> Tuple[str, Optional[str]]:
    r = _session.get(f"https://api.smartrecruiters.com/v1/companies/{company['slug']}/postings/{job_id}", timeout=15)
    r.raise_for_status()
    d = r.json()
    sections = ((d.get("jobAd") or {}).get("sections") or {})
    parts = []
    for key in ("jobDescription", "qualifications", "additionalInformation", "companyDescription"):
        sec = sections.get(key) or {}
        if sec.get("text"):
            parts.append(f"{sec.get('title', '')}\n{html_to_text(sec['text'])}")
    return "\n\n".join(parts), d.get("postingUrl")


# --------------------------------------------------------------------------
# Workday
# --------------------------------------------------------------------------

def _workday_base(company: Dict[str, Any]) -> str:
    return f"https://{company['slug']}.{company['wd']}.myworkdayjobs.com"


_WD_POSTED = re.compile(r"(\d+)\+?\s+Days?\s+Ago", re.IGNORECASE)


def _workday_posted(label: str) -> Optional[int]:
    if not label:
        return None
    if re.search(r"today", label, re.IGNORECASE):
        return 0
    if re.search(r"yesterday", label, re.IGNORECASE):
        return 1
    m = _WD_POSTED.search(label)
    return int(m.group(1)) if m else None


def _workday_list(company: Dict[str, Any], query: str = "") -> List[Dict[str, Any]]:
    url = f"{_workday_base(company)}/wday/cxs/{company['slug']}/{company['site']}/jobs"
    facet = company.get("india_facet")
    out: List[Dict[str, Any]] = []
    # A role query returns relevance-sorted results, so the first page is enough.
    for offset in ((0,) if query else (0, 20, 40)):
        body: Dict[str, Any] = {"appliedFacets": {}, "limit": 20, "offset": offset, "searchText": query}
        if facet:
            body["appliedFacets"] = {facet: [WORKDAY_INDIA_ID]}
        else:
            body["searchText"] = f"{query} India".strip()
        r = _session.post(url, json=body, headers={"Content-Type": "application/json"}, timeout=15)
        r.raise_for_status()
        data = r.json()
        posts = data.get("jobPostings", [])
        for p in posts:
            path = p.get("externalPath") or ""
            loc_text = p.get("locationsText") or ""
            path_city = path.split("/job/")[1].split("/")[0].replace("-", " ") if "/job/" in path else ""
            location = loc_text if not re.match(r"\d+ Locations", loc_text) else f"{path_city} + more"
            if not facet and not (is_india(loc_text) or is_india(path_city)):
                continue
            days = _workday_posted(p.get("postedOn") or "")
            out.append(_job(company, path, p.get("title"), location,
                            f"{_workday_base(company)}/{company['site']}{path}", posted_days=days))
        if len(posts) < 20 or offset + 20 >= data.get("total", 0):
            break
    return out


def _workday_detail(company: Dict[str, Any], path: str) -> str:
    r = _session.get(f"{_workday_base(company)}/wday/cxs/{company['slug']}/{company['site']}{path}", timeout=15)
    r.raise_for_status()
    info = r.json().get("jobPostingInfo") or {}
    return html_to_text(info.get("jobDescription") or "")


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

_LISTERS = {"greenhouse": _greenhouse_list, "lever": _lever_list, "ashby": _ashby_list}
_SEARCHERS = {"smartrecruiters": _smartrecruiters_list, "workday": _workday_list}


def fetch_company_jobs(company: Dict[str, Any], queries: List[str]) -> List[Dict[str, Any]]:
    """All India postings for a company. Boards without server-side search are
    fetched whole and cached; search-capable boards are queried per role."""
    ats = company["ats"]
    if ats in _LISTERS:
        return _cached(f"list:{ats}:{company['slug']}", BOARD_TTL, lambda: _LISTERS[ats](company))
    jobs: Dict[str, Dict[str, Any]] = {}
    for q in queries[:2] or [""]:
        for j in _cached(f"search:{ats}:{company['slug']}:{q.lower()}", BOARD_TTL, lambda q=q: _SEARCHERS[ats](company, q)):
            jobs[j["id"]] = j
    return list(jobs.values())


def find_company(slug_or_name: str) -> Optional[Dict[str, Any]]:
    key = re.sub(r"[^a-z0-9]", "", (slug_or_name or "").lower())
    for c in load_registry():
        if key in (re.sub(r"[^a-z0-9]", "", c["slug"].lower()), re.sub(r"[^a-z0-9]", "", c["name"].lower())):
            return c
    return None


def fetch_job_description(job_id: str) -> Dict[str, Any]:
    """job_id has the form '{ats}:{slug}:{native id}'. Returns {description, url}."""
    try:
        ats, slug, native = job_id.split(":", 2)
    except ValueError:
        return {"description": "", "url": None, "error": "Malformed job id"}
    company = next((c for c in load_registry() if c["slug"] == slug and c["ats"] == ats), None)
    if not company:
        return {"description": "", "url": None, "error": "Unknown company"}

    def run():
        if ats == "greenhouse":
            return {"description": _greenhouse_detail(company, native), "url": None}
        if ats == "smartrecruiters":
            desc, url = _smartrecruiters_detail(company, native)
            return {"description": desc, "url": url}
        if ats == "workday":
            return {"description": _workday_detail(company, native), "url": f"{_workday_base(company)}/{company['site']}{native}"}
        for j in fetch_company_jobs(company, []):
            if j["id"] == job_id:
                return {"description": j.get("description") or "", "url": j["url"]}
        return {"description": "", "url": None, "error": "Posting no longer listed"}

    try:
        return _cached(f"detail:{job_id}", 6 * 3600, run)
    except Exception as e:
        return {"description": "", "url": None, "error": f"Could not load description: {str(e)[:120]}"}
