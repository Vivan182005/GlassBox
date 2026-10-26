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
from explainability.fairness import calculate_fairness_metrics, calculate_mitigated_fairness_metrics
from explainability.explainer import explainer_instance

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
        self.assertEqual(_split_roles(["AI Product | Associate Product Manager, Product Analyst"]),
                         ["AI Product", "Associate Product Manager", "Product Analyst"])

    def test_ambiguous_aliases(self):
        self.assertEqual(find_skills("Sentence Transformers, n8n onboarding, faster monitoring"), {})


class TestFairnessLab(unittest.TestCase):
    def test_fairness_metrics(self):
        metrics = calculate_fairness_metrics()
        self.assertIn("disparate_impact_ratio", metrics)
        self.assertIsInstance(metrics["disparate_impact_ratio"], float)
        mit = calculate_mitigated_fairness_metrics()
        self.assertIn("mitigated", mit)

    def test_shap_lime_agreement(self):
        feat = {"years_experience": 10.0, "skill_count": 12, "college_tier": "Tier 1", "employment_gap_months": 0,
                "has_internship": True, "gpa": 3.9, "project_count": 5, "graduation_year": 2023, "has_referral": True,
                "demographic_proxy": "Group A"}
        waterfall = explainer_instance.get_candidate_shap_waterfall(feat)["waterfall"]
        lime = explainer_instance.get_lime_explanation(feat)["lime_rules"]
        self.assertGreaterEqual(explainer_instance.compute_shap_lime_agreement(waterfall, lime), 0.5)


if __name__ == "__main__":
    unittest.main()
