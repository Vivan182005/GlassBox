"""
1-5 job rating: "is this application worth sending?"

Borrowed from career-ops' evaluation (five dimensions, apply only at 4.0+),
but every dimension here comes from something GlassBox measured rather than
an open-ended LLM judgment:
  * CV match    - the ATS pass check for this exact JD and ATS
  * Role fit    - how closely the job title matches the roles the user targets
  * Level fit   - years asked for vs years the resume shows
  * Location    - the user's chosen cities / remote
  * Red flags   - stale postings, missing degree, hard screening requirements
"""
import re
from typing import Any, Dict, List, Optional

from jobs.discovery import candidate_level, title_level

APPLY_THRESHOLD = 4.0


def _band(score: float) -> Dict[str, str]:
    if score >= 4.5:
        return {"label": "Strong match", "advice": "Apply now. This is the kind of role your resume is built for."}
    if score >= APPLY_THRESHOLD:
        return {"label": "Good match", "advice": "Worth applying once the resume is tailored."}
    if score >= 3.5:
        return {"label": "Stretch", "advice": "Skip unless you have a specific reason, such as a referral."}
    return {"label": "Weak match", "advice": "Not worth the application. Your time is better spent on 4.0+ roles."}


def _role_fit(title_match: Optional[float]) -> float:
    if title_match is None:
        return 3.0
    if title_match >= 1.0:
        return 5.0
    if title_match >= 0.8:
        return 4.5
    if title_match >= 0.45:
        return 3.0
    return 1.5


def _location_fit(job: Dict[str, Any], cities: List[str]) -> float:
    if not cities:
        return 4.0
    if "Remote" in cities and job.get("remote"):
        return 5.0
    if any(c in (job.get("cities") or []) for c in cities):
        return 5.0
    return 2.5


def rate(job: Dict[str, Any], check: Dict[str, Any], cities: Optional[List[str]] = None,
         profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cities = cities or []
    # CV match is about what the candidate has, not how the file is
    # formatted: parsing and title wording are fixed by tailoring, so only
    # keyword coverage (skills genuinely on the resume) counts here.
    cov = check["coverage"]
    must_ratio = cov["must_matched"] / cov["must_total"] if cov["must_total"] else 0.6
    nice_ratio = cov["nice_matched"] / cov["nice_total"] if cov["nice_total"] else 0.6
    have = 0.75 * must_ratio + 0.25 * nice_ratio
    cv = max(1.0, min(5.0, 1 + 4 * min(1.0, have / 0.85)))  # 85% coverage is a full match
    role = _role_fit(job.get("title_match"))

    knock = {k["type"]: k for k in check.get("knockouts", [])}
    exp = knock.get("experience")
    level = 5.0 if not exp else (3.5 if exp["severity"] == "medium" else 1.5)
    level_note = exp["detail"] if exp else "Experience requirement met or not stated"
    # The title's level matters even when the JD states no years.
    profile = profile or {}
    t_level = title_level(job.get("title", ""))
    c_level = candidate_level(float(profile.get("screening_years") or profile.get("years_experience") or 0))
    if t_level - c_level > 1.3:
        level = min(level, 2.0 if t_level >= 3 else 3.0)
        level_note = f"The title reads as more senior than {profile.get('seniority') or 'your level'}"
    student_full_time = bool(profile.get("student")) and t_level > 0
    if student_full_time:
        level_note = "Full-time role; you're still studying, so this is for after you graduate"
    loc = _location_fit(job, cities)

    flags: List[Dict[str, Any]] = []
    if exp and exp["severity"] == "high":
        flags.append({"text": exp["detail"], "penalty": 0.0})  # already priced into level fit and the cap below
    if "degree" in knock:
        flags.append({"text": knock["degree"]["detail"], "penalty": 0.3})
    age = job.get("posted_days")
    if age is not None and age > 45:
        flags.append({"text": f"Posted {age} days ago, so it may already be filled.", "penalty": 0.4})
    for k in check.get("knockouts", []):
        if k["type"] == "screening_question" and re.search(r"citizen|clearance|visa|sponsor|relocat|night shift|notice", k["detail"], re.I):
            flags.append({"text": f"Screening requirement: {k['detail']}", "penalty": 0.0})
    if must_ratio < 0.5:
        flags.append({"text": f"Your resume covers few of this job's required skills ({check['coverage']['must_matched']}/{check['coverage']['must_total']}).", "penalty": 0.0})

    score = 0.45 * cv + 0.25 * role + 0.20 * level + 0.10 * loc - sum(f["penalty"] for f in flags)
    # Hard caps: a strong keyword match can't hide a deal-breaker.
    caps = []
    if exp and exp["severity"] == "high":
        caps.append(3.4)
    if must_ratio < 0.5:
        caps.append(3.4)
    if role <= 1.5:
        caps.append(3.0)
    if student_full_time:
        caps.append(3.9)
    if caps:
        score = min(score, min(caps))
    score = round(max(1.0, min(5.0, score)), 1)
    return {
        "score": score,
        "apply": score >= APPLY_THRESHOLD,
        **_band(score),
        "dimensions": [
            {"key": "cv_match", "label": "CV match", "score": round(cv, 1),
             "detail": f"{check['coverage']['must_matched']}/{check['coverage']['must_total']} required skills on your resume"},
            {"key": "role_fit", "label": "Role fit", "score": role, "detail": "Job title vs the roles you chose"},
            {"key": "level_fit", "label": "Level fit", "score": level, "detail": level_note},
            {"key": "location", "label": "Location", "score": loc, "detail": ", ".join(job.get("cities") or []) or job.get("location") or "Not stated"},
        ],
        "red_flags": [f["text"] for f in flags],
    }
