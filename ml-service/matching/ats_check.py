"""
"Will my resume get through?" for one specific job.

Combines four measurable signals:
  * keyword coverage: the JD's must-have and nice-to-have terms, matched
    alias-aware against the resume (the way recruiter boolean searches and
    ATS ranking match them);
  * parse survival: how much of the resume this company's ATS parser keeps;
  * knockouts: years of experience and degree requirements;
  * title alignment: whether the resume uses the job's title wording.
The result is a simulation estimate, not a vendor's real score.
"""
import re
from typing import Any, Dict, List, Optional

from ats.profiles import get_profile, public_profile
from core.llm import llm_json
from matching.skills_lexicon import find_skills, term_in_text, canonicalize, skill_category, implied_by, SOFT_CATEGORY
from parsing.profile_extractor import detect_degree
from parsing.resume_reader import parse_score

_REQ_HDR = r"(requirements?|qualifications?|must[- ]haves?|what you(?:'| wi)ll need|what we(?:'| a)re looking for|you have|who you are|skills required|key skills|desired skills|basic qualifications|minimum qualifications|eligibility)"
_PREF_HDR = r"(nice[- ]to[- ]haves?|preferred(?: qualifications)?|bonus(?: points)?|good[- ]to[- ]haves?|pluses|it'?s a plus|additional qualifications|preferred skills)"
_DEGREE_RANK = {"Diploma": 0, "B.A.": 1, "B.Com": 1, "BBA": 1, "B.Sc": 1, "BCA": 1, "B.Tech / B.E.": 1, "MCA": 2, "M.Sc": 2,
                "M.Tech / M.E. / M.S.": 2, "MBA": 2, "PhD": 3}


def degree_rank(text: str) -> Optional[int]:
    """Lowest degree level a phrase accepts: 0 diploma, 1 bachelor's, 2 master's, 3 PhD.
    'B.Tech/M.Tech' or "Bachelor's or Master's" accept a bachelor's."""
    t = (text or "").lower()
    if not t:
        return -1
    ranks = []
    if re.search(r"bachelor|undergrad|graduate degree|\bb\.?\s?(tech|e|sc|com|ca|ba|a)\b|\bbba\b|\bbca\b", t):
        ranks.append(1)
    if re.search(r"master|post\s?grad|\bm\.?\s?(tech|e|s|sc|ca|ba)\b|\bmba\b|\bmca\b|pgdm", t):
        ranks.append(2)
    if re.search(r"ph\.?\s?d|doctor", t):
        ranks.append(3)
    if re.search(r"diploma", t):
        ranks.append(0)
    label = detect_degree(text)
    if label in _DEGREE_RANK:
        ranks.append(_DEGREE_RANK[label])
    return min(ranks) if ranks else None


def _section(text: str, header: str) -> str:
    m = re.search(r"(?im)^[\s•\-*#]*" + header + r"\b[^\n]{0,40}$", text)
    if not m:
        return ""
    after = text[m.end():]
    nxt = re.search(r"(?m)^\s*[A-Z][A-Za-z ,'&/()-]{3,50}:?\s*$", after)
    return after[: nxt.start()] if nxt and nxt.start() > 40 else after[:2500]


_YEARS_RE = re.compile(r"(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:-|–|to)?\s*(\d{1,2})?\s*\+?\s*(?:years?|yrs?)", re.IGNORECASE)


def years_required(jd: str, title: str = "") -> Optional[float]:
    """The overall experience requirement. A range in the title wins; otherwise
    the largest 'N+ years of experience' statement, since smaller numbers in a
    JD are usually per-technology ('2+ years with Kafka')."""
    m = _YEARS_RE.search(title or "")
    if m and 0 < float(m.group(1)) <= 20:
        return float(m.group(1))
    best = None
    for m in _YEARS_RE.finditer(jd or ""):
        ctx = jd[max(0, m.start() - 60): m.end() + 60].lower()
        if not any(w in ctx for w in ("experience", "exp ", "working", "industry", "professional", "hands-on")):
            continue
        if re.search(r"\b(we have|our|founded|since|company|history)\b", jd[max(0, m.start() - 40): m.start()].lower()):
            continue
        val = float(m.group(1))
        if 0 < val <= 15:
            best = val if best is None else max(best, val)
    return best


