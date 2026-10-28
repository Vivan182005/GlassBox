"""
India job discovery across the verified company network.

Flow: expand the candidate's target roles into the title phrases recruiters
actually use (LLM, with a built-in role-family map as fallback) -> scan every
company board in parallel -> keep titles in the candidate's role family ->
enrich the best matches with full descriptions -> rank by title, skill and
seniority fit.
"""
import re
import time
import threading
import concurrent.futures as cf
from typing import Any, Dict, List, Optional

from core.llm import llm_json
from jobs.boards import load_registry, fetch_company_jobs, fetch_job_description, india_cities_in, posted_hours
from jobs.network import jsearch, network_status, search_links
from matching.skills_lexicon import find_skills, SOFT_CATEGORY, skill_category
from matching.ats_check import years_required

ROLE_FAMILIES: Dict[str, List[str]] = {
    "software": ["software engineer", "software developer", "sde", "software development engineer", "backend", "back end", "back-end",
                 "frontend", "front end", "front-end", "full stack", "fullstack", "full-stack", "web developer", "application developer",
                 "member of technical staff", "mts", "java developer", "python developer", "node developer", "react developer",
                 "golang developer", "mobile developer", "android developer", "android engineer", "ios developer", "ios engineer",
                 "product engineer", "application engineer", "software development"],
    "data_analytics": ["data analyst", "business analyst", "analytics", "business intelligence", "bi analyst", "bi developer",
                       "product analyst", "insights analyst", "reporting analyst", "mis analyst", "decision scientist", "strategy analyst"],
    "data_science": ["data scientist", "data science", "machine learning", "ml engineer", "ai engineer", "applied scientist",
                     "research scientist", "nlp", "computer vision", "deep learning", "genai", "generative ai", "ai/ml", "ml scientist",
                     "ai research", "llm", "mlops"],
    "data_engineering": ["data engineer", "analytics engineer", "etl", "big data", "data platform", "data infrastructure"],
    "devops": ["devops", "site reliability", "sre", "cloud engineer", "platform engineer", "infrastructure engineer", "cloud architect",
               "systems engineer", "production engineer"],
    "product": ["product manager", "associate product manager", "apm", "product owner", "product lead", "group product manager",
                "technical product manager", "product management", "senior product manager"],
    "design": ["product designer", "ui designer", "ux designer", "ui/ux", "ux/ui", "interaction designer", "visual designer", "ux researcher",
               "design lead"],
    "qa": ["qa engineer", "test engineer", "sdet", "quality assurance", "automation engineer", "test automation", "quality engineer",
           "qa analyst", "software tester"],
    "security": ["security engineer", "security analyst", "cyber security", "cybersecurity", "soc analyst", "penetration tester",
                 "appsec", "information security", "security operations", "threat"],
    "hardware": ["embedded", "firmware", "vlsi", "asic", "fpga", "hardware engineer", "design verification", "physical design",
                 "silicon", "rtl"],
    "marketing": ["marketing", "growth", "seo", "content", "brand", "performance marketing", "social media", "communications"],
    "sales": ["sales", "account executive", "business development", "account manager", "inside sales", "pre-sales", "presales",
              "customer success", "partnerships"],
    "finance": ["finance", "financial analyst", "accountant", "accounting", "audit", "tax", "fp&a", "treasury", "controller",
                "accounts payable", "accounts receivable", "credit analyst", "risk analyst"],
    "hr": ["recruiter", "talent acquisition", "hr ", "human resources", "people partner", "hrbp", "people operations"],
    "operations": ["operations", "program manager", "project manager", "supply chain", "logistics", "procurement", "business operations"],
    "consulting": ["consultant", "solutions architect", "solution architect", "solutions engineer", "implementation", "technical consultant"],
}

