"""
Candidate profile extraction.

An LLM reads the resume into structured fields; the skill lexicon and a
date-range scanner then cross-check it, so skills and years of experience
are traceable to the text even when the LLM is unavailable. Fields that
can't be found are returned as None, never filled with plausible defaults.
"""
import re
import datetime
from typing import Any, Dict, List, Optional, Tuple

from core.llm import llm_json
from matching.skills_lexicon import find_skills, canonicalize, skill_category


def safe_float(val: Any, default: Optional[float] = None) -> Optional[float]:
    if val is None:
        return default
    try:
        if isinstance(val, (int, float)):
            return float(val)
        match = re.search(r"(\d+(\.\d+)?)", str(val))
        return float(match.group(1)) if match else default
    except Exception:
        return default


def safe_int(val: Any, default: Optional[int] = None) -> Optional[int]:
    if val is None:
        return default
    try:
        if isinstance(val, (int, float)):
            return int(val)
        match = re.search(r"\b(\d{4})\b", str(val)) or re.search(r"(\d+)", str(val))
        return int(match.group(1)) if match else default
    except Exception:
        return default


# ---------------------------------------------------------------------------
# Date-range experience calculation. Resumes rarely state "3 years of
# experience"; they list ranges ("Jun 2023 - Present") the reader must sum.
# ---------------------------------------------------------------------------

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3, "apr": 4, "april": 4, "may": 5,
    "jun": 6, "june": 6, "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
_MONTH_NAMES = "|".join(sorted(_MONTHS, key=len, reverse=True))


def _date_pattern(prefix: str) -> str:
    return (rf"(?:\b(?P<{prefix}m>{_MONTH_NAMES})\.?,?\s*['’]?\s*|\b(?P<{prefix}n>0?[1-9]|1[0-2])\s*[/\-.]\s*)?"
            rf"(?P<{prefix}y>(?:19|20)\d{{2}}|['’]\d{{2}})")


_RANGE = re.compile(
    _date_pattern("s") + r"\s*(?:-|–|—|to|till|until)\s*"
    + r"(?:(?P<present>present|current|now|ongoing|date|today)|" + _date_pattern("e") + ")",
    re.IGNORECASE,
)


def _year(y: str) -> Optional[int]:
    y = (y or "").strip("'’ ")
    if len(y) == 2:
        return 2000 + int(y)
    return int(y) if len(y) == 4 else None


def _month(name: Optional[str], num: Optional[str], default: int) -> int:
    if name:
        return _MONTHS.get(name.lower().rstrip("."), default)
    if num:
        return int(num)
    return default


def compute_experience_years(text: str, work_text: Optional[str] = None, now: Optional[datetime.date] = None) -> Tuple[float, int]:
    """Sums date ranges (merging overlaps) found in the work/experience part of
    the resume. Education ranges are excluded when a work section can be isolated."""
    now = now or datetime.date.today()
    source = work_text if work_text else text
    intervals = []
    for m in _RANGE.finditer(source):
        sy = _year(m.group("sy"))
        if not sy or sy < 1980 or sy > now.year + 1:
            continue
        sm = _month(m.group("sm"), m.group("sn"), 1)
        if m.group("present"):
            ey, em = now.year, now.month
        else:
            ey = _year(m.group("ey"))
            if not ey:
                continue
            em = _month(m.group("em"), m.group("en"), 12 if not m.group("sm") and not m.group("sn") else 1)
        start, end = sy * 12 + sm, ey * 12 + em
        if end < start or end - start > 180:
            continue
        intervals.append((start, end))
    if not intervals:
        return 0.0, 0
    intervals.sort()
    merged = [intervals[0]]
    for s, e in intervals[1:]:
        if s <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    months = sum(e - s for s, e in merged)
    return round(months / 12.0, 1), len(intervals)


def _work_section(text: str) -> Optional[str]:
    m = re.search(r"(?im)^\s*(work experience|professional experience|experience|employment history|work history|internships?)\s*:?\s*$", text)
    if not m:
        return None
    after = text[m.end():]
    nxt = re.search(r"(?im)^\s*(education|academic\w*|projects?|skills|technical skills|certifications?|achievements|awards|"
                    r"positions of responsibility|extra[- ]?curricular\w*|publications|languages|interests)\s*:?\s*$", after)
    return after[: nxt.start()] if nxt else after


