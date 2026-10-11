"""V2.1 (owner B-03, kills round 3, batch T08a): kill tests for the survivors of aisef2/app/lineage.py's V2.1 mutation
targets `reconcile` and `usage_lineage`.

* `reconcile` decides what a continuation may call the kernel's own effect (an identified merge, a candidate in the
  kernel's worktree) and what it must refuse unless the operator leaves it out by name (an unidentified commit, a main
  that moved back). The earlier kill files drive it only through full runs killed at a window; no assertion of theirs
  depends on a closed story next to a merge-looking commit, a main that moved back, a worktree head main already
  contains, or the cut event's key set. This file builds the run directory's repository directly (a real git
  repository, the journal's events, the cut bytes) and calls `reconcile` with inputs on both sides of each decision.
* `usage_lineage` shows a lineage's cost: a run that has no record or has unaccounted spend never shows its priced
  cost as known. The earlier files read only the lineage's total, in lineages that hold a killed run next to fully
  accounted ones: that total is null either way, so a wrong override of an accounted run is masked. Each combination
  of (recorded, unaccounted) is built here from the evidence files `account_of` derives it from, and read per run
  and in total."""

from __future__ import annotations

import json
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
from aisef2.arch.enums import EventType as T  # noqa: E402
from aisef2.journal import event as ev  # noqa: E402
from aisef2.journal import format3  # noqa: E402

PRICES = {"currency": "USD", "input_per_mtok": 1.0, "cache_read_per_mtok": 0.1, "cache_write_per_mtok": 1.25,
          "output_per_mtok": 4.0, "source": "test table", "effective_date": "2026-10-06"}


def git(cwd, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")} | {
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, encoding="utf-8", env=env,
                          check=True).stdout.strip()


def journal(*rows) -> list:
    """The events `reconcile` is given, from (type, data) rows with seq == index. It reads each event's type and data
    only: story/begin and story/end (`story_id`), proof/verified (`candidate`, `story_id`)."""
    return [ev.Event(n, t, d, 0.0) for n, (t, d) in enumerate(rows)]


