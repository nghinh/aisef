"""V2.1 (C): a review finding is acted on only when the kernel's own probe reproduces it (aisef2/app/review_verify.py).

* The five defects release smoke #2's reviewer found and 2.0.0 shipped as "advisory" (360° §3.5: all five reproduced on
  the final main) are regressions here. Each is the reviewer's finding with a reproducer in the cli_invocation
  grammar, run against a LedgerLock variant carrying that defect (the reference with one change, the defect's shape)
  — CONFIRMED — and against the correct reference — NOT_REPRODUCED: a false finding never blocks.
* Triage: no reproducer, a clause of no requirement, a subject outside the product, an observation the probe refuses
  or has no calibration for — UNVERIFIABLE; below the severity floor, or under the `advisory` policy, nothing blocks.
* The limit, measured rather than hidden: a reproducer that states a behaviour the requirement does not demand is
  CONFIRMED when the candidate does not do it — the cited clause is there for a person to judge.
* The product path (`aisef run`, fake client): a confirmed finding under `fix-loop` blocks (REVIEW_FINDING, the
  REVIEW limit bounds the loop), and the developer's retry prompt carries the finding; without `review` in the
  settings the same review is advisory, as in 2.0.0."""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import review_verify as V  # noqa: E402
from aisef2.app import settings  # noqa: E402
from tests.v2.test_app_run import SETTINGS, ProductBase  # noqa: E402

REFERENCE = ROOT / "tests/v2/fixtures/workloads/ledgerlock-reference/reference/ledgerlock"
REQUIREMENTS = {"R-7": object(), "R-9": object()}
MAIN = {"kind": "cli_invocation", "locator": "ledgerlock:__main__"}


