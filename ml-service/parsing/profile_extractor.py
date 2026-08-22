import os
import json
import re
import datetime
from typing import Dict, Any, Optional, List, Tuple
from groq import Groq
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Small numeric helpers
# ---------------------------------------------------------------------------

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
        if isinstance(val, int):
            return val
        if isinstance(val, float):
            return int(val)
        match = re.search(r"\b(\d{4})\b", str(val)) or re.search(r"(\d+)", str(val))
        return int(match.group(1)) if match else default
    except Exception:
        return default

# ---------------------------------------------------------------------------
# Optional Supabase Client initialization
# ---------------------------------------------------------------------------

supabase_client = None
try:
    from supabase import create_client
    supabase_url = os.environ.get("SUPABASE_URL", "").strip()
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip() or os.environ.get("SUPABASE_ANON_KEY", "").strip()
    if supabase_url and supabase_key:
        supabase_client = create_client(supabase_url, supabase_key)
except Exception as e:
    print("Supabase client init notice:", e)


# ===========================================================================
# DATE-RANGE BASED EXPERIENCE CALCULATION
# The single biggest cause of "experience not accounted for": resumes almost
# never say "3 years of experience" in plain text. They list role date ranges
# ("Jun 2023 - Aug 2023", "Jan 2024 - Present") and expect the reader to sum
# them. Both the LLM prompt AND the offline heuristic now do that explicitly.
# ===========================================================================

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12
}

_DATE_RANGE_PATTERN = re.compile(
    r"""
    (?P<start_month>[A-Za-z]{3,9})?\s*['’]?\s*(?P<start_year>\d{2,4})
    \s*(?:-|–|—|to)\s*
    (?P<end_token>Present|Current|Now|(?:[A-Za-z]{3,9})?\s*['’]?\s*\d{2,4})
    """,
    re.IGNORECASE | re.VERBOSE
)

def _normalize_year(y: str) -> Optional[int]:
    y = y.strip()
    if len(y) == 2:
        yi = int(y)
        return 2000 + yi if yi < 50 else 1900 + yi
    if len(y) == 4:
        return int(y)
    return None

def _month_lookup(name: Optional[str]) -> int:
    if not name:
        return 6  # assume mid-year if only a year is given, keeps duration estimates unbiased
    return _MONTHS.get(name.strip(".").lower(), 6)

def compute_experience_years_from_text(text: str, now: Optional[datetime.date] = None) -> Tuple[float, int]:
    """
    Scans the whole resume for date ranges (role/internship durations) and sums
    them into a total years-of-experience figure. Overlapping ranges are merged
    so a candidate with 3 concurrent part-time roles doesn't get 3x credit.
    Returns (years_experience, ranges_found_count).
    """
    now = now or datetime.date.today()
    intervals: List[Tuple[int, int]] = []  # (start_month_index, end_month_index) since year 0

    for m in _DATE_RANGE_PATTERN.finditer(text):
        start_year = _normalize_year(m.group("start_year") or "")
        if not start_year or start_year < 1990 or start_year > now.year + 1:
            continue
        start_month = _month_lookup(m.group("start_month"))

        end_token = (m.group("end_token") or "").strip()
        if re.match(r"present|current|now", end_token, re.IGNORECASE):
            end_year, end_month = now.year, now.month
        else:
            end_match = re.match(r"([A-Za-z]{3,9})?\s*['’]?\s*(\d{2,4})", end_token)
            if not end_match:
                continue
            end_year = _normalize_year(end_match.group(2) or "")
            if not end_year:
                continue
            end_month = _month_lookup(end_match.group(1))

        start_idx = start_year * 12 + start_month
        end_idx = end_year * 12 + end_month
        if end_idx < start_idx:
            continue
        # Discard implausibly long single spans (likely a false-positive match,
        # e.g. two unrelated years on the same line) rather than let one bad
        # regex hit dominate the total.
        if end_idx - start_idx > 120:
            continue
        intervals.append((start_idx, end_idx))

    if not intervals:
        return 0.0, 0

    # Merge overlapping/adjacent intervals before summing
    intervals.sort()
    merged = [intervals[0]]
    for start, end in intervals[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end + 1:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))

    total_months = sum(end - start for start, end in merged)
    years = round(total_months / 12.0, 1)
    return years, len(intervals)