_LEVELS = [
    (0, r"\bintern(ship)?\b|\btrainee\b|\bapprentice\b"),
    (5, r"\bdirector\b|\bhead of\b|\bvp\b|\bvice president\b|\bchief\b"),
    (4, r"\bprincipal\b|\bstaff\b|\blead\b|\barchitect\b|\bengineering manager\b|\bmanager,|\bsr\.? manager\b|\bavp\b|assistant vice president"),
    (3, r"\bsenior\b|\bsr\.?\b|\biii\b|\b3\b"),
    (1, r"\bjunior\b|\bjr\.?\b|\bassociate\b|\bgraduate\b|\bfresher\b|\bentry\b|\bi\b|\b1\b"),
]


def title_level(title: str) -> int:
    t = (title or "").lower()
    for level, pat in _LEVELS:
        if re.search(pat, t):
            return level
    return 2


def candidate_level(years: float) -> float:
    if years < 0.5:
        return 0.5
    if years < 2:
        return 1.2
    if years < 4:
        return 2.0
    if years < 7:
        return 3.0
    if years < 11:
        return 3.8
    return 4.5


def _families_for(role: str) -> List[str]:
    r = (role or "").lower()
    return [fam for fam, phrases in ROLE_FAMILIES.items() if any(p.strip() in r for p in phrases)]


_expansion_lock = threading.Lock()
_expansion_cache: Dict[str, Dict[str, List[str]]] = {}


def expand_roles(roles: List[str]) -> Dict[str, List[str]]:
    key = "|".join(sorted(r.lower() for r in roles))
    with _expansion_lock:
        if key in _expansion_cache:
            return _expansion_cache[key]
    phrases = {r.lower() for r in roles}
    for r in roles:
        for fam in _families_for(r):
            phrases.update(p.strip() for p in ROLE_FAMILIES[fam])
    excludes: List[str] = []
    data = llm_json(
        "You help job seekers in India find openings. Given target job roles, list the job-title phrases that recruiters "
        "in India use for the SAME job family (synonyms, common variants, abbreviations), and phrases that look similar "
        "but belong to a DIFFERENT job family and should be excluded. Phrases must be lowercase, 1-4 words, and match "
        'inside real job titles. Return JSON: {"include": ["..."], "exclude": ["..."]} with at most 30 include and 15 exclude.',
        "Target roles: " + "; ".join(roles), max_tokens=700)
    if data:
        phrases.update(p.lower().strip() for p in data.get("include", []) if isinstance(p, str) and 2 <= len(p) <= 40)
        excludes = [p.lower().strip() for p in data.get("exclude", []) if isinstance(p, str) and 2 <= len(p) <= 40]
    result = {"include": sorted(phrases), "exclude": [e for e in excludes if e not in phrases]}
    with _expansion_lock:
        _expansion_cache[key] = result
    return result


def _phrase_in(phrase: str, text: str) -> bool:
    return bool(re.search(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])", text))


def title_match(title: str, roles: List[str], expansion: Dict[str, List[str]]) -> float:
    t = (title or "").lower()
    if any(_phrase_in(e, t) for e in expansion["exclude"]):
        return 0.0
    if any(_phrase_in(r.lower(), t) for r in roles):
        return 1.0
    if any(_phrase_in(p, t) for p in expansion["include"]):
        return 0.8
    # Last resort: most of a role's distinctive words appear in the title.
    # Generic words ("manager", "analyst") never count on their own, or
    # "Associate Product Manager" would match "Relationship Manager".
    best = 0.0
    for r in roles:
        toks = [w for w in re.findall(r"[a-z0-9+#/]+", r.lower()) if w not in _SENIORITY_WORDS]
        distinctive = [w for w in toks if w not in _GENERIC_TITLE_WORDS]
        if not distinctive:
            continue
        hits = sum(1 for w in distinctive if _phrase_in(w, t))
        if hits and sum(1 for w in toks if _phrase_in(w, t)) / len(toks) >= 0.6:
            best = max(best, hits / len(distinctive))
    return 0.45 if best >= 0.5 else 0.0


