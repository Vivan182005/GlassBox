"""
Tailored, ATS-safe resume for one job.

The AI restructures the candidate's own resume around the job's keywords;
a fact guard in code then reverts any bullet that introduces a number the
original resume doesn't contain and drops employers that aren't in it.
The result is re-scored with the same ATS check, so the before/after score
is measured, not promised. Output is single column, standard headings,
plain fonts and full URLs: everything the X-ray penalises is designed out.
"""
import difflib
import io
import json
import re
from typing import Any, Dict, List, Optional

from core.llm import llm_json
from matching.ats_check import run_check
from matching.skills_lexicon import implied_by, term_in_text
from parsing.resume_reader import audit, read_text
from application import latex

SECTION_ORDER = ["summary", "skills", "experience", "projects", "education", "certifications", "achievements"]
HEADINGS = {"summary": "SUMMARY", "skills": "SKILLS", "experience": "EXPERIENCE", "projects": "PROJECTS",
            "education": "EDUCATION", "certifications": "CERTIFICATIONS", "achievements": "ACHIEVEMENTS"}

_STRUCTURE_PROMPT = (
    "Transcribe this resume into JSON exactly as written. Copy every bullet VERBATIM (fix only line-break hyphenation "
    "and missing spaces), keep every entry in its original order, and invent nothing. Fields that aren't present are "
    "null or empty lists. Return ONLY JSON:\n"
    '{"headline": str|null (a role line under the name, if any), "summary": str|null (an intro paragraph, if any), '
    '"skills": [{"group": str (label before the colon, or "Skills"), "items": [str]}], '
    '"experience": [{"company": str, "title": str, "location": str|null, "dates": str|null, "bullets": [str]}], '
    '"projects": [{"name": str, "subtitle": str|null (tagline after a dash), "tech": str|null (tech stack line), '
    '"bullets": [str]}], '
    '"education": [{"school": str, "degree": str|null, "dates": str|null, "location": str|null, "detail": str|null (grade, coursework or note)}], '
    '"certifications": [str], "achievements": [str]}'
)

_EDIT_PROMPT = (
    "You tailor a candidate's resume for ONE job with the smallest set of edits that gets it through ATS keyword "
    "screening. You are given the resume as JSON. Return only the edits. Rules:\n"
    "1. Use ONLY facts already in the resume. Never add employers, titles, dates, numbers, tools or claims.\n"
    "2. bullet_edits: rewrite a bullet only when a small change lets it use the job's exact wording for something it "
    "already shows (e.g. 'dashboards in Tableau' -> 'data visualization dashboards in Tableau'). Keep every number and "
    "the bullet's length. Only INSERT a few words into the original sentence; never delete or replace its words. Place "
    "each keyword under KEYWORDS TO PLACE in a bullet that mentions the tool it names in brackets, and nowhere else, "
    "in brackets after that tool: 'PostgreSQL' -> 'PostgreSQL (SQL)', 'FastAPI' -> 'FastAPI (REST APIs)'. "
    "Never put a skill into a bullet that doesn't already show it. Leave all other bullets out.\n"
    "3. skills: the same groups with the same names; reorder items so the job's must-haves come first; add a keyword "
    "only when the resume shows it (e.g. 'SQL' when it lists PostgreSQL).\n"
    "4. headline / summary: an edited version only if the resume has one, same length and voice; else null.\n"
    "Return ONLY JSON:\n"
    '{"bullet_edits": [{"original": "the bullet, copied exactly", "text": "edited bullet"}], '
    '"skills": [{"group": str, "items": [str]}], "headline": str|null, "summary": str|null, '
    '"do_not_claim": ["job keywords the resume does not support"], '
    '"cover_letter": "150-220 words, first person, specific to this company and role, only resume facts, no greeting or sign-off"}'
)

_NUM = re.compile(r"\d+(?:[.,]\d+)?")


def _numbers(text: str) -> set:
    return {n.replace(",", "") for n in _NUM.findall(text or "")}


