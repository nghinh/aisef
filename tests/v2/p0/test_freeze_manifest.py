"""WP-0.1 — the approved architecture baseline is mechanically identifiable, and drift fails."""

import contextlib
import hashlib
import importlib.util
import io
import json
import pathlib
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[3]
_s = importlib.util.spec_from_file_location("freeze_manifest", ROOT / "validation" / "v2" / "freeze_manifest.py")
fm = importlib.util.module_from_spec(_s)
_s.loader.exec_module(fm)


def _copy_tree(tmp: pathlib.Path, skip: tuple = ()) -> pathlib.Path:
    """The baseline files copied into `tmp`, those named in `skip` left out (a missing file, deleting nothing)."""
    for rel in (r for r in fm.BASELINE_FILES if r not in skip):
        dst = tmp / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, dst)
    return tmp


from tests.v2.sealing_gate import sealing  # noqa: E402 — ROADMAP-2.2 F1: the sealing tier's gate


class FreezeManifest(unittest.TestCase):
    def setUp(self):
        self.text = (ROOT / fm.RFC_REL).read_text(encoding="utf-8")
        self.approval = json.loads((ROOT / fm.APPROVAL_REL).read_text(encoding="utf-8"))
        self.effective, self.links, self.broken = fm.lineage(ROOT)

    def test_normative_digest_matches_the_approval_lineage(self):
        self.assertEqual(self.broken, [])
        self.assertEqual(fm.normative_digest(self.text), self.effective["rfc_normative_digest"])

    def test_freeze_table_digest_matches_the_approval_lineage(self):
        self.assertEqual(fm.freeze_table_digest(self.text), self.effective["freeze_table_digest"])

    def test_the_original_approval_is_unchanged_and_heads_the_lineage(self):
        self.assertEqual(self.links[0]["record"], fm.APPROVAL_REL)
        self.assertEqual(self.links[0]["sha256"], "c23191bd71bc299dba9df3f996f45b04ab82b6f113dd6629c62343d1776fe59a")
        self.assertEqual(self.links[0]["rfc_normative_digest"],
                         "8f0d522d9db0322c3aff5df2b5e0d568dce0a422f466dc610c7a6a9acdba8e3f")
        self.assertEqual([link["record"] for link in self.links[1:]], list(fm.AMENDMENTS))

    def _broken_lineage(self, edit):
        with tempfile.TemporaryDirectory() as t:
            root = _copy_tree(pathlib.Path(t))
            edit(root)
            return fm.check(root)

    def test_an_edited_exception_breaks_the_lineage(self):
        def edit(root):
            p = root / fm.EXCEPTIONS[0]
            p.write_text(p.read_text(encoding="utf-8").replace("DEVELOPER", "PLAN", 1), encoding="utf-8")
        self.assertTrue(any("exception record" in p for p in self._broken_lineage(edit)))

    def test_an_amendment_that_does_not_start_from_the_approved_digest_breaks_the_lineage(self):
        def edit(root):
            p = root / fm.AMENDMENTS[0]
            d = json.loads(p.read_text(encoding="utf-8"))
            d["rfc_normative_digest"]["before"] = "0" * 64
            p.write_text(json.dumps(d), encoding="utf-8")
        self.assertTrue(any("'before' is not the previously approved digest" in p for p in self._broken_lineage(edit)))

    def test_an_edited_original_approval_breaks_the_lineage(self):
        def edit(root):
            p = root / fm.APPROVAL_REL
            p.write_text(p.read_text(encoding="utf-8").replace('"owner"', '"someone"', 1), encoding="utf-8")
        self.assertTrue(any("does not amend" in p for p in self._broken_lineage(edit)))

    def test_the_2_0_manifest_is_history_and_an_edit_of_it_fails(self):
        self.assertEqual(fm.history_problems(ROOT), [])
        self.assertNotEqual(fm.MANIFEST_REL, fm.HISTORY_MANIFEST_REL)
        tagged = subprocess.run(["git", "rev-parse", f"{fm.HISTORY_TAG}:{fm.HISTORY_MANIFEST_REL}"], cwd=ROOT,
                                capture_output=True, encoding="utf-8", check=True).stdout.strip()
        self.assertEqual(tagged, fm.HISTORY_BLOB)   # the pinned blob is the tag's

        def edit(root):
            p = root / fm.HISTORY_MANIFEST_REL
            p.write_text(p.read_text(encoding="utf-8").replace('"WP-0.1"', '"WP-0.X"', 1), encoding="utf-8")
        self.assertTrue(any("differs from its blob at v2.0.0" in p for p in self._broken_lineage(edit)))

    def _in_copy(self, edit, skip: tuple = ()):
        """history_problems and check on a copy of the baseline files after `edit(root)`; neither may raise."""
        with tempfile.TemporaryDirectory() as t:
            root = _copy_tree(pathlib.Path(t), skip)
            edit(root)
            return fm.history_problems(root), fm.check(root)

    def test_a_2_0_manifest_that_recorded_drift_fails_even_under_its_own_pin(self):
        def edit(root):
            p = root / fm.HISTORY_MANIFEST_REL
            d = json.loads(p.read_text(encoding="utf-8"))
            d["rfc_normative_digest"] = "0" * 64
            p.write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
            data = p.read_bytes().replace(b"\r\n", b"\n")   # the pin rule hashes LF bytes, as history_problems does:
            self._pin = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()   # write_text emits CRLF on Windows
        with tempfile.TemporaryDirectory() as t:
            root = _copy_tree(pathlib.Path(t))
            edit(root)
            with mock.patch.object(fm, "HISTORY_BLOB", self._pin):   # the blob check alone would not see it
                problems = fm.history_problems(root)
        self.assertIn(f"{fm.HISTORY_MANIFEST_REL} records a drifted baseline", problems)
        self.assertFalse(any("differs from its blob" in p for p in problems), problems)

    def test_a_re_chained_earlier_link_is_not_the_lineage_the_2_0_manifest_froze(self):
        """An earlier link rewritten and re-chained (V2-007 re-bound to the new V2-006 bytes) leaves no broken link,
        so only the history check sees it."""
        def edit(root):
            v6, v7 = (root / fm.AMENDMENTS[-2]), (root / fm.AMENDMENTS[-1])
            d = json.loads(v6.read_text(encoding="utf-8"))
            d["rule"] += " (rewritten)"
            v6.write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
            d7 = json.loads(v7.read_text(encoding="utf-8"))
            d7["amends"]["sha256"] = fm._lf_sha(v6)
            v7.write_text(json.dumps(d7, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
            self.assertEqual(fm.lineage(root)[2], [])
        history, problems = self._in_copy(edit)
        head = f"the lineage {fm.HISTORY_MANIFEST_REL} froze is not the head of the current lineage"
        self.assertEqual(history, [head])
        self.assertIn(head, problems)

    def test_an_unreadable_2_0_manifest_is_a_problem_never_an_exception(self):
        for content, reason in ((b"{not json", "is not a readable manifest"), (b"[]", "is not a readable manifest"),
                                (b"\xff\xfe", "is not a readable manifest"), (None, "is missing or unreadable")):
            def edit(root, content=content):
                if content is not None:
                    (root / fm.HISTORY_MANIFEST_REL).write_bytes(content)
            history, problems = self._in_copy(edit, () if content else (fm.HISTORY_MANIFEST_REL,))
            self.assertTrue(any(reason in p for p in history), (content, history))
            self.assertTrue(problems, content)   # check() reports, never raises
            if content is not None:
                self.assertTrue(any("differs from its blob at v2.0.0" in p for p in history), history)

    def test_a_missing_or_non_utf8_current_manifest_is_a_problem_not_an_exception(self):
        for content, reason in ((b"\xff", f"{fm.MANIFEST_REL} is stale: regenerate it"), (None, f"{fm.MANIFEST_REL} is missing")):
            def edit(root, content=content):
                if content is not None:
                    (root / fm.MANIFEST_REL).write_bytes(content)
            self.assertIn(reason, self._in_copy(edit, () if content else (fm.MANIFEST_REL,))[1])

    def test_the_writer_names_its_refusal_and_never_overwrites(self):
        def main(edit=None, skip=(), **patch):
            """fm.main on a fresh copy of the baseline files: its exit code, its output and the copy's 2.0 and 2.1 bytes."""
            with tempfile.TemporaryDirectory() as t:
                root = _copy_tree(pathlib.Path(t), skip)
                if edit:
                    edit(root)
                out = io.StringIO()
                with mock.patch.multiple(fm, ROOT=root, **patch), contextlib.redirect_stdout(out):
                    rc = fm.main([])
                manifest = root / fm.MANIFEST_REL
                return (rc, out.getvalue(), (root / fm.HISTORY_MANIFEST_REL).read_bytes(),
                        manifest.read_bytes() if manifest.exists() else None, fm.check(root))
        committed, history = (ROOT / fm.MANIFEST_REL).read_bytes(), (ROOT / fm.HISTORY_MANIFEST_REL).read_bytes()

        rc, out, h, m, _ = main()
        self.assertEqual((rc, out.strip()), (1, f"REFUSED: {fm.MANIFEST_REL} exists; a record is never overwritten"))
        self.assertEqual((h, m), (history, committed))
        rc, out, h, _, _ = main(MANIFEST_REL=fm.HISTORY_MANIFEST_REL)
        self.assertEqual(rc, 1)
        self.assertIn("is not a 2.1 path; a 2.0 record is never rewritten", out)
        self.assertEqual(h, history)
        rc, out, h, m, problems = main(skip=(fm.MANIFEST_REL,))
        self.assertEqual(rc, 0, out)
        self.assertEqual((h, m, problems), (history, committed, []))   # the writer derives the committed bytes

        def edit_history(r):
            p = r / fm.HISTORY_MANIFEST_REL
            p.write_text(p.read_text(encoding="utf-8").replace('"WP-0.1"', '"WP-0.X"', 1), encoding="utf-8")
        rc, out, _, m, _ = main(edit_history, skip=(fm.MANIFEST_REL,))
        self.assertEqual((rc, m), (1, None))
        self.assertTrue(out.startswith("REFUSED: the 2.0 manifest is not intact history: "), out)
        self.assertIn("differs from its blob at v2.0.0", out)
        self.assertNotIn("RFC at HEAD", out)

        def edit_rfc(r):
            rfc = r / fm.RFC_REL
            text = rfc.read_text(encoding="utf-8")
            i = text.index(fm.NORMATIVE_MARK) + len(fm.NORMATIVE_MARK) + 10
            rfc.write_text(text[:i] + "X" + text[i + 1:], encoding="utf-8")
        rc, out, _, m, _ = main(edit_rfc, skip=(fm.MANIFEST_REL,))
        self.assertEqual((rc, m), (1, None))
        self.assertIn("the RFC at HEAD does not match the approval record", out)
        self.assertNotIn("2.0 manifest", out)

    @sealing
    def test_the_V2_007_exception_records_what_the_owner_decided_and_when(self):
        """The load-bearing content of the write-once V2-007 records, checked against their sources."""
        def git(*a):
            return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, encoding="utf-8", check=True).stdout.strip()
        exc = json.loads((ROOT / fm.EXCEPTIONS[-1]).read_text(encoding="utf-8"))
        amendment = json.loads((ROOT / fm.AMENDMENTS[-1]).read_text(encoding="utf-8"))
        ledger_rel = "closure-evidence/v2/cycle2/RELEASE-DECISIONS.json"
        entry = next(e for e in json.loads((ROOT / ledger_rel).read_text(encoding="utf-8"))["entries"] if e["seq"] == 4)
        self.assertEqual((exc["id"], exc["status"]), ("ARCHITECTURE-EXCEPTION-V2-007", "APPROVED — APPLIED"))
        ledger = {"path": ledger_rel, "seq": 4, "id": entry["id"]}
        self.assertEqual(entry["id"], "AISEF_V2_1_B01_ARCHITECTURE_EXCEPTION_V2_007")
        self.assertEqual(exc["owner_decision"]["ledger"], ledger)
        self.assertEqual(exc["applied_before_approval"]["approval"]["ledger"], ledger)
        self.assertEqual(exc["owner_decision"]["owner_text"], entry["owner_text"])   # verbatim
        self.assertIn("the owner did not sign this file", exc["owner_decision"]["recorded_by"])
        self.assertEqual(exc["owner_approval"], amendment["owner_approval"])
        self.assertEqual(exc["owner_approval"]["decision"], exc["owner_decision"]["decision"])
        dossier = exc["promoted_from"]["path"]
        self.assertEqual(exc["promoted_from"]["sha256"], fm._lf_sha(ROOT / dossier))
        # applied before the approval: each commit exists at its recorded time and precedes the commit that wrote seq 4
        approval_commit = git("log", "--format=%H", "-S", entry["id"], "--", ledger_rel).splitlines()[-1]
        applied = exc["applied_before_approval"]["commits"]
        self.assertEqual([c["commit"] for c in applied], exc["replacement"]["implementation_commits"])
        for c in applied:
            self.assertEqual(git("show", "-s", "--format=%cI", c["commit"]), c["date"], c["commit"])
            self.assertEqual(subprocess.run(["git", "merge-base", "--is-ancestor", c["commit"], approval_commit],
                                            cwd=ROOT).returncode, 0, c["commit"])
        # living files are named by the commit they were read at, never by their current bytes
        adr = exc["adr"]
        self.assertEqual(git("rev-parse", f"{adr['read_at']}:{adr['path']}"), adr["git_blob"])
        self.assertIn(f"## {adr['section']}\n", git("show", f"{adr['read_at']}:{adr['path']}") + "\n")
        read = exc["replacement"]["tests_read_at"]
        for rel, blob in read["git_blob"].items():
            self.assertEqual(git("rev-parse", f"{read['commit']}:{rel}"), blob, rel)
        self.assertNotIn("sha256", adr)
        # the RFC as amended and the measured rows
        self.assertEqual(self.text.count(exc["replacement"]["rfc_text"]["markers"]), exc["replacement"]["rfc_text"]["marker_count"])
        self.assertEqual(exc["frozen_rows_measured"]["row_sha256"],
                         {i["id"]: i["row_sha256"] for i in fm.freeze_items(self.text)})

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
            for rel in fm.BASELINE_FILES:
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
