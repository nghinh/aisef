"""PM-7 (B-03 round 3, docs/v2.1/decisions/B03-R3-PROBE-MODULE-FINDINGS.md §PM-7): the sources of a probe's
EXECUTION_DIGEST are the files whose code decides what the probe observes -- declared from a measurement, and held
against drift.

What a source is. `PROBE_SOURCES` of each probe module names the files of `aisef2/` whose bytes make up the probe's
EXECUTION_DIGEST, the third identity of V2-007 ("the bytes that run": a calibration row and the run's RunSpec bind
it, so a byte change needs its calibrations demonstrated again before anything admits). A file belongs there when its
code is part of what the probe does, not when it is merely loaded. Measured on the three probes that run a subject
in a process of their own (cli_invocation, process_effect, python_callable_v2), during their real tests:

* the host process executes, while `observe` / `run_probe` is on the stack: the probe module, `probe/protocol.py`,
  `probe/python_callable.py`, `product/contract.py` (`plain`, `names_test_artefact`, `digest`, `content_of`),
  `product/outcome.py` (`Executed.__post_init__`, `on_subject_absent`) and `runtime/process_range.py` (every
  `ProcessRange` method), and the process range launches `runtime/range_anchor.py` as a script of its own;
* the probe's two child processes -- the controller (HARNESS) and the subject's process (AGENT), and the subprocess
  step's boot -- import the standard library and nothing of `aisef2/`: their behaviour is the text of the scripts,
  which sit in the probe modules (measured with the interpreter's own `-X importtime` on both command lines).

Until this change the digest left out `runtime/process_range.py`, `runtime/range_anchor.py`, `product/contract.py` and
`product/outcome.py`: five commits changed `process_range.py` after the calibrations were written and 19 of 19 rows
stayed "valid". Declaring them makes a change to any of the four demand its calibrations again.

What a source is not. A source is hashed and nothing else (PROBE_SOURCES is read by `_probe_digest` only: asserted
below): it is never opened, copied, imported or executed on a probe's behalf, so declaring one extends no authority
-- not to read, not to run -- and brings no file other than the four into the digest. The rest of the closure the
probe's imports load (24 modules, 8 of them package initialisers) is named in `LOADED_NOT_A_SOURCE` with the reason
it does not decide what the probe observes; a module that joins the closure without being a source or named there
fails here, so the choice is made when it is introduced.

This file holds, for each of the three probes:

1. MEASURED: every file of `aisef2/` whose code executes during real observations (a SATISFIED run, an absent
   subject, a refused spec, a harness that cannot launch) is a source;
2. LOADED: every file the probe module's imports pull in (the static closure, imports inside functions included) is
   a source or is named in `LOADED_NOT_A_SOURCE`, and every entry there is not a source and exists;
3. SCRIPTS: the anchor the range launches is a source; the child scripts import only the standard library;
4. HASH ONLY: `PROBE_SOURCES` is referenced in `aisef2/` only by its own assignment and by `_probe_digest`, whose
   only act on a source is to read its bytes into a hash.

Adding a fourth probe or a source is a one-row change of the tables below.
"""

import ast
import contextlib
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import Enforcement  # noqa: E402
from aisef2.probe import cli_invocation as ci  # noqa: E402
from aisef2.probe import process_effect as pe_module  # noqa: E402
from aisef2.probe import python_callable_v2 as pc2_module  # noqa: E402
from aisef2.probe.protocol import ExecutionEnv, RevisionRef, run_probe  # noqa: E402
from aisef2.runtime import process_range  # noqa: E402
from tests.v2 import test_c2_cli_invocation as cli  # noqa: E402  (builders only)
from tests.v2 import test_probe_process_effect as pe  # noqa: E402
from tests.v2 import test_python_callable_v2 as pc2  # noqa: E402

AISEF2 = pathlib.Path(ci.__file__).resolve().parents[1]
MOD = "def f():\n    return 1\n\n\ndef main(argv):\n    return 0\n"