# ===========================================================================
# MAIN EXTRACTION ENTRYPOINT
# ===========================================================================

def extract_candidate_profile(raw_text: str, filename: str = "resume.pdf", api_key_override: Optional[str] = None) -> Dict[str, Any]:
    """
    Extracts structured candidate profile from raw resume text using Groq/Gemini,
    falling back to a rule-based extractor only if both LLM paths are unavailable
    or fail. At every stage, fields that cannot be genuinely determined from the
    resume text are left as None/unknown rather than filled with plausible-looking
    fabricated values -- so the caller (and the UI) can tell the difference between
    "the candidate doesn't have this" and "we failed to extract this."
    """
    clean_text = raw_text.strip()
    if not clean_text:
        return {
            "error": "Empty resume text provided",
            "explicit_fields": {},
            "inferred_fields": {},
            "consolidated_profile": {},
            "extraction_warnings": ["No resume text was provided."]
        }

    override = (api_key_override or "").strip()
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()

    if override:
        if override.startswith("AIza"):
            gemini_key = override
        elif override.startswith("gsk_") or not groq_key:
            groq_key = override

    today_str = datetime.date.today().strftime("%B %Y")

    system_prompt = (
        "You are an expert HR-tech Applicant Tracking System auditor and candidate profiler. "
        "Analyze the ACTUAL resume text below and extract structured profile data. "
        "Today's date is " + today_str + " -- use this to resolve 'Present'/'Current' end dates.\n\n"
        "CRITICAL REQUIREMENTS:\n"
        "1. You MUST strictly distinguish EXPLICIT facts present in the text from INFERRED estimations.\n"
        "2. For 'years_experience': find EVERY role/internship/work entry with a date range "
        "(e.g. 'Jun 2023 - Aug 2023', 'Jan 2024 - Present', '06/2022 - 08/2022'). Compute the duration "
        "of each in months, merge overlapping ranges, sum the total, and convert to years "
        "(one decimal place). If there are zero date ranges anywhere in the resume, return 0.0 -- "
        "do NOT guess a plausible-sounding number.\n"
        "3. For 'primary_role': prefer an explicitly stated headline/objective/target-role line if the "
        "resume has one. Otherwise infer the role from the actual skills, project titles, and experience "
        "entries present in THIS resume -- do not default to a generic title unrelated to the content.\n"
        "4. For every other field: if the information is not present anywhere in the text, return null "
        "(or an empty list for skill_list) rather than inventing a value.\n\n"
        "Return ONLY a valid JSON object matching this schema:\n"
        "{\n"
        '  "explicit_fields": {\n'
        '    "full_name": "exact candidate name if present, else null",\n'
        '    "years_experience": float (see rule 2 above, 0.0 if no date ranges found),\n'
        '    "experience_source": "date_ranges" | "explicit_statement" | "none_found",\n'
        '    "skill_list": ["explicitly mentioned skills, technologies, and tools -- as many as are present"],\n'
        '    "college_name": "exact university/college name if present, else null",\n'
        '    "college_tier": "Tier 1" (ONLY if explicitly IIT, NIT, BITS, Stanford, MIT, CMU, Harvard, UC Berkeley, Ivy League) else "Tier 2/3" if any college is named, else null,\n'
        '    "gpa": float or null if not stated,\n'
        '    "graduation_year": integer (actual or expected), or null if not stated,\n'
        '    "employment_gap_months": integer (explicit gaps you can identify between the END of one role and the START of the next), 0 if none identifiable,\n'
        '    "has_internship": true only if an internship/apprenticeship is explicitly listed, else false,\n'
        '    "project_count": integer count of distinct projects actually listed in the resume,\n'
        '    "has_referral": false,\n'
        '    "location": "city/country if stated, else null"\n'
        "  },\n"
        '  "inferred_fields": {\n'
        '    "primary_role": "role inferred from THIS resume\'s actual content (see rule 3)",\n'
        '    "seniority_level": "Entry Level" | "Mid Level" | "Senior",\n'
        '    "top_domain": "best-fit domain based on the resume\'s actual skills/projects (e.g. Software Engineering, Data Science / ML, Cloud/DevOps, Product, Other)",\n'
        '    "suggested_alternative_roles": ["2-4 roles genuinely consistent with this candidate\'s actual skills and projects"]\n'
        "  }\n"
        "}\n"
        "Do NOT hallucinate or fabricate facts. Every explicit_fields value must be traceable to text "
        "actually present in the resume below."
    )

    explicit, inferred = None, None
    extraction_warnings: List[str] = []

    # --- Priority 1: Groq API (user key preferred) ---
    if groq_key:
        try:
            client = Groq(api_key=groq_key)
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"RAW CANDIDATE RESUME TEXT:\n{clean_text[:6000]}"}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            res_content = response.choices[0].message.content
            extracted_json = json.loads((res_content or "").strip())
            explicit = extracted_json.get("explicit_fields", {})
            inferred = extracted_json.get("inferred_fields", {})
        except Exception as e:
            print("Groq candidate profile extraction failed:", e)
            extraction_warnings.append("Groq extraction failed; tried next available method.")

    # --- Priority 2: Gemini API ---
    if not explicit and gemini_key:
        try:
            genai.configure(api_key=gemini_key)  # type: ignore
            model = genai.GenerativeModel("gemini-1.5-flash")  # type: ignore
            response = model.generate_content(
                f"{system_prompt}\n\nRAW CANDIDATE RESUME TEXT:\n{clean_text[:6000]}"
            )
            raw_res = (response.text or "").strip()
            json_match = re.search(r"\{.*\}", raw_res, re.DOTALL)
            if json_match:
                extracted_json = json.loads(json_match.group(0))
                explicit = extracted_json.get("explicit_fields", {})
                inferred = extracted_json.get("inferred_fields", {})
        except Exception as e:
            print("Gemini candidate profile extraction failed:", e)
            extraction_warnings.append("Gemini extraction failed; falling back to rule-based extraction.")

    # --- Priority 3: Rule-based extraction (reads the actual resume text; no fixed presets) ---
    used_heuristic = False
    if not explicit:
        explicit, inferred = _heuristic_extraction(clean_text)
        used_heuristic = True
        extraction_warnings.append(
            "No LLM API key was available/working, so fields were extracted with rule-based text "
            "scanning. Accuracy is lower than LLM extraction, especially for role inference."
        )

    explicit = explicit or {}
    inferred = inferred or {}

    # Cross-check: if the LLM (or heuristic) reported 0 date-range-derived experience
    # but never actually looked, or reported an experience_source we can double check,
    # run our own independent date-range scan and prefer it when it found more signal.
    computed_years, ranges_found = compute_experience_years_from_text(clean_text)
    llm_years = safe_float(explicit.get("years_experience"))
    if llm_years is None or (ranges_found > 0 and (llm_years == 0.0 or llm_years is None)):
        if ranges_found > 0:
            explicit["years_experience"] = computed_years
            explicit.setdefault("experience_source", "date_ranges")

    # Track which consolidated fields could not be genuinely determined, so the
    # frontend can show "not extracted" instead of a silently-wrong number.
    unresolved_fields: List[str] = []

    def resolve(key: str, transform=lambda v: v, min_confidence_default=None):
        raw_val = explicit.get(key)
        if raw_val is None or raw_val == "":
            unresolved_fields.append(key)
            return min_confidence_default
        try:
            return transform(raw_val)
        except Exception:
            unresolved_fields.append(key)
            return min_confidence_default

    consolidated = {
        "full_name": resolve("full_name", str, None),
        "primary_role": inferred.get("primary_role") or None,
        "years_experience": safe_float(explicit.get("years_experience"), None),
        "experience_source": explicit.get("experience_source", "none_found"),
        "skill_count": len(explicit.get("skill_list") or []) if isinstance(explicit.get("skill_list"), list) else 0,
        "skill_list": explicit.get("skill_list") if isinstance(explicit.get("skill_list"), list) else [],
        "college_name": resolve("college_name", str, None),
        "college_tier": explicit.get("college_tier") or None,
        "employment_gap_months": safe_int(explicit.get("employment_gap_months"), 0),
        "has_internship": bool(explicit.get("has_internship")) if explicit.get("has_internship") is not None else False,
        "gpa": safe_float(explicit.get("gpa"), None),
        "project_count": safe_int(explicit.get("project_count"), 0),
        "graduation_year": safe_int(explicit.get("graduation_year"), None),
        "has_referral": bool(explicit.get("has_referral") or False),
        "demographic_proxy": "Group B",
        "location": resolve("location", str, None),
    }

    if not consolidated["primary_role"]:
        unresolved_fields.append("primary_role")
    if consolidated["years_experience"] is None:
        consolidated["years_experience"] = 0.0
        if "years_experience" not in unresolved_fields:
            unresolved_fields.append("years_experience")
    if consolidated["gpa"] is None:
        unresolved_fields.append("gpa")

    if unresolved_fields:
        extraction_warnings.append(
            "Could not confidently extract from the resume text: " + ", ".join(sorted(set(unresolved_fields))) +
            ". These are shown as unknown rather than guessed."
        )

    result = {
        "explicit_fields": explicit,
        "inferred_fields": inferred,
        "consolidated_profile": consolidated,
        "raw_text_length": len(clean_text),
        "resume_id": None,
        "profile_id": None,
        "extraction_method": "heuristic" if used_heuristic else ("groq" if groq_key and explicit else "gemini"),
        "extraction_warnings": extraction_warnings,
        "unresolved_fields": sorted(set(unresolved_fields))
    }

    # Save to Supabase DB if client is active
    if supabase_client is not None:
        try:
            res_db = supabase_client.table("resumes").insert({
                "filename": filename,
                "file_type": filename.split(".")[-1] if "." in filename else "text",
                "raw_text": clean_text
            }).select().execute()

            db_data: Any = res_db.data
            if db_data and len(db_data) > 0:
                resume_id = db_data[0].get("id")
                result["resume_id"] = resume_id

                prof_db = supabase_client.table("candidate_profiles").insert({
                    "resume_id": resume_id,
                    "full_name": consolidated["full_name"],
                    "primary_role": consolidated["primary_role"],
                    "years_experience": consolidated["years_experience"],
                    "skill_list": consolidated["skill_list"],
                    "college_name": consolidated["college_name"],
                    "college_tier": consolidated["college_tier"],
                    "gpa": consolidated["gpa"],
                    "graduation_year": consolidated["graduation_year"],
                    "employment_gap_months": consolidated["employment_gap_months"],
                    "has_internship": consolidated["has_internship"],
                    "project_count": consolidated["project_count"],
                    "has_referral": consolidated["has_referral"],
                    "location": consolidated["location"],
                    "explicit_data": explicit,
                    "inferred_data": inferred
                }).select().execute()

                prof_data: Any = prof_db.data
                if prof_data and len(prof_data) > 0:
                    result["profile_id"] = prof_data[0].get("id")
        except Exception as err:
            print("Supabase profile save notice:", err)

    return result


