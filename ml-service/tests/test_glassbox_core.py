import os
import sys
import unittest
import datetime
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ats.detector import detect_from_url, detect_from_html, _slug_variants
from ats.profiles import get_profile
from jobs.boards import india_cities_in, is_india
from jobs.discovery import title_match, title_level
from matching.ats_check import years_required, degree_rank, run_check
from matching.skills_lexicon import find_skills, term_in_text, canonicalize
from parsing.profile_extractor import compute_experience_years, detect_degree, experience_from_entries, _split_roles, _work_section
from parsing.resume_reader import read_text, audit, parse_score, detect_sections

RESUME = """Arjun Mehta
Bengaluru | arjun@example.com | +91 91234 56789
Summary
Backend engineer building Java microservices.
Experience
Software Engineer, Razorpay   Jun 2023 - Present
- Built reconciliation services in Java and Spring Boot handling 2M transactions per day
- Cut p99 latency by 35% with Redis caching and PostgreSQL tuning
Software Engineering Intern, Zeta   Jan 2023 - May 2023
- Wrote Python tests with pytest
Education
B.Tech in Computer Science, NIT Trichy, 2023
Skills
Java, Python, Go, SQL, Spring Boot, Kafka, Docker, Kubernetes, AWS
"""

JD = """Backend Engineer
Requirements:
- 3+ years of experience building backend services in Java
- Strong with Spring Boot, Kafka and PostgreSQL
- Experience with Docker and Kubernetes on AWS
- B.Tech or equivalent in Computer Science
Nice to have:
- Experience with Terraform and gRPC
"""


class TestSkillLexicon(unittest.TestCase):
    def test_aliases_map_to_one_skill(self):
        found = find_skills("ReactJS, k8s, Amazon Web Services, Node.js")
        self.assertIn("React", found)
        self.assertIn("Kubernetes", found)
        self.assertIn("AWS", found)
        self.assertNotIn("JavaScript", found, "'.js' suffix must not count as JavaScript")

    def test_ambiguous_short_names_need_context(self):
        self.assertNotIn("Go", find_skills("We go further every day."))
        self.assertNotIn("R", find_skills("Our R&D team"))
        self.assertIn("Go", find_skills("Skills: Python, Go, SQL"))

    def test_term_matching(self):
        self.assertEqual(canonicalize("ReactJS"), "React")
        self.assertGreater(term_in_text("stakeholder management", "Led stakeholder management for launches"), 0)
        self.assertEqual(term_in_text("Terraform", RESUME), 0)


class TestResumeReading(unittest.TestCase):
    def test_experience_from_date_ranges(self):
        years, ranges = compute_experience_years(RESUME, now=datetime.date(2026, 10, 1))
        self.assertEqual(ranges, 2)
        self.assertAlmostEqual(years, 3.6, delta=0.2)

    def test_sections_and_creative_headers(self):
        s = detect_sections("SUPERPOWERS\nPython\nMY JOURNEY\nEngineer\nEducation\nB.Tech")
        self.assertIn("education", s["found"])
        self.assertEqual({n["suggested"] for n in s["nonstandard"]}, {"Skills", "Experience"})

    def test_audit_flags_personal_details_and_strict_parsers_penalise_more(self):
        text = "WHAT I'VE BUILT\nApp\nDate of Birth: 01/01/2000\nMarital Status: Single\n" + RESUME
        a = audit(read_text(text))
        keys = {i["key"] for i in a["issues"]}
        self.assertIn("personal_details", keys)
        self.assertIn("nonstandard_header", keys)
        self.assertLess(parse_score(a, get_profile("taleo"))["score"], parse_score(a, get_profile("lever"))["score"])

    def test_degree_detection(self):
        self.assertEqual(detect_degree(RESUME), "B.Tech / B.E.")
        self.assertEqual(degree_rank("B.Tech/M.Tech in Computer Science"), 1)
        self.assertEqual(degree_rank("Master's degree required"), 2)


