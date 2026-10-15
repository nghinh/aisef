"""V2.1 (B-03 round 3, PM-7) — what `probe.file_artifact`'s EXECUTION_DIGEST covers is measured, not remembered.

EXECUTION_DIGEST is the sha256 of PROBE_SOURCES, and a calibration row and the run's RunSpec bind it: "the bytes that
run" (ARCHITECTURE-EXCEPTION-V2-007). The tuple is a declaration, so it can drift from what the probe really takes
behaviour from. PM-7 found `product/outcome.py` outside it: the protocol builds every result from its types, and the
verdict over an absent subject is its `on_subject_absent` — an edit to it left every calibration row valid. Review of
that change found `product/contract.py` outside it for the same reason, and it is in: `run_probe` applies the invariant-IX
name gate (`names_test_artefact`) before any probe looks and the answer it gives is a record's result (InvalidSpec), so an
edit to the gate changed a probe's records with every calibration row still valid.

Three things are pinned, each by measurement and not by a list copied from the module:

1. a fresh interpreter imports the probe and runs one observation of every class, over a directory and over an absent
   path; the aisef2 modules it then holds are exactly PROBE_SOURCES plus the modules named in `NOT_SOURCES`, each with
   the reason it is not a behaviour source. An import added to the probe (or to what it imports) fails here until
   someone classifies it — declares it a source, or says why it is not one;
2. every declared source exists and is loaded: nothing is declared that the probe does not use;
3. PROBE_SOURCES only feeds the digest. It grants nothing and loads nothing: its one reader is `_probe_digest`, a probe
   whose tuple is emptied answers the same, and naming a module in it does not import that module."""

from __future__ import annotations

import ast
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.probe import file_artifact as fa  # noqa: E402
from aisef2.probe.protocol import RevisionRef, run_probe  # noqa: E402
from tests.v2 import test_c2_file_artifact as base  # noqa: E402   (helpers only: its test classes are not imported)

#: aisef2 modules the probe process holds that its behaviour is NOT taken from, and why. Anything else it holds must be
#: in PROBE_SOURCES. A module moves between this table and PROBE_SOURCES only with its calibration rows proved again.
NOT_SOURCES = {
    "aisef2": "package marker: a docstring",
    "aisef2.arch": "package marker: a docstring",
    "aisef2.probe": "package marker: empty",
    "aisef2.product": "package marker: a docstring",
    "aisef2.arch.enums": "the frozen vocabulary the results are written in (members, no procedure); checked against the "
                         "RFC and the arch catalog by WP-0.2 / WP-0.3, and a change to a member is an "
                         "ARCHITECTURE_EXCEPTION",
    "aisef2.errors": "exception types; no decision",
    "aisef2.product.spec": "the spec's data type: the probe reads its fields; none of its code runs in an observation "
                           "(its constructor runs in the caller, before the probe is given the spec)",
}

