import os
import sys
import json
import re
import base64
import concurrent.futures as cf
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core.llm import llm_status
from core.db import get_supabase
from core.ratelimit import Limiter, allowed_origins, client_ip, cost_class
from ats.profiles import ATS_PROFILES, get_profile, public_profile
from ats.detector import lookup_company, confirm_company_ats, company_board_jobs
from jobs.boards import load_registry, fetch_job_description, INDIA_CITIES
from jobs.discovery import discover_jobs, warm_cache, expand_roles, score_job
from jobs.network import RAPIDAPI_KEY, company_listings, network_status, search_links
from parsing.resume_reader import read_resume, read_text, audit, parse_score, ats_view
from parsing.profile_extractor import extract_profile
from matching.ats_check import run_check, tailor
from application.rating import rate, APPLY_THRESHOLD
from application.forms import application_form
from application.answers import answer_form, summarize
from application import latex, pdf_edit, resume_builder
from jobs.role_titles import ROLE_TITLES
from matching.skills_lexicon import _SKILLS

app = FastAPI(title="GlassBox ML Service", description="Resume X-ray, India job network and ATS pass check", version="2.0.0")

ORIGINS = allowed_origins()
limiter = Limiter()


# Registered before CORS so CORS wraps it and the refusals below still reach
# the app's error messages.
@app.middleware("http")
async def guard(request: Request, call_next):
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") not in ORIGINS:
        return JSONResponse({"detail": "This site isn't allowed to use the GlassBox API."}, status_code=403)
    if request.url.path.startswith("/api/") and request.method != "OPTIONS":
        refused = limiter.check(client_ip(request.headers, request.client.host if request.client else None),
                                cost_class(request.url.path))
        if refused:
            message, wait = refused
            return JSONResponse({"detail": message, "rate_limited": True}, status_code=429,
                                headers={"Retry-After": str(wait)})
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGINS, allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["*"],
    expose_headers=["Content-Disposition", "Retry-After", "X-Resume-Renderer"],
)

MAX_UPLOAD_BYTES = 8 * 1024 * 1024


@app.on_event("startup")
def _startup():
    warm_cache()


@app.get("/api/health")
def health():
    registry = load_registry()
    by_ats: Dict[str, int] = {}
    for c in registry:
        name = get_profile(c["ats"])["name"]
        by_ats[name] = by_ats.get(name, 0) + 1
    return {
        "status": "ok", "service": "GlassBox ML Service", "version": app.version,
        "llm": llm_status(),
        "network": {"companies": len(registry), "by_ats": by_ats, **network_status()},
        "latex": latex.can_compile(), "supabase": get_supabase() is not None,
    }


@app.get("/api/meta")
def meta():
    registry = load_registry()
    return {
        "companies": [{"name": c["name"], "domain": c.get("domain"), "ats_id": c["ats"], "ats_name": get_profile(c["ats"])["name"]} for c in registry],
        "ats_profiles": [public_profile(p) for p in ATS_PROFILES],
        "cities": list(INDIA_CITIES.keys()) + ["Remote"],
        "roles": ROLE_TITLES,
        "skills": sorted({c for c, _, _ in _SKILLS}, key=str.lower),
    }


# ---------------------------------------------------------------------------
# Resume X-ray
# ---------------------------------------------------------------------------

def _ats_scores(audit_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    scores = []
    for p in ATS_PROFILES:
        s = parse_score(audit_result, p)
        scores.append({"id": p["id"], "name": p["name"], "region": p["vendor_region"], "score": s["score"], "reasons": s["reasons"]})
    return sorted(scores, key=lambda s: s["score"])


@app.post("/api/resume/analyze")
async def analyze_resume(file: Optional[UploadFile] = File(None), raw_text: Optional[str] = Form(None)):
    if file is not None:
        data = await file.read()
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "Resume file is larger than 8 MB.")
        try:
            read = read_resume(data, file.filename or "resume")
        except Exception as e:
            raise HTTPException(422, f"Could not read this file: {str(e)[:120]}. Upload a PDF or DOCX.")
    elif raw_text and raw_text.strip():
        read = read_text(raw_text)
    else:
        raise HTTPException(400, "Upload a PDF/DOCX resume or paste the text.")

    audit_result = audit(read)
    profile = extract_profile(read["text"], audit_result) if read["text"] else {"error": "No text", "warnings": [], "skills": [], "target_roles": []}
    scores = _ats_scores(audit_result)
    avg = round(sum(s["score"] for s in scores) / len(scores)) if scores else 0
    return {
        "resume_text": read["text"],
        "naive_text": read["naive_text"],
        "profile": profile,
        "audit": audit_result,
        "ats_scores": scores,
        "readability": avg,
        "ats_view": ats_view(read, audit_result, get_profile("workday")) | {"ats_id": "workday"},
    }


