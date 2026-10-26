"""
Answers every question on an application form, with a source for each one:

  from_resume - read straight from the resume (name, email, college...)
  saved       - the user answered this before (notice period, CTC...)
  drafted     - written by the AI from resume facts; the user must read it
  needs_you   - can't be known from the resume; the user must answer
  sensitive   - demographic/legal questions; only ever the user's own answer
  file        - the tailored resume is attached here

Nothing is invented: when the resume doesn't say, the answer is left empty
and the question is put to the user.
"""
import re
from typing import Any, Dict, List, Optional

from core.llm import llm_json

# label pattern -> slot. Slots are the stable keys user answers are saved under.
_SLOTS = [
    ("first_name", r"^first name|given name"),
    ("last_name", r"^last name|surname|family name"),
    ("full_name", r"^(full )?name$|^your name"),
    ("email", r"e-?mail"),
    ("phone", r"phone|mobile|contact number"),
    ("linkedin", r"linkedin"),
    ("github", r"github"),
    ("website", r"website|portfolio|personal (site|url)|other (url|link)"),
    ("resume", r"resume|\bcv\b"),
    ("cover_letter", r"cover letter"),
    ("location", r"current (location|city)|where are you (based|located)|^location$|^city$|what is your location"),
    ("current_company", r"current (company|employer|organi[sz]ation)"),
    ("current_title", r"current (designation|title|role|position)|career stage|current status|experience level|which best describes you"),
    ("years", r"years of (work |professional |relevant )?experience|experience \(?in years|yrs\.? of exp|total experience|how many years"),
    ("college", r"college|university|school|institut"),
    ("degree", r"degree|qualification"),
    ("graduation_year", r"graduat(ion|ed)? (year|date)|year of (graduation|passing)|passing year|batch"),
    ("gpa", r"\bgpa\b|cgpa|percentage|grade"),
    ("notice_period", r"notice period|how soon can you join|earliest (start|joining)|start date|when can you start|availability to join"),
    ("current_ctc", r"current (ctc|salary|compensation|package)"),
    ("expected_ctc", r"expected (ctc|salary|compensation|package)|salary expectation"),
    ("work_authorization", r"authori[sz]ed to work|work authori[sz]ation|right to work|legally (eligible|allowed)"),
    ("sponsorship", r"sponsor"),
    ("relocate", r"relocat"),
    ("office", r"work from (the )?office|on-?site|in[- ]office|hybrid|commute"),
    ("referral", r"referr|how did you (hear|find)|source"),
]


def slot_for(label: str) -> Optional[str]:
    l = (label or "").lower()
    for slot, pat in _SLOTS:
        if re.search(pat, l):
            return slot
    return None


def answer_key(field: Dict[str, Any]) -> str:
    """Key a user's answer is saved under, so it's reused on the next form."""
    return slot_for(field["label"]) or re.sub(r"[^a-z0-9]+", "_", field["label"].lower()).strip("_")[:60]


def _pick(options: List[str], *wanted: str) -> Optional[str]:
    """First option matching any wanted phrase (case-insensitive, substring)."""
    for w in wanted:
        for o in options:
            if w.lower() == o.lower():
                return o
        for o in options:
            if w and w.lower() in o.lower():
                return o
    return None


