"""Kiểm chứng dò stack và lọc security tầng 2."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisdlc.kit.detect_stack import Stack, detect  # noqa: E402
from aisdlc.kit.security_filter import (  # noqa: E402
    ALWAYS_RELEVANT,
    Classification,
    Verdict,
    classify_all,
    select_for_stack,
    subdomains_for_stack,
)
from aisdlc.kit.skills import Skill  # noqa: E402

CORPUS = ROOT / "references" / "cybersecurity-skills" / "skills"


class TestDetect(unittest.TestCase):
    def test_python_react_postgres_docker(self):
        s = detect("Backend Python FastAPI, frontend React, PostgreSQL, triển khai Docker.")
        self.assertEqual(s.backend, ["python"])
        self.assertEqual(s.frontend, ["react"])
        self.assertEqual(s.database, ["postgres"])
        self.assertEqual(s.deploy, ["docker"])

    def test_go_detected_when_capitalised(self):
        """'Dịch vụ Go' là ngôn ngữ; 'go to the page' thì không."""
        self.assertIn("go", detect("Dịch vụ Go chạy trên Kubernetes.").backend)

    def test_lowercase_go_is_not_a_language(self):
        self.assertEqual(detect("Người dùng go to the settings page.").backend, [])

    def test_word_boundary_prevents_false_match(self):
        """'go' không được khớp bên trong 'Django'."""
        s = detect("Backend dùng Django.")
        self.assertEqual(s.backend, ["python"])

    def test_mobile(self):
        s = detect("Ứng dụng Flutter, backend Node.js, MongoDB.")
        self.assertEqual(s.mobile, ["flutter"])
        self.assertEqual(s.backend, ["node"])
        self.assertTrue(s.has_ui)

    def test_multiple_in_one_category(self):
        s = detect("Chạy trên Kubernetes ở AWS, dùng Docker.")
        self.assertEqual(set(s.deploy), {"kubernetes", "aws", "docker"})

    def test_nothing_detected_is_recorded_not_guessed(self):
        """Không có căn cứ thì để trống, không mặc định Postgres."""
        s = detect("Ứng dụng quản lý công việc cho đội nhóm.")
        self.assertEqual(s.database, [])
        self.assertIn("database", s.undetermined)
        self.assertIn("backend", s.undetermined)

    def test_web_without_framework_still_needs_ui(self):
        s = detect("Ứng dụng web chạy trên trình duyệt di động.")
        self.assertIn("frontend", s.undetermined)

    def test_summary_readable(self):
        self.assertIn("python", detect("Backend Python, PostgreSQL.").summary())

    def test_empty_text(self):
        s = detect("")
        self.assertFalse(s.has_ui)
        self.assertIn("backend", s.undetermined)


class TestSubdomainSelection(unittest.TestCase):
    def test_always_relevant_included_even_with_empty_stack(self):
        got = subdomains_for_stack(Stack().as_dict())
        self.assertTrue(ALWAYS_RELEVANT <= got)

    def test_docker_pulls_container_security(self):
        s = detect("Triển khai bằng Docker.")
        self.assertIn("container-security", subdomains_for_stack(s.as_dict()))

    def test_no_cloud_subdomain_without_cloud(self):
        """Dự án không dùng đám mây thì không nhận skill đám mây."""
        s = detect("Backend Python, PostgreSQL, Docker.")
        self.assertNotIn("cloud-security", subdomains_for_stack(s.as_dict()))

    def test_aws_pulls_cloud_security(self):
        s = detect("Chạy trên AWS Lambda.")
        self.assertIn("cloud-security", subdomains_for_stack(s.as_dict()))

    def test_auth_marker_pulls_identity(self):
        text = "Có đăng nhập bằng JWT."
        got = subdomains_for_stack(detect(text).as_dict(), requirements_text=text)
        self.assertIn("identity-access-management", got)

    def test_no_auth_no_identity(self):
        text = "Công cụ dòng lệnh xử lý tệp cục bộ."
        got = subdomains_for_stack(detect(text).as_dict(), requirements_text=text)
        self.assertNotIn("identity-access-management", got)

    def test_mobile_pulls_mobile_security(self):
        s = detect("Ứng dụng Flutter.")
        self.assertIn("mobile-security", subdomains_for_stack(s.as_dict()))


class TestSelectionSafety(unittest.TestCase):
    def _cls(self, name, subdomain, verdict):
        return Classification(Skill(name=name, path=Path(name), subdomain=subdomain), verdict, "test")

    def test_offensive_never_selected_regardless_of_stack(self):
        """Skill tấn công không bao giờ được đưa vào, dù stack là gì."""
        results = [
            self._cls("attacking-x", "devsecops", Verdict.OFFENSIVE),
            self._cls("implementing-y", "devsecops", Verdict.KEEP),
        ]
        got = select_for_stack(results, detect("Docker, Python").as_dict())
        self.assertEqual([c.skill.name for c in got], ["implementing-y"])

    def test_out_of_scope_not_selected(self):
        results = [self._cls("hunting-z", "threat-hunting", Verdict.OUT_OF_SCOPE)]
        self.assertEqual(select_for_stack(results, detect("Python").as_dict()), [])


@unittest.skipUnless(CORPUS.is_dir(), "chưa clone references/cybersecurity-skills")
class TestOnRealCorpus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = classify_all(CORPUS)
        cls.keep = [r for r in cls.results if r.verdict is Verdict.KEEP]

    def test_tier2_reduces_further(self):
        text = "Backend Python FastAPI, frontend React, PostgreSQL, Docker. Có đăng nhập."
        sel = select_for_stack(self.keep, detect(text).as_dict(), requirements_text=text)
        self.assertLess(len(sel), len(self.keep))
        self.assertGreater(len(sel), 0)

    def test_non_cloud_project_gets_no_cloud_skills(self):
        text = "Backend Python, PostgreSQL, Docker."
        sel = select_for_stack(self.keep, detect(text).as_dict(), requirements_text=text)
        self.assertEqual([r for r in sel if r.skill.subdomain == "cloud-security"], [])

    def test_no_offensive_in_selection(self):
        text = "Go trên Kubernetes ở AWS."
        sel = select_for_stack(self.keep, detect(text).as_dict(), requirements_text=text)
        self.assertTrue(all(r.verdict is Verdict.KEEP for r in sel))


if __name__ == "__main__":
    unittest.main(verbosity=2)