def _normalize(data: Dict[str, Any]) -> Dict[str, Any]:
    """LLMs sometimes return a list of strings where objects were asked for;
    coerce every section to the documented shape so rendering never breaks."""
    def as_list(v):
        return v if isinstance(v, list) else ([v] if v else [])

    skills = []
    for g in as_list(data.get("skills")):
        if isinstance(g, str):
            skills.append({"group": "Skills", "items": [x.strip() for x in g.split(",") if x.strip()]})
        elif isinstance(g, dict):
            skills.append({"group": g.get("group") or "Skills", "items": [str(i) for i in as_list(g.get("items")) if i]})
    data["skills"] = skills
    data["experience"] = [e for e in as_list(data.get("experience")) if isinstance(e, dict)]
    data["projects"] = [p for p in as_list(data.get("projects")) if isinstance(p, dict) and p.get("name")]
    for p in data["projects"]:  # a link's label isn't a tagline
        if re.fullmatch(r"\s*(link|github|demo|code|live|repo|website)?\s*", str(p.get("subtitle") or ""), re.I):
            p["subtitle"] = None
        p["name"] = re.sub(r"\s*[-–—|]\s*(Link|GitHub|Demo|Code)\s*$", "", str(p["name"]))
    data["education"] = [e for e in as_list(data.get("education")) if isinstance(e, dict) and (e.get("school") or e.get("degree"))]
    for key in ("certifications", "achievements", "do_not_claim"):
        data[key] = [str(x) for x in as_list(data.get(key)) if x and not isinstance(x, (dict, list))]
    for key in ("headline", "summary", "cover_letter"):
        if not isinstance(data.get(key), str):
            data[key] = ""
    return data


def _flat(text: str) -> str:
    """Whitespace/punctuation-insensitive form for matching wording."""
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def bullet_text(b: Any) -> str:
    return (b.get("text") if isinstance(b, dict) else b) or ""


def _guard(data: Dict[str, Any], source: str) -> List[str]:
    """Reverts bullets with numbers the original resume doesn't have; drops
    employers that aren't in it. Returns notes on what was corrected."""
    src_nums = _numbers(source)
    src_lower = re.sub(r"\s+", " ", source.lower())
    notes = []

    src_flat = _flat(source)

    def fix_bullets(bullets):
        """Each bullet becomes {text, original}: original is the resume's own
        wording (None for a bullet the resume doesn't have), so the user can
        accept or reject every edit."""
        out = []
        for b in bullets or []:
            if isinstance(b, str):
                b = {"text": b, "source": ""}
            text = (b.get("text") or "").strip()
            orig = (b.get("original") or b.get("source") or "").strip()
            original = orig if orig and _flat(orig)[:60] in src_flat else None
            extra = _numbers(text) - src_nums
            if extra:
                if original:
                    notes.append(f"Kept your original wording where the rewrite added {', '.join(sorted(extra))}.")
                    text = original
                else:
                    notes.append(f"Dropped a bullet that claimed {', '.join(sorted(extra))}, which isn't on your resume.")
                    continue
            if text:
                out.append({**{k: v for k, v in b.items() if k not in ("text", "source", "original")}, "text": text, "original": original or text})
        return out

    # Skills: every item must be traceable to the original resume, and nothing
    # the model itself flagged as unsupported may slip back in.
    # The resume is the authority in both directions: a skill it shows is kept
    # even if the model listed it under do_not_claim, and do_not_claim is
    # cleaned of anything the resume actually has.
    def supported(item: str) -> bool:
        item = item.strip()
        return bool(item) and (term_in_text(item, source) > 0 or bool(implied_by(item, source)))

    dnc = [re.sub(r"\s*\(.*?\)\s*", " ", t).strip() for t in data.get("do_not_claim") or []]
    data["do_not_claim"] = list(dict.fromkeys(t for t in dnc if t and not supported(t)))

    for g in data.get("skills") or []:
        items = []
        own = set(g.get("original") or [])
        for raw in g.get("items") or []:
            if raw in own:  # transcribed from the resume itself
                items.append(raw)
                continue
            m = re.match(r"^(.*?)\s*\((.*)\)\s*$", raw or "")
            if m:  # "AI tools (LLMs, OpenAI API, Claude)": check each inner item
                inner = [x.strip() for x in m.group(2).split(",") if supported(x)]
                base_ok = supported(m.group(1))
                if inner:
                    items.append(f"{m.group(1)} ({', '.join(inner)})")
                elif base_ok:
                    items.append(m.group(1))
                dropped = [x.strip() for x in m.group(2).split(",") if x.strip() and x.strip() not in inner]
            else:
                dropped = [] if supported(raw or "") else [raw]
                if not dropped:
                    items.append(raw)
            for d in dropped:
                if d:
                    notes.append(f"Removed skill '{d}', which isn't on your resume.")
        g["items"] = items
        if g.get("original") is not None:
            continue
        m = re.search(r"(?im)^\s*" + re.escape(g.get("group") or "~~") + r"\s*:\s*(.+(?:\n(?![^\n]{0,40}:)[^\n]+){0,2})", source)
        if m:
            body = m.group(1).split("\n\n")[0]
            body = re.split(r"\n(?=[A-Z][\w &/]{2,30}\n)", body)[0].replace("\n", " ")
            g["original"] = [x.strip() for x in re.split(r",(?![^()]*\))", body) if x.strip()]
        else:
            g["original"] = None

    kept = []
    for e in data.get("experience") or []:
        company = (e.get("company") or "").strip()
        first = company.lower().split(",")[0].split("(")[0].strip()
        if first and first[:12] not in src_lower:
            notes.append(f"Removed '{company}', which isn't on your original resume.")
            continue
        e["bullets"] = fix_bullets(e.get("bullets"))
        kept.append(e)
    data["experience"] = kept
    for p in data.get("projects") or []:
        p["bullets"] = fix_bullets(p.get("bullets"))
    return notes