# ===========================================================================
# RULE-BASED FALLBACK (only used if both Groq and Gemini are unavailable/fail)
# Reads the actual resume text for every field. Anything it can't genuinely
# find is left as None/empty rather than filled with a fixed preset value.
# ===========================================================================

_TIER1_KEYWORDS = [
    "iit", "indian institute of technology", "nit", "national institute of technology",
    "bits pilani", "birla institute", "stanford", "mit", "massachusetts institute of technology",
    "cmu", "carnegie mellon", "harvard", "uc berkeley", "berkeley", "princeton", "yale",
    "columbia university", "cornell", "caltech"
]

# Broad, domain-spanning role vocabulary -- covers SDE/AI-ML/Data as well as
# Product, since the previous list was skewed almost entirely toward PM roles
# and would silently mis-tag a CS/AI-ML resume.
_ROLE_VOCABULARY = [
    "Machine Learning Engineer", "ML Engineer", "AI Engineer", "Data Scientist",
    "Data Analyst", "Data Engineer", "AI/ML Engineer", "Deep Learning Engineer",
    "NLP Engineer", "Computer Vision Engineer", "Research Engineer",
    "Software Development Engineer", "SDE", "Software Engineer", "Backend Developer",
    "Backend Engineer", "Frontend Engineer", "Frontend Developer", "Full Stack Engineer",
    "Full Stack Developer", "DevOps Engineer", "Cloud Engineer", "Site Reliability Engineer",
    "Mobile App Developer", "Android Developer", "iOS Developer",
    "Product Manager", "Associate Product Manager", "Product Analyst", "AI Product Manager",
    "UI/UX Designer", "Product Owner", "Quality Assurance Engineer", "QA Engineer",
    "Security Engineer", "Embedded Systems Engineer"
]

