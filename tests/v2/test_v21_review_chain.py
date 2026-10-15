"""V2.1 (C): the review chain on the product path — candidate -> review -> coverage -> finding verified and anchored ->
fed back to the developer -> new candidate -> proved and reviewed again -> merge decision — through `aisef run` and the
one decision path (story_runner, orchestrate.review, the taxonomy's REVIEW and ENVIRONMENT limits).

A calc command (`python -m app A B` exits with A + B; clause 1.2: exit 2 on a usage error — two approved contracts on
two stimuli, so the clause's approved outcome is shown constant). The developer is a fake client whose answers are
scripted per attempt and which records every prompt; the finder is a FAKE Open Code Review executable (pinned by its
sha256 like the real one) writing OCR's documents from a scripted scenario per review. Cases:

* a correct, anchored finding: attempt 1 RETRY (REVIEW_FINDING) with the finding in the developer's retry prompt;
  attempt 2 fixes it, is proved and reviewed again, and commits — main holds the fix;
* reproducible but the expectation is not the requirement's (UNANCHORED, CONTRADICTS_APPROVED): no block, commit;
* not reproducible: no block, commit;
* a review that did not cover the candidate (partial, timed out, its token budget spent, an unsupported manifest
  schema): under fix-loop never a commit on it (CAPABILITY_UNRUNNABLE; a provider failure PROVIDER_UNAVAILABLE),
  under advisory a commit with the coverage recorded;
* the candidate changed during the review (a file edited, a commit made in the checkout): CAPABILITY_UNRUNNABLE,
  every finding discarded, the change never reaches main;
* the fix rounds spent while the defect persists: ROLLBACK, main unchanged.

The real binary (built from the pinned commit; AISEF_TEST_OCR_EXE) is exercised in RealBinary: `--preview` on a real
repository, and a full review whose model is a scripted OpenAI-compatible server on loopback. Nothing reaches a real
model or provider."""

from __future__ import annotations

import hashlib
import http.server
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import adapters as ad  # noqa: E402
from aisef2.app import bundle, client, review_ocr, settings  # noqa: E402
from aisef2.app import run as R  # noqa: E402
from aisef2.arch.enums import ObligationRole, Polarity, SubjectAbsence, SubjectKind  # noqa: E402
from aisef2.journal import format3  # noqa: E402
from aisef2.plan.obligation import EXPECTED_AT_PARENT, NOT_PREREGISTERED, Plan, PlanObligation  # noqa: E402
from aisef2.probe import catalog  # noqa: E402
from aisef2.product.approval import ContractApproval, Requirement  # noqa: E402
from aisef2.product.compiler import ProbeRef, compile_spec  # noqa: E402
from aisef2.product.contract import BehaviorContract, Subject  # noqa: E402
from tests.v2.test_app_run import SETTINGS, client_config, git, provider  # noqa: E402

REQUIREMENTS = ("# Calc CLI\n\n## 1. Command line\n\n1.1 `python -m app A B` exits with the sum of the integers A and B.\n\n"
                "1.2 Exit 2 on a usage error (any other number of arguments).\n")
SUM_TEXT = "exits with the sum of the integers A and B"
USAGE_TEXT = "exit 2 on a usage error (any other number of arguments)"
#: attempt 1's command: three arguments are summed as two — a usage error the approved contracts do not exercise
DEFECTIVE = "def main(args):\n    if len(args) < 2:\n        return 2\n    return int(args[0]) + int(args[1])\n"
FIXED = "def main(args):\n    if len(args) != 2:\n        return 2\n    return int(args[0]) + int(args[1])\n"
ENTRY = "import sys\n\nfrom app.cli import main\n\nsys.exit(main(sys.argv[1:]))\n"
TEST = ("import unittest\n\nfrom app.cli import main\n\n\nclass T(unittest.TestCase):\n    def test_sum(self):\n"
        "        self.assertEqual(main(['2', '3']), 5)\n\n    def test_usage(self):\n        self.assertEqual(main([]), 2)\n")
MAIN = {"kind": "cli_invocation", "locator": "app:__main__"}


def reproducer(clause: str, argv: list, exit_code: int) -> dict:
    return {"clause": clause, "subject": MAIN, "stimulus": {"argv": argv}, "observable": {"exit_code": exit_code, "within_s": 20}}


#: the anchored finding: three arguments are a usage error (1.2, approved outcome exit 2 on two stimuli)
THREE_ARGS = reproducer("R-CLI/1.2", ["1", "2", "3"], 2)

