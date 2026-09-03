"""Kiểm chứng sổ đăng ký nguồn skill — gồm ràng buộc pháp lý."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisdlc.kit.catalog import CATALOG_FILE, Catalog, CatalogError  # noqa: E402

REFERENCES = ROOT / "references"


class TestRealCatalog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cat = Catalog.load()

    def test_loads(self):
        self.assertGreaterEqual(len(self.cat.sources), 5)

    def test_every_source_pins_a_commit(self):
        """Không ghim commit thì bản cài hôm nay khác bản cài tuần sau."""
        for s in self.cat.sources:
            with self.subTest(source=s.id):
                self.assertGreaterEqual(len(s.commit), 7)

    def test_unlicensed_source_is_not_redistributable(self):
        """karpathy-skills không có LICENSE → chỉ tham chiếu, không sao chép."""
        karpathy = self.cat.by_id("karpathy")
        self.assertIsNone(karpathy.license)
        self.assertFalse(karpathy.redistribute)
        self.assertFalse(karpathy.installable)

    def test_no_source_redistributes_without_license(self):
        """Bất biến pháp lý — áp cho mọi nguồn, không chỉ karpathy."""
        offenders = [s.id for s in self.cat.sources if s.redistribute and not s.license]
        self.assertEqual(offenders, [])

    def test_installable_sources_have_license(self):
        for s in self.cat.installable():
            with self.subTest(source=s.id):
                self.assertTrue(s.license, f"{s.id} thiếu license")

    def test_security_source_is_filtered_not_all(self):
        """818 skill không bao giờ được cài thẳng."""
        self.assertEqual(self.cat.by_id("security").selection, "filtered")

    def test_ui_source_requires_frontend(self):
        self.assertIn("frontend_or_mobile", self.cat.by_id("ui-ux").requires)

    def test_superpowers_allowlist_is_explicit(self):
        s = self.cat.by_id("superpowers")
        self.assertEqual(s.selection, "allowlist")
        self.assertIn("test-driven-development", s.allowlist)
        self.assertIn("verification-before-completion", s.allowlist)

    @unittest.skipUnless(REFERENCES.is_dir(), "chưa clone references/")
    def test_all_paths_exist(self):
        problems = self.cat.verify_paths(REFERENCES)
        self.assertEqual(problems, [], f"đường dẫn hỏng: {problems}")

    @unittest.skipUnless((REFERENCES / "PINS.md").is_file(), "không có PINS.md")
    def test_commits_match_pins_file(self):
        """Sổ đăng ký và PINS.md không được lệch nhau."""
        pins = (REFERENCES / "PINS.md").read_text(encoding="utf-8")
        for s in self.cat.sources:
            with self.subTest(source=s.id):
                self.assertIn(s.commit, pins, f"{s.id}: commit không có trong PINS.md")


class TestValidation(unittest.TestCase):
    def write(self, data: dict) -> Path:
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(data, tmp)
        tmp.close()
        return Path(tmp.name)

    def base_source(self, **over) -> dict:
        s = {
            "id": "x", "repo": "https://e.com/x", "commit": "abcdef1234",
            "license": "MIT", "redistribute": True, "local_path": "references/x",
            "skill_roots": ["skills"], "selection": "all",
        }
        s.update(over)
        return s

    def test_rejects_redistribute_without_license(self):
        p = self.write({"sources": [self.base_source(license=None)]})
        with self.assertRaises(CatalogError) as ctx:
            Catalog.load(p)
        self.assertIn("license", str(ctx.exception))

    def test_rejects_short_commit(self):
        p = self.write({"sources": [self.base_source(commit="abc")]})
        with self.assertRaises(CatalogError):
            Catalog.load(p)

    def test_rejects_duplicate_id(self):
        p = self.write({"sources": [self.base_source(), self.base_source()]})
        with self.assertRaises(CatalogError) as ctx:
            Catalog.load(p)
        self.assertIn("trùng", str(ctx.exception))

    def test_rejects_missing_field(self):
        s = self.base_source()
        del s["commit"]
        with self.assertRaises(CatalogError):
            Catalog.load(self.write({"sources": [s]}))

    def test_rejects_empty(self):
        with self.assertRaises(CatalogError):
            Catalog.load(self.write({"sources": []}))

    def test_rejects_malformed_json(self):
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        tmp.write("{ hỏng")
        tmp.close()
        with self.assertRaises(CatalogError):
            Catalog.load(Path(tmp.name))

    def test_reference_only_is_not_installable(self):
        p = self.write({"sources": [self.base_source(selection="reference_only")]})
        self.assertFalse(Catalog.load(p).sources[0].installable)


if __name__ == "__main__":
    unittest.main(verbosity=2)
