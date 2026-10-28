"""
LaTeX output for tailored resumes, typeset to look like the candidate's own.

Two routes:
  * render(): the original PDF's measured style (font family, size, paper,
    margins, accent colour, name layout, heading rules, bullet glyph, link
    colour) and its own section order and heading names are reproduced in a
    LaTeX document filled with the tailored content.
  * apply_to_tex(): when the candidate has their .tex (Overleaf: Menu ->
    Download -> Source), only the changed bullets and skill lines are swapped
    inside it, so every macro and spacing stays exactly theirs.

The source compiles on Overleaf (pdfLaTeX) and with Tectonic (XeTeX). When a
Tectonic binary is installed, compile() returns the PDF.
"""
import difflib
import os
import re
import shutil
import subprocess
import tempfile
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Escaping
# ---------------------------------------------------------------------------

_TEX_SPECIAL = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
                "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
_UNICODE = {"₹": "Rs.~", "\u2011": "-", "\u2010": "-", "\u2212": "-", "\u00a0": "~", "\u200b": "", "→": r"$\rightarrow$",
            "–": "--", "—": "---", "“": "``", "”": "''", "‘": "`", "’": "'", "…": r"\ldots{}", "•": r"\textbullet{}", "✓": ""}


def esc(text: Any) -> str:
    s = str(text or "")
    s = "".join(_TEX_SPECIAL.get(ch, ch) for ch in s)
    for k, v in _UNICODE.items():
        s = s.replace(k, v)
    return s


def _url(u: str) -> str:
    """A link target that can't break out of \\href: URL characters only, with
    the two TeX-special ones hyperref accepts escaped."""
    u = re.sub(r"[^A-Za-z0-9:/?=&._~+@!,;*()%#-]", "", (u or "").strip())
    u = u if re.match(r"^(https?://|mailto:)", u) else f"https://{u}"
    return u.replace("%", r"\%").replace("#", r"\#")