#: the developer: `answers` is the list of files to write per developer call (the last repeats); every prompt kept
FAKE_DEVELOPER = r'''import json, pathlib, sys
argv = sys.argv[1:]
if argv == ["--version"]:
    print("0.0.0-fake")
    raise SystemExit(0)
here = pathlib.Path(__file__).parent
title, cwd = argv[argv.index("--title") + 1], pathlib.Path(argv[argv.index("--dir") + 1])
if title.startswith("developer"):
    calls = sorted(here.glob("prompt-*.txt"))
    (here / f"prompt-{len(calls):02d}.txt").write_text(argv[-1], encoding="utf-8")
    answers = json.loads((here / "answers.json").read_text(encoding="utf-8"))
    for rel, text in answers[min(len(calls), len(answers) - 1)].items():
        (cwd / rel).parent.mkdir(parents=True, exist_ok=True)
        (cwd / rel).write_text(text, encoding="utf-8")
print(json.dumps({"type": "text", "part": {"text": "done"}}))
print(json.dumps({"type": "step_finish", "part": {"tokens": {"input": 120, "output": 7, "reasoning": 3,
                                                             "cache": {"read": 10, "write": 0}}}}))
'''

#: the finder: OCR's command line and documents (manifest v1, preview), one scripted scenario per review run
FAKE_OCR = r'''import hashlib, json, pathlib, subprocess, sys, time
argv = sys.argv[1:]
here = pathlib.Path(__file__).parent
with (here / "calls.jsonl").open("a", encoding="utf-8") as _calls:     # every start, whatever it was asked
    _calls.write(json.dumps(argv) + "\n")
if argv == ["version"]:      # the identity gate asks before any review command; identity.json scripts a different answer
    said = json.loads((here / "identity.json").read_text(encoding="utf-8")) if (here / "identity.json").exists() else {}
    time.sleep(said.get("sleep", 0))
    sys.stdout.write(said.get("text", "open-code-review v1.12.12 (182898c) darwin/arm64\nbuilt at: 2026-10-05T00:00:00Z\n"))
    raise SystemExit(said.get("exit", 0))
def opt(name):
    return argv[argv.index(name) + 1]
repo, base, head, out = opt("--repo"), opt("--from"), opt("--to"), opt("--output")
rows = subprocess.run(["git", "-C", repo, "diff", "--name-status", "--no-renames", base + ".." + head],
                      capture_output=True, text=True, encoding="utf-8").stdout.splitlines()
changed = [r.split("\t", 1) for r in rows if "\t" in r]
if "--preview" in argv:
    files = [{"path": p, "status": "added" if k == "A" else "modified", "insertions": 1, "deletions": 0,
              "will_review": True} for k, p in changed if k != "D"]
    pathlib.Path(out).write_text(json.dumps({"files": files, "total_files": len(files)}), encoding="utf-8")
    raise SystemExit(0)
runs = sorted(here.glob("review-*.json"))
(here / f"review-{len(runs):02d}.json").write_text(json.dumps(argv), encoding="utf-8")
scenarios = json.loads((here / "scenarios.json").read_text(encoding="utf-8"))
sc = scenarios[min(len(runs), len(scenarios) - 1)]
kind = sc.get("kind", "complete")
if kind == "sleep":
    time.sleep(120)
def item(p):
    return {"item_id": hashlib.sha256("\x00".join(["review", "range", p, p]).encode("utf-8")).hexdigest(), "path": p}
done = [item(p) for k, p in changed if k != "D"]
manifest = {"schema_version": "ocr.run-manifest/v1", "operation": "review", "terminal_state": "complete" if done else "skipped",
            "input": {"mode": "range", "resolved_base": base, "resolved_head": head},
            "execution": {"ocr_version": "v1.12.12"},
            "coverage": {"selected": done, "completed": done, "reused": [], "failed": [], "waived": []}}
doc = {"status": "complete", "comments": [], "manifest": manifest, "tool_calls": {"failure_details": []},
       "summary": {"input_tokens": 300, "output_tokens": 60, "total_tokens": 360}, "message": "reviewed"}
for rep in sc.get("reproducers", []):
    doc["comments"].append({"path": "app/cli.py", "category": "bug", "severity": sc.get("severity", "high"),
                            "existing_code": "    return int(args[0]) + int(args[1])", "start_line": 4,
                            "content": sc.get("summary", "a usage error is not refused") + "\n```aisef-reproducer\n"
                                       + json.dumps(rep) + "\n```"})
code = 0
if kind == "partial":
    manifest["terminal_state"] = doc["status"] = "partial"
    manifest["coverage"]["completed"] = []
    manifest["coverage"]["failed"] = [dict(i, classification="timeout", reason="round timed out") for i in done]
elif kind == "budget":
    manifest["terminal_state"] = doc["status"] = "partial"
    manifest["coverage"]["completed"] = []
    manifest["coverage"]["failed"] = [dict(i, classification="budget") for i in done]
    doc["warnings"] = [{"type": "token_budget_reached", "message": "token budget reached", "file": ""}]
elif kind == "schema":
    manifest["schema_version"] = "ocr.run-manifest/v2"
elif kind == "provider":
    manifest["terminal_state"] = doc["status"] = "failed"
    manifest["coverage"]["completed"] = []
    manifest["run_failure"] = {"classification": "provider", "reason": "HTTP 503"}
    code = 1
elif kind == "tamper":
    target = pathlib.Path(repo, "app", "cli.py")
    target.chmod(0o644)
    target.write_text("def main(args):\n    return 0\n", encoding="utf-8")
elif kind == "commit":
    subprocess.run(["git", "-C", repo, "-c", "user.name=r", "-c", "user.email=r@r", "commit", "-q", "--allow-empty",
                    "-m", "reviewer"], check=True)
pathlib.Path(out).write_text(json.dumps(doc), encoding="utf-8")
raise SystemExit(code)
'''


