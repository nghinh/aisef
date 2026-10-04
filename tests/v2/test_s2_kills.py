"""V2.0-S2 mutation: cases that kill survivors of the current-snapshot campaign. A file of its own, named only in the kill
sets of the targets it was written for (validation/v2/mutation.py), so adding to it re-measures those targets alone —
every other result's kill-test closure stays byte-identical (validation/qualification/s2_mutation_record.py)."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import select
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from aisef2.app import bundle  # noqa: E402
from aisef2.app import run as R  # noqa: E402
from aisef2.arch.enums import BehaviorVerdict, Enforcement, SubjectAbsence  # noqa: E402
from aisef2.orchestrate import workspace as w  # noqa: E402
from aisef2.probe import cli_invocation as ci  # noqa: E402
from aisef2.probe import process_effect as pe  # noqa: E402
from aisef2.probe import python_callable_v2 as pc2  # noqa: E402
from aisef2.probe.protocol import ExecutionEnv, Observation, ObservationKind, RevisionRef  # noqa: E402
from aisef2.product.spec import ProductProofSpec  # noqa: E402


class AgentInvoke(unittest.TestCase):
    """cli_invocation's shipped AGENT, op invoke of a module as `python -m` runs it."""

    def test_a_module_run_as_main_sees_itself_as_main_and_its_own_file_as_argv0(self):
        """AGENT/op_invoke L129 (`alter_sys=True`): the subject's sys.argv[0] is its file and sys.modules['__main__'] is
        the subject itself, as under `python -m`."""
        with tempfile.TemporaryDirectory() as t:
            t = pathlib.Path(os.path.realpath(t))
            root, work = t / "rev", t / "work"
            (root / "mainsubj").mkdir(parents=True)
            work.mkdir()
            (root / "mainsubj" / "__init__.py").write_text("", encoding="utf-8")
            mod = root / "mainsubj" / "cli.py"
            mod.write_text("import sys\nMARK = object()\nprint(sys.argv[0])\nprint(sys.argv[1:])\n"
                           "print(sys.modules['__main__'].__dict__.get('MARK') is MARK)\n", encoding="utf-8")
            with open(work / "agent.log", "wb") as log:
                agent = subprocess.Popen([sys.executable, "-I", "-B", "-X", "utf8=1", "-c", ci.AGENT, str(root), str(work)],
                                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, cwd=work)
            try:
                self.assertEqual(json.loads(agent.stdout.readline()), {"ready": True, "n": 0})
                req = {"op": "invoke", "n": 1, "stdin": os.devnull, "out": str(work / "o.bin"), "err": str(work / "e.bin"),
                       "name": "mainsubj.cli", "attr": "__main__", "argv": ["x", "y"]}
                agent.stdin.write((json.dumps(req) + "\n").encode("utf-8"))
                agent.stdin.flush()
                self.assertEqual(json.loads(agent.stdout.readline()), {"raw": None, "code": 0, "raised": None, "n": 1})
            finally:
                agent.stdin.close()
                agent.wait(30)
                agent.stdout.close()
            self.assertEqual((work / "o.bin").read_bytes().decode("utf-8").splitlines(), [str(mod), "['x', 'y']", "True"])
            self.assertEqual((work / "e.bin").read_bytes(), b"")


class ProcessEffectAsk(unittest.TestCase):
    """process_effect HARNESS/ask: two of its mutants were killed only by the clock (L47 the request line's newline,
    L51 the answer ask returns) — each leaves the harness waiting. One bounded observation, its whole outcome asserted,
    fails them by assertion inside its own window. First in that target's kill set, before the files that would hang."""

    def test_one_asked_call_is_answered_and_observed(self):
        with tempfile.TemporaryDirectory(prefix="aisef2-s2-kills-") as t:
            root = pathlib.Path(os.path.realpath(t))
            (root / "subj.py").write_text("def total(*values):\n    return sum(values)\n", encoding="utf-8")
            probe = pe.ProcessEffectProbe()
            spec = ProductProofSpec.create(
                contract_id="BC-EFFECT", probe_id=probe.id, probe_digest=probe.digest,
                probe_input={"subject": {"kind": "process_effect", "locator": "subj:total"},
                             "stimulus": {"scenario": [{"step": "call", "args": [1, 2], "kwargs": {}}]},
                             "observable": {"returns": 3, "within_s": 5},
                             "subject_absence": SubjectAbsence.REQUIRES_SUBJECT.value},
                candidate_expectation=BehaviorVerdict.SATISFIED, compiler_id="test", compiler_digest="c" * 64)
            o = probe.observe(spec, RevisionRef("89abcdef0123456789abcdef0123456789abcdef", str(root)),
                              ExecutionEnv(sys.executable, 10, Enforcement.PARTIAL))
            self.assertEqual((o.kind, o.verdict), (ObservationKind.OBSERVED, BehaviorVerdict.SATISFIED), o.detail)


class CallableWatch(unittest.TestCase):
    """python_callable_v2._watch L504: after DISPATCHED the RESULT wait timed out, nothing of the range is left and its
    exit status was never reported — the controller's own statement is HARNESS_FAILED, with that detail. Not reachable
    end to end (a range that empties reports its status); pinned here."""

    def test_a_range_gone_without_an_exit_status_is_a_harness_failure(self):
        class Gone:
            ledger: list = []

            def members(self):
                return []

            def wait(self, timeout):
                return None
        with mock.patch.object(ci, "_await", side_effect=[("LINE", {"DISPATCHED": [""]}), ("TIMEOUT", {})]):
            o = pc2._watch(Gone(), "proto", "nonce", "key", "returns", {"returns": 1, "within_s": 5},
                           ExecutionEnv(sys.executable, 10, Enforcement.PARTIAL), "/ws")
        self.assertEqual((o.kind, o.verdict, o.detail),
                         (ObservationKind.HARNESS_FAILED, None, "the harness process ended and its exit status was never reported"))


class CallableConcluded(unittest.TestCase):
    """python_callable_v2._concluded L532: an answer on the subject's channel the agent did not write refutes, whatever
    else the facts say — a satisfying return value beside it included. (Today's controller builds tampered facts
    fresh, without one; the precedence is the defence, pinned here.)"""

    def test_tampering_refutes_even_beside_a_satisfying_value(self):
        facts = {"subject": "present", "tampered": "an answer on the subject's channel is not the agent's",
                 "resolved": True, "returned": 3}
        self.assertEqual(pc2._concluded("returns", {"returns": 3, "within_s": 5}, facts),
                         Observation(ObservationKind.OBSERVED, BehaviorVerdict.REFUTED, detail=json.dumps(facts)))