def _rules_jd(jd: str, title: str) -> Dict[str, Any]:
    req = _section(jd, _REQ_HDR)
    pref = _section(jd, _PREF_HDR)
    all_sk = find_skills(jd)
    pref_sk = find_skills(pref) if pref else {}
    req_sk = find_skills(req) if req else {}
    must, nice, soft = [], [], []
    for s, n in sorted(all_sk.items(), key=lambda kv: -kv[1]):
        if skill_category(s) == SOFT_CATEGORY:
            soft.append(s)
        elif s in pref_sk and s not in req_sk:
            nice.append(s)
        elif s in req_sk or n >= 2 or not req:
            must.append(s)
        else:
            nice.append(s)
    degree = detect_degree(req or jd)
    return {"title": title, "min_years": years_required(jd, title), "degree": degree, "must_have": must[:18], "nice_to_have": nice[:14],
            "soft_skills": soft[:8], "knockouts": [], "method": "rules"}


def analyze_jd(jd: str, title: str = "") -> Dict[str, Any]:
    data = llm_json(
        "You are an ATS configuration expert. Extract the keywords a recruiter would search for or an ATS ranker would "
        "match when screening resumes for this job. Use the exact wording recruiters would search (e.g. 'Python', 'SQL', "
        "'Spring Boot', 'Power BI', 'B2B SaaS', 'financial modeling', 'AWS Certified'). Only concrete, searchable hard "
        "skills, tools, technologies, methods, domains and certifications. NEVER include culture or values phrases, "
        "generic duties, company products, degree names, or vague phrases like 'scalable architecture' or "
        "'engineering culture'. must_have = the core requirements (usually 6-12); nice_to_have = preferred or bonus "
        "items. Each term 1-3 words. Return ONLY JSON:\n"
        '{"title": string, "min_years": number|null (overall minimum years of experience), "degree": string|null, '
        '"must_have": [string], "nice_to_have": [string], "soft_skills": [string], '
        '"knockouts": ["hard requirements such as location, notice period, work authorisation, shift"]}\n'
        "At most 14 must_have, 10 nice_to_have, 6 soft_skills, 5 knockouts.",
        f"JOB TITLE: {title}\n\nJOB DESCRIPTION:\n{jd[:9000]}", max_tokens=1200)
    rules = _rules_jd(jd, title)
    if not data:
        return rules
    def clean(items, limit):
        out, seen = [], set()
        for t in items or []:
            if isinstance(t, str) and 1 < len(t.strip()) <= 50:
                c = canonicalize(t.strip())
                if c.lower() not in seen:
                    seen.add(c.lower())
                    out.append(c)
        return out[:limit]
    must = clean(data.get("must_have"), 14)
    nice = [t for t in clean(data.get("nice_to_have"), 10) if t.lower() not in {m.lower() for m in must}]
    # Lexicon skills the LLM skipped but the JD repeats still count.
    counts = find_skills(jd)
    for s in rules["must_have"]:
        if counts.get(s, 0) >= 2 and s.lower() not in {m.lower() for m in must + nice} and len(must) < 16:
            must.append(s)
    return {
        "title": data.get("title") or title,
        "min_years": data.get("min_years") if isinstance(data.get("min_years"), (int, float)) else rules["min_years"],
        "degree": data.get("degree") or rules["degree"],
        "must_have": must, "nice_to_have": nice,
        "soft_skills": clean(data.get("soft_skills"), 8),
        "knockouts": [k for k in (data.get("knockouts") or []) if isinstance(k, str)][:5],
        "method": "ai",
    }


def _skills_section(text: str) -> str:
    m = re.search(r"(?im)^\s*(technical skills|skills|core competencies|key skills|skills & tools|skills and tools|technologies)\s*:?\s*$", text)
    if not m:
        m = re.search(r"(?im)^\s*(technical skills|skills)\s*[:\-]", text)
        if not m:
            return ""
        return text[m.start(): m.start() + 600].split("\n\n")[0]
    after = text[m.end():]
    nxt = re.search(r"(?m)^\s*[A-Z][A-Za-z &/]{3,40}:?\s*$", after)
    return after[: nxt.start()] if nxt else after[:1200]


def _match_terms(terms: List[str], resume: str, skills_text: str) -> List[Dict[str, Any]]:
    rows = []
    for t in terms:
        total = term_in_text(t, resume)
        in_skills = term_in_text(t, skills_text) if skills_text else 0
        via: List[str] = []
        if total == 0:
            via = implied_by(t, resume)
            status = "implied" if via else "missing"
        elif skills_text and total - in_skills <= 0:
            status = "skills_only"
        else:
            status = "matched"
        row = {"term": t, "status": status, "mentions": total}
        if via:
            row["via"] = via
        rows.append(row)
    return rows