class ViewRequest(BaseModel):
    resume_text: str
    naive_text: Optional[str] = None
    audit: Dict[str, Any]
    ats_id: str


@app.post("/api/resume/ats-view")
def resume_ats_view(req: ViewRequest):
    read = {"text": req.resume_text, "naive_text": req.naive_text or req.resume_text}
    return ats_view(read, req.audit, get_profile(req.ats_id)) | {"ats_id": req.ats_id}


# ---------------------------------------------------------------------------
# Jobs in India
# ---------------------------------------------------------------------------

class JobSearchRequest(BaseModel):
    roles: List[str]
    skills: List[str] = []
    years_experience: float = 0.0
    cities: List[str] = []
    max_age_days: Optional[int] = None
    limit: int = 120
    student: bool = False


@app.post("/api/jobs/search")
def jobs_search(req: JobSearchRequest):
    return discover_jobs(req.roles, req.skills, req.years_experience, req.cities, req.max_age_days, req.limit, req.student)


@app.get("/api/jobs/description")
def job_description(id: str):
    return fetch_job_description(id)


# ---------------------------------------------------------------------------
# ATS pass check
# ---------------------------------------------------------------------------

class CheckRequest(BaseModel):
    resume_text: str
    profile: Dict[str, Any] = {}
    audit: Dict[str, Any]
    job_id: Optional[str] = None
    jd_text: Optional[str] = None
    ats_id: Optional[str] = None
    company: Optional[str] = ""
    job_title: Optional[str] = ""


@app.post("/api/check")
def ats_check(req: CheckRequest):
    jd = (req.jd_text or "").strip()
    if not jd and req.job_id:
        jd = (fetch_job_description(req.job_id).get("description") or "").strip()
    if len(jd) < 80:
        raise HTTPException(400, "The job description is empty or too short to check against. Paste the full JD.")
    ats_id = req.ats_id
    if not ats_id and req.company:
        ats_id = (lookup_company(req.company).get("ats") or {}).get("id")
    result = run_check(req.resume_text, req.profile or {}, req.audit, jd, ats_id or "generic", req.job_title or "", req.company or "")
    result["jd_text"] = jd
    result["ats_source"] = "job_board" if req.ats_id else ("company_lookup" if ats_id else "generic")
    return result


class TailorRequest(BaseModel):
    resume_text: str
    jd_text: str
    check: Dict[str, Any]


@app.post("/api/check/tailor")
def ats_tailor(req: TailorRequest):
    out = tailor(req.resume_text, req.jd_text, req.check)
    if not out:
        raise HTTPException(503, "AI rewriting is unavailable right now (no working LLM key).")
    return out


# ---------------------------------------------------------------------------
# Apply: rate -> tailor -> answer -> approve
# ---------------------------------------------------------------------------

class RateRequest(BaseModel):
    resume_text: str
    profile: Dict[str, Any] = {}
    audit: Dict[str, Any]
    jobs: List[Dict[str, Any]]
    cities: List[str] = []


def _jd_for(job: Dict[str, Any]) -> str:
    return (fetch_job_description(job["id"]).get("description") or "").strip() if job.get("id") else ""


def _rate_one(req_resume: str, profile, audit_result, job, cities):
    jd = _jd_for(job)
    if len(jd) < 80:
        return {"id": job.get("id"), "error": "No job description to rate against."}
    check = run_check(req_resume, profile, audit_result, jd, job.get("ats_id") or "generic", job.get("title", ""), job.get("company", ""))
    return {"id": job["id"], "rating": rate(job, check, cities, profile), "check_score": check["score"], "verdict": check["verdict"]}


