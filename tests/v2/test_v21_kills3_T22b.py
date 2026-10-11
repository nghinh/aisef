"""Mutation survivors of `aisef2/app/verify.py::verify` (batch T22b): what `aisef run --verify` answers for a run
directory whose journal reference cannot be read, whose manifest is not JSON, that is checked against an expected
anchor it cannot match, whose record's spend was lowered alone, and for a run that was priced.

`verify` reads RUN.json and the evidence beside it; a hand-edited or damaged directory is a finding (REFUTED, a problem
that names what could not be trusted), never a traceback and never a false VERIFIED. Offline: the fake client and the
fake provider of test_app_run. Two runs are executed for the whole file (one priced) and each test works on its own
copy of the directory."""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import run as R  # noqa: E402
from aisef2.app import settings  # noqa: E402
from aisef2.app.verify import verify  # noqa: E402
from tests.v2 import test_app_run as base  # noqa: E402
from tests.v2 import test_v21_continue_usage as priced  # noqa: E402

_RUNS: dict[bool, base.ProductBase] = {}


def _executed(prices: bool) -> base.ProductBase:
    """The fixture of one executed run (S1 committed by the fake developer), built once: a ProductBase constructed for
    its setUp alone, as test_s2_kills.AppVerify does. `prices`: executed with the price table of test_v21_continue_usage."""
    if prices not in _RUNS:
        fx = base.ProductBase("setUp")
        try:
            fx.setUp()
            if prices:
                fx.settings = settings.load({**base.SETTINGS, "prices": priced.PRICES})
            fx.execute()
        except BaseException:
            fx.doCleanups()     # a fixture that is never stored would leave its os.environ / scanner patches behind
            raise
        _RUNS[prices] = fx
    return _RUNS[prices]


def tearDownModule() -> None:
    while _RUNS:
        _RUNS.popitem()[1].doCleanups()


@unittest.skipUnless(os.name == "posix", "the fake client is a script started by its shebang")
class ExecutedRun(unittest.TestCase):
    """A copy of an executed run's directory that verifies untouched; no tests of its own."""

    prices = False

    def setUp(self) -> None:
        fx = _executed(self.prices)
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.out = pathlib.Path(t.name).resolve() / "out"
        shutil.copytree(fx.tmp / "out", self.out)
        self.project = fx.project
        self.rec = json.loads((self.out / "RUN.json").read_text(encoding="utf-8"))
        if not self.prices:      # so that a REFUTED below is the edit's doing
            self.assertEqual(verify(self.project, self.out)["verdict"], "VERIFIED")

    def with_record(self, **changes) -> dict:
        """The record as if the run had written it so: RUN.json rewritten, EVIDENCE.json made again, so the manifest
        is not what refutes it (as test_app_units.Verification.with_record)."""
        (self.out / "RUN.json").write_text(json.dumps({**self.rec, **changes}), encoding="utf-8")
        (self.out / R.MANIFEST).write_text(json.dumps(R.evidence_manifest(self.out)), encoding="utf-8")
        return verify(self.project, self.out)


class JournalReferenceUnreadable(ExecutedRun):
    """A RUN.json whose journal reference cannot be read is REFUTED, never an exception, and the problem that carries
    the cause says it is the journal that was not readable. Pins aisef2/app/verify.py::verify [84, 85, 86, 157]."""

    def refuted_unreadable(self, journal: dict, cls: str) -> None:
        v = self.with_record(journal=journal)
        self.assertEqual(v["verdict"], "REFUTED", v)
        named = [p for p in v["problems"] if cls in p]
        self.assertEqual(len(named), 1, v["problems"])       # the cause, once, as the class the operator can look up
        self.assertIn("journal", named[0])                   # and about which artifact: not a bare class name
        self.assertEqual(v["journal_events"], 0, v)          # nothing was read, so nothing is claimed of it

    def test_a_journal_file_that_is_absent(self):          # [84] OSError: FileNotFoundError
        self.refuted_unreadable({**self.rec["journal"], "path": "run/journals/absent.jsonl"}, "FileNotFoundError")

    def test_a_journal_reference_without_a_path(self):     # [85] KeyError
        self.refuted_unreadable({k: v for k, v in self.rec["journal"].items() if k != "path"}, "KeyError")

    def test_a_journal_path_that_is_not_a_path(self):      # [86] TypeError
        self.refuted_unreadable({**self.rec["journal"], "path": 7}, "TypeError")


class ManifestThatIsNotJson(ExecutedRun):
    """An EVIDENCE.json that cannot be parsed refutes the directory: no anchor is derivable, and the problem names the
    file and that it is not JSON. Pins aisef2/app/verify.py::verify [136]."""

    def test_a_corrupt_manifest_is_refuted_naming_the_file_and_why(self):
        (self.out / R.MANIFEST).write_text("{not json", encoding="utf-8")
        v = verify(self.project, self.out)
        self.assertEqual((v["verdict"], v["evidence_anchor"]), ("REFUTED", None), v)
        named = [p for p in v["problems"] if R.MANIFEST in p]
        self.assertEqual(len(named), 1, v["problems"])
        reason = named[0].replace(R.MANIFEST, "").lower()     # the reason, not just the file's own ".json"
        self.assertTrue("json" in reason or "pars" in reason, named[0])