def _contract(cid: str, req: Requirement, argv: list, code: int) -> BehaviorContract:
    return BehaviorContract.create(id=cid, requirement_ids=(req.id,), subject=Subject(SubjectKind.CLI_INVOCATION, "app:__main__"),
                                   stimulus={"argv": argv}, observable={"exit_code": code, "within_s": 20},
                                   polarity=Polarity.MUST_HOLD, subject_absence=SubjectAbsence.REQUIRES_SUBJECT,
                                   rationale="the requirement's own example")


def cli_bundle(baseline: str) -> dict:
    req = Requirement.create(id="R-CLI", text="python -m app A B exits with the sum of the integers A and B; exit 2 on a "
                                              "usage error (any other number of arguments)", source="docs/requirements.md §1")
    contracts = (_contract("BC-SUM", req, ["2", "3"], 5), _contract("BC-USAGE-0", req, [], 2),
                 _contract("BC-USAGE-1", req, ["1"], 2))
    approvals = tuple(ContractApproval(req.id, req.requirement_hash, c.id, c.contract_hash, "human:fixture-owner", 1.0, ())
                      for c in contracts)
    e = catalog.active()[SubjectKind.CLI_INVOCATION]
    probes = {SubjectKind.CLI_INVOCATION: ProbeRef(e.probe_id, e.probe_digest)}
    spec = {c.id: compile_spec(c, requirements={req.id: req}, approvals=list(approvals), probes=probes).id for c in contracts}
    rows = (("C-SUM", "BC-SUM", "1.1", SUM_TEXT), ("C-USAGE-0", "BC-USAGE-0", "1.2", USAGE_TEXT),
            ("C-USAGE-1", "BC-USAGE-1", "1.2", USAGE_TEXT))
    plan = Plan.create(id="PLAN-CLI", baseline=baseline, plan_quality_policy=NOT_PREREGISTERED, obligations=tuple(
        PlanObligation(cid, spec[con], "S1", ObligationRole.INTRODUCE, EXPECTED_AT_PARENT[ObligationRole.INTRODUCE], (),
                       f"S1 introduces {cid}") for cid, con, _, _ in rows))
    facts = {cid: {"requirement": "R-CLI", "section": "§1", "clause": clause, "clause_text": text, "subject": "python -m app"}
             for cid, _, clause, text in rows}
    return bundle.dump(name="calc-cli", description="A calculator command.", requirements_path="docs/requirements.md",
                       requirements_sha256=hashlib.sha256(REQUIREMENTS.encode()).hexdigest(), product_roots=("app", "tests"),
                       requirements=(req,), contracts=contracts, approvals=approvals, plan=plan, facts=facts,
                       stories={"S1": {"depends_on": [], "tests": ["tests/test_cli.py"]}})


def answer(cli: str) -> dict:
    return {"app/cli.py": cli, "app/__main__.py": ENTRY, "tests/__init__.py": "", "tests/test_cli.py": TEST}


