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


# "Jul–Nov 2024" shares one year across both months; spell it out so the
# range pattern sees "Jul 2024 – Nov 2024".
_SHARED_YEAR = re.compile(rf"\b({_MONTH_NAMES})\.?\s*(-|–|—|to)\s*({_MONTH_NAMES})\.?,?\s*((?:19|20)\d{{2}})", re.IGNORECASE)
_NOT_WORK = re.compile(r"\b(b\.?\s?tech|b\.?e\b|m\.?\s?tech|bachelor|master|degree|university|college|school|gpa|cgpa|"
                       r"fellowship|cohort|course|certification|bootcamp|semester|class of|batch)\b", re.IGNORECASE)


def _merge_months(intervals: List[Tuple[int, int]]) -> int:
    if not intervals:
        return 0
    intervals = sorted(intervals)
    merged = [intervals[0]]
    for s, e in intervals[1:]:
        if s <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    # An inclusive "Jul–Nov" is five months of work, not four.
    return sum(e - s + 1 for s, e in merged)


def _ranges(text: str, now: datetime.date, skip_education: bool = False) -> List[Tuple[int, int]]:
    text = _SHARED_YEAR.sub(lambda m: f"{m.group(1)} {m.group(4)} {m.group(2)} {m.group(3)} {m.group(4)}", text)
    intervals = []
    for m in _RANGE.finditer(text):
        if skip_education:
            ls, le = text.rfind("\n", 0, m.start()) + 1, text.find("\n", m.end())
            if _NOT_WORK.search(text[ls: le if le != -1 else len(text)]):
                continue
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
        start, end = sy * 12 + sm, min(ey * 12 + em, now.year * 12 + now.month)
        if end < start or end - start > 180:
            continue
        intervals.append((start, end))
    return intervals


def compute_experience_years(text: str, work_text: Optional[str] = None, now: Optional[datetime.date] = None) -> Tuple[float, int]:
    """Sums date ranges (merging overlaps) found in the work/experience part of
    the resume. Lines that read as education, fellowships or courses are skipped."""
    now = now or datetime.date.today()
    intervals = _ranges(work_text if work_text else text, now, skip_education=True)
    return round(_merge_months(intervals) / 12.0, 1), len(intervals)


def experience_from_entries(entries: List[Dict[str, Any]], now: Optional[datetime.date] = None) -> Optional[Dict[str, float]]:
    """Years from the structured job list (title, company, start, end). Returns
    None when no entry has dates the range parser can read."""
    now = now or datetime.date.today()
    full, intern, parsed = [], [], 0
    for e in entries:
        span = f"{e.get('start') or ''} - {e.get('end') or ''}"
        iv = _ranges(span, now)
        if not iv:
            continue
        parsed += 1
        is_intern = bool(e.get("is_internship")) or bool(re.search(r"\bintern|trainee|apprentice", str(e.get("title") or ""), re.IGNORECASE))
        (intern if is_intern else full).extend(iv)
    if not parsed:
        return None
    return {"full_time": round(_merge_months(full) / 12.0, 1), "internship": round(_merge_months(intern) / 12.0, 1)}


def _work_section(text: str) -> Optional[str]:
    m = re.search(r"(?im)^\s*(work experience|professional experience|experience|employment history|work history|internships?)\s*:?\s*$", text)
    if not m:
        return None
    after = text[m.end():]
    nxt = re.search(r"(?im)^\s*(education|academic\w*|projects?|skills|technical skills|certifications?|achievements|awards|"
                    r"positions of responsibility|extra[- ]?curricular\w*|publications|languages|interests|portfolio)\b[^\n]{0,40}$", after)
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