def to_text(data: Dict[str, Any], header: Dict[str, Any]) -> str:
    """Plain-text rendering; also what the ATS check scores."""
    lines = [header["name"]]
    if data.get("headline"):
        lines.append(data["headline"])
    lines.append(" | ".join(header["contact"]))
    for sec in SECTION_ORDER:
        body = _section_lines(data, sec)
        if body:
            lines += ["", HEADINGS[sec]] + body
    return "\n".join(lines)


def _section_lines(data: Dict[str, Any], sec: str) -> List[str]:
    out: List[str] = []
    if sec == "summary" and data.get("summary"):
        out.append(data["summary"])
    elif sec == "skills":
        for g in data.get("skills") or []:
            items = [i for i in g.get("items") or [] if i]
            if items:
                out.append(f"{g.get('group') or 'Skills'}: {', '.join(items)}")
    elif sec == "experience":
        for e in data.get("experience") or []:
            out.append(f"{e.get('title', '')}, {e.get('company', '')}" + (f", {e['location']}" if e.get("location") else "")
                       + (f" | {e['dates']}" if e.get("dates") else ""))
            out += [f"- {bullet_text(b)}" for b in e.get("bullets") or []]
    elif sec == "projects":
        for p in data.get("projects") or []:
            out.append(p.get("name", "") + (f" - {p['subtitle']}" if p.get("subtitle") else "") + (f" | {p['tech']}" if p.get("tech") else "")
                       + (f" | {p['link']}" if p.get("link") else ""))
            out += [f"- {bullet_text(b)}" for b in p.get("bullets") or []]
    elif sec == "education":
        for ed in data.get("education") or []:
            out.append(", ".join(x for x in [ed.get("degree"), ed.get("school")] if x) + (f" | {ed['dates']}" if ed.get("dates") else ""))
            if ed.get("detail"):
                out.append(ed["detail"])
    elif sec in ("certifications", "achievements"):
        out += [f"- {c}" for c in data.get(sec) or [] if c]
    return out


def _add_implied_skills(data: Dict[str, Any], rows: List[Dict[str, Any]], notes: List[str]) -> None:
    """A skill the resume shows through a specific tool (SQL via PostgreSQL)
    goes into the group that lists that tool, in the job's own word."""
    text = to_text(data, {"name": "", "contact": []})
    for r in rows:
        if r["status"] != "implied" or term_in_text(r["term"], text):
            continue
        group = next((g for g in data.get("skills") or [] if any(term_in_text(v, ", ".join(g.get("items") or [])) for v in r.get("via") or [])), None)
        if group is None and data.get("skills"):
            group = data["skills"][0]
        if group is not None:
            group["items"] = list(group.get("items") or []) + [r["term"]]
            notes.append(f"Added '{r['term']}' to {group.get('group') or 'Skills'}: you list {', '.join(r.get('via') or [])}.")