class RunDirBase(unittest.TestCase):
    """A run directory whose `repo` is a real repository on `main` holding one commit, `self.base`."""

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(t.name)
        self.run_dir = self.tmp / "run-dir"
        self.repo = self.run_dir / "repo"
        self.repo.mkdir(parents=True)
        git(self.repo, "init", "-q", "-b", "main")
        self.base = self.commit("base")

    def commit(self, name: str) -> str:
        (self.repo / f"{name}.txt").write_text(name + "\n", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", name)
        return git(self.repo, "rev-parse", "HEAD")

    def side(self, branch: str, *names: str, start: str = "main") -> str:
        """A branch off `start` with one commit per name; its tip. main stays checked out."""
        git(self.repo, "checkout", "-q", "-b", branch, start)
        tip = ""
        for name in names:
            tip = self.commit(name)
        git(self.repo, "checkout", "-q", "main")
        return tip

    def merge(self, branch: str, message: str) -> str:
        git(self.repo, "merge", "-q", "--no-ff", "-m", message, branch)
        return git(self.repo, "rev-parse", "HEAD")

    def reconcile(self, events: list, baseline: str | None = None, torn: bool = False) -> dict:
        return lineage.reconcile(self.run_dir, events, baseline or self.base, torn)

    def begin(self, story: str) -> tuple:
        return "story/begin", {"story_id": story, "parent": self.base}

    @staticmethod
    def end(story: str) -> tuple:
        return "story/end", {"story_id": story}

    @staticmethod
    def verified(story: str, candidate: str) -> tuple:
        return "proof/verified", {"story_id": story, "criterion_id": "C1", "candidate": candidate}


class ClosedStory(RunDirBase):
    """A commit on main is the kernel's merge in flight only while the story's attempt is open: `story/end` closes it.
    Authority logic — it decides what a continuation may carry on past without `--leave-out-unidentified`: a
    merge-looking commit (two parents, subject `merge <second parent[:12]>`) of a candidate proved for a story whose
    attempt the journal closed is not the kernel's merge in flight and is refused as unidentified; with the attempt
    open it is.

    Pins aisef2/app/lineage.py::reconcile [28, 58]."""

    def test_a_merge_looking_commit_of_a_closed_story_is_unidentified_and_of_an_open_one_is_the_kernels(self):
        cand = self.side("s1", "cand-s1")
        merged = self.merge("s1", f"merge {cand[:12]}")
        proved = self.verified("S1", cand)

        closed = self.reconcile(journal(self.begin("S1"), proved, self.end("S1")))
        self.assertEqual([(i["commit"], i["operation"], i["identified"]) for i in closed["items"]],
                         [(merged, "unknown", False)])
        self.assertEqual(closed["unidentified"], closed["items"])       # what continue_from refuses without a name

        opened = self.reconcile(journal(self.begin("S1"), proved))
        self.assertEqual([(i["commit"], i["operation"], i["story"], i["identified"]) for i in opened["items"]],
                         [(merged, "merge", "S1", True)])
        self.assertEqual(opened["unidentified"], [])


class MergeItem(RunDirBase):
    """The kernel's merge in flight is reported with the identity the journal gave it: the merge commit, the story, and
    the proved candidate that is the merge's second parent (the report is where the operator sees which candidate was
    left out of the continuation's baseline), `identified`, and the evidence that identified it (it carries the story
    and the candidate's 12-digit prefix). The key set is the record's contract: `aisef bundle continue` prints
    `unconfirmed` as JSON.

    Pins aisef2/app/lineage.py::reconcile [84, 86, 117, 119]."""

    def test_the_identified_merge_names_its_commit_story_candidate_and_evidence(self):
        cand = self.side("s2", "cand-s2")
        merged = self.merge("s2", f"merge {cand[:12]}")
        (item,) = self.reconcile(journal(self.begin("S2"), self.verified("S2", cand)))["items"]
        self.assertEqual(set(item), {"commit", "operation", "story", "candidate", "identified", "why"})
        self.assertEqual((item["commit"], item["operation"], item["story"], item["identified"]),
                         (merged, "merge", "S2", True))
        self.assertEqual(item["candidate"], git(self.repo, "rev-parse", f"{merged}^2"))   # the candidate, in full
        self.assertEqual(item["candidate"], cand)
        self.assertIsInstance(item["why"], str)
        self.assertIn("S2", item["why"])
        self.assertIn(cand[:12], item["why"])


class MainMovedBack(RunDirBase):
    """Main behind the journal's last commit (the operator reset or rewound the run's repository after a crash) is one
    unidentified item — refused by `continue_from` unless left out by name: nothing the journal or git identifies. Its
    machine-read fields are exact (`commit` is read by reconcile's own worktree de-duplication and by the refusal
    message; `identified` decides the refusal) and its reason names the ref and the two ids in order and the cause
    class (main does not descend from the journal's last commit): the refusal prints (commit[:12], why), so the reason
    is how the operator tells this item from a stray commit, which has the same operation and `identified`.

    Pins aisef2/app/lineage.py::reconcile [64, 65, 66, 67, 92, 93, 94, 95, 96, 97, 130, 131]."""

    def test_main_behind_the_last_journaled_commit_is_one_unidentified_item(self):
        second = self.commit("second")
        journaled = journal(self.begin("S1"), ("story/commit", {"story_id": "S1", "revision": second}), self.end("S1"))
        git(self.repo, "reset", "-q", "--hard", self.base)             # main is now behind the journal's last commit
        self.assertEqual(git(self.repo, "rev-parse", "main"), self.base)

        r = self.reconcile(journaled, baseline=second)
        self.assertEqual(len(r["items"]), 1)
        item = r["items"][0]
        self.assertEqual(r["unidentified"], [item])                    # refused unless left out by name
        self.assertEqual(set(item), {"commit", "operation", "identified", "why"})
        self.assertEqual((item["commit"], item["operation"], item["identified"]), (self.base, "unknown", False))
        why = item["why"]
        self.assertIsInstance(why, str)
        self.assertIn(f"main {self.base[:12]}", why)                   # the ref and the id it is at ...
        after = why[why.index(self.base[:12]) + 12:]
        self.assertIn(second[:12], after)                              # ... then the journal's last commit
        self.assertIn("descend", why)                                  # the cause class: main is not a descendant


class UnidentifiedCommit(RunDirBase):
    """A commit on main no journaled operation accounts for is listed unidentified with a reason, and the reason is
    what tells it from the other unidentified kind (main moved back): both are operation `unknown`, `identified`
    False. `continue_from` prints `(commit[:12], why)` of each, up to five, in the refusal an operator reads before
    deciding to leave them out.

    Pins aisef2/app/lineage.py::reconcile [129]."""

    def test_a_stray_commit_is_unidentified_with_a_reason_that_is_not_main_moved_back(self):
        second = self.commit("second")
        stray = self.commit("stray")
        journaled = journal(self.begin("S1"), ("story/commit", {"story_id": "S1", "revision": second}), self.end("S1"))

        r = self.reconcile(journaled, baseline=second)
        (item,) = r["items"]
        self.assertEqual(r["unidentified"], [item])
        self.assertEqual((item["commit"], item["operation"], item["identified"]), (stray, "unknown", False))
        stray_why = item["why"]
        self.assertIsInstance(stray_why, str)
        self.assertTrue(stray_why.strip(), "the refusal lists (commit, why): an empty why tells the operator nothing")

        git(self.repo, "reset", "-q", "--hard", self.base)
        (moved_back,) = self.reconcile(journaled, baseline=second)["items"]
        self.assertEqual((moved_back["operation"], moved_back["identified"]), ("unknown", False))
        self.assertNotEqual(stray_why, moved_back["why"])


class WorktreeHead(RunDirBase):
    """A kernel worktree (`wt-<open story>`) is reported as an unjournaled candidate only when main does not already
    contain its head: a head that main reaches through a merge's second parent is not in main's first-parent listing,
    but its effect is already among the commits listed, and listing it again would report one effect twice. A head
    main does not contain, descending from the journal's last commit, is the identified candidate.

    Pins aisef2/app/lineage.py::reconcile [133, 134]."""

    def test_a_head_main_already_contains_is_not_a_second_item_and_one_it_does_not_is_the_candidate(self):
        self.side("by-hand", "f1", "f2")
        merged = self.merge("by-hand", "by hand")           # not the kernel's convention: parents [base, f2]
        f1 = git(self.repo, "rev-parse", "by-hand~1")
        # the premises: main reaches f1, and f1 is not among the commits reconcile lists from main
        git(self.repo, "merge-base", "--is-ancestor", f1, "main")
        self.assertEqual(git(self.repo, "rev-list", "--first-parent", f"{self.base}..main").split(), [merged])
        git(self.repo, "worktree", "add", "-q", "--detach", str(self.tmp / "wt-S2"), f1)
        outside = self.side("not-merged", "g1", start=self.base)
        git(self.repo, "worktree", "add", "-q", "--detach", str(self.tmp / "wt-S3"), outside)

        items = self.reconcile(journal(self.begin("S2"), self.begin("S3")))["items"]
        self.assertEqual([(i["commit"], i["operation"], i["identified"]) for i in items],
                         [(merged, "unknown", False), (outside, "candidate", True)])
        self.assertEqual(items[1]["story"], "S3")


class CutEvent(RunDirBase):
    """A torn last line is reported as `cut_event`, the record that stands for an event whose effects are not assumed
    undone: exactly `seq` (the verified events before it), `bytes` (the length of the cut line), `type` (the event's
    type when the cut bytes still say it, else null), `stories` (the story ids they still hold, sorted, so the report
    is stable across processes) and `why`. `aisef bundle continue` prints it as JSON with the report; `why` is its
    statement of the module's central rule — the cut record's effects, if any, are among the reconciled items — so
    it is present and not empty (what the sentence says is not asserted).

    Pins aisef2/app/lineage.py::reconcile [20, 52, 55, 54]."""

    def torn_journal(self, line_of_next_event, cut_at) -> tuple[list, str]:
        """The journal file: two whole events, then `cut_at(line)` of the line the third would have been. Returns the
        two events reconcile is given and the cut text."""
        whole = journal(("run/begin", {"journal_format": 3, "run_id": "r"}), self.begin("S1"))
        prev, lines = ev.GENESIS, []
        for e in whole:
            prev = ev.link(prev, e)
            lines.append(ev.encode(e, prev))
        line = ev.encode(line_of_next_event(len(whole)), "0" * 64).rstrip("\n")
        cut = cut_at(line)
        self.assertNotIn("\n", cut)
        path = self.run_dir / lineage.JOURNAL
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(("".join(lines) + cut).encode("utf-8"))
        return whole, cut

    def test_the_cut_event_has_exactly_its_five_fields_and_a_reason(self):
        def commit_of_s2(seq: int) -> ev.Event:
            return ev.Event(seq, "story/commit", {"story_id": "S2", "revision": "a" * 40}, 0.0)
        typed = '"type":"story/commit"'
        for label, cut_at, kind in (("cut before its type, the last field", lambda s: s[:s.index('"type"')], None),
                                    ("cut after its type", lambda s: s[:s.index(typed) + len(typed)], "story/commit")):
            with self.subTest(label):
                events, cut = self.torn_journal(commit_of_s2, cut_at)
                got = self.reconcile(events, torn=True)["cut_event"]
                self.assertEqual(set(got), {"seq", "bytes", "type", "stories", "why"})
                self.assertEqual((got["seq"], got["bytes"], got["type"], got["stories"]),
                                 (len(events), len(cut.encode("utf-8")), kind, ["S2"]))
                self.assertIsInstance(got["why"], str)
                self.assertTrue(got["why"].strip(), "the operator reads why to know the cut record's effects are not "
                                                    "assumed undone")

    def test_a_whole_journal_has_no_cut_event(self):
        self.assertIsNone(self.reconcile(journal(self.begin("S1")))["cut_event"])

    def test_the_stories_the_cut_bytes_hold_are_listed_sorted(self):
        ids = [f"S{n}" for n in range(9, -1, -1)]         # S9 ... S0: ten ids, descending in the bytes
        # a cut probe/evaluated event: its free-form `record` can hold several story ids before the cut. A set's own
        # order differs per process (string hashes are randomised): ten ids come out sorted by chance 1 in 10!
        def probe(seq: int) -> ev.Event:
            return ev.Event(seq, "probe/evaluated", {"story_id": "S9", "criterion_id": "C1",
                                                     "record": {"seen": [{"story_id": s} for s in ids]}}, 0.0)
        events, _ = self.torn_journal(probe, lambda s: s[:s.index('"type"')])
        got = self.reconcile(events, torn=True)["cut_event"]
        self.assertEqual(got["stories"], sorted(ids))


class UsageLineage(unittest.TestCase):
    """What a lineage's cost may claim to know. A run of the lineage whose spend `account_of` cannot fully account for
    (a request in flight when it ended), or that has no RUN.json record (killed before it, its last step may be
    missing), never shows its priced cost as known: the row's cost is null and `partial`, and with it the lineage's
    total is null — never a partial sum shown as the whole. A fully accounted, recorded run keeps its priced cost, and
    the total is the sum. All four combinations are built, from the session stream, the journal and the record a run
    leaves, and read per run: a total that is null in any case with an unknown run cannot tell a wrong override of a
    fully accounted run from the right one.

    Pins aisef2/app/lineage.py::usage_lineage [1, 6, 17, 45]."""

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(t.name)

    def run_of(self, name: str, *, recorded: bool, answered: bool) -> pathlib.Path:
        """A run that spent one million input tokens (1.0 USD at PRICES) in one developer session of S1."""
        run = self.tmp / name
        (run / "sessions").mkdir(parents=True)
        (run / "sessions" / "S1.developer.1.jsonl").write_text(json.dumps(
            {"type": "step_finish", "part": {"tokens": {"input": 1_000_000, "output": 0, "reasoning": 0,
                                                        "cache": {"read": 0, "write": 0}}}}) + "\n", encoding="utf-8")
        (run / lineage.JOURNAL).parent.mkdir(parents=True)
        w = format3.JournalWriter3(run / lineage.JOURNAL, clock=lambda: 0.0)
        try:
            w.append(T.RUN_BEGIN, {"journal_format": 3, "run_id": name})
            request = w.append(T.PROVIDER_REQUEST, {"story_id": "S1", "criteria": ["C1"], "budget_owner": "DEVELOPER"})
            if answered:
                w.append(T.PROVIDER_RESULT, {"story_id": "S1", "outcome": "COMPLETED", "synthetic": False,
                                             "detail": "ok"}, source_seqs=(request.seq,))
        finally:
            w.close()
        if recorded:
            (run / "RUN.json").write_text("{}\n", encoding="utf-8")
        return run

    def lineage_of(self, name: str, *, recorded: bool, answered: bool) -> dict:
        pred = self.run_of(name, recorded=recorded, answered=answered)
        account = lineage.account_of(pred)       # the premise: the combination built is the one named
        self.assertEqual((account["recorded"], bool(account["unaccounted"])), (recorded, not answered), account)
        own = {"tokens": {}, "cost": {"value": 0.5, "status": "known"}}
        return lineage.usage_lineage(pred, self.tmp / "this-run", own, PRICES)

    def test_a_recorded_fully_accounted_run_keeps_its_cost_and_the_total_is_the_sum(self):
        r = self.lineage_of("accounted-recorded", recorded=True, answered=True)
        cost = r["runs"][0]["cost"]
        self.assertEqual((cost["value"], cost["status"]), (1.0, "known"))
        self.assertEqual((r["cost"]["value"], r["cost"]["status"]), (1.5, "known"))

    def test_a_run_with_unaccounted_spend_or_no_record_never_shows_a_known_cost(self):
        for name, recorded, answered in (("in-flight-recorded", True, False),
                                         ("answered-unrecorded", False, True),
                                         ("in-flight-unrecorded", False, False)):
            with self.subTest(name):
                r = self.lineage_of(name, recorded=recorded, answered=answered)
                cost = r["runs"][0]["cost"]
                self.assertIsNone(cost["value"])
                self.assertTrue(cost["status"].startswith("partial"), cost["status"])
                self.assertIsNone(r["cost"]["value"])               # never a partial sum shown as the whole
                self.assertTrue(r["cost"]["status"].startswith("unknown"), r["cost"]["status"])


if __name__ == "__main__":
    unittest.main()