def _split_roles(items: List[Any]) -> List[str]:
    out: List[str] = []
    for item in items:
        if not isinstance(item, str):
            continue
        for part in re.split(r"\s*(?:\||,|/(?=\s)|·|•|;)\s*", item):
            part = part.strip(" -–")
            if 2 < len(part) <= 60 and part.lower() not in {o.lower() for o in out}:
                out.append(part)
    return out


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
    '  "target_roles": ["3-5 realistic job titles this person should search for in India, most relevant first; one title per item, matched to their actual seniority (a fresher gets entry-level titles)"],\n'
    '  "location": "city if stated, else null",\n'
    '  "education": {"degree": string|null, "field": string|null, "college": string|null, "graduation_year": int|null, "gpa": number|null, "gpa_scale": number|null},\n'
    '  "experience": [{"title": string, "company": string, "start": "Mon YYYY", "end": "Mon YYYY or Present", "is_internship": bool}] '
    '(jobs and internships only: never degrees, fellowships, courses, bootcamps or personal projects; "Jul–Nov 2024" means start "Jul 2024", end "Nov 2024"),\n'
    '  "years_experience": number (sum of non-overlapping professional and internship durations, 0 if none),\n'
    '  "skills": ["every concrete skill, tool, language, framework and methodology explicitly in the resume"],\n'
    '  "domain": "e.g. Software Engineering, Data / AI, Product, Design, Finance, Marketing, Sales, Operations, HR, Core Engineering",\n'
    '  "summary": "one sentence, third person, what makes this candidate distinctive"\n'
    "}\n"
    "Never invent facts: every value must be traceable to the resume. Use null when something is absent."
)


def _name_from(text: str, llm_name: Optional[str], rule_name: Optional[str]) -> Optional[str]:
    """The candidate's name exactly as the resume spells it. The model's version
    is used only when it appears in the text: it sometimes retypes a name with
    a letter changed. All-caps headers become ordinary capitalisation for forms."""
    flat = re.sub(r"\s+", " ", text or "").lower()
    found = [n.strip() for n in (rule_name, llm_name) if n and n.strip() and re.sub(r"\s+", " ", n.strip()).lower() in flat]
    name = max(found, key=len) if found else None
    name = name or rule_name or llm_name
    if name and name.isupper():
        name = " ".join(w.capitalize() for w in name.split())
    return name


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
    entries = [e for e in ((llm or {}).get("experience") or []) if isinstance(e, dict)]
    from_entries = experience_from_entries(entries)
    internship_years = 0.0
    if from_entries is not None:
        # The AI's job list is anchored to titles and companies, so it isn't
        # fooled by degree, fellowship or project dates the way a raw scan is.
        years, internship_years, source = from_entries["full_time"] + from_entries["internship"], from_entries["internship"], "job_entries"
    elif ranges:
        years, source = computed_years, "date_ranges"
    else:
        years, source = 0.0, "none_found"
        warnings.append("No employment date ranges were found, so experience is counted as 0 years.")
    full_time_years = round(max(0.0, years - internship_years), 1)

    edu = (llm or {}).get("education") or {}
    roles = _split_roles((llm or {}).get("target_roles") or [])
    headline = (llm or {}).get("headline")
    if not roles:
        roles = _guess_roles([s["name"] for s in skills])
        headline = headline or (roles[0] if roles else None)
    # A headline like "AI Product | APM | Product Analyst" is several search
    # titles, not one; each goes in as its own role.
    for r in reversed(_split_roles([headline] if headline else [])):
        if r.lower() not in {x.lower() for x in roles}:
            roles.insert(0, r)
    if not llm:
        warnings.append("AI extraction was unavailable, so a rule-based reader was used. Role suggestions are less precise.")

    college = edu.get("college") or rules["college"]
    college_tier = None
    if college:
        college_tier = "Tier 1" if any(k in (college.lower() + " ") for k in _TIER1) else "Tier 2/3"

    # Still studying: internships are the realistic search, so they lead and
    # the full-time titles follow for after graduation.
    grad = safe_int(edu.get("graduation_year")) or rules["graduation_year"]
    today = datetime.date.today()
    student = bool(grad and (grad > today.year or (grad == today.year and today.month < 6)))
    if student and roles and not any(re.search(r"\bintern", r, re.I) for r in roles):
        roles = [f"{roles[0]} Intern"] + ([f"{roles[1]} Intern"] if len(roles) > 1 else []) + roles
        roles = list(dict.fromkeys(roles))

    profile = {
        "name": _name_from(text, (llm or {}).get("name"), rules["name"]),
        "headline": headline,
        "target_roles": roles[:6],
        "student": student,
        "location": (llm or {}).get("location") or rules["location"],
        "years_experience": round(years, 1),
        "full_time_years": full_time_years,
        "internship_years": internship_years,
        # What a recruiter's "N+ years" filter effectively credits: full-time
        # work plus internships at half weight.
        "screening_years": round(full_time_years + 0.5 * internship_years, 1),
        "experience_source": source,
        "seniority": _seniority(full_time_years),
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
    return profile