def _ledger_bytes(*lines_of) -> bytes:
    """A valid LedgerLock file, written by the reference's own Ledger.put in a process of its own (this one's import
    path is never touched)."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "L")
        code = ("import json, sys; from ledgerlock.ledger import Ledger\n"
                "for n, (k, v) in enumerate(json.loads(sys.argv[2]), 1): Ledger(sys.argv[1]).put(k, v, 'r-' + k, n)")
        subprocess.run([sys.executable, "-c", code, path, json.dumps(lines_of)], cwd=REFERENCE.parent, check=True,
                       capture_output=True, encoding="utf-8")
        return pathlib.Path(path).read_bytes()


VALID = _ledger_bytes(("a", 1))
NO_HASH = json.dumps({k: v for k, v in json.loads(VALID).items() if k != "hash"}).encode() + b"\n"


def reproducer(clause, argv, exit_code, workspace=None):
    return {"clause": clause, "subject": MAIN,
            "stimulus": {"argv": argv, "stdin": None, "workspace": workspace or {}, "pre": []},
            "observable": {"exit_code": exit_code, "within_s": 20}}


#: the five shipped defects (smoke #2 reviewer sessions STORY-04-01 #1, STORY-04-02 #3): the finding as the reviewer
#: wrote it, a reproducer of the behaviour its clause demands, and the defect's shape as a change of the reference
DEFECTS = {
    "repair-utf8-crash": ("R-7/1", reproducer("R-7/1", ["repair-tail", "<ws>/L"], 0,
                                              {"L": {"bytes_hex": (VALID + b'{"key":"\xc3').hex()}}),
                          ("ledger.py", "        return f.read()\n", "        data = f.read()\n        data.decode('utf-8')\n        return data\n")),
    "empty-rid-exit": ("R-9/2", reproducer("R-9/2", ["put", "<ws>/L", "k", "1", "--rid", "", "--ts", "1"], 2,
                                           {"L": {"bytes_hex": VALID.hex()}}),
                       ("cli.py", "    except ValueError as e:\n        sys.stderr.write(f\"usage error: {e}\\n\")\n        return EXIT_USAGE\n", "")),
    "r93-repair-missing": ("R-9/3", reproducer("R-9/3", ["repair-tail", "<ws>/missing.jsonl"], 3),
                           ("ledger.py", "        raw = _read_raw(self.path)\n        records, unparsable, unterminated = scan(raw)",
                            "        raw = _read_raw(self.path, missing_ok=True)\n        records, unparsable, unterminated = scan(raw)")),
    "r93-snapshot-missing": ("R-9/3", reproducer("R-9/3", ["snapshot", "<ws>/missing.jsonl"], 3),
                             ("ledger.py", "        records, _ = self._records(missing_ok=False)",
                              "        records, _ = self._records(missing_ok=True)")),
    "r95-keyerror-crash": ("R-9/5", reproducer("R-9/5", ["verify", "<ws>/L"], 5, {"L": {"bytes_hex": NO_HASH.hex()}}),
                           ("ledger.py", '        intact = rec.get("hash") == line_hash(prev, rec)',
                            '        intact = rec["hash"] == line_hash(prev, rec)')),
}


class Probe(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = pathlib.Path(self._tmp.name)

    def checkout(self, name: str, change=None) -> pathlib.Path:
        root = self.tmp / name
        shutil.copytree(REFERENCE, root / "ledgerlock", ignore=shutil.ignore_patterns("__pycache__"))
        if change:
            f, old, new = change
            p = root / "ledgerlock" / f
            text = p.read_text(encoding="utf-8")
            self.assertEqual(text.count(old), 1, f"the defect's shape no longer matches the reference: {old!r}")
            p.write_text(text.replace(old, new), encoding="utf-8")
        return root

    def verify(self, finding: dict, root: pathlib.Path) -> V.Verification:
        return V.verify(finding, requirements=REQUIREMENTS, product_roots=("ledgerlock",), root=str(root),
                        revision="0" * 40, timeout_s=60, interpreter=sys.executable)


@unittest.skipUnless(os.name == "posix" or sys.platform == "win32", "the probe runs on both")
class HistoricalDefects(Probe):
    def test_each_shipped_defect_is_confirmed_on_its_shape_and_not_on_the_reference(self):
        reference = self.checkout("reference")
        for fid, (clause, rep, change) in DEFECTS.items():
            self.assertEqual(rep["clause"], clause)
            finding = {"id": fid, "blocking": True, "severity": "high", "summary": fid, "reproducer": rep}
            with self.subTest(fid):
                defective = self.verify(finding, self.checkout(fid, change))
                self.assertEqual(defective.status, V.CONFIRMED, defective)
                self.assertTrue(V.blocks(defective, finding, "fix-loop", "high"))
                self.assertEqual(defective.evidence(), "probe:probe.cli_invocation:REFUTED")
                correct = self.verify(finding, reference)
                self.assertEqual(correct.status, V.NOT_REPRODUCED, correct)    # the false finding
                self.assertFalse(V.blocks(correct, finding, "fix-loop", "low"))


class Triage(Probe):
    def setUp(self) -> None:
        super().setUp()
        self.root = self.checkout("reference")
        self.rep = DEFECTS["r93-snapshot-missing"][1]

    def status(self, **change) -> str:
        return self.verify({"id": "x", "severity": "critical", "reproducer": {**self.rep, **change}}, self.root).status

    def test_what_cannot_be_verified_is_triage(self):
        self.assertEqual(self.verify({"id": "x", "summary": "looks wrong"}, self.root).status, V.UNVERIFIABLE)
        self.assertEqual(self.status(clause="R-404/1"), V.UNVERIFIABLE)                      # no such requirement
        self.assertEqual(self.status(subject={"kind": "cli_invocation", "locator": "json:__main__"}), V.UNVERIFIABLE)
        self.assertEqual(self.status(observable={"exit_code": 3}), V.UNVERIFIABLE)             # no window: refused
        self.assertEqual(self.status(observable={"vibes": "bad", "within_s": 5}), V.UNVERIFIABLE)
        bad = {"id": "x", "severity": "critical", "reproducer": {**self.rep, "extra": 1}}
        self.assertEqual(self.verify(bad, self.root).status, V.UNVERIFIABLE)

    def test_severity_floor_and_policy(self):
        defective = self.checkout("d", DEFECTS["r93-snapshot-missing"][2])
        for severity, policy, floor, blocks in (("medium", "fix-loop", "high", False), ("high", "fix-loop", "high", True),
                                                ("critical", "advisory", "low", False), (None, "fix-loop", "medium", False)):
            finding = {"id": "x", "severity": severity, "reproducer": self.rep}
            v = self.verify(finding, defective)
            self.assertEqual(v.status, V.CONFIRMED)
            self.assertEqual(V.blocks(v, finding, policy, floor), blocks, (severity, policy, floor))

    def test_the_limit_a_misread_requirement_is_confirmed(self):
        """The reproducer says snapshot of a missing file exits 4 (§9 says 3): the reference exits 3, so the stated
        behaviour does not hold and the finding is CONFIRMED. A confirmation proves the candidate does not do what the
        finding states — never that the finding read the requirement right; the cited clause is for a person."""
        misread = {"id": "x", "severity": "high", "reproducer": {**self.rep, "observable": {"exit_code": 4, "within_s": 20}}}
        self.assertEqual(self.verify(misread, self.root).status, V.CONFIRMED)


@unittest.skipUnless(os.name == "posix", "the fake client is a script started by its shebang")
class ProductPath(ProductBase):
    """The calc project: the developer writes a correct add; the reviewer states that add(2, 2) returns 5 (R-ADD/1)."""

    FINDING = {"id": "add-misread", "blocking": True, "severity": "high", "summary": "add(2, 2) must return 5",
               "reproducer": {"clause": "R-ADD/1", "subject": {"kind": "python_callable", "locator": "app.calc:add"},
                              "stimulus": {"args": [2, 2]}, "observable": {"returns": 5, "within_s": 10}}}

    def setUp(self) -> None:
        super().setUp()
        (self.client.parent / "review.json").write_text(json.dumps({"findings": [self.FINDING]}), encoding="utf-8")

    def test_fix_loop_blocks_a_confirmed_finding_and_tells_the_developer(self):
        self.settings = settings.load({**SETTINGS, "review": {"policy": "fix-loop", "min_severity": "high"}})
        rec = self.execute()
        self.assertEqual(rec["story_outcomes"], {"S1": ["RETRY", "ROLLBACK"]})
        self.assertEqual(rec["delivery_verdict"], "FAIL")
        failures = [e.data["code"] for e in self.journal().events if e.type == "failure/observed"]
        self.assertEqual(failures, ["REVIEW_FINDING", "REVIEW_FINDING"])
        rows = [e.data for e in self.journal().events if e.type == "gate/check" and e.data["check"] == "S1:review:add-misread"]
        self.assertTrue(rows and all(not r["passed"] and "probe:probe.python_callable_v2:REFUTED" in r["detail"] for r in rows))
        from aisef2.app import feedback      # what Developer.implement puts in the retry prompt, from the journal
        told = feedback.retry_feedback(((e.seq, e.type, e.data) for e in self.journal().events), "S1", self.project)
        self.assertIn("REVIEW_FINDING (owner REVIEW)", told)
        self.assertIn("add(2, 2) must return 5", told)
        self.assertIn('"clause": "R-ADD/1"', told)

    def test_without_a_review_policy_the_same_review_is_advisory_as_in_2_0_0(self):
        rec = self.execute()
        self.assertEqual((rec["story_outcomes"], rec["delivery_verdict"]), ({"S1": ["COMMIT"]}, "PASS"))
        rows = [e.data for e in self.journal().events if e.type == "gate/check" and e.data["check"] == "S1:review:add-misread"]
        self.assertEqual([r["passed"] for r in rows], [True])
        self.assertIn('"verification": "CONFIRMED"', rows[0]["detail"])        # verified, recorded, not acted on


if __name__ == "__main__":
    unittest.main()