# ---------------------------------------------------------------------------
# Rule-based fallback pieces
# ---------------------------------------------------------------------------

_TIER1 = ["iit", "indian institute of technology", "nit ", "national institute of technology", "bits pilani", "birla institute",
          "iiit", "iim", "indian institute of management", "iisc", "indian institute of science", "dtu", "delhi technological",
          "nsut", "stanford", "massachusetts institute of technology", "carnegie mellon", "harvard", "berkeley", "oxford", "cambridge"]
_DEGREES = [
    ("PhD", r"\bph\.?\s?d\b|doctorate"),
    ("MBA", r"\bmba\b|\bpgdm\b|post graduate diploma in management"),
    ("M.Tech / M.E. / M.S.", r"\bm\.?\s?tech\b|\bm\.?e\.?\b(?= |,)|\bm\.?s\.?\b(?= in)|master of (?:technology|engineering|science)"),
    ("MCA", r"\bmca\b|master of computer applications"),
    ("M.Sc", r"\bm\.?sc\b"),
    ("B.Tech / B.E.", r"\bb\.?\s?tech\b|\bb\.?e\.?\b(?= |,|\()|bachelor of (?:technology|engineering)"),
    ("BCA", r"\bbca\b|bachelor of computer applications"),
    ("B.Sc", r"\bb\.?sc\b|bachelor of science"),
    ("B.Com", r"\bb\.?com\b|bachelor of commerce"),
    ("BBA", r"\bbba\b|\bbms\b|bachelor of business"),
    ("B.A.", r"\bb\.?a\.?\b(?= in| \(|,)|bachelor of arts"),
    ("Diploma", r"\bdiploma\b"),
]
_CITIES = ["Bengaluru", "Bangalore", "Mumbai", "New Delhi", "Delhi", "Hyderabad", "Pune", "Chennai", "Kolkata", "Ahmedabad", "Noida",
           "Gurugram", "Gurgaon", "Jaipur", "Kochi", "Indore", "Chandigarh", "Coimbatore", "Lucknow", "Bhopal", "Nagpur", "Mysuru",
           "Visakhapatnam", "Thiruvananthapuram", "Bhubaneswar", "Vadodara", "Surat"]


def detect_degree(text: str) -> Optional[str]:
    for label, pat in _DEGREES:
        if re.search(pat, text, re.IGNORECASE):
            return label
    return None


def _rules_profile(text: str) -> Dict[str, Any]:
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    name = None
    for l in lines[:5]:
        if re.search(r"@|http|www\.|\d{5,}|linkedin|github|resume|curriculum", l, re.IGNORECASE):
            continue
        cleaned = re.sub(r"[^A-Za-z .]", " ", l).strip()
        if 1 < len(cleaned.split()) <= 4 and len(cleaned) < 40:
            name = cleaned.title() if cleaned.isupper() else cleaned
            break
    loc = next((c for c in _CITIES if re.search(r"\b" + c + r"\b", text)), None)
    college = None
    for l in lines:
        m = re.search(r"([A-Z][A-Za-z&,.\-\s]{2,80}?(?:Institute of Technology|Institute|University|College|Vidyalaya|IIT\s?\w*|NIT\s?\w*))", l)
        if m:
            college = m.group(1).strip(" ,.-")
            break
    grad = re.search(r"(?:expected|graduat\w*|batch|class of)\D{0,15}((?:19|20)\d{2})", text, re.IGNORECASE)
    gpa = re.search(r"\b(?:c?gpa|cpi|sgpa)\s*[:\-]?\s*(\d{1,2}(?:\.\d{1,2})?)\s*(?:/\s*(10|4)(?:\.0)?)?", text, re.IGNORECASE)
    return {
        "name": name, "location": loc, "college": college,
        "graduation_year": int(grad.group(1)) if grad else None,
        "gpa": float(gpa.group(1)) if gpa else None,
        "gpa_scale": float(gpa.group(2)) if gpa and gpa.group(2) else (10.0 if gpa and float(gpa.group(1)) > 4.0 else (4.0 if gpa else None)),
    }


