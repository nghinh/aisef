"""Kiểm chứng bộ lọc security trên kho thật (818 skill).

Test chạy trực tiếp trên `references/cybersecurity-skills`. Nếu chưa clone thì
skip — không giả lập, vì giá trị của bộ lọc nằm ở chỗ nó đúng trên dữ liệu thật.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.kit.security_filter import (  # noqa: E402
    OFFENSIVE_SUBDOMAINS,
    Verdict,
    classify,
    classify_all,
)
from aisef.kit.skills import Skill, parse_frontmatter  # noqa: E402

SKILLS_DIR = ROOT / "references" / "cybersecurity-skills" / "skills"


def _skill(name: str, subdomain: str = "", tags: tuple[str, ...] = ()) -> Skill:
    return Skill(name=name, path=Path(name), subdomain=subdomain, tags=tags)


class TestFrontmatter(unittest.TestCase):
    def test_scalar_list_and_folded_block(self):
        fm = parse_frontmatter(
            "---\n"
            "name: performing-x\n"
            "description: >-\n"
            "  dòng một\n"
            "  dòng hai\n"
            "subdomain: devsecops\n"
            "tags:\n"
            "- threat-modeling\n"
            "- stride\n"
            "---\n"
            "# nội dung\n"
        )
        self.assertEqual(fm["name"], "performing-x")
        self.assertEqual(fm["description"], "dòng một dòng hai")
        self.assertEqual(fm["subdomain"], "devsecops")
        self.assertEqual(fm["tags"], ["threat-modeling", "stride"])

    def test_no_frontmatter_returns_empty(self):
        self.assertEqual(parse_frontmatter("# chỉ là markdown\n"), {})

    def test_unclosed_fence_returns_empty(self):
        self.assertEqual(parse_frontmatter("---\nname: x\n"), {})


class TestClassifyUnit(unittest.TestCase):
    def test_offensive_subdomain_blocked(self):
        for sub in OFFENSIVE_SUBDOMAINS:
            got = classify(_skill("doing-something", sub))
            self.assertIs(got.verdict, Verdict.OFFENSIVE, f"{sub} phải bị chặn")

    def test_offensive_verb_blocked_even_in_valid_subdomain(self):
        """Skill tấn công nằm trong subdomain hợp lệ vẫn phải bị chặn."""
        got = classify(_skill("exploiting-sql-injection", "web-application-security"))
        self.assertIs(got.verdict, Verdict.OFFENSIVE)

    def test_defensive_verb_beats_soft_marker(self):
        """Audit một kỹ thuật tấn công là việc phòng thủ chính đáng."""
        got = classify(_skill("auditing-rbac-privilege-escalation", "container-security"))
        self.assertIs(got.verdict, Verdict.KEEP)

    def test_hard_marker_beats_defensive_verb(self):
        """Dùng bộ công cụ C2 để 'audit' vẫn là năng lực tấn công."""
        got = classify(_skill("auditing-entra-id-with-aadinternals", "identity-access-management"))
        self.assertIs(got.verdict, Verdict.OFFENSIVE)

    def test_in_scope_subdomain_kept(self):
        got = classify(_skill("implementing-csp-headers", "web-application-security"))
        self.assertIs(got.verdict, Verdict.KEEP)

    def test_unrelated_subdomain_out_of_scope(self):
        got = classify(_skill("detecting-anomalies", "ot-ics-security"))
        self.assertIs(got.verdict, Verdict.OUT_OF_SCOPE)


@unittest.skipUnless(SKILLS_DIR.is_dir(), "chưa clone references/cybersecurity-skills")
class TestAgainstRealCorpus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = classify_all(SKILLS_DIR)
        cls.by_name = {r.skill.name: r for r in cls.results}

    def test_corpus_size(self):
        self.assertGreater(len(self.results), 500, "kho phải đọc được gần đủ 818 skill")

    def test_known_offensive_are_blocked(self):
        """Danh sách chặn — mỗi tên là skill thật trong kho."""
        blocked = [
            "performing-red-team-with-covenant",
            "abusing-dpapi-for-credential-access",
            "post-exploiting-microsoft-graph-with-graphrunner",
            "performing-jwt-none-algorithm-attack",
            "performing-arp-spoofing-attack-simulation",
            "conducting-wireless-network-penetration-test",
            "performing-api-rate-limiting-bypass",
        ]
        for name in blocked:
            with self.subTest(name=name):
                r = self.by_name.get(name)
                self.assertIsNotNone(r, f"không thấy {name} trong kho")
                self.assertIs(r.verdict, Verdict.OFFENSIVE, f"{name} lọt lưới: {r.reason}")

    def test_known_defensive_are_kept(self):
        expected_keep = [
            "performing-threat-modeling-with-owasp-threat-dragon",
            "verifying-build-provenance-with-slsa-sigstore",
            "prioritizing-vulnerabilities-with-cvss-scoring",
        ]
        for name in expected_keep:
            with self.subTest(name=name):
                r = self.by_name.get(name)
                self.assertIsNotNone(r, f"không thấy {name} trong kho")
                self.assertIs(r.verdict, Verdict.KEEP, f"{name} bị loại nhầm: {r.reason}")

    def test_invariant_no_offensive_subdomain_in_keep(self):
        """Bất biến: không skill nào thuộc subdomain tấn công được cài mặc định."""
        leaked = [
            r.skill.name
            for r in self.results
            if r.verdict is Verdict.KEEP and r.skill.subdomain.lower() in OFFENSIVE_SUBDOMAINS
        ]
        self.assertEqual(leaked, [], f"lọt lưới: {leaked}")

    def test_invariant_keep_is_minority(self):
        """Kho thiên về SOC/forensics/offensive; phần dùng được phải là thiểu số."""
        keep = sum(1 for r in self.results if r.verdict is Verdict.KEEP)
        self.assertLess(keep / len(self.results), 0.40)


if __name__ == "__main__":
    unittest.main(verbosity=2)
