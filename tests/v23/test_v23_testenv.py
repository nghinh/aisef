"""L1-TESTENV (W1-DESIGN §7): a kill test never sees the real client (V21-36); arming never leaks into an unarmed-refusal
test (#34). No existing test file is edited (§2.8).

V21-36: the product resolves its client by name on the PATH it is given (aisef2/app/run.py `client_on_path`,
aisef2/app/client.py `session`: `shutil.which("opencode", ...)`), and the kill-test environment keeps the worker's PATH
(validation/v2/mutation.py `ENV_KEEP`). A mutant that drops a test's `client_exe` override therefore starts the real,
paid client wherever one is installed. `mutation.main` refuses (exit 3) before any `run_target` when an executable
`opencode` is resolvable on PATH; that hunk is L1-F5's (W1-DESIGN §7, §8). Red-before: at 1e25ef84 `t0` and `run` reach
`run_target` with a client on PATH.
V21-36 OPEN until that hunk lands: the guard test carries an explicit `@unittest.expectedFailure` (reported as "expected
failures=1", never skipped). It cannot outlive the fix: once the guard exists it is an unexpected success, which fails
the raw discover and release_qualify (`unexpectedSuccesses` count as failing), so the hunk's commit must drop the
marker. An unmarked test pins that the expected failure is exactly the measured red-before and nothing else.
Evidence: docs/v2.3/evidence/l1-testenv/README.md.

#34: `_ARMED` (the tiers) and `_RUNTIME_ARMED` (`arm_runtime()`) are process globals of aisef2/invariants/registry.py,
and `require_armed` passes when either holds the invariant. A test that clears the tiers alone still runs armed once any
test of the interpreter called `arm_runtime()`, so its refusal never fires (CODE-AUDIT #34). The scan below fails on
any such patch in tests/ (red-before on known-bad inline sources); the three named unarmed-refusal tests still observe
InvariantError in one interpreter that called `arm_runtime()` first.
"""

from __future__ import annotations

import ast
import contextlib
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.v2 import mutation  # noqa: E402


# ------------------------------------------------------------------------------------------------ V21-36

MODES = ("t0", "run")   # L1-F5's --run-affected joins the guard's modes and this tuple once it exists


class _Ran(BaseException):
    """run_target was reached. A BaseException, so main's `except Exception` around a target never makes a record of it."""


def _with_client(d: pathlib.Path) -> str:
    exe = d / ("opencode.exe" if os.name == "nt" else "opencode")
    exe.write_bytes(b"")
    exe.chmod(0o755)
    return str(d)


