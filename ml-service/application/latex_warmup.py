"""
Compiles a placeholder resume in every font family the templates support, so
Tectonic downloads and caches their packages at build time instead of on a
user's first click. Run by bin/install_tectonic.sh.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from application.latex import _FONTS, compile_pdf, render  # noqa: E402

SAMPLE = {
    "headline": "Data Analyst", "summary": "Placeholder summary used to warm the LaTeX package cache.",
    "skills": [{"group": "Tools", "items": ["Python", "SQL"]}],
    "experience": [{"company": "Example Co", "title": "Intern", "dates": "2024", "bullets": [{"text": "Built a dashboard.", "original": "Built a dashboard."}]}],
    "projects": [{"name": "Example", "subtitle": "Demo", "tech": "Python", "link": "github.com/example/demo", "link_label": "GitHub", "bullets": []}],
    "education": [{"school": "Example University", "degree": "B.Tech", "dates": "2025", "detail": "CGPA 8/10"}],
    "certifications": ["Example certificate"], "achievements": [],
}
PLAN = {"order": [{"keys": ["skills"], "heading": "Skills"}, {"keys": ["experience"], "heading": "Experience"},
                  {"keys": ["projects"], "heading": "Projects"}, {"keys": ["education"], "heading": "Education"}], "untitled_summary": True}

if __name__ == "__main__":
    failed = []
    for family in _FONTS:
        for muted in (None, "#5A6473"):  # classic and modern layouts
            style = {"family": family, "paper": "a4", "base_pt": 10.5, "bullet": "•", "muted_color": muted,
                     "heading": {"color": "#1F3D6B", "rule": True}, "name": {"align": "left" if muted else "center", "upper": True}}
            pdf, log = compile_pdf(render(SAMPLE, {"name": "Sample Name", "contact": []}, style, PLAN, {"email": "a@example.com"}))
            if not pdf:
                failed.append(family)
                print(f"{family}: {log[-300:]}", file=sys.stderr)
    print(f"Warmed {len(_FONTS) - len(set(failed))}/{len(_FONTS)} font families" + (f"; failed: {sorted(set(failed))}" if failed else ""))
