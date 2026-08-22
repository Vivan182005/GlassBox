import os
import re
import json
import hashlib
import datetime
from typing import Dict, Any, Optional, List, Tuple
import requests
from dotenv import load_dotenv

load_dotenv()

# Reuse the same broad, domain-spanning skills vocabulary used by the resume
# extractor so a candidate's extracted skills and a job's extracted skills are
# matched against the same taxonomy.
try:
    from parsing.profile_extractor import _SKILLS_VOCABULARY
except Exception:
    _SKILLS_VOCABULARY = [
        "Python", "Java", "C++", "JavaScript", "TypeScript", "SQL", "React", "Node.js",
        "Machine Learning", "Deep Learning", "PyTorch", "TensorFlow", "AWS", "Docker",
        "Kubernetes", "Product Management", "SQL", "Tableau", "REST APIs"
    ]

# ---------------------------------------------------------------------------
# Supabase client -- this is now the ONLY persistence layer. No JSON files,
# no in-memory fake dataset. If Supabase isn't configured, the service says
# so explicitly rather than silently falling back to fabricated postings.
# ---------------------------------------------------------------------------
supabase_client = None
SUPABASE_CONFIGURED = False
try:
    from supabase import create_client
    s_url = os.environ.get("SUPABASE_URL", "").strip()
    s_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip() or os.environ.get("SUPABASE_ANON_KEY", "").strip()
    if s_url and s_key:
        supabase_client = create_client(s_url, s_key)
        SUPABASE_CONFIGURED = True
except Exception as e:
    print("Supabase client init in job_discovery_service:", e)

# ---------------------------------------------------------------------------
# JSearch (RapidAPI) -- a real job-search aggregator (LinkedIn + Indeed +
# Glassdoor + Google for Jobs). LinkedIn itself does not expose a public job
# search API to individual developers -- that requires a Talent Solutions
# partnership, which is why the previous "Official LinkedIn API" branch never
# actually worked and silently fell through to fake data every time.
#
# Get a free RAPIDAPI_KEY at https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch
# and set RAPIDAPI_KEY in your .env. Free tier is enough for portfolio-scale use.
# ---------------------------------------------------------------------------
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "").strip()
JSEARCH_HOST = "jsearch.p.rapidapi.com"
JSEARCH_URL = f"https://{JSEARCH_HOST}/search"

DATE_POSTED_OPTIONS = {"all", "today", "3days", "week", "month"}

CACHE_FRESHNESS_HOURS = 6          # re-use cached Supabase results if fetched within this window
MAX_PAGES_PER_QUERY = 15           # JSearch returns ~10 results/page -> up to ~150 raw results per query
TARGET_RESULT_CAP = 200            # hard ceiling on how many filtered jobs we ever return


# ===========================================================================
# Helpers
# ===========================================================================

def _map_max_age_to_date_posted(max_age: str) -> str:
    max_age = (max_age or "").lower()
    if "1" in max_age and "day" in max_age:
        return "today"
    if "3" in max_age:
        return "3days"
    if "7" in max_age or "week" in max_age:
        return "week"
    if "30" in max_age or "month" in max_age:
        return "month"
    return "month"


def _posted_cutoff(date_posted: str) -> Optional[datetime.datetime]:
    days_map = {"today": 1, "3days": 3, "week": 7, "month": 30}
    days = days_map.get(date_posted)
    if not days:
        return None
    return datetime.datetime.utcnow() - datetime.timedelta(days=days)


def _extract_skills_from_text(text: str) -> List[str]:
    if not text:
        return []
    found = []
    for s in _SKILLS_VOCABULARY:
        if re.search(r"(?<![A-Za-z0-9])" + re.escape(s) + r"(?![A-Za-z0-9])", text, re.IGNORECASE):
            found.append(s)
    return found