#: probe module (relative to aisef2/) -> the module, a spec builder taking the window, and the probe's own test module
#: (its builders, SHA, env and probe instance)
PROBES = {
    "probe/cli_invocation.py": (ci, lambda window=5: cli.spec("m:main", {"exit_code": 0}, window=window), cli),
    "probe/process_effect.py": (pe_module, lambda window=5: pe.spec("m:f", [pe.call(None)], {"returns": 1},
                                                                    window=window), pe),
    "probe/python_callable_v2.py": (pc2_module, lambda window=5: pc2.spec("m:f", {"returns": 1}, {}, window=window),
                                    pc2),
}

#: Files of `aisef2/` that a probe's imports load but whose code does not decide what the probe observes: the reason,
#: per file. Every entry holds for the three probes; none may be a source.
LOADED_NOT_A_SOURCE = {
    "__init__.py": "package initialiser: a docstring and no code",
    "arch/__init__.py": "package initialiser: a docstring and no code",
    "control/__init__.py": "package initialiser: a docstring and no code",
    "journal/__init__.py": "package initialiser: a docstring and no code",
    "plan/__init__.py": "package initialiser: a docstring and no code",
    "probe/__init__.py": "package initialiser: a docstring and no code",
    "product/__init__.py": "package initialiser: a docstring and no code",
    "runtime/__init__.py": "package initialiser: a docstring and no code",
    "arch/enums.py": "the closed vocabularies: members used by name, no function of it runs in an observation "
                     "(measured, test 1); the frozen architecture's own change control governs it",
    "errors.py": "the kernel's error type, constructed only when an invariant is violated: not on an observation's "
                 "path (measured, test 1)",
    "product/spec.py": "the spec a probe is GIVEN: minted and verified by the compiler before any probe runs; a probe "
                       "reads its fields and no function of it runs in an observation (measured, test 1)",
    "probe/calibration.py": "loaded through plan/static_admission (below); the calibration check is admission's, "
                            "never a step of an observation",
    "runtime/story_scope.py": "imported by process_range only for the `Residual` type: StoryScope is the CALLER's "
                              "`on_range` hook, handed to the probe by the harness and never called by it; its bytes "
                              "are bound by RunSpec.kernel, not by a probe's digest",
    "journal/format2.py": "imported by process_range only for the `ResourceKind` vocabulary",
    "journal/event.py": "reached through journal/format2 (an event type of the journal): not on a probe's path",
    "journal/compat.py": "reached through journal/format2 (journal compatibility): not on a probe's path",
    "control/owner.py": "reached through journal/event: failure ownership is the kernel's decision on a "
                        "ProbeResult, never part of producing one",
    "control/routing.py": "reached through plan/story_admission: routing consumes a ProbeResult, never produces one",
    "plan/drift.py": "reached through journal/event: plan drift is the kernel's, not a probe's",
    "plan/obligation.py": "reached through journal/event: obligations are the plan's, not a probe's",
    "plan/static_admission.py": "reached through journal/event: admission checks a spec before a probe runs",
    "plan/story_admission.py": "reached through journal/event: story admission consumes probe results",
    "product/approval.py": "reached through plan/static_admission: approvals are checked before a probe runs",
    "product/compiler.py": "reached through plan/static_admission: specs are compiled before a probe runs",
}
#: Files of `aisef2/` whose code executes during an observation and are not a source: none. An entry is a reason, so
#: a file added here is a decision with its reason in the review.
EXECUTED_NOT_A_SOURCE: dict[str, str] = {}

#: the names `_probe_digest` may call: reading bytes into a hash and nothing else
HASHING_CALLS = {"Path", "resolve", "sha256", "update", "encode", "read_bytes", "replace", "hexdigest"}


def sources_of(module) -> tuple[str, ...]:
    return tuple(module.PROBE_SOURCES)


def module_file(dotted: str) -> pathlib.Path | None:
    path = ROOT.joinpath(*dotted.split("."))
    if path.with_suffix(".py").is_file():
        return path.with_suffix(".py")
    init = path / "__init__.py"
    return init if init.is_file() else None