def _current_job(profile: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    for e in profile.get("experience") or []:
        if re.search(r"present|current|now|till date", str(e.get("end") or ""), re.I):
            return e
    return None


def _from_resume(field: Dict[str, Any], slot: Optional[str], profile: Dict[str, Any], contact: Dict[str, Any],
                 job: Dict[str, Any]) -> Optional[str]:
    name = (profile.get("name") or "").strip()
    parts = name.split()
    edu = profile.get("education") or {}
    opts = field.get("options") or []
    cur = _current_job(profile)
    student = bool(edu.get("graduation_year") and edu["graduation_year"] >= _this_year())
    fresher = (profile.get("full_time_years") or 0) < 1

    if slot == "first_name" and parts:
        return parts[0]
    if slot == "last_name" and len(parts) > 1:
        return parts[-1]
    if slot == "full_name" and name:
        return name
    if slot in ("email", "phone", "linkedin", "github") and contact.get(slot):
        v = contact[slot]
        return ("https://" + v) if slot in ("linkedin", "github") and not v.startswith("http") else v
    if slot == "website":
        links = [u for u in contact.get("links") or [] if not re.search(r"linkedin\.com|github\.com", u, re.I)]
        return links[0] if links else None
    if slot == "location" and profile.get("location"):
        return _pick(opts, profile["location"]) if opts else f"{profile['location']}, India"
    if slot == "current_company":
        if cur:
            return _pick(opts, cur.get("company", "")) or (cur.get("company") if not opts else None)
        if opts:
            return _pick(opts, "not applicable", "none", "fresher", "student")
        return "Not currently employed" if not student else f"Student, {edu.get('college') or 'university'}"
    if slot == "current_title":
        if opts:
            if student:
                return _pick(opts, "student", "intern", "fresher")
            if fresher:
                return _pick(opts, "fresher", "college grad", "entry", "graduate")
            return _pick(opts, "experienced", "professional")
        return (cur or {}).get("title") or ("Student" if student else None)
    if slot == "years":
        yrs = profile.get("full_time_years")
        if yrs is None:
            yrs = profile.get("years_experience")
        if yrs is None:
            return None
        if opts:
            return _pick(opts, str(int(yrs)), "0-1" if yrs < 1 else "", "fresher" if yrs < 1 else "", "less than 1" if yrs < 1 else "")
        intern = profile.get("internship_years") or 0
        if field.get("type") == "text" and intern and yrs < 1:
            return f"{yrs:g} (plus {round(intern * 12)} months of internship)"
        return f"{yrs:g}"
    if slot == "college" and edu.get("college"):
        return _pick(opts, edu["college"]) if opts else edu["college"]
    if slot == "degree" and edu.get("degree"):
        d = edu["degree"] + (f", {edu['field']}" if edu.get("field") else "")
        return _pick(opts, edu["degree"].split()[0], "bachelor") if opts else d
    if slot == "graduation_year" and edu.get("graduation_year"):
        return _pick(opts, str(edu["graduation_year"])) if opts else str(edu["graduation_year"])
    if slot == "gpa" and edu.get("gpa"):
        return f"{edu['gpa']:g}/{(edu.get('gpa_scale') or 10):g}"
    return None


def _this_year() -> int:
    import datetime
    return datetime.date.today().year


def _facts(profile: Dict[str, Any]) -> str:
    """Status facts stated plainly, so drafted answers don't guess them."""
    edu = profile.get("education") or {}
    grad = edu.get("graduation_year")
    student = bool(grad and grad >= _this_year()) if profile.get("student") is None else profile.get("student")
    cur = _current_job(profile)
    return (f"Graduation year: {grad or 'unknown'} ({'still studying' if student else 'graduated'}). "
            f"Full-time experience: {profile.get('full_time_years') or 0} years; internships: {round((profile.get('internship_years') or 0) * 12)} months. "
            f"Currently: {('working at ' + cur.get('company', '')) if cur else ('a student' if student else 'not employed')}. "
            f"Location: {profile.get('location') or 'unknown'}.")


def _draft(fields: List[Dict[str, Any]], resume_text: str, profile: Dict[str, Any], job: Dict[str, Any], jd_text: str) -> Dict[str, Any]:
    if not fields:
        return {}
    spec = [{"id": f["id"], "question": f["label"], "type": f["type"], "options": f.get("options") or None,
             "hint": f.get("description") or None} for f in fields]
    data = llm_json(
        "You fill in a job application for a candidate in India, using ONLY facts in their resume. For each question:\n"
        "- If it has options, answer with one option copied exactly (multiselect: a list of exact options).\n"
        "- Free-text questions (why this company, describe a project, cover letter, anything else to add): write a "
        "specific, first-person answer from the resume, 60-140 words, no clichés, no invented facts, numbers or employers.\n"
        "- If the resume doesn't contain the answer (salary, notice period, visa, preferences, personal facts), return null. "
        "Never guess these.\n"
        'Return ONLY JSON: {"answers": {"<id>": {"value": string|list|null, "basis": "the resume fact used, or why null"}}}',
        f"CANDIDATE FACTS (authoritative): {_facts(profile)}\n"
        f"JOB: {job.get('title')} at {job.get('company')}\nJOB DESCRIPTION (excerpt):\n{(jd_text or '')[:3500]}\n\n"
        f"RESUME:\n{resume_text[:7000]}\n\nQUESTIONS:\n{spec}",
        max_tokens=2500, timeout=60)
    return (data or {}).get("answers") or {}


def answer_form(fields: List[Dict[str, Any]], resume_text: str, profile: Dict[str, Any], contact: Dict[str, Any],
                job: Dict[str, Any], jd_text: str = "", saved: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    saved = {k: v for k, v in (saved or {}).items() if v not in (None, "", [])}
    out: List[Dict[str, Any]] = []
    to_draft: List[Dict[str, Any]] = []
    for f in fields:
        slot = slot_for(f["label"])
        key = answer_key(f)
        row = {**f, "key": key, "value": None, "status": "needs_you", "basis": None}
        if f["type"] == "file":
            is_cover = slot == "cover_letter"
            row.update(status="file", value="cover_letter" if is_cover else "tailored_resume",
                       basis="Your cover letter" if is_cover else "Your tailored resume (PDF) is attached here")
        elif key in saved:
            row.update(status="saved", value=saved[key], basis="Your saved answer")
        elif f.get("sensitive"):
            row.update(status="sensitive", basis="Only you can answer this. Choosing not to disclose is always allowed.")
        else:
            v = _from_resume(f, slot, profile, contact, job)
            if v:
                row.update(status="from_resume", value=v, basis="From your resume")
            elif slot in ("notice_period", "current_ctc", "expected_ctc", "work_authorization", "sponsorship", "relocate", "office", "referral"):
                row.update(basis="Not on your resume. Answer once and GlassBox reuses it on every form.")
            else:
                to_draft.append(f)
        out.append(row)

    drafted = _draft(to_draft, resume_text, profile, job, jd_text)
    for row in out:
        d = drafted.get(row["id"]) if row["status"] == "needs_you" else None
        if not d or d.get("value") in (None, "", []):
            if row["status"] == "needs_you" and not row["basis"]:
                row["basis"] = (d or {}).get("basis") or "Your resume doesn't say."
            continue
        v = d["value"]
        if row.get("options"):
            vals = v if isinstance(v, list) else [v]
            vals = [o for o in row["options"] if any(str(x).strip().lower() == o.lower() for x in vals)]
            if not vals:
                continue
            v = vals if row["type"] == "multiselect" else vals[0]
        row.update(status="drafted", value=v, basis=d.get("basis") or "Drafted from your resume")
    return out


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for r in rows:
        out[r["status"]] = out.get(r["status"], 0) + 1
    out["blocking"] = sum(1 for r in rows if r["required"] and r["status"] in ("needs_you", "sensitive") and not r.get("value"))
    return out