class TestJobsAndAts(unittest.TestCase):
    def test_india_locations(self):
        self.assertEqual(india_cities_in("Gurugram, Haryana, India"), ["Delhi NCR"])
        self.assertTrue(is_india("Bangalore, KA"))
        self.assertFalse(is_india("Remote in US"))

    def test_title_matching_and_levels(self):
        exp = {"include": ["backend engineer", "software engineer"], "exclude": ["sales engineer"]}
        self.assertEqual(title_match("Senior Backend Engineer", ["Backend Engineer"], exp), 1.0)
        self.assertEqual(title_match("Sales Engineer", ["Backend Engineer"], exp), 0.0)
        self.assertEqual(title_level("Software Engineering Intern"), 0)
        self.assertEqual(title_level("Staff Engineer"), 4)

    def test_years_required_prefers_title_and_overall_requirement(self):
        self.assertEqual(years_required("2+ years of experience with Kafka", "Engineer (11-15 years exp)"), 11)
        self.assertEqual(years_required("5+ years of professional experience. 2+ years experience with Kafka."), 5)

    def test_ats_fingerprints(self):
        self.assertEqual(detect_from_url("https://jobs.lever.co/acme/123")["id"], "lever")
        self.assertEqual(detect_from_url("https://acme.wd5.myworkdayjobs.com/External")["id"], "workday")
        self.assertEqual(detect_from_url("https://zepto.darwinbox.in/ms/candidate/careers")["id"], "darwinbox")
        self.assertEqual(detect_from_html('<script src="https://boards.greenhouse.io/embed/job_board/js?for=acme">')[0]["id"], "greenhouse")
        self.assertIsNone(detect_from_url("https://example.com/careers"))
        self.assertEqual(_slug_variants("Acme Technologies Pvt Ltd")[0], "acme")

    @patch("matching.ats_check.llm_json", return_value=None)
    def test_pass_check_offline(self, _):
        a = audit(read_text(RESUME))
        result = run_check(RESUME, {"years_experience": 3.6, "education": {"degree": "B.Tech / B.E."}}, a, JD, "greenhouse", "Backend Engineer", "Acme")
        must = {r["term"]: r["status"] for r in result["keywords"]["must_have"]}
        self.assertEqual(must.get("Java"), "matched")
        self.assertIn(result["verdict"], ("pass", "borderline"))
        self.assertFalse(any(k["type"] == "experience" for k in result["knockouts"]))
        self.assertFalse(any(k["type"] == "degree" for k in result["knockouts"]))


class TestFresherExperience(unittest.TestCase):
    """A 2025 graduate with one internship was read as 4.9 years, mid level:
    degree and fellowship dates were summed and 'Jul–Nov2024' wasn't parsed."""
    TEXT = ("Experience\nBosch Automotive Electronics — Data Analyst Intern   Bengaluru | Jul–Nov2024\n"
            "• Built Tableau dashboards\nEducation&Certifications\n"
            "Vellore Institute of Technology — B.Tech, CSE   2021–2025 | GPA 7.7/10\n"
            "NextLeap — Product Management Fellowship, Cohort 47   Mar–Jun2026\n")

    def test_shared_year_range_and_education_excluded(self):
        now = datetime.date(2026, 10, 1)
        self.assertNotIn("2021", _work_section(self.TEXT))
        self.assertEqual(compute_experience_years(self.TEXT, _work_section(self.TEXT), now=now), (0.4, 1))
        # Even without a work section, degree and fellowship lines are skipped.
        self.assertEqual(compute_experience_years(self.TEXT, now=now), (0.4, 1))

    def test_job_entries_split_internships(self):
        out = experience_from_entries([
            {"title": "Data Analyst Intern", "start": "Jul 2024", "end": "Nov 2024", "is_internship": True},
            {"title": "Analyst", "start": "Jan 2025", "end": "Present"},
        ], now=datetime.date(2026, 1, 1))
        self.assertEqual(out, {"full_time": 1.1, "internship": 0.4})

    def test_headline_split_into_roles(self):
        # "AI Product" names a field, not a job, so the real titles fill the search slots.
        self.assertEqual(_split_roles(["AI Product | Associate Product Manager, Product Analyst"]),
                         ["Associate Product Manager", "Product Analyst"])

    def test_ambiguous_aliases(self):
        self.assertEqual(find_skills("Sentence Transformers, n8n onboarding, faster monitoring"), {})


