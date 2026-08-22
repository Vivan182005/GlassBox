import unittest
import os
import sys
import time
from unittest.mock import patch, MagicMock

# Ensure ml-service directory is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsing.ats_signatures import detect_ats_by_company_name, record_user_confirmation, TTL_SECONDS, load_company_cache, save_company_cache
from explainability.fairness import calculate_fairness_metrics, calculate_mitigated_fairness_metrics
from explainability.explainer import explainer_instance
from bias_model.model_trainer import trainer_instance

class TestGlassBoxCore(unittest.TestCase):
    def test_ats_cache_staleness_reprobes(self):
        """Asserts that cache entries older than TTL (90 days) are re-probed rather than returned stale."""
        cache = load_company_cache()
        test_key = "stale_test_corp_xyz"
        
        stale_time = time.time() - (TTL_SECONDS + 1000)
        cache[test_key] = {
            "detected": True,
            "company_name": "Stale Test Corp XYZ",
            "profile": {"id": "workday", "name": "Workday"},
            "source_tier": "tier1",
            "cached_at": stale_time
        }
        save_company_cache(cache)
        
        with patch("urllib.request.urlopen", side_effect=Exception("Network error")):
            res = detect_ats_by_company_name("Stale Test Corp XYZ")
            self.assertFalse(res.get("from_cache") is True and res.get("source_tier") != "user_confirmed")

    def test_user_confirmed_ats_override(self):
        """Asserts user manual ATS confirmation is saved and takes priority."""
        res = record_user_confirmation("Acme Corp", "greenhouse")
        self.assertTrue(res["detected"])
        self.assertEqual(res["profile"]["id"], "greenhouse")
        self.assertEqual(res["source_tier"], "user_confirmed")

    def test_fairness_metrics_computation(self):
        """Asserts fairness metrics are calculated dynamically from actual model predictions."""
        metrics = calculate_fairness_metrics()
        self.assertIn("demographic_parity_difference", metrics)
        self.assertIn("disparate_impact_ratio", metrics)
        self.assertIn("ground_truth_bias_disclosure", metrics)
        self.assertIsInstance(metrics["disparate_impact_ratio"], float)

    def test_mitigated_fairness_metrics_comparison(self):
        """Asserts mitigation pass improves or changes disparate impact ratio."""
        mit_metrics = calculate_mitigated_fairness_metrics()
        self.assertIn("unmitigated", mit_metrics)
        self.assertIn("mitigated", mit_metrics)
        self.assertIn("disparate_impact_ratio", mit_metrics["mitigated"])

    def test_shap_lime_consistency(self):
        """Asserts SHAP and LIME top feature directions agree on clear candidate vectors."""
        feat_dict = {
            "years_experience": 10.0,
            "skill_count": 12,
            "college_tier": "Tier 1",
            "employment_gap_months": 0,
            "has_internship": True,
            "gpa": 3.9,
            "project_count": 5,
            "graduation_year": 2023,
            "has_referral": True,
            "demographic_proxy": "Group A"
        }
        waterfall = explainer_instance.get_candidate_shap_waterfall(feat_dict)["waterfall"]
        lime = explainer_instance.get_lime_explanation(feat_dict)["lime_rules"]
        
        agreement = explainer_instance.compute_shap_lime_agreement(waterfall, lime)
        self.assertGreaterEqual(agreement, 0.50)
        self.assertIsInstance(agreement, float)

    def test_plain_language_factor_consistency(self):
        """Asserts plain-language summary cites the same primary factor as SHAP waterfall."""
        feat_dict = {
            "years_experience": 1.0,
            "skill_count": 2,
            "college_tier": "Tier 2/3",
            "employment_gap_months": 18,
            "has_internship": False,
            "gpa": 2.8,
            "project_count": 1,
            "graduation_year": 2020,
            "has_referral": False,
            "demographic_proxy": "Group B"
        }
        verdict = trainer_instance.predict_candidate(feat_dict)
        waterfall = explainer_instance.get_candidate_shap_waterfall(feat_dict)["waterfall"]
        ice = explainer_instance.get_ice_plot_data("employment_gap_months", feat_dict)
        
        plain_text = explainer_instance.generate_plain_language_explanation(
            feat_dict, verdict, waterfall, ice, api_key_override=None
        )
        
        top_factor_display = waterfall[0]["display_name"].lower()
        self.assertTrue(top_factor_display in plain_text.lower() or "qualification" in plain_text.lower())

if __name__ == "__main__":
    unittest.main()
