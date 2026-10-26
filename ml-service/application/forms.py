"""
Reads the real application form for a posting, so every question can be
answered before the user opens the page.

  * Greenhouse - public board API with ?questions=true
  * Lever      - the hosted /apply page (standard fields + custom cards and
                 surveys embedded as JSON)
  * Ashby      - the hosted page's public GraphQL endpoint
  * Workday, SmartRecruiters, others - forms sit behind a candidate login, so
    the standard fields every ATS asks for are returned instead.
"""
import html
import json
import re
from typing import Any, Dict, List, Optional

import requests

from jobs.boards import load_registry

_UA = {"User-Agent": "Mozilla/5.0 (GlassBox application helper)"}

# Questions whose answers can't be inferred from a resume and are the
# candidate's alone to give (or decline).
SENSITIVE = re.compile(r"gender|sex\b|pronoun|ethnic|race|racial|disab|veteran|age range|\bage\b|date of birth|religio|caste|"
                       r"marital|sexual orientation|lgbt|nationality|citizenship|criminal|pregnan|demographic", re.I)

STANDARD = [
    {"id": "first_name", "label": "First name", "type": "text", "required": True},
    {"id": "last_name", "label": "Last name", "type": "text", "required": True},
    {"id": "email", "label": "Email", "type": "text", "required": True},
    {"id": "phone", "label": "Phone", "type": "text", "required": True},
    {"id": "resume", "label": "Resume/CV", "type": "file", "required": True},
    {"id": "linkedin", "label": "LinkedIn profile", "type": "text", "required": False},
    {"id": "location", "label": "Current location", "type": "text", "required": False},
    {"id": "years", "label": "Total years of experience", "type": "text", "required": False},
    {"id": "notice", "label": "Notice period", "type": "text", "required": False},
    {"id": "current_ctc", "label": "Current CTC (annual)", "type": "text", "required": False},
    {"id": "expected_ctc", "label": "Expected CTC (annual)", "type": "text", "required": False},
]


def _field(fid: str, label: str, ftype: str, required: bool, options: Optional[List[str]] = None, description: str = "") -> Dict[str, Any]:
    label = re.sub(r"\s+", " ", html.unescape(label or "")).strip(" ✱*")
    return {"id": fid, "label": label, "type": ftype, "required": bool(required), "options": options or [],
            "description": re.sub(r"<[^>]+>", " ", html.unescape(description or "")).strip()[:400],
            "sensitive": bool(SENSITIVE.search(label))}


def _greenhouse(slug: str, native: str) -> List[Dict[str, Any]]:
    r = requests.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{native}?questions=true", headers=_UA, timeout=15)
    r.raise_for_status()
    data = r.json()
    out = []
    for q in data.get("questions", []) + data.get("location_questions", []):
        fields = q.get("fields") or []
        if not fields:
            continue
        f = fields[0]
        t = f.get("type", "")
        ftype = ("file" if t == "input_file" else "textarea" if t == "textarea" else
                 "select" if t == "multi_value_single_select" else "multiselect" if t == "multi_value_multi_select" else "text")
        out.append(_field(f.get("name") or q["label"], q["label"], ftype, q.get("required"),
                          [v["label"] for v in f.get("values") or []], q.get("description") or ""))
    for section in (data.get("compliance") or []):
        for q in section.get("questions", []):
            f = (q.get("fields") or [{}])[0]
            out.append(_field(f.get("name") or q["label"], q["label"], "select", q.get("required"),
                              [v["label"] for v in f.get("values") or []]))
    return out