def _search_signature(target_roles: List[str], locations: List[str], date_posted: str) -> str:
    raw = json.dumps({
        "roles": sorted([r.lower() for r in target_roles]),
        "locations": sorted([l.lower() for l in locations]),
        "date_posted": date_posted
    }, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _matches_location(job: Dict[str, Any], requested_locations: List[str]) -> bool:
    """Strict, no-fallback location check against the NORMALIZED job schema
    (city/state/country/is_remote -- see normalize_jsearch_job / _row_to_job_dict).
    If nothing matches, the job is excluded -- never silently included just to
    pad out the result count."""
    if not requested_locations:
        return True
    job_city = (job.get("city") or "").lower()
    job_state = (job.get("state") or "").lower()
    job_country = (job.get("country") or "").lower()
    is_remote = bool(job.get("is_remote"))
    haystack = f"{job_city} {job_state} {job_country}"

    for loc in requested_locations:
        loc_lower = loc.lower()
        if "remote" in loc_lower and is_remote:
            return True
        # Tokenize the requested location, dropping generic country/state
        # words so "Bengaluru, Karnataka, India" reduces to a real city token.
        tokens = [t for t in re.split(r"[,\s]+", loc_lower) if t and t not in {"karnataka", "india", "remote"}]
        for tok in tokens:
            if tok in ("bangalore", "bengaluru") and ("bengaluru" in haystack or "bangalore" in haystack):
                return True
            if tok and tok in haystack:
                return True
    return False


def _role_relevance(job_title: str, target_roles: List[str], job_skills: List[str], candidate_skills: List[str]) -> float:
    """Returns 0.0 for genuinely irrelevant postings -- these get excluded, not
    padded in. This is the direct fix for 'Product Analyst' searches returning
    unrelated roles: there is no catch-all fallback below."""
    title_lower = (job_title or "").lower()

    if any(r.lower() in title_lower for r in target_roles):
        return 1.0

    token_hits = 0
    for r in target_roles:
        for tok in r.lower().split():
            if len(tok) > 2 and re.search(r"\b" + re.escape(tok) + r"\b", title_lower):
                token_hits += 1

    skill_overlap = len(set(s.lower() for s in job_skills) & set(s.lower() for s in candidate_skills))

    if token_hits >= 1 and skill_overlap >= 1:
        return 0.75
    if skill_overlap >= 3:
        return 0.55
    return 0.0


# ===========================================================================
# JSearch provider -- fetches real, current postings. No synthetic data.
# ===========================================================================

class JSearchProvider:
    def __init__(self):
        self.api_key = RAPIDAPI_KEY

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def fetch_raw_jobs(self, role_query: str, location_query: str, date_posted: str) -> List[Dict[str, Any]]:
        if not self.is_configured():
            raise RuntimeError(
                "RAPIDAPI_KEY is not set. Job discovery requires a real data source -- "
                "get a free key at https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch "
                "and set RAPIDAPI_KEY in your environment. Refusing to return placeholder jobs."
            )

        headers = {"X-RapidAPI-Key": self.api_key, "X-RapidAPI-Host": JSEARCH_HOST}
        query = f"{role_query} in {location_query}" if location_query else role_query

        collected: List[Dict[str, Any]] = []
        seen_ids = set()

        for page in range(1, MAX_PAGES_PER_QUERY + 1):
            params = {
                "query": query,
                "page": str(page),
                "num_pages": "1",
                "date_posted": date_posted if date_posted in DATE_POSTED_OPTIONS else "month"
            }
            try:
                resp = requests.get(JSEARCH_URL, headers=headers, params=params, timeout=15)
                resp.raise_for_status()
                payload = resp.json()
            except Exception as e:
                print(f"JSearch request failed on page {page}:", e)
                break

            page_jobs = payload.get("data") or []
            if not page_jobs:
                break  # no more results -- stop paginating rather than looping needlessly

            new_this_page = 0
            for job in page_jobs:
                jid = job.get("job_id")
                if jid and jid not in seen_ids:
                    seen_ids.add(jid)
                    collected.append(job)
                    new_this_page += 1

            if new_this_page == 0:
                break  # API started repeating itself -- exhausted real results
            if len(collected) >= TARGET_RESULT_CAP:
                break

        return collected


# ===========================================================================
# Supabase persistence -- replaces JSON entirely.
#
# Expected schema (create once in Supabase SQL editor):
#
#   create table if not exists jobs (
#     external_id text primary key,
#     source text not null default 'jsearch',
#     title text,
#     company_name text,
#     location text,
#     city text,
#     state text,
#     country text,
#     work_mode text,
#     is_remote boolean,
#     employment_type text,
#     salary_text text,
#     skills jsonb,
#     description text,
#     apply_url text,
#     posted_at timestamptz,
#     fetched_at timestamptz default now()
#   );
#
#   create table if not exists job_search_cache (
#     search_signature text primary key,
#     job_external_ids jsonb,
#     fetched_at timestamptz default now()
#   );
# ===========================================================================

class SupabaseJobStore:
    def __init__(self, client):
        self.client = client

    def get_cached_job_ids(self, signature: str) -> Optional[List[str]]:
        if not self.client:
            return None
        try:
            res = self.client.table("job_search_cache").select("*").eq("search_signature", signature).limit(1).execute()
            if not res.data:
                return None
            entry = res.data[0]
            fetched_at = entry.get("fetched_at")
            if not fetched_at:
                return None
            fetched_dt = datetime.datetime.fromisoformat(str(fetched_at).replace("Z", "+00:00"))
            age_hours = (datetime.datetime.now(datetime.timezone.utc) - fetched_dt).total_seconds() / 3600
            if age_hours > CACHE_FRESHNESS_HOURS:
                return None
            return entry.get("job_external_ids") or []
        except Exception as e:
            print("Supabase cache read notice:", e)
            return None

    def get_jobs_by_ids(self, ids: List[str]) -> List[Dict[str, Any]]:
        if not self.client or not ids:
            return []
        try:
            res = self.client.table("jobs").select("*").in_("external_id", ids).execute()
            return res.data or []
        except Exception as e:
            print("Supabase jobs read notice:", e)
            return []

    def upsert_jobs(self, normalized_jobs: List[Dict[str, Any]]) -> None:
        if not self.client or not normalized_jobs:
            return
        try:
            rows = []
            for j in normalized_jobs:
                rows.append({
                    "external_id": j["external_id"],
                    "source": "jsearch",
                    "title": j["title"],
                    "company_name": j["company_name"],
                    "location": j["location"],
                    "city": j.get("city"),
                    "state": j.get("state"),
                    "country": j.get("country"),
                    "work_mode": j.get("work_mode"),
                    "is_remote": j.get("is_remote", False),
                    "employment_type": j.get("employment_type"),
                    "salary_text": j.get("salary_text"),
                    "skills": j.get("skills", []),
                    "description": j.get("description", ""),
                    "apply_url": j.get("apply_url"),
                    "posted_at": j.get("posted_at"),
                    "fetched_at": datetime.datetime.utcnow().isoformat()
                })
            self.client.table("jobs").upsert(rows, on_conflict="external_id").execute()
        except Exception as e:
            print("Supabase jobs upsert notice:", e)

    def write_cache_entry(self, signature: str, job_ids: List[str]) -> None:
        if not self.client:
            return
        try:
            self.client.table("job_search_cache").upsert({
                "search_signature": signature,
                "job_external_ids": job_ids,
                "fetched_at": datetime.datetime.utcnow().isoformat()
            }, on_conflict="search_signature").execute()
        except Exception as e:
            print("Supabase cache write notice:", e)


# ===========================================================================
# Normalization -- raw JSearch job -> GlassBox schema
# ===========================================================================

def normalize_jsearch_job(raw: Dict[str, Any]) -> Dict[str, Any]:
    description = raw.get("job_description") or ""
    # JSearch sometimes returns explicit required-skills; when absent, derive
    # them the same way profile_extractor derives resume skills, from the
    # actual description text -- never a hardcoded per-job skill list.
    explicit_skills = raw.get("job_required_skills")
    skills = explicit_skills if isinstance(explicit_skills, list) and explicit_skills else _extract_skills_from_text(description)

    city = raw.get("job_city") or ""
    state = raw.get("job_state") or ""
    country = raw.get("job_country") or ""
    location_str = ", ".join([p for p in [city, state, country] if p]) or ("Remote" if raw.get("job_is_remote") else "Not specified")

    min_sal = raw.get("job_min_salary")
    max_sal = raw.get("job_max_salary")
    currency = raw.get("job_salary_currency") or ""
    period = raw.get("job_salary_period") or ""
    if min_sal and max_sal:
        salary_text = f"{currency} {min_sal:,.0f} - {max_sal:,.0f} / {period}".strip()
    else:
        salary_text = "Not disclosed"

    return {
        "external_id": raw.get("job_id"),
        "title": raw.get("job_title") or "Untitled Position",
        "company_name": raw.get("employer_name") or "Unknown Company",
        "location": location_str,
        "city": city or None,
        "state": state or None,
        "country": country or None,
        "work_mode": "Remote" if raw.get("job_is_remote") else "On-Site/Hybrid",
        "is_remote": bool(raw.get("job_is_remote")),
        "employment_type": raw.get("job_employment_type") or "Full-time",
        "salary_text": salary_text,
        "skills": skills,
        "description": description,
        "apply_url": raw.get("job_apply_link") or raw.get("job_google_link"),
        "posted_at": raw.get("job_posted_at_datetime_utc"),
    }


def _row_to_job_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    """Supabase row -> same shape normalize_jsearch_job() produces, so both
    the live-fetch path and the cache-read path feed the ranking step identically."""
    return {
        "external_id": row.get("external_id"),
        "title": row.get("title"),
        "company_name": row.get("company_name"),
        "location": row.get("location"),
        "city": row.get("city"),
        "state": row.get("state"),
        "country": row.get("country"),
        "work_mode": row.get("work_mode"),
        "is_remote": row.get("is_remote", False),
        "employment_type": row.get("employment_type"),
        "salary_text": row.get("salary_text"),
        "skills": row.get("skills") or [],
        "description": row.get("description") or "",
        "apply_url": row.get("apply_url"),
        "posted_at": row.get("posted_at"),
    }


# ===========================================================================
# Main service
# ===========================================================================

class JobDiscoveryService:
    def __init__(self):
        self.provider = JSearchProvider()
        self.store = SupabaseJobStore(supabase_client)

    def search_and_rank_jobs(
        self,
        preferences: Dict[str, Any],
        decision_factors: Optional[Dict[str, float]] = None,
        api_key_override: Optional[str] = None  # reserved: optional future Groq-generated "why matched" copy
    ) -> Dict[str, Any]:

        target_roles = [r.strip() for r in (preferences.get("target_roles") or []) if r.strip()]
        preferred_locations = [l.strip() for l in (preferences.get("preferred_locations") or []) if l.strip()]
        candidate_skills = [s.strip() for s in (preferences.get("skills") or []) if s.strip()]
        candidate_exp = float(preferences.get("years_experience") or 0.0)
        max_age = preferences.get("maximum_posting_age") or "month"

        if not target_roles:
            return {"status": "error", "message": "At least one target role is required.", "jobs": [], "total_found": 0}
        if not preferred_locations:
            return {"status": "error", "message": "At least one preferred location is required.", "jobs": [], "total_found": 0}

        date_posted = _map_max_age_to_date_posted(max_age) if not preferences.get("date_posted") else preferences["date_posted"]
        signature = _search_signature(target_roles, preferred_locations, date_posted)

        raw_jobs_normalized: List[Dict[str, Any]] = []
        served_from_cache = False

        cached_ids = self.store.get_cached_job_ids(signature)
        if cached_ids:
            rows = self.store.get_jobs_by_ids(cached_ids)
            if rows:
                raw_jobs_normalized = [_row_to_job_dict(r) for r in rows]
                served_from_cache = True

        if not raw_jobs_normalized:
            if not self.provider.is_configured():
                return {
                    "status": "error",
                    "provider": "JSearch",
                    "message": (
                        "Job discovery has no working data source configured. Set RAPIDAPI_KEY to a "
                        "valid JSearch (RapidAPI) key -- this service will not return placeholder jobs."
                    ),
                    "jobs": [],
                    "total_found": 0
                }
            all_raw: List[Dict[str, Any]] = []
            for role in target_roles:
                for loc in preferred_locations:
                    try:
                        page_jobs = self.provider.fetch_raw_jobs(role, loc, date_posted)
                        all_raw.extend(page_jobs)
                    except Exception as e:
                        print("JSearch fetch failed for", role, loc, ":", e)

            # Dedup across role/location query combinations
            dedup: Dict[str, Dict[str, Any]] = {}
            for j in all_raw:
                jid = j.get("job_id")
                if jid:
                    dedup[jid] = j

            raw_jobs_normalized = [normalize_jsearch_job(j) for j in dedup.values()]
            self.store.upsert_jobs(raw_jobs_normalized)
            self.store.write_cache_entry(signature, [j["external_id"] for j in raw_jobs_normalized if j.get("external_id")])

        if not raw_jobs_normalized:
            return {
                "status": "empty",
                "provider": "JSearch",
                "message": "No live postings were returned for this role/location/date combination.",
                "jobs": [],
                "total_found": 0
            }

        # --- Strict local filtering (no blanket fallback that discards constraints) ---
        cutoff = _posted_cutoff(date_posted)
        filtered: List[Dict[str, Any]] = []
        for job in raw_jobs_normalized:
            if not _matches_location(job, preferred_locations):
                continue

            if cutoff and job.get("posted_at"):
                try:
                    posted_dt = datetime.datetime.fromisoformat(str(job["posted_at"]).replace("Z", "+00:00")).replace(tzinfo=None)
                    if posted_dt < cutoff:
                        continue
                except Exception:
                    pass  # unparsable date -- don't discard solely for that

            relevance = _role_relevance(job["title"], target_roles, job["skills"], candidate_skills)
            if relevance <= 0.0:
                continue

            matched_skills = [s for s in job["skills"] if s.lower() in [c.lower() for c in candidate_skills]]
            missing_skills = [s for s in job["skills"] if s.lower() not in [c.lower() for c in candidate_skills]]
            skill_score = (len(matched_skills) / len(job["skills"])) if job["skills"] else 0.5

            df = decision_factors or {}
            w_title = df.get("title_match", 0.40)
            w_skills = df.get("skill_match", 0.40)
            w_exp = df.get("experience", 0.20)
            exp_score = 1.0 if candidate_exp >= 0 else 0.5  # placeholder weight; real gating is relevance+location above

            composite = (relevance * w_title) + (skill_score * w_skills) + (exp_score * w_exp)
            match_percentage = min(99, max(40, int(composite * 100)))

            why_matched = (
                f"Title/skills overlap with '{job['title']}': {', '.join(matched_skills[:4])}"
                if matched_skills else f"Role relevance match on '{job['title']}' in {job['location']}"
            )

            filtered.append({
                **job,
                "match_percentage": match_percentage,
                "matched_skills": matched_skills,
                "missing_skills": missing_skills,
                "why_matched": why_matched
            })

        filtered.sort(key=lambda x: x["match_percentage"], reverse=True)
        filtered = filtered[:TARGET_RESULT_CAP]

        return {
            "status": "success" if filtered else "empty",
            "provider": "JSearch (cache)" if served_from_cache else "JSearch (live)",
            "total_found": len(filtered),
            "message": None if filtered else (
                f"{len(raw_jobs_normalized)} postings were fetched for this query, but none matched "
                f"the requested location/role/date filters strictly enough to show. Try broadening "
                f"the location or role."
            ),
            "jobs": filtered
        }


job_discovery_engine = JobDiscoveryService()