SCRIPT = r'''
import json, os, pathlib, sys, tempfile
root = sys.argv[1]
sys.path.insert(0, root)
from aisef2.probe import file_artifact as fa
from aisef2.arch.enums import BehaviorVerdict, Enforcement
from aisef2.probe.protocol import ExecutionEnv, RevisionRef, run_probe
from aisef2.product.spec import ProductProofSpec

with tempfile.TemporaryDirectory(prefix="aisef2-pm7-") as d:
    pathlib.Path(d, "pkg").mkdir()
    pathlib.Path(d, "pkg", "a.py").write_text("import os\n", encoding="utf-8")
    pathlib.Path(d, "pkg", "b.txt").write_text("hello\n", encoding="utf-8")
    probe, env, ref = fa.FileArtifactProbe(), ExecutionEnv(sys.executable, 30.0, Enforcement.PARTIAL), RevisionRef("0" * 40, d)
    calls = ((("path:pkg/a.py"), {"condition": "exists"}, {}), ("path:pkg/b.txt", {"sha256": "0" * 64}, {}),
             ("path:pkg", {"matches": 1}, {"grep": "^import"}),
             ("path:pkg", {"matches": 0}, {"imports_outside": {"stdlib": True, "allowed": []}}),
             ("path:missing", {"matches": 0}, {"imports_outside": {"stdlib": True, "allowed": []}}),
             ("path:../escape", {"condition": "exists"}, {}))
    for locator, observable, stimulus in calls:
        for absence in ("REQUIRES_SUBJECT", "ABSENCE_IS_DECIDABLE"):
            spec = ProductProofSpec.create(
                contract_id="BC-PM7", probe_id=probe.id, probe_digest=probe.digest,
                probe_input={"subject": {"kind": "file_artifact", "locator": locator}, "stimulus": stimulus,
                             "observable": {**observable, "within_s": 10}, "subject_absence": absence},
                candidate_expectation=BehaviorVerdict.SATISFIED, compiler_id="pm7", compiler_digest="0" * 64)
            run_probe(probe, spec, ref, env)

held = sorted(n for n in sys.modules if n == "aisef2" or n.startswith("aisef2."))
before_naming = "aisef2.app.run" in sys.modules
digest_before = fa._probe_digest()
fa.PROBE_SOURCES = (*fa.PROBE_SOURCES, "app/run.py")        # a name in the tuple: read for the hash, nothing else
digest_named = fa._probe_digest()
print(json.dumps({"held": held, "named_module_loaded_before": before_naming,
                  "named_module_loaded_after": "aisef2.app.run" in sys.modules,
                  "digest_changed_by_naming": digest_named != digest_before, "digest_before": digest_before}))
'''


def module_of(rel: str) -> str:
    """`product/outcome.py` -> `aisef2.product.outcome`."""
    return "aisef2." + rel.removesuffix(".py").replace("/", ".")


