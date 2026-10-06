"""V2.1 (D): recovery around external effects — a run interrupted for real (SIGKILL: no `finally` runs) at a
synchronisation point inside each window that matters, then continued (`aisef bundle continue`, `aisef run --parent`).

Every kill point is a deterministic hook — a wrapped function or a step of the fake client — at a named moment, never a
random kill. The windows (app/lineage's docstring says what each event does and does not prove):

* a provider request: journaled but its client never started (nothing was sent: known 0); its client running, the
  request sent, no usage reported yet; its usage reported, its result not journaled — the last two are unknown spend,
  and a continuation starts no paid work until the operator accepts it (`--accept-unaccounted`), which is recorded;
* a commit: the developer's candidate committed, no event journaled (identified by the kernel's worktree, developed
  again); the merge moved main, the story not committed in the journal (identified by git: the kernel's merge of a
  proved candidate) — neither assumed undone, both left out of the continuation's baseline with their identity;
* a journal append of the story's commit: before the write, a short write (the writer killed mid-line: a torn tail
  whose effect — the merge — is still reconciled in git), after the write and before the fsync, after the fsync (a
  process kill keeps a written event: only a power loss or an OS crash could lose it, which no test here simulates);
* the claim: taken and the claimant killed before the child began (superseded by evidence, a new generation; nothing
  deleted); the child began and was killed (never superseded: the lineage continues from it); a claim whose child is
  missing and whose claimant is gone; a claimant alive, or on another host (refused; superseded only by the operator
  naming the claim's sha256); a finished continuation asked for again (refused, pointing at the child); two runs at
  once (exactly one claims, the other spends nothing).

And, measured rather than assumed: the probe processes a killed run leaves (identified by their process groups and
the candidate's own pid — all gone: the range anchor's watchdog kills its group), and a descendant that left its group
(setsid) — NOT controlled: it outlives the run (a normal run detects it as escaped: tests/v2/p4/test_process_range).
After each continuation: no story committed twice across the lineage, merges on the final main exactly the stories
delivered, no obligation lost, every session stream counted once in the lineage and a killed run's cost never `known`.
The evidence anchor's model: docs/v2.1/ANCHOR-THREAT-MODEL.md. Offline: a fake developer, the fake provider."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import signal
import socket
import subprocess
import sys
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle, bundle_cli, lineage, usage  # noqa: E402
from aisef2.app import run as R  # noqa: E402
from aisef2.app import settings as S  # noqa: E402
from aisef2.app.verify import verify  # noqa: E402
from aisef2.journal import format3  # noqa: E402
from tests.v2.test_app_run import ADD, SETTINGS, ProductBase, git  # noqa: E402
from tests.v2.test_v21_continue_usage import AUTHORING, PRICES  # noqa: E402

MUL = ADD + "\n\ndef mul(a, b):\n    return a * b\n"
#: S2's candidate when the probe is the kill point: mul writes its pid (and, detached, a grandchild's), then waits
MUL_SLOW = ADD + ("\n\ndef mul(a, b):\n    import os, pathlib, subprocess, sys, time\n"
                  "    if {detach!r}:\n"
                  "        g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(8)'], start_new_session=True)\n"
                  "        pathlib.Path({marker!r} + '.detached').write_text(str(g.pid))\n"
                  "    pathlib.Path({marker!r}).write_text(str(os.getpid()))\n"
                  "    time.sleep(20)\n    return a * b\n")
TEST_ADD = "import unittest\n\nfrom app import calc\n\n\nclass T(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(calc.add(2, 3), 5)\n"
TEST_MUL = "import unittest\n\nfrom app import calc\n\n\nclass T(unittest.TestCase):\n    def test_mul(self):\n        self.assertEqual(calc.mul(2, 3), 6)\n"

#: the developer: per story the code it writes (S2's from mul.py); kill.json {"title", "when", "pid_file"}: when the
#: session `title` reaches `when` ("before-step": the request sent, no usage yet; "after-step": its usage reported),
#: the run's process is SIGKILLed
FAKE = r'''import json, os, pathlib, signal, sys
argv = sys.argv[1:]
if argv == ["--version"]:
    print("0.0.0-fake")
    raise SystemExit(0)
here = pathlib.Path(__file__).parent
title, cwd = argv[argv.index("--title") + 1], pathlib.Path(argv[argv.index("--dir") + 1])
kill = json.loads((here / "kill.json").read_text()) if (here / "kill.json").exists() else {}
def maybe(when):
    if kill.get("title") == title and kill.get("when") == when:
        sys.stdout.flush()
        os.kill(int(pathlib.Path(kill["pid_file"]).read_text()), signal.SIGKILL)
        raise SystemExit(0)
if title == "developer S1":
    (cwd / "app" / "calc.py").write_text(ADD)
    (cwd / "tests").mkdir(exist_ok=True)
    (cwd / "tests" / "__init__.py").write_text("")
    (cwd / "tests" / "test_add.py").write_text(TEST_ADD)
elif title == "developer S2":
    (cwd / "app" / "calc.py").write_text((here / "mul.py").read_text())
    (cwd / "tests" / "test_mul.py").write_text(TEST_MUL)
print(json.dumps({"type": "text", "part": {"text": '{"findings": []}' if title.startswith("reviewer") else "done"}}), flush=True)
maybe("before-step")
print(json.dumps({"type": "step_finish", "part": {"tokens": {"input": 120, "output": 7, "reasoning": 3,
                                                             "cache": {"read": 10, "write": 0}}}}), flush=True)
maybe("after-step")
'''

#: R.execute in a process of its own; `point` names the synchronisation point at which it SIGKILLs itself
DRIVER = r'''import json, os, pathlib, signal, sys, threading, time
cfg = json.loads(pathlib.Path(sys.argv[1]).read_text())
sys.path.insert(0, cfg["root"])
from aisef2.app import adapters as ad, bundle, client, lineage, settings, run as R
from aisef2.journal import format3
from aisef2.orchestrate import story_runner as sr
from aisef2.runtime.run_scope import RunScope
from tests.v2.test_app_run import provider
ad.scanner = lambda: ad.NoScanner()
pathlib.Path(cfg["pid_file"]).write_text(str(os.getpid()))
def die():
    os.kill(os.getpid(), signal.SIGKILL)
point = cfg.get("point")
def wrap(owner, name, before=None, after=None):
    real = getattr(owner, name)
    def hooked(*a, **k):
        if before and before(*a, **k):
            die()
        out = real(*a, **k)
        if after and after(*a, **k):
            die()
        return out
    setattr(owner, name, hooked)
if point == "request-before-start":       # the developer's provider/request journaled; its client never started
    wrap(client, "session", before=lambda name, *a, **k: name == "developer S2")
elif point == "commit-before-event":      # the developer's candidate committed; nothing journaled about it
    wrap(ad, "commit_all", after=lambda checkout, message, **k: message.startswith("S2:"))
elif point == "merge-before-event":       # S2's merge moved main; its post-merge proof and commit not journaled
    wrap(sr, "reprove", before=lambda run, story_id, *a, **k: story_id == "S2")
elif point == "after-commit":             # S1 committed; S2 not begun
    wrap(sr, "run_story", before=lambda run, plan, story_id, *a, **k: story_id == "S2")
elif point == "claim-before-begin":       # the predecessor claimed; the child's run not begun
    wrap(lineage, "claim", after=lambda *a, **k: True)
elif point == "begun":                    # the child's run begun (its first event journaled), nothing else
    wrap(RunScope, "begin", after=lambda *a, **k: True)
elif point and point.startswith("journal-"):   # the append of S2's story/commit, at one of four points
    real_os = os
    class Os:
        armed = False
        def __getattr__(self, name):
            return getattr(real_os, name)
        def write(self, fd, data):
            target = b'"story/commit"' in data and b'"S2"' in data
            if target and point == "journal-before-write":
                die()
            if target and point == "journal-short-write":
                real_os.write(fd, data[: len(data) // 2])
                die()
            n = real_os.write(fd, data)
            self.armed = target
            return n
        def fsync(self, fd):
            if self.armed and point == "journal-after-write":
                die()
            real_os.fsync(fd)
            if self.armed and point == "journal-after-fsync":
                die()
            self.armed = False
    format3.os = Os()
elif point == "in-probe":
    marker = pathlib.Path(cfg["marker"])
    def watch():
        while not marker.exists():
            time.sleep(0.02)
        time.sleep(0.2)
        import subprocess
        ps = subprocess.run(["ps", "-axo", "pid=,pgid=,command="], capture_output=True, text=True, encoding="utf-8").stdout
        pathlib.Path(cfg["ps_before"]).write_text("\n".join(ln for ln in ps.splitlines() if cfg["out"] in ln))
        die()
    threading.Thread(target=watch, daemon=True).start()
elif point == "together":
    while not pathlib.Path(cfg["go"]).exists():
        time.sleep(0.005)
project = bundle.load(json.loads(pathlib.Path(cfg["bundle"]).read_text()))
s = settings.load(json.loads(pathlib.Path(cfg["settings"]).read_text()))
parent = pathlib.Path(cfg["parent"]) if cfg.get("parent") else None
R.execute(project, s, pathlib.Path(cfg["source"]), pathlib.Path(cfg["out"]), transport=provider(),
          client_exe=cfg["client"], cals=R.calibrations(), predecessor=parent, accept_unaccounted=cfg.get("accept", False))
'''


@unittest.skipUnless(os.name == "posix", "the fake client is a script started by its shebang; the kill is SIGKILL")
class LineageBase(ProductBase):
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
        self.settings = S.load(self.settings_doc)
        self.drivers = 0

    def execute(self, out: str = "out", **kw) -> dict:
        from tests.v2.test_app_run import provider
        kw.setdefault("transport", provider())
        return R.execute(self.project, self.settings, kw.pop("source", self.tmp / "source"), self.tmp / out,
                         client_exe=str(self.client), cals=R.calibrations(), **kw)

    def mul(self, text: str) -> None:
        (self.client.parent / "mul.py").write_text(text)

    def arm(self, title: str = "(disarmed)", when: str = "", driver: int = 1) -> None:
        (self.client.parent / "kill.json").write_text(json.dumps({"title": title, "when": when,
                                                                  "pid_file": str(self.tmp / f"driver-{driver}" / "pid")}))

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
        p = subprocess.Popen([sys.executable, str(d / "driver.py"), str(d / "cfg.json")], cwd=str(ROOT),
                             env={**os.environ, "PYTHONPATH": str(ROOT)}, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, encoding="utf-8")
        if not wait:
            return p
        p.communicate(timeout=600)
        return p.returncode

    def killed(self, point: str | None, **kw) -> pathlib.Path:
        self.assertEqual(self.drive("first", self.doc, point=point, **kw), -signal.SIGKILL, point)
        first = self.tmp / "first"
        self.assertFalse((first / "RUN.json").exists())      # killed: no record
        self.assertTrue((first / R.STARTED).exists())
        return first

    def journal(self, out: str):
        return format3.reconstruct((self.tmp / out / "run" / "journals" / "aisef-run.jsonl").read_text(encoding="utf-8")).events

    def continue_and_finish(self, first: str, out: str = "second", **kw) -> tuple[dict, dict, dict]:
        self.mul(MUL)
        self.arm()
        doc, report = bundle_cli.continue_from(self.doc, self.tmp / first,
                                               leave_out_unidentified=kw.pop("leave_out_unidentified", False))
        self.project = bundle.load(doc)
        rec = self.execute(out, source=self.tmp / first / "repo", predecessor=self.tmp / first, **kw)
        return doc, report, rec

    def assert_one_lineage(self, runs: list[str], rec: dict, delivered: tuple[str, ...] = ("S1", "S2")) -> None:
        commits = [e.data["story_id"] for out in runs if (self.tmp / out / "run").exists()
                   for e in self.journal(out) if e.type == "story/commit"]
        self.assertEqual(sorted(s for s in commits if s in ("S1", "S2")), sorted(delivered))     # each once
        merges = git(self.tmp / runs[-1] / "repo", "log", "--merges", "--format=%s", "main").splitlines()
        self.assertEqual(len(merges), len(delivered), merges)                                   # once each
        self.assertEqual((rec["delivery_verdict"], rec["productproof"]["delivered"], rec["productproof"]["total"]),
                         ("PASS", 2, 2))
        streams = {k: 0 for k in usage.CLASSES}
        for out in runs:
            sessions = self.tmp / out / "sessions"
            for log in sessions.glob("*.jsonl") if sessions.is_dir() else ():
                for k, v in usage.session_tokens(log)["tokens"].items():
                    streams[k] += v
        self.assertEqual(rec["lineage_usage"]["tokens"], streams)                               # every stream once
        own = self.tmp / runs[-1] / "sessions"
        self.assertEqual(rec["usage"]["tokens"], {k: sum(usage.session_tokens(p)["tokens"][k] for p in own.glob("*.jsonl"))
                                                  for k in usage.CLASSES})


class ProviderRequestWindows(LineageBase):
    def test_journaled_but_the_client_never_started_nothing_was_sent(self):
        first = self.killed("request-before-start")
        events = self.journal("first")
        self.assertEqual(sum(1 for e in events if e.type == "provider/request" and e.data["story_id"] == "S2"), 1)
        self.assertEqual(list((first / "sessions").glob("S2.*")), [])                # no stream: never started
        self.assertEqual(lineage.account_of(first)["unaccounted"], [])
        _, report, rec = self.continue_and_finish("first")
        self.assertEqual(report["unaccounted"], [])
        self.assertNotIn("accepted_unaccounted", rec["continues"])
        self.assert_one_lineage(["first", "second"], rec)

    def assert_unknown_spend_blocks_until_accepted(self, when: str) -> None:
        self.arm("developer S2", when)
        first = self.killed(None)
        unknown = lineage.account_of(first)["unaccounted"]
        self.assertTrue(any("in flight when the run ended" in u for u in unknown), unknown)
        with self.assertRaises(R.RunRefused) as c:              # no paid work starts on unknown spend
            self.continue_and_finish("first")
        self.assertIn("--accept-unaccounted", str(c.exception))
        refused = json.loads((self.tmp / "second" / "RUN.json").read_text())
        self.assertEqual((refused["failure"]["stage"], refused.get("preflight")), ("claim", None))  # nothing sent
        self.assertFalse((self.tmp / "second" / "preflight").exists())
        _, _, rec = self.continue_and_finish("first", "third", accept_unaccounted=True)
        self.assertEqual(rec["continues"]["accepted_unaccounted"], unknown)          # the operator's acceptance, recorded
        self.assertEqual(rec["continues"]["claim"]["supersedes"]["child_state"], lineage.ENDED_UNBEGUN)
        self.assertIsNone(rec["lineage_usage"]["cost"]["value"])                      # unknown, never 0
        self.assert_one_lineage(["first", "second", "third"], rec)

    def test_the_request_sent_before_any_usage_is_reported(self):
        self.assert_unknown_spend_blocks_until_accepted("before-step")

    def test_its_usage_reported_its_result_never_journaled(self):
        self.assert_unknown_spend_blocks_until_accepted("after-step")


class CommitWindows(LineageBase):
    def test_the_developers_candidate_committed_nothing_journaled(self):
        first = self.killed("commit-before-event")
        _, report = bundle_cli.continue_from(self.doc, first)
        candidate = [i for i in report["unconfirmed"] if i["operation"] == "candidate"]
        self.assertEqual([(i["story"], i["identified"]) for i in candidate], [("S2", True)])
        self.assertIn("wt-S2", candidate[0]["why"])
        _, _, rec = self.continue_and_finish("first", accept_unaccounted=True)      # its session's end unknown
        self.assertNotIn(candidate[0]["commit"], git(self.tmp / "second" / "repo", "rev-list", "main").splitlines())
        self.assert_one_lineage(["first", "second"], rec)

    def test_the_merge_moved_main_the_journal_never_committed_it(self):
        first = self.killed("merge-before-event")
        s1 = next(e.data["revision"] for e in self.journal("first") if e.type == "story/commit")
        moved = git(first / "repo", "rev-parse", "main")
        self.assertNotEqual(moved, s1)
        _, report = bundle_cli.continue_from(self.doc, first)
        self.assertEqual([(i["operation"], i["story"], i["commit"], i["identified"]) for i in report["unconfirmed"]],
                         [("merge", "S2", moved, True)])
        _, _, rec = self.continue_and_finish("first")
        self.assertNotIn(moved, git(self.tmp / "second" / "repo", "rev-list", "main").splitlines())
        self.assert_one_lineage(["first", "second"], rec)

    def test_a_commit_on_main_nothing_identifies_is_refused_unless_left_out_by_name(self):
        first = self.killed("after-commit")
        (first / "repo" / "stray.txt").write_text("not the kernel's\n")
        git(first / "repo", "add", "-A")
        git(first / "repo", "commit", "-q", "-m", "someone else")
        with self.assertRaises(bundle.BundleError) as c:
            bundle_cli.continue_from(self.doc, first)
        self.assertIn("nothing identifies", str(c.exception))
        _, report, rec = self.continue_and_finish("first", leave_out_unidentified=True)
        self.assertTrue(report["left_out_unidentified"])
        self.assert_one_lineage(["first", "second"], rec)


class JournalAppendWindows(LineageBase):
    def outcome(self, point: str) -> tuple[dict, object]:
        first = self.killed(point)
        got = format3.reconstruct((first / "run" / "journals" / "aisef-run.jsonl").read_text(encoding="utf-8"))
        _, report = bundle_cli.continue_from(self.doc, first)
        return report, got

    def test_before_the_write_the_event_is_absent_and_its_merge_reconciled(self):
        report, got = self.outcome("journal-before-write")
        self.assertFalse(got.torn_tail)
        self.assertEqual((report["carried"], [i["operation"] for i in report["unconfirmed"]]), (["S1"], ["merge"]))

    def test_a_short_write_is_a_torn_tail_whose_effect_is_still_reconciled(self):
        report, got = self.outcome("journal-short-write")
        self.assertTrue(got.torn_tail)
        cut = report["cut_event"]
        self.assertTrue(report["torn_tail"])
        self.assertEqual(cut["seq"], len(got.events))
        self.assertGreater(cut["bytes"], 0)
        # measured: the first half of a canonical event holds its chain and part of its data — not its type (the last
        # field), here not even its story: the record is unreadable, so only git can say what the event's effect was
        self.assertEqual((cut["type"], cut["stories"]), (None, []))
        self.assertEqual(report["carried"], ["S1"])                                    # the cut commit: not confirmed
        self.assertEqual([(i["operation"], i["story"]) for i in report["unconfirmed"]], [("merge", "S2")])  # its effect
        _, _, rec = self.continue_and_finish("first")
        self.assert_one_lineage(["first", "second"], rec)

    def test_after_the_write_before_the_fsync_a_killed_process_keeps_the_event(self):
        report, got = self.outcome("journal-after-write")
        self.assertFalse(got.torn_tail)
        self.assertEqual((report["carried"], report["unconfirmed"]), (["S1", "S2"], []))

    def test_after_the_fsync_the_event_is_kept(self):
        report, got = self.outcome("journal-after-fsync")
        self.assertEqual((report["carried"], report["unconfirmed"]), (["S1", "S2"], []))

    def test_a_corrupt_line_before_the_end_is_refused(self):
        first = self.killed("after-commit")
        copy = self.tmp / "copy"
        shutil.copytree(first, copy, symlinks=True)
        journal = copy / "run" / "journals" / "aisef-run.jsonl"
        data = bytearray(journal.read_bytes())
        data[bytes(data).index(b'"story/commit"') + 2] ^= 0x20
        journal.write_bytes(bytes(data))
        with self.assertRaises(bundle.BundleError) as c:
            bundle_cli.continue_from(self.doc, copy)
        self.assertIn("does not reconstruct", str(c.exception))


class ClaimLifecycle(LineageBase):
    def setUp(self) -> None:
        super().setUp()
        self.first = self.killed("after-commit")
        self.cont, _ = bundle_cli.continue_from(self.doc, self.first)

    def claim_file(self, n: int = 1) -> pathlib.Path:
        return self.first / (R.CLAIM if n == 1 else f"CONTINUED-BY.{n}.json")

    def test_the_claimant_killed_before_the_child_began_is_superseded_by_evidence(self):
        self.assertEqual(self.drive("dead", self.cont, point="claim-before-begin", parent=self.first,
                                    source=self.first / "repo"), -signal.SIGKILL)
        self.assertEqual(lineage.child_state(self.tmp / "dead"), lineage.UNBEGUN)
        claim1 = self.claim_file().read_bytes()
        _, _, rec = self.continue_and_finish("first")
        sup = rec["continues"]["claim"]["supersedes"]
        self.assertEqual((sup["claim"], sup["child_state"], sup["claimant_gone"], sup["operator_asserted"]),
                         (R.CLAIM, lineage.UNBEGUN, True, False))
        self.assertEqual(self.claim_file().read_bytes(), claim1)                        # kept, never deleted
        self.assertEqual(json.loads(self.claim_file(2).read_text())["run"], str(self.tmp / "second"))
        self.assert_one_lineage(["first", "dead", "second"], rec)

    def test_a_child_that_began_is_never_superseded_the_lineage_continues_from_it(self):
        self.assertEqual(self.drive("begun", self.cont, point="begun", parent=self.first, source=self.first / "repo"),
                         -signal.SIGKILL)
        self.assertEqual(lineage.child_state(self.tmp / "begun"), lineage.BEGUN)
        with self.assertRaises(bundle.BundleError) as c:
            bundle_cli.continue_from(self.doc, self.first)
        self.assertIn("which began", str(c.exception))
        self.project = bundle.load(self.cont)
        with self.assertRaises(R.RunRefused) as c:
            self.execute("second", source=self.first / "repo", predecessor=self.first)
        self.assertIn("which began: continue the lineage from it", str(c.exception))
        sha = hashlib.sha256(self.claim_file().read_bytes()).hexdigest()
        with self.assertRaises(R.RunRefused):                                            # not even by assertion
            self.execute("third", source=self.first / "repo", predecessor=self.first, supersede_claim=sha)
        self.assertEqual(lineage.claims(self.first), [(1, self.claim_file())])           # no claim was added
        rec = self.execute("fourth", source=self.tmp / "begun" / "repo", predecessor=self.tmp / "begun")
        self.assertEqual(rec["story_outcomes"], {"CARRIED": ["COMMIT"], "S2": ["COMMIT"]})
        self.assertEqual([(pathlib.Path(r["run"]).name, r["superseded"]) for r in rec["lineage_usage"]["runs"]],
                         [("begun", False), ("first", False), ("this run", False)])      # the refused ones spent nothing

    def fabricate(self, child: pathlib.Path, who: dict) -> pathlib.Path:
        """A claim as a claimant would have written it (a fixture: the cases no driver can produce here)."""
        p = self.claim_file()
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps({"run": str(child), "claimed": 1.0, "claimant": who}) + "\n")
        return p

    def test_a_missing_child_whose_claimant_is_gone_is_superseded(self):
        gone = int(subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"], capture_output=True, text=True,
                                  encoding="utf-8").stdout.strip())
        self.fabricate(self.tmp / "never-made", {"host": socket.gethostname(), "pid": gone, "started": "Thu Jan  1 00:00:00 1970"})
        _, _, rec = self.continue_and_finish("first")
        sup = rec["continues"]["claim"]["supersedes"]
        self.assertEqual((sup["child_state"], sup["claimant_gone"], sup["operator_asserted"]), (lineage.UNBEGUN, True, False))

    def test_a_claimant_alive_or_elsewhere_is_superseded_only_by_the_operator_naming_the_claim(self):
        for who, name in ((lineage.claimant(), "alive"), ({"host": "another-host", "pid": 1, "started": "x"}, "elsewhere")):
            with self.subTest(name):
                fresh = self.tmp / f"case-{name}"
                shutil.copytree(self.first, fresh, symlinks=True)
                keep, self.first = self.first, fresh
                p = self.fabricate(self.tmp / f"pending-{name}", who)
                with self.assertRaises(R.RunRefused) as c:
                    self.continue_and_finish(fresh.name, f"refused-{name}")
                self.assertIn("not superseded without evidence", str(c.exception))
                sha = hashlib.sha256(p.read_bytes()).hexdigest()
                _, _, rec = self.continue_and_finish(fresh.name, f"asserted-{name}", supersede_claim=sha)
                sup = rec["continues"]["claim"]["supersedes"]
                self.assertEqual((sup["sha256"], sup["operator_asserted"]), (sha, True))
                self.first = keep

    def test_a_finished_continuation_asked_for_again_is_refused_pointing_at_it(self):
        self.continue_and_finish("first")
        with self.assertRaises(bundle.BundleError) as c:
            bundle_cli.continue_from(self.doc, self.first)
        self.assertIn(f"continued by {self.tmp / 'second'}, which began", str(c.exception))
        with self.assertRaises(R.RunRefused) as c:
            self.execute("again", source=self.first / "repo", predecessor=self.first)
        self.assertIn(f"continued by {self.tmp / 'second'}, which began", str(c.exception))

    def test_two_runs_at_once_one_claims_and_the_other_spends_nothing(self):
        go = self.tmp / "go"
        procs = {n: self.drive(n, self.cont, point="together", parent=self.first, source=self.first / "repo", wait=False,
                               go=str(go)) for n in ("a", "b")}
        time.sleep(1.5)
        go.write_text("go")
        recs = {}
        for n, p in procs.items():
            p.communicate(timeout=600)
            recs[n] = json.loads((self.tmp / n / "RUN.json").read_text(encoding="utf-8"))
        refused = [n for n, r in recs.items() if (r.get("failure") or {}).get("type") == "RunRefused"]
        self.assertEqual(len(refused), 1, {n: r.get("failure") for n, r in recs.items()})
        loser, winner = refused[0], ("b" if refused[0] == "a" else "a")
        self.assertIn("a run is continued once", recs[loser]["failure"]["detail"])
        self.assertEqual(recs[loser]["failure"]["stage"], "claim")
        self.assertFalse((self.tmp / loser / "preflight").exists())        # it sent no provider request
        self.assertEqual(json.loads(self.claim_file().read_text())["run"], str(self.tmp / winner))
        self.assertEqual(recs[winner]["story_outcomes"], {"CARRIED": ["COMMIT"], "S2": ["COMMIT"]})

    def test_the_predecessors_evidence_stays_byte_identical_but_the_claim(self):
        def files():
            return {p.relative_to(self.first).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in self.first.rglob("*") if p.is_file() and p.relative_to(self.first).parts[0] != "repo"}
        before = files()
        self.continue_and_finish("first")
        after = files()
        self.assertEqual(set(after) - set(before), {R.CLAIM})
        self.assertEqual({k: after[k] for k in before}, before)


class ProcessesOfAKilledRun(LineageBase):
    def kill_in_probe(self, detach: bool) -> tuple[list[str], pathlib.Path]:
        marker = self.tmp / "in-mul"
        self.mul(MUL_SLOW.format(marker=str(marker), detach=detach))
        before = self.tmp / "ps-before.txt"
        self.killed("in-probe", marker=str(marker), ps_before=str(before))
        return before.read_text().splitlines(), marker

    @staticmethod
    def alive(pid: int) -> bool:
        return subprocess.run(["ps", "-o", "pid=", "-p", str(pid)], capture_output=True, text=True,
                              encoding="utf-8").stdout.strip() == str(pid)

    @staticmethod
    def groups_alive(groups: set[int]) -> set[int]:
        listed = subprocess.run(["ps", "-axo", "pgid="], capture_output=True, text=True, encoding="utf-8").stdout.split()
        return {g for g in groups if str(g) in listed}

    def test_the_probe_processes_are_identified_and_die_with_the_run(self):
        rows, marker = self.kill_in_probe(detach=False)
        groups = {int(r.split()[1]) for r in rows if "pycache_prefix" in r}
        self.assertTrue(groups, "no probe process was alive at the kill: the measurement would be vacuous")
        subject = int(marker.read_text())                       # the candidate's own process, by its own pid
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and (self.alive(subject) or self.groups_alive(groups)):
            time.sleep(0.2)
        self.assertFalse(self.alive(subject))
        self.assertEqual(self.groups_alive(groups), set())
        print(f"\n[in-probe kill] {len(rows)} process(es) of the run in {len(groups)} probe group(s) at the kill; the "
              f"candidate's pid {subject} and every such group gone after it", file=sys.stderr)

    def test_a_descendant_that_left_its_group_is_not_controlled(self):
        rows, marker = self.kill_in_probe(detach=True)
        detached = int(pathlib.Path(str(marker) + ".detached").read_text())
        time.sleep(1.0)
        self.assertTrue(self.alive(detached), "the detached descendant was expected to outlive the run (measured)")
        print(f"\n[in-probe kill] a descendant that called setsid (pid {detached}) outlived the killed run: AISEF does "
              "not control it here (without confinement)", file=sys.stderr)
        deadline = time.monotonic() + 30
        while self.alive(detached) and time.monotonic() < deadline:     # it ends by itself (an 8 s sleep)
            time.sleep(0.5)


@unittest.skipUnless(os.name == "posix", "the fake client is a script started by its shebang")
class AnchorThreatModel(ProductBase):
    """docs/v2.1/ANCHOR-THREAT-MODEL.md, measured."""

    def setUp(self) -> None:
        super().setUp()
        self.rec = self.execute()
        self.out = self.tmp / "out"
        self.store = self.tmp / "operator-only"
        self.store.mkdir()
        lineage.write_anchor(self.store / "out.anchor", R.anchor_in(self.out))

    def forge(self) -> str:
        log = next((self.out / "sessions").glob("S1.developer.*.jsonl"))
        log.write_text(log.read_text().replace('"done"', '"done (rewritten)"'))
        manifest = R.evidence_manifest(self.out)
        (self.out / R.MANIFEST).write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
        return R.anchor_of(manifest)

    def test_the_limit_an_attacker_who_can_write_the_store_too_is_not_detected(self):
        forged = self.forge()
        (self.store / "out.anchor").chmod(0o644)
        (self.store / "out.anchor").write_text(forged + "\n")          # the same permissions: the store rewritten too
        v = verify(self.project, self.out, expect_anchor=lineage.read_anchor(self.store / "out.anchor"))
        self.assertEqual(v["verdict"], "VERIFIED")                      # the anchor's source is the trust, not AISEF

    def test_an_attacker_who_cannot_write_the_store_is_refuted(self):
        self.forge()
        v = verify(self.project, self.out, expect_anchor=lineage.read_anchor(self.store / "out.anchor"))
        self.assertEqual(v["verdict"], "REFUTED")

    def test_the_anchor_file_is_new_exact_and_never_through_a_link(self):
        anchor = R.anchor_in(self.out)
        self.assertEqual(oct((self.store / "out.anchor").stat().st_mode & 0o777), "0o444")
        with self.assertRaises(FileExistsError):
            lineage.write_anchor(self.store / "out.anchor", anchor)                  # an existing path
        os.symlink(self.tmp / "elsewhere", self.store / "link.anchor")
        with self.assertRaises(FileExistsError):                                     # a link, even dangling
            lineage.write_anchor(self.store / "link.anchor", anchor)
        self.assertFalse((self.tmp / "elsewhere").exists())
        locked = self.tmp / "locked"
        locked.mkdir()
        locked.chmod(0o555)
        self.addCleanup(locked.chmod, 0o755)
        with self.assertRaises(PermissionError):                                     # a write that fails
            lineage.write_anchor(locked / "a.anchor", anchor)
        for n, partial in enumerate((anchor[:30], anchor, anchor + "\nextra\n", "z" * 64 + "\n")):   # cut or foreign
            p = self.store / f"partial-{n}"
            p.write_text(partial)
            with self.assertRaises(ValueError):
                lineage.read_anchor(p)
        self.assertEqual(lineage.read_anchor(self.store / "out.anchor"), anchor)

    def test_the_cli_refuses_anchor_paths_it_would_not_write_and_a_malformed_expected_anchor(self):
        from aisef2.app import cli
        common = ["--project", str(self.tmp / "bundle.json"), "--out", str(self.tmp / "x")]
        os.symlink(self.tmp / "nowhere", self.store / "dangling")
        for argv in (["--settings", "s", "--repo", "r", *common, "--anchor-out", str(self.store / "out.anchor")],
                     ["--settings", "s", "--repo", "r", *common, "--anchor-out", str(self.store / "dangling")],
                     ["--verify", *common, "--anchor-out", str(self.store / "new.anchor")],
                     ["--verify", *common, "--expect-anchor", "not-an-anchor"]):
            with self.subTest(argv[-1]), self.assertRaises(SystemExit) as c:
                cli.run(argv)
            self.assertEqual(c.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
