"""WP-0.2 — the generated architecture catalog fails closed in both directions."""

import copy
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
_s = importlib.util.spec_from_file_location("gen_arch_catalog", ROOT / "validation" / "v2" / "gen_arch_catalog.py")
gc = importlib.util.module_from_spec(_s)
_s.loader.exec_module(gc)


class ArchCatalog(unittest.TestCase):
    def setUp(self):
        self.code = gc.code_vocabularies()
        self.catalog = (ROOT / gc.CATALOG_REL).read_text(encoding="utf-8")

    def test_committed_catalog_is_in_sync(self):
        self.assertEqual(gc.check(), [])

    def test_round_trip_parse_equals_code(self):
        self.assertEqual(gc.parse(gc.render(self.code)), self.code)

    def test_member_in_code_absent_from_catalog_fails(self):
        code = copy.deepcopy(self.code)
        code["Owner"][2].append("AUDITOR")
        self.assertIn("in code, absent from catalog: Owner.AUDITOR", gc.compare(code, self.catalog))

    def test_member_in_catalog_absent_from_code_fails(self):
        edited = self.catalog.replace("`INTEGRATION` |", "`INTEGRATION`, `AUDITOR` |", 1)
        self.assertNotEqual(edited, self.catalog, "fixture edit did not apply")
        self.assertIn("in catalog, absent from code: Owner.AUDITOR", gc.compare(self.code, edited))

    def test_vocabulary_in_code_absent_from_catalog_fails(self):
        code = dict(self.code)
        code["NewVocabulary"] = ("F1", "§20", ["X"])
        self.assertIn("in code, absent from catalog: vocabulary NewVocabulary", gc.compare(code, self.catalog))

    def test_vocabulary_in_catalog_absent_from_code_fails(self):
        code = dict(self.code)
        del code["IdentityGrade"]
        self.assertIn("in catalog, absent from code: vocabulary IdentityGrade", gc.compare(code, self.catalog))

    def test_removing_a_member_from_code_fails(self):
        code = copy.deepcopy(self.code)
        code["StoryAdmissionDisposition"][2].remove("PRE_SATISFIED")
        self.assertIn("in catalog, absent from code: StoryAdmissionDisposition.PRE_SATISFIED",
                      gc.compare(code, self.catalog))

    def test_frozen_item_reassignment_fails(self):
        code = copy.deepcopy(self.code)
        code["Owner"] = ("F2", *code["Owner"][1:])
        self.assertTrue(any("frozen item / RFC section differ for Owner" in p for p in gc.compare(code, self.catalog)))

    def test_cosmetic_edit_is_still_drift(self):
        self.assertTrue(gc.compare(self.code, self.catalog.replace("vocabularies,", "vocabularies;", 1)))


if __name__ == "__main__":
    unittest.main()