@app.post("/api/apply/rate")
def apply_rate(req: RateRequest):
    """1-5 rating for up to 12 jobs: worth applying at 4.0+."""
    jobs = req.jobs[:12]
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(lambda j: _rate_one(req.resume_text, req.profile, req.audit, j, req.cities), jobs))
    return {"threshold": APPLY_THRESHOLD, "ratings": results}


class PrepareRequest(BaseModel):
    resume_text: str
    profile: Dict[str, Any] = {}
    audit: Dict[str, Any]
    job: Dict[str, Any]
    saved_answers: Dict[str, Any] = {}
    cities: List[str] = []


@app.post("/api/apply/prepare")
def apply_prepare(req: PrepareRequest):
    """Everything needed to apply to one job: rating, tailored resume (re-scored),
    cover letter, and an answer for every question on the real form."""
    job = req.job
    jd = _jd_for(job)
    if len(jd) < 80:
        raise HTTPException(400, "This posting has no readable job description, so it can't be tailored.")
    ats_id = job.get("ats_id") or "generic"
    before = run_check(req.resume_text, req.profile, req.audit, jd, ats_id, job.get("title", ""), job.get("company", ""))
    with cf.ThreadPoolExecutor(max_workers=3) as ex:
        f_form = ex.submit(application_form, job["id"])
        f_resume = ex.submit(resume_builder.build, req.resume_text, req.profile, req.audit, jd, before, ats_id,
                             job.get("title", ""), job.get("company", ""))
        form = f_form.result()
        answers = answer_form(form["fields"], req.resume_text, req.profile, req.audit.get("contact") or {}, job, jd, req.saved_answers)
        tailored = f_resume.result()
    return {
        "job": {k: job.get(k) for k in ("id", "title", "company", "url", "ats_id", "ats_name", "location")},
        "rating": rate(job, before, req.cities, req.profile),
        "check": {k: before[k] for k in ("score", "verdict", "breakdown", "coverage", "knockouts", "ats")},
        "tailored": tailored,
        "form": {"source": form["source"], "note": form.get("note") or form.get("error")},
        "answers": answers,
        "answer_summary": summarize(answers),
    }


class RenderRequest(BaseModel):
    source_pdf: str  # base64 of the candidate's original PDF
    resume: Dict[str, Any]
    profile: Dict[str, Any] = {}
    audit: Dict[str, Any]
    job: Dict[str, Any]
    cities: List[str] = []


def _edits_from(resume: Dict[str, Any]) -> List[Dict[str, str]]:
    edits = []
    for sec in ("experience", "projects"):
        for i, it in enumerate(resume.get(sec) or []):
            for j, b in enumerate(it.get("bullets") or []):
                if isinstance(b, dict) and b.get("original") and b.get("text") != b.get("original"):
                    edits.append({"id": f"{sec}:{i}:{j}", "original": b["original"], "text": b["text"], "kind": "bullet"})
    for i, g in enumerate(resume.get("skills") or []):
        if g.get("original") and g.get("items") != g["original"]:
            label = g.get("group") or "Skills"
            edits.append({"id": f"skills:{i}", "original": f"{label}: {', '.join(g['original'])}",
                          "text": f"{label}: {', '.join(g['items'])}", "kind": "line"})
    return edits


@app.post("/api/apply/render")
def apply_render(req: RenderRequest):
    """Writes the kept edits into the candidate's own PDF (same fonts, colours,
    positions) and measures the result: the edited file is read back with the
    same reader and checked against the job, so the scores describe the exact
    file that will be sent."""
    try:
        source = base64.b64decode(req.source_pdf)
    except Exception:
        raise HTTPException(400, "The original PDF couldn't be read. Scan it again.")
    edits = _edits_from(req.resume)
    edited, report = pdf_edit.apply_edits(source, edits) if edits else (None, [])
    final = edited or source
    read = read_resume(final, "resume.pdf")
    audit_result = audit(read)
    jd = _jd_for(req.job)
    if len(jd) < 80:
        raise HTTPException(400, "This posting has no readable job description.")
    job = req.job
    check = run_check(read["text"], req.profile, audit_result, jd, job.get("ats_id") or "generic", job.get("title", ""), job.get("company", ""))
    return {
        "pdf": base64.b64encode(final).decode(),
        "edited": edited is not None,
        "report": report,
        "check": {k: check[k] for k in ("score", "verdict", "breakdown", "coverage", "keywords", "knockouts", "ats", "fixes")},
        "rating": rate(job, check, req.cities, req.profile),
        "issues": [i["title"] for i in audit_result["issues"]],
        "text_order_ok": _reads_in_order(final, read["text"]),
    }