def _link_projects(data: Dict[str, Any], link_lines: List[Dict[str, str]]) -> None:
    """Replace placeholder link text ("GitHub", "Link") with the real URL the
    original PDF hid behind it. Each link is matched through the line it sat
    on in the original (the project's title row); ATS can't follow links."""
    for p in data.get("projects") or []:
        link = (p.get("link") or "").strip()
        if re.match(r"^(https?://|www\.)", link) or re.search(r"\.(com|io|dev|app|in)/", link):
            continue
        words = {w for w in re.findall(r"[a-z0-9]+", (p.get("name") or "").lower()) if len(w) > 2}
        best, best_hits = None, 0
        for l in link_lines:
            if re.search(r"linkedin\.com|mailto:", l["uri"]):
                continue
            line = re.sub(r"[^a-z0-9]+", " ", l["line"].lower())
            hits = sum(1 for w in words if re.search(r"\b" + re.escape(w), line))
            if hits > best_hits:
                best, best_hits = l, hits
        p["link"] = re.sub(r"^https?://(www\.)?", "", best["uri"]).rstrip("/") if best else None
        label = re.search(r"\b(Link|GitHub|Github|Demo|Code|Live|Repo|Website)\s*$", best["line"]) if best else None
        p["link_label"] = label.group(1) if label else None


def _header(profile: Dict[str, Any], contact: Dict[str, Any]) -> Dict[str, Any]:
    bits = []
    if profile.get("location"):
        bits.append(f"{profile['location']}, India")
    for k in ("phone", "email", "linkedin", "github"):
        if contact.get(k):
            bits.append(re.sub(r"^https?://(www\.)?", "", contact[k]).rstrip("/"))
    return {"name": profile.get("name") or "Your Name", "contact": bits}


def resume_structure(resume_text: str) -> Optional[Dict[str, Any]]:
    """The original resume as sections/entries/bullets, verbatim (cached by the LLM layer)."""
    raw = llm_json(_STRUCTURE_PROMPT, resume_text[:12000], max_tokens=5000, timeout=90)
    if not isinstance(raw, dict):
        return None
    data = _normalize(raw)
    for sec in ("experience", "projects"):
        for it in data[sec]:
            it["bullets"] = [{"text": str(b).strip(), "original": str(b).strip()} for b in it.get("bullets") or []
                             if isinstance(b, (str, int, float)) and str(b).strip()]
    for g in data["skills"]:
        g["original"] = list(g["items"])
    return data


_GLUE = {"a", "an", "the", "and", "or", "to", "for", "of", "in", "on", "with", "by", "using", "via", "as", "at", "from", "into"}


def _drops_facts(original: str, new: str) -> bool:
    """True when the edit removes a content word of the original: edits may
    add the job's wording, never trade away what the candidate did."""
    words = lambda t: re.findall(r"[a-z0-9+#]+(?:\.[a-z0-9]+)*", t.lower())
    kept = set(words(new))
    return any(w not in kept and w not in _GLUE for w in words(original))


def _apply_edits(data: Dict[str, Any], edits: Dict[str, Any], source: str, notes: List[str], keywords: List[str]) -> None:
    src_nums = _numbers(source)
    placed: set = set()
    bullets = [b for sec in ("experience", "projects") for it in data[sec] for b in it["bullets"]]
    for e in edits.get("bullet_edits") or []:
        if not isinstance(e, dict) or not e.get("original") or not e.get("text"):
            continue
        target = _flat(e["original"])
        best, score = None, 0.0
        for b in bullets:
            r = difflib.SequenceMatcher(None, target, _flat(b["original"])).ratio()
            if r > score:
                best, score = b, r
        if not best or score < 0.85:
            continue
        new = str(e["text"]).strip()
        extra = _numbers(new) - src_nums
        if extra:
            notes.append(f"Skipped an edit that added {', '.join(sorted(extra))}, which isn't on your resume.")
            continue
        # An edit earns its place only by naming a job keyword the bullet didn't
        # have yet, once per keyword, without bloating the line.
        gained = {k for k in keywords if term_in_text(k, new) and not term_in_text(k, best["original"])}
        # Truthful only if this bullet itself shows the skill: "SQL" into a
        # bullet about PostgreSQL, never "Java" into one that never used it.
        if any(not implied_by(k, best["original"]) for k in gained):
            continue
        if not gained or gained <= placed or len(new) > len(best["original"]) * 1.35 + 20 or _drops_facts(best["original"], new):
            continue
        placed |= gained
        best["text"] = new
        best["keywords"] = sorted(gained)
    # Skills: only the resume's own groups, matched by name.
    by_name = {(g.get("group") or "").strip().lower(): g for g in data["skills"]}
    for g in edits.get("skills") or []:
        if not isinstance(g, dict):
            continue
        own = by_name.get((g.get("group") or "").strip().lower())
        if own and isinstance(g.get("items"), list) and g["items"]:
            own["items"] = [str(i) for i in g["items"] if i]
    for key in ("headline", "summary"):
        if data.get(key) and isinstance(edits.get(key), str) and edits[key].strip() and not (_numbers(edits[key]) - src_nums):
            data[key] = edits[key].strip()
    data["do_not_claim"] = edits.get("do_not_claim") or []
    data["cover_letter"] = edits.get("cover_letter") if isinstance(edits.get("cover_letter"), str) else ""