class CallableHarnessArgv(unittest.TestCase):
    """python_callable_v2._harness_argv L401: the harness runs under the fresh bytecode-cache prefix, so it never reads
    bytecode a subject could have planted in a shared cache (P7-FINDING-001). Without the key, `-X <path>` is an option
    Python accepts silently and ignores."""

    def test_the_harness_command_line_names_the_fresh_cache_prefix(self):
        self.assertEqual(pc2._harness_argv("/py", "/w/ask.json", "/w/pyc"),
                         ["/py", "-I", "-B", "-X", "pycache_prefix=/w/pyc", "-c", pc2.HARNESS, "/w/ask.json"])


class WorkspaceConfigListing(unittest.TestCase):
    """workspace.config_problems L58: where git cannot list a configuration at all (here, a directory that does not
    exist), the answer is the empty list of keys — a list, as everywhere else, never None."""

    def test_no_listing_is_an_empty_list_of_keys(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(w.config_problems(pathlib.Path(t) / "absent"), [])


class AgentPlain(unittest.TestCase):
    """cli_invocation AGENT/plain L45-L46: an invoke result json cannot carry comes back as its repr — a set (TypeError)
    and a circular list (ValueError) alike — never an agent failure, never None."""

    def test_unserializable_results_come_back_as_their_repr(self):
        with tempfile.TemporaryDirectory() as t:
            t = pathlib.Path(os.path.realpath(t))
            root, work = t / "rev", t / "work"
            (root / "plainsubj").mkdir(parents=True)
            work.mkdir()
            (root / "plainsubj" / "__init__.py").write_text("", encoding="utf-8")
            (root / "plainsubj" / "cli.py").write_text("def as_set(argv):\n    return {1}\n"
                                                       "def circular(argv):\n    x = []\n    x.append(x)\n    return x\n",
                                                       encoding="utf-8")
            with open(work / "agent.log", "wb") as log:
                agent = subprocess.Popen([sys.executable, "-I", "-B", "-X", "utf8=1", "-c", ci.AGENT, str(root), str(work)],
                                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, cwd=work)
            try:
                self.assertEqual(json.loads(agent.stdout.readline()), {"ready": True, "n": 0})
                for n, (attr, raw) in enumerate((("as_set", "{1}"), ("circular", "[[...]]")), 1):
                    req = {"op": "invoke", "n": n, "stdin": os.devnull, "out": str(work / f"o{n}.bin"),
                           "err": str(work / f"e{n}.bin"), "name": "plainsubj.cli", "attr": attr, "argv": []}
                    agent.stdin.write((json.dumps(req) + "\n").encode("utf-8"))
                    agent.stdin.flush()
                    self.assertEqual(json.loads(agent.stdout.readline()), {"raw": raw, "code": 1, "raised": None, "n": n})
            finally:
                agent.stdin.close()
                agent.wait(30)
                agent.stdout.close()


class AgentGuarded(unittest.TestCase):
    """cli_invocation AGENT/guarded L88: a controlled fault raises with the message 'controlled fault <id>', which the
    caller sees through the exception's attributes."""

    def test_the_controlled_fault_names_itself_in_its_message(self):
        with tempfile.TemporaryDirectory() as t:
            t = pathlib.Path(os.path.realpath(t))
            root, work = t / "rev", t / "work"
            root.mkdir()
            work.mkdir()
            (root / "guardsubj.py").write_text("import os\ndef cwd():\n    return os.getcwd()\n", encoding="utf-8")
            with open(work / "agent.log", "wb") as log:
                agent = subprocess.Popen([sys.executable, "-I", "-B", "-X", "utf8=1", "-c", ci.AGENT, str(root), str(work)],
                                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, cwd=work)
            try:
                self.assertEqual(json.loads(agent.stdout.readline()), {"ready": True, "n": 0})
                ops = ({"op": "import", "name": "guardsubj"}, {"op": "resolve", "chain": ["cwd"]},
                       {"op": "call", "args": [], "kwargs": {}, "patch": ["os", "getcwd", "OSError", "F1"], "attrs": ["args"]})
                answers = []
                for n, op in enumerate(ops, 1):
                    agent.stdin.write((json.dumps({**op, "n": n}) + "\n").encode("utf-8"))
                    agent.stdin.flush()
                    answers.append(json.loads(agent.stdout.readline()))
                self.assertEqual(answers[2], {"raised": "OSError", "attrs": {"args": {"json": ["controlled fault F1"]}},
                                              "fired": True, "n": 3})
            finally:
                agent.stdin.close()
                agent.wait(30)
                agent.stdout.close()


class AppRun(unittest.TestCase):
    """aisef2.app.run: admit L87 (each failed admission check names its problems, which the refusal shows) and
    check_git L100 (a `git --version` that times out is refused, never raised)."""

    def test_a_failed_admission_check_carries_its_problems(self):
        from tests.v2 import test_app_run as e2e
        failed = R.admit(bundle.load(e2e.project_bundle("a" * 40)), ())["failed"]
        self.assertEqual([sorted(f) for f in failed], [["check", "problems"]])
        self.assertEqual(failed[0]["check"], "9. probe_calibration")
        self.assertTrue(failed[0]["problems"] and all("no ProbeCapabilityCalibration" in x for x in failed[0]["problems"]),
                        failed[0]["problems"])

    def test_a_git_that_hangs_is_refused(self):
        with mock.patch.object(R.subprocess, "run", side_effect=subprocess.TimeoutExpired(["git", "--version"], 60)), \
                self.assertRaises(R.RunRefused) as c:
            R.check_git()
        self.assertEqual(str(c.exception), "git 2.31 or newer is required (B4): found unavailable: TimeoutExpired")


@unittest.skipUnless(os.name == "posix", "select on a pipe is POSIX")
class AgentSend(unittest.TestCase):
    """cli_invocation AGENT/send L27: every answer is one newline-terminated line — without the newline a reader waiting
    for a line waits for ever (that mutant was killed only by the clock). Read with a bound, asserted, first in the
    target's kill set."""

    def test_the_ready_answer_is_one_whole_line(self):
        with tempfile.TemporaryDirectory() as t:
            t = pathlib.Path(os.path.realpath(t))
            with open(t / "agent.log", "wb") as log:
                agent = subprocess.Popen([sys.executable, "-I", "-B", "-X", "utf8=1", "-c", ci.AGENT, str(t), str(t)],
                                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, cwd=t)
            try:
                ready, _, _ = select.select([agent.stdout], [], [], 30)
                self.assertTrue(ready, "the agent sent nothing in 30 s")
                self.assertEqual(os.read(agent.stdout.fileno(), 4096), b'{"ready": true, "n": 0}\n')
            finally:
                agent.stdin.close()
                agent.wait(30)
                agent.stdout.close()


class AppRepositoryAndInterpreter(unittest.TestCase):
    """aisef2.app.run: check_repository L109/L113 (the baseline must be a commit; the refusal names the document) and
    probe_interpreter L119/L120 (B6: the venv is made isolated (-I), its failure raises with what it said captured, and
    the Windows layout is Scripts/python.exe)."""

    def test_a_baseline_that_is_not_a_commit_is_refused_and_a_wrong_document_is_named(self):
        from tests.v2 import test_app_run as e2e
        with tempfile.TemporaryDirectory() as t:
            repo = pathlib.Path(t) / "repo"
            base = e2e.make_repo(repo)
            tree = subprocess.run(["git", "-C", str(repo), "rev-parse", f"{base}^{{tree}}"], capture_output=True, text=True,
                                  encoding="utf-8", check=True).stdout.strip()
            with self.assertRaises(R.RunRefused) as c:
                R.check_repository(bundle.load(e2e.project_bundle(tree)), repo)
            self.assertEqual(str(c.exception), f"{repo} does not hold the plan's baseline {tree}")
            doc = e2e.project_bundle(base)
            doc["requirements_document"]["path"] = "docs/absent.md"
            with self.assertRaises(R.RunRefused) as c:
                R.check_repository(bundle.load(doc), repo)
            self.assertEqual(str(c.exception), "the requirements document docs/absent.md at the baseline is not the bundle's")

    def test_the_probe_venv_is_made_isolated_from_the_hosts_python_path(self):
        with tempfile.TemporaryDirectory() as t:
            t = pathlib.Path(t)
            (t / "host" / "venv").mkdir(parents=True)
            marker = t / "host-venv-ran"
            (t / "host" / "venv" / "__init__.py").write_text("", encoding="utf-8")
            (t / "host" / "venv" / "__main__.py").write_text(f"open({str(marker)!r}, 'w').close()\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"PYTHONPATH": str(t / "host")}):
                exe = R.probe_interpreter(t / "py")
            self.assertFalse(marker.exists(), "the host's PYTHONPATH reached the venv creation")
            self.assertTrue(pathlib.Path(exe).is_file())

    @unittest.skipUnless(os.name == "posix", "a script interpreter by its shebang")
    def test_a_failing_venv_creation_raises_with_its_output_captured(self):
        with tempfile.TemporaryDirectory() as t:
            t = pathlib.Path(t)
            bad = t / "badpython"
            bad.write_text("#!/bin/sh\necho boom >&2\nexit 3\n", encoding="utf-8")
            bad.chmod(0o755)
            with self.assertRaises(subprocess.CalledProcessError) as c:
                R.probe_interpreter(t / "py", python=str(bad))
            self.assertEqual((c.exception.returncode, c.exception.stderr), (3, b"boom\n"))

    def test_the_windows_layout_is_scripts_python_exe(self):
        with tempfile.TemporaryDirectory() as t:
            where = pathlib.Path(t) / "py"

            def made(argv, **kw):
                (where / "Scripts").mkdir(parents=True)
                (where / "Scripts" / "python.exe").write_bytes(b"")
                return subprocess.CompletedProcess(argv, 0, b"", b"")
            with mock.patch.object(R.subprocess, "run", side_effect=made), mock.patch.object(R.os, "name", "nt"):
                exe = R.probe_interpreter(where)
            self.assertEqual(exe, str(where / "Scripts/python.exe"))


class AppRunSpec(unittest.TestCase):
    """aisef2.app.run.runspec_of L149-L165: the run's specification, whole — every capability with its grade,
    enforcement and tool, and every resolved setting with its value and the layer it came from."""

    def test_the_runspec_names_every_capability_and_every_setting_with_its_layer(self):
        from aisef2.app import adapters as ad
        from aisef2.app import preflight, settings
        from aisef2.probe import catalog
        from aisef2.product.contract import plain
        from tests.v2 import test_app_run as e2e
        with tempfile.TemporaryDirectory() as t:
            p, st = bundle.load(e2e.project_bundle("a" * 40)), settings.load(e2e.SETTINGS)
            pre = preflight.run(e2e.ROUTE, 2, e2e.provider(), pathlib.Path(t) / "pre")
            for scanner, tool, grade in ((ad.NoScanner(), "none", "OPAQUE"), (ad.RuffScanner(sys.executable), "ruff", "VERIFIED")):
                spec = R.runspec_of(p, st, pre, "client-x", sys.executable, scanner)
                caps = {c.name: (c.grade.value, c.enforcement.value) for c in spec.capabilities}
                probes = {e.probe_id: ("VERIFIED", "PARTIAL") for e in catalog.CATALOG if e.active}
                self.assertEqual(caps, {"kernel": ("VERIFIED", "FULL"), "python": ("VERIFIED", "PARTIAL"),
                                        "git": ("VERIFIED", "PARTIAL"), "developer": ("ATTESTED", "PARTIAL"),
                                        "reviewer": ("ATTESTED", "PARTIAL"), "scanner": (grade, "PARTIAL"), **probes})
                self.assertEqual(dict({c.name: c for c in spec.capabilities}["scanner"].tuple_).get("tool"), tool)
                self.assertEqual(plain(spec.settings), {
                    "revision": {"value": "a" * 40, "layer": "run"},
                    "workload": {"value": p.name, "layer": "bundle"}, "bundle_digest": {"value": p.digest, "layer": "bundle"},
                    "plan_hash": {"value": p.plan.plan_hash, "layer": "plan"},
                    "requirements_sha256": {"value": p.requirements_sha256, "layer": "bundle"},
                    "settings_sha256": {"value": hashlib.sha256(json.dumps(st.content, sort_keys=True).encode()).hexdigest(),
                                        "layer": "settings"},
                    "limits": {"value": {k.value: v for k, v in st.limits.items()}, "layer": "settings"},
                    "budget": {"value": plain(st.budget), "layer": "settings"},
                    "max_turns_per_session": {"value": st.max_turns_per_session, "layer": "settings"},
                    "timeouts_s": {"value": plain(st.timeouts_s), "layer": "settings"}})


class AppProductProof(unittest.TestCase):
    """aisef2.app.run.productproof L173-L182: an obligation's row, whole — its last proof (candidate, seq, agreement,
    verdict) and the probe its spec binds."""

    def test_an_obligation_row_is_whole(self):
        from tests.v2 import test_app_run as e2e
        p = bundle.load(e2e.project_bundle("a" * 40))
        spec = next(iter(p.specs.values()))
        expected = spec.candidate_expectation.value
        events = [{"seq": 9, "type": "proof/verified", "data": {"story_id": "S1", "criterion_id": "C-ADD", "candidate": "c1",
                                                                "agreement": True, "verdict": expected}}]
        self.assertEqual(R.productproof(p, events, {"S1"})["obligations"], [{
            "story": "S1", "criterion": "C-ADD", "role": "INTRODUCE", "spec": spec.id, "probe_id": spec.probe_id,
            "expected": expected, "last_proof": {"candidate": "c1", "seq": 9, "agreement": True, "verdict": expected},
            "satisfied_at_last_proof": True, "delivered": True}])


class AppDelivery(unittest.TestCase):
    """aisef2.app.run.delivery L196/L199: a story's last lifecycle event in the journal decides — a retry after its
    commit leaves it uncommitted whatever the results say — and the stories that did not commit are named in order."""

    def test_the_journal_s_last_event_decides_and_the_missing_are_named_in_order(self):
        from tests.v2 import test_app_run as e2e
        p = bundle.load(e2e.project_bundle("a" * 40))
        ev = lambda seq, t, **d: {"seq": seq, "type": t, "data": d}  # noqa: E731
        events = [ev(1, "gate/decision"), ev(2, "story/commit", story_id="S1"), ev(3, "story/retry", story_id="S1")]
        self.assertEqual(R.delivery(p, events, {"S1": ["COMMIT"]}, None, []),
                         ("FAIL", ["1 of the plan's stories did not commit: ['S1']"], set()))
        stories = ["S6", "S2", "S5", "S1", "S4", "S3"]
        six = types.SimpleNamespace(plan=types.SimpleNamespace(obligations=[types.SimpleNamespace(story_id=s) for s in stories]))
        self.assertEqual(R.delivery(six, [ev(1, "gate/decision")], {}, None, []),
                         ("FAIL", ["6 of the plan's stories did not commit: ['S1', 'S2', 'S3', 'S4', 'S5', 'S6']"], set()))


class _Stop(BaseException):
    """Not an Exception: stops a run the way an interruption does."""


@unittest.skipUnless(os.name == "posix", "the fake client is a script started by its shebang")
class AppExecute(unittest.TestCase):
    """aisef2.app.run.execute: the run record, whole (RUN.json's keys, values and bytes; the run's directories; what each
    story is given), every refusal with its message and stage, a refused story that does not stop the run, a story not
    run for the budget, and a failure after a delivered story."""

    def setUp(self):
        from tests.v2 import test_app_run as e2e
        self.e2e = e2e
        self.base = e2e.ProductBase("setUp")   # its fixture: the one-story calc project, the fake client and provider
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.tmp, self.p, self.st = self.base.tmp, self.base.project, self.base.settings

    def run_(self, out, **kw):
        kw.setdefault("transport", self.e2e.provider())
        kw.setdefault("client_exe", str(self.base.client))
        kw.setdefault("cals", self.e2e.calibrations())
        return R.execute(self.p, self.st, self.tmp / "source", out, **kw)

    def record(self, out):
        return json.loads((out / "RUN.json").read_text(encoding="utf-8"))

    def test_the_record_of_a_delivered_run_is_whole(self):
        from aisef2.app import adapters as ad
        from aisef2.orchestrate import story_runner as sr
        from aisef2.orchestrate.quality import TestsPolicy
        self.e2e.client_config(self.tmp, key="config-literal-key-0001")      # the client's own key: not the one used
        seen = {}
        real_rt, real_dev, real_story = R.regression_tests, ad.Developer, sr.run_story

        def rt(repo, project, story, delivered):
            seen["delivered"] = delivered
            return real_rt(repo, project, story, delivered)

        def dev(run, project, logs, kw, timeout):
            seen["secrets"] = kw["secrets"]
            return real_dev(run, project, logs, kw, timeout)

        def story(run, plan, sid, inputs, adapters, policy):
            seen["policy"] = policy
            return real_story(run, plan, sid, inputs, adapters, policy)
        roots, real_ws, real_merger = [], R.GitWorkspace, R.GitMerger

        def workspace(repo, root):
            roots.append(("workspace", pathlib.Path(root)))
            return real_ws(repo, root)

        def merger(repo, branch, root):
            roots.append(("merger", pathlib.Path(root)))
            return real_merger(repo, branch, root)
        out = self.tmp / "deep" / "out"     # its parent does not exist yet
        with mock.patch.dict(os.environ, {"AISEF_TEST_NO_KEY": "env-provider-key-0001"}), \
                mock.patch.object(R, "regression_tests", rt), mock.patch.object(R.ad, "Developer", dev), \
                mock.patch.object(R.sr, "run_story", story), mock.patch.object(R, "GitWorkspace", workspace), \
                mock.patch.object(R, "GitMerger", merger):
            rec = self.run_(out, clock=lambda: 7.0)
        self.assertEqual(roots, [("workspace", out / "work" / "ws"), ("merger", out / "work" / "merge")])
        self.assertEqual((out / "RUN.json").read_text(encoding="utf-8"), json.dumps(rec, indent=1, sort_keys=True, default=str) + "\n")
        self.assertEqual(sorted(rec), sorted([
            "format", "bundle_digest", "project", "plan_hash", "settings", "started", "stage", "kernel_digest", "platform",
            "admission", "preflight", "runspec_hash", "aggregate_min_grade", "scanner", "journal", "finished", "story_outcomes",
            "story_errors", "final_main", "delivery_verdict", "delivery_blocked_by", "plan_quality_verdict",
            "generalization_claim", "productproof", "budget", "budget_stop", "sessions", "failure"]))
        main = subprocess.run(["git", "-C", str(out / "repo"), "rev-parse", "main"], capture_output=True, text=True,
                              encoding="utf-8", check=True).stdout.strip()
        import platform as pf
        self.assertEqual({k: rec[k] for k in ("format", "bundle_digest", "project", "plan_hash", "settings", "started",
                                              "finished", "stage", "kernel_digest", "platform", "story_outcomes",
                                              "story_errors", "final_main", "delivery_verdict", "delivery_blocked_by",
                                              "plan_quality_verdict", "generalization_claim", "budget_stop", "failure")},
                         {"format": R.FORMAT, "bundle_digest": self.p.digest, "project": self.p.name,
                          "plan_hash": self.p.plan.plan_hash, "settings": self.st.content, "started": 7.0, "finished": 7.0,
                          "stage": "finished", "kernel_digest": R.kernel_digest(),
                          "platform": {"system": pf.system().lower(), "python": pf.python_version()},
                          "story_outcomes": {"S1": ["COMMIT"]}, "story_errors": [], "final_main": main,
                          "delivery_verdict": "PASS", "delivery_blocked_by": [], "plan_quality_verdict": "NOT_CLAIMED",
                          "generalization_claim": "NONE", "budget_stop": None, "failure": None})
        self.assertEqual(rec["journal"]["closed"], "SHUTDOWN")
        self.assertTrue(rec["sessions"] and all("text" not in s for s in rec["sessions"]))
        self.assertTrue(all(d.is_dir() for d in (out / "work" / "ws", out / "work" / "merge", out / "probe-python")))
        self.assertEqual(seen["delivered"], {"S1": True})
        self.assertEqual(seen["secrets"], ("env-provider-key-0001",))
        self.assertEqual(seen["policy"], sr.Policy(self.st.limits, TestsPolicy(True), tool_timeout_s=self.st.timeouts_s["tool"]))

    def refusal(self, out, exc=R.RunRefused, **kw):
        with self.assertRaises(exc) as c:
            self.run_(out, **kw)
        failure = self.record(out)["failure"]
        self.assertEqual(failure, {"type": exc.__name__, "detail": str(c.exception), "stage": failure["stage"]})
        return str(c.exception), failure["stage"]

    def test_every_refusal_names_itself_and_the_stage_it_stopped(self):
        from aisef2.app import preflight
        with self.assertRaises(R.RunRefused) as c:
            R.execute(self.p, self.st, self.tmp / "absent", self.tmp / "o1", transport=self.e2e.provider(),
                      client_exe=str(self.base.client), cals=self.e2e.calibrations())
        self.assertTrue(str(c.exception).startswith("the project repository could not be cloned: "), str(c.exception))
        self.assertEqual(self.record(self.tmp / "o1")["failure"]["stage"], "repository")
        real_git = R.git

        def no_checkout(repo, *args):
            return subprocess.CompletedProcess(args, 1, "", "") if args[:1] == ("checkout",) else real_git(repo, *args)
        with mock.patch.object(R, "git", no_checkout):
            self.assertEqual(self.refusal(self.tmp / "o2"), ("the baseline could not be checked out as main", "repository"))
        msg, stage = self.refusal(self.tmp / "o3", cals=())
        self.assertEqual(stage, "admission")
        with mock.patch.object(R, "probe_interpreter", side_effect=R.RunRefused("no interpreter")):
            self.assertEqual(self.refusal(self.tmp / "o4"), ("no interpreter", "probe interpreter"))
        import shutil
        (self.tmp / "gitonly").mkdir()
        (self.tmp / "gitonly" / "git").symlink_to(shutil.which("git"))     # git, and no client, on the run's PATH
        with mock.patch.dict(os.environ, {"PATH": str(self.tmp / "gitonly")}):
            self.assertEqual(self.refusal(self.tmp / "o5", client_exe=None),
                             ("the client (opencode) is not on the PATH the run gives it", "preflight"))
        with mock.patch.dict(os.environ, {"PATH": f"{self.base.client.parent}{os.pathsep}{os.environ.get('PATH', '')}"}), \
                mock.patch.object(R.client, "configured_provider", side_effect=_Stop("found")):
            with self.assertRaises(_Stop):    # found on the PATH the run gives the client: the run went on to its config
                self.run_(self.tmp / "o6", client_exe=None)
        bad = self.e2e.provider(served="other-model")
        msg, stage = self.refusal(self.tmp / "o7", exc=preflight.IdentityStop, transport=bad)
        problems = self.record(self.tmp / "o7")["preflight"]["problems"]
        self.assertEqual((msg, stage, len(problems)), ("the route is not attested: " + "; ".join(problems), "preflight", 2))
        real_pre = preflight.run

        def unaccounted(*a, **k):
            pre = real_pre(*a, **k)
            return {**pre, "accounting": {**pre["accounting"], "unaccounted": ["r1"]}}
        with mock.patch.object(R.preflight, "run", unaccounted):
            self.assertEqual(self.refusal(self.tmp / "o8", exc=preflight.IdentityStop),
                             ("preflight requests unaccounted: ['r1']", "preflight"))

    def test_a_refused_story_does_not_stop_a_running_run(self):
        with mock.patch.object(bundle.Project, "order", lambda self: ["S1", "S1"]), \
                mock.patch.object(R.sr, "run_story", side_effect=RuntimeError("boom")):
            rec = self.run_(self.tmp / "o")
        self.assertEqual((rec["story_errors"], rec["story_outcomes"]),
                         ([{"story": "S1", "error": "RuntimeError: boom"}] * 2, {"S1": ["REFUSED: RuntimeError"]}))

    def test_a_story_not_run_for_the_budget_is_named(self):
        with mock.patch.object(R.client.Budget, "reached", return_value="max_provider_requests: 9 of 9"):
            rec = self.run_(self.tmp / "o")
        self.assertEqual(rec["story_outcomes"], {"S1": ["NOT_RUN: max_provider_requests: 9 of 9"]})
        self.assertTrue(rec["budget_stop"].startswith("S1 not run: max_provider_requests: 9 of 9"), rec["budget_stop"])

    def test_a_failure_after_a_delivered_story_fails_the_run(self):
        from aisef2.orchestrate import story_runner as sr
        real, calls = sr.run_story, []

        def once(*a, **k):
            calls.append(1)
            if len(calls) > 1:
                raise _Stop("stopped after S1")
            return real(*a, **k)
        out = self.tmp / "o"
        with mock.patch.object(bundle.Project, "order", lambda self: ["S1", "S1"]), mock.patch.object(R.sr, "run_story", once), \
                self.assertRaises(_Stop):
            self.run_(out)
        rec = self.record(out)
        self.assertEqual((rec["story_outcomes"], rec["delivery_verdict"], rec["failure"]["type"]), ({"S1": ["COMMIT"]}, "FAIL", "_Stop"))


@unittest.skipUnless(os.name == "posix", "the fake client is a script started by its shebang")
class AppVerify(unittest.TestCase):
    """aisef2.app.verify.verify L40-L52: refused stories re-derive FAIL; a record without a final main, or a run
    directory without its repository, is not compared with one; a journal that does not reconstruct is named with its
    error; and the answer is whole."""

    def setUp(self):
        from tests.v2 import test_app_run as e2e
        self.base = e2e.ProductBase("setUp")
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.base.execute()
        self.out = self.base.tmp / "out"
        self.rec = json.loads((self.out / "RUN.json").read_text(encoding="utf-8"))

    def verify(self, **changes):
        from aisef2.app.verify import verify
        (self.out / "RUN.json").write_text(json.dumps({**self.rec, **changes}), encoding="utf-8")
        return verify(self.base.project, self.out)

    def test_the_answer_is_whole_and_every_branch_is_its_own(self):
        from aisef2.journal import format3
        n = len(self.base.journal().events)
        self.assertEqual(self.verify(), {"verdict": "VERIFIED", "problems": [], "delivery_verdict": "PASS", "journal_events": n})
        refused = self.verify(story_errors=[{"story": "S1", "error": "RuntimeError: x"}], delivery_verdict="FAIL")
        self.assertEqual((refused["verdict"], refused["delivery_verdict"]), ("VERIFIED", "FAIL"))
        self.assertEqual(self.verify(final_main=None)["verdict"], "VERIFIED")
        (self.out / "repo").rename(self.out / "repo-aside")
        try:
            self.assertEqual(self.verify()["verdict"], "VERIFIED")    # no repository: nothing to compare
        finally:
            (self.out / "repo-aside").rename(self.out / "repo")
        journal = self.out / self.rec["journal"]["path"]
        bad = b'{"not": "a journal line"}\n'
        journal.write_bytes(bad)
        try:
            format3.reconstruct(bad.decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            why = f"the journal does not reconstruct: {type(e).__name__}: {e}"[:500]
        else:
            self.fail("the planted journal reconstructs")
        v = self.verify(journal={**self.rec["journal"], "sha256": hashlib.sha256(bad).hexdigest(), "lines": 1})
        self.assertIn(why, v["problems"])


class ClientReadSession(unittest.TestCase):
    """aisef2.app.client.read_session L38/L39/L56: a client's event log is read whatever it holds — bytes that are not
    UTF-8, lines that are JSON but not an event object, a finished step whose token report lacks a count."""

    def test_a_log_with_foreign_bytes_non_object_lines_and_a_partial_token_report(self):
        from aisef2.app import client
        with tempfile.TemporaryDirectory() as t:
            log = pathlib.Path(t) / "s.jsonl"
            log.write_bytes(b"\xff\xfe not text\n" + b"[1]\n" + b'{"type": "text", "part": {"text": "hi"}}\n'
                            + b'{"type": "step_finish", "part": {"tokens": {"input": 3}}}\n'
                            + b'{"type": "step_finish", "part": {"tokens": {"input": 2, "output": 1}}}\n')
            self.assertEqual(client.read_session(log), {"error": None, "text": "hi", "turns": 2,
                                                         "tokens": {"input": 2, "output": 1}, "steps_without_tokens": 1})


class ClientBudget(unittest.TestCase):
    """aisef2.app.client.Budget L70/L74/L94: the refusal of an incomplete budget names itself; the sessions are read in
    name order whatever order the directory lists them; every unaccounted reason is named, '; '-joined."""

    LIMITS = {"provider_requests": 10, "turns": 10, "input_tokens": 100, "output_tokens": 100}

    def test_an_incomplete_budget_is_refused_by_name(self):
        from aisef2.app import client
        with self.assertRaises(ValueError) as c:
            client.Budget({"turns": 1}, {}, pathlib.Path("."))
        self.assertEqual(str(c.exception), "a budget has the four ceilings, and a base that accounts for each of them")

    def test_unaccounted_spend_is_named_in_session_order(self):
        from aisef2.app import client
        with tempfile.TemporaryDirectory() as t:
            t = pathlib.Path(t)
            for name in ("a.jsonl", "b.jsonl"):     # one finished step each, with no token report
                (t / name).write_text('{"type": "step_finish", "part": {}}\n', encoding="utf-8")

            class Listed:                            # the directory, its logs listed in reverse name order
                def is_dir(self):
                    return True

                def glob(self, pattern):
                    return [t / "b.jsonl", t / "a.jsonl"]
            b = client.Budget(self.LIMITS, dict.fromkeys(self.LIMITS, 0), Listed())
            reasons = ["2 sessions were started but 0 provider requests are recorded",
                       "a.jsonl: 1 finished steps report no tokens", "b.jsonl: 1 finished steps report no tokens"]
            self.assertEqual(b.spend()["unaccounted"], reasons)
            self.assertEqual(b.reached(), "unaccounted: " + "; ".join(reasons))


class ClientEnvironment(unittest.TestCase):
    """aisef2.app.client.environment L119-L120: the client's environment is exactly the operator's PATH, home, system
    root, locale, temporary and XDG directories, the variables the settings name, and the overlay — nothing else."""

    def test_exactly_the_kept_variables_the_named_ones_and_the_overlay(self):
        from aisef2.app import client
        kept = ("PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "SystemRoot", "WINDIR", "LANG", "LC_ALL", "TMPDIR", "TEMP", "TMP",
                "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME")
        host = {**{k: f"v-{k}" for k in kept}, "AISEF_NAMED": "named", "AISEF_NOT_NAMED": "dropped"}
        with mock.patch.dict(os.environ, host, clear=True):
            env = client.environment(("AISEF_NAMED",), {"model": "m", "a": 1})
        self.assertEqual(env, {**{k: f"v-{k}" for k in kept}, "AISEF_NAMED": "named",
                               "OPENCODE_CONFIG_CONTENT": "{\"a\": 1, \"model\": \"m\"}"})


class ClientWaitWithin(unittest.TestCase):
    """aisef2.app.client.wait_within L153/L156: the wait ends once the process has an exit status (a further wait is a
    failure here, not a clock kill), and a request already in progress at the request ceiling may finish."""

    class Process:
        def __init__(self, codes):
            self.codes = list(codes)

        def wait(self, timeout):
            if not self.codes:
                raise AssertionError("waited again after the process reported its exit status")
            return self.codes.pop(0)

    def test_the_wait_ends_at_the_exit_status_and_a_request_in_progress_may_finish_at_the_ceiling(self):
        from aisef2.app import client
        limits = {"provider_requests": 1, "turns": 10, "input_tokens": 100, "output_tokens": 100}
        with tempfile.TemporaryDirectory() as t:
            t = pathlib.Path(t)
            budget = client.Budget(limits, dict.fromkeys(limits, 0), t / "logs", lambda: 1)   # the one request, recorded
            log = t / "s.jsonl"
            log.write_text("", encoding="utf-8")
            self.assertEqual(client.wait_within(self.Process([None, 0]), log, 30, budget, 9), (0, None))


class AppSettingsLoad(unittest.TestCase):
    """aisef2.app.settings.load L76/L84/L94: the refusals name the keys in order and the provider's shape; model_limit's
    two keys are accepted in any order."""

    def test_refusals_name_themselves_and_key_order_does_not_matter(self):
        from aisef2.app import settings
        from tests.v2 import test_app_run as e2e
        data = {k: v for k, v in e2e.SETTINGS.items() if k != "preflight"}
        data["extra"] = 1
        with self.assertRaises(settings.SettingsError) as c:
            settings.load(data)
        self.assertEqual(str(c.exception), f"run settings hold exactly {sorted(settings.KEYS)}; these hold {sorted(data)} — "
                                           "nothing is defaulted")
        with self.assertRaises(settings.SettingsError) as c:
            settings.load({**e2e.SETTINGS, "provider": {**e2e.SETTINGS["provider"], "name": "other"}})
        self.assertEqual(str(c.exception), "provider is {api_key_env, endpoint, listed_owner, model_limit, name, served_model}, "
                                           "its name the route's provider")
        reversed_limit = {**e2e.SETTINGS["provider"], "model_limit": {"output": 8000, "context": 100000}}
        self.assertEqual(settings.load({**e2e.SETTINGS, "provider": reversed_limit}).model_limit, {"context": 100000, "output": 8000})


class AppBundleLoad(unittest.TestCase):
    """aisef2.app.bundle.load L105-L129: every refusal names itself (the keys in order, a kernel object that does not
    load, a contract that does not compile, the facts' shape, the unknown specs in order); a KeyError while loading is a
    refusal; the approvals and their reviews load immutable."""

    def test_refusals_name_themselves_and_the_approvals_load_immutable(self):
        from tests.v2 import test_app_run as e2e
        doc = e2e.project_bundle("a" * 40)

        def refused(d):
            with self.assertRaises(bundle.BundleError) as c:
                bundle.load(d)
            return str(c.exception)
        keys = {k: v for k, v in doc.items() if k != "facts"}
        keys["extra"] = 1
        self.assertEqual(refused(keys), f"a bundle holds exactly {sorted(bundle.KEYS)}; it holds {sorted(keys)}")
        self.assertEqual(refused({**doc, "requirements": [{"no_id": 1}]}), "the bundle's kernel objects do not load: KeyError: 'id'")
        self.assertTrue(refused({**doc, "approvals": []}).startswith(f"contract {doc['contracts'][0]['id']} does not compile: "))
        self.assertEqual(refused({**doc, "facts": {}}),
                         f"facts are the public fields {list(bundle.FACT_FIELDS)} (strings) of every plan criterion, and no other")
        reviews = [{**a, "model_reviews": "not-a-list"} for a in doc["approvals"]]
        self.assertEqual(refused({**doc, "approvals": reviews}),
                         "the bundle's kernel objects do not load: ContractError: model_reviews must be a tuple of journal references")
        p = bundle.load(doc)
        self.assertIs(type(p.approvals), tuple)
        self.assertTrue(p.approvals and all(type(a.model_reviews) is tuple for a in p.approvals))

    def test_the_unknown_specs_are_named_in_order(self):
        doc = json.loads((ROOT / "closure-evidence/v2/release/LEDGERLOCK-PROJECT.json").read_text(encoding="utf-8"))
        named = sorted({o.product_proof_spec_id for o in bundle._plan(doc["plan"]).obligations})
        self.assertGreater(len(named), 3)
        with self.assertRaises(bundle.BundleError) as c:
            bundle.load({**doc, "contracts": []})
        self.assertEqual(str(c.exception), f"the plan names {len(named)} spec(s) no approved contract compiles to under this "
                                           f"release's probes: {named[:3]}")


FAKE_OPENCODE = """
import json, pathlib, sys, time
here = pathlib.Path(sys.argv[0]).parent
(here / "argv.json").write_text(json.dumps(sys.argv[1:]))
mode = (here / "mode").read_text()
print(json.dumps({"type": "text", "part": {"text": "hello"}}), flush=True)
print(json.dumps({"type": "step_finish", "part": {"tokens": {"input": 5, "output": 2}}}), flush=True)
if mode != "exit":
    time.sleep(60)
"""


@unittest.skipUnless(os.name == "posix", "the fake client is a script started by its shebang")
class ClientSession(unittest.TestCase):
    """aisef2.app.client.session L188-L211: the refusal of an unbound session names what is unbound; the client found on
    the PATH the session is given runs exactly `opencode run --format json --model M --title N --dir D PROMPT`; the
    log's parents are made; and the answer is whole — exited, timed out, stopped at the turn cap, or never started."""

    LIMITS = {"provider_requests": 9, "turns": 99, "input_tokens": 10 ** 6, "output_tokens": 10 ** 6}

    def setUp(self):
        from aisef2.app import client
        self.client = client
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(os.path.realpath(t.name))
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        (self.bin / "opencode").write_text(f"#!{sys.executable}\n" + FAKE_OPENCODE, encoding="utf-8")
        (self.bin / "opencode").chmod(0o755)
        self.logs = self.tmp / "deep" / "logs"     # its parent does not exist yet
        self.kw = {"model": "fakeprov/m", "env": {"PATH": f"{self.bin}{os.pathsep}/usr/bin:/bin"}, "turn_cap": 5,
                   "budget": client.Budget(self.LIMITS, dict.fromkeys(self.LIMITS, 0), self.logs, lambda: 1)}

    def mode(self, m):
        (self.bin / "mode").write_text(m, encoding="utf-8")

    def test_an_unbound_session_is_refused_naming_what_is_unbound(self):
        with self.assertRaises(self.client.SessionRefused) as c:
            self.client.session("n", "p", str(self.tmp), self.logs / "u.jsonl", 5, **{**self.kw, "model": None, "env": None})
        self.assertEqual(str(c.exception), "a model session needs a fixed route, a built environment, a budget and a turn cap; "
                                           "unbound: model, env")

    def test_a_session_runs_the_client_s_command_line_and_answers_whole(self):
        self.mode("exit")
        s = self.client.session("S1-dev", "the prompt", str(self.tmp), self.logs / "s.jsonl", 30, **self.kw)
        self.assertEqual(json.loads((self.bin / "argv.json").read_text()),
                         ["run", "--format", "json", "--model", "fakeprov/m", "--title", "S1-dev", "--dir", str(self.tmp), "the prompt"])
        self.assertIsInstance(s.pop("seconds"), float)
        self.assertEqual(s, {"exit": 0, "timed_out": False, "stopped": None, "started": True, "error": None, "text": "hello",
                             "turns": 1, "tokens": {"input": 5, "output": 2}, "log": "s.jsonl", "redacted": 0})

    def test_a_hung_session_times_out_and_a_capped_one_is_stopped(self):
        self.mode("hang")
        self.logs.mkdir(parents=True)        # a log whose directory already exists
        s = self.client.session("n", "p", str(self.tmp), self.logs / "h.jsonl", 1, **{**self.kw, "turn_cap": 99})
        self.assertEqual((s["exit"], s["timed_out"], s["stopped"], s["started"]), (None, True, None, True))
        capped = self.tmp / "capped"      # its own logs and budget: one session, one recorded request
        budget = self.client.Budget(self.LIMITS, dict.fromkeys(self.LIMITS, 0), capped, lambda: 1)
        s = self.client.session("n", "p", str(self.tmp), capped / "c.jsonl", 30, **{**self.kw, "turn_cap": 1, "budget": budget})
        self.assertEqual((s["exit"], s["timed_out"], s["stopped"]), (None, False, "session turn cap: 1 turns"))

    def test_a_session_that_never_starts_answers_whole(self):
        self.logs.mkdir(parents=True)
        (self.logs / "x.jsonl").write_text("", encoding="utf-8")
        why = "x.jsonl exists: a session's evidence is never overwritten"
        self.assertEqual(self.client.session("n", "p", str(self.tmp), self.logs / "x.jsonl", 5, **self.kw),
                         {"exit": None, "timed_out": False, "stopped": why, "started": False, "error": why, "text": "",
                          "turns": 0, "tokens": {"input": 0, "output": 0}, "seconds": 0.0, "log": None})


class AppPreflightAccounting(unittest.TestCase):
    """aisef2.app.preflight.accounting L59: requests sent and never answered are named in order."""

    def test_unanswered_requests_in_order(self):
        from aisef2.app import preflight
        with tempfile.TemporaryDirectory() as t:
            ledger = pathlib.Path(t) / "ledger.jsonl"
            ledger.write_text("".join(json.dumps({"event": "sent", "n": n}) + "\n" for n in (1, 8)), encoding="utf-8")
            self.assertEqual(preflight.accounting(ledger)["unaccounted"], [1, 8])    # {1, 8} iterates as [8, 1]


class AppAdapters(unittest.TestCase):
    """aisef2.app.adapters Developer.implement / Reviewer.review: the sessions they start (name, log, role), the
    developer's retry prompt, commit message and details, and the review's findings, whole."""

    def setUp(self):
        from tests.v2 import test_app_run as e2e
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(os.path.realpath(t.name))
        e2e.make_repo(self.tmp / "repo")
        self.project = bundle.load(e2e.project_bundle("a" * 40))
        from aisef2.arch.enums import ControlProjection
        self.events = []
        self.run = types.SimpleNamespace(events=self.events, state=lambda proj: {"S1": {"attempt": 2}}
                                         if proj is ControlProjection.STORY_STATE else None)
        self.calls = []

    def session(self, *, text="", write=None, stopped=None):
        from aisef2.app import client

        def fake(name, prompt, cwd, log, timeout_s, **kw):
            self.calls.append((name, prompt, log))
            if write:
                (pathlib.Path(cwd) / write).write_text("x = 1\n")
            return {"exit": 0, "timed_out": False, "stopped": stopped, "started": True, "error": None, "text": text,
                    "turns": 1, "tokens": {"input": 1, "output": 1}, "seconds": 0.0, "log": log.name}
        return mock.patch.object(client, "session", fake)

    def head_subject(self):
        return subprocess.run(["git", "-C", str(self.tmp / "repo"), "log", "-1", "--format=%s"], capture_output=True,
                              text=True, encoding="utf-8", check=True).stdout.strip()

    def test_the_developer_s_sessions_commits_and_details(self):
        from aisef2.app import adapters as ad
        from aisef2.journal.format2 import OperationOutcome as O
        dev = ad.Developer(self.run, self.project, self.tmp / "logs", {}, 5)
        with self.session():
            r = dev.implement("S1", ("C-ADD",), str(self.tmp / "repo"))
        self.assertEqual((r.outcome, r.detail), (O.FAILED, "the developer changed nothing (exit 0, timed out False)"))
        self.assertEqual(self.calls[-1][0::2], ("developer S1", self.tmp / "logs" / "S1.developer.2.jsonl"))
        self.assertEqual(dev.sessions[-1]["role"], "developer")
        with self.session(write="app/one.py"):
            r = dev.implement("S1", ("C-ADD",), str(self.tmp / "repo"))
        self.assertEqual((r.outcome, r.detail, self.head_subject()), (O.COMPLETED, "opencode exit 0, 1 turns", "S1: developer attempt 2"))
        with self.session(write="app/two.py", stopped="session turn cap: 1 turns"):
            r = dev.implement("S1", ("C-ADD",), str(self.tmp / "repo"))
        self.assertEqual(r.detail, "opencode exit 0, 1 turns, session turn cap: 1 turns")
        self.events.append(types.SimpleNamespace(seq=7, type="failure/observed", data={"story_id": "S1", "code": "X", "owner": "DEVELOPER"}))
        with self.session(write="app/three.py"):
            dev.implement("S1", ("C-ADD",), str(self.tmp / "repo"))
        self.assertTrue(self.calls[-1][1].endswith("\nFix the implementation."), self.calls[-1][1][-80:])

    def test_the_reviewer_s_session_and_findings(self):
        from aisef2.app import adapters as ad
        rev = ad.Reviewer(self.run, self.project, self.tmp / "logs", {}, 5)
        scope = types.SimpleNamespace(story_id="S1", root=str(self.tmp / "repo"))
        with self.session(text='{"findings": [{"id": "F1", "blocking": true}]}'):
            r = rev.review(scope, ("C-ADD",))
        self.assertEqual(self.calls[-1][0::2], ("reviewer S1", self.tmp / "logs" / "S1.reviewer.2.jsonl"))
        self.assertEqual((rev.sessions[-1]["role"], rev.sessions[-1]["findings"]), ("reviewer", [{"id": "F1", "blocking": True}]))
        self.assertIs(type(r.findings), tuple)


class AppPreflightRun(unittest.TestCase):
    """aisef2.app.preflight.run L67-L91: what the preflight sends, what its ledger says, what it observed, and the
    record it writes — whole."""

    def test_the_preflight_s_requests_ledger_observation_and_record(self):
        from aisef2.app import preflight
        from tests.v2 import test_app_run as e2e
        sent, provider = [], e2e.provider()

        def transport(path, body=None):
            sent.append((path, body))
            return provider(path, body)
        with tempfile.TemporaryDirectory() as t:
            d = pathlib.Path(t) / "deep" / "pre"        # its parent does not exist yet
            rec = preflight.run(e2e.ROUTE, 2, transport, d, "model-1", "fake")
            chat = {"model": "model-1", "messages": [{"role": "user", "content": preflight.PROBE_PROMPT}],
                    "max_tokens": preflight.PROBE_MAX_TOKENS, "temperature": 0}
            self.assertEqual(sent, [("/models", None), ("/chat/completions", chat), ("/chat/completions", chat)])
            self.assertEqual([json.loads(x) for x in (d / "LEDGER.jsonl").read_text(encoding="utf-8").splitlines()], [
                {"n": 1, "event": "sent", "kind": "listing"}, {"n": 1, "event": "done", "http": 200},
                {"n": 2, "event": "sent", "kind": "chat"}, {"n": 2, "event": "done", "http": 200, "input_tokens": 9, "output_tokens": 1},
                {"n": 3, "event": "sent", "kind": "chat"}, {"n": 3, "event": "done", "http": 200, "input_tokens": 9, "output_tokens": 1}])
            probe = {"http": 200, "served_model": "model-1", "system_fingerprint": "fp-1"}
            self.assertEqual(rec["observation"], {"route": e2e.ROUTE, "declared_model": "model-1", "expected_served_model": "model-1",
                                                  "expected_listed_owner": "fake",
                                                  "listing": {"http": 200, "listed": True, "id": "model-1", "owned_by": "fake"},
                                                  "probes": [probe, probe]})
            self.assertEqual((d / "PREFLIGHT.json").read_text(encoding="utf-8"), json.dumps(rec, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    unittest.main()