def _num(v: Any, default: float, lo: float, hi: float) -> float:
    """A style number from the client, clamped; anything else becomes the default."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return min(hi, max(lo, f)) if f == f else default


def _short(u: str) -> str:
    return re.sub(r"^(https?://)?(www\.)?", "", (u or "").strip()).rstrip("/")


# ---------------------------------------------------------------------------
# The original's section order and heading names
# ---------------------------------------------------------------------------

_SECTION_KEYS = [
    ("summary", r"\b(summary|profile|objective|about me)\b"),
    ("skills", r"\b(skills?|competenc|tech(nical)? stack|technologies|toolkit|tools)\b"),
    ("experience", r"\b(experience|employment|work history|internships?)\b"),
    ("projects", r"\b(projects?|portfolio)\b"),
    ("education", r"\b(education|academic)"),
    ("certifications", r"\b(certifications?|courses|licen[cs]es?)\b"),
    ("achievements", r"\b(achievements?|awards?|honou?rs)\b"),
]
DEFAULT_ORDER = ["summary", "experience", "projects", "skills", "education", "certifications", "achievements"]


def section_plan(resume_text: str) -> Dict[str, Any]:
    """[(keys, heading as written)] in the original's order, plus whether it
    opens with an untitled summary paragraph."""
    order: List[Dict[str, Any]] = []
    seen = set()
    first_heading_at = None
    lines = (resume_text or "").split("\n")
    for i, raw in enumerate(lines):
        line = raw.strip().strip(":").strip()
        if not line or len(line.split()) > 5 or len(line) > 45 or line.endswith(".") or "@" in line or "|" in line:
            continue
        keys = [k for k, pat in _SECTION_KEYS if re.search(pat, line, re.I) and k not in seen]
        if not keys:
            continue
        # A heading is a short line that isn't a sentence; "Data Analyst Intern" isn't one.
        if not (line.istitle() or line.isupper() or re.fullmatch(r"[A-Z][\w&/ -]+", line)) or re.search(r"\b(intern|engineer|analyst|manager)\b", line, re.I):
            continue
        first_heading_at = first_heading_at if first_heading_at is not None else i
        seen.update(keys)
        order.append({"keys": keys, "heading": line})
    preamble = " ".join(lines[: first_heading_at or 0])
    untitled_summary = "summary" not in seen and len(re.findall(r"\w+", preamble)) > 45
    return {"order": order, "untitled_summary": untitled_summary}


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

_FONTS = {
    "computer_modern": r"\ifPDFTeX\usepackage{lmodern}\fi",
    "carlito": r"\usepackage[sfdefault,lf]{carlito}",
    "lato": r"\usepackage[default]{lato}",
    "source_sans": r"\usepackage[default]{sourcesanspro}",
    "roboto": r"\usepackage[sfdefault]{roboto}",
    "open_sans": r"\usepackage[default]{opensans}",
    "fira_sans": r"\usepackage[sfdefault]{FiraSans}",
    "helvetica": "\\usepackage{tgheros}\n\\renewcommand{\\familydefault}{\\sfdefault}",
    "times": r"\usepackage{tgtermes}",
    "garamond": r"\usepackage{ebgaramond}",
    "palatino": r"\usepackage{tgpagella}",
    "charter": r"\usepackage{XCharter}",
    "caladea": r"\usepackage{caladea}",
    "montserrat": r"\usepackage[defaultfam,tabular,lining]{montserrat}",
    "raleway": r"\usepackage[default]{raleway}",
}
_BULLETS = {"•": r"\textbullet", "●": r"\textbullet", "–": r"\textendash", "-": r"\textendash", "—": r"\textemdash",
            "◦": r"$\circ$", "▪": r"$\blacksquare$", "■": r"$\blacksquare$", "‣": r"\textbullet"}
_SEPS = {"|": r"\,\textbar\,", "—": r" --- ", "•": r" \textbullet{} ", "·": r" \textperiodcentered{} ", "/": " / "}


def _color(name: str, hexcolor: Optional[str], fallback: str) -> str:
    h = (hexcolor or fallback).lstrip("#").upper()
    if not re.fullmatch(r"[0-9A-F]{6}", h):
        h = fallback.lstrip("#")
    return f"\\definecolor{{{name}}}{{HTML}}{{{h}}}"


def _bullets(items: List[Any], label: str) -> List[str]:
    texts = [b.get("text") if isinstance(b, dict) else b for b in items or []]
    texts = [t for t in texts if t]
    if not texts:
        return []
    return [f"\\begin{{itemize}}[label={label},leftmargin=1.1em,labelsep=0.45em,itemsep=1pt,topsep=1pt,parsep=0pt]"] + \
           [f"  \\item {esc(t)}" for t in texts] + [r"\end{itemize}"]


def render(data: Dict[str, Any], header: Dict[str, Any], style: Dict[str, Any], plan: Dict[str, Any],
           contact: Optional[Dict[str, Any]] = None) -> str:
    style = style or {}
    contact = contact or {}
    family = style.get("family") or "computer_modern"
    base = _num(style.get("base_pt"), 10.5, 8, 14)
    cls_pt = 10 if base < 10.75 else 11 if base < 11.75 else 12
    paper = "a4paper" if style.get("paper") == "a4" else "letterpaper"
    m = style.get("margins_pt") if isinstance(style.get("margins_pt"), dict) else {}
    left, right = _num(m.get("left"), 50, 28, 120), _num(m.get("right"), 50, 28, 120)
    top = _num(m.get("top"), 36, 24, 120) - 6
    name = style.get("name") if isinstance(style.get("name"), dict) else {}
    head = style.get("heading") if isinstance(style.get("heading"), dict) else {}
    modern = bool(style.get("muted_color"))  # a secondary grey for dates/tech marks the "modern" layout
    bullet = _BULLETS.get(style.get("bullet") or "•", r"\textbullet")
    sep = _SEPS.get(style.get("contact_sep") or "|", r"\,\textbar\,")
    link = style.get("link_color")
    link_is_text = not link or link == style.get("body_color")
    head_pt = _num(head.get("size_pt"), base + 1.5, 8, 20)
    upper_cmd = "\\MakeUppercase" if head.get("upper") else ""
    bold_cmd = "\\bfseries" if name.get("bold", True) else ""
    name_pt = _num(name.get("size_pt"), 20, 10, 36)

    pre = [
        f"\\documentclass[{paper},{cls_pt}pt]{{article}}",
        f"\\usepackage[left={left}pt,right={right}pt,top={top}pt,bottom=36pt]{{geometry}}",
        r"\usepackage{iftex}",
        r"\ifPDFTeX\usepackage[T1]{fontenc}\usepackage[utf8]{inputenc}\fi",
        _FONTS.get(family, _FONTS["computer_modern"]),
        r"\usepackage{xcolor}",
        _color("bodytext", style.get("body_color"), "#000000"),
        _color("accent", head.get("color"), "#000000"),
        _color("namecolor", name.get("color"), "#000000"),
        _color("rulecolor", head.get("rule_color") or head.get("color"), "#000000"),
        _color("muted", style.get("muted_color"), "#555555"),
        _color("linkcolor", link, "#000000"),
        r"\usepackage{enumitem}",
        r"\usepackage{titlesec}",
        r"\usepackage{amssymb}",
        r"\usepackage[hidelinks]{hyperref}" if link_is_text else r"\usepackage[colorlinks=true,urlcolor=linkcolor,linkcolor=linkcolor]{hyperref}",
        r"\pagestyle{empty}",
        r"\setlength{\parindent}{0pt}",
        r"\raggedright",
        (f"\\titleformat{{\\section}}{{\\color{{accent}}\\fontsize{{{head_pt}}}{{{head_pt * 1.2:.1f}}}"
         f"\\selectfont\\bfseries{upper_cmd}}}{{}}{{0em}}{{}}"
         + (f"[{{\\color{{rulecolor}}\\titlerule[{_num(head.get('rule_pt'), 0.4, 0.1, 3)}pt]}}]" if head.get("rule", True) else "")),
        r"\titlespacing*{\section}{0pt}{7pt}{4pt}",
        r"\begin{document}",
        f"\\fontsize{{{base}}}{{{base * 1.22:.1f}}}\\selectfont\\color{{bodytext}}",
    ]

    # Header
    nm = esc(header.get("name") or "")
    nm = nm.upper() if name.get("upper") else nm
    name_tex = f"{{\\color{{namecolor}}\\fontsize{{{name_pt}}}{{{name_pt * 1.15:.1f}}}\\selectfont{bold_cmd} {nm}}}"
    items = []
    for k in ("phone", "email", "linkedin", "github"):
        v = contact.get(k)
        if not v:
            continue
        if k == "phone":
            items.append(esc(v))
        elif k == "email":
            items.append(f"\\href{{{_url('mailto:' + str(v))}}}{{{esc(v)}}}")
        else:
            items.append(f"\\href{{{_url(v)}}}{{{esc(_short(v))}}}")
    location = name.get("beside") or next((c for c in header.get("contact") or [] if "India" in c or "," in c and "@" not in c), "")
    body: List[str] = []
    if name.get("align") == "left":
        body.append(f"{name_tex}\\hfill{{\\color{{muted}}\\small {esc(location)}}}\\\\[3pt]")
        body.append(f"{{\\small {sep.join(items)}}}\\par")
    else:
        body.append(r"\begin{center}")
        body.append(f"{name_tex}\\\\[4pt]")
        if location:
            body.append(f"{esc(location)}\\\\[1pt]")
        body.append(f"{sep.join(items)}")
        body.append(r"\end{center}")
        body.append(r"\vspace{-6pt}")

    planned = plan.get("order") or []
    has_summary_heading = any("summary" in s["keys"] for s in planned)
    if data.get("headline") and (plan.get("untitled_summary") or has_summary_heading):
        body.append(f"\\vspace{{4pt}}{{\\bfseries {esc(data['headline'])}}}\\par")
    if data.get("summary") and plan.get("untitled_summary"):
        body.append(f"\\vspace{{2pt}}{esc(data['summary'])}\\par")

    def entry(left_bold: str, right: str, sub_left: str = "", sub_right: str = "") -> List[str]:
        if modern:
            line = f"\\textbf{{{left_bold}}}" + (f" \\,---\\, {{\\color{{muted}}{sub_left}}}" if sub_left else "")
            return [f"{line}\\hfill{{\\color{{muted}}\\small {right}}}\\par"]
        out = [f"\\textbf{{{left_bold}}}\\hfill\\textbf{{{right}}}\\\\"]
        if sub_left or sub_right:
            out.append(f"\\textit{{{sub_left}}}\\hfill\\textit{{{sub_right}}}\\par")
        else:
            out[-1] = out[-1][:-2] + r"\par"
        return out

    def section_body(key: str) -> List[str]:
        out: List[str] = []
        if key == "summary" and data.get("summary"):
            out.append(esc(data["summary"]) + r"\par")
        elif key == "skills":
            groups = [g for g in data.get("skills") or [] if g.get("items")]
            for i, g in enumerate(groups):
                out.append(f"\\textbf{{{esc(g.get('group') or 'Skills')}:}} {esc(', '.join(g['items']))}\\par" + ("\\vspace{2pt}" if i < len(groups) - 1 else ""))
        elif key == "experience":
            for e in data.get("experience") or []:
                if modern:
                    right = " \\,\\textbar\\, ".join(esc(x) for x in (e.get("location"), e.get("dates")) if x)
                    out += entry(f"{esc(e.get('company', ''))} \\,---\\, {esc(e.get('title', ''))}", right)
                else:
                    out += entry(esc(e.get("company", "")), esc(e.get("dates") or ""), esc(e.get("title") or ""), esc(e.get("location") or ""))
                out += _bullets(e.get("bullets"), bullet) + [r"\vspace{3pt}"]
        elif key == "projects":
            for p in data.get("projects") or []:
                label = esc(p.get("link_label") or _short(p.get("link") or ""))
                link_tex = f"\\href{{{_url(p['link'])}}}{{{label}}}" if p.get("link") else ""
                title = f"\\textbf{{{esc(p.get('name', ''))}}}"
                if modern:
                    sub = f" \\,---\\, {{\\color{{muted}}{esc(p['subtitle'])}}}" if p.get("subtitle") else ""
                    out.append(f"{title}{sub}\\hfill{{\\footnotesize {link_tex}}}\\par")
                    if p.get("tech"):
                        out.append(f"{{\\footnotesize\\color{{muted}} {esc(p['tech'])}}}\\par")
                else:
                    sub = f" -- {esc(p['subtitle'])}" if p.get("subtitle") else ""
                    tech = f" \\textbar{{}} \\textit{{{esc(p['tech'])}}}" if p.get("tech") else ""
                    out.append(f"\\textbf{{{esc(p.get('name', ''))}{sub}}}{tech}\\hfill{{\\small {link_tex}}}\\par")
                out += _bullets(p.get("bullets"), bullet) + [r"\vspace{3pt}"]
        elif key == "education":
            for ed in data.get("education") or []:
                if modern:
                    right = " \\,\\textbar\\, ".join(esc(x) for x in (ed.get("dates"), ed.get("detail") if len(ed.get("detail") or "") < 25 else None) if x)
                    out += entry(" \\,---\\, ".join(esc(x) for x in (ed.get("school"), ed.get("degree")) if x), right)
                    if ed.get("detail") and len(ed["detail"]) >= 25:
                        out.append(f"{{\\small {esc(ed['detail'])}}}\\par")
                else:
                    out += entry(esc(ed.get("school") or ed.get("degree") or ""), esc(ed.get("dates") or ""),
                                 esc(ed.get("degree") if ed.get("school") else ""), esc(ed.get("location") or ""))
                    if ed.get("detail"):
                        out += _bullets([ed["detail"]], bullet)
        elif key in ("certifications", "achievements"):
            vals = [c for c in data.get(key) or [] if c]
            if vals:
                label = "Certifications" if key == "certifications" else "Achievements"
                out.append(f"{{\\small\\textbf{{{label}:}} {sep.join(esc(c) for c in vals)}}}\\par")
        return out

    rendered = set()
    for sec in planned:
        chunk: List[str] = []
        for k in sec["keys"]:
            if k == "summary" and plan.get("untitled_summary"):
                continue
            chunk += section_body(k)
            rendered.add(k)
        if chunk:
            body.append(f"\\section*{{{esc(sec['heading'])}}}")
            body += chunk
    defaults = {"summary": "Summary", "skills": "Skills", "experience": "Experience", "projects": "Projects", "education": "Education",
                "certifications": "Certifications", "achievements": "Achievements"}
    for k in DEFAULT_ORDER:
        if k in rendered or (k == "summary" and plan.get("untitled_summary")) or (k == "summary" and not has_summary_heading):
            continue
        chunk = section_body(k)
        if chunk:
            body.append(f"\\section*{{{defaults[k]}}}")
            body += chunk
    return "\n".join(pre + body + [r"\end{document}", ""])


# ---------------------------------------------------------------------------
# Editing the candidate's own .tex
# ---------------------------------------------------------------------------

def _plain(tex: str) -> str:
    """LaTeX fragment -> comparable plain text."""
    t = re.sub(r"%.*", "", tex)
    t = re.sub(r"\\href\{[^}]*\}\{([^}]*)\}", r"\1", t)
    t = re.sub(r"\\[a-zA-Z@]+\*?(\[[^\]]*\])?", " ", t)
    t = t.replace("{", "").replace("}", "").replace("~", " ").replace("--", "-")
    t = re.sub(r"\\(.)", r"\1", t)
    return re.sub(r"\s+", " ", t).strip().lower()


def _norm(text: str) -> str:
    t = (text or "").replace("–", "-").replace("—", "-").replace("’", "'")
    return re.sub(r"\s+", " ", t).strip().lower()


def apply_to_tex(tex: str, data: Dict[str, Any]) -> Tuple[str, List[str]]:
    """Swaps changed bullets (and reordered skill lines) inside the user's own
    .tex. Returns (new tex, notes about anything that couldn't be placed)."""
    changes = []
    for sec in ("experience", "projects"):
        for item in data.get(sec) or []:
            for b in item.get("bullets") or []:
                if isinstance(b, dict) and b.get("original") and _norm(b["original"]) != _norm(b.get("text")):
                    changes.append((b["original"], b["text"]))
    notes: List[str] = []
    out = tex
    # \item bodies run to the next \item or the end of the list.
    items = list(re.finditer(r"\\item(?:\[[^\]]*\])?\s*(.*?)(?=\\item\b|\\end\{itemize\}|\\resumeItemListEnd|\Z)", out, re.S))
    spans = [(m.start(1), m.end(1), _plain(m.group(1))) for m in items]
    replacements = []
    for original, new in changes:
        target = _norm(original)
        best, score = None, 0.0
        for start, end, plain in spans:
            r = difflib.SequenceMatcher(None, target, plain).ratio()
            if r > score:
                best, score = (start, end), r
        if best and score >= 0.8:
            body = out[best[0]:best[1]]
            trailing = re.search(r"\s*$", body).group(0)
            # Keep a wrapper like \resumeItem{...} intact: replace only inside the braces.
            wrapped = re.match(r"^(\s*\{)(.*)(\}\s*)$", body, re.S)
            new_body = f"{wrapped.group(1)}{esc(new)}{wrapped.group(3)}" if wrapped else esc(new) + trailing
            replacements.append((best[0], best[1], new_body))
        else:
            notes.append(f"Couldn't find this bullet in your .tex, so it's unchanged: “{original[:70]}…”")
    for start, end, new_body in sorted(replacements, reverse=True):
        out = out[:start] + new_body + out[end:]
    # Skill lines: "\textbf{Group:} a, b, c" keeps its label; the list is replaced.
    for g in data.get("skills") or []:
        label = re.escape(g.get("group") or "")
        if not label or not g.get("items"):
            continue
        m = re.search(r"(\\textbf\{\s*" + label + r"\s*:?\s*\}\s*:?\s*\{?\s*:?\s*)([^\n\\}]+)", out)
        if m:
            out = out[:m.start(2)] + esc(", ".join(g["items"])) + out[m.end(2):]
    return out, notes


# ---------------------------------------------------------------------------
# Compiling
# ---------------------------------------------------------------------------

def _tectonic() -> Optional[str]:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for cand in (os.environ.get("TECTONIC_BIN"), os.path.join(here, ".tectonic", "tectonic"), shutil.which("tectonic")):
        if cand and os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return None


def can_compile() -> bool:
    return _tectonic() is not None


def compile_pdf(tex: str, timeout: int = 150) -> Tuple[Optional[bytes], str]:
    """(pdf bytes or None, log tail)."""
    exe = _tectonic()
    if not exe:
        return None, "No LaTeX engine installed (run ml-service/bin/install_tectonic.sh)."
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # Only what Tectonic needs: the service's API keys stay out of the compiler's
    # reach, and untrusted mode keeps shell escape off whatever the source says.
    env = {k: os.environ[k] for k in ("PATH", "HOME", "LANG", "TMPDIR") if k in os.environ}
    env["TECTONIC_CACHE_DIR"] = os.environ.get("TECTONIC_CACHE_DIR") or os.path.join(here, ".tectonic", "cache")
    env["TECTONIC_UNTRUSTED_MODE"] = "1"
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "resume.tex")
        with open(src, "w", encoding="utf-8") as f:
            f.write(tex)
        try:
            proc = subprocess.run([exe, "-X", "compile", "--outdir", tmp, src], capture_output=True, text=True, timeout=timeout, env=env)
        except subprocess.TimeoutExpired:
            return None, "LaTeX timed out."
        pdf = os.path.join(tmp, "resume.pdf")
        if proc.returncode == 0 and os.path.exists(pdf):
            with open(pdf, "rb") as f:
                return f.read(), ""
        return None, (proc.stderr or proc.stdout)[-1500:]
