"""P7-FINDING-001 — bytecode isolation of the python_callable observation (owner's kernel correction authorization,
§3–§16; PYC-1..12).

The defect: a revision that carries bytecode of another source beside a source (`__pycache__/*.pyc` committed by a
developer, or written by an earlier observation) made the interpreter's verdict depend on the checkout's file dates —
CPython takes a timestamp .pyc whose header mtime (whole seconds) and size equal the source's — so two independent
checkouts of one immutable revision could observe different code. The correction: the harness runs with a fresh,
empty, harness-owned bytecode cache of its own (`-X pycache_prefix`, on the command line, which `-I` honours) and
`-B` as defence in depth. Every case here constructs the offending state deterministically — no timing, no sleeps —
and reads the verdict from the real probe on a real checkout (git where the case is about a revision).
"""

import importlib.util
import os
import pathlib
import py_compile
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import BehaviorVerdict as V, Enforcement, EventType as T, MeasurementPoint, ObligationRole  # noqa: E402
from aisef2.orchestrate import story_runner as sr  # noqa: E402
from aisef2.orchestrate.proof import Party, prove  # noqa: E402
from aisef2.orchestrate.workspace import GitMerger, GitWorkspace, commit_all, git  # noqa: E402
from aisef2.probe import python_callable as pc  # noqa: E402
from aisef2.probe.protocol import ExecutionEnv, RevisionRef, run_probe  # noqa: E402
from aisef2.probe.python_callable import PythonCallableProbe  # noqa: E402
from aisef2.product.outcome import Executed  # noqa: E402
from aisef2.product.spec import ProductProofSpec  # noqa: E402
from aisef2.runtime.run_scope import RunScope  # noqa: E402
from tests.v2 import test_p6_orchestration as orch  # noqa: E402
from tests.v2.p4.test_run_scope import spec as RUN_SPEC  # noqa: E402
from tests.v2.p4.world import closed_after  # noqa: E402

ENV = ExecutionEnv(sys.executable, 60, Enforcement.PARTIAL)
SOURCE_A = "def f():\n    return 1\n"     # the source the stale bytecode was compiled from
SOURCE_B = "def f():\n    return 2\n"     # the source of the revision under proof: same size, one character apart
assert len(SOURCE_A) == len(SOURCE_B)
RETURNS_2 = {"returns": 2, "within_s": 10}
RETURNS_1 = {"returns": 1, "within_s": 10}


def spec(observable, *, expectation=V.SATISFIED, probe=None):
    probe = probe or pc
    return ProductProofSpec.create(
        contract_id="BC-PYC", probe_id=probe.PROBE_ID, probe_digest=probe.DIGEST,
        probe_input={"subject": {"kind": "python_callable", "locator": "app.mod:f"}, "stimulus": {},
                     "observable": observable, "subject_absence": "REQUIRES_SUBJECT"},
        candidate_expectation=expectation, compiler_id="test", compiler_digest="c" * 64)


def stale_checkout(root: pathlib.Path, *, offset_s: int = 0, bytecode: bool = True) -> dict:
    """The offending state, constructed: app/mod.py holding SOURCE_B beside app/__pycache__/mod.<tag>.pyc compiled
    from SOURCE_A, the bytecode's header matching the source's size and, with `offset_s` 0, its whole-second mtime —
    exactly what lets an interpreter without a cache of its own take the stale code; another offset dates the source
    away from the collision. `bytecode` False: the sources alone. Returns what was built."""
    app = root / "app"
    app.mkdir(parents=True, exist_ok=True)
    (app / "__init__.py").write_text("", encoding="utf-8")
    src = app / "mod.py"
    src.write_text(SOURCE_A, encoding="utf-8", newline="\n")
    cfile = importlib.util.cache_from_source(str(src))
    if bytecode:
        py_compile.compile(str(src), cfile=cfile, doraise=True, invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP)
    header = pathlib.Path(cfile).read_bytes()[:16] if bytecode else b"\0" * 16
    src.write_text(SOURCE_B, encoding="utf-8", newline="\n")
    second = int.from_bytes(header[8:12], "little")
    os.utime(src, (second + offset_s, second + offset_s))
    st = src.stat()
    return {"source": str(src), "bytecode": cfile if bytecode else None, "header_mtime": second,
            "header_size": int.from_bytes(header[12:16], "little"), "source_mtime_s": int(st.st_mtime) & 0xFFFFFFFF,
            "source_size": st.st_size & 0xFFFFFFFF,
            "collision": bytecode and second == int(st.st_mtime) & 0xFFFFFFFF and st.st_size == int.from_bytes(header[12:16], "little")}