def static_closure(start: str) -> set[str]:
    """Every file of `aisef2/` the import statements of `start` and, transitively, of what it imports can reach: any
    `import` / `from ... import` at any depth of a file, each parent package's initialiser included."""
    seen: dict[str, pathlib.Path] = {}
    todo: list[str] = []

    def add(name: str) -> None:
        parts = name.split(".")
        for i in range(1, len(parts) + 1):     # the import system runs every parent package's initialiser
            sub = ".".join(parts[:i])
            path = module_file(sub)
            if sub not in seen and path is not None:
                seen[sub] = path
                todo.append(sub)

    add(start)
    while todo:
        for node in ast.walk(ast.parse(seen[todo.pop()].read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module, *(f"{node.module}.{a.name}" for a in node.names)]
            else:
                continue
            for name in names:
                if name.split(".")[0] == "aisef2":
                    add(name)
    return {path.relative_to(AISEF2).as_posix() for path in seen.values()}


@contextlib.contextmanager
def executing():
    """The files of `aisef2/` any code runs in -- function calls and module-level code -- while this block is on the
    stack, in this process and in every thread started inside it."""
    seen: set[str] = set()
    cache: dict[str, str | None] = {}
    prefix = os.path.normcase(str(AISEF2)) + os.sep

    def hook(frame, event, arg):
        if event != "call":
            return
        name = frame.f_code.co_filename
        if name not in cache:
            real = os.path.normcase(os.path.realpath(name))
            cache[name] = real[len(prefix):].replace(os.sep, "/") if real.startswith(prefix) else None
        if cache[name] is not None:
            seen.add(cache[name])

    before, before_threads = sys.getprofile(), threading.getprofile()
    sys.setprofile(hook)
    threading.setprofile(hook)
    try:
        yield seen
    finally:
        sys.setprofile(before)
        threading.setprofile(before_threads)


class _Observed(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp = tempfile.TemporaryDirectory(prefix="aisef2-pm7-", ignore_cleanup_errors=True)
        cls.addClassCleanup(tmp.cleanup)
        present = pe.checkout(os.path.join(tmp.name, "present"), {"m.py": MOD})
        absent = pe.checkout(os.path.join(tmp.name, "absent"), {"README.md": "nothing of the product yet\n"})
        cant_launch = ExecutionEnv(os.path.join(tmp.name, "no-python"), 20, Enforcement.PARTIAL)
        cls.executed: dict[str, set[str]] = {}
        for rel, (_module, build, helper) in PROBES.items():
            runs = (
                (build(), RevisionRef(helper.SHA, present), helper.env()),                  # SATISFIED
                (build(), RevisionRef(helper.SHA, absent), helper.env()),                   # the subject is absent
                (build(window=None), RevisionRef(helper.SHA, present), helper.env()),       # a spec with no class
                (build(), RevisionRef(helper.SHA, present), cant_launch),                   # a harness that cannot launch
            )
            with executing() as seen:
                statuses = [run_probe(helper.P, s, at, env).result.status.value for s, at, env in runs]
            if statuses != ["EXECUTED", "EXECUTED", "INVALID_SPEC", "UNRUNNABLE"]:
                raise AssertionError(f"{rel}: the four observations ended {statuses}")
            cls.executed[rel] = seen


class TheDigestCoversWhatRuns(_Observed):
    def test_every_file_whose_code_runs_in_an_observation_is_a_source(self):
        """Measured, on the real probes: the files that executed are sources, bar the (empty) documented exceptions.
        Pins the declared set against a change that makes a probe call into a file the digest does not cover."""
        for rel, (module, _build, _helper) in PROBES.items():
            executed = self.executed[rel]
            with self.subTest(probe=rel):
                self.assertIn(rel, executed)      # the measurement saw the probe at all
                self.assertIn("probe/protocol.py", executed)
                self.assertIn("runtime/process_range.py", executed)
                self.assertIn("product/outcome.py", executed)        # on_subject_absent / Executed
                self.assertIn("product/contract.py", executed)       # plain / names_test_artefact
                missing = executed - set(sources_of(module)) - set(EXECUTED_NOT_A_SOURCE)
                self.assertEqual(missing, set(),
                                 f"code of {sorted(missing)} ran during an observation of {rel} and is not a source "
                                 "of its EXECUTION_DIGEST: declare it in PROBE_SOURCES, or name it with its reason "
                                 "in EXECUTED_NOT_A_SOURCE")

    def test_nothing_is_declared_that_no_observation_runs_but_the_anchor_script(self):
        """The sources are exactly the files that ran in this process or run as its child: the anchor, a script the
        range launches, which no profile of this process can see, is the one source that is not executed here."""
        anchor = os.path.relpath(process_range.ANCHOR, AISEF2).replace(os.sep, "/")
        self.assertEqual(anchor, "runtime/range_anchor.py")
        for rel, (module, _build, _helper) in PROBES.items():
            with self.subTest(probe=rel):
                self.assertIn(anchor, sources_of(module))
                self.assertEqual(set(sources_of(module)) - {anchor}, self.executed[rel] - set(EXECUTED_NOT_A_SOURCE))


class TheLoadedClosureIsAccountedFor(unittest.TestCase):
    def test_every_file_a_probe_loads_is_a_source_or_is_named_with_its_reason(self):
        for rel, (module, _build, _helper) in PROBES.items():
            closure = static_closure("aisef2." + rel[:-3].replace("/", ".")) | {"runtime/range_anchor.py"}  # a script
            sources = set(sources_of(module))
            with self.subTest(probe=rel):
                self.assertTrue(sources <= closure, f"declared but not loaded: {sorted(sources - closure)}")
                unaccounted = closure - sources - set(LOADED_NOT_A_SOURCE)
                self.assertEqual(unaccounted, set(),
                                 f"{sorted(unaccounted)} are loaded by {rel} and are neither a source of its digest "
                                 "nor named in LOADED_NOT_A_SOURCE: decide which, and say why")

    def test_what_a_fresh_interpreter_loads_is_inside_the_static_closure(self):
        """The static closure is only as good as its reading of the imports: what a new interpreter loads on importing
        each probe module must be inside it (an import by `importlib` or `__import__` would not be)."""
        code = ("import json, sys\nsys.path.insert(0, sys.argv[1])\n__import__(sys.argv[2])\n"
                "print(json.dumps(sorted(m.__file__ for n, m in list(sys.modules.items())"
                " if n.split('.')[0] == 'aisef2' and getattr(m, '__file__', None))))")
        for rel in PROBES:
            dotted = "aisef2." + rel[:-3].replace("/", ".")
            done = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", code, str(ROOT), dotted], check=True,
                                  capture_output=True, encoding="utf-8", stdin=subprocess.DEVNULL, timeout=120)
            loaded = {pathlib.Path(f).resolve().relative_to(AISEF2).as_posix() for f in json.loads(done.stdout)}
            with self.subTest(probe=rel):
                self.assertEqual(loaded - static_closure(dotted), set())
                self.assertIn(rel, loaded)

    def test_the_named_exceptions_are_real_files_with_a_reason_and_none_is_a_source(self):
        every_source = {s for module, _b, _h in PROBES.values() for s in sources_of(module)}
        for rel, reason in {**LOADED_NOT_A_SOURCE, **EXECUTED_NOT_A_SOURCE}.items():
            with self.subTest(file=rel):
                self.assertTrue((AISEF2 / rel).is_file())
                self.assertGreater(len(reason.split()), 3)
                self.assertNotIn(rel, every_source)

    def test_a_package_initialiser_named_above_holds_no_code(self):
        for rel in (r for r in LOADED_NOT_A_SOURCE if r.endswith("__init__.py")):
            tree = ast.parse((AISEF2 / rel).read_text(encoding="utf-8"))
            with self.subTest(file=rel):
                self.assertTrue(all(isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) for n in tree.body),
                                "an initialiser with code is a file that runs: decide it like any other")

    def test_the_sources_are_distinct_relative_files_and_the_digest_is_over_them_in_order(self):
        for rel, (module, _build, _helper) in PROBES.items():
            sources = sources_of(module)
            with self.subTest(probe=rel):
                self.assertEqual(len(set(sources)), len(sources))
                self.assertIn(rel, sources)                 # its own module is one of them
                self.assertTrue(all((AISEF2 / s).is_file() and not s.startswith(("/", "..")) for s in sources))
                h = hashlib.sha256()
                for s in sources:
                    h.update(s.encode() + b"\0" + (AISEF2 / s).read_bytes().replace(b"\r\n", b"\n") + b"\0")
                self.assertEqual(h.hexdigest(), module._probe_digest())