class RealClientGuard(unittest.TestCase):
    def main(self, mode: str, path: str):
        """mutation.main([mode, target]) with PATH = `path`. Nothing it can reach runs or writes: ROOT is a scratch
        directory, and the host table, the pristine copy and run_target are stand-ins."""
        target = next(t for phase in mutation.RECORDS for t in mutation.PHASE_TARGETS[phase])   # one `run` measures
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"PATH": path}), \
                mock.patch.object(mutation, "ROOT", pathlib.Path(d)), \
                mock.patch.object(mutation, "_earlier", return_value=[]), \
                mock.patch.object(mutation, "_pristine", return_value=(pathlib.Path(d), "0" * 64)), \
                mock.patch.object(mutation, "run_target", side_effect=_Ran) as run_target, \
                contextlib.redirect_stdout(io.StringIO()) as out:
            try:
                code = mutation.main([mode, target])
            except _Ran:
                code = "reached run_target"
        return code, run_target.call_count, out.getvalue()

    def with_client(self) -> dict:
        with tempfile.TemporaryDirectory() as empty, tempfile.TemporaryDirectory() as bin_:
            path = os.pathsep.join([empty, _with_client(pathlib.Path(bin_))])   # not the first entry: any entry counts
            return {mode: self.main(mode, path) for mode in MODES}

    # V21-36 OPEN — guard hunk owned by L1-F5. Drop this marker, and test_the_open_marker_turns_red_once_the_guard_
    # exists, in the commit that lands the hunk: until then a pass here is an unexpected success, which fails the run.
    @unittest.expectedFailure
    def test_a_client_resolvable_on_path_stops_t0_and_run_before_any_target(self):
        for mode, (code, calls, out) in self.with_client().items():
            with self.subTest(mode=mode):
                self.assertEqual((code, calls), (3, 0), out)
                self.assertIn("opencode", out)

    def test_v21_36_is_open_exactly_as_measured_or_closed(self):
        # unmarked: the expected failure above may only be the measured red-before. A third outcome (an error, another
        # exit code, a refusal that does not name the client, one mode guarded and the other not) fails here.
        def state(code, calls, out):
            return "open" if (code, calls) == ("reached run_target", 1) else \
                "guarded" if (code, calls) == (3, 0) and "opencode" in out else f"neither {(code, calls, out)!r}"
        states = {mode: state(*got) for mode, got in self.with_client().items()}
        self.assertIn(set(states.values()), ({"open"}, {"guarded"}), states)

    def test_the_open_marker_turns_red_once_the_guard_exists(self):
        # L1-F5's hunk, simulated around mutation.main: the marked test then passes, i.e. it is an unexpected success
        real = mutation.main

        def guarded(argv):
            if argv[:1] in (["t0"], ["run"]) and (exe := shutil.which("opencode")):
                print(f"STOPPED before the first target: an executable opencode is resolvable on PATH ({exe})")
                return 3
            return real(argv)

        result = unittest.TestResult()
        with mock.patch.object(mutation, "main", guarded):
            RealClientGuard("test_a_client_resolvable_on_path_stops_t0_and_run_before_any_target").run(result)
        self.assertEqual((len(result.unexpectedSuccesses), result.failures, result.errors, result.expectedFailures),
                         (1, [], [], []))
        self.assertFalse(result.wasSuccessful())

    def test_with_no_client_on_path_t0_and_run_reach_the_target(self):
        # the control: the stand-ins above do reach run_target, so the refusal is the guard's and nothing else's
        with tempfile.TemporaryDirectory() as empty:
            for mode in MODES:
                with self.subTest(mode=mode):
                    self.assertEqual(self.main(mode, empty)[:2], ("reached run_target", 1))

    def test_a_kill_test_gets_fresh_xdg_directories_never_the_workers(self):
        # the XDG half of V21-36, already the runner's (_FRESH): pinned, so the PATH guard is never the only isolation
        names = ("HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME")
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {k: os.path.join(d, "worker") for k in names}):
            run = pathlib.Path(d) / "run"
            run.mkdir()
            env = mutation._env(run, "w:1")
            for k in names:
                with self.subTest(var=k):
                    self.assertEqual(os.path.dirname(env[k]), str(run))


# ------------------------------------------------------------------------------------------------ #34

_MUTATORS = {"clear", "pop", "popitem", "update", "setdefault", "__setitem__", "__delitem__"}


def _leaf(node) -> str | None:
    return node.attr if isinstance(node, ast.Attribute) else node.id if isinstance(node, ast.Name) else None


def _patched(*calls) -> set[str]:
    """The arming globals these `mock.patch*` calls patch: patch.object(x, NAME), patch.dict(x.NAME), patch("m.NAME"),
    patch.multiple(x, NAME=...)."""
    out: set[str] = set()
    for c in calls:
        if not isinstance(c, ast.Call):
            continue
        chain, f = [], c.func
        while isinstance(f, ast.Attribute):
            chain.append(f.attr)
            f = f.value
        chain = [*([f.id] if isinstance(f, ast.Name) else []), *reversed(chain)]
        if "patch" not in chain:
            continue
        kind, a = chain[chain.index("patch") + 1:], c.args
        if kind == ["object"] and len(a) > 1 and isinstance(a[1], ast.Constant):
            out.add(a[1].value)
        elif kind == ["dict"] and a:
            out.add(a[0].value.rsplit(".", 1)[-1] if isinstance(a[0], ast.Constant) and isinstance(a[0].value, str)
                    else _leaf(a[0]))
        elif kind == [] and a and isinstance(a[0], ast.Constant) and isinstance(a[0].value, str):
            out.add(a[0].value.rsplit(".", 1)[-1])
        elif kind == ["multiple"]:
            out.update(k.arg for k in c.keywords)
    return out & {"_ARMED", "_RUNTIME_ARMED"}