_SENIORITY_WORDS = {"senior", "sr", "junior", "jr", "associate", "lead", "i", "ii", "iii", "intern", "trainee", "-", "&", "/"}
_GENERIC_TITLE_WORDS = {"manager", "analyst", "engineer", "developer", "specialist", "executive", "associate", "consultant",
                        "officer", "lead", "head", "intern", "of", "and", "the", "for", "ai"}


def score_job(job: Dict[str, Any], roles: List[str], expansion, cand_skills: Dict[str, int], cand_years: float,
              student: bool = False) -> Dict[str, Any]:
    """Fit = title family match + skill overlap with the JD + seniority fit.
    Without a description the skill overlap is unknown, so it's scored
    conservatively instead of letting un-read postings outrank read ones."""
    tscore = title_match(job["title"], roles, expansion)
    desc = job.get("description") or ""
    job_skills = [s for s in find_skills(desc) if skill_category(s) != SOFT_CATEGORY] if desc else []
    cand_set = set(cand_skills)
    matched = [s for s in job_skills if s in cand_set]
    missing = [s for s in job_skills if s not in cand_set]
    if job_skills:
        skill_score = min(1.0, len(matched) / min(len(job_skills), 10))
    else:
        skill_score = 0.3

    cand_level = candidate_level(cand_years)
    level = title_level(job["title"])
    seniority = max(0.0, 1.0 - max(0.0, abs(level - cand_level) - 0.8) * 0.45)
    seniority_note = None
    if level - cand_level > 1.3:
        seniority_note = "Asks for more seniority than your experience shows"
    elif cand_level - level > 1.8:
        seniority_note = "More junior than your experience"
    min_years = years_required(desc, job["title"]) if desc else years_required("", job["title"])
    if min_years is not None:
        gap = min_years - cand_years
        if gap > 0.5:
            seniority = min(seniority, max(0.0, 1.0 - 0.3 * gap))
            seniority_note = f"Asks for {min_years:g}+ years (you have {cand_years:g})"
        elif seniority_note and "more seniority" in seniority_note and level <= 3:
            # "Senior" titles at many Indian companies start at 3-4 years.
            seniority, seniority_note = max(seniority, 0.85), None

    # Seniority scales the fit instead of adding to it: a perfect title and
    # skill match is still a long shot when the job wants 4 more years.
    fit = (0.52 * tscore + 0.48 * skill_score) * (0.5 + 0.5 * seniority)
    if student:
        # Still studying: internships are what they can actually take now.
        if level == 0:
            fit = min(1.0, fit * 1.15 + 0.05)
        else:
            fit *= 0.72
            seniority_note = seniority_note or "Full-time role, for after you graduate"
    return {
        **job,
        "fit": int(round(min(fit, 1.0) * 100)),
        "title_match": tscore,
        "matched_skills": matched[:12],
        "missing_skills": missing[:12],
        "skills_from": "description" if desc else None,
        "min_years": min_years,
        "seniority_note": seniority_note,
    }


_BACHELOR = re.compile(r"\b(b\.?\s?tech|b\.?\s?e|bachelor'?s?|b\.?\s?sc|bca|bba|b\.?\s?com|undergrad\w*)\b", re.I)
_HIGHER = re.compile(r"\b(master'?s|m\.?\s?tech|m\.?\s?sc|ms|mba|ph\.?\s?d|doctoral|post\s?-?grad\w*)\b", re.I)


def _degree_gap(jobs: List[Dict[str, Any]], degree: Optional[str]) -> List[Dict[str, Any]]:
    """A bachelor's candidate sees postings whose title asks for a Master's or
    PhD lower down, with the reason, instead of at the top."""
    if not degree or not _BACHELOR.search(degree) or _HIGHER.search(degree):
        return jobs
    out = []
    for j in jobs:
        if _HIGHER.search(j["title"]) and not _BACHELOR.search(j["title"]):
            j = {**j, "fit": round(j["fit"] * 0.6), "seniority_note": "Title asks for a postgraduate degree; your resume shows a bachelor's"}
        out.append(j)
    return out