@unittest.skipUnless(os.name == "posix", "the fake client and the fake finder are scripts started by their shebang")
class ChainBase(unittest.TestCase):
    """The calc command, the scripted developer and the scripted finder."""

    POLICY = "fix-loop"

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(t.name).resolve()
        src = self.tmp / "source"
        src.mkdir()
        git(src, "init", "-q", "-b", "main")
        (src / "app").mkdir()
        (src / "app" / "__init__.py").write_text("")
        (src / "docs").mkdir()
        (src / "docs" / "requirements.md").write_text(REQUIREMENTS)
        git(src, "add", "-A")
        git(src, "commit", "-q", "-m", "baseline")
        self.baseline = git(src, "rev-parse", "HEAD")
        self.project = bundle.load(cli_bundle(self.baseline))
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.client = self._script("opencode", FAKE_DEVELOPER)
        self.ocr = self._script("ocr", FAKE_OCR)
        self.scanner = mock.patch.object(ad, "scanner", lambda: ad.NoScanner())
        self.scanner.start()
        self.addCleanup(self.scanner.stop)
        xdg = mock.patch.dict(os.environ, client_config(self.tmp))
        xdg.start()
        self.addCleanup(xdg.stop)

    def _script(self, name: str, body: str) -> pathlib.Path:
        p = self.bin / name
        p.write_text(f"#!{sys.executable}\n" + body)
        p.chmod(0o755)
        return p

    def settings(self, policy: str | None = None, **timeouts) -> settings.Settings:
        review = {"policy": policy or self.POLICY, "min_severity": "high", "finder": "ocr",
                  "ocr": {"exe": str(self.ocr), "sha256": hashlib.sha256(self.ocr.read_bytes()).hexdigest(),
                          "timeout_min": 1, "max_tokens": 4000}}
        return settings.load({**SETTINGS, "review": review, "timeouts_s": {**SETTINGS["timeouts_s"], **timeouts}})

    def run_with(self, answers: list[str], scenarios: list[dict], policy: str | None = None, **timeouts) -> dict:
        (self.bin / "answers.json").write_text(json.dumps([answer(a) for a in answers]), encoding="utf-8")
        (self.bin / "scenarios.json").write_text(json.dumps(scenarios), encoding="utf-8")
        self.out = self.tmp / "out"
        return R.execute(self.project, self.settings(policy, **timeouts), self.tmp / "source", self.out,
                         transport=provider(), client_exe=str(self.client), cals=R.calibrations())

    def events(self):
        return format3.reconstruct((self.out / "run" / "journals" / "aisef-run.jsonl").read_text(encoding="utf-8")).events

    def failures(self) -> list[str]:
        return [e.data["code"] for e in self.events() if e.type == "failure/observed"]

    def review_rows(self) -> list[dict]:
        return [e.data for e in self.events() if e.type == "gate/check" and e.data["check"].startswith("S1:review")]

    def main_file(self) -> str | None:
        held = subprocess.run(["git", "-C", str(self.out / "repo"), "cat-file", "-e", "main:app/cli.py"]).returncode == 0
        return (git(self.out / "repo", "show", "main:app/cli.py") + "\n") if held else None

    def prompts(self) -> list[str]:
        return [p.read_text(encoding="utf-8") for p in sorted(self.bin.glob("prompt-*.txt"))]


class FixLoop(ChainBase):
    def test_a_correct_anchored_finding_is_fixed_before_the_merge(self):
        rec = self.run_with([DEFECTIVE, FIXED], [{"reproducers": [THREE_ARGS]}, {}])
        self.assertEqual((rec["story_outcomes"], rec["delivery_verdict"]), ({"S1": ["RETRY", "COMMIT"]}, "PASS"))
        self.assertEqual(self.failures(), ["REVIEW_FINDING"])
        blocked = [r for r in self.review_rows() if not r["passed"]]
        self.assertEqual(len(blocked), 1)
        self.assertIn("probe:probe.cli_invocation:REFUTED", blocked[0]["detail"])
        stated = json.loads(blocked[0]["detail"].split(" — ", 1)[1])
        self.assertEqual((stated["verification"], stated["anchor"]), ("CONFIRMED", "ANCHORED"))
        prompts = self.prompts()
        self.assertEqual(len(prompts), 2)
        self.assertNotIn("REVIEW_FINDING", prompts[0])
        self.assertIn("REVIEW_FINDING (owner REVIEW)", prompts[1])      # fed back: the finding and its reproducer
        self.assertIn('"argv": ["1", "2", "3"]', prompts[1])
        self.assertEqual(self.main_file(), FIXED)                        # the fix, merged after it was proved and reviewed
        reviews = sorted(self.bin.glob("review-*.json"))
        self.assertEqual(len(reviews), 2)                                # the second candidate was reviewed again
        heads = [json.loads(p.read_text())[json.loads(p.read_text()).index("--to") + 1] for p in reviews]
        self.assertNotEqual(heads[0], heads[1])
        commit = next(e.data for e in self.events() if e.type == "story/commit")
        self.assertEqual(git(self.out / "repo", "rev-parse", "main"), commit["revision"])
        s = [x for x in rec["sessions"] if x["role"] == "reviewer"]
        self.assertEqual([x["coverage"]["status"] for x in s], ["COMPLETE", "COMPLETE"])
        self.assertEqual(rec["usage"]["tokens"]["input"], 2 * 120 + 2 * 300)   # the finder's tokens are the run's

    def test_the_fix_rounds_spent_with_the_defect_left_roll_back(self):
        rec = self.run_with([DEFECTIVE, DEFECTIVE], [{"reproducers": [THREE_ARGS]}])
        self.assertEqual((rec["story_outcomes"], rec["delivery_verdict"]), ({"S1": ["RETRY", "ROLLBACK"]}, "FAIL"))
        self.assertEqual(self.failures(), ["REVIEW_FINDING", "REVIEW_FINDING"])
        self.assertIsNone(self.main_file())                              # main is the baseline
        self.assertEqual(git(self.out / "repo", "rev-parse", "main"), self.baseline)