def unpaired(source: str, where: str = "<source>") -> list[str]:
    """Every patch of `_ARMED` in `source` that no patch of `_RUNTIME_ARMED` covers — in the same `with` statement or an
    enclosing one, or among the decorators of the same test or its class — and every patch of `_ARMED` started by hand
    or write of it in place, where no pairing can be read."""
    out: list[str] = []

    def walk(node, held: set, cls: set) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            deco = _patched(*node.decorator_list)
            if "_ARMED" in deco and "_RUNTIME_ARMED" not in deco | cls:
                out.append(f"{where}:{node.lineno}: {node.name}: a decorator patches _ARMED, none patches _RUNTIME_ARMED")
            for child in node.body:
                walk(child, cls | deco, cls | deco if isinstance(node, ast.ClassDef) else cls)
            return
        if isinstance(node, (ast.With, ast.AsyncWith)):
            mine = _patched(*(i.context_expr for i in node.items))
            if "_ARMED" in mine and "_RUNTIME_ARMED" not in mine | held:
                out.append(f"{where}:{node.lineno}: a with statement patches _ARMED; neither it nor an enclosing one "
                           "patches _RUNTIME_ARMED")
            for child in node.body:
                walk(child, held | mine, cls)
            return
        if isinstance(node, ast.Call):
            if "_ARMED" in _patched(node):
                out.append(f"{where}:{node.lineno}: a patch of _ARMED outside a with statement or a decorator")
            elif isinstance(node.func, ast.Attribute) and node.func.attr in _MUTATORS and _leaf(node.func.value) == "_ARMED":
                out.append(f"{where}:{node.lineno}: _ARMED.{node.func.attr}() writes the tiers' arming in place")
        targets = node.targets if isinstance(node, (ast.Assign, ast.Delete)) else \
            [node.target] if isinstance(node, (ast.AugAssign, ast.AnnAssign)) else []
        if any(_leaf(t.value if isinstance(t, ast.Subscript) else t) == "_ARMED" for t in targets):
            out.append(f"{where}:{node.lineno}: a direct write of _ARMED")
        for child in ast.iter_child_nodes(node):
            walk(child, held, cls)

    walk(ast.parse(source), set(), set())
    return out


_IMPORTS = ("from unittest import mock\nfrom aisef2.invariants import registry as reg\n"
            "from aisef2.invariants.registry import InvariantId, require_armed\n\n")
KNOWN_BAD = {
    "with: the tiers only": "def test(self):\n    with mock.patch.dict(reg._ARMED, clear=True):\n"
                            "        require_armed(InvariantId.VIII)\n",
    "patch.object: the tiers only": "def test(self):\n    with mock.patch.object(reg, '_ARMED', {}):\n        pass\n",
    "patch by name: the tiers only": "def test(self):\n    with mock.patch('aisef2.invariants.registry._ARMED', {}):\n"
                                     "        pass\n",
    "decorator: the tiers only": "@mock.patch.object(reg, '_ARMED', {})\ndef test(self):\n    pass\n",
    "runtime patched after the with": "def test(self):\n    with mock.patch.dict(reg._ARMED, clear=True):\n        pass\n"
                                      "    with mock.patch.object(reg, '_RUNTIME_ARMED', None):\n        pass\n",
    "started by hand": "def test(self):\n    p = mock.patch.dict(reg._ARMED, clear=True)\n    p.start()\n",
    "cleared in place": "def test(self):\n    reg._ARMED.clear()\n",
    "assigned": "def test(self):\n    reg._ARMED = {}\n",
}
KNOWN_GOOD = {
    "one with": "def test(self):\n    with mock.patch.dict(reg._ARMED, clear=True), "
                "mock.patch.object(reg, '_RUNTIME_ARMED', None):\n        require_armed(InvariantId.VIII)\n",
    "enclosing with": "def test(self):\n    with mock.patch.object(reg, '_RUNTIME_ARMED', None):\n"
                      "        with mock.patch.dict(reg._ARMED, clear=True):\n            pass\n",
    "decorators": "@mock.patch.object(reg, '_RUNTIME_ARMED', None)\n@mock.patch.object(reg, '_ARMED', {})\n"
                  "def test(self):\n    pass\n",
    "class decorator": "@mock.patch.object(reg, '_RUNTIME_ARMED', None)\nclass T:\n"
                       "    @mock.patch.object(reg, '_ARMED', {})\n    def test(self):\n        pass\n",
    "multiple": "def test(self):\n    with mock.patch.multiple(reg, _ARMED={}, _RUNTIME_ARMED=None):\n        pass\n",
    "a read": "def test(self):\n    before = dict(reg._ARMED)\n",
}

