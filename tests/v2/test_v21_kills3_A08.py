"""V2.1 (owner B-03, batch A08): two decisions of aisef2/app/lineage.py that no earlier kill file pins.

* `reconcile` names a merge the kernel made "identified" (left out of the continuation by name) only when its second
  parent is the candidate of a `proof/verified` event of the run. No journal event but `proof/verified` has a
  `candidate` field today (every format's schemas are closed: format3.validate refuses unknown fields), so the reader
  never hands `reconcile` an event that makes the rule observable: over reader-produced events the type test is
  unobservable. The function's own rule is what is pinned here, with a hand-made event list of every other type of the
  vocabulary naming a candidate (and so any type added later), for the day one of them names a candidate it did not
  prove: a merge nothing proved must stay a commit nothing identifies.
* `usage_lineage` totals the lineage's cost only when every run's cost value is a number; `0` and `2` — JSON integers,
  what `round(0, 6)` gives — are numbers. Only a null value makes the total unknown.

Offline; a scratch git repository and scratch run directories."""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import lineage  # noqa: E402
from aisef2.arch.enums import EventType  # noqa: E402
from aisef2.journal.event import Event  # noqa: E402

PRICES = {"currency": "USD", "input_per_mtok": 1.0, "cache_read_per_mtok": 0.1, "cache_write_per_mtok": 1.25,
          "output_per_mtok": 4.0, "source": "test table", "effective_date": "2026-10-06"}


def git(cwd: pathlib.Path, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")} | {
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, encoding="utf-8", env=env,
                          check=True).stdout.strip()


class ReconcileIdentifiesAMergeByAProvedCandidateOnly(unittest.TestCase):
    """reconcile — "L182 And swapped" (candidates: `type == proof/verified and candidate` -> `or`): the map from a
    candidate to its story is built from `proof/verified` events and from nothing else. A merge on main whose second
    parent is a candidate that an event merely names — a candidate nothing proved — is a commit nothing identifies
    (`identified` False: `continue` refuses it unless the operator leaves it out by name); one whose second parent is a
    proved candidate of an open story is the kernel's merge of it (identified, with its story). Pins
    aisef2/app/lineage.py::reconcile [26]."""

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.run_dir = pathlib.Path(t.name) / "run"
        repo = self.run_dir / "repo"
        repo.mkdir(parents=True)
        git(repo, "init", "-q", "-b", "main")
        (repo / "a.txt").write_text("a\n", encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "baseline")
        self.baseline = git(repo, "rev-parse", "HEAD")
        git(repo, "checkout", "-q", "-b", "candidate")
        (repo / "b.txt").write_text("b\n", encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "the developer's candidate")
        self.candidate = git(repo, "rev-parse", "HEAD")
        git(repo, "checkout", "-q", "main")
        git(repo, "merge", "-q", "--no-ff", "-m", f"merge {self.candidate[:12]}", "candidate")
        self.merged = git(repo, "rev-parse", "main")
        self.assertNotEqual(self.merged, self.baseline)

    def reconcile(self, *events: Event) -> dict:
        begin = Event(0, "story/begin", {"story_id": "S2"}, 0.0)
        return lineage.reconcile(self.run_dir, [begin, *events], self.baseline, False)

    def test_an_event_that_only_names_a_candidate_does_not_identify_its_merge(self):
        # one event of every other type of the vocabulary, each naming the candidate (the story brackets are left
        # alone: they decide which stories are open, not which candidates are proved)
        others = sorted(t.value for t in EventType if t.value not in ("proof/verified", "story/begin", "story/end"))
        self.assertIn("probe/evaluated", others)
        named = [Event(n, kind, {"story_id": "S2", "candidate": self.candidate}, 0.0) for n, kind in enumerate(others, 1)]
        got = self.reconcile(*named)
        self.assertEqual([(i["commit"], i["operation"], i["identified"]) for i in got["items"]],
                         [(self.merged, "unknown", False)])
        self.assertEqual(got["unidentified"], got["items"])          # what `continue` refuses without --leave-out-unidentified

    def test_a_proved_candidate_identifies_the_kernels_merge_of_it_with_its_story(self):
        proved = Event(1, "proof/verified", {"story_id": "S2", "candidate": self.candidate}, 0.0)
        got = self.reconcile(proved)
        self.assertEqual([(i["commit"], i["operation"], i["story"], i["identified"]) for i in got["items"]],
                         [(self.merged, "merge", "S2", True)])
        self.assertEqual(got["unidentified"], [])


class AnIntegerCostIsAKnownCost(unittest.TestCase):
    """usage_lineage — "L324 element 0 dropped" (`isinstance(v, (int, float))` -> `(float,)`): the lineage's cost is
    known exactly when every run's cost value is a number, and then it is their sum. A value can be a JSON integer —
    `usage.usage` gives `0`, not `0.0`, when prices are set, no session is priced and the preflight ledger does not
    read (`round(0, 6)`), and that record is what `usage_lineage` takes as `own` — and a total that does not count an
    integer as a number says "unknown" of a lineage whose every cost is a number. Pins
    aisef2/app/lineage.py::usage_lineage [56]."""

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        root = pathlib.Path(t.name)
        self.pred = root / "first"                    # a recorded run that used nothing: its cost is a known 0.0
        self.pred.mkdir()
        (self.pred / "RUN.json").write_text("{}\n", encoding="utf-8")
        self.child = root / "second"

    def total(self, value) -> dict:
        own = {"tokens": {"input": 7}, "cost": {"value": value, "status": "known"}}
        got = lineage.usage_lineage(self.pred, self.child, own, PRICES)
        self.assertEqual(got["runs"][0]["cost"]["value"], 0.0)               # the predecessor's cost is known
        self.assertEqual([r["run"] for r in got["runs"]], [str(self.pred), "this run"])
        return got

    def test_zero_and_a_whole_number_are_numbers(self):
        self.assertEqual(self.total(0)["cost"], {"value": 0.0, "status": "known"})
        self.assertEqual(self.total(2)["cost"], {"value": 2.0, "status": "known"})

    def test_a_null_value_is_what_makes_it_unknown(self):
        got = self.total(None)["cost"]
        self.assertIsNone(got["value"])
        self.assertTrue(got["status"].startswith("unknown"), got)


if __name__ == "__main__":
    unittest.main()