class NotABlocker(ChainBase):
    def assert_committed_with(self, anchor_or_status: str) -> dict:
        self.assertEqual(self.failures(), [])
        rows = [r for r in self.review_rows() if r["check"] != "S1:review"]
        self.assertTrue(rows and all(r["passed"] for r in rows), rows)
        stated = json.loads(rows[0]["detail"].split(" — ", 1)[1])
        self.assertIn(anchor_or_status, (stated.get("anchor"), stated["verification"]))
        return stated

    def test_a_reproduced_finding_whose_clause_shows_no_constant_outcome_does_not_block(self):
        # "1 1 must exit 3" citing 1.1: the candidate exits 2 (CONFIRMED) but 1.1's one approved contract (2 3 -> 5)
        # shows no constant outcome
        rec = self.run_with([FIXED], [{"reproducers": [reproducer("R-CLI/1.1", ["1", "1"], 3)]}])
        self.assertEqual(rec["story_outcomes"], {"S1": ["COMMIT"]})
        stated = self.assert_committed_with("UNANCHORED")
        self.assertEqual(stated["verification"], "CONFIRMED")

    def test_a_reproduced_finding_an_approved_contract_contradicts_does_not_block(self):
        # "no arguments must exit 0" citing 1.2: approved contract BC-USAGE-0 decides that stimulus: exit 2
        rec = self.run_with([FIXED], [{"reproducers": [reproducer("R-CLI/1.2", [], 0)]}])
        self.assertEqual(rec["story_outcomes"], {"S1": ["COMMIT"]})
        stated = self.assert_committed_with("CONTRADICTS_APPROVED")
        self.assertEqual(stated["verification"], "CONFIRMED")
        self.assertIn("BC-USAGE-0", stated["anchor_why"])

    def test_a_finding_that_does_not_reproduce_does_not_block(self):
        rec = self.run_with([FIXED], [{"reproducers": [THREE_ARGS]}])
        self.assertEqual(rec["story_outcomes"], {"S1": ["COMMIT"]})
        self.assert_committed_with("NOT_REPRODUCED")
        self.assertEqual(self.main_file(), FIXED)


class IncompleteReview(ChainBase):
    def assert_never_committed_on(self, kind: str, code: str, why: str, **timeouts) -> dict:
        rec = self.run_with([FIXED], [{"kind": kind}], **timeouts)
        self.assertEqual((rec["story_outcomes"], rec["delivery_verdict"]), ({"S1": ["RETRY", "ROLLBACK"]}, "FAIL"), kind)
        self.assertEqual(self.failures(), [code, code])
        results = [e.data["detail"] for e in self.events() if e.type == "provider/result" and "review" in e.data["detail"]]
        self.assertTrue(results and all(why in d for d in results), (kind, results))
        self.assertEqual(git(self.out / "repo", "rev-parse", "main"), self.baseline)
        return rec

    def test_partial(self):
        self.assert_never_committed_on("partial", "CAPABILITY_UNRUNNABLE", "terminal state 'partial'")

    def test_its_token_budget_spent(self):
        self.assert_never_committed_on("budget", "CAPABILITY_UNRUNNABLE", "warning token_budget_reached")

    def test_an_unsupported_manifest_schema(self):
        self.assert_never_committed_on("schema", "CAPABILITY_UNRUNNABLE", "manifest schema 'ocr.run-manifest/v2'")

    def test_timed_out_and_its_spend_unknown(self):
        """A finder stopped at its deadline wrote nothing: what it spent is unknown, so its stream's one step reports no
        tokens — the budget is then unaccounted and no further paid work starts (the 2.0.0 budget stop: the next
        developer session is refused, journaled as the provider's), and the record names it. Never a commit."""
        rec = self.run_with([FIXED], [{"kind": "sleep"}], reviewer=3)
        self.assertEqual(rec["story_outcomes"]["S1"][-1], "ROLLBACK")
        self.assertEqual(self.failures()[0], "CAPABILITY_UNRUNNABLE")
        first = next(e.data["detail"] for e in self.events() if e.type == "provider/result" and "review" in e.data["detail"])
        self.assertIn("timed out: no run manifest", first)
        self.assertTrue(all(c == "PROVIDER_UNAVAILABLE" for c in self.failures()[1:]))
        self.assertIn("unaccounted: S1.reviewer.1.jsonl: 1 finished steps report no tokens", rec["budget_stop"])
        self.assertEqual(rec["usage"]["cost"]["value"], None)
        self.assertEqual(git(self.out / "repo", "rev-parse", "main"), self.baseline)

    def test_a_provider_failure_is_the_providers(self):
        self.assert_never_committed_on("provider", "PROVIDER_UNAVAILABLE", "OCR could not reach the provider")

    def test_under_advisory_the_incomplete_review_is_recorded_and_does_not_block(self):
        rec = self.run_with([FIXED], [{"kind": "partial"}], policy="advisory")
        self.assertEqual(rec["story_outcomes"], {"S1": ["COMMIT"]})
        result = next(e.data["detail"] for e in self.events() if e.type == "provider/result" and "coverage" in e.data["detail"])
        self.assertIn("coverage INDETERMINATE", result)
        self.assertEqual([x["coverage"]["status"] for x in rec["sessions"] if x["role"] == "reviewer"], ["INDETERMINATE"])