def snapshot(root: pathlib.Path) -> dict:
    """Every file under `root` (git's own directory aside) by content and mtime — the checkout, byte for byte."""
    out = {}
    for p in sorted(root.rglob("*")):
        if ".git" in p.parts or not p.is_file():
            continue
        out[str(p.relative_to(root))] = (p.read_bytes(), p.stat().st_mtime_ns)
    return out


def verdict(record):
    return record.result.behavior_verdict if isinstance(record.result, Executed) else record.result


class Launch:
    """Captures the harness command lines the probe launched (the real ProcessRange runs them)."""

    def __init__(self):
        self.argv = []
        self.real = pc.ProcessRange

    def __enter__(self):
        def make(name, argv, **kw):
            self.argv.append(list(argv))
            return self.real(name, argv, **kw)
        self._p = mock.patch.object(pc, "ProcessRange", make)
        self._p.start()
        return self

    def __exit__(self, *exc):
        self._p.stop()
        return False

    def prefixes(self):
        return [a[a.index("-X") + 1].removeprefix("pycache_prefix=") for a in self.argv]


class WithoutPrefix:
    """A controlled mutant: the harness command line without the external bytecode cache (the pre-correction line,
    plus -B when `keep_b`)."""

    def __init__(self, keep_b: bool):
        self.keep_b = keep_b

    def __enter__(self):
        def argv(interpreter, ask, pycache):
            return [interpreter, "-I", *(["-B"] if self.keep_b else []), "-c", pc.HARNESS, ask]
        self._p = mock.patch.object(pc, "_harness_argv", argv)
        self._p.start()
        return self

    def __exit__(self, *exc):
        self._p.stop()
        return False


class WithoutB:
    """A controlled mutant: the command line without -B, the external cache kept."""

    def __enter__(self):
        def argv(interpreter, ask, pycache):
            return [interpreter, "-I", "-X", f"pycache_prefix={pycache}", "-c", pc.HARNESS, ask]
        self._p = mock.patch.object(pc, "_harness_argv", argv)
        self._p.start()
        return self

    def __exit__(self, *exc):
        self._p.stop()
        return False


