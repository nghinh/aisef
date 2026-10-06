"""V2.1 (D): what a run used, re-derived from its evidence (aisef2/app/usage.py), and the continuation of a run that
stopped (`aisef bundle continue`, `aisef run --parent`).

* Money only from a price table the operator gave; without one every cost is `null` and `unknown` — never 0; a session
  whose steps report no tokens leaves the total `partial`. Retries that repeat the same failures are reported, never
  acted on (the taxonomy decides a retry).
* A two-story calc run where S1 commits and S2 does not: the continuation's baseline is the journal's last commit, S1's
  obligations become a VERIFY story the kernel proves again with no developer call (one review request: K-NOWORK-001
  keeps review for a story without developer work — an owner ruling, not changed here), S2 runs as it was, the old run directory is not modified and the new record names it. Refused: another bundle's run, a run that
  committed nothing, another kernel. A merge the journal never committed is reported and left out.
Offline: the fake client and provider of test_app_run."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle, bundle_cli, settings, usage  # noqa: E402
from aisef2.app import run as R  # noqa: E402
from tests.v2.test_app_run import SETTINGS, ProductBase, git  # noqa: E402

PRICES = {"currency": "USD", "input_per_mtok": 1.0, "cache_read_per_mtok": 0.1, "cache_write_per_mtok": 1.25,
          "output_per_mtok": 4.0, "source": "test table", "effective_date": "2026-10-06"}


def step(i=100, o=10, r=2, cr=50, cw=0):
    return json.dumps({"type": "step_finish", "part": {"tokens": {"input": i, "output": o, "reasoning": r,
                                                                  "cache": {"read": cr, "write": cw}}}})


class Usage(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.out = pathlib.Path(self._tmp.name)
        (self.out / "sessions").mkdir()

    def log(self, name, *lines):
        (self.out / "sessions" / name).write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_without_prices_cost_is_unknown_never_zero(self):
        self.log("S1.developer.1.jsonl", step(), step())
        u = usage.usage(self.out, [], None, {"started": 1.0, "finished": 3.5})
        self.assertEqual(u["tokens"], {"input": 200, "cache_read": 100, "cache_write": 0, "output": 20, "reasoning": 4})
        self.assertEqual((u["cost"]["value"], u["cost"]["status"], u["wall_s"]), (None, "unknown", 2.5))

    def test_with_prices_known_and_a_blind_step_makes_it_partial(self):
        self.log("S1.developer.1.jsonl", step(i=1_000_000, o=0, r=0, cr=0))
        u = usage.usage(self.out, [], PRICES, {})
        self.assertEqual((u["cost"]["value"], u["cost"]["status"]), (1.0, "known"))
        self.log("S1.reviewer.1.jsonl", json.dumps({"type": "step_finish", "part": {}}))
        u = usage.usage(self.out, [], PRICES, {})
        self.assertEqual((u["cost"]["value"], u["cost"]["known"]), (None, 1.0))
        self.assertTrue(u["cost"]["status"].startswith("partial"))
        self.assertEqual(u["cost"]["sessions_unknown"], ["S1.reviewer.1.jsonl"])

    def test_a_price_table_is_complete_or_refused(self):
        self.assertIsNone(usage.price_problem(PRICES))
        for bad in ({**PRICES, "output_per_mtok": -1}, {k: v for k, v in PRICES.items() if k != "source"},
                    {**PRICES, "effective_date": "yesterday"}):
            self.assertIsNotNone(usage.price_problem(bad))
            with self.assertRaises(settings.SettingsError):
                settings.load({**SETTINGS, "prices": bad})
        self.assertEqual(settings.load({**SETTINGS, "prices": PRICES}).prices, PRICES)
        self.assertIsNone(settings.load(SETTINGS).prices)

    def test_retries_that_change_nothing_are_reported(self):
        def ev(t, **d):
            return {"type": t, "data": {"story_id": "S1", **d}}
        same = [ev("failure/observed", code="CONTRACT_UNSATISFIED", detail="proof of C1: CONTRACT_UNSATISFIED"), ev("story/retry")]
        events = same + same + [ev("failure/observed", code="CONTRACT_UNSATISFIED", detail="proof of C1: CONTRACT_UNSATISFIED"),
                                ev("story/rollback")]
        self.assertEqual(usage.no_progress(events), [{"story": "S1", "attempts_repeating_the_one_before": [2, 3],
                                                      "failures": ["CONTRACT_UNSATISFIED: proof of C1: CONTRACT_UNSATISFIED"]}])
        self.assertEqual(usage.no_progress([ev("story/commit")]), [])


AUTHORING = {
    "format": "aisef-v2-authoring/1", "name": "calc2", "description": "add, then mul",
    "requirements_document": {"path": "docs/requirements.md"}, "product_roots": ["app", "tests"], "baseline": "HEAD",
    "requirements": [{"id": "R-ADD", "text": "add", "source": "docs/requirements.md 1.1"},
                     {"id": "R-MUL", "text": "mul", "source": "docs/requirements.md 2.1"}],
    "contracts": [{"id": "BC-ADD", "requirement_ids": ["R-ADD"], "subject": {"kind": "python_callable", "locator": "app.calc:add"},
                   "stimulus": {"args": [2, 3]}, "observable": {"returns": 5, "within_s": 10}, "polarity": "MUST_HOLD",
                   "subject_absence": "REQUIRES_SUBJECT", "rationale": "2 + 3"},
                  {"id": "BC-MUL", "requirement_ids": ["R-MUL"], "subject": {"kind": "python_callable", "locator": "app.calc:mul"},
                   "stimulus": {"args": [2, 3]}, "observable": {"returns": 6, "within_s": 10}, "polarity": "MUST_HOLD",
                   "subject_absence": "REQUIRES_SUBJECT", "rationale": "2 * 3"}],
    "stories": {"S1": {"depends_on": [], "tests": ["tests/test_add.py"], "criteria": [
                    {"id": "C-ADD", "contract": "BC-ADD", "role": "INTRODUCE", "depends_on": [], "why": "S1 adds",
                     "facts": {"requirement": "R-ADD", "section": "§1", "clause": "1.1", "clause_text": "add", "subject": "add"}}]},
                "S2": {"depends_on": ["S1"], "tests": ["tests/test_mul.py"], "criteria": [
                    {"id": "C-MUL", "contract": "BC-MUL", "role": "INTRODUCE", "depends_on": ["C-ADD"], "why": "S2 multiplies",
                     "facts": {"requirement": "R-MUL", "section": "§2", "clause": "2.1", "clause_text": "mul", "subject": "mul"}}]}}}


@unittest.skipUnless(os.name == "posix", "the fake client is a script started by its shebang")
class Continue(ProductBase):
    """The fake developer writes `add` for every story: S1 commits, S2 (mul) does not."""

    def setUp(self) -> None:
        super().setUp()
        doc, _ = bundle_cli.seal(AUTHORING, repo=self.tmp / "source")
        for c in ("BC-ADD", "BC-MUL"):
            doc = bundle_cli.approve(doc, c, "human:t", 1.0)
        self.doc = doc
        self.project = bundle.load(doc)
        self.rec = self.execute("first")
        self.first = self.tmp / "first"

    def cals(self):
        return R.calibrations()

    def execute(self, out: str = "out", **kw) -> dict:
        from tests.v2.test_app_run import provider
        kw.setdefault("transport", provider())
        return R.execute(self.project, self.settings, kw.pop("source", self.tmp / "source"), self.tmp / out,
                         client_exe=str(self.client), cals=R.calibrations(), **kw)

    def test_the_run_stopped_after_s1(self):
        self.assertEqual(self.rec["story_outcomes"]["S1"], ["COMMIT"])
        self.assertNotEqual(self.rec["story_outcomes"]["S2"][-1], "COMMIT")

    def test_the_continuation_inherits_what_the_journal_committed_and_proves_it_again_for_free(self):
        before = hashlib.sha256((self.first / "RUN.json").read_bytes()).hexdigest()
        doc, report = bundle_cli.continue_from(self.doc, self.first)
        s1 = next(e.data["revision"] for e in self.journal("first").events if e.type == "story/commit")
        self.assertEqual((report["carried"], report["baseline"], report["remaining"], report["in_flight"]),
                         (["S1"], s1, ["S2"], None))
        project = bundle.load(doc)
        self.assertEqual(project.stories["CARRIED"]["depends_on"], [])
        self.assertEqual(project.stories["S2"]["depends_on"], ["CARRIED"])
        self.assertEqual({o.criterion_id: (o.story_id, o.role.value) for o in project.plan.obligations},
                         {"C-ADD": ("CARRIED", "VERIFY"), "C-MUL": ("S2", "INTRODUCE")})
        self.assertEqual((doc["contracts"], doc["approvals"]), (self.doc["contracts"], self.doc["approvals"]))
        self.project = project
        rec = self.execute("second", source=self.first / "repo", predecessor=self.first)
        self.assertEqual(rec["story_outcomes"]["CARRIED"], ["COMMIT"])
        events = self.journal("second").events
        self.assertEqual([e.data["budget_owner"] for e in events if e.type == "provider/request"
                          and e.data.get("story_id") == "CARRIED"], ["REVIEW"])      # no developer call; K-NOWORK-001's review
        self.assertEqual({k: rec["continues"][k] for k in ("path", "evidence_anchor")},
                         {"path": str(self.first), "evidence_anchor": R.anchor_in(self.first)})
        self.assertEqual((rec["continues"]["claim"]["run"], rec["continues"]["account"]["unaccounted"]),
                         (str(self.tmp / "second"), []))
        self.assertEqual(hashlib.sha256((self.first / "RUN.json").read_bytes()).hexdigest(), before)   # untouched

    def test_a_merge_the_journal_never_committed_is_left_out(self):
        s1 = next(e.data["revision"] for e in self.journal("first").events if e.type == "story/commit")
        repo = self.first / "repo"
        (repo / "stray.txt").write_text("an in-flight merge\n")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "in flight")
        with self.assertRaises(bundle.BundleError) as c:      # nothing identifies it: never left out silently
            bundle_cli.continue_from(self.doc, self.first)
        self.assertIn("nothing identifies", str(c.exception))
        _, report = bundle_cli.continue_from(self.doc, self.first, leave_out_unidentified=True)
        self.assertEqual(report["baseline"], s1)
        self.assertIn("left out", report["in_flight"])
        self.assertEqual([(i["operation"], i["identified"], i["subject"]) for i in report["unconfirmed"]],
                         [("unknown", False, "in flight")])

    def test_refusals(self):
        other = dict(self.doc, description="another project")
        with self.assertRaises(bundle.BundleError) as c:
            bundle_cli.continue_from(other, self.first)
        self.assertIn("another bundle", str(c.exception))
        rec = json.loads((self.first / "RUN.json").read_text(encoding="utf-8"))
        moved = self.tmp / "moved"
        moved.mkdir()
        for name in ("run", "repo"):
            os.symlink(self.first / name, moved / name)
        (moved / "RUN.json").write_text(json.dumps(dict(rec, kernel_digest="0" * 40)), encoding="utf-8")
        with self.assertRaises(bundle.BundleError) as c:
            bundle_cli.continue_from(self.doc, moved)
        self.assertIn("another kernel", str(c.exception))
        with self.assertRaises(R.RunRefused):
            self.execute("third", predecessor=self.tmp / "nowhere")


if __name__ == "__main__":
    unittest.main()
