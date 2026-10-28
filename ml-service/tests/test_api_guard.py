import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.ratelimit import Limiter, allowed_origins, client_ip, cost_class


class RateLimitTests(unittest.TestCase):
    def test_per_ip_window(self):
        lim = Limiter({"search": (2, 60, 0)})
        self.assertIsNone(lim.check("1.1.1.1", "search", now=0))
        self.assertIsNone(lim.check("1.1.1.1", "search", now=1))
        refused = lim.check("1.1.1.1", "search", now=2)
        self.assertIsNotNone(refused)
        self.assertEqual(refused[1], 59)
        self.assertIsNone(lim.check("2.2.2.2", "search", now=2))  # other callers unaffected
        self.assertIsNone(lim.check("1.1.1.1", "search", now=61))  # window slid past

    def test_daily_cap_across_ips(self):
        lim = Limiter({"llm": (100, 3600, 3)})
        for i in range(3):
            self.assertIsNone(lim.check(f"10.0.0.{i}", "llm", now=100))
        self.assertIn("today", lim.check("10.0.0.9", "llm", now=100)[0])
        self.assertIsNone(lim.check("10.0.0.9", "llm", now=86400 + 100))  # next day

    def test_cost_classes(self):
        self.assertEqual(cost_class("/api/jobs/search"), "search")
        self.assertEqual(cost_class("/api/check/tailor"), "llm")
        self.assertEqual(cost_class("/api/apply/prepare"), "llm")
        self.assertEqual(cost_class("/api/health"), "default")
        self.assertEqual(cost_class("/api/jobs/description"), "default")

    def test_client_ip(self):
        self.assertEqual(client_ip({"cf-connecting-ip": "9.9.9.9", "x-forwarded-for": "1.2.3.4"}, "127.0.0.1"), "9.9.9.9")
        self.assertEqual(client_ip({"x-forwarded-for": "1.2.3.4, 10.0.0.1"}, "127.0.0.1"), "1.2.3.4")
        self.assertEqual(client_ip({}, "127.0.0.1"), "127.0.0.1")

    def test_origins(self):
        with patch.dict(os.environ, {"ALLOWED_ORIGINS": "*, https://staging.example.com/"}):
            origins = allowed_origins()
        self.assertIn("https://glass-box-psi.vercel.app", origins)
        self.assertIn("https://staging.example.com", origins)
        self.assertNotIn("*", origins)


if __name__ == "__main__":
    unittest.main()
