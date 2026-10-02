"""K-NOWORK-001 (owner ruling 'AISEF V2 — K-NOWORK-001 MEASURED ARCHITECTURE CORRECTION', 2026-10-02) — the defect
reproduced and the correction measured, under both kernels, through the real story runner. No provider, no model, no
LedgerLock repository; recorded separately from K-PRESAT-001.

    python -P validation/qualification/c2_k_nowork_001.py --write   # -> closure-evidence/v2/cycle2/K-NOWORK-001-REHEARSAL.json (minutes)
    python -P validation/qualification/c2_k_nowork_001.py --check   # the record's bound identities are this tree's (nothing is re-run)

Two measurements, each made twice — on the kernel before the correction (`BEFORE`, read from git's object store into a
temporary directory) and on this tree's kernel — in a child process whose `aisef2` is the kernel under measurement:

* **the regression cases** (tests/v2/test_c2_k_nowork_001.py): A and B are red before and green after; C, D and E are
  green under both — the correction changes nothing for them.
* **a LedgerLock-shaped rehearsal**: the corrected plan (7 stories, 67 obligations) and its 59 ProductProofSpecs, each
  on its own real probe, through `story_runner.run_story`; the developer is a stand-in that, whenever it is called,
  installs the P5 reference implementation and the story's unittest file — so the first story over-delivers, legitimately,
  everything the later stories would introduce. Before: the stories left with only PRESERVE / VERIFY work are sent to
  the developer and rolled back TESTS_INADEQUATE while the product satisfies every spec. After: every story commits,
  the developer is called for the first story only, and the product is the same.

H-REGRESSION-001 (found reviewing this correction; the harness, not the kernel): the runner named the test file of every
committed story as a regression test of the next — also of a story that committed without a developer call, which wrote
none. The same rehearsal with a developer that over-delivers PARTLY (its first delivery gets one later behaviour wrong:
the reference with the fixture's mutant `PARTIAL`; called again, it installs the reference and tests what it fixed),
on this tree's kernel, with the set the runner used to build and with `c2_p9.regression_tests`: before, the story that
fixes the behaviour is rolled back TESTS_INADEQUATE for test files nobody was asked to write, and the product is left
wrong; after, it commits and the product satisfies every spec.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT_REL = "closure-evidence/v2/cycle2/K-NOWORK-001-REHEARSAL.json"
AUTHORITY = ("owner ruling 'AISEF V2 — K-NOWORK-001 MEASURED ARCHITECTURE CORRECTION / OWNER RULING / NO PROVIDER CALL / NO "
             "LEDGERLOCK RUN / NO Q4-Q5' (2026-10-02)")
BEFORE = "d427299376d7af48d3dd6d86242bf5def6a43003"         # K-PRESAT-001: the kernel the defect was measured on
BEFORE_TREE = "4fe9ccaab17d7cac03b5e578ee1ecb57d04b8160"
CASES = "tests.v2.test_c2_k_nowork_001"
BOUND = ("aisef2/orchestrate/story_runner.py", "tests/v2/test_c2_k_nowork_001.py", "validation/qualification/c2_k_nowork_001.py",
         "closure-evidence/v2/cycle2/PLAN-V2.2-CORRECTION-1.json", "validation/qualification/c2_p9.py")
#: the reference mutant a partly over-delivering developer's first delivery is (R-7: repair-tail on an intact chain removes
#: its last line — S-7-d, STORY-04-01's to introduce), and the story that then has developer work
PARTIAL, PARTIAL_STORY, PARTIAL_SPEC = "M-7-1", "STORY-04-01", "S-7-d"
MUTANTS = "tests/v2/fixtures/workloads/ledgerlock-reference/mutants"
ATTEMPT_2 = "closure-evidence/v2/cycle2/P10/attempt-2/JOURNAL.json"
NOT_RULED = "VERIFY_NO_INTRODUCER_UNSATISFIED_REQUIRES_OWNER_DECISION"
MARK = "K-NOWORK-001-RESULT "
CHILD = """
import json, sys
kernel, root, job = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path[:0] = [p for p in (kernel, root) if p]
import aisef2                     # the kernel under measurement: its package path is fixed from here on
sys.path.insert(0, root)          # everything else — tests, validation — is this tree's, whatever the kernel's root also holds
from validation.qualification import c2_k_nowork_001 as kn
print(kn.MARK + json.dumps({"kernel_file": aisef2.__file__, "result": kn.JOBS[job]()}, default=str), flush=True)
"""
TEST = ("import tempfile, unittest, pathlib\nfrom ledgerlock.ledger import Ledger, ConflictError\n\n\nclass T(unittest.TestCase):\n"
        "    def test_put_replay_conflict_verify_snapshot(self):\n        with tempfile.TemporaryDirectory() as d:\n"
        "            p = pathlib.Path(d) / 'l.jsonl'\n            p.write_text('')\n            led = Ledger(str(p))\n"
        "            led.apply_batch([['put', 'a', 1, 'r1', 1]])\n            led.apply_batch([['put', 'a', 1, 'r1', 2]])\n"
        "            with self.assertRaises(ConflictError):\n                led.apply_batch([['delete', 'a', None, 'r9', 3]])\n"
        "            led.verify()\n            led.snapshot()\n            self.assertEqual(len(p.read_text().splitlines()), 1)\n")
#: what a developer asked to make repair-tail a no-op on a clean chain tests (the behaviour `PARTIAL` gets wrong)
TEST_REPAIR = ("\n    def test_repair_tail_is_a_no_op_on_a_clean_chain(self):\n        with tempfile.TemporaryDirectory() as d:\n"
               "            p = pathlib.Path(d) / 'l.jsonl'\n            p.write_text('')\n            led = Ledger(str(p))\n"
               "            led.apply_batch([['put', 'a', 1, 'r1', 1]])\n            before = p.read_bytes()\n"
               "            self.assertFalse(led.repair_tail())\n            self.assertEqual(p.read_bytes(), before)\n")


# ---------------------------------------------------------------------------------------------------- the jobs

def job_cases() -> dict:
    """Every regression case, by name, under the kernel this process imported."""
    import unittest
    out: dict[str, str] = {}

    class Result(unittest.TestResult):
        def addSuccess(self, test):
            out[test.id().split(".", 3)[-1]] = "PASS"

        def addFailure(self, test, err):
            out[test.id().split(".", 3)[-1]] = "FAIL"

        def addError(self, test, err):
            out[test.id().split(".", 3)[-1]] = "ERROR"
    unittest.defaultTestLoader.loadTestsFromName(CASES).run(Result())
    return dict(sorted((k, v) for k, v in out.items() if not k.startswith("Record.")))     # the record's own checks are not a case


class ReferenceDeveloper:
    """A stand-in developer (never a model): called, it installs the P5 reference implementation — written from the
    requirements, satisfying all 59 specs — and the story's unittest file, and commits. With `first_wrong`, its first
    delivery is the reference with that mutant's files (one later behaviour wrong); called again it installs the
    reference and tests the behaviour it fixed."""

    def __init__(self, first_wrong: str | None = None) -> None:
        self.calls: list[tuple[str, tuple[str, ...]]] = []
        self.first_wrong = first_wrong

    def implement(self, story_id: str, criteria: tuple[str, ...], checkout: str):
        from aisef2.journal.format2 import OperationOutcome as O
        from aisef2.orchestrate.adapters import Implemented
        from aisef2.orchestrate.workspace import commit_all
        from validation.qualification import c2_p9
        from validation.qualification import p5_falsifiability as pf
        self.calls.append((story_id, tuple(criteria)))
        root = pathlib.Path(checkout)
        (root / "ledgerlock").mkdir(exist_ok=True)
        for name, text in pf.reference_modules().items():
            (root / "ledgerlock" / name).write_text(text, encoding="utf-8", newline="\n")
        first = len(self.calls) == 1
        if self.first_wrong and first:
            for f in sorted((ROOT / MUTANTS / self.first_wrong).glob("*.py")):
                (root / "ledgerlock" / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
        (root / "tests").mkdir(exist_ok=True)
        (root / "tests" / "__init__.py").write_text("", encoding="utf-8")
        (root / c2_p9.test_path(story_id)).write_text(TEST + (TEST_REPAIR if self.first_wrong and not first else ""),
                                                      encoding="utf-8", newline="\n")
        return Implemented(O.COMPLETED, commit_all(checkout, f"{story_id}: the reference implementation and the story's test"), "stand-in developer")


class NoFindingsReviewer:
    def review(self, scope, criteria: tuple[str, ...]):
        from aisef2.journal.format2 import OperationOutcome as O
        from aisef2.orchestrate.adapters import Reviewed
        return Reviewed(O.COMPLETED, (), "stand-in reviewer: no findings")


class QuietScanner:
    """A scanner that runs (in the kernel's own process range) and reports no finding."""
    name = "quiet"

    def argv(self, scope, report: str) -> tuple[str, ...]:
        return (sys.executable, "-c", "import sys; open(sys.argv[1], 'w').write('[]')", report)

    def read(self, report: str, exit_code):
        from aisef2.orchestrate.adapters import Scanned
        return Scanned(pathlib.Path(report).exists(), ())


def job_rehearsal(first_wrong: str | None = None, name_every_committed_story: bool = False) -> dict:
    """The corrected plan and its 59 specs through the real story runner, with the stand-in developer. The regression
    set of a story is the runner's (`c2_p9.regression_tests`) — or, with `name_every_committed_story`, the one the runner
    built before H-REGRESSION-001."""
    from aisef2.arch.enums import ControlProjection, Enforcement, Owner
    from aisef2.orchestrate import story_runner as sr
    from aisef2.orchestrate.quality import TestsPolicy
    from aisef2.orchestrate.workspace import GitMerger, GitWorkspace, commit_all, git
    from aisef2.probe import catalog
    from aisef2.probe.protocol import ExecutionEnv
    from aisef2.product.contract import plain
    from aisef2.quality import test_execution as te
    from aisef2.runtime.capability import verified
    from aisef2.runtime.run_scope import RunScope
    from aisef2.runtime.runspec import resolve
    from validation.qualification import c2_delivery_experiment as dx
    from validation.qualification import c2_p9
    from validation.qualification import c2_plan_correction as pc
    from validation.qualification import p10_contracts as aid
    plan = pc.corrected_plan()
    specs = {s.id: s for s in c2_p9._compiled().values()}
    with tempfile.TemporaryDirectory(prefix="aisef2-k-nowork-") as d:
        tmp = pathlib.Path(d).resolve()
        repo = tmp / "repo"
        repo.mkdir()
        git(repo, "init", "-q", "-b", "main")
        (repo / "README.md").write_text("LedgerLock-shaped rehearsal: an empty project\n", encoding="utf-8")
        base = commit_all(repo, "base")
        for n in ("ws", "merge", "run"):
            (tmp / n).mkdir()
        run = RunScope(tmp / "run", "k-nowork-001-rehearsal",
                       spec=lambda: resolve([verified("kernel", b"k-nowork-001 rehearsal", Enforcement.FULL)], {}, base))
        run.begin()
        dev = ReferenceDeveloper(first_wrong)
        adapters = sr.Adapters(dev, NoFindingsReviewer(), QuietScanner(), GitMerger(repo, "main", tmp / "merge"), GitWorkspace(repo, tmp / "ws"))
        factories = {e.probe_id: (lambda on_range, scratch, f=e.factory: f(on_range=on_range, scratch=scratch)) for e in catalog.CATALOG}
        env = ExecutionEnv(sys.executable, 60, Enforcement.PARTIAL)
        limits = {Owner[k]: v for k, v in c2_p9.PROFILES[c2_p9.EXPERIMENT].items()}
        results, delivered = {}, []
        for story in c2_p9.order(plan, aid.story_graph()):
            regressions = (tuple(c2_p9.test_path(s) for s in delivered) or (c2_p9.test_path(story),)) if name_every_committed_story \
                else c2_p9.regression_tests(repo, story, delivered)
            inputs = sr.StoryInputs(specs, factories, env, te.DeveloperTests(story, (c2_p9.test_path(story),)),
                                    te.DeveloperTests(story, regressions), te.Dependencies(frozenset(), c2_p9.PROJECT), te.UNITTEST)
            r = sr.run_story(run, plan, story, inputs, adapters, sr.Policy(limits, TestsPolicy(True), tool_timeout_s=120))
            results[story] = [a.outcome for a in r.attempts]
            if results[story][-1:] == ["COMMIT"]:
                delivered.append(story)
        state = plain(run.state(ControlProjection.STORY_STATE))
        run.shutdown()
        events = [{"type": e.type, "data": plain(e.data)} for e in run.events]
        final = git(repo, "rev-parse", "main").stdout.strip()
        tree = tmp / "final"
        git(repo, "worktree", "add", "--detach", str(tree), final)
        proof = dx.final_proof(tree, final)
    stories = {}
    for e in events:
        s = e["data"].get("story_id")
        row = stories.setdefault(s, {"admissions": [], "developer_requests": 0, "review_requests": 0, "adequacy": [], "failures": []}) if s else None
        if e["type"] == "story/admitted":
            counts: dict[str, int] = {}
            for v in e["data"]["dispositions"].values():
                counts[v] = counts.get(v, 0) + 1
            row["admissions"].append(dict(sorted(counts.items())))
        elif e["type"] == "provider/request":
            row["developer_requests" if e["data"]["budget_owner"] == "DEVELOPER" else "review_requests"] += 1
        elif e["type"] == "tests/adequacy":
            row["adequacy"].append({**{k: e["data"].get(k) for k in ("outcome", "vacuity", "relevance")},
                                    "regressions": e["data"]["regressions"].get("selection")})
        elif e["type"] == "failure/observed":
            row["failures"].append(e["data"]["code"])
    return {"plan_hash": plan.plan_hash, "stories": len(results), "obligations": len(plan.obligations), "outcomes": results,
            "committed": sorted(delivered), "not_committed": sorted(s for s in results if s not in delivered),
            "developer_calls": [s for s, _ in dev.calls], "by_story": {s: stories.get(s) for s in results},
            "story_state_outcomes": {s: (state.get(s) or {}).get("outcome") for s in results},
            "final_main_satisfies": {k: proof[k] for k in ("total", "satisfied", "not_satisfied")}}


JOBS = {"cases": job_cases, "rehearsal": job_rehearsal,
        "partial_naming_every_committed_story": lambda: job_rehearsal(PARTIAL, name_every_committed_story=True),
        "partial": lambda: job_rehearsal(PARTIAL)}


def in_kernel(kernel_root: pathlib.Path | None, job: str) -> dict:
    """`job` in a child whose `aisef2` is the kernel under `kernel_root` (None: this tree's)."""
    r = subprocess.run([sys.executable, "-c", CHILD, str(kernel_root or ""), str(ROOT), job], capture_output=True, encoding="utf-8",
                       errors="replace", cwd=ROOT, timeout=3600)
    line = next((x for x in r.stdout.splitlines() if x.startswith(MARK)), None)
    if line is None:
        raise SystemExit(f"{job} left no result (exit {r.returncode}): {r.stderr[-1500:]}")
    out = json.loads(line[len(MARK):])
    want = str(kernel_root or ROOT)
    if not str(pathlib.Path(out["kernel_file"]).resolve()).startswith(str(pathlib.Path(want).resolve())):
        raise SystemExit(f"{job} ran under {out['kernel_file']}, not the kernel under {want}")
    return out["result"]


# --------------------------------------------------------------------------------------------------- the record

def _rp():
    from validation.qualification import c2_orchestration_repair as rp
    return rp


def _bound() -> dict:
    rp = _rp()
    return {rel: rp._lf((ROOT / rel).read_bytes()) for rel in BOUND}


def measured_before_the_ruling() -> dict:
    """The real run that showed the shape first: QP-2.9 attempt 2's STORY-05-01, PRESERVE obligations only."""
    events = json.loads((ROOT / ATTEMPT_2).read_text(encoding="utf-8"))
    mine = [e for e in events if e["data"].get("story_id") == "STORY-05-01"]
    return {"journal": ATTEMPT_2, "story": "STORY-05-01",
            "admissions": [dict(e["data"]["dispositions"]) for e in mine if e["type"] == "story/admitted"],
            "developer_requests": sum(1 for e in mine if e["type"] == "provider/request" and e["data"]["budget_owner"] == "DEVELOPER"),
            "adequacy": [{k: e["data"].get(k) for k in ("outcome", "vacuity", "relevance")} for e in mine if e["type"] == "tests/adequacy"],
            "failures": [e["data"]["code"] for e in mine if e["type"] == "failure/observed"],
            "ended": [e["type"] for e in mine if e["type"] in ("story/commit", "story/rollback")]}


def write() -> dict:
    rp = _rp()
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="aisef2-kernel-before-k-nowork-") as t:
        old_root = pathlib.Path(t)
        old = rp.materialise(BEFORE, old_root)
        if old["aisef2_tree"] != BEFORE_TREE:
            raise SystemExit(f"{BEFORE}:aisef2 is {old['aisef2_tree']}, not {BEFORE_TREE}")
        before = {"cases": in_kernel(old_root, "cases"), "rehearsal": in_kernel(old_root, "rehearsal")}
    after = {"cases": in_kernel(None, "cases"), "rehearsal": in_kernel(None, "rehearsal")}
    partial = {"before": in_kernel(None, "partial_naming_every_committed_story"), "after": in_kernel(None, "partial")}
    rec = {
        "record": "AISEF V2 — K-NOWORK-001: a story with no developer work was sent to the developer and falsely rolled back — "
                  "the defect reproduced and the correction measured under both kernels",
        "authority": AUTHORITY,
        "separate_from": "K-PRESAT-001 (every obligation PRE_SATISFIED): its records and history are untouched",
        "defect": "a story admitted with every INTRODUCE obligation PRE_SATISFIED and its remaining PRESERVE / VERIFY obligations "
                  "already SATISFIED at the parent has no product behaviour left to introduce, yet a satisfied PRESERVE and any "
                  "VERIFY are READY (§13), so the developer was called; the no-op or tests-only result was then judged VACUOUS / "
                  "IRRELEVANT by engineering adequacy, and a correct product was rolled back",
        "ruling": "developer work is required only where an INTRODUCE obligation is READY. When none is and every obligation is "
                  "INTRODUCE + PRE_SATISFIED, PRESERVE + SATISFIED or VERIFY + SATISFIED: no developer call, no developer budget, no "
                  "engineering adequacy, candidate = parent; every obligation still proved at the candidate by both parties, review "
                  "and security as before, the post-merge proof, PLAN_DRIFT for each PRE_SATISFIED INTRODUCE. No new disposition",
        "correction": {"where": "aisef2/orchestrate/story_runner.py::_attempt",
                       "what": "one fact read from the admission already made — every obligation measured SATISFIED at the parent, "
                               "which on an admitted story is exactly the ruling's predicate (§13's table; pinned by the regression "
                               "module's Predicate case) — decides both the developer call and the adequacy stage",
                       "unchanged": "StoryAdmission and its dispositions (F7), ContractSatisfaction, routing, budgets, journal events "
                                    "and payloads, every contract, spec, probe and plan"},
        "not_ruled": {"code": NOT_RULED,
                      "case": "no INTRODUCE obligation READY and a VERIFY obligation measured UNSATISFIED at the parent",
                      "what_the_correction_does": "nothing: the case is not the correction's — the kernel does what it did before "
                                                  "(the READY VERIFY is the developer's work, adequacy runs); regression case E pins it",
                      "decision": "the owner's"},
        "kernel": {"before": old, "after": {"kernel_digest": rp.kernel_digest(ROOT / "aisef2"),
                                            "rule": "q4's kernel digest over this working tree's aisef2; the files below bind it by content"}},
        "cases": {"module": CASES, "before": before["cases"], "after": after["cases"]},
        "rehearsal": {"shape": "the corrected plan and its 59 ProductProofSpecs on their real probes through story_runner.run_story; "
                               "the delivery experiment's retry limits; TestsPolicy(blocking); a stand-in developer that installs the "
                               "P5 reference implementation and the story's unittest file whenever it is called; a stand-in reviewer "
                               "and scanner without findings; an empty temporary repository",
                      "before": before["rehearsal"], "after": after["rehearsal"]},
        "h_regression_001": {
            "defect": "the runner (validation/qualification/c2_p9.py — the harness, not the kernel) named the test file of every "
                      "committed story as a regression test of the next; a story that committed without a developer call "
                      "(K-PRESAT-001, K-NOWORK-001) wrote none, so the next story WITH developer work failed engineering adequacy "
                      "(regression tests not collectable) and was rolled back for a file nobody was asked to write",
            "correction": "c2_p9.regression_tests: only the test files main holds; with none, the story's own tests (as for the "
                          "first story). The kernel is unchanged by it",
            "shape": f"the rehearsal above on this tree's kernel, the stand-in developer over-delivering partly: its first delivery "
                     f"is the reference with the fixture's mutant {PARTIAL} ({PARTIAL_SPEC} wrong, {PARTIAL_STORY}'s to introduce); "
                     "called again it installs the reference and tests the behaviour it fixed",
            "before": partial["before"], "after": partial["after"]},
        "measured_before_the_ruling": measured_before_the_ruling(),
        "bound": _bound(),
        "provider_calls": 0, "ledgerlock_runs": 0,
        "platform": {"python": sys.version.split()[0], "platform": sys.platform},
    }
    rec["problems"] = problems(rec)
    rec["verdict"] = "REPRODUCED AND CORRECTED" if not rec["problems"] else "PROBLEMS"
    rec["seconds"] = round(time.monotonic() - started, 1)
    (ROOT / OUT_REL).write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return rec