def _title_alignment(title: str, resume: str, headline: Optional[str]) -> Dict[str, Any]:
    t = re.sub(r"\(.*?\)|[-–,|].*$", "", title or "").strip()
    core = [w for w in re.findall(r"[a-z0-9+#/]+", t.lower()) if w not in {"senior", "sr", "junior", "jr", "i", "ii", "iii", "iv", "lead", "staff", "principal", "associate"}]
    if not core:
        return {"score": 60, "status": "unknown", "core_title": t}
    if re.search(r"(?<![a-z])" + r"\W+".join(map(re.escape, core)) + r"(?![a-z])", resume.lower()):
        return {"score": 100, "status": "exact", "core_title": " ".join(core).title()}
    hits = sum(1 for w in core if re.search(r"(?<![a-z])" + re.escape(w), resume.lower()))
    if hits / len(core) >= 0.6:
        return {"score": 65, "status": "partial", "core_title": " ".join(core).title()}
    return {"score": 25, "status": "missing", "core_title": " ".join(core).title()}


def run_check(resume_text: str, profile: Dict[str, Any], audit_result: Dict[str, Any], jd_text: str,
              ats_id: str = "generic", job_title: str = "", company: str = "") -> Dict[str, Any]:
    ats = get_profile(ats_id)
    jd = analyze_jd(jd_text, job_title)
    skills_text = _skills_section(resume_text)
    must = _match_terms(jd["must_have"], resume_text, skills_text)
    nice = _match_terms(jd["nice_to_have"], resume_text, skills_text)
    soft = _match_terms(jd["soft_skills"], resume_text, skills_text)

    def credit(rows):
        # Implied skills get partial credit: an ATS keyword search for "SQL"
        # won't match "PostgreSQL", even though the candidate has it.
        return sum({"matched": 1.0, "skills_only": 0.8, "implied": 0.4}.get(r["status"], 0) for r in rows)

    denom = 2 * len(must) + len(nice)
    keyword_score = round(100 * (2 * credit(must) + credit(nice)) / denom) if denom else 60

    parse = parse_score(audit_result, ats)
    title = _title_alignment(jd.get("title") or job_title, resume_text, profile.get("headline"))

    years = float(profile.get("screening_years") if profile.get("screening_years") is not None else profile.get("years_experience") or 0)
    min_years = jd.get("min_years")
    knockouts = []
    if min_years:
        gap = min_years - years
        exp_score = 100 if gap <= 0 else 75 if gap <= 1 else max(0, 100 - 35 * gap)
        if gap > 0:
            knockouts.append({"type": "experience", "severity": "high" if gap >= 2 else "medium",
                              "detail": f"Asks for {min_years:g}+ years; your resume shows {years:g}"
                                        + (" (internships counted at half weight)." if profile.get("internship_years") else ".")})
    else:
        exp_score = 85
    req_degree = jd.get("degree")
    have_degree = (profile.get("education") or {}).get("degree") or detect_degree(resume_text)
    degree_score = 100
    req_rank = degree_rank(req_degree) if req_degree else None
    if req_rank is not None and req_rank >= 0:
        found = [r for r in (degree_rank(have_degree or ""), degree_rank(detect_degree(resume_text) or "")) if r is not None and r >= 0]
        have_rank = max(found) if found else None
        if have_rank is None:
            degree_score = 50
            knockouts.append({"type": "degree", "severity": "medium", "detail": f"Asks for {req_degree}; no degree was detected on your resume."})
        elif have_rank < req_rank:
            degree_score = 60
            knockouts.append({"type": "degree", "severity": "medium", "detail": f"Asks for {req_degree}; your resume shows {have_degree}."})
    for k in jd.get("knockouts", []):
        knockouts.append({"type": "screening_question", "severity": "info", "detail": k})

    w_kw = ats["keyword_weight"]
    rest = 1 - w_kw
    score = (w_kw * keyword_score + rest * 0.40 * parse["score"] + rest * 0.25 * exp_score
             + rest * 0.20 * title["score"] + rest * 0.15 * degree_score)
    if any(k["type"] == "experience" and k["severity"] == "high" for k in knockouts):
        score = min(score, 52)
    if parse["score"] < 40:
        score = min(score, 45)
    score = int(round(score))
    verdict = "pass" if score >= 75 else "borderline" if score >= 55 else "fail"

    fixes: List[Dict[str, Any]] = []
    for r in parse["reasons"]:
        if r["penalty"] >= 7:
            issue = next((i for i in audit_result["issues"] if i["title"] == r["issue"]), None)
            if issue:
                fixes.append({"priority": 1 if r["penalty"] >= 15 else 2, "kind": "format", "title": issue["title"],
                              "detail": f"Costs about {r['penalty']} points on {ats['name']}. {issue['fix']}"})
    missing_must = [r["term"] for r in must if r["status"] == "missing"]
    if missing_must:
        fixes.append({"priority": 1, "kind": "keywords", "title": f"Missing {len(missing_must)} required keyword(s)",
                      "detail": "Only if you genuinely have them: add " + ", ".join(missing_must[:8])
                                + " to your Skills section and to a bullet that shows you using them.",
                      "terms": missing_must})
    implied = [r for r in must + nice if r["status"] == "implied"]
    if implied:
        fixes.append({"priority": 1, "kind": "keywords", "title": "Name skills you already have in the job's words",
                      "detail": "; ".join(f"write '{r['term']}' (you list {', '.join(r['via'][:2])})" for r in implied[:5])
                                + ". An ATS keyword search won't connect them for you.",
                      "terms": [r["term"] for r in implied]})
    skills_only = [r["term"] for r in must + nice if r["status"] == "skills_only"]
    if skills_only:
        fixes.append({"priority": 2, "kind": "keywords", "title": "Keywords only listed, never shown in use",
                      "detail": "Mention " + ", ".join(skills_only[:6]) + " inside experience or project bullets. Rankers and recruiters weight demonstrated skills higher.",
                      "terms": skills_only})
    if title["status"] != "exact" and title.get("core_title"):
        fixes.append({"priority": 2, "kind": "title", "title": "Match the job title wording",
                      "detail": f"Use the exact phrase '{title['core_title']}' in your headline or summary, if it truthfully describes you. Recruiters search by title first."})
    missing_nice = [r["term"] for r in nice if r["status"] == "missing"]
    if missing_nice:
        fixes.append({"priority": 3, "kind": "keywords", "title": "Bonus keywords to consider",
                      "detail": "Nice-to-haves you don't mention: " + ", ".join(missing_nice[:8]) + ".", "terms": missing_nice})
    fixes.sort(key=lambda f: f["priority"])

    return {
        "company": company, "job_title": jd.get("title") or job_title,
        "ats": public_profile(ats),
        "score": score, "verdict": verdict,
        "breakdown": {"keywords": keyword_score, "parsing": parse["score"], "experience": exp_score, "title": title["score"], "education": degree_score},
        "weights": {"keywords": round(w_kw, 2), "parsing": round(rest * 0.40, 2), "experience": round(rest * 0.25, 2),
                    "title": round(rest * 0.20, 2), "education": round(rest * 0.15, 2)},
        "keywords": {"must_have": must, "nice_to_have": nice, "soft_skills": soft},
        "coverage": {
            "must_matched": sum(1 for r in must if r["status"] != "missing"), "must_total": len(must),
            "must_implied": sum(1 for r in must if r["status"] == "implied"),
            "nice_matched": sum(1 for r in nice if r["status"] != "missing"), "nice_total": len(nice),
        },
        "title_alignment": title,
        "requirements": {"min_years": min_years, "your_years": years, "degree": req_degree, "your_degree": have_degree},
        "knockouts": knockouts,
        "parse_reasons": parse["reasons"],
        "fixes": fixes,
        "jd_method": jd["method"],
    }