class Bytecode(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory(prefix="aisef2-pyc-")
        self.addCleanup(self._d.cleanup)
        self.tmp = pathlib.Path(self._d.name)
        self.root = self.tmp / "checkout"
        self.built = stale_checkout(self.root)
        self.assertTrue(self.built["collision"], self.built)
        self.at = RevisionRef("a" * 40, str(self.root))

    def observe(self, observable, *, probe=None, expectation=V.SATISFIED):
        probe = probe or PythonCallableProbe()
        return run_probe(probe, spec(observable, expectation=expectation), self.at, ENV)

    def test_PYC_1_in_tree_stale_bytecode_with_a_matching_header_is_not_the_subject_the_source_is(self):
        # returns 2 is SOURCE_B's behaviour; the stale bytecode returns 1
        self.assertEqual(verdict(self.observe(RETURNS_2)), V.SATISFIED)
        self.assertEqual(verdict(self.observe(RETURNS_1, expectation=V.REFUTED)), V.REFUTED)

    def test_PYC_2_two_checkouts_of_the_same_content_with_different_dates_observe_one_verdict(self):
        other = self.tmp / "verifier"
        built = stale_checkout(other, offset_s=100)   # same files, the source dated away from the collision
        self.assertFalse(built["collision"])
        a = run_probe(PythonCallableProbe(), spec(RETURNS_2), RevisionRef("a" * 40, str(self.root)), ENV)
        b = run_probe(PythonCallableProbe(), spec(RETURNS_2), RevisionRef("a" * 40, str(other)), ENV)
        self.assertEqual((verdict(a), verdict(b)), (V.SATISFIED, V.SATISFIED))
        self.assertEqual(a.result, b.result)

    def test_PYC_3_a_checkout_with_committed_bytecode_is_byte_identical_before_and_after_the_proof(self):
        git(self.root, "init", "-q", "-b", "main")
        rev = commit_all(self.root, "revision with committed bytecode")
        self.assertIn("app/__pycache__/", git(self.root, "ls-tree", "-r", "--name-only", rev).stdout)
        before, status_before = snapshot(self.root), git(self.root, "status", "--porcelain").stdout
        self.assertEqual(verdict(run_probe(PythonCallableProbe(), spec(RETURNS_2), RevisionRef(rev, str(self.root)), ENV)), V.SATISFIED)
        self.assertEqual(snapshot(self.root), before)
        self.assertEqual(git(self.root, "status", "--porcelain").stdout, status_before)
        self.assertEqual(status_before, "")

    def test_PYC_4_the_probe_writes_no_bytecode_into_the_checkout(self):
        plain = self.tmp / "plain"
        stale_checkout(plain, bytecode=False)   # the sources alone, no __pycache__ at all
        self.assertEqual(verdict(run_probe(PythonCallableProbe(), spec(RETURNS_2), RevisionRef("a" * 40, str(plain)), ENV)), V.SATISFIED)
        self.assertEqual(sorted(str(p.relative_to(plain)) for p in plain.rglob("*.pyc")), [])
        self.assertFalse((plain / "app" / "__pycache__").exists())

    def test_PYC_5_the_bytecode_cache_is_fresh_empty_and_outside_the_checkout(self):
        seen = {}
        real_start = pc.ProcessRange.start

        def start(run):   # the state at launch: the prefix exists, is empty, and is not under the checkout
            argv = run._argv
            prefix = argv[argv.index("-X") + 1].removeprefix("pycache_prefix=")
            seen["argv"], seen["prefix"] = argv, prefix
            seen["empty_at_launch"] = os.listdir(prefix) == []
            seen["inside_checkout"] = pc._inside(prefix, str(self.root))
            return real_start(run)
        with mock.patch.object(pc.ProcessRange, "start", start):
            self.assertEqual(verdict(self.observe(RETURNS_2)), V.SATISFIED)
        self.assertEqual(seen["argv"][1:4], ["-I", "-B", "-X"])
        self.assertEqual((seen["empty_at_launch"], seen["inside_checkout"]), (True, False))
        self.assertTrue(pathlib.Path(seen["prefix"]).parent.name.startswith("aisef2-probe-"), seen["prefix"])
        self.assertFalse(pathlib.Path(seen["prefix"]).exists())   # the probe's own temporary directory: gone with the evaluation

    def test_PYC_5b_under_a_story_scratch_the_cache_lies_there_and_is_left_to_the_scratch(self):
        """With -B nothing is written anywhere; without it (the controlled mutant) the bytecode lands under the
        prefix, in the scratch — never in the checkout — and stays for the scratch's own disposal."""
        scratch = self.tmp / "scratch"
        scratch.mkdir()
        before = snapshot(self.root)
        with Launch() as launched:
            self.assertEqual(verdict(self.observe(RETURNS_2, probe=PythonCallableProbe(scratch=str(scratch)))), V.SATISFIED)
            with WithoutB():
                self.assertEqual(verdict(self.observe(RETURNS_2, probe=PythonCallableProbe(scratch=str(scratch)))), V.SATISFIED)
        with_b, without_b = launched.prefixes()
        self.assertEqual({pathlib.Path(with_b).parent.parent, pathlib.Path(without_b).parent.parent}, {scratch})
        self.assertTrue(all(pathlib.Path(x).parent.name.startswith("probe-") for x in (with_b, without_b)), (with_b, without_b))
        self.assertEqual(sorted(pathlib.Path(with_b).rglob("*.pyc")), [])
        cached = sorted(str(p.relative_to(without_b)) for p in pathlib.Path(without_b).rglob("*.pyc"))
        self.assertTrue(any(p.endswith("mod." + sys.implementation.cache_tag + ".pyc") for p in cached), cached)
        self.assertEqual(snapshot(self.root), before)   # the checkout untouched either way

    def test_PYC_6_implementer_and_verifier_get_distinct_caches(self):
        scratch = self.tmp / "scratch"
        scratch.mkdir()
        with Launch() as launched:
            for _ in ("implementer", "verifier"):
                self.assertEqual(verdict(self.observe(RETURNS_2, probe=PythonCallableProbe(scratch=str(scratch)))), V.SATISFIED)
        a, b = launched.prefixes()
        self.assertNotEqual(a, b)
        self.assertTrue(pathlib.Path(a).exists() and pathlib.Path(b).exists())

    def test_PYC_7_an_evaluation_never_reuses_the_cache_of_the_one_before(self):
        """Three evaluations of one probe under one scratch, without -B so that each writes bytecode into its own
        prefix: three prefixes, each empty at its own launch although the earlier ones hold bytecode by then."""
        scratch = self.tmp / "scratch"
        scratch.mkdir()
        probe = PythonCallableProbe(scratch=str(scratch))
        states = []
        real_start = pc.ProcessRange.start

        def start(run):
            argv = run._argv
            prefix = argv[argv.index("-X") + 1].removeprefix("pycache_prefix=")
            states.append((prefix, sorted(os.listdir(prefix))))
            return real_start(run)
        with WithoutB(), mock.patch.object(pc.ProcessRange, "start", start):
            for _ in range(3):
                self.assertEqual(verdict(self.observe(RETURNS_2, probe=probe)), V.SATISFIED)
        prefixes = [s[0] for s in states]
        self.assertEqual(len(set(prefixes)), 3)
        self.assertEqual([s[1] for s in states], [[], [], []])   # each empty at its launch
        self.assertTrue(all(list(pathlib.Path(p).rglob("*.pyc")) for p in prefixes))   # and each holds its own bytecode now

    def test_PYC_8_isolated_mode_keeps_the_command_line_controls_and_drops_the_environment_route(self):
        probe_line = subprocess.run([sys.executable, "-I", "-B", "-X", f"pycache_prefix={self.tmp / 'c'}", "-c",
                                     "import sys; print(sys.pycache_prefix, sys.dont_write_bytecode, sys.flags.isolated)"],
                                    capture_output=True, encoding="utf-8")
        self.assertEqual(probe_line.stdout.split(), [str(self.tmp / "c"), "True", "1"])
        env_line = subprocess.run([sys.executable, "-I", "-c", "import sys; print(sys.pycache_prefix, sys.dont_write_bytecode)"],
                                  env={**os.environ, "PYTHONPYCACHEPREFIX": str(self.tmp / "c"), "PYTHONDONTWRITEBYTECODE": "1"},
                                  capture_output=True, encoding="utf-8")
        self.assertEqual(env_line.stdout.split(), ["None", "False"])
        runner_line = subprocess.run([sys.executable, "-E", "-s", "-B", "-c", "import sys; print(sys.dont_write_bytecode)"],
                                     env={**os.environ, "PYTHONDONTWRITEBYTECODE": ""}, capture_output=True, encoding="utf-8")
        self.assertEqual(runner_line.stdout.strip(), "True")

    def test_PYC_9_without_B_the_external_cache_alone_keeps_the_stale_bytecode_out_and_the_checkout_unwritten(self):
        before = snapshot(self.root)
        with WithoutB():
            self.assertEqual(verdict(self.observe(RETURNS_2)), V.SATISFIED)
        self.assertEqual(snapshot(self.root), before)

    def test_PYC_10_without_the_external_cache_the_stale_bytecode_decides_the_verdict_the_reproducer_detects_the_defect(self):
        for keep_b in (True, False):
            with self.subTest(keep_b=keep_b), WithoutPrefix(keep_b=keep_b):
                self.assertEqual(verdict(self.observe(RETURNS_2)), V.REFUTED)   # the stale code's 1, not the source's 2
                self.assertEqual(verdict(self.observe(RETURNS_1, expectation=V.REFUTED)), V.SATISFIED)

    def test_PYC_11_a_size_and_whole_second_collision_cannot_split_the_two_parties_of_a_proof(self):
        """The two-party proof (proof.py), the implementer's checkout dated into the collision and the verifier's not,
        at one revision: agreement, and the source's verdict on both sides."""
        tmp = self.tmp
        (tmp / "run").mkdir()
        run = closed_after(self, RunScope(tmp / "run", "run-pyc", spec=RUN_SPEC, clock=iter(float(n) for n in range(10 ** 6)).__next__))
        run.begin()
        s = spec(RETURNS_2)
        sr._freeze_plan(run, orch.plan_of("a" * 40, orch.PlanObligation("C1", s.id, "S1", ObligationRole.INTRODUCE,
                                                                        orch.EXPECTED_AT_PARENT[ObligationRole.INTRODUCE], (), "S1 owns C1")))
        run.append(T.STORY_BEGIN, {"story_id": "S1", "parent": "a" * 40})
        run.append(T.STORY_ADMITTED, {"story_id": "S1", "parent": "a" * 40, "admitted": True, "developer_call_permitted": True,
                                      "dispositions": {"C1": "READY"}})
        scope = run.story("S1")
        other = tmp / "verifier"
        built = stale_checkout(other, offset_s=100)
        self.assertFalse(built["collision"])
        scratch = tmp / "scratch"
        scratch.mkdir()
        implementer = Party(scope, lambda on_range: PythonCallableProbe(on_range=on_range, scratch=str(scratch)), "implementer")
        verifier = Party(scope, lambda on_range: PythonCallableProbe(on_range=on_range, scratch=str(scratch)), "verifier")
        p = prove(run, "S1", "C1", s, ObligationRole.INTRODUCE, implementer=implementer, verifier=verifier, candidate="a" * 40,
                  implementer_root=str(self.root), verifier_root=str(other), env=ENV, point=MeasurementPoint.CANDIDATE)
        self.assertTrue(p.agreement)
        self.assertIsNone(p.failure)
        records = [run.events[q].data["record"]["result"] for q in (p.implementer_seq, p.verifier_seq)]
        self.assertEqual(records, [{"behavior_verdict": "SATISFIED", "reason": None}] * 2)
        scope.dispose()

    def test_PYC_13_an_evaluation_directory_inside_the_checkout_is_refused_not_used(self):
        """A scratch that lies inside the checkout would make the cache product state: the probe refuses to run there
        (HARNESS_FAILED -> UNRUNNABLE) rather than write into the revision."""
        inside = self.root / "scratch-in-tree"
        inside.mkdir()
        record = self.observe(RETURNS_2, probe=PythonCallableProbe(scratch=str(inside)))
        self.assertEqual(record.result.status.value, "UNRUNNABLE")
        self.assertIn("inside the revision checkout: refused", record.result.detail)
        self.assertEqual(sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*.pyc")),
                         [os.path.relpath(self.built["bytecode"], self.root)])   # nothing new in the checkout
        self.assertEqual(sorted(p.name for p in inside.iterdir()), sorted(p.name for p in inside.iterdir()))

    def test_PYC_14_an_evaluation_directory_that_cannot_be_created_is_a_harness_failure(self):
        """A scratch that does not exist: the evaluation directory cannot be created — HARNESS_FAILED -> UNRUNNABLE,
        typed with the error's name, before any launch; never a verdict."""
        record = self.observe(RETURNS_2, probe=PythonCallableProbe(scratch=str(self.tmp / "no-such-scratch")))
        self.assertEqual(record.result.status.value, "UNRUNNABLE")
        self.assertEqual(record.result.detail, "the evaluation directory cannot be created: FileNotFoundError")
        self.assertFalse((self.tmp / "no-such-scratch").exists())

    def test_PYC_12_one_revision_across_repeated_fresh_scopes_observes_one_verdict(self):
        results = []
        for n in range(5):
            scratch = self.tmp / f"scratch-{n}"
            scratch.mkdir()
            results.append(self.observe(RETURNS_2, probe=PythonCallableProbe(scratch=str(scratch))).result)
        self.assertEqual(results, [Executed(V.SATISFIED)] * 5)


class Revision(unittest.TestCase):
    """The story-level shape of the finding (DIAG-2 of test_p6_orchestration.py is the full path): a merged revision
    carrying stale bytecode, two worktrees of it, one dated into the collision — one verdict, from the source."""

    def test_PYC_11b_two_worktrees_of_one_revision_with_committed_stale_bytecode_agree(self):
        with tempfile.TemporaryDirectory(prefix="aisef2-pyc-") as t:
            tmp = pathlib.Path(t)
            repo = tmp / "repo"
            built = stale_checkout(repo)
            git(repo, "init", "-q", "-b", "main")
            rev = commit_all(repo, "stale bytecode committed")
            ws = GitWorkspace(repo, tmp / "ws")
            (tmp / "ws").mkdir()
            impl, ver = ws.checkout("wt-S1", rev), ws.checkout("verifier-wt-S1", rev)
            second = built["header_mtime"]
            os.utime(impl.path / "app" / "mod.py", (second, second))   # the implementer's file dated into the collision
            a = run_probe(PythonCallableProbe(), spec(RETURNS_2), RevisionRef(rev, str(impl.path)), ENV)
            b = run_probe(PythonCallableProbe(), spec(RETURNS_2), RevisionRef(rev, str(ver.path)), ENV)
            self.assertEqual((verdict(a), verdict(b)), (V.SATISFIED, V.SATISFIED))
            self.assertEqual(git(impl.path, "status", "--porcelain").stdout + git(ver.path, "status", "--porcelain").stdout, "")
            impl.release()
            ver.release()
            self.assertIsInstance(GitMerger(repo, "main", tmp / "merge").base(), str)


if __name__ == "__main__":
    unittest.main()
