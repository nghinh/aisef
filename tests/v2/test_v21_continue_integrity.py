"""V2.1 (D): a continued run is the one it says it is — interrupted for real (SIGKILL, so no `finally` runs) at each
point that matters, then continued (`aisef bundle continue`, `aisef run --parent`), with the lineage checked:

* no story committed or merged twice across the lineage (journal story/commit events; merge commits reachable from the
  final main), no plan obligation lost (carried and proved again, or delivered), no cost lost or counted twice (the
  lineage total is each run's own streams once; a killed run's cost is never `known`);
* points: in the developer session after its tokens were reported, before any record (the run has only its
  RUN.started.json); after the merge moved main but before the journal committed the story; after a story committed;
  inside a probe evaluation (and the probe processes a killed run leaves, measured); two runs continuing one
  predecessor at once — exactly one claims it;
* a journal whose last line was torn (a power cut, not a signal: an append is one write and one fsync) is the reader's
  verified prefix — the cut event did not happen — and the report says so; a corrupt line before the end is refused;
* the evidence anchor (docs/v2.1/ANCHOR-THREAT-MODEL.md): an attacker who can write both the run directory and the
  anchor's store makes a consistent forgery `--verify --expect-anchor` accepts (the limit, measured); one who cannot
  write the store is refuted.

Offline: a fake developer (per story code, a kill hook), the fake provider of test_app_run; drivers run R.execute in
a subprocess so the kill is real."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import signal
import subprocess
import sys
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle, bundle_cli, usage  # noqa: E402
from aisef2.app import run as R  # noqa: E402
from aisef2.app.verify import verify  # noqa: E402
from aisef2.journal import format3  # noqa: E402
from tests.v2.test_app_run import ADD, SETTINGS, ProductBase, git  # noqa: E402
from tests.v2.test_v21_continue_usage import AUTHORING, PRICES  # noqa: E402

MUL = ADD + "\n\ndef mul(a, b):\n    return a * b\n"
#: S2's candidate when the probe is the kill point: mul announces itself, then takes its time
MUL_SLOW = ADD + ("\n\ndef mul(a, b):\n    import pathlib, time\n    pathlib.Path({marker!r}).write_text('in mul')\n"
                  "    time.sleep(20)\n    return a * b\n")
TEST_ADD = "import unittest\n\nfrom app import calc\n\n\nclass T(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(calc.add(2, 3), 5)\n"
TEST_MUL = "import unittest\n\nfrom app import calc\n\n\nclass T(unittest.TestCase):\n    def test_mul(self):\n        self.assertEqual(calc.mul(2, 3), 6)\n"

#: the developer: per story the code it writes (S2's from mul.py), a kill hook: kill.json {"title", "pid_file"} — after
#: the step's tokens are reported, the run's process is SIGKILLed (what was spent is in the stream, nothing recorded)
FAKE = r'''import json, os, pathlib, signal, sys
argv = sys.argv[1:]
if argv == ["--version"]:
    print("0.0.0-fake")
    raise SystemExit(0)
here = pathlib.Path(__file__).parent
title, cwd = argv[argv.index("--title") + 1], pathlib.Path(argv[argv.index("--dir") + 1])
if title == "developer S1":
    (cwd / "app" / "calc.py").write_text(ADD)
    (cwd / "tests").mkdir(exist_ok=True)
    (cwd / "tests" / "__init__.py").write_text("")
    (cwd / "tests" / "test_add.py").write_text(TEST_ADD)
elif title == "developer S2":
    (cwd / "app" / "calc.py").write_text((here / "mul.py").read_text())
    (cwd / "tests" / "test_mul.py").write_text(TEST_MUL)
print(json.dumps({"type": "text", "part": {"text": '{"findings": []}' if title.startswith("reviewer") else "done"}}))
print(json.dumps({"type": "step_finish", "part": {"tokens": {"input": 120, "output": 7, "reasoning": 3,
                                                             "cache": {"read": 10, "write": 0}}}}), flush=True)
kill = here / "kill.json"
if kill.exists():
    k = json.loads(kill.read_text())
    if k["title"] == title:
        os.kill(int(pathlib.Path(k["pid_file"]).read_text()), signal.SIGKILL)
'''

#: runs R.execute as the test would, in a process of its own, with an optional kill point
DRIVER = r'''import json, os, pathlib, signal, sys, threading, time
cfg = json.loads(pathlib.Path(sys.argv[1]).read_text())
sys.path.insert(0, cfg["root"])
from aisef2.app import adapters as ad, bundle, settings, run as R
from aisef2.orchestrate import story_runner as sr
from tests.v2.test_app_run import provider
ad.scanner = lambda: ad.NoScanner()
pathlib.Path(cfg["pid_file"]).write_text(str(os.getpid()))
def die():
    os.kill(os.getpid(), signal.SIGKILL)
point = cfg.get("point")
if point == "after-merge":          # S2's merge moved main; the journal has not committed S2
    real_reprove = sr.reprove
    def reprove(run, story_id, *a, **k):
        if story_id == "S2":
            die()
        return real_reprove(run, story_id, *a, **k)
    sr.reprove = reprove
elif point == "after-commit":       # S1 committed; S2 not begun
    real_run_story = sr.run_story
    def run_story(run, plan, story_id, *a, **k):
        if story_id == "S2":
            die()
        return real_run_story(run, plan, story_id, *a, **k)
    sr.run_story = run_story
elif point == "in-probe":           # the candidate is being evaluated by a probe
    marker = pathlib.Path(cfg["marker"])
    def watch():
        while not marker.exists():
            time.sleep(0.02)
        import subprocess
        ps = subprocess.run(["ps", "-axo", "pid=,pgid=,command="], capture_output=True, text=True, encoding="utf-8").stdout
        pathlib.Path(cfg["ps_before"]).write_text("\n".join(ln for ln in ps.splitlines() if cfg["out"] in ln))
        die()
    threading.Thread(target=watch, daemon=True).start()
elif point == "together":           # start the run at the same moment as its rival
    while not pathlib.Path(cfg["go"]).exists():
        time.sleep(0.005)
project = bundle.load(json.loads(pathlib.Path(cfg["bundle"]).read_text()))
s = settings.load(json.loads(pathlib.Path(cfg["settings"]).read_text()))
parent = pathlib.Path(cfg["parent"]) if cfg.get("parent") else None
rec = R.execute(project, s, pathlib.Path(cfg["source"]), pathlib.Path(cfg["out"]), transport=provider(),
                client_exe=cfg["client"], cals=R.calibrations(), predecessor=parent)
print(json.dumps({"outcomes": rec["story_outcomes"], "failure": rec["failure"]}))
'''


@unittest.skipUnless(os.name == "posix", "the fake client is a script started by its shebang; the kill is SIGKILL")
class Lineage(ProductBase):
    """S1 (add) and S2 (mul) of the two-story calc bundle, both deliverable."""

    def setUp(self) -> None:
        super().setUp()
        doc, _ = bundle_cli.seal(AUTHORING, repo=self.tmp / "source")
        for c in ("BC-ADD", "BC-MUL"):
            doc = bundle_cli.approve(doc, c, "human:t", 1.0)
        self.doc = doc
        self.client.write_text(f"#!{sys.executable}\nADD = {ADD!r}\nTEST_ADD = {TEST_ADD!r}\nTEST_MUL = {TEST_MUL!r}\n" + FAKE)
        self.mul(MUL)
        self.settings_doc = {**SETTINGS, "prices": PRICES}
        self.drivers = 0

    def execute(self, out: str = "out", **kw) -> dict:
        from tests.v2.test_app_run import provider
        kw.setdefault("transport", provider())
        return R.execute(self.project, self.settings, kw.pop("source", self.tmp / "source"), self.tmp / out,
                         client_exe=str(self.client), cals=R.calibrations(), **kw)

    def mul(self, text: str) -> None:
        (self.client.parent / "mul.py").write_text(text)

    def drive(self, out: str, doc: dict, point: str | None = None, parent: pathlib.Path | None = None,
              source: pathlib.Path | None = None, wait: bool = True, **extra):
        self.drivers += 1
        d = self.tmp / f"driver-{self.drivers}"
        d.mkdir()
        (d / "bundle.json").write_text(json.dumps(doc))
        (d / "settings.json").write_text(json.dumps(self.settings_doc))
        (d / "driver.py").write_text(DRIVER)
        cfg = {"root": str(ROOT), "pid_file": str(d / "pid"), "point": point, "bundle": str(d / "bundle.json"),
               "settings": str(d / "settings.json"), "source": str(source or self.tmp / "source"), "out": str(self.tmp / out),
               "client": str(self.client), "parent": str(parent) if parent else None, **extra}
        (d / "cfg.json").write_text(json.dumps(cfg))
        env = {**os.environ, "PYTHONPATH": str(ROOT)}
        p = subprocess.Popen([sys.executable, str(d / "driver.py"), str(d / "cfg.json")], cwd=str(ROOT), env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
        if not wait:
            return p
        stdout, stderr = p.communicate(timeout=600)
        return p.returncode, stdout, stderr

    def journal(self, out: str):
        return format3.reconstruct((self.tmp / out / "run" / "journals" / "aisef-run.jsonl").read_text(encoding="utf-8")).events

    def continue_and_finish(self, first: str) -> tuple[dict, dict, dict]:
        """`aisef bundle continue` of the killed run, then `aisef run --parent` to the end (S2 deliverable)."""
        self.mul(MUL)
        (self.client.parent / "kill.json").write_text(json.dumps({"title": "(disarmed)", "pid_file": ""}))
        doc, report = bundle_cli.continue_from(self.doc, self.tmp / first)
        self.project = bundle.load(doc)
        import aisef2.app.settings as S
        self.settings = S.load(self.settings_doc)
        rec = self.execute("second", source=self.tmp / first / "repo", predecessor=self.tmp / first)
        return doc, report, rec

    def assert_one_lineage(self, first: str, rec: dict) -> None:
        commits = [e.data["story_id"] for out in (first, "second") for e in self.journal(out) if e.type == "story/commit"]
        self.assertEqual(sorted(s for s in commits if s in ("S1", "S2")), ["S1", "S2"])     # each once, across the lineage
        merges = git(self.tmp / "second" / "repo", "log", "--merges", "--format=%s", "main").splitlines()
        self.assertEqual(len(merges), 2, merges)                                           # S1's and S2's, once each
        self.assertEqual((rec["delivery_verdict"], rec["productproof"]["delivered"], rec["productproof"]["total"]),
                         ("PASS", 2, 2))                                                  # carried C-ADD and C-MUL
        own = {k: 0 for k in usage.CLASSES}
        for out in (first, "second"):
            for log in (self.tmp / out / "sessions").glob("*.jsonl"):
                for k, v in usage.session_tokens(log)["tokens"].items():
                    own[k] += v
        self.assertEqual(rec["lineage_usage"]["tokens"], own)                               # every stream, once
        self.assertEqual(rec["usage"]["tokens"], {k: sum(usage.session_tokens(p)["tokens"][k] for p in
                                                        (self.tmp / "second" / "sessions").glob("*.jsonl"))
                                                  for k in usage.CLASSES})                # own: only its own

    def test_killed_in_the_developer_session_after_spending_before_any_record(self):
        (self.client.parent / "kill.json").write_text(json.dumps({"title": "developer S2",
                                                                  "pid_file": str(self.tmp / "driver-1" / "pid")}))
        code, _, _ = self.drive("first", self.doc)
        self.assertEqual(code, -signal.SIGKILL)
        first = self.tmp / "first"
        self.assertFalse((first / "RUN.json").exists())
        self.assertTrue((first / R.STARTED).exists())
        spent = usage.session_tokens(next((first / "sessions").glob("S2.developer.*.jsonl")))
        self.assertEqual(spent["tokens"]["input"], 120)                                      # spent, never recorded
        doc, report, rec = self.continue_and_finish("first")
        self.assertEqual((report["recorded"], report["carried"], report["remaining"]), (False, ["S1"], ["S2"]))
        self.assertEqual(rec["continues"]["recorded"], False)
        self.assertIsNone(rec["continues"]["evidence_anchor"])                               # it never had one
        killed = rec["lineage_usage"]["runs"][0]
        self.assertEqual((killed["recorded"], killed["cost"]["value"]), (False, None))
        self.assertIn("no record", killed["cost"]["status"])
        self.assertEqual(rec["lineage_usage"]["cost"]["value"], None)                       # unknown, not 0
        self.assertIsInstance(rec["usage"]["cost"]["value"], float)                         # this run's own is known
        self.assert_one_lineage("first", rec)

    def test_killed_after_the_merge_before_the_journal_committed_it(self):
        code, _, _ = self.drive("first", self.doc, point="after-merge")
        self.assertEqual(code, -signal.SIGKILL)
        events = self.journal("first")
        self.assertEqual([e.data["story_id"] for e in events if e.type == "story/commit"], ["S1"])
        first_main = git(self.tmp / "first" / "repo", "rev-parse", "main")
        s1 = next(e.data["revision"] for e in events if e.type == "story/commit")
        self.assertNotEqual(first_main, s1)                                                 # S2's merge moved main
        doc, report, rec = self.continue_and_finish("first")
        self.assertEqual(report["baseline"], s1)
        self.assertIn("left out", report["in_flight"])
        self.assertNotIn(first_main, git(self.tmp / "second" / "repo", "rev-list", "main").splitlines())
        self.assert_one_lineage("first", rec)

    def test_killed_after_a_commit(self):
        code, _, _ = self.drive("first", self.doc, point="after-commit")
        self.assertEqual(code, -signal.SIGKILL)
        doc, report, rec = self.continue_and_finish("first")
        self.assertEqual((report["carried"], report["in_flight"]), (["S1"], None))
        self.assertEqual(rec["story_outcomes"], {"CARRIED": ["COMMIT"], "S2": ["COMMIT"]})
        self.assert_one_lineage("first", rec)

    def test_killed_inside_a_probe_evaluation(self):
        marker = self.tmp / "in-mul"
        self.mul(MUL_SLOW.format(marker=str(marker)))
        started = time.monotonic()
        before = self.tmp / "ps-before.txt"
        code, _, _ = self.drive("first", self.doc, point="in-probe", marker=str(marker), ps_before=str(before))
        self.assertEqual(code, -signal.SIGKILL)
        killed_at = time.monotonic()
        alive = [ln for ln in before.read_text().splitlines() if "pycache_prefix" in ln]
        self.assertTrue(alive, "no probe process was alive when the run was killed: the measurement would be vacuous")
        # the range anchor's watchdog (aisef2/runtime/range_anchor.py): end of file on its stdin — its controller gone —
        # kills its whole process group, so the probe's controller and the candidate's process die with the run
        def left() -> list[str]:
            ps = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True, encoding="utf-8").stdout
            return [ln for ln in ps.splitlines() if str(self.tmp / "first") in ln]
        deadline = time.monotonic() + 30
        while left() and time.monotonic() < deadline:
            time.sleep(0.2)
        self.assertEqual(left(), [], "probe processes of the killed run were still alive 30 s later")
        print(f"\n[in-probe kill] {len(alive)} probe process(es) alive at the kill ({killed_at - started:.1f} s into the "
              f"run); none left {time.monotonic() - killed_at:.1f} s after it", file=sys.stderr)
        doc, report, rec = self.continue_and_finish("first")
        self.assertEqual(report["carried"], ["S1"])
        self.assert_one_lineage("first", rec)

    def test_two_runs_continuing_one_predecessor_at_once_one_claims_it(self):
        code, _, _ = self.drive("first", self.doc, point="after-commit")
        self.assertEqual(code, -signal.SIGKILL)
        doc, _ = bundle_cli.continue_from(self.doc, self.tmp / "first")
        go = self.tmp / "go"
        a = self.drive("a", doc, point="together", parent=self.tmp / "first", source=self.tmp / "first" / "repo",
                       wait=False, go=str(go))
        b = self.drive("b", doc, point="together", parent=self.tmp / "first", source=self.tmp / "first" / "repo",
                       wait=False, go=str(go))
        time.sleep(1.5)
        go.write_text("go")
        results = {}
        for name, p in (("a", a), ("b", b)):
            p.communicate(timeout=600)
            rec = json.loads((self.tmp / name / "RUN.json").read_text(encoding="utf-8"))
            results[name] = {"outcomes": rec["story_outcomes"], "failure": rec["failure"]}
        refused = [n for n, r in results.items() if (r.get("failure") or {}).get("type") == "RunRefused"]
        self.assertEqual(len(refused), 1, results)
        loser, winner = refused[0], ("b" if refused[0] == "a" else "a")
        self.assertIn("already continued by", results[loser]["failure"]["detail"])
        claim = json.loads((self.tmp / "first" / R.CLAIM).read_text())
        self.assertEqual(claim["run"], str(self.tmp / winner))
        self.assertEqual(results[winner]["outcomes"], {"CARRIED": ["COMMIT"], "S2": ["COMMIT"]})
        self.assertFalse((self.tmp / loser / "run").exists())        # the refused run began nothing

    def test_a_completed_continuation_leaves_the_predecessors_evidence_byte_identical(self):
        code, _, _ = self.drive("first", self.doc, point="after-commit")
        self.assertEqual(code, -signal.SIGKILL)
        first = self.tmp / "first"
        before = {p.relative_to(first).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in first.rglob("*") if p.is_file() and "repo" not in p.relative_to(first).parts[:1]}
        self.continue_and_finish("first")
        after = {p.relative_to(first).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in first.rglob("*") if p.is_file() and "repo" not in p.relative_to(first).parts[:1]}
        self.assertEqual(set(after) - set(before), {R.CLAIM})          # one new file: the claim
        self.assertEqual({k: after[k] for k in before}, before)        # nothing of its evidence changed

    def test_a_torn_journal_tail_is_the_verified_prefix_and_a_corrupt_line_is_refused(self):
        code, _, _ = self.drive("first", self.doc, point="after-commit")
        self.assertEqual(code, -signal.SIGKILL)
        _, intact = bundle_cli.continue_from(self.doc, self.tmp / "first")
        self.assertFalse(intact["torn_tail"])
        copy = self.tmp / "copy"
        shutil.copytree(self.tmp / "first", copy, symlinks=True)
        journal = copy / "run" / "journals" / "aisef-run.jsonl"
        data = journal.read_bytes()
        lines = data.split(b"\n")
        commit = next(n for n, ln in enumerate(lines) if b'"story/commit"' in ln)
        journal.write_bytes(b"\n".join(lines[: commit + 1]) + b"\n" + lines[commit + 1][:40])   # cut after S1's commit
        _, report = bundle_cli.continue_from(self.doc, copy)
        self.assertEqual((report["torn_tail"], report["carried"], report["baseline"]),
                         (True, ["S1"], intact["baseline"]))
        cut = b"\n".join(lines[:commit]) + b"\n" + lines[commit][:40]                       # S1's commit itself cut
        journal.write_bytes(cut)
        with self.assertRaises(bundle.BundleError) as c:
            bundle_cli.continue_from(self.doc, copy)
        self.assertIn("committed no story", str(c.exception))                                # it did not happen
        middle = bytearray(data)
        middle[data.index(b'"story/commit"') + 2] ^= 0x20                                      # a corrupt middle line
        journal.write_bytes(bytes(middle))
        with self.assertRaises(bundle.BundleError) as c:
            bundle_cli.continue_from(self.doc, copy)
        self.assertIn("does not reconstruct", str(c.exception))


@unittest.skipUnless(os.name == "posix", "the fake client is a script started by its shebang")
class AnchorThreatModel(ProductBase):
    """The anchor is as trustworthy as the place it is kept (docs/v2.1/ANCHOR-THREAT-MODEL.md)."""

    def setUp(self) -> None:
        super().setUp()
        self.rec = self.execute()
        self.out = self.tmp / "out"
        self.store = self.tmp / "operator-only"
        self.store.mkdir()
        (self.store / "out.anchor").write_text(R.anchor_in(self.out) + "\n")

    def forge(self) -> str:
        """Rewrite a session stream consistently: the evidence manifest re-made, its new anchor computed."""
        log = next((self.out / "sessions").glob("S1.developer.*.jsonl"))
        log.write_text(log.read_text().replace('"done"', '"done (rewritten)"'))
        manifest = R.evidence_manifest(self.out)
        (self.out / R.MANIFEST).write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
        return R.anchor_of(manifest)

    def test_the_limit_an_attacker_who_can_write_the_store_too_is_not_detected(self):
        forged = self.forge()
        (self.store / "out.anchor").write_text(forged + "\n")          # the same permissions: the store rewritten too
        v = verify(self.project, self.out, expect_anchor=(self.store / "out.anchor").read_text().strip())
        self.assertEqual(v["verdict"], "VERIFIED")                      # undetectable: the anchor's store is the trust

    def test_an_attacker_who_cannot_write_the_store_is_refuted(self):
        self.forge()
        v = verify(self.project, self.out, expect_anchor=(self.store / "out.anchor").read_text().strip())
        self.assertEqual(v["verdict"], "REFUTED")

    def test_anchor_out_names_a_new_file_for_a_run(self):
        from aisef2.app import cli
        common = ["--project", str(self.tmp / "bundle.json"), "--out", str(self.tmp / "x")]
        for argv in (["--settings", "s", "--repo", "r", *common, "--anchor-out", str(self.store / "out.anchor")],   # exists
                     ["--verify", *common, "--anchor-out", str(self.store / "new.anchor")]):                   # not a run
            with self.subTest(argv[0]), self.assertRaises(SystemExit) as c:
                cli.run(argv)
            self.assertEqual(c.exception.code, 2)
        self.assertEqual((self.store / "out.anchor").read_text().strip(), R.anchor_in(self.out))   # untouched


if __name__ == "__main__":
    unittest.main()