_SKILLS_VOCABULARY = [
    # Languages
    "Python", "Java", "C++", "C", "JavaScript", "TypeScript", "Go", "Rust", "SQL", "R", "Scala",
    # AI/ML/Data
    "Machine Learning", "Deep Learning", "PyTorch", "TensorFlow", "Keras", "Scikit-learn",
    "NLP", "Computer Vision", "OpenCV", "Pandas", "NumPy", "LLMs", "RAG", "Prompt Engineering",
    "Hugging Face", "OpenAI API", "FAISS", "XGBoost", "Data Analysis", "ETL Automation",
    "Tableau", "Power BI", "Matplotlib", "Seaborn",
    # Web/Backend
    "React", "Next.js", "Node.js", "Express", "FastAPI", "Django", "Flask", "REST APIs",
    "GraphQL", "Spring Boot", "PostgreSQL", "MySQL", "MongoDB", "Redis",
    # Infra/DevOps
    "Docker", "Kubernetes", "AWS", "Azure", "GCP", "CI/CD", "Git", "GitHub Actions", "Linux",
    "Terraform", "Nginx",
    # CS Fundamentals
    "Data Structures", "Algorithms", "DSA", "System Design", "OOP", "Distributed Systems",
    # Product
    "Product Management", "Product Discovery", "PRDs", "MVP Scoping", "RICE Prioritization",
    "Roadmapping", "A/B Experimentation", "User Research", "KPI Design"
]