def _reads_in_order(pdf: bytes, text: str) -> bool:
    """True when a parser that reads the file in stored order (not by page
    position) still sees the same text as the position-based reader."""
    import pymupdf
    try:
        doc = pymupdf.open(stream=pdf, filetype="pdf")
        raw = "".join(p.get_text(sort=False) for p in doc)
        flat = lambda t: re.sub(r"[^a-z0-9]+", "", t.lower())
        import difflib
        return difflib.SequenceMatcher(None, flat(raw)[:6000], flat(text)[:6000], autojunk=False).ratio() > 0.97
    except Exception:
        return True


class ResumeFileRequest(BaseModel):
    resume: Dict[str, Any]
    header: Dict[str, Any]
    filename: str = "resume"
    style: Dict[str, Any] = {}
    plan: Dict[str, Any] = {}
    contact: Dict[str, Any] = {}
    user_tex: Optional[str] = None


def _tex_for(req: ResumeFileRequest):
    if req.user_tex and "\\begin{document}" in req.user_tex:
        return latex.apply_to_tex(req.user_tex, req.resume)
    return latex.render(req.resume, req.header, req.style, req.plan, req.contact), []


def _safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", name)[:60] or "resume"


@app.post("/api/apply/resume.tex")
def apply_resume_tex(req: ResumeFileRequest):
    """LaTeX source in the original's style (or the user's own .tex with the
    accepted edits); open it in Overleaf or compile it anywhere."""
    tex, notes = _tex_for(req)
    return {"tex": tex, "notes": notes, "filename": f"{_safe_name(req.filename)}.tex", "engine": latex.can_compile()}


@app.post("/api/apply/resume.pdf")
def apply_resume_pdf(req: ResumeFileRequest):
    pdf, renderer = None, "basic"
    if req.style or req.user_tex:
        tex, _ = _tex_for(req)
        pdf, _log = latex.compile_pdf(tex)
        renderer = "latex" if pdf else "basic"
    if pdf is None:
        pdf = resume_builder.to_pdf(req.resume, req.header)
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{_safe_name(req.filename)}.pdf"', "X-Resume-Renderer": renderer,
                             "Access-Control-Expose-Headers": "X-Resume-Renderer"})


@app.post("/api/apply/resume.docx")
def apply_resume_docx(req: ResumeFileRequest):
    name = _safe_name(req.filename)
    return Response(resume_builder.to_docx(req.resume, req.header),
                    media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": f'attachment; filename="{name}.docx"'})


# ---------------------------------------------------------------------------
# Company ATS lookup
# ---------------------------------------------------------------------------

class CompanyLookupRequest(BaseModel):
    company: str
    roles: List[str] = []
    skills: List[str] = []
    years_experience: float = 0.0
    refresh: bool = False


@app.post("/api/company/lookup")
def company_lookup(req: CompanyLookupRequest):
    if not req.company.strip():
        raise HTTPException(400, "Enter a company name.")
    result = lookup_company(req.company, use_cache=not req.refresh)
    jobs = company_board_jobs(result, req.roles)
    if jobs and req.roles:
        expansion = expand_roles(req.roles)
        skills = {s: 1 for s in req.skills}
        scored = [score_job(j, req.roles, expansion, skills, req.years_experience) for j in jobs]
        scored.sort(key=lambda j: (j["title_match"] > 0, j["fit"]), reverse=True)
        jobs = scored
    result["india_jobs"] = [{k: v for k, v in j.items() if k != "description"} for j in jobs[:60]]
    result["india_jobs_total"] = len(jobs)
    if not result.get("network_listings") and (result["status"] != "verified" or not jobs):
        result["network_listings"] = company_listings(result["company"], req.roles[0] if req.roles else "")
    role = req.roles[0] if req.roles else ""
    result["search_links"] = search_links(f"{result['company']} {role}".strip())
    return result


class CompanyConfirmRequest(BaseModel):
    company: str
    ats_id: str


@app.post("/api/company/confirm")
def company_confirm(req: CompanyConfirmRequest):
    return confirm_company_ats(req.company, req.ats_id)