class NothingToReview(ChainBase):
    def test_a_story_with_no_change_is_reviewed_as_nothing_and_commits(self):
        """K-NOWORK-001 keeps a review for a story with no developer work; OCR's review of the empty range is `skipped`
        (measured on the real binary: RealBinary.test_an_empty_range_is_skipped_without_a_model_call) — a complete
        review of nothing, not a gap that blocks."""
        src = self.tmp / "source"
        for rel, text in answer(FIXED).items():
            (src / rel).parent.mkdir(parents=True, exist_ok=True)
            (src / rel).write_text(text)
        git(src, "add", "-A")
        git(src, "commit", "-q", "-m", "already there")
        self.project = bundle.load(cli_bundle(git(src, "rev-parse", "HEAD")))
        rec = self.run_with([FIXED], [{}])
        self.assertEqual((rec["story_outcomes"], self.prompts()), ({"S1": ["COMMIT"]}, []))     # no developer call
        s = [x for x in rec["sessions"] if x["role"] == "reviewer"]
        self.assertEqual([(x["required"], x["coverage"]["status"]) for x in s], [([], "COMPLETE")])


class CandidateChangedDuringReview(ChainBase):
    def test_a_file_edited_by_the_finder_discards_the_review_and_never_reaches_main(self):
        rec = self.run_with([FIXED], [{"kind": "tamper"}, {}])
        self.assertEqual(rec["story_outcomes"], {"S1": ["RETRY", "COMMIT"]})
        self.assertEqual(self.failures(), ["CAPABILITY_UNRUNNABLE"])
        refused = next(e.data["detail"] for e in self.events() if e.type == "provider/result" and "changed during" in e.data["detail"])
        self.assertIn("app/cli.py", refused)
        self.assertEqual(self.main_file(), FIXED)       # the developer's candidate, never the finder's edit

    def test_a_commit_made_by_the_finder_discards_the_review(self):
        rec = self.run_with([FIXED], [{"kind": "commit"}, {}])
        self.assertEqual(rec["story_outcomes"], {"S1": ["RETRY", "COMMIT"]})
        self.assertEqual(self.failures(), ["CAPABILITY_UNRUNNABLE"])
        refused = next(e.data["detail"] for e in self.events() if e.type == "provider/result" and "changed during" in e.data["detail"])
        self.assertIn("HEAD is no longer", refused)
        log = git(self.out / "repo", "log", "--format=%s", "main")
        self.assertNotIn("reviewer", log.splitlines())

    def test_a_finder_binary_that_is_not_the_pinned_one_does_not_run(self):
        s = self.settings()
        self.ocr.write_text(self.ocr.read_text() + "\n# changed\n")
        (self.bin / "answers.json").write_text(json.dumps([answer(FIXED)]), encoding="utf-8")
        (self.bin / "scenarios.json").write_text(json.dumps([{}]), encoding="utf-8")
        self.out = self.tmp / "out"
        rec = R.execute(self.project, s, self.tmp / "source", self.out, transport=provider(), client_exe=str(self.client),
                        cals=R.calibrations())
        self.assertEqual(rec["story_outcomes"], {"S1": ["RETRY", "ROLLBACK"]})
        self.assertEqual(self.failures(), ["CAPABILITY_UNRUNNABLE", "CAPABILITY_UNRUNNABLE"])
        self.assertEqual(list(self.bin.glob("review-*.json")), [])
        self.assertFalse((self.bin / "calls.jsonl").exists())              # it was never started: not even for `version`