def problems(rec: dict) -> list[str]:
    out = []
    b, a = rec["cases"]["before"], rec["cases"]["after"]
    red = sorted(k for k, v in b.items() if v != "PASS")
    if not a or sorted(a) != sorted(b) or any(v != "PASS" for v in a.values()):
        out.append(f"the regression cases are not all green on the corrected kernel: { {k: v for k, v in a.items() if v != 'PASS'} }")
    if not red or any(not k.startswith("NoDeveloperWork.") for k in red) or not any("test_A_" in k for k in red) or not any("test_B_" in k for k in red):
        out.append(f"the cases red before the correction are not exactly the no-developer-work ones (A and B): {red}")
    if any(v != "PASS" for k, v in b.items() if k.startswith(("DeveloperWorkRemains.", "Predicate."))):
        out.append("a case the correction must not change (C, D, E) was not green before it")
    rb, ra = rec["rehearsal"]["before"], rec["rehearsal"]["after"]
    for name, r in (("before", rb), ("after", ra)):
        if (r["stories"], r["obligations"]) != (7, 67) or r["final_main_satisfies"] != {"total": 59, "satisfied": 59, "not_satisfied": []}:
            out.append(f"rehearsal {name}: not the 7 stories / 67 obligations with a final main satisfying 59 of 59")
    false_rollbacks = {s: rb["by_story"][s] for s in rb["not_committed"]}
    if not false_rollbacks or any(set(v["failures"]) != {"TESTS_INADEQUATE"} or not v["developer_requests"] for v in false_rollbacks.values()):
        out.append(f"rehearsal before: the defect did not show as TESTS_INADEQUATE rollbacks of stories sent to the developer: {rb['outcomes']}")
    if ra["not_committed"] or any(v != ["COMMIT"] for v in ra["outcomes"].values()):
        out.append(f"rehearsal after: not every story committed at its first attempt: {ra['outcomes']}")
    if ra["developer_calls"] != ["STORY-01-01"]:
        out.append(f"rehearsal after: the developer was called for {ra['developer_calls']}, not for the first story only")
    if any(v["adequacy"] or v["failures"] for s, v in ra["by_story"].items() if s != "STORY-01-01"):
        out.append("rehearsal after: a story without developer work ran engineering adequacy or failed")
    hb, ha = rec["h_regression_001"]["before"], rec["h_regression_001"]["after"]
    row = hb["by_story"][PARTIAL_STORY]
    if hb["not_committed"] != [PARTIAL_STORY] or set(row["failures"]) != {"TESTS_INADEQUATE"} \
            or {a["regressions"] for a in row["adequacy"]} != {"STORY_TESTS_NOT_COLLECTABLE"} \
            or hb["final_main_satisfies"]["not_satisfied"] != [PARTIAL_SPEC]:
        out.append(f"partial over-delivery before: {PARTIAL_STORY} was not rolled back for regression files nobody wrote: {hb['outcomes']}")
    if ha["not_committed"] or any(v != ["COMMIT"] for v in ha["outcomes"].values()) or ha["developer_calls"] != ["STORY-01-01", PARTIAL_STORY] \
            or ha["final_main_satisfies"] != {"total": 59, "satisfied": 59, "not_satisfied": []}:
        out.append(f"partial over-delivery after: not every story committed at its first attempt with the product satisfying 59 of 59: {ha['outcomes']}")
    m = rec["measured_before_the_ruling"]
    if not (m["developer_requests"] and m["ended"] == ["story/rollback"] and set(m["failures"]) == {"TESTS_INADEQUATE"}):
        out.append("the real run's STORY-05-01 does not show the measured shape")
    return out


def check() -> list[str]:
    path = ROOT / OUT_REL
    if not path.exists():
        return [f"{OUT_REL} is missing"]
    rec = json.loads(path.read_text(encoding="utf-8"))
    out = [] if rec.get("verdict") == "REPRODUCED AND CORRECTED" and not rec.get("problems") else [f"the record's verdict is {rec.get('verdict')}"]
    out += problems(rec)
    out += [f"{rel} changed since the record" for rel, sha in _bound().items() if rec["bound"].get(rel) != sha]
    if rec["measured_before_the_ruling"] != measured_before_the_ruling():
        out.append("the real run's rows differ from the record")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", action="store_true")
    g.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    if a.write:
        rec = write()
        print(f"{OUT_REL}: {rec['verdict']} ({rec['seconds']} s)")
        for x in rec["problems"]:
            print(f"FAIL  {x}")
        return 0 if not rec["problems"] else 1
    found = check()
    print("\n".join(f"FAIL  {x}" for x in found) if found else "PASS")
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