def build(resume_text: str, profile: Dict[str, Any], audit_result: Dict[str, Any], jd_text: str, before: Dict[str, Any],
          ats_id: str, job_title: str, company: str) -> Optional[Dict[str, Any]]:
    data = resume_structure(resume_text)
    if not data:
        return None
    must = [r["term"] for r in before["keywords"]["must_have"]]
    nice = [r["term"] for r in before["keywords"]["nice_to_have"]]
    rows = before["keywords"]["must_have"] + before["keywords"]["nice_to_have"]
    to_place = [f"{r['term']} (only in a bullet that mentions {' or '.join(r['via'])})" for r in rows if r["status"] == "implied"]
    implied = [f"{r['term']} (shown by {', '.join(r['via'])})" for r in rows if r["status"] == "implied"]
    view = {k: data[k] for k in ("headline", "summary", "skills")}
    view["experience"] = [{**{k: v for k, v in e.items() if k != "bullets"}, "bullets": [b["text"] for b in e["bullets"]]} for e in data["experience"]]
    view["projects"] = [{**{k: v for k, v in p.items() if k != "bullets"}, "bullets": [b["text"] for b in p["bullets"]]} for p in data["projects"]]
    edits = llm_json(_EDIT_PROMPT,
                     f"JOB: {job_title} at {company}\nMUST-HAVE KEYWORDS: {', '.join(must)}\nNICE-TO-HAVE: {', '.join(nice)}\n"
                     f"KEYWORDS TO PLACE (supported by the resume, not yet in the job's words): {', '.join(to_place) or 'none'}\n"
                     f"IMPLIED BY THE RESUME (truthful to name): {', '.join(implied) or 'none'}\n\n"
                     f"JOB DESCRIPTION:\n{jd_text[:5000]}\n\nRESUME JSON:\n{json.dumps(view, ensure_ascii=False)[:9000]}",
                     max_tokens=3000, timeout=90) or {}
    notes: List[str] = []
    _apply_edits(data, edits, resume_text, notes, must + nice)
    notes += _guard(data, resume_text)
    _add_implied_skills(data, rows, notes)
    _link_projects(data, (audit_result.get("contact") or {}).get("link_lines") or [])
    plan = latex.section_plan(resume_text)
    header = _header(profile, audit_result.get("contact") or {})
    text = to_text(data, header)

    new_audit = audit(read_text(text))
    after = run_check(text, profile, new_audit, jd_text, ats_id, job_title, company)
    return {
        "resume": data, "header": header, "text": text, "fact_notes": notes,
        "do_not_claim": data.get("do_not_claim") or [],
        "cover_letter": data.get("cover_letter") or "",
        "before": {"score": before["score"], "verdict": before["verdict"], "coverage": before["coverage"]},
        "after": {"score": after["score"], "verdict": after["verdict"], "coverage": after["coverage"],
                  "keywords": after["keywords"], "fixes": after["fixes"]},
        "audit_issues": [i["title"] for i in new_audit["issues"]],
        "style": audit_result.get("style") or {}, "plan": plan,
        "changes": sum(1 for sec in ("experience", "projects") for it in data.get(sec) or [] for b in it.get("bullets") or []
                       if _flat(b["text"]) != _flat(b["original"])),
        "latex_engine": latex.can_compile(),
    }


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------

_LATIN = str.maketrans({"–": "-", "—": "-", "‘": "'", "’": "'", "“": '"', "”": '"', "•": "-", "…": "...", "₹": "Rs.",
                        "→": "->", " ": " ", "​": ""})


