"""V2.1 (B, V21-37): file_artifact's `python_imports` class counts import statements by syntax.

Release smoke #2 rolled back a correct story: the approved LedgerLock criterion BC-V22-S-10-a counted, with a line
regex, the docstring line `    from disk without trusting …` (ledgerlock/ledger.py:261) as an import outside the
allowed set (S6-SMOKE-2-FALSE-ROLLBACK-S10A). Here the real probe, on the LedgerLock reference package: the approved
regex contract reproduces the false refutation; both unapproved drafts (docs/v2.1/drafts/) are SATISFIED on it and
REFUTED by a real import outside the set (positive and negative controls). Offline: the probe reads a directory."""

from __future__ import annotations

import json
import pathlib
import shutil
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import BehaviorVerdict, Enforcement  # noqa: E402
from aisef2.probe import file_artifact as fa  # noqa: E402
from aisef2.probe.protocol import ExecutionEnv, RevisionRef, run_probe  # noqa: E402
from aisef2.product.contract import BehaviorContract  # noqa: E402
from aisef2.product.spec import ProductProofSpec  # noqa: E402

REFERENCE = ROOT / "tests/v2/fixtures/workloads/ledgerlock-reference/reference/ledgerlock"
APPROVED = next(c for c in json.loads((ROOT / "closure-evidence/v2/release/LEDGERLOCK-PROJECT.json").read_text(
    encoding="utf-8"))["contracts"] if c["id"] == "BC-V22-S-10-a")
DRAFTS = json.loads((ROOT / "docs/v2.1/drafts/LEDGERLOCK-BC-V22-S-10-a-r2.DRAFT.json").read_text(encoding="utf-8"))
SMOKE2_LINE = '\n\ndef _reread(path):\n    """Re-read the ledger\n    from disk without trusting any cached in-memory state."""\n    return path\n'


def observe(contract: dict, package: pathlib.Path) -> BehaviorVerdict | str:
    c = BehaviorContract.from_json(contract)
    spec = ProductProofSpec.create(contract_id=c.id, probe_id=fa.PROBE_ID, probe_digest=fa.DIGEST,
                                   probe_input={"subject": {"kind": c.subject.kind.value, "locator": c.subject.locator},
                                                "stimulus": c.stimulus, "observable": c.observable,
                                                "subject_absence": c.subject_absence.value},
                                   candidate_expectation=BehaviorVerdict.SATISFIED, compiler_id="test", compiler_digest="0" * 64)
    rec = run_probe(fa.FileArtifactProbe(), spec, RevisionRef("0" * 40, str(package.parent)),
                    ExecutionEnv(sys.executable, 30.0, Enforcement.FULL))
    return getattr(rec.result, "behavior_verdict", None) or str(rec.result)


class Controls(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def package(self, extra: str = "") -> pathlib.Path:
        root = pathlib.Path(self._tmp.name) / f"c{len(list(pathlib.Path(self._tmp.name).iterdir()))}"
        shutil.copytree(REFERENCE, root / "ledgerlock", ignore=shutil.ignore_patterns("__pycache__"))
        with open(root / "ledgerlock" / "ledger.py", "a", encoding="utf-8") as f:
            f.write(extra)
        return root / "ledgerlock"

    def test_the_approved_regex_reproduces_the_false_rollback(self):
        self.assertEqual(observe(APPROVED, self.package()), BehaviorVerdict.SATISFIED)
        self.assertEqual(observe(APPROVED, self.package(SMOKE2_LINE)), BehaviorVerdict.REFUTED)   # V21-37

    def test_each_draft_holds_on_the_smoke2_shape_and_refutes_a_real_import(self):
        for name, option in DRAFTS["options"].items():
            with self.subTest(name):
                self.assertEqual(observe(option["contract"], self.package()), BehaviorVerdict.SATISFIED)
                self.assertEqual(observe(option["contract"], self.package(SMOKE2_LINE)), BehaviorVerdict.SATISFIED)
                self.assertEqual(observe(option["contract"], self.package("\nimport yaml\n")), BehaviorVerdict.REFUTED)
                self.assertEqual(observe(option["contract"], self.package("\nfrom requests.adapters import HTTPAdapter\n")),
                                 BehaviorVerdict.REFUTED)
                self.assertEqual(observe(option["contract"], self.package("\n# import yaml\nx = 'import yaml'\n")),
                                 BehaviorVerdict.SATISFIED)

    def test_the_two_drafts_differ_where_the_draft_says(self):
        a, b = (DRAFTS["options"][k]["contract"] for k in ("A_enumerated", "B_stdlib"))
        self.assertEqual(observe(a, self.package("\nimport sqlite3\n")), BehaviorVerdict.REFUTED)     # not in §10's list
        self.assertEqual(observe(b, self.package("\nimport sqlite3\n")), BehaviorVerdict.SATISFIED)   # in the stdlib
        self.assertEqual(observe(a, self.package("\nimport unittest\n")), BehaviorVerdict.REFUTED)    # the noted deviation

    def test_a_file_that_does_not_parse_is_no_count(self):
        facts = fa.import_facts({"stdlib": True, "allowed": []}, [("x.py", b"def (:\n")])
        self.assertNotIn("matches", facts)
        self.assertEqual(facts["unparsable"], "x.py:1")
        self.assertEqual(fa.verdict_of("python_imports", {"matches": 0}, facts), BehaviorVerdict.REFUTED)

    def test_the_grammar_is_closed(self):
        ok = {"imports_outside": {"stdlib": True, "allowed": []}}
        self.assertEqual(fa.observation_class({"matches": 0, "within_s": 5}, ok), "python_imports")
        for bad in ({"imports_outside": {"stdlib": "yes", "allowed": []}}, {"imports_outside": {"allowed": []}},
                    {"imports_outside": {"stdlib": True, "allowed": ["a.b"]}}, {**ok, "grep": "x"},
                    {**ok, "suffixes": ["py"]}):
            with self.subTest(bad=bad):
                self.assertIsNone(fa.observation_class({"matches": 0, "within_s": 5}, bad))
        self.assertIsNone(fa.observation_class({"matches": 0}, ok))      # no window: no meaning


if __name__ == "__main__":
    unittest.main()