_ROLE_HINTS = [
    ("Machine Learning Engineer", ["Machine Learning", "Deep Learning", "PyTorch", "TensorFlow", "MLOps"]),
    ("Data Scientist", ["Machine Learning", "Statistics", "Pandas", "Scikit-learn"]),
    ("Data Analyst", ["SQL", "Excel", "Power BI", "Tableau", "Data Analysis"]),
    ("Data Engineer", ["Spark", "Airflow", "ETL", "Kafka", "Data Warehousing"]),
    ("Frontend Engineer", ["React", "JavaScript", "TypeScript", "CSS", "Next.js"]),
    ("Backend Engineer", ["Node.js", "Spring Boot", "Django", "Microservices", "REST APIs", "PostgreSQL"]),
    ("Software Engineer", ["Data Structures & Algorithms", "Java", "Python", "C++", "System Design", "Git"]),
    ("DevOps Engineer", ["Docker", "Kubernetes", "Terraform", "CI/CD", "AWS"]),
    ("Product Manager", ["Product Management", "Product Roadmap", "PRDs", "User Research", "Product Analytics"]),
    ("UI/UX Designer", ["Figma", "UX Design", "UI Design"]),
    ("QA Engineer", ["Test Automation", "Manual Testing", "API Testing"]),
    ("Security Analyst", ["Cybersecurity", "Penetration Testing", "SIEM", "Network Security"]),
    ("Digital Marketing Specialist", ["Digital Marketing", "SEO", "Content Marketing", "Marketing Analytics"]),
    ("Financial Analyst", ["Financial Modeling", "Accounting", "Excel"]),
    ("Business Analyst", ["Business Analysis", "SQL", "Excel", "Stakeholder Management"]),
]


def _guess_roles(skills: List[str]) -> List[str]:
    s = set(skills)
    scored = sorted(((sum(1 for k in kws if k in s) / len(kws), role) for role, kws in _ROLE_HINTS), reverse=True)
    return [role for score, role in scored if score >= 0.34][:4]


def _seniority(years: float) -> str:
    if years < 1:
        return "Fresher / Entry level"
    if years < 3:
        return "Junior (1–3 yrs)"
    if years < 6:
        return "Mid level (3–6 yrs)"
    if years < 10:
        return "Senior (6–10 yrs)"
    return "Lead / Principal (10+ yrs)"


SYSTEM_PROMPT = (
    "You are an expert resume parser used by an ATS-audit tool for job seekers in India. Read the resume and return ONLY JSON:\n"
    "{\n"
    '  "name": string|null,\n'
    '  "headline": "the role this person is targeting or currently doing, inferred from THIS resume",\n'
    '  "target_roles": ["3-5 realistic job titles this person should search for in India, most relevant first"],\n'
    '  "location": "city if stated, else null",\n'
    '  "education": {"degree": string|null, "field": string|null, "college": string|null, "graduation_year": int|null, "gpa": number|null, "gpa_scale": number|null},\n'
    '  "experience": [{"title": string, "company": string, "start": "Mon YYYY", "end": "Mon YYYY or Present", "is_internship": bool}],\n'
    '  "years_experience": number (sum of non-overlapping professional and internship durations, 0 if none),\n'
    '  "skills": ["every concrete skill, tool, language, framework and methodology explicitly in the resume"],\n'
    '  "domain": "e.g. Software Engineering, Data / AI, Product, Design, Finance, Marketing, Sales, Operations, HR, Core Engineering",\n'
    '  "summary": "one sentence, third person, what makes this candidate distinctive"\n'
    "}\n"
    "Never invent facts: every value must be traceable to the resume. Use null when something is absent."
)


