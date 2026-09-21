"""WP-0.1 — the approved architecture baseline is mechanically identifiable, and drift fails."""

import importlib.util
import json
import pathlib
import shutil
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
_s = importlib.util.spec_from_file_location("freeze_manifest", ROOT / "validation" / "v2" / "freeze_manifest.py")
fm = importlib.util.module_from_spec(_s)
_s.loader.exec_module(fm)


def _copy_tree(tmp: pathlib.Path) -> pathlib.Path:
    for rel in (fm.RFC_REL, fm.APPROVAL_REL, fm.MANIFEST_REL):
        dst = tmp / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, dst)
    return tmp


class FreezeManifest(unittest.TestCase):
    def setUp(self):
        self.text = (ROOT / fm.RFC_REL).read_text(encoding="utf-8")
        self.approval = json.loads((ROOT / fm.APPROVAL_REL).read_text(encoding="utf-8"))

    def test_normative_digest_matches_approval_record(self):
        self.assertEqual(fm.normative_digest(self.text), self.approval["rfc"]["rfc_normative_digest"])

    def test_freeze_table_digest_matches_approval_record(self):
        self.assertEqual(fm.freeze_table_digest(self.text), self.approval["freeze_table"]["digest_sha256"])

    def test_exactly_F1_to_F11_enumerated(self):
        self.assertEqual([i["id"] for i in fm.freeze_items(self.text)], [f"F{i}" for i in range(1, 12)])

    def test_digest_rules_are_the_ones_the_approval_record_states(self):
        self.assertIn(repr(fm.NORMATIVE_MARK), self.approval["rfc"]["normative_body_rule"])
        self.assertIn(repr(fm.FREEZE_TABLE_BEGIN), self.approval["freeze_table"]["digest_rule"])
        self.assertIn(repr(fm.FREEZE_TABLE_END), self.approval["freeze_table"]["digest_rule"])

    def test_committed_manifest_is_current(self):
        self.assertEqual(fm.check(ROOT), [])

    def test_a_crlf_checkout_is_the_same_baseline(self):
        """Windows CI checks out with autocrlf: every file arrives with CRLF. That is the same committed content,
        so it must identify the same baseline (it once read as a stale manifest: the approval hash was of raw bytes)."""
        with tempfile.TemporaryDirectory() as t:
            root = _copy_tree(pathlib.Path(t))
            for rel in (fm.RFC_REL, fm.APPROVAL_REL, fm.MANIFEST_REL):
                f = root / rel
                f.write_bytes(f.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))  # already CRLF on Windows
            self.assertEqual(fm.check(root), [])
            self.assertEqual(fm.build(root)["approval_record_sha256"], fm.build(ROOT)["approval_record_sha256"])

    def test_one_byte_normative_edit_fails(self):
        with tempfile.TemporaryDirectory() as t:
            root = _copy_tree(pathlib.Path(t))
            rfc = root / fm.RFC_REL
            text = rfc.read_text(encoding="utf-8")
            i = text.index(fm.NORMATIVE_MARK) + len(fm.NORMATIVE_MARK) + 10
            rfc.write_text(text[:i] + "X" + text[i + 1:], encoding="utf-8")
            self.assertTrue(any("normative body differs" in p for p in fm.check(root)))

    def test_status_preamble_edit_does_not_change_the_normative_digest(self):
        with tempfile.TemporaryDirectory() as t:
            root = _copy_tree(pathlib.Path(t))
            rfc = root / fm.RFC_REL
            text = rfc.read_text(encoding="utf-8")
            edited = text.replace("**Status: APPROVED — FROZEN.**", "**Status: APPROVED — FROZEN (reworded).**", 1)
            self.assertNotEqual(edited, text, "fixture edit did not apply")
            rfc.write_text(edited, encoding="utf-8")
            self.assertEqual(fm.normative_digest(edited), fm.normative_digest(text))
            self.assertEqual(fm.check(root), [])

    def test_freeze_table_row_edit_fails(self):
        with tempfile.TemporaryDirectory() as t:
            root = _copy_tree(pathlib.Path(t))
            rfc = root / fm.RFC_REL
            text = rfc.read_text(encoding="utf-8")
            edited = text.replace("| **F3** | The `Owner` set", "| **F3** | The `Owner` enumeration", 1)
            self.assertNotEqual(edited, text, "fixture edit did not apply")
            rfc.write_text(edited, encoding="utf-8")
            problems = fm.check(root)
            self.assertTrue(any("freeze table differs" in p for p in problems), problems)

    def test_a_twelfth_frozen_item_fails(self):
        extra = "| **F12** | a new item | none |\n"
        text = self.text.replace("## Adversarial regression cases", extra + "\n## Adversarial regression cases", 1)
        ids = [i["id"] for i in fm.freeze_items(text)]
        self.assertIn("F12", ids)
        self.assertNotEqual(ids, fm.FROZEN_IDS)


if __name__ == "__main__":
    unittest.main()