NAMED = ("tests.v2.p5.test_invariants.Arming.test_a_runtime_guard_refuses_to_work_in_an_unarmed_process",
         "tests.v2.p5.test_invariants.MemoryIsContext.test_the_boundary_inspects_no_model_and_fails_closed",
         "tests.v2.p4.test_run_scope.B1SurvivorKills.test_an_unarmed_begin_refuses_and_attributes_the_refusal_to_invariant_II")
#: one fresh interpreter: arm_runtime() first, then the named tests, then a tiers-only refusal (the known-bad shape)
ONE_INTERPRETER = r'''
import json, sys, unittest
from unittest import mock
sys.path.insert(0, sys.argv[1])
from aisef2.errors import InvariantError
from aisef2.invariants import registry as reg
from aisef2.invariants.registry import InvariantId, require_armed
reg.arm_runtime()


class TiersOnly(unittest.TestCase):
    def test_refusal(self):
        with mock.patch.dict(reg._ARMED, clear=True), self.assertRaises(InvariantError):
            require_armed(InvariantId.VIII)


def run(suite):
    r = unittest.TestResult()
    suite.run(r)
    return {"ran": r.testsRun, "failures": [str(t) for t, _ in r.failures], "errors": [str(t) for t, _ in r.errors],
            "skipped": [str(t) for t, _ in r.skipped]}


named = unittest.defaultTestLoader.loadTestsFromNames(sys.argv[2:])
state = lambda: {"runtime": sorted(i.value for i in reg._RUNTIME_ARMED or ()), "tiers": sorted(t.name for t in reg._ARMED)}
before = state()
print(json.dumps({"before": before, "named": run(named), "tiers_only": run(unittest.defaultTestLoader.loadTestsFromTestCase(TiersOnly)),
                  "after": state()}))
'''


class ArmingNeverLeaks(unittest.TestCase):
    def test_the_scan_refuses_every_known_bad_shape_and_accepts_every_paired_one(self):
        for name, body in KNOWN_BAD.items():
            with self.subTest(bad=name):
                self.assertTrue(unpaired(_IMPORTS + body), name)
        for name, body in KNOWN_GOOD.items():
            with self.subTest(good=name):
                self.assertEqual(unpaired(_IMPORTS + body), [])

    def test_no_test_in_tests_patches_the_tiers_without_the_runtime_arming(self):
        scanned, sites = [], 0
        for p in sorted((ROOT / "tests").rglob("*.py")):
            text = p.read_text(encoding="utf-8", errors="replace")
            if "_ARMED" not in text:
                continue
            rel = p.relative_to(ROOT).as_posix()   # this file too: its known-bad shapes are strings, not code
            self.assertEqual(unpaired(text, rel), [])
            scanned.append(rel)
            sites += sum(1 for n in ast.walk(ast.parse(text)) if isinstance(n, ast.Call) and "_ARMED" in _patched(n))
        # not vacuous: the three named tests' four patch sites are read
        self.assertLessEqual({"tests/v2/p5/test_invariants.py", "tests/v2/p4/test_run_scope.py"}, set(scanned))
        self.assertGreaterEqual(sites, 4)

    def test_the_named_refusals_hold_in_one_interpreter_after_arm_runtime(self):
        r = subprocess.run([sys.executable, "-P", "-c", ONE_INTERPRETER, str(ROOT), *NAMED], cwd=ROOT,
                           capture_output=True, text=True, encoding="utf-8", timeout=300)
        self.assertEqual(r.returncode, 0, r.stderr[-3000:])
        got = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(len(got["before"]["runtime"]), 9, got)       # runtime-armed before the first named test
        self.assertTrue(got["before"]["tiers"], got)                  # and tier-armed: the tier packages were imported
        self.assertEqual(got["named"], {"ran": 3, "failures": [], "errors": [], "skipped": []}, r.stderr[-3000:])
        # the known-bad shape in the same state: it fails, so this interpreter is one where a tiers-only clear leaks
        self.assertEqual((got["tiers_only"]["ran"], len(got["tiers_only"]["failures"])), (1, 1), got)
        self.assertEqual(got["after"], got["before"])                 # what the tests patched is back


if __name__ == "__main__":
    unittest.main()