class _ScriptedModel(http.server.BaseHTTPRequestHandler):
    """An OpenAI-compatible chat completions endpoint on loopback: every request with OCR's tools is answered with one
    code_comment (carrying an aisef-reproducer block) and task_done. Records what it was sent."""
    seen: list = []
    COMMENT = True      # False: the model finds nothing and only says it is done

    def do_POST(self):  # noqa: N802 — http.server's name
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        tools = [t["function"]["name"] for t in body.get("tools") or []]
        type(self).seen.append({"path": self.path, "tools": tools, "authorization": self.headers.get("Authorization"),
                                "model": body.get("model")})
        content = "three arguments are summed as two\n```aisef-reproducer\n" + json.dumps(THREE_ARGS) + "\n```"
        calls = [{"id": "c2", "type": "function", "function": {"name": "task_done", "arguments": '{"state": "DONE"}'}}]
        if self.COMMENT:
            calls.insert(0, {"id": "c1", "type": "function", "function": {"name": "code_comment", "arguments": json.dumps(
                {"comments": [{"path": "app/cli.py", "content": content, "category": "bug", "severity": "high",
                               "existing_code": "    return int(args[0]) + int(args[1])"}]})}})
        out = json.dumps({"id": "x", "object": "chat.completion", "created": 0, "model": body.get("model"),
                          "choices": [{"index": 0, "finish_reason": "tool_calls",
                                       "message": {"role": "assistant", "content": "", "tool_calls": calls}}],
                          "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *args):
        pass


class _QuietModel(_ScriptedModel):
    """The same endpoint, a model that finds nothing: every request is answered with task_done alone."""
    seen: list = []
    COMMENT = False


@unittest.skipUnless(os.environ.get("AISEF_TEST_OCR_EXE"), "the real Open Code Review binary (AISEF_TEST_OCR_EXE)")
class RealBinary(unittest.TestCase):
    """The real `ocr` built from the pinned commit: its preview, and a full review against a scripted model."""

    def setUp(self) -> None:
        self.exe = os.environ["AISEF_TEST_OCR_EXE"]
        self.sha = hashlib.sha256(pathlib.Path(self.exe).read_bytes()).hexdigest()
        # the product's own question, as the review stage asks it (clean environment, empty HOME): the real binary
        # must be accepted by the same function that refuses another version or commit — not a substring of its output
        self.declared, why = ad._declared(self.exe, review_ocr.VERSION_TIMEOUT_S)
        self.assertIsNone(why)
        self.assertEqual((self.declared["version"], review_ocr.OCR["commit"].startswith(self.declared["commit"])),
                         (review_ocr.OCR["version"], True))
        print(f"\n[real OCR] {self.declared['line']} sha256 {self.sha}", file=sys.stderr)
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(t.name).resolve()
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "main")
        (self.repo / "app").mkdir()
        (self.repo / "app" / "__init__.py").write_text("")
        (self.repo / "README.txt").write_text("calc\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "base")
        self.base = git(self.repo, "rev-parse", "HEAD")
        (self.repo / "app" / "cli.py").write_text(DEFECTIVE)
        (self.repo / "notes.txt").write_text("not code\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "candidate")
        self.head = git(self.repo, "rev-parse", "HEAD")
        (self.tmp / "home").mkdir()
        (self.tmp / "rule.json").write_text(json.dumps({"include": ["app/**"]}))
        (self.tmp / "background.md").write_text("review the change")

    def ocr(self, output: str, preview: bool, endpoint: dict | None = None) -> int:
        env = review_ocr.environment({"PATH": os.environ["PATH"]}, self.tmp / "home", endpoint)
        argv = review_ocr.argv(self.exe, repo=str(self.repo), base=self.base, head=self.head, rule=str(self.tmp / "rule.json"),
                               output=str(self.tmp / output), model="model-1", max_tokens=4000, budget_tokens=50000,
                               timeout_min=2, background_file=str(self.tmp / "background.md"), preview=preview)
        return subprocess.run(argv, env=env, capture_output=True, text=True, encoding="utf-8", timeout=300).returncode

    def test_the_preview_is_read_as_the_adapter_expects(self):
        self.assertEqual(self.ocr("preview.json", True), 0)
        preview = review_ocr.read_output(self.tmp / "preview.json")
        files = {f["path"]: f for f in preview["files"]}
        self.assertTrue(files["app/cli.py"]["will_review"])
        self.assertEqual(files["notes.txt"]["exclude_reason"], "unsupported_ext")
        self.assertEqual(sorted(os.listdir(self.tmp / "home")), [])         # nothing written to its HOME by a preview
        self.assertEqual(git(self.repo, "status", "--porcelain", "--ignored"), "")

    def test_an_empty_range_is_skipped_without_a_model_call(self):
        self.head = self.base                                               # a story with no change
        code = self.ocr("output.json", False, {"url": "http://127.0.0.1:9/v1", "token": "sk-none", "model": "model-1"})
        output = review_ocr.read_output(self.tmp / "output.json")
        self.assertEqual((code, output["manifest"]["terminal_state"], output["summary"]["input_tokens"]), (0, "skipped", 0))
        cov = review_ocr.coverage(output, code, required=[], base=self.base, head=self.head, preview=None)
        self.assertEqual(cov.status, review_ocr.COMPLETE)
        self.assertEqual(review_ocr.coverage(output, code, required=["app/cli.py"], base=self.base, head=self.head).status,
                         review_ocr.INDETERMINATE)

    def test_the_review_stage_runs_the_real_binary_as_the_product_does(self):
        """`Reviewer.review` — the kernel's own call, under fix-loop — over the real binary: the identity question in the
        clean environment, the preview, the review against a model that finds nothing, the coverage COMPLETE (fix-loop
        raises on anything else) and the session record carrying what the binary declared. Real here: the binary, the
        stage's process handling, the controller's scope and coverage. Scripted: the model, on loopback."""
        _QuietModel.seen = []
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _QuietModel)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        logs = self.tmp / "out" / "sessions"
        budget = client.Budget({"provider_requests": 50, "turns": 50, "input_tokens": 10 ** 6, "output_tokens": 10 ** 6},
                               dict.fromkeys(client.Budget.KEYS, 0), logs)
        review = {"policy": "fix-loop", "min_severity": "high", "finder": "ocr", "given": True,
                  "ocr": {"exe": self.exe, "sha256": self.sha, "timeout_min": 2, "max_tokens": 4000}}
        run = types.SimpleNamespace(events=[types.SimpleNamespace(type="story/begin",
                                                                  data={"story_id": "S1", "parent": self.base})],
                                    state=lambda proj: {"S1": {"attempt": 1}})
        rev = ad.Reviewer(run, bundle.load(cli_bundle(self.base)), logs, {"budget": budget, "secrets": ()}, 300.0,
                          review=review, route={"url": f"http://127.0.0.1:{server.server_address[1]}/v1",
                                                "token": "sk-test-not-a-key", "model": "model-1",
                                                "env": {"PATH": os.environ["PATH"]}})
        result = rev.review(types.SimpleNamespace(story_id="S1", root=str(self.repo)), ("C-SUM",))
        (s,) = rev.sessions
        self.assertEqual((result.outcome.name, result.findings), ("COMPLETED", ()))
        self.assertEqual((s["coverage"]["status"], s["required"], s["exit"]), (review_ocr.COMPLETE, ["app/cli.py"], 0))
        self.assertEqual(s["identity"]["declared"], {k: self.declared[k] for k in ("version", "commit", "platform", "line")})
        self.assertEqual(s["identity"]["sha256_checked"], self.sha)
        self.assertTrue(_QuietModel.seen and all(r["path"] == "/v1/chat/completions"
                                                 and r["authorization"] == "Bearer sk-test-not-a-key"
                                                 for r in _QuietModel.seen), _QuietModel.seen)
        self.assertEqual(git(self.repo, "status", "--porcelain", "--ignored"), "")

    def test_a_full_review_against_a_scripted_model(self):
        _ScriptedModel.seen = []
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _ScriptedModel)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        url = f"http://127.0.0.1:{server.server_address[1]}/v1"
        self.assertEqual(self.ocr("preview.json", True), 0)
        code = self.ocr("output.json", False, {"url": url, "token": "sk-test-not-a-key", "model": "model-1"})
        self.assertEqual(code, 0)
        output = review_ocr.read_output(self.tmp / "output.json")
        cov = review_ocr.coverage(output, code, required=["app/cli.py"], base=self.base, head=self.head,
                                  preview=review_ocr.read_output(self.tmp / "preview.json"))
        self.assertEqual((cov.status, cov.reasons), (review_ocr.COMPLETE, ()))
        found = review_ocr.findings(output, ["app/cli.py"])
        self.assertEqual(len(found), 1)                                    # the same comment each round: one finding
        self.assertEqual(found[0]["reproducer"], THREE_ARGS)
        self.assertEqual(found[0]["severity"], "high")
        self.assertTrue(_ScriptedModel.seen and all(s["path"] == "/v1/chat/completions" and "code_comment" in s["tools"]
                                                    and s["authorization"] == "Bearer sk-test-not-a-key"
                                                    for s in _ScriptedModel.seen))
        summary = output["summary"]
        self.assertEqual((summary["input_tokens"], summary["output_tokens"]),
                         (100 * len(_ScriptedModel.seen), 20 * len(_ScriptedModel.seen)))
        self.assertEqual(git(self.repo, "status", "--porcelain", "--ignored"), "")   # OCR wrote nothing in the repository


if __name__ == "__main__":
    unittest.main()