def _lever(slug: str, native: str) -> List[Dict[str, Any]]:
    r = requests.get(f"https://jobs.lever.co/{slug}/{native}/apply", headers=_UA, timeout=15)
    r.raise_for_status()
    page = r.text
    out = []
    for li in re.findall(r'<li class="application-question[^"]*">(.*?)</li>', page, re.S):
        label = re.search(r'<div class="application-label[^"]*">(.*?)</div>', li, re.S)
        name = re.search(r'name="([^"]+)"', li)
        if not label or not name or name.group(1).startswith(("cards[", "surveysResponses[", "eeo[")):
            continue
        text = re.sub(r"<[^>]+>", "", label.group(1))
        ftype = "file" if 'type="file"' in li else "textarea" if "<textarea" in li else "select" if "<select" in li else "text"
        opts = [html.unescape(o) for o in re.findall(r"<option[^>]*>([^<]+)</option>", li) if o.strip() and "select" not in o.lower()]
        out.append(_field(name.group(1), text, ftype, "required" in li or "✱" in text, opts))
    # Custom questions ("cards") and surveys are JSON in hidden inputs.
    for raw in re.findall(r'<input type="hidden" value="(\{[^"]*?&quot;fields&quot;[^"]*?\})"', page):
        try:
            block = json.loads(html.unescape(raw))
        except ValueError:
            continue
        for f in block.get("fields", []):
            t = f.get("type", "")
            ftype = ("select" if t in ("multiple-choice", "dropdown") else "multiselect" if t == "multiple-select" else
                     "textarea" if t == "textarea" else "file" if t == "file-upload" else "text")
            out.append(_field(f.get("id") or f["text"], f.get("text", ""), ftype, f.get("required"),
                              [o.get("text", "") for o in f.get("options") or []], f.get("description", "")))
    return out


_ASHBY_QUERY = ("query ApiJobPosting($organizationHostedJobsPageName: String!, $jobPostingId: String!) { jobPosting("
                "organizationHostedJobsPageName: $organizationHostedJobsPageName, jobPostingId: $jobPostingId) { applicationForm "
                "{ sections { fieldEntries { ... on FormFieldEntry { isRequired descriptionHtml field } } } } } }")


def _ashby(slug: str, native: str) -> List[Dict[str, Any]]:
    r = requests.post("https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobPosting", headers=_UA, timeout=15, json={
        "operationName": "ApiJobPosting", "query": _ASHBY_QUERY,
        "variables": {"organizationHostedJobsPageName": slug, "jobPostingId": native}})
    r.raise_for_status()
    form = ((r.json().get("data") or {}).get("jobPosting") or {}).get("applicationForm") or {}
    out = []
    for section in form.get("sections") or []:
        for e in section.get("fieldEntries") or []:
            f = e.get("field") or {}
            t = f.get("type", "")
            ftype = ("file" if t == "File" else "textarea" if t == "LongText" else
                     "select" if t in ("ValueSelect", "Boolean") else "multiselect" if t == "MultiValueSelect" else "text")
            opts = [o.get("label", "") for o in (f.get("selectableValues") or [])] or (["Yes", "No"] if t == "Boolean" else [])
            out.append(_field(f.get("path") or f.get("id") or f.get("title", ""), f.get("title", ""), ftype,
                              e.get("isRequired"), opts, e.get("descriptionHtml") or ""))
    return out


_READERS = {"greenhouse": _greenhouse, "lever": _lever, "ashby": _ashby}


def application_form(job_id: str) -> Dict[str, Any]:
    """job_id is '{ats}:{slug}:{native id}', as produced by jobs.boards."""
    try:
        ats, slug, native = job_id.split(":", 2)
    except ValueError:
        return {"source": "standard", "fields": [dict(f, options=[], description="", sensitive=False) for f in STANDARD]}
    reader = _READERS.get(ats)
    if reader:
        try:
            fields = reader(slug, native)
            if fields:
                return {"source": ats, "fields": fields}
        except Exception as e:  # form changed or posting closed: fall back, but say so
            return {"source": "standard", "error": f"Could not read the live form ({str(e)[:80]})",
                    "fields": [dict(f, options=[], description="", sensitive=False) for f in STANDARD]}
    company = next((c for c in load_registry() if c["slug"] == slug and c["ats"] == ats), None)
    note = f"{company['ats'].title() if company else ats.title()} asks these after you sign in, so the usual fields are prepared."
    return {"source": "standard", "note": note, "fields": [dict(f, options=[], description="", sensitive=False) for f in STANDARD]}