def _within_reach(jobs: List[Dict[str, Any]], years: float, hidden: Dict[str, int]) -> List[Dict[str, Any]]:
    cand = candidate_level(years)
    out = []
    for j in jobs:
        level = title_level(j["title"])
        need = j.get("min_years") if j.get("min_years") is not None else j.get("listed_min_years")
        if (level >= 3 and level - cand > 1.3) or (need is not None and need - years > 1.5):
            hidden["too_senior"] += 1
            continue
        out.append(j)
    return out


def _dedupe(jobs: List[Dict[str, Any]], hidden: Dict[str, int]):
    """The same opening listed twice (several cities, or a board and a job
    site): the first, best-ranked copy wins. Returns (board jobs, site jobs)."""
    seen = set()
    boards, sites = [], []
    for j in jobs:
        key = (re.sub(r"\W+", "", (j.get("company") or "").lower())[:20], re.sub(r"\W+", " ", j["title"].lower()).strip())
        if key in seen or (j["id"] in seen):
            hidden["duplicates"] += 1
            continue
        seen.update([key, j["id"]])
        (sites if j.get("source") == "network" else boards).append(j)
    return boards, sites


def discover_jobs(roles: List[str], skills: List[str], years: float = 0.0, cities: Optional[List[str]] = None,
                  max_age_days: Optional[int] = None, limit: int = 120, student: bool = False,
                  degree: Optional[str] = None) -> Dict[str, Any]:
    started = time.time()
    roles = [r.strip() for r in roles if r and r.strip()][:5]
    if not roles:
        return {"status": "error", "message": "Add at least one target role.", "jobs": []}
    # Canonical names, so "Bangalore" or "Gurgaon" match like the app's "Bengaluru" / "Delhi NCR".
    cities = list(dict.fromkeys(c if c == "Remote" else (india_cities_in(c) or [c])[0] for c in (cities or []) if c))
    cand_skills = {s: 1 for s in skills}
    years = float(years or 0.0)
    expansion = expand_roles(roles)

    registry = load_registry()
    raw: List[Dict[str, Any]] = []
    scanned, failed = 0, []

    def fetch(company):
        return company, fetch_company_jobs(company, roles)

    # Job sites (LinkedIn, Naukri, Indeed, Internshala… via JSearch) are
    # searched at the same time as the company boards.
    where = cities[0] if cities and cities[0] != "Remote" else ""
    wants_intern = student or any(re.search(r"\bintern", r, re.I) for r in roles)
    site_calls = [(jsearch, (r, where, 1, max_age_days, wants_intern and bool(re.search(r"\bintern", r, re.I)))) for r in roles[:3]]
    network_jobs: List[Dict[str, Any]] = []

    with cf.ThreadPoolExecutor(max_workers=48) as ex:
        site_futures = [ex.submit(fn, *args) for fn, args in site_calls]
        futures = [ex.submit(fetch, c) for c in registry]
        for fut in cf.as_completed(futures):
            try:
                company, jobs = fut.result()
                scanned += 1
                raw.extend(jobs)
            except Exception as e:
                failed.append(str(e)[:80])
        for fut in site_futures:
            try:
                network_jobs.extend(fut.result())
            except Exception as e:
                failed.append(str(e)[:80])

    def city_ok(job):
        if not cities:
            return True
        if "Remote" in cities and job.get("remote"):
            return True
        return any(c in job.get("cities", []) for c in cities)

    candidates = []
    for job in raw:
        if not city_ok(job):
            continue
        if max_age_days == 1:
            # "Past 24 hours", like LinkedIn: exact where the board gives a
            # timestamp; for day-granular boards only "Posted Today" counts.
            hours = posted_hours(job)
            if (hours is not None and hours > 24) or (hours is None and job.get("posted_days") != 0):
                continue
        elif max_age_days and job.get("posted_days") is not None and job["posted_days"] > max_age_days:
            continue
        if title_match(job["title"], roles, expansion) <= 0:
            continue
        candidates.append(job)

    ranked = [score_job(j, roles, expansion, cand_skills, years, student) for j in candidates]
    ranked.sort(key=lambda j: (j["title_match"], j["fit"]), reverse=True)

    # Read the full description for the strongest title matches so their
    # skill overlap and stated experience requirement are actually measured.
    to_enrich = [j for j in ranked[:90] if not j.get("description")]

    def enrich(job):
        d = fetch_job_description(job["id"])
        return job["id"], d.get("description") or ""

    with cf.ThreadPoolExecutor(max_workers=32) as ex:
        descs = dict(ex.map(enrich, to_enrich))
    refreshed = []
    for j in ranked:
        if descs.get(j["id"]):
            j = score_job({**j, "description": descs[j["id"]]}, roles, expansion, cand_skills, years, student)
        refreshed.append(j)
    ranked = sorted(refreshed, key=lambda j: j["fit"], reverse=True)

    network_ranked = [score_job(j, roles, expansion, cand_skills, years, student) for j in network_jobs
                      if city_ok(j) and title_match(j["title"], roles, expansion) > 0]
    network_ranked.sort(key=lambda j: j["fit"], reverse=True)

    # Only roles this person can get now: nothing that asks for clearly more
    # seniority or years than the resume shows.
    hidden = {"too_senior": 0, "duplicates": 0}
    ranked, network_ranked = _within_reach(ranked, years, hidden), _within_reach(network_ranked, years, hidden)
    ranked, network_ranked = _degree_gap(ranked, degree), _degree_gap(network_ranked, degree)
    ranked, network_ranked = _dedupe(ranked + network_ranked, hidden)

    jobs_out = []
    for j in sorted(ranked[:limit] + network_ranked[:60], key=lambda j: j["fit"], reverse=True):
        out = {k: v for k, v in j.items() if k != "description"}
        out["has_description"] = bool(j.get("description")) or not j["id"].startswith("jsearch:")
        h = posted_hours(j)
        out["posted_hours"] = round(h, 1) if h is not None else None
        jobs_out.append(out)

    by_ats: Dict[str, int] = {}
    companies = set()
    for j in ranked:
        by_ats[j["ats_name"]] = by_ats.get(j["ats_name"], 0) + 1
        companies.add(j["company"])

    return {
        "status": "success" if jobs_out else "empty",
        "jobs": jobs_out,
        "total_matches": len(ranked) + len(network_ranked),
        "stats": {
            "companies_scanned": scanned,
            "companies_failed": len(failed),
            "postings_scanned": len(raw),
            "companies_hiring": len(companies),
            "by_ats": by_ats,
            "network_results": len(network_ranked),
            "hidden_too_senior": hidden["too_senior"],
            "hidden_duplicates": hidden["duplicates"],
            "sources": network_status(),
            "elapsed_seconds": round(time.time() - started, 1),
        },
        "title_phrases": expansion["include"][:40],
        "search_links": search_links(roles[0], cities[0] if cities and cities[0] != "Remote" else ""),
        "message": None if jobs_out else "No openings in the scanned company network match these roles and cities right now. Try more cities, a broader role, or the job-site links.",
    }


def warm_cache() -> None:
    """Prefetch list-style boards in the background so the first search is fast."""
    def run():
        registry = [c for c in load_registry() if c["ats"] in ("greenhouse", "lever", "ashby")]
        with cf.ThreadPoolExecutor(max_workers=16) as ex:
            list(ex.map(lambda c: _safe_fetch(c), registry))
    threading.Thread(target=run, daemon=True).start()


def _safe_fetch(company):
    try:
        fetch_company_jobs(company, [])
    except Exception:
        pass