_CITY_VOCABULARY = [
    "Bengaluru", "Bangalore", "Mumbai", "Delhi", "Hyderabad", "Pune", "Chennai", "Kolkata",
    "Ahmedabad", "Noida", "Gurugram", "Gurgaon", "San Francisco", "New York", "Seattle",
    "London", "Toronto", "Remote"
]


def _heuristic_extraction(text: str) -> tuple:
    """
    Rule-based candidate profile extractor. Used only as a last resort when no
    LLM key is available or both LLM calls fail. Every field is derived from
    the actual resume text; fields with no textual evidence are returned as
    None/empty so the caller can distinguish "not found" from a real value.
    """
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    # 1. Full name from the header, excluding contact-info-looking lines
    full_name = None
    for l in lines[:4]:
        if not re.search(r"@|http|\+91|\d{7,}|linkedin|github", l, re.IGNORECASE):
            cleaned = re.sub(r"[^a-zA-Z\s]", "", l).strip()
            cleaned = re.sub(
                r"\b(" + "|".join(_CITY_VOCABULARY) + r"|India|USA)\b", "", cleaned, flags=re.IGNORECASE
            ).strip()
            if cleaned and 1 < len(cleaned.split()) <= 4:
                full_name = cleaned.title()
                break

    # 2. Explicit stated target role/objective line, if present
    primary_role = None
    obj_match = re.search(
        r"(?:career\s+objective|objective|target\s+role|applying\s+for|seeking)\s*[:\-]\s*([^\n]+)",
        text, re.IGNORECASE
    )
    if obj_match:
        obj_line = obj_match.group(1).strip()
        for r in _ROLE_VOCABULARY:
            if re.search(r"\b" + re.escape(r) + r"\b", obj_line, re.IGNORECASE):
                primary_role = r
                break

    # 3. Otherwise, count role-keyword frequency across the whole document
    detected_roles: List[str] = []
    if not primary_role:
        role_counts = {}
        for r in _ROLE_VOCABULARY:
            hits = len(re.findall(r"\b" + re.escape(r) + r"\b", text, re.IGNORECASE))
            if hits > 0:
                role_counts[r] = hits
        detected_roles = sorted(role_counts, key=lambda r: role_counts[r], reverse=True)
        primary_role = detected_roles[0] if detected_roles else None
    else:
        detected_roles = [primary_role]

    suggested_roles = [r for r in detected_roles if r != primary_role][:4]

    # 4. Skills actually present in the text (broad, domain-spanning vocabulary)
    extracted_skills = []
    for s in _SKILLS_VOCABULARY:
        if re.search(r"(?<![A-Za-z0-9])" + re.escape(s) + r"(?![A-Za-z0-9])", text, re.IGNORECASE):
            extracted_skills.append(s)

    # 5. Location -- only if a known city actually appears in the text
    loc_match = re.search(r"\b(" + "|".join(_CITY_VOCABULARY) + r")\b", text, re.IGNORECASE)
    location = loc_match.group(1).title() if loc_match else None

    # 6. College name -- search line-by-line for a real institution keyword,
    #    rather than defaulting to any fixed institution name. Matching per-line
    #    (not across the whole text) avoids greedily spanning unrelated
    #    newline-separated content that happens to precede the keyword.
    college_name = None
    for l in lines:
        inst_match = re.search(
            r"([A-Z][A-Za-z&,.\-\s]{2,80}?(?:Institute of Technology|University|College|Polytechnic))",
            l
        )
        if inst_match:
            college_name = inst_match.group(1).strip(" ,.-")
            break
    college_tier = None
    if college_name:
        college_tier = "Tier 1" if any(k in college_name.lower() for k in _TIER1_KEYWORDS) else "Tier 2/3"
    elif any(k in text.lower() for k in _TIER1_KEYWORDS):
        college_tier = "Tier 1"

    # 7. GPA -- only if explicitly stated
    gpa_match = re.search(r"\b(?:gpa|cgpa)\s*[:\-]?\s*([0-9]\.[0-9]{1,2})\s*(?:/\s*(?:4|10))?\b", text, re.IGNORECASE)
    gpa_val = safe_float(gpa_match.group(1)) if gpa_match else None

    # 8. Graduation year -- explicit "Expected 20XX" / plain 4-digit year near "graduat"
    grad_match = (
        re.search(r"(?:expected|graduat\w*)\D{0,15}(20[1-3]\d)", text, re.IGNORECASE) or
        re.search(r"\b(201[5-9]|202[0-9]|203[0-5])\b", text)
    )
    grad_year = int(grad_match.group(1)) if grad_match else None

    # 9. Experience: prefer explicit "X years" phrasing; otherwise sum real date ranges
    exp_match = re.search(r"(\d+(\.\d+)?)\s*\+?\s*years?\s+(?:of\s+)?experience", text, re.IGNORECASE)
    if exp_match:
        years_exp = float(exp_match.group(1))
        experience_source = "explicit_statement"
    else:
        years_exp, ranges_found = compute_experience_years_from_text(text)
        experience_source = "date_ranges" if ranges_found > 0 else "none_found"

    # 10. Internship -- only if the word actually appears
    has_internship = bool(re.search(r"\bintern(ship)?\b", text, re.IGNORECASE))

    # 11. Project count -- count "Projects" section entries by looking for a
    #     Projects heading and counting subsequent bullet/heading lines until
    #     the next all-caps section header.
    project_count = 0
    proj_section = re.search(r"(?im)^\s*projects?\s*$", text)
    if proj_section:
        after = text[proj_section.end():]
        next_section = re.search(
            r"(?im)^\s*(experience|education|skills|certifications|achievements|extracurricular)\s*$", after
        )
        section_text = after[:next_section.start()] if next_section else after[:1500]
        project_count = len(re.findall(r"(?m)^\s*[•\-\*]\s+\S", section_text)) or len(
            re.findall(r"(?m)^[A-Z][A-Za-z0-9 &\-]{3,60}$", section_text)
        )

    explicit = {
        "full_name": full_name,
        "years_experience": years_exp,
        "experience_source": experience_source,
        "skill_list": extracted_skills,
        "college_name": college_name,
        "college_tier": college_tier,
        "gpa": gpa_val,
        "graduation_year": grad_year,
        "employment_gap_months": 0,
        "has_internship": has_internship,
        "project_count": project_count,
        "has_referral": False,
        "location": location
    }
    inferred = {
        "primary_role": primary_role,
        "seniority_level": "Entry Level" if years_exp < 2 else ("Mid Level" if years_exp < 5 else "Senior"),
        "top_domain": (
            "Data Science / ML" if primary_role and re.search(r"machine learning|ai|data|nlp|vision", primary_role, re.IGNORECASE)
            else "Product Management" if primary_role and "product" in primary_role.lower()
            else "Software Engineering" if primary_role
            else None
        ),
        "suggested_alternative_roles": suggested_roles
    }
    return explicit, inferred