def _latin(s: str) -> str:
    import unicodedata
    s = re.sub(r"[\u2010-\u2015\u2212]", "-", (s or "").translate(_LATIN)).replace("\u00ad", "")
    # Anything still outside Latin-1 (the PDF core fonts' range) is decomposed
    # to its base letter, or dropped, rather than printed as "?".
    out = []
    for ch in s:
        if ord(ch) < 256:
            out.append(ch)
        else:
            base = unicodedata.normalize("NFKD", ch).encode("latin-1", "ignore").decode("latin-1")
            out.append(base)
    return "".join(out)


def to_pdf(data: Dict[str, Any], header: Dict[str, Any]) -> bytes:
    from fpdf import FPDF

    pdf = FPDF(format="A4")
    pdf.set_margins(16, 14, 16)
    pdf.set_auto_page_break(True, 14)
    pdf.add_page()
    w = pdf.w - pdf.l_margin - pdf.r_margin
    pdf.set_font("Helvetica", "B", 17)
    pdf.cell(w, 8, _latin(header["name"]), new_x="LMARGIN", new_y="NEXT", align="C")
    if data.get("headline"):
        pdf.set_font("Helvetica", "", 10.5)
        pdf.cell(w, 5.5, _latin(data["headline"]), new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "", 9.5)
    pdf.multi_cell(w, 4.8, _latin(" | ".join(header["contact"])), align="C", new_x="LMARGIN", new_y="NEXT")

    def heading(t):
        pdf.ln(2.5)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(w, 6, t, new_x="LMARGIN", new_y="NEXT")
        y = pdf.get_y()
        pdf.line(pdf.l_margin, y, pdf.l_margin + w, y)
        pdf.ln(1.2)

    def para(t, style="", size=10, h=4.9):
        pdf.set_font("Helvetica", style, size)
        pdf.multi_cell(w, h, _latin(t), align="L", new_x="LMARGIN", new_y="NEXT")

    def bullet(t):
        pdf.set_font("Helvetica", "", 10)
        pdf.set_x(pdf.l_margin + 3)
        pdf.multi_cell(w - 3, 4.9, _latin(f"- {t}"), align="L", new_x="LMARGIN", new_y="NEXT")

    for sec in SECTION_ORDER:
        if not _section_lines(data, sec):
            continue
        heading(HEADINGS[sec])
        if sec == "summary":
            para(data["summary"])
        elif sec == "skills":
            for g in data.get("skills") or []:
                if g.get("items"):
                    para(f"{g.get('group') or 'Skills'}: {', '.join(g['items'])}")
        elif sec == "experience":
            for e in data["experience"]:
                para(f"{e.get('title', '')}, {e.get('company', '')}" + (f", {e['location']}" if e.get("location") else "")
                     + (f"  |  {e['dates']}" if e.get("dates") else ""), "B")
                for b in e.get("bullets") or []:
                    bullet(bullet_text(b))
                pdf.ln(1)
        elif sec == "projects":
            for p in data["projects"]:
                para(p.get("name", "") + (f"  |  {p['tech']}" if p.get("tech") else ""), "B")
                if p.get("link"):
                    para(p["link"], size=9)
                for b in p.get("bullets") or []:
                    bullet(bullet_text(b))
                pdf.ln(1)
        elif sec == "education":
            for ed in data["education"]:
                para(", ".join(x for x in [ed.get("degree"), ed.get("school")] if x) + (f"  |  {ed['dates']}" if ed.get("dates") else ""), "B")
                if ed.get("detail"):
                    para(ed["detail"])
        else:
            for c in data.get(sec) or []:
                bullet(c)
    return bytes(pdf.output())


def to_docx(data: Dict[str, Any], header: Dict[str, Any]) -> bytes:
    import docx
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt

    d = docx.Document()
    style = d.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(10.5)
    for s in d.sections:
        s.left_margin = s.right_margin = s.top_margin = s.bottom_margin = Cm(1.8)
    p = d.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(header["name"])
    r.bold, r.font.size = True, Pt(17)
    for line in ([data["headline"]] if data.get("headline") else []) + [" | ".join(header["contact"])]:
        q = d.add_paragraph(line)
        q.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for sec in SECTION_ORDER:
        body = _section_lines(data, sec)
        if not body:
            continue
        h = d.add_paragraph()
        hr = h.add_run(HEADINGS[sec])
        hr.bold, hr.font.size = True, Pt(11.5)
        for line in body:
            if line.startswith("- "):
                d.add_paragraph(line[2:], style="List Bullet")
            else:
                para = d.add_paragraph()
                run = para.add_run(line)
                run.bold = sec in ("experience", "projects", "education") and " | " in line
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()
