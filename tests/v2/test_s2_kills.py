"""V2.0-S2 mutation: cases that kill survivors of the current-snapshot campaign. A file of its own, named only in the kill
sets of the targets it was written for (validation/v2/mutation.py), so adding to it re-measures those targets alone —
every other result's kill-test closure stays byte-identical (validation/qualification/s2_mutation_record.py)."""

from __future__ import annotations

import json
import os
import pathlib
import select
import subprocess
import sys
import tempfile
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
        import hashlib
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


if __name__ == "__main__":
    unittest.main()