def extract_profile(text: str, layout_audit: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    text = (text or "").strip()
    warnings: List[str] = []
    if not text:
        return {"error": "Empty resume text", "warnings": ["No text could be read from the resume."]}

    today = datetime.date.today().strftime("%B %Y")
    llm = llm_json(SYSTEM_PROMPT, f"Today is {today}.\n\nRESUME:\n{text[:12000]}", max_tokens=2500, timeout=60)
    rules = _rules_profile(text)

    lex = find_skills(text)
    skill_names = list(lex)
    if llm:
        for s in llm.get("skills") or []:
            if isinstance(s, str) and s.strip():
                c = canonicalize(s.strip())
                if c not in lex and len(c) <= 40:
                    lex[c] = 1
                    skill_names.append(c)
    skills = sorted(
        ({"name": s, "category": skill_category(s) if skill_category(s) != "Other" else "Other", "mentions": lex[s]} for s in skill_names),
        key=lambda s: (-s["mentions"], s["name"]),
    )

    work = _work_section(text)
    computed_years, ranges = compute_experience_years(text, work)
    llm_years = safe_float((llm or {}).get("years_experience"))
    if llm_years is not None and (ranges == 0 or abs(llm_years - computed_years) <= 1.5):
        years, source = llm_years, "ai_reviewed_dates"
    elif ranges:
        years, source = computed_years, "date_ranges"
    else:
        years, source = 0.0, "none_found"
        warnings.append("No employment date ranges were found, so experience is counted as 0 years.")

    edu = (llm or {}).get("education") or {}
    roles = [r for r in ((llm or {}).get("target_roles") or []) if isinstance(r, str) and r.strip()]
    headline = (llm or {}).get("headline")
    if not roles:
        roles = _guess_roles([s["name"] for s in skills])
        headline = headline or (roles[0] if roles else None)
    if headline and headline not in roles:
        roles.insert(0, headline)
    if not llm:
        warnings.append("AI extraction was unavailable, so a rule-based reader was used. Role suggestions are less precise.")

    college = edu.get("college") or rules["college"]
    college_tier = None
    if college:
        college_tier = "Tier 1" if any(k in (college.lower() + " ") for k in _TIER1) else "Tier 2/3"

    profile = {
        "name": (llm or {}).get("name") or rules["name"],
        "headline": headline,
        "target_roles": roles[:5],
        "location": (llm or {}).get("location") or rules["location"],
        "years_experience": round(years, 1),
        "experience_source": source,
        "seniority": _seniority(years),
        "experience": [e for e in ((llm or {}).get("experience") or []) if isinstance(e, dict)][:12],
        "education": {
            "degree": edu.get("degree") or detect_degree(text),
            "field": edu.get("field"),
            "college": college,
            "college_tier": college_tier,
            "graduation_year": safe_int(edu.get("graduation_year")) or rules["graduation_year"],
            "gpa": safe_float(edu.get("gpa")) or rules["gpa"],
            "gpa_scale": safe_float(edu.get("gpa_scale")) or rules["gpa_scale"],
        },
        "skills": skills,
        "domain": (llm or {}).get("domain"),
        "summary": (llm or {}).get("summary"),
        "method": "ai" if llm else "rules",
        "warnings": warnings,
    }
    profile["bias_features"] = bias_features(profile, layout_audit or {})
    return profile


def bias_features(profile: Dict[str, Any], layout_audit: Dict[str, Any]) -> Dict[str, Any]:
    """Maps the profile onto the feature vector used by the Fairness Lab's audited model."""
    edu = profile.get("education") or {}
    gpa = edu.get("gpa")
    if gpa and (edu.get("gpa_scale") or 10) > 4.5:
        gpa = round(gpa / 10 * 4, 2)
    exp = profile.get("experience") or []
    return {
        "years_experience": profile.get("years_experience") or 0.0,
        "skill_count": len([s for s in profile.get("skills", []) if s["category"] != "Soft Skills"]),
        "college_tier": edu.get("college_tier") or "Tier 2/3",
        "employment_gap_months": 0,
        "has_internship": any(e.get("is_internship") for e in exp) or bool(re.search(r"intern", " ".join(e.get("title", "") for e in exp), re.IGNORECASE)),
        "gpa": gpa if gpa else 3.0,
        "project_count": max(1, min(10, layout_audit.get("bullets", 0) // 4)) if layout_audit else 3,
        "graduation_year": edu.get("graduation_year") or datetime.date.today().year,
        "has_referral": False,
    }
