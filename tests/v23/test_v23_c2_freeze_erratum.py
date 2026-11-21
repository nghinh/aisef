"""L1-QUAL (W1-DESIGN §7 #17; CODE-AUDIT #17): the C2-FINAL history-freeze row is corrected append-only, never edited.

`history_freeze()` froze C2-FINAL over 43 working-tree entries of `C2-FINAL-RUN-HISTORY.json`; no committed version of
that history ever held more than 35, so `c2_closure_audit.py --check` could never pass (red-before: it reports
"C2-FINAL: the first 43 entries are not the frozen ones"). The erratum `docs/v2.3/evidence/l1-qual/C2-FINAL-FREEZE-
ERRATUM.json` (written once by `--erratum`) binds the freeze file's sha256, the committed history and the timing
evidence. `check()` accepts the mismatching row only while that file is exactly what the tree derives; the row stays
INVALIDATED (never VERIFIED_REUSE) and `cite()` refuses it as current evidence. The freeze candidate is byte-identical.
"""

from __future__ import annotations

import contextlib
import copy
import io
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.qualification import c2_closure_audit as c2  # noqa: E402

RED_BEFORE = "C2-FINAL: the first 43 entries are not the frozen ones"


class Erratum(unittest.TestCase):
    def test_red_before_without_the_erratum_check_reports_the_row_exactly_as_before(self):
        with mock.patch.object(c2, "ERRATUM_REL", "docs/v2.3/evidence/l1-qual/NO-SUCH-ERRATUM.json"):
            self.assertEqual(c2.check(), [RED_BEFORE])

    def test_with_the_erratum_check_passes_and_the_row_stays_invalidated(self):
        self.assertEqual(c2.check(), [])
        states = c2.freeze_states()
        self.assertEqual(states.pop("C2-FINAL")[0], "INVALIDATED")
        self.assertEqual(len(states), 12)
        self.assertEqual({s for s, _ in states.values()}, {"VERIFIED_REUSE"})

    def test_an_invalidated_row_cannot_be_cited_as_current_evidence(self):
        with self.assertRaises(LookupError) as refused:
            c2.cite("C2-FINAL")
        self.assertIn("C2-FINAL: INVALIDATED", str(refused.exception))
        self.assertEqual(c2.cite("C2-P0")["state"], "VERIFIED_REUSE")
        with mock.patch.object(c2, "freeze_states", return_value={"C2-P0": ("UNRESOLVED", "x")}), self.assertRaises(LookupError):
            c2.cite("C2-P0")

    def test_the_erratum_binds_the_freeze_file_the_committed_history_and_the_timing(self):
        doc = json.loads((ROOT / c2.ERRATUM_REL).read_text(encoding="utf-8"))
        self.assertEqual(doc, c2.erratum())
        self.assertFalse(c2.ERRATUM_REL.startswith("closure-evidence/"))
        self.assertEqual((doc["phase"], doc["state"]), ("C2-FINAL", "INVALIDATED"))
        self.assertEqual(doc["freeze"]["sha256"], c2.ident(c2.FREEZE_REL)["sha256"])
        self.assertEqual((doc["freeze"]["row"]["entry_count"], doc["history"]["entries"], doc["history"]["max_committed_entries"],
                          doc["history"]["entries_at_head_when_written"]), (43, 35, 35, 35))
        self.assertFalse(doc["history"]["file_sha256_when_written_is_a_committed_version"])
        for rel in (c2.FREEZE_REL, doc["history"]["path"]):     # the v2.2-era evidence itself is never edited
            self.assertEqual(subprocess.run(["git", "-C", str(ROOT), "diff", "--quiet", "HEAD", "--", rel]).returncode, 0, rel)
        self.assertEqual(len(c2.git("log", "--format=%H", "HEAD", "--", c2.FREEZE_REL).split()), 1)   # committed once

    def test_a_stale_or_edited_erratum_is_refused_and_the_row_is_reported_again(self):
        good, load = c2.erratum(), c2.load
        for name, change in (("claims reuse", lambda d: d.update(state="VERIFIED_REUSE")),
                             ("another freeze file", lambda d: d["freeze"].update(sha256="0" * 64)),
                             ("another history", lambda d: d["history"].update(entries=43)),
                             ("other timing", lambda d: d["history"].update(entries_at_head_when_written=27))):
            bad = copy.deepcopy(good)
            change(bad)
            with self.subTest(name), mock.patch.object(c2, "load", side_effect=lambda rel, b=bad: b if rel == c2.ERRATUM_REL else load(rel)):
                self.assertEqual(c2.check(), [RED_BEFORE, f"{c2.ERRATUM_REL} is not what this tree derives for C2-FINAL"])

    def test_the_writer_writes_once_and_only_for_an_invalidated_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            at = pathlib.Path(tmp) / "ERRATUM.json"
            with mock.patch.object(c2, "ERRATUM_REL", str(at)), contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertEqual(c2.main(["--erratum"]), 0)
                self.assertEqual(json.loads(at.read_text(encoding="utf-8")), c2.erratum())
                self.assertEqual(c2.main(["--erratum"]), 1)
                self.assertIn("never rewritten", err.getvalue())
                with mock.patch.object(c2, "freeze_states", return_value={"C2-FINAL": ("VERIFIED_REUSE", "x")}):
                    at.unlink()
                    self.assertEqual(c2.main(["--erratum"]), 1)
                    self.assertFalse(at.exists())


if __name__ == "__main__":
    unittest.main()