class TestLatex(unittest.TestCase):
    def test_section_plan_keeps_own_headings(self):
        from application.latex import section_plan
        plan = section_plan("NAME\nAI Product | APM\n" + "word " * 50 + "\nSkills\nx\nAI Product Portfolio\ny\n"
                            "Experience\nBosch — Data Analyst Intern\nEducation & Certifications\nVIT")
        self.assertEqual([s["heading"] for s in plan["order"]], ["Skills", "AI Product Portfolio", "Experience", "Education & Certifications"])
        self.assertEqual(plan["order"][3]["keys"], ["education", "certifications"])
        self.assertTrue(plan["untitled_summary"])

    def test_render_escapes_and_styles(self):
        from application.latex import render
        tex = render({"skills": [{"group": "Data & AI", "items": ["C++", "R&D"]}],
                      "experience": [{"company": "A_B", "title": "Intern", "dates": "2024", "bullets": [{"text": "Cut cost 50% & time", "original": "x"}]}]},
                     {"name": "Riya Sen", "contact": []},
                     {"family": "carlito", "paper": "a4", "base_pt": 10.5, "bullet": "•", "heading": {"color": "#1F3D6B", "rule": True},
                      "name": {"upper": True, "align": "left"}, "muted_color": "#5A6473"},
                     {"order": [{"keys": ["experience"], "heading": "Work"}, {"keys": ["skills"], "heading": "Skills"}], "untitled_summary": False},
                     {"email": "r@x.in"})
        self.assertIn("carlito", tex)
        self.assertIn("a4paper", tex)
        self.assertIn(r"50\% \& time", tex)
        self.assertIn(r"A\_B", tex)
        self.assertIn("RIYA SEN", tex)
        self.assertLess(tex.index("section*{Work}"), tex.index("section*{Skills}"))

    def test_apply_to_own_tex(self):
        from application.latex import apply_to_tex
        tex = "\\begin{itemize}\n\\item Built \\textbf{Tableau} dashboards for 4 teams.\n\\item Other.\n\\end{itemize}"
        out, notes = apply_to_tex(tex, {"experience": [{"bullets": [
            {"original": "Built Tableau dashboards for 4 teams.", "text": "Built data visualization dashboards in Tableau for 4 teams."}]}]})
        self.assertIn("data visualization dashboards", out)
        self.assertIn("\\item Other.", out)
        self.assertEqual(notes, [])


class TestPdfInPlaceEdit(unittest.TestCase):
    """Edits go into the candidate's own PDF: same font and baselines, nothing
    else moves, and the text stays in reading order for stream-order parsers."""

    def _pdf(self):
        import pymupdf
        doc = pymupdf.open()
        page = doc.new_page(width=612, height=792)
        lines = ["Experience", "- Built dashboards in Tableau and automated reports using Python and PostgreSQL",
                 "  for the plant operations team every week.", "- Second bullet stays exactly as it was.", "Education"]
        y = 80
        for i, text in enumerate(lines):
            if text.startswith("- "):
                page.insert_text((40, y), "-", fontname="helv", fontsize=10)
                page.insert_text((52, y), text[2:], fontname="helv", fontsize=10)
            elif text.startswith("  "):
                page.insert_text((52, y), text.strip(), fontname="helv", fontsize=10)
            else:
                page.insert_text((40, y), text, fontname="helv", fontsize=11)
            y += 14
        return doc.tobytes()

    def test_edit_in_place_and_in_order(self):
        import pymupdf
        from application.pdf_edit import apply_edits
        src = self._pdf()
        original = "Built dashboards in Tableau and automated reports using Python and PostgreSQL for the plant operations team every week."
        pdf, report = apply_edits(src, [{"id": "a", "original": original, "kind": "bullet",
                                         "text": original.replace("PostgreSQL", "PostgreSQL (SQL)")}])
        self.assertEqual(report, [{"id": "a", "applied": True}])
        page = pymupdf.open(stream=pdf, filetype="pdf")[0]
        stored = page.get_text(sort=False)
        self.assertIn("PostgreSQL (SQL)", stored.replace("\n", " "))
        # Stored order still reads top to bottom.
        self.assertLess(stored.index("Experience"), stored.index("Built"))
        self.assertLess(stored.index("Built"), stored.index("Second bullet"))
        self.assertLess(stored.index("Second bullet"), stored.index("Education"))
        # Untouched lines keep their exact position.
        before = {w[4]: w[:2] for w in pymupdf.open(stream=src, filetype="pdf")[0].get_text("words")}
        after = {w[4]: w[:2] for w in page.get_text("words")}
        self.assertEqual(before["Second"], after["Second"])
        self.assertEqual(before["Education"], after["Education"])

    def test_edit_that_needs_a_new_line_is_refused(self):
        from application.pdf_edit import apply_edits
        original = "Built dashboards in Tableau and automated reports using Python and PostgreSQL for the plant operations team every week."
        pdf, report = apply_edits(self._pdf(), [{"id": "a", "original": original, "kind": "bullet",
                                                 "text": original + " " + "Added a very long tail of extra words " * 4}])
        self.assertIsNone(pdf)
        self.assertFalse(report[0]["applied"])
        self.assertIn("extra line", report[0]["reason"])


