"""validation/qualification/v21_requalification.py: a stopped and restarted campaign gets a revision of the scope
manifest that names what it supersedes by its bytes, and --check reports every version that moved since."""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from validation.qualification import v21_requalification as Q  # noqa: E402

SCOPE = {"mutation": {"targets": {"a.py::f": {"kill_tests": ["tests/v2/test_a.py"], "mutants": 3}}},
         "checkers": ["c1"], "q5_corpus": ["i1"]}


class Revisions(unittest.TestCase):
    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = pathlib.Path(t.name)
        (self.root / Q.OUT_REL).parent.mkdir(parents=True)
        for p in (mock.patch.object(Q, "ROOT", self.root), mock.patch.object(Q, "scope", return_value=SCOPE)):
            p.start()
            self.addCleanup(p.stop)

    def write(self, n: int, doc: dict) -> None:
        (self.root / Q.revision_rel(n)).write_text(json.dumps(doc), encoding="utf-8")

    def test_revisions_are_numbered_after_the_first_and_the_newest_is_found(self):
        self.assertEqual(Q.revision_rel(1), Q.OUT_REL)
        self.assertEqual(Q.revision_rel(3), "closure-evidence/v2/v2.1/REQUALIFICATION-MANIFEST-3.json")
        self.assertEqual(Q.newest(self.root), 0)
        self.write(1, SCOPE)
        self.write(2, SCOPE)
        self.assertEqual(Q.newest(self.root), 2)
        self.write(4, SCOPE)                       # a gap: revision 3 is missing, so 4 is not reached
        self.assertEqual(Q.newest(self.root), 2)

    def test_a_revision_is_refused_without_its_predecessor_twice_or_without_a_reason(self):
        with self.assertRaisesRegex(SystemExit, "revision 2 needs revision 1"):
            Q.build_revision(2, "why", "", None, None, None)
        self.write(1, {**SCOPE, "base": "b"})
        with self.assertRaisesRegex(SystemExit, "says why"):
            Q.build_revision(2, "  ", "", None, None, None)
        self.write(2, SCOPE)
        with self.assertRaisesRegex(SystemExit, "no revision 2 yet"):
            Q.build_revision(2, "why", "", None, None, None)
        with self.assertRaisesRegex(SystemExit, "needs revision 0"):
            Q.build_revision(1, "why", "", None, None, None)

    def test_check_reads_the_newest_revision_and_reports_what_moved_since(self):
        self.write(1, SCOPE)
        prev_sha = Q._sha(Q.revision_rel(1))
        (self.root / "t0.json").write_text("{}", encoding="utf-8")
        vers = {"harness": {"validation/v2/mutation.py": "aa"}, "kill_files": {"tests/v2/test_a.py": "bb"}}
        self.write(2, {**SCOPE, "supersedes": {"path": Q.revision_rel(1), "sha256": prev_sha}, "versions": vers,
                       "t0": {"path": "t0.json", "sha256": Q._sha("t0.json")}, "execution_order": "declared", "preflight": None})
        with mock.patch.object(Q, "versions", return_value=vers):
            self.assertEqual(Q.check(), [])
        moved = {"harness": {"validation/v2/mutation.py": "zz"}, "kill_files": {"tests/v2/test_a.py": "bb", "tests/v2/test_b.py": "cc"}}
        with mock.patch.object(Q, "versions", return_value=moved):
            self.assertEqual(Q.check(), [f"1 harness changed since {Q.revision_rel(2)}: ['validation/v2/mutation.py']",
                                         f"1 kill files changed since {Q.revision_rel(2)}: ['tests/v2/test_b.py']"])
        (self.root / "t0.json").write_text('{"x": 1}', encoding="utf-8")
        self.write(1, {**SCOPE, "edited": True})
        with mock.patch.object(Q, "versions", return_value=vers):
            self.assertEqual(Q.check(), [f"{Q.revision_rel(2)} does not name revision 1 by its bytes",
                                         f"the t0 record t0.json is not the one {Q.revision_rel(2)} names"])


if __name__ == "__main__":
    unittest.main()