def tailor(resume_text: str, jd_text: str, check: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    missing = [r["term"] for r in check["keywords"]["must_have"] if r["status"] != "matched"]
    return llm_json(
        "You are a resume coach for job seekers in India. Rewrite parts of the candidate's resume so it reads well for "
        "this job's ATS keyword search, WITHOUT inventing experience. Only reuse facts that are in the resume. If a "
        "missing keyword isn't supported by the resume, list it under 'do_not_claim' instead of adding it.\n"
        'Return ONLY JSON: {"headline": "one-line headline using the job\'s title wording if it is truthful", '
        '"summary": "2-3 sentence summary", "bullets": [{"original": "existing bullet", "rewrite": "improved bullet with '
        'relevant keywords and a measurable result when the resume gives one"}], "skills_line": "comma-separated skills '
        'line ordered for this job", "do_not_claim": ["keywords the resume does not support"]}\n'
        "Give 3-5 bullets.",
        f"JOB: {check.get('job_title')} at {check.get('company')}\nKEYWORDS TO COVER: {', '.join(missing) or 'none'}\n"
        f"CANDIDATE'S MEASURED EXPERIENCE: {check.get('requirements', {}).get('your_years')} years (use this figure if you mention years)\n\n"
        f"JOB DESCRIPTION:\n{jd_text[:6000]}\n\nRESUME:\n{resume_text[:8000]}",
        max_tokens=1800, timeout=60)