class TestApplyFlow(unittest.TestCase):
    CHECK = {"score": 70, "verdict": "pass", "breakdown": {"keywords": 70},
             "coverage": {"must_matched": 7, "must_total": 8, "nice_matched": 3, "nice_total": 4},
             "knockouts": [], "ats": {"name": "Greenhouse"}}

    def test_rating_threshold_and_caps(self):
        from application.rating import rate
        good = rate({"title": "Data Analyst", "title_match": 1.0, "cities": ["Bengaluru"]}, self.CHECK, ["Bengaluru"],
                    {"screening_years": 1.5})
        self.assertGreaterEqual(good["score"], 4.0)
        self.assertTrue(good["apply"])
        senior = rate({"title": "Senior Data Analyst", "title_match": 1.0, "cities": ["Bengaluru"]},
                      {**self.CHECK, "knockouts": [{"type": "experience", "severity": "high", "detail": "Asks for 5+ years"}]},
                      ["Bengaluru"], {"screening_years": 0.2})
        self.assertLessEqual(senior["score"], 3.4)
        student = rate({"title": "Data Analyst", "title_match": 1.0, "cities": ["Bengaluru"]}, self.CHECK, ["Bengaluru"],
                       {"screening_years": 0.2, "student": True})
        self.assertLess(student["score"], 4.0)

    def test_answers_never_guess_sensitive_or_salary(self):
        from application.answers import answer_form
        fields = [{"id": "g", "label": "Gender", "type": "select", "required": True, "options": ["Male", "Female"], "sensitive": True},
                  {"id": "c", "label": "Expected CTC", "type": "text", "required": True, "options": [], "sensitive": False},
                  {"id": "e", "label": "Email", "type": "text", "required": True, "options": [], "sensitive": False},
                  {"id": "r", "label": "Resume/CV", "type": "file", "required": True, "options": [], "sensitive": False}]
        with patch("application.answers.llm_json", return_value=None):
            rows = {r["id"]: r for r in answer_form(fields, "resume", {"name": "A B"}, {"email": "a@b.co"}, {})}
        self.assertEqual(rows["g"]["status"], "sensitive")
        self.assertIsNone(rows["g"]["value"])
        self.assertEqual(rows["c"]["status"], "needs_you")
        self.assertEqual(rows["e"]["value"], "a@b.co")
        self.assertEqual(rows["r"]["status"], "file")
        with patch("application.answers.llm_json", return_value=None):
            saved = answer_form(fields, "resume", {}, {}, {}, saved={"expected_ctc": "8 LPA"})
        self.assertEqual(next(r for r in saved if r["id"] == "c")["value"], "8 LPA")

    def test_fact_guard(self):
        from application.resume_builder import _guard, _normalize
        src = "Python, PostgreSQL. Built dashboards used by 4 teams."
        data = _normalize({"skills": [{"group": "x", "items": ["Python", "SQL", "Power BI"]}],
                           "experience": [{"company": "Acme", "bullets": []}],
                           "projects": [{"name": "P", "bullets": [
                               {"text": "Built dashboards used by 40 teams", "source": "Built dashboards used by 4 teams."}]}]})
        notes = _guard(data, src)
        self.assertEqual(data["skills"][0]["items"], ["Python", "SQL"])  # SQL is implied by PostgreSQL
        self.assertEqual(data["experience"], [])  # Acme isn't on the resume
        self.assertEqual([b["text"] for b in data["projects"][0]["bullets"]], ["Built dashboards used by 4 teams."])
        self.assertTrue(any("Power BI" in n for n in notes))


class DegreeGapTests(unittest.TestCase):
    def test_postgrad_titles_rank_lower_for_bachelors(self):
        from jobs.discovery import _degree_gap
        jobs = [{"title": "GenAI Engineer Intern- Master's Degree", "fit": 100},
                {"title": "ML Intern (B.Tech/M.Tech)", "fit": 90},
                {"title": "Software Engineer Intern", "fit": 80}]
        out = _degree_gap(jobs, "B.Tech")
        self.assertEqual([j["fit"] for j in out], [60, 90, 80])
        self.assertIn("postgraduate", out[0]["seniority_note"])
        self.assertEqual(_degree_gap(jobs, "M.Tech"), jobs)  # already postgraduate
        self.assertEqual(_degree_gap(jobs, None), jobs)


class RoleSplitTests(unittest.TestCase):
    def test_field_names_from_a_headline_are_not_roles(self):
        from parsing.profile_extractor import _split_roles
        self.assertEqual(_split_roles(["AI Product | Associate Product Manager | Product Analyst"]),
                         ["Associate Product Manager", "Product Analyst"])
        self.assertEqual(_split_roles(["Data Science"]), ["Data Science"])  # nothing better to keep


class NameTests(unittest.TestCase):
    def test_name_is_spelled_as_on_the_resume(self):
        from parsing.profile_extractor import _name_from
        text = "VIVAN JEEVAN NAIK\nBengaluru, India"
        self.assertEqual(_name_from(text, "Vivan Jeeban Naik", "VIVAN JEEVAN NAIK"), "Vivan Jeevan Naik")  # model typo ignored
        self.assertEqual(_name_from("Asha Rao\nPune", "Asha Rao", "Asha"), "Asha Rao")  # fullest version in the text
        self.assertIsNone(_name_from("no name here", None, None))


if __name__ == "__main__":
    unittest.main()