class ExpectedAnchor(ExecutedRun):
    """`--expect-anchor` rejects every directory whose manifest does not give that anchor, including one whose manifest
    is gone (docs/v2.1/ANCHOR-THREAT-MODEL.md), and a match carries the limit of what it proves.
    Pins aisef2/app/verify.py::verify [138, 110]."""

    def test_a_directory_without_its_manifest_is_refuted_not_a_crash(self):          # [138]
        anchor = R.anchor_in(self.out)
        self.assertRegex(anchor, r"^[0-9a-f]{64}$")
        (self.out / R.MANIFEST).unlink()
        v = verify(self.project, self.out, expect_anchor=anchor)
        self.assertEqual((v["verdict"], v["evidence_anchor"]), ("REFUTED", None), v)
        self.assertTrue(any("anchor" in p for p in v["problems"]), v["problems"])

    def test_another_anchor_is_refuted_and_both_are_named_by_their_prefix(self):
        anchor = R.anchor_in(self.out)
        other = "f" * 64 if not anchor.startswith("f") else "e" * 64
        v = verify(self.project, self.out, expect_anchor=other)
        self.assertEqual((v["verdict"], v["evidence_anchor"]), ("REFUTED", anchor), v)
        named = [p for p in v["problems"] if "anchor" in p]
        self.assertEqual(len(named), 1, v["problems"])
        self.assertIn(anchor[:12], named[0])
        self.assertIn(other[:12], named[0])

    def test_a_match_says_where_the_limit_of_what_it_proves_is_written(self):        # [110]
        anchor = R.anchor_in(self.out)
        v = verify(self.project, self.out, expect_anchor=anchor)
        self.assertEqual((v["verdict"], v["problems"]), ("VERIFIED", []), v)
        self.assertEqual(len(v["notes"]), 1, v["notes"])
        self.assertIn("docs/v2.1/ANCHOR-THREAT-MODEL.md", v["notes"][0])
        self.assertEqual(verify(self.project, self.out)["notes"], [])      # without an expected anchor nothing is claimed

    def test_the_match_of_a_forged_directory_carries_it_too(self):
        """The very case the note exists for: the directory and the anchor store were both rewritten, the match holds."""
        log = next((self.out / "sessions").glob("S1.developer.*.jsonl"))
        log.write_text(log.read_text(encoding="utf-8").replace('"done"', '"done (rewritten)"'), encoding="utf-8")
        forged = R.evidence_manifest(self.out)
        self.assertNotEqual(R.anchor_of(forged), R.anchor_in(self.out))        # the rewrite changed what the anchor binds
        (self.out / R.MANIFEST).write_text(json.dumps(forged, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        v = verify(self.project, self.out, expect_anchor=R.anchor_of(forged))
        self.assertEqual(v["verdict"], "VERIFIED", v)
        self.assertEqual(len(v["notes"]), 1, v["notes"])
        self.assertIn("ANCHOR-THREAT-MODEL.md", v["notes"][0])


class SpendLoweredAlone(ExecutedRun):
    """A record whose spent counter was lowered while the sessions' streams, the ledger and the journal were not
    touched is refuted by the spend account, and the problem names the account and the counter that differs.
    Pins aisef2/app/verify.py::verify [147]."""

    def test_the_counter_that_differs_is_named_and_the_ones_that_agree_are_not(self):
        spent = self.rec["budget"]["spent"]
        self.assertGreater(spent["output_tokens"], 0)
        lowered = {**self.rec["budget"], "spent": {**spent, "output_tokens": spent["output_tokens"] - 1}}
        v = self.with_record(budget=lowered)
        self.assertEqual(v["verdict"], "REFUTED", v)
        named = [p for p in v["problems"] if "output_tokens" in p]
        self.assertEqual(len(named), 1, v["problems"])
        self.assertTrue(any(w in named[0] for w in ("spend", "spent", "budget")), named[0])   # the account it belongs to
        for agreeing in ("provider_requests", "turns", "input_tokens"):
            self.assertNotRegex(named[0], rf"\b{agreeing}\b")


class PricedRun(ExecutedRun):
    """A run executed with a price table verifies untouched: the account is re-derived with the record's own
    `settings.prices`, so a run whose cost was known is not refuted as 'usage is not what the evidence re-derives'.
    Pins aisef2/app/verify.py::verify [149, 164]."""

    prices = True

    def test_a_priced_run_verifies_and_its_cost_stays_known(self):
        self.assertEqual(self.rec["usage"]["cost"]["status"], "known", self.rec["usage"])     # not vacuous: prices used
        self.assertEqual(self.rec["settings"]["prices"], priced.PRICES)
        v = verify(self.project, self.out)
        self.assertEqual((v["verdict"], v["problems"]), ("VERIFIED", []), v)


if __name__ == "__main__":
    unittest.main()