class TheChildScriptsRunNothingOfTheKernel(unittest.TestCase):
    def test_the_child_processes_import_only_the_standard_library(self):
        """The controller (HARNESS), the subject's process (AGENT) and the subprocess step's boot run under
        `-I -S` with the revision on the path and import no module of `aisef2/` (also measured with the
        interpreter's `-X importtime`): so the text of the scripts, which is in the probe modules, is all of them."""
        scripts = {"cli_invocation.AGENT": ci.AGENT, "cli_invocation.HARNESS": ci.HARNESS,
                   "process_effect.HARNESS": pe_module.HARNESS, "process_effect.SUBPROCESS": pe_module.SUBPROCESS,
                   "python_callable_v2.HARNESS": pc2_module.HARNESS}
        for name, text in scripts.items():
            imported = set()
            for node in ast.walk(ast.parse(text)):
                if isinstance(node, ast.Import):
                    imported |= {a.name.split(".")[0] for a in node.names}
                elif isinstance(node, ast.ImportFrom):
                    imported.add((node.module or "").split(".")[0])
            with self.subTest(script=name):
                self.assertTrue(imported)
                self.assertEqual(imported - set(sys.stdlib_module_names), set())


class ASourceIsOnlyHashed(unittest.TestCase):
    def references(self, path: pathlib.Path):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        for node in ast.walk(tree):
            if (isinstance(node, ast.Name) and node.id == "PROBE_SOURCES") \
                    or (isinstance(node, ast.Attribute) and node.attr == "PROBE_SOURCES"):
                scope = node
                while scope in parents and not isinstance(scope, (ast.FunctionDef, ast.Module)):
                    scope = parents[scope]
                yield node, scope

    def test_in_the_kernel_it_is_assigned_once_and_read_by_probe_digest_alone(self):
        found = 0
        for path in sorted(AISEF2.rglob("*.py")):
            for node, scope in self.references(path):
                found += 1
                rel = path.relative_to(AISEF2).as_posix()
                with self.subTest(file=rel, line=node.lineno):
                    assigned = isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store) \
                        and isinstance(scope, ast.Module)
                    hashed = isinstance(scope, ast.FunctionDef) and scope.name == "_probe_digest"
                    self.assertTrue(assigned or hashed, f"{rel}:{node.lineno} uses PROBE_SOURCES outside the "
                                                        "assignment and _probe_digest: a source is only hashed")
        self.assertGreaterEqual(found, 10)    # five probe modules, an assignment and a read each

    def test_probe_digest_does_nothing_with_a_source_but_read_its_bytes_into_a_hash(self):
        for rel in ("probe/cli_invocation.py", "probe/process_effect.py", "probe/python_callable_v2.py",
                    "probe/file_artifact.py", "probe/python_callable.py"):
            tree = ast.parse((AISEF2 / rel).read_text(encoding="utf-8"))
            digest = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_probe_digest")
            called = {n.func.attr if isinstance(n.func, ast.Attribute) else n.func.id
                      for n in ast.walk(digest) if isinstance(n, ast.Call)}
            with self.subTest(file=rel):
                self.assertEqual(called - HASHING_CALLS, set())
                self.assertEqual({n.id for n in ast.walk(digest) if isinstance(n, ast.Name)} & {"open", "exec", "eval",
                                                                                              "compile", "__import__"},
                                 set())


if __name__ == "__main__":
    unittest.main()
