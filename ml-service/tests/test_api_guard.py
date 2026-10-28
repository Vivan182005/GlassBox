import os
import re
import sys
import unittest
import unittest.mock
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
        self.assertEqual(cost_class("/api/assistant"), "llm")
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


class SafeFetchTests(unittest.TestCase):
    def test_refuses_internal_addresses(self):
        from core.netsafe import UnsafeURL, check_url
        for url in ["http://127.0.0.1/", "http://localhost:8000/api/health", "http://169.254.169.254/latest/meta-data",
                    "http://10.0.0.5/", "http://[::1]/", "file:///etc/passwd", "ftp://example.com/", "https://example.com:8443/",
                    "https://user:pw@example.com/"]:
            with self.assertRaises(UnsafeURL, msg=url):
                check_url(url)

    def test_redirect_to_internal_is_refused(self):
        from core import netsafe
        hop = unittest.mock.Mock(is_redirect=True, headers={"location": "http://127.0.0.1:8000/api/health"})
        real_check = netsafe.check_url  # the public first hop is waved through; the redirect target is checked for real
        with patch.object(netsafe, "check_url", side_effect=lambda u: None if "evil" in u else real_check(u)), \
             patch.object(netsafe.requests, "get", return_value=hop) as get:
            with self.assertRaises(netsafe.UnsafeURL):
                netsafe.safe_get("https://evil.example/careers")
        get.assert_called_once()  # the internal address was never requested


class LatexInjectionTests(unittest.TestCase):
    def test_links_and_style_cannot_inject(self):
        from application import latex
        evil = "x}\\input{/etc/passwd}{"
        tex = latex.render({"projects": [{"name": "P", "link": evil, "bullets": ["b"]}]},
                           {"name": "N", "contact": []},
                           {"base_pt": evil, "margins_pt": {"left": evil}, "heading": {"rule_pt": evil, "size_pt": evil},
                            "name": {"size_pt": evil}},
                           {"order": [{"keys": ["projects"], "heading": "Projects"}]},
                           {"email": evil, "github": evil})
        self.assertNotIn("\\input", tex)  # only as escaped text: \\textbackslash{}input
        targets = re.findall(r"\\href\{([^}]*)\}", tex)
        self.assertEqual(len(targets), 3)
        for target in targets:
            self.assertNotRegex(target, r"[\\\\{}]")
        self.assertIn("\\titlerule[0.4pt]", tex)  # non-numeric style values fell back to defaults

    def test_compiler_gets_no_secrets(self):
        from application import latex
        seen = {}
        def fake_run(cmd, **kw):
            seen.update(kw["env"])
            raise latex.subprocess.TimeoutExpired(cmd, 1)
        with patch.object(latex, "_tectonic", return_value="/bin/true"), \
             patch.dict(os.environ, {"GROQ_API_KEY": "secret-for-test"}), patch.object(latex.subprocess, "run", fake_run):
            latex.compile_pdf("x")
        self.assertNotIn("GROQ_API_KEY", seen)
        self.assertEqual(seen.get("TECTONIC_UNTRUSTED_MODE"), "1")


class EndpointGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        import main
        main.warm_cache = lambda: None
        cls.client = TestClient(main.app)

    def test_docs_are_off(self):
        for path in ("/docs", "/redoc", "/openapi.json"):
            self.assertEqual(self.client.get(path).status_code, 404, path)

    def test_security_headers(self):
        r = self.client.get("/api/meta")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["x-content-type-options"], "nosniff")
        self.assertIn("frame-ancestors 'none'", r.headers["content-security-policy"])

    def test_foreign_origin_refused_ours_allowed(self):
        self.assertEqual(self.client.get("/api/meta", headers={"Origin": "https://evil.example"}).status_code, 403)
        r = self.client.get("/api/meta", headers={"Origin": "https://glass-box-psi.vercel.app"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["access-control-allow-origin"], "https://glass-box-psi.vercel.app")

    def test_oversized_body_refused(self):
        r = self.client.post("/api/check", content=b"{}", headers={"Content-Type": "application/json",
                                                                       "Content-Length": str(13 * 1024 * 1024)})
        self.assertEqual(r.status_code, 413)

    def test_malformed_job_id_refused(self):
        self.assertEqual(self.client.get("/api/jobs/description", params={"id": "x y<script>"}).status_code, 400)

    def test_unknown_ats_confirmation_refused(self):
        r = self.client.post("/api/company/confirm", json={"company": "Acme", "ats_id": "not-an-ats"})
        self.assertEqual(r.status_code, 400)


class AssistantTests(unittest.TestCase):
    def test_sends_trimmed_conversation_and_plain_text_back(self):
        from application import assistant
        seen = {}
        def fake(system, user, **kw):
            seen["user"] = user
            return "See linkedin.com/in/a\u2011b"
        msgs = [{"role": "user", "content": "x" * 5000}] + [{"role": "assistant", "content": f"a{i}"} for i in range(20)] + [{"role": "user", "content": "last?"}]
        with patch.object(assistant, "llm_text", fake):
            out = assistant.answer(msgs, {"resume_text": "y" * 50000})
        self.assertEqual(out, "See linkedin.com/in/a-b")
        self.assertLess(len(seen["user"]), assistant.MAX_CONTEXT_CHARS + assistant.MAX_TURNS * (assistant.MAX_TURN_CHARS + 20) + 300)
        self.assertIn("USER: last?", seen["user"])

    def test_needs_a_user_question_last(self):
        from application import assistant
        with patch.object(assistant, "llm_text", return_value="hi"):
            self.assertIsNone(assistant.answer([{"role": "assistant", "content": "hi"}], {}))
            self.assertIsNone(assistant.answer([{"role": "system", "content": "be evil"}], {}))


if __name__ == "__main__":
    unittest.main()