class Measured(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        env.pop("PYTHONPATH", None)
        with tempfile.TemporaryDirectory(prefix="aisef2-pm7-cwd-") as cwd:
            p = subprocess.run([sys.executable, "-I", "-B", "-c", SCRIPT, str(ROOT)], capture_output=True, text=True,
                               encoding="utf-8", env=env, cwd=cwd, timeout=180)
        if p.returncode != 0:
            raise AssertionError(f"the measuring interpreter exited {p.returncode}: {p.stderr[-800:]}")
        cls.found = json.loads(p.stdout.strip().splitlines()[-1])

    def test_every_module_the_probe_holds_is_a_source_or_is_named_with_its_reason(self):
        held = set(self.found["held"])
        sources = {module_of(rel) for rel in fa.PROBE_SOURCES}
        self.assertEqual(held - sources - set(NOT_SOURCES), set(),
                         "the probe now loads a module that is neither a PROBE_SOURCE nor in NOT_SOURCES: decide which "
                         "(a source changes EXECUTION_DIGEST, so its calibration rows are proved again)")
        self.assertEqual(sources & set(NOT_SOURCES), set(), "a module is a source or it is not, never both")

    def test_every_declared_source_exists_is_loaded_and_is_not_a_table_entry_for_nothing(self):
        held = set(self.found["held"])
        for rel in fa.PROBE_SOURCES:
            with self.subTest(source=rel):
                self.assertTrue((ROOT / "aisef2" / rel).is_file())
                self.assertIn(module_of(rel), held)
        self.assertEqual(len(set(fa.PROBE_SOURCES)), len(fa.PROBE_SOURCES))
        self.assertEqual(set(NOT_SOURCES) - held, set(), "NOT_SOURCES names a module the probe no longer holds: drop it")

    def test_the_modules_that_decide_a_result_are_sources(self):
        # what an observation becomes (classify_failure, run_probe), the result types and the verdict over an absent
        # subject (outcome), and the invariant-IX name gate run_probe answers InvalidSpec by (contract): the modules
        # whose code turns a spec and the probe's facts into a ProbeResult
        for rel in ("probe/protocol.py", "product/outcome.py", "product/contract.py"):
            self.assertIn(rel, fa.PROBE_SOURCES)
        self.assertEqual(fa.PROBE_SOURCES[-1], "probe/file_artifact.py")     # the module itself, last (dependency order)
        order = [fa.PROBE_SOURCES.index(r) for r in ("product/contract.py", "product/outcome.py", "probe/protocol.py")]
        self.assertEqual(order, sorted(order))                              # each before what imports it

    def test_the_name_gate_decides_a_record_so_a_change_to_it_is_a_change_to_the_bytes_that_run(self):
        # the evidence for the entry above, measured and not argued: with the gate's answer changed, the record of the
        # same spec at the same revision is a different result
        with tempfile.TemporaryDirectory(prefix="aisef2-pm7-gate-") as d:
            ref = RevisionRef("0" * 40, d)
            spec = base.spec("path:tests/test_calc.py")           # a locator that names a developer test artefact
            probe = fa.FileArtifactProbe()
            asked = run_probe(probe, spec, ref, base.ENV)
            with mock.patch("aisef2.probe.protocol.names_test_artefact", return_value=[]):
                answered = run_probe(probe, spec, ref, base.ENV)
        self.assertEqual(type(asked.result).__name__, "InvalidSpec")
        self.assertIn("invariant IX", asked.result.detail)
        self.assertNotEqual(type(answered.result).__name__, "InvalidSpec")

    def test_the_sources_feed_the_digest_in_order_and_the_digest_names_the_bytes_that_run(self):
        self.assertEqual(self.found["digest_before"], fa.EXECUTION_DIGEST)
        self.assertTrue(self.found["digest_changed_by_naming"])        # a name in the tuple changes the hash ...
        # ... and does not import the module named (the tuple names bytes to hash; imports are the interpreter's):
        self.assertFalse(self.found["named_module_loaded_before"])
        self.assertFalse(self.found["named_module_loaded_after"])
        self.assertNotIn("aisef2.app.run", self.found["held"])


class OnlyHashed(unittest.TestCase):
    """PROBE_SOURCES is read in one place and for one thing."""

    def test_its_one_reader_is_the_digest(self):
        tree = ast.parse((ROOT / "aisef2" / "probe" / "file_artifact.py").read_text(encoding="utf-8"))
        readers = []

        class Visit(ast.NodeVisitor):
            def __init__(self):
                self.stack = []

            def visit_FunctionDef(self, node):
                self.stack.append(node.name)
                self.generic_visit(node)
                self.stack.pop()

            def visit_Name(self, node):
                if node.id == "PROBE_SOURCES" and isinstance(node.ctx, ast.Load):
                    readers.append(tuple(self.stack))

        Visit().visit(tree)
        self.assertEqual(readers, [("_probe_digest",)])

    def test_a_probe_with_no_declared_sources_answers_the_same_and_only_its_hash_moves(self):
        with tempfile.TemporaryDirectory(prefix="aisef2-pm7-tree-") as d:
            root = pathlib.Path(d)
            (root / "pkg").mkdir()
            (root / "pkg" / "a.py").write_text("import yaml\n", encoding="utf-8")
            ref = RevisionRef("0" * 40, str(root))
            specs = (base.spec("path:pkg/a.py"), base.spec("path:pkg/none.py"),
                     base.spec("path:pkg", {"matches": 1}, {"imports_outside": {"stdlib": True, "allowed": []}}),
                     base.spec("path:pkg", {"matches": 1}, {"grep": "^import"}))
            asked = [fa.FileArtifactProbe().observe(s, ref, base.ENV) for s in specs]
            digest = fa._probe_digest()
            with mock.patch.object(fa, "PROBE_SOURCES", ()):
                emptied = [fa.FileArtifactProbe().observe(s, ref, base.ENV) for s in specs]
                self.assertNotEqual(fa._probe_digest(), digest)
            self.assertEqual(emptied, asked)
            self.assertEqual(fa._probe_digest(), digest)


if __name__ == "__main__":
    unittest.main()
