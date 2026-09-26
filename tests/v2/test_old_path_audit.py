"""WP-6.3 — the old-path audit on synthetic trees: every direction it fails closed in, every disposition it computes,
every static proof it establishes, on small trees it builds itself (the kill tests of validation/v2/old_path_audit.py).
The real-tree proofs are in test_no_dual_authority.py."""

import ast
import collections
import hashlib
import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load(name, rel):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


opa = _load("aisef_v2_old_path_audit", "validation/v2/old_path_audit.py")

RUNNER = '''"""a runner"""
from aisef2.arch.enums import EventType as T
from aisef2.control import budget
from aisef2.control.owner import classify, FailureCode
from aisef2.orchestrate import gate, seam
from aisef2.orchestrate.merge import merge, reprove
from aisef2.orchestrate.proof import prove
from aisef2.orchestrate.quality import assess
from aisef2.orchestrate.review import review
from aisef2.orchestrate.security import scan
from aisef2.plan.story_admission import admit_story


def run_story(run, plan, story_id, inputs, adapters, policy):
    seam.admit_legacy(inputs.legacy, inputs.migration_table, inputs.declarations)
    _freeze_plan(run, plan)
    return _attempt(run, plan, story_id, inputs, adapters, policy)


def _freeze_plan(run, plan):
    run.append(T.PLAN_FROZEN, {})


def _attempt(run, plan, story_id, inputs, adapters, policy):
    checks = []
    scope = run.story(story_id)
    scratch = scope.acquire(adapters.workspace.scratch("s"))
    impl = scope.acquire(adapters.workspace.checkout("wt", "a" * 40))
    verifier_wt = scope.acquire(adapters.workspace.checkout("v", "a" * 40))
    admission = admit_story(plan, story_id, None, specs=inputs.specs, probes={}, env=inputs.env, committed_stories=frozenset(), sink=None)
    checks.append(gate.check(run, story_id, "admission", admission.admitted, "admitted"))
    implemented = adapters.developer.implement(story_id, (), str(impl.path))
    checks.append(gate.check(run, story_id, "developer", True, implemented.detail))
    candidate = implemented.candidate
    adapters.workspace.move(impl, candidate)
    adapters.workspace.move(verifier_wt, candidate)
    p = prove(run, story_id, "C1", inputs.specs["S"], None, implementer=None, verifier=None, candidate=candidate,
              implementer_root=str(impl.path), verifier_root=str(verifier_wt.path), env=inputs.env, point=None)
    checks.append(gate.check(run, story_id, f"proof:{'C1'}", p.failure is None, "verified"))
    q = assess(run, story_id, str(verifier_wt.path), "", inputs.story_tests, inputs.regression_tests, inputs.deps,
               inputs.runner, policy.tests, interpreter="python", timeout_s=1)
    checks.append(gate.check(run, story_id, "quality", q.failure is None, "ADEQUATE"))
    rv = review(run, story_id, None, adapters.reviewer, ())
    checks.extend(rv.checks)
    sc = scan(run, story_id, None, adapters.scanner, str(scratch.path), timeout_s=1, attempt=1)
    checks.extend(sc.checks)
    m = merge(run, story_id, adapters.merger, candidate)
    checks.append(m.check)
    adapters.workspace.move(impl, m.merge.revision)
    ps, cs = reprove(run, story_id, plan, inputs.specs, merged=m.merge.revision, implementer=None, verifier=None,
                     implementer_root="", verifier_root="", env=inputs.env, committed=frozenset())
    checks.extend(cs)
    decision_seq = gate.decision(run, checks, True)
    charge = budget.charge(run.events, story_id, policy.limits)
    if charge.retry:
        run.retry(story_id, policy.limits)
    run.append(T.STORY_COMMIT, {"story_id": story_id, "revision": m.merge.revision})
    return decision_seq
'''
SEAM = '''"""the seam"""
from aisef2.arch.enums import ObligationRole, Polarity, SubjectAbsence

HUMAN_DECLARATION_REQUIRED = "HUMAN_DECLARATION_REQUIRED"


def resolve(criterion_id, mode, table, declaration):
    row = next((r for r in table["rows"] if r["v1_mode"] == mode), None)
    if row["subject_absence"] == HUMAN_DECLARATION_REQUIRED and not isinstance(declaration, SubjectAbsence):
        raise ValueError(criterion_id)
    return (ObligationRole(row["obligation_role"]), Polarity(row["polarity"]))


def admit_legacy(modes, table, declarations):
    return tuple(resolve(c, m, table, declarations.get(c)) for c, m in sorted(modes.items()))
'''
GATE = '''from aisef2.arch.enums import EventType as T


def check(run, story_id, stage, passed, detail):
    return run.append(T.GATE_CHECK, {"gate": "story", "check": f"{story_id}:{stage}", "passed": bool(passed), "detail": detail}).seq


def decision(run, checks, passed):
    return run.append(T.GATE_DECISION, {"gate": "story", "passed": bool(passed)}, source_seqs=checks).seq
'''
V1_GATE = '''"""V1 gate"""


class StoryGate:
    def run(self):
        return "PASS"


def evaluate(story):
    return "PASS"


def judge_only(story):
    return True


def review_waiver(x):
    return False


def authoritative_baseline(x):
    return x
'''
MIGRATION = '''"""reads V1 as text"""
import ast

HUMAN_DECLARATION_REQUIRED = "HUMAN_DECLARATION_REQUIRED"


def derive(path):
    return {"rows": [], "declared": HUMAN_DECLARATION_REQUIRED, "tree": ast.parse(open(path).read())}
'''
PYPROJECT = '[project]\nname = "aisef"\n\n[project.scripts]\naisef = "aisef.cli:main"\n'
ABSENCE_SNIPPET = (
    "from aisef2.arch.enums import BehaviorVerdict, SubjectAbsence\n\n\n"
    "def on_subject_absent(spec):\n"
    "    return {SubjectAbsence.ABSENCE_IS_DECIDABLE: BehaviorVerdict.REFUTED}[SubjectAbsence(spec.probe_input['subject_absence'])]\n")


def tree(files: dict[str, str]) -> pathlib.Path:
    d = pathlib.Path(tempfile.mkdtemp(prefix="opa-"))
    for rel, text in files.items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return d


def base_files() -> dict[str, str]:
    return {
        "pyproject.toml": PYPROJECT,
        "aisef2/__init__.py": "", "aisef2/orchestrate/__init__.py": "", "aisef2/control/__init__.py": "",
        "aisef2/orchestrate/story_runner.py": RUNNER, "aisef2/orchestrate/seam.py": SEAM, "aisef2/orchestrate/gate.py": GATE,
        "aisef2/control/owner.py": "class FailureCode: pass\n\n\ndef classify(code):\n    return code\n",
        "aisef/__init__.py": "", "aisef/control/__init__.py": "", "aisef/control/gate.py": V1_GATE,
        "aisef/cli/__init__.py": "", "aisef/cli/parser.py": "def main(argv=None):\n    return 0\n",
        "aisef/kit/__init__.py": "", "aisef/kit/util.py": "def helper():\n    return 1\n",
        "validation/v2/gen_migration_table.py": MIGRATION,
        "validation/v2/fold_check.py": "from aisef2.journal.fold import fold\n\n\ndef build(events):\n    return fold(events)\n",
        "aisef2/journal/__init__.py": "", "aisef2/journal/projections/__init__.py": "",
        "aisef2/journal/projections/terminal_state.py": "class TerminalState:\n    def step(self, e):\n        return self\n\n\ndef helper():\n    return 1\n",
        "tests/v2/__init__.py": "",
    }


def line_of(src: str, needle: str) -> int:
    return src.splitlines().index(needle) + 1


class Base(unittest.TestCase):
    def setUp(self):
        self.root = tree(base_files())
        inv = opa.inventory(self.root)
        (self.root / opa.INVENTORY_REL).parent.mkdir(parents=True, exist_ok=True)
        (self.root / opa.INVENTORY_REL).write_text(opa.render(inv), encoding="utf-8")
        self.inv = inv

    def write(self, rel, text):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def problems(self):
        return opa.check(self.root)

    def row(self, rid):
        return next(r for r in opa.inventory(self.root)["rows"] if r["id"] == rid)


class Dispositions(Base):
    def test_the_synthetic_tree_is_fully_classified_and_the_committed_inventory_matches(self):
        self.assertEqual(self.problems(), [])
        s = self.inv["summary"]
        self.assertEqual(s["UNCLASSIFIABLE"], 0)
        self.assertEqual(s["COMPATIBILITY_NONAUTHORITATIVE"], 3)      # seam.resolve, seam.admit_legacy, gen_migration_table.derive
        self.assertGreaterEqual(s["ACTIVE_V2_AUTHORITY"], 4)
        self.assertEqual(s["REMOVED"], 0)
        ids = [r["id"] for r in self.inv["rows"]]
        self.assertEqual(len(ids), len(set(ids)))
        for r in self.inv["rows"]:
            self.assertIn(r["disposition"], opa.DISPOSITIONS, r["id"])
            self.assertTrue(set(r["authority_kind"]) <= set(opa.KINDS), r["id"])
            self.assertEqual(sorted(r), ["authority_kind", "def_digest", "disposition", "evidence", "id", "path", "reachable_from", "replacement", "symbol"]
                             if "def_digest" in r else ["authority_kind", "disposition", "evidence", "id", "path", "reachable_from", "replacement", "symbol"])

    def test_v2_rows_carry_their_capabilities_and_reachability(self):
        r = self.row("aisef2/orchestrate/story_runner.py::_attempt")
        self.assertEqual(r["disposition"], "ACTIVE_V2_AUTHORITY")
        self.assertEqual(r["reachable_from"], ["aisef2/orchestrate/story_runner.py::run_story"])
        for k in ("GATE_DECISION", "RETRY", "BUDGET", "PRODUCT_TRUTH", "ADMISSION", "MERGE_ROLLBACK_COMMIT", "TERMINAL_STATE"):
            self.assertIn(k, r["authority_kind"], k)
        self.assertIn('"calls": [', r["evidence"])
        self.assertIn("aisef2.control.budget.charge", r["evidence"])
        g = self.row("aisef2/orchestrate/gate.py::decision")
        self.assertEqual((g["disposition"], g["authority_kind"]), ("ACTIVE_V2_AUTHORITY", ["GATE_DECISION"]))
        self.assertEqual(sorted(self.row("aisef2/orchestrate/story_runner.py::run_story")["authority_kind"]), ["ADMISSION", "GATE_DECISION", "TERMINAL_STATE"])

    def test_a_module_not_imported_by_run_story_is_v2_but_says_so(self):
        self.write("aisef2/plan/__init__.py", "")
        self.write("aisef2/plan/static_admission.py", "from aisef2.arch.enums import EventType as T\n\n\ndef admit(run, plan):\n    return run.append(T.PLAN_STATIC_ADMITTED, {}).seq\n")
        r = self.row("aisef2/plan/static_admission.py::admit")
        self.assertEqual((r["disposition"], r["authority_kind"]), ("ACTIVE_V2_AUTHORITY", ["ADMISSION"]))
        self.assertEqual(r["reachable_from"], ["V2 plan-level or runtime API (not imported by run_story)"])
        self.assertIn("not reachable", r["evidence"])
        self.assertIn("aisef2/orchestrate/gate.py", opa.reachable_modules(self.root))
        self.assertNotIn("aisef2/plan/static_admission.py", opa.reachable_modules(self.root))

    def test_v1_rows_are_unreachable_with_their_digest_replacement_and_entry(self):
        r = self.row("aisef/control/gate.py::<module>")
        self.assertEqual(r["disposition"], "UNREACHABLE")
        self.assertEqual(r["authority_kind"], ["GATE_DECISION", "PRODUCT_TRUTH"])
        self.assertTrue(r["replacement"].startswith("aisef2/orchestrate/gate.py"))
        self.assertEqual(len(r["def_digest"]), 64)
        self.assertEqual(r["reachable_from"], ["aisef/cli/parser.py::main (the frozen V1 console script; not a V2 entrypoint)"])
        for sym in ("StoryGate", "evaluate", "judge_only", "review_waiver", "authoritative_baseline"):
            s = self.row(f"aisef/control/gate.py::{sym}")
            self.assertEqual(s["disposition"], "UNREACHABLE", sym)
            self.assertTrue(s["evidence"].startswith("resolves in the frozen tree (AST); "))
        e = self.row("pyproject.toml::console_script aisef")
        self.assertEqual((e["disposition"], e["symbol"]), ("UNREACHABLE", "aisef = aisef.cli:main"))
        self.assertNotIn("aisef/kit/util.py::<module>", [r["id"] for r in self.inv["rows"]])   # no control vocabulary: not a candidate

    def test_a_projection_step_is_inventoried_by_its_module_and_a_validation_checker_is_unreachable(self):
        ids = [r["id"] for r in self.inv["rows"]]
        self.assertIn("aisef2/journal/projections/terminal_state.py::TerminalState.step", ids)
        self.assertNotIn("aisef2/journal/projections/terminal_state.py::TerminalState", ids)
        self.assertNotIn("aisef2/journal/projections/terminal_state.py::helper", ids)
        r = self.row("aisef2/journal/projections/terminal_state.py::TerminalState.step")
        self.assertEqual((r["disposition"], r["authority_kind"], r["reachable_from"]),
                         ("ACTIVE_V2_AUTHORITY", ["TERMINAL_STATE"], ["V2 plan-level or runtime API (not imported by run_story)"]))
        self.write("aisef2/journal/projections/__init__.py", "class Init:\n    def step(self, e):\n        return e\n")
        self.write("aisef2/control/story_state.py", "class Elsewhere:\n    def step(self, e):\n        return e\n")
        ids = [r["id"] for r in opa.inventory(self.root)["rows"]]
        self.assertNotIn("aisef2/journal/projections/__init__.py::Init.step", ids)
        self.assertNotIn("aisef2/control/story_state.py::Elsewhere.step", ids)
        real = {r["id"]: r for r in opa.v2_reality(self.root)}
        self.assertEqual(real["validation/v2/fold_check.py::build"]["tree"], "validation")
        self.assertEqual(real["aisef2/orchestrate/gate.py::check"]["tree"], "aisef2")
        self.assertEqual(sorted(real["aisef2/orchestrate/gate.py::check"]),
                         ["authority_kind", "capabilities", "id", "path", "reachable", "symbol", "tree"])
        v = self.row("validation/v2/fold_check.py::build")
        self.assertEqual((v["disposition"], v["authority_kind"], v["reachable_from"]),
                         ("UNREACHABLE", ["EVIDENCE_SELECTION"], ["validation CLI: python -P validation/v2/fold_check.py"]))
        caps = real["aisef2/orchestrate/story_runner.py::_attempt"]["capabilities"]
        self.assertEqual(caps["calls"], sorted(caps["calls"]))
        self.assertEqual(len(caps["calls"]), 10)
        self.assertEqual(caps["events"], ["STORY_COMMIT"])

    def test_every_evidence_string_is_exact(self):
        inv = self.inv
        self.assertEqual((inv["record"], inv["tool"], inv["v2_entry"], inv["v1_entry"], inv["dispositions"], inv["kinds"]),
                         ("AISEF V2 — P6 AUTHORITY INVENTORY (WP-6.3)", "validation/v2/old_path_audit.py",
                          "aisef2/orchestrate/story_runner.py::run_story", "aisef/cli/parser.py::main", opa.DISPOSITIONS, opa.KINDS))
        self.assertEqual([r["id"] for r in inv["rows"]], sorted(r["id"] for r in inv["rows"]))
        self.assertEqual(sorted(inv), ["adapters", "dispositions", "entrypoints", "kinds", "legacy_references", "record", "rows", "summary", "tool", "v1_entry", "v2_entry"])
        self.assertEqual((inv["entrypoints"], inv["legacy_references"], inv["adapters"]), (opa.entrypoints(self.root), [], opa.adapter_conditions(self.root)))
        self.assertTrue(set(opa.V1_SYMBOLS) <= set(opa.V1_MODULES))   # every named V1 symbol's module has its row
        g = self.row("aisef2/orchestrate/gate.py::decision")
        self.assertEqual((g["evidence"], g["replacement"], g["reachable_from"]),
                         ('AST: {"calls": [], "events": ["GATE_DECISION"], "types": []}; import graph from run_story: reachable', None,
                          ["aisef2/orchestrate/story_runner.py::run_story"]))
        m = self.row("aisef/control/gate.py::<module>")
        self.assertEqual(m["evidence"], f"def_digest {m['def_digest']} over 6 definitions; no runtime module of aisef2 or validation/v2 "
                                        "imports aisef (import graph); poisoned at runtime by tests/v2/test_no_dual_authority.py")
        self.assertEqual(m["replacement"], "aisef2/orchestrate/gate.py + story_runner._attempt (gate rows and the cited decision)")
        j = self.row("aisef/control/gate.py::judge_only")
        self.assertEqual((j["evidence"], j["replacement"], j["authority_kind"]),
                         ("resolves in the frozen tree (AST); unreachable from V2 (import graph); poisoned at runtime", m["replacement"],
                          ["GATE_DECISION", "PRODUCT_TRUTH"]))
        e = self.row("pyproject.toml::console_script aisef")
        self.assertEqual((e["evidence"], e["replacement"], e["reachable_from"], e["authority_kind"]),
                         ('pyproject scripts {"aisef": "aisef.cli:main"}; the V2 tree never imports aisef',
                          "none: V2 has no console script in cycle 1; run_story is the supported V2 entrypoint",
                          ["the operating system: the installed V1 console script"], ["GATE_DECISION", "ADMISSION", "TERMINAL_STATE"]))
        a = self.row("aisef2/orchestrate/seam.py::admit_legacy")
        self.assertEqual((a["evidence"], a["replacement"], a["authority_kind"]), (
            'adapter conditions: {"before_the_first_event": true, "constructs_only_v2_inputs": true, "exists": true, "imports_v1": [], '
            '"refuses_human_declaration_required": true, "touches_engineering_quality": false}', None, ["ADMISSION"]))
        v = self.row("validation/v2/fold_check.py::build")
        self.assertEqual((v["evidence"], v["replacement"]), ('AST: {"calls": ["aisef2.journal.fold.fold"], "events": [], "types": []}; never imported by aisef2 (import graph)', None))
        self.write("aisef2/orchestrate/story_runner.py", RUNNER.replace(
            "    seam.admit_legacy(inputs.legacy, inputs.migration_table, inputs.declarations)\n    _freeze_plan(run, plan)\n",
            "    _freeze_plan(run, plan)\n    seam.admit_legacy(inputs.legacy, inputs.migration_table, inputs.declarations)\n"))
        u = self.row("aisef2/orchestrate/seam.py::admit_legacy")
        self.assertEqual((u["disposition"], u["reachable_from"]), ("UNCLASSIFIABLE", []))
        self.assertTrue(u["evidence"].startswith('adapter conditions violated: {"before_the_first_event": false, '), u["evidence"])
        self.write("aisef2/orchestrate/story_runner.py", "import aisef.control.gate\n" + RUNNER)
        rows = opa.inventory(self.root)["rows"]
        v1 = [r for r in rows if r["path"].startswith("aisef/")]
        self.assertTrue(v1 and all(r["disposition"] == "UNCLASSIFIABLE" for r in v1))   # V1 reachable again: nothing of it is classifiable
        self.assertEqual(self.row("pyproject.toml::console_script aisef")["disposition"], "UNREACHABLE")

    def test_v1_rows_carry_sorted_vocabulary_and_nothing_else(self):
        self.write("aisef/kit/mixed.py", "".join(f"def {n}():\n    pass\n\n\n" for n in ("zz_verdict", "nn_proof", "aa_gate", "mm_budget", "bb_retry", "cc_ledger", "plain")))
        rows = {r["id"]: r for r in opa.v1_reality(self.root)}
        r = rows["aisef/kit/mixed.py::<module>"]
        self.assertEqual(r["vocabulary"], ["aa_gate", "bb_retry", "cc_ledger", "mm_budget", "nn_proof", "zz_verdict"])
        self.assertEqual((r["definitions"], sorted(r)), (7, ["def_digest", "definitions", "id", "path", "symbol", "vocabulary"]))
        self.assertNotIn("aisef/kit/util.py::<module>", rows)
        self.assertEqual(rows["aisef/control/gate.py::judge_only"],
                         {"id": "aisef/control/gate.py::judge_only", "path": "aisef/control/gate.py", "symbol": "judge_only", "resolves": True})

    def test_entrypoints_read_the_scripts_table_only(self):
        self.assertEqual(opa.entrypoints(self.root), {"console_scripts": {"aisef": "aisef.cli:main"}, "v1_console_script": "aisef.cli:main", "v2_console_script": False})
        self.write("pyproject.toml", '[project]\nname = "aisef"\nversion = "1"\n\n[project.scripts]\naisef = "aisef.cli:main"\naisef2 = "aisef2.cli:main"\n\n[tool.x]\nother = "a.b:c"\n')
        self.assertEqual(opa.entrypoints(self.root), {"console_scripts": {"aisef": "aisef.cli:main", "aisef2": "aisef2.cli:main"},
                                                      "v1_console_script": "aisef.cli:main", "v2_console_script": True})
        self.write("pyproject.toml", '[project]\nname = "aisef"\n\n[project.scripts]\nzeta = "z.cli:main"\naisef = "aisef.cli:main"\n')
        e = self.row("pyproject.toml::console_script aisef")
        self.assertEqual((e["disposition"], e["evidence"]), ("UNREACHABLE", 'pyproject scripts {"aisef": "aisef.cli:main", "zeta": "z.cli:main"}; the V2 tree never imports aisef'))
        self.write("pyproject.toml", '[project]\nname = "aisef"\n')
        self.assertEqual(opa.entrypoints(self.root), {"console_scripts": {}, "v1_console_script": None, "v2_console_script": False})
        self.assertEqual(opa.entrypoints(tree({})), {"console_scripts": {}, "v1_console_script": None, "v2_console_script": False})

    def test_a_named_v1_symbol_that_is_gone_is_REMOVED_and_a_missing_module_row_is_unclassifiable(self):
        self.write("aisef/control/gate.py", V1_GATE.replace("def judge_only(story):", "def judge_none(story):"))
        gone = self.row("aisef/control/gate.py::judge_only")
        self.assertEqual((gone["disposition"], gone["evidence"]), ("REMOVED", "no longer defined; unreachable from V2 (import graph); poisoned at runtime"))
        problems = self.problems()
        self.assertIn("DISPOSITION moved: aisef/control/gate.py::judge_only is REMOVED in the tree, UNREACHABLE in the inventory", problems)
        self.assertIn("REMOVED without the inventory saying so: aisef/control/gate.py::judge_only", problems)
        self.assertTrue(opa.proofs(self.root)["NO_OLD_GATE_AUTHORITY"]["static"])   # a removed old authority is no authority
        (self.root / opa.INVENTORY_REL).write_text(opa.render(opa.inventory(self.root)), encoding="utf-8")
        self.assertEqual(self.problems(), [])                                        # the inventory now says REMOVED
        self.write("aisef/kit/verdicts.py", "class Verdict:\n    pass\n")
        inv = opa.inventory(self.root)
        bad = [r for r in inv["rows"] if r["disposition"] not in opa.DISPOSITIONS]
        self.assertEqual([(r["id"], r["disposition"]) for r in bad], [("aisef/kit/verdicts.py::<module>", "UNCLASSIFIABLE")])
        self.assertEqual(inv["summary"]["UNCLASSIFIABLE"], 1)
        self.assertEqual((bad[0]["evidence"], bad[0]["authority_kind"], bad[0]["replacement"], bad[0]["reachable_from"]),
                         ("a module of the V1 tree with control vocabulary ['Verdict'] has no row in V1_MODULES", [], None,
                          ["aisef/cli/parser.py::main (the frozen V1 console script; not a V2 entrypoint)"]))
        self.assertIn("UNCLASSIFIABLE: aisef/kit/verdicts.py::<module>: a module of the V1 tree with control vocabulary ['Verdict'] has no row in V1_MODULES",
                      self.problems())
        self.assertFalse(opa.proofs(self.root)["NO_OLD_GATE_AUTHORITY"]["static"])

    def test_the_adapters_are_compatibility_nonauthoritative_under_their_measured_conditions(self):
        r = self.row("aisef2/orchestrate/seam.py::admit_legacy")
        self.assertEqual(r["disposition"], "COMPATIBILITY_NONAUTHORITATIVE")
        self.assertEqual(r["reachable_from"], ["aisef2/orchestrate/story_runner.py::run_story (before its first event)"])
        cond = opa.adapter_conditions(self.root)
        self.assertEqual(cond["aisef2/orchestrate/seam.py"], {"exists": True, "imports_v1": [], "constructs_only_v2_inputs": True,
                                                              "touches_engineering_quality": False,
                                                              "refuses_human_declaration_required": True, "before_the_first_event": True})
        self.assertEqual(cond["validation/v2/gen_migration_table.py"], {"exists": True, "imports_v1": [], "constructs_only_v2_inputs": True,
                                                                          "touches_engineering_quality": False,
                                                                          "emits_human_declaration_required": True, "reads_v1_as_text_only": True})
        self.assertEqual(self.row("validation/v2/gen_migration_table.py::derive")["disposition"], "COMPATIBILITY_NONAUTHORITATIVE")

    def test_adapter_conditions_are_measured_one_by_one(self):
        seam, gen = "aisef2/orchestrate/seam.py", "validation/v2/gen_migration_table.py"
        header = "from aisef2.arch.enums import ObligationRole, Polarity, SubjectAbsence"
        for only in ("ObligationRole", "Polarity", "SubjectAbsence"):
            self.write(seam, SEAM.replace(header, f"from aisef2.arch.enums import {only}"))
            self.assertTrue(opa.adapter_conditions(self.root)[seam]["constructs_only_v2_inputs"], only)
        self.write(seam, SEAM.replace(header + "\n", ""))
        self.assertFalse(opa.adapter_conditions(self.root)[seam]["constructs_only_v2_inputs"])
        self.assertEqual(self.row(f"{seam}::admit_legacy")["disposition"], "UNCLASSIFIABLE")
        self.write(seam, SEAM)
        self.write(gen, "import aisef\n" + MIGRATION)
        cond = opa.adapter_conditions(self.root)[gen]
        self.assertEqual((cond["imports_v1"], cond["reads_v1_as_text_only"]), ([(1, "aisef")], False))
        self.assertEqual(self.row(f"{gen}::derive")["disposition"], "UNCLASSIFIABLE")
        self.assertIn("ADAPTER touches V1: validation/v2/gen_migration_table.py imports [(1, 'aisef')]", self.problems())
        self.write(gen, MIGRATION.replace("ast.parse(open(path).read())", "ast.parse(path)"))
        self.assertTrue(opa.adapter_conditions(self.root)[gen]["reads_v1_as_text_only"])
        self.write(gen, MIGRATION.replace('"tree": ast.parse(open(path).read())', '"tree": None'))
        self.assertFalse(opa.adapter_conditions(self.root)[gen]["reads_v1_as_text_only"])
        self.assertEqual(self.row(f"{gen}::derive")["disposition"], "UNCLASSIFIABLE")
        self.write(gen, MIGRATION)
        self.assertEqual(opa.adapter_conditions(tree({k: v for k, v in base_files().items() if k != seam}))[seam], {"exists": False})

    def test_the_seam_ordering_is_measured_against_every_kind_of_first_write(self):
        seam_call = "    seam.admit_legacy(inputs.legacy, inputs.migration_table, inputs.declarations)\n"
        self.assertIs(opa._seam_before_first_event(self.root), True)
        self.write("aisef2/orchestrate/story_runner.py", RUNNER.replace("def run_story(", "def go("))
        self.assertIs(opa._seam_before_first_event(self.root), False)
        self.write("aisef2/orchestrate/story_runner.py", RUNNER.replace(seam_call, "    plan = dict(plan)\n"))
        self.assertIs(opa._seam_before_first_event(self.root), False)          # no seam call at all
        self.write("aisef2/orchestrate/story_runner.py", RUNNER.replace(seam_call + "    _freeze_plan(run, plan)\n",
                                                                        "    run.append(T.PLAN_FROZEN, {})\n" + seam_call))
        self.assertIs(opa._seam_before_first_event(self.root), False)          # a journal append precedes the seam
        self.write("aisef2/orchestrate/story_runner.py", RUNNER.replace(seam_call + "    _freeze_plan(run, plan)\n    return _attempt(run, plan, story_id, inputs, adapters, policy)\n",
                                                                        "    r = _attempt(run, plan, story_id, inputs, adapters, policy)\n" + seam_call + "    return r\n"))
        self.assertIs(opa._seam_before_first_event(self.root), False)          # the attempt precedes the seam
        self.write("aisef2/orchestrate/story_runner.py", RUNNER.replace(seam_call + "    _freeze_plan(run, plan)\n",
                                                                        "    plan = dict(plan)\n" + seam_call + "    _freeze_plan(run, plan)\n"))
        self.assertIs(opa._seam_before_first_event(self.root), True)           # a non-writing call before the seam is fine

    def test_render_is_indented_utf8_json_ending_in_a_newline(self):
        self.assertEqual(opa.render({"rows": [{"evidence": "é — ü"}]}), '{\n "rows": [\n  {\n   "evidence": "é — ü"\n  }\n ]\n}\n')
        self.assertEqual(json.loads(opa.render(self.inv))["rows"], self.inv["rows"])

    def test_the_inventory_digest_is_a_sha256_over_the_rows(self):
        d = opa.inventory_digest(self.inv)
        self.assertEqual(d, hashlib.sha256(json.dumps(self.inv["rows"], sort_keys=True, ensure_ascii=False).encode()).hexdigest())
        self.assertEqual(d, opa.audit(self.root)["committed_digest"])
        other = {"rows": self.inv["rows"][1:]}
        self.assertNotEqual(opa.inventory_digest(other), d)
        self.assertEqual(len(d), 64)
        self.assertEqual(opa.inventory_digest({"rows": [{"evidence": "é — ü"}]}), hashlib.sha256('[{"evidence": "é — ü"}]'.encode()).hexdigest())

    def test_a_seam_that_runs_after_the_first_event_or_names_quality_or_forgets_the_refusal_is_unclassifiable(self):
        self.write("aisef2/orchestrate/story_runner.py", RUNNER.replace(
            "    seam.admit_legacy(inputs.legacy, inputs.migration_table, inputs.declarations)\n    _freeze_plan(run, plan)\n",
            "    _freeze_plan(run, plan)\n    seam.admit_legacy(inputs.legacy, inputs.migration_table, inputs.declarations)\n"))
        self.assertFalse(opa.adapter_conditions(self.root)["aisef2/orchestrate/seam.py"]["before_the_first_event"])
        self.assertEqual(self.row("aisef2/orchestrate/seam.py::admit_legacy")["disposition"], "UNCLASSIFIABLE")
        self.write("aisef2/orchestrate/story_runner.py", RUNNER)
        self.write("aisef2/orchestrate/seam.py", SEAM.replace("HUMAN_DECLARATION_REQUIRED = \"HUMAN_DECLARATION_REQUIRED\"", "HUMAN_DECLARATION_REQUIRED = \"HDR\""))
        self.assertEqual(self.row("aisef2/orchestrate/seam.py::admit_legacy")["disposition"], "UNCLASSIFIABLE")
        self.write("aisef2/orchestrate/seam.py", SEAM + "from aisef2.quality.test_execution import DeveloperTests\n")
        self.assertEqual(self.row("aisef2/orchestrate/seam.py::admit_legacy")["disposition"], "UNCLASSIFIABLE")


class FailsClosed(Base):
    def test_an_unenumerated_authority_fails_the_audit(self):
        self.write("aisef2/orchestrate/side_gate.py", "from aisef2.arch.enums import EventType as T\n\n\ndef decide(run):\n    return run.append(T.GATE_DECISION, {}).seq\n")
        self.assertIn("UNENUMERATED authority: aisef2/orchestrate/side_gate.py::decide (ACTIVE_V2_AUTHORITY) is in the tree and not in the inventory",
                      self.problems())
        self.write("aisef/control/machine_gate.py", "def check_all():\n    return True\n")
        self.assertIn("UNENUMERATED authority: aisef/control/machine_gate.py::<module> (UNREACHABLE) is in the tree and not in the inventory",
                      self.problems())

    def test_problems_come_in_id_order_within_each_kind(self):
        names = ("zeta", "alpha", "mid", "beta", "omega", "gamma")
        for n in names:
            self.write(f"aisef2/orchestrate/{n}_gate.py", "from aisef2.arch.enums import EventType as T\n\n\ndef decide(run):\n    return run.append(T.GATE_DECISION, {}).seq\n")
        inv = json.loads((self.root / opa.INVENTORY_REL).read_text(encoding="utf-8"))
        for n in names:
            inv["rows"].append({"id": f"aisef2/orchestrate/{n}_ghost.py::decide", "path": f"aisef2/orchestrate/{n}_ghost.py", "symbol": "decide",
                                "authority_kind": ["GATE_DECISION"], "reachable_from": [], "disposition": "ACTIVE_V2_AUTHORITY", "replacement": None, "evidence": "x"})
        moved = [r for r in inv["rows"] if r["path"] == "aisef/control/gate.py"]
        self.assertEqual(len(moved), 6)
        for r in moved:
            r["disposition"] = "HISTORICAL_ONLY"
        (self.root / opa.INVENTORY_REL).write_text(opa.render(inv), encoding="utf-8")
        problems = self.problems()
        unenumerated = [x for x in problems if x.startswith("UNENUMERATED")]
        stale = [x for x in problems if x.startswith("STALE")]
        moved_msgs = [x for x in problems if x.startswith("DISPOSITION moved")]
        self.assertEqual(unenumerated, [f"UNENUMERATED authority: aisef2/orchestrate/{n}_gate.py::decide (ACTIVE_V2_AUTHORITY) is in the tree and not in the inventory" for n in sorted(names)])
        self.assertEqual(stale, [f"STALE inventory row: aisef2/orchestrate/{n}_ghost.py::decide no longer resolves to an authority in the tree" for n in sorted(names)])
        self.assertEqual(moved_msgs, sorted(moved_msgs))
        self.assertEqual(len(moved_msgs), 6)
        self.assertEqual(problems[:6], unenumerated)
        self.assertEqual(problems[6:12], stale)

    def test_a_stale_inventory_row_fails_the_audit(self):
        inv = json.loads((self.root / opa.INVENTORY_REL).read_text(encoding="utf-8"))
        inv["rows"].append({"id": "aisef2/orchestrate/ghost.py::decide", "path": "aisef2/orchestrate/ghost.py", "symbol": "decide",
                            "authority_kind": ["GATE_DECISION"], "reachable_from": [], "disposition": "ACTIVE_V2_AUTHORITY",
                            "replacement": None, "evidence": "invented"})
        (self.root / opa.INVENTORY_REL).write_text(opa.render(inv), encoding="utf-8")
        self.assertEqual(self.problems(), ["STALE inventory row: aisef2/orchestrate/ghost.py::decide no longer resolves to an authority in the tree"])

    def test_a_moved_disposition_a_changed_kind_and_a_changed_shape_fail_the_audit(self):
        inv = json.loads((self.root / opa.INVENTORY_REL).read_text(encoding="utf-8"))
        row = next(r for r in inv["rows"] if r["id"] == "aisef/control/gate.py::<module>")
        row["disposition"] = "HISTORICAL_ONLY"
        (self.root / opa.INVENTORY_REL).write_text(opa.render(inv), encoding="utf-8")
        self.assertIn("DISPOSITION moved: aisef/control/gate.py::<module> is UNREACHABLE in the tree, HISTORICAL_ONLY in the inventory",
                      self.problems())
        row["disposition"] = "UNREACHABLE"
        row["authority_kind"] = ["BUDGET"]
        (self.root / opa.INVENTORY_REL).write_text(opa.render(inv), encoding="utf-8")
        self.assertIn("KIND changed: aisef/control/gate.py::<module>", self.problems())
        row["authority_kind"] = ["GATE_DECISION", "PRODUCT_TRUTH"]
        (self.root / opa.INVENTORY_REL).write_text(opa.render(inv), encoding="utf-8")
        self.assertEqual(self.problems(), [])
        self.write("aisef/control/gate.py", V1_GATE + "\n\ndef new_gate(x):\n    return x\n")
        self.assertEqual(self.problems(), ["SHAPE changed: aisef/control/gate.py::<module> def_digest differs from the inventory"])

    def test_a_missing_inventory_fails(self):
        self.root = tree(base_files())   # a tree that never had an inventory
        self.write("aisef/control/gate.py", V1_GATE.replace("def judge_only(story):", "def judge_none(story):"))   # a REMOVED row, unenumerated
        problems = self.problems()
        self.assertIn("UNENUMERATED authority: aisef/control/gate.py::judge_only (REMOVED) is in the tree and not in the inventory", problems)
        self.assertFalse(any(p.startswith("REMOVED without") for p in problems))
        a = opa.audit(self.root)
        self.assertEqual((a["committed_digest"], a["inventory_digest"], a["problems"]), (None, opa.inventory_digest(a["inventory"]), problems))
        self.assertEqual(sorted(a), ["committed_digest", "inventory", "inventory_digest", "problems", "proofs"])
        self.assertEqual(a["proofs"], opa.proofs(self.root, a["inventory"]))
        self.assertIn(f"{opa.INVENTORY_REL} is missing: generate it", problems)
        self.assertTrue(all(p.startswith("UNENUMERATED") or p.endswith("generate it") for p in problems))

    def test_dual_authority_fails_even_when_both_paths_agree(self):
        self.write("aisef2/orchestrate/twin.py",
                   "from aisef.control.gate import judge_only\nfrom aisef2.control.owner import classify\n\n\n"
                   "def decide(story):\n    legacy = judge_only(story)\n    mine = classify(story)\n    return legacy and mine\n")
        problems = self.problems()
        self.assertIn("LEGACY_IMPORT: aisef2/orchestrate/twin.py:1 aisef.control.gate — an old authority is reachable again", problems)
        self.assertIn("DUAL_AUTHORITY: aisef2/orchestrate/twin.py:5 decide names ['judge_only'] — an old authority is reachable again", problems)
        self.assertIn("PROOF NO_OLD_GATE_AUTHORITY does not hold statically", " ".join(problems))
        self.assertTrue(any(p.startswith("UNCLASSIFIABLE: aisef/control/gate.py::<module>") for p in problems))   # V1 reachable again

    def test_a_legacy_fallback_fails(self):
        self.write("aisef2/orchestrate/fallback.py",
                   "import aisef.control.gate as legacy\n\n\ndef decide(story, v2):\n    try:\n        return v2(story)\n"
                   "    except Exception:\n        return legacy.evaluate(story)\n\n\n"
                   "def decide2(story, v2_unknown, legacy_result=None):\n    if v2_unknown:\n        return legacy.judge_only(story)\n    return 1\n")
        problems = self.problems()
        self.assertIn("LEGACY_FALLBACK: aisef2/orchestrate/fallback.py:4 decide names ['legacy'] — an old authority is reachable again", problems)
        self.assertIn("LEGACY_FALLBACK: aisef2/orchestrate/fallback.py:11 decide2 names ['legacy'] — an old authority is reachable again", problems)
        refs = opa.legacy_references(self.root)
        self.assertEqual([r["kind"] for r in refs], ["LEGACY_IMPORT", "LEGACY_FALLBACK", "LEGACY_FALLBACK"])

    def test_a_plain_legacy_reference_and_an_adapter_touching_v1_fail(self):
        self.write("validation/v2/gen_migration_table.py", "import aisef.control.gate as g\n\n\ndef derive(path):\n    return g.evaluate(path)\n")
        problems = self.problems()
        self.assertIn("LEGACY_REFERENCE: validation/v2/gen_migration_table.py:4 derive names ['g'] — an old authority is reachable again", problems)
        self.assertIn("ADAPTER touches V1: validation/v2/gen_migration_table.py imports [(1, 'aisef.control.gate')]", problems)
        self.assertTrue(any(p.startswith("UNCLASSIFIABLE: validation/v2/gen_migration_table.py::derive") for p in problems))

    def test_legacy_reference_kinds_are_exact(self):
        self.write("aisef2/orchestrate/side.py",
                   "import aisef\nfrom aisef.control.gate import evaluate as v1_eval, judge_only as v1_judge, review_waiver as v1_waiver, StoryGate as V1Gate\n"
                   "from aisef.control import gate as v1_gate\n\n\n"
                   "def plain(x):\n    try:\n        y = int(x)\n    except ValueError:\n        y = 0\n    if y:\n        return y\n    return aisef.control.gate.evaluate(x)\n\n\n"
                   "def fallback(x):\n    try:\n        return int(x)\n    except ValueError:\n        return v1_eval(x)\n\n\n"
                   "def branch(x):\n    if x is None:\n        return v1_judge(x)\n    return 1\n\n\n"
                   "def many(x):\n    return (v1_eval, v1_judge, v1_waiver, V1Gate, v1_gate, aisef)\n")
        refs = opa.legacy_references(self.root)
        self.assertEqual({r["detail"]: r["kind"] for r in refs if r["kind"] != "LEGACY_IMPORT"},
                         {"plain names ['aisef']": "LEGACY_REFERENCE", "fallback names ['v1_eval']": "LEGACY_FALLBACK",
                          "branch names ['v1_judge']": "LEGACY_FALLBACK",
                          "many names ['V1Gate', 'aisef', 'v1_eval', 'v1_gate', 'v1_judge', 'v1_waiver']": "LEGACY_REFERENCE"})
        self.assertEqual([(r["line"], r["detail"]) for r in refs if r["kind"] == "LEGACY_IMPORT"], [(1, "aisef"), (2, "aisef.control.gate"), (3, "aisef.control")])
        self.assertEqual([r["line"] for r in refs if r["kind"] != "LEGACY_IMPORT"], [6, 16, 23, 29])
        self.assertIn("LEGACY_REFERENCE: aisef2/orchestrate/side.py:6 plain names ['aisef'] — an old authority is reachable again", self.problems())

    def test_a_test_module_importing_v1_is_historical_only_and_must_be_enumerated(self):
        self.write("tests/v2/test_old.py", "import aisef.control.gate\n")
        problems = self.problems()
        self.assertEqual(problems, ["UNENUMERATED authority: tests/v2/test_old.py::<import aisef.control.gate> (HISTORICAL_ONLY) is in the tree and not in the inventory"])
        (self.root / opa.INVENTORY_REL).write_text(opa.render(opa.inventory(self.root)), encoding="utf-8")
        self.assertEqual(self.problems(), [])
        r = self.row("tests/v2/test_old.py::<import aisef.control.gate>")
        self.assertEqual((r["disposition"], r["authority_kind"], r["reachable_from"]), ("HISTORICAL_ONLY", [], ["a test module only"]))
        self.assertEqual((r["evidence"], r["replacement"], r["symbol"]),
                         ("line 1: a historical reproducer of a V1 defect; the test tree is not a runtime authority path", None, "<import aisef.control.gate>"))
        self.assertTrue(opa.proofs(self.root)["NO_OLD_GATE_AUTHORITY"]["static"])   # a historical reproducer is no authority
        self.write("aisef2/orchestrate/story_runner.py", "import aisef.control.gate\n" + RUNNER)   # a runtime import is never historical
        self.assertEqual(opa.test_legacy_imports(self.root), [{"path": "tests/v2/test_old.py", "line": 1, "module": "aisef.control.gate"}])
        self.assertEqual([r["id"] for r in opa.inventory(self.root)["rows"] if r["disposition"] == "HISTORICAL_ONLY"],
                         ["tests/v2/test_old.py::<import aisef.control.gate>"])

    def test_a_v2_console_script_or_a_moved_v1_script_is_unclassifiable(self):
        self.write("pyproject.toml", PYPROJECT + 'aisef2 = "aisef2.cli:main"\n')
        e = self.row("pyproject.toml::console_script aisef")
        self.assertEqual(e["disposition"], "UNCLASSIFIABLE")
        self.write("pyproject.toml", PYPROJECT.replace("aisef.cli:main", "aisef.cli.parser:main"))
        self.assertEqual(self.row("pyproject.toml::console_script aisef")["disposition"], "UNCLASSIFIABLE")


class StaticProofs(Base):
    def test_all_six_hold_on_the_synthetic_tree(self):
        pr = opa.proofs(self.root)
        self.assertEqual(list(pr), list(opa.PROOFS))
        self.assertEqual({k: v["static"] for k, v in pr.items()}, {k: True for k in opa.PROOFS})
        self.assertEqual({k: v["runtime"] for k, v in pr.items()}, {
            "NO_OLD_GATE_AUTHORITY": "tests/v2/test_no_dual_authority.py::Poisoned (every V1 family raises; real ORCH fixtures unchanged)",
            "NO_DEVELOPER_TEST_PRODUCT_AUTHORITY": "tests/v2/test_no_dual_authority.py::DeveloperTestsNeverDecide",
            "NO_PARENT_DEVELOPER_EXECUTION": "tests/v2/test_no_dual_authority.py::NothingExecutesAtTheParent",
            "NO_RECENCY_EVIDENCE_SELECTION": "tests/v2/test_no_dual_authority.py::OnlyExplicitReferencesSelectEvidence",
            "NO_SIDE_RETRY_COUNTER": "tests/v2/test_no_dual_authority.py::RetryStateIsTheJournal",
            "ALL_CONTROL_DECISIONS_JOURNAL_BACKED": "tests/v2/test_no_dual_authority.py::EveryDecisionIsJournalBacked (decision -> source-seq table)"})
        self.assertEqual({k: sorted(v) for k, v in pr.items()}, {
            "NO_OLD_GATE_AUTHORITY": ["legacy_references_in_runtime", "runtime", "static", "v1_rows"],
            "NO_DEVELOPER_TEST_PRODUCT_AUTHORITY": ["flows", "kernel_rules", "runtime", "static"],
            "NO_PARENT_DEVELOPER_EXECUTION": ["kernel_rules", "runtime", "sites", "static"],
            "NO_RECENCY_EVIDENCE_SELECTION": ["runtime", "sites", "static"],
            "NO_SIDE_RETRY_COUNTER": ["kernel_rules", "runtime", "static"],
            "ALL_CONTROL_DECISIONS_JOURNAL_BACKED": ["runtime", "sites", "static"]})
        self.assertEqual(pr["NO_OLD_GATE_AUTHORITY"]["v1_rows"], 1 + sum(1 for r in self.inv["rows"] if r["path"].startswith("aisef/")))
        self.assertEqual(pr["NO_OLD_GATE_AUTHORITY"]["legacy_references_in_runtime"], [])
        self.assertEqual((pr["NO_DEVELOPER_TEST_PRODUCT_AUTHORITY"]["flows"], pr["NO_DEVELOPER_TEST_PRODUCT_AUTHORITY"]["kernel_rules"]), ([], []))
        self.assertEqual((pr["NO_PARENT_DEVELOPER_EXECUTION"]["sites"], pr["NO_RECENCY_EVIDENCE_SELECTION"]["sites"],
                          pr["NO_SIDE_RETRY_COUNTER"]["kernel_rules"], pr["ALL_CONTROL_DECISIONS_JOURNAL_BACKED"]["sites"]), ([], [], [], []))

    def test_R2_a_quality_result_flowing_into_a_product_call_is_a_flow(self):
        self.write("aisef2/orchestrate/story_runner.py", RUNNER.replace(
            "    rv = review(run, story_id, None, adapters.reviewer, ())",
            "    p2 = prove(run, story_id, 'C1', q, None, implementer=None, verifier=None, candidate=candidate, implementer_root='', verifier_root='', env=inputs.env, point=None)\n"
            "    rv = review(run, story_id, None, adapters.reviewer, ())"))
        flows = opa.developer_test_flows(self.root)
        self.assertEqual(len(flows), 1)
        self.assertIn("_attempt: engineering-quality result ['q'] flows into aisef2.orchestrate.proof.prove", flows[0])
        src = RUNNER.replace(
            "    rv = review(run, story_id, None, adapters.reviewer, ())",
            "    q2 = assess(run, story_id, '', '', (), (), (), None, policy.tests, interpreter='python', timeout_s=1)\n"
            "    q3 = assess(run, story_id, '', '', (), (), (), None, policy.tests, interpreter='python', timeout_s=1)\n"
            "    q4 = assess(run, story_id, '', '', (), (), (), None, policy.tests, interpreter='python', timeout_s=1)\n"
            "    p2 = prove(run, story_id, 'C1', inputs.specs['S'], None, implementer=q3, verifier=q, candidate=candidate, implementer_root=q2, verifier_root=q4, env=inputs.env, point=None)\n"
            "    rv = review(run, story_id, None, adapters.reviewer, ())")
        self.write("aisef2/orchestrate/story_runner.py", src)
        ln = line_of(src, "    p2 = prove(run, story_id, 'C1', inputs.specs['S'], None, implementer=q3, verifier=q, candidate=candidate, implementer_root=q2, verifier_root=q4, env=inputs.env, point=None)")
        self.assertEqual(opa.developer_test_flows(self.root),
                         [f"aisef2/orchestrate/story_runner.py:{ln} _attempt: engineering-quality result ['q', 'q2', 'q3', 'q4'] flows into aisef2.orchestrate.proof.prove"])
        self.assertFalse(opa.proofs(self.root)["NO_DEVELOPER_TEST_PRODUCT_AUTHORITY"]["static"])
        self.write("aisef2/quality/__init__.py", "")
        self.write("aisef2/quality/adequacy.py", "def assemble(x):\n    return BehaviorVerdict\n")
        self.assertIn("aisef2/quality/adequacy.py:2 engineering-quality code names 'BehaviorVerdict'", opa.developer_test_flows(self.root))

    def test_R3_assess_before_the_move_or_admission_with_tests_or_a_seam_naming_quality_is_a_site(self):
        self.assertEqual(opa.parent_execution_sites(self.root), [])
        self.write("aisef2/orchestrate/story_runner.py", RUNNER.replace(
            "    adapters.workspace.move(verifier_wt, candidate)\n", "").replace(
            "    checks.append(gate.check(run, story_id, \"quality\", q.failure is None, \"ADEQUATE\"))\n",
            "    checks.append(gate.check(run, story_id, \"quality\", q.failure is None, \"ADEQUATE\"))\n    adapters.workspace.move(verifier_wt, candidate)\n"))
        self.assertEqual(opa.parent_execution_sites(self.root), ["story_runner._attempt: assess must follow the verifier checkout's move to the candidate"])
        admit = "    admission = admit_story(plan, story_id, None, specs=inputs.specs, probes={}, env=inputs.env, committed_stories=frozenset(), sink=None)"
        for variant in ("admit_story(plan, story_id, None, specs=inputs.specs, probes={}, env=inputs.env, committed_stories=frozenset(), sink=inputs.story_tests)",
                        "admit_story(plan, story_id, inputs.deps, specs=inputs.specs, probes={}, env=inputs.env, committed_stories=frozenset(), sink=None)",
                        "admit_story(plan, story_id, runner, specs=inputs.specs, probes={}, env=inputs.env, committed_stories=frozenset(), sink=None)",
                        "admit_story(plan, story_id, None, specs=inputs.specs, probes={}, env=inputs.env, committed_stories=frozenset(), sink=regression_tests)"):
            src = RUNNER.replace(admit, "    admission = " + variant)
            self.write("aisef2/orchestrate/story_runner.py", src)
            self.assertEqual(opa.parent_execution_sites(self.root),
                             [f"story_runner._attempt:{line_of(src, '    admission = ' + variant)} admission receives developer-test input"], variant)
        self.write("aisef2/orchestrate/story_runner.py", RUNNER.replace("    adapters.workspace.move(verifier_wt, candidate)\n", "    adapters.workspace.touch(verifier_wt, candidate)\n"))
        self.assertEqual(opa.parent_execution_sites(self.root), ["story_runner._attempt: assess must follow the verifier checkout's move to the candidate"])
        self.write("aisef2/orchestrate/story_runner.py", RUNNER)
        self.write("aisef2/orchestrate/seam.py", SEAM + "\n\ndef red(t):\n    return TestExecution\n")
        self.assertEqual(opa.parent_execution_sites(self.root), ["aisef2/orchestrate/seam.py:19 the seam names 'TestExecution'"])
        self.assertFalse(opa.proofs(self.root)["NO_PARENT_DEVELOPER_EXECUTION"]["static"])

    def test_R4_time_file_order_recency_keys_and_HEAD_are_sites_and_the_writers_may_stamp_time(self):
        self.assertEqual(opa.recency_sites(self.root), [])
        for src in ("import datetime\n", "import glob\n", "import os, glob\n", "from datetime import datetime\n", "from glob import glob\n", "from time import time\n"):
            self.write("aisef2/control/latest.py", src)
            self.assertEqual(opa.recency_sites(self.root), ["aisef2/control/latest.py:1 a control module imports wall-clock time or directory listing"], src)
        self.write("aisef2/control/latest.py", "def pick(events):\n    return min(events, key=lambda e: e['time'])\n")
        self.assertEqual(opa.recency_sites(self.root), ["aisef2/control/latest.py:2 orders by a recency key",
                                                        "aisef2/control/latest.py:2 reads an event's wall-clock time: recorded, never folded"])
        self.write("aisef2/control/latest.py", "import os\n\n\ndef pick(events, seqs):\n    return sorted(events, key=len) + [max(seqs, key=int)] + os.sep\n")
        self.assertEqual(opa.recency_sites(self.root), [])
        self.write("aisef2/control/latest.py", "import time\n\n\ndef pick(events):\n    return max(events, key=lambda e: e.time)\n")
        self.assertEqual(opa.recency_sites(self.root), [
            "aisef2/control/latest.py:1 a control module imports wall-clock time or directory listing",
            "aisef2/control/latest.py:5 orders by a recency key",
            "aisef2/control/latest.py:5 reads an event's wall-clock time: recorded, never folded"])
        self.write("aisef2/control/latest.py", "import pathlib\n\n\ndef pick(d):\n    return sorted(pathlib.Path(d).iterdir(), key=lambda p: p.stat().st_mtime)[-1]\n")
        sites = opa.recency_sites(self.root)
        self.assertIn("aisef2/control/latest.py:5 reads iterdir: file time or directory order is never evidence", sites)
        self.assertIn("aisef2/control/latest.py:5 reads st_mtime: file time or directory order is never evidence", sites)
        self.assertIn("aisef2/control/latest.py:5 orders by a recency key", sites)
        self.write("aisef2/control/latest.py", "def tip(git):\n    return git('rev-parse', 'HEAD')\n")
        self.assertEqual(opa.recency_sites(self.root), ["aisef2/control/latest.py:2 names HEAD: a control module holds full SHAs only"])
        self.write("aisef2/journal/__init__.py", "")
        self.write("aisef2/journal/writer.py", "import time as _time\n\n\ndef stamp():\n    return _time.time()\n")
        self.assertEqual(opa.recency_sites(self.root), ["aisef2/control/latest.py:2 names HEAD: a control module holds full SHAs only"])
        self.write("aisef2/journal/fold.py", "def newest(events):\n    return events[-1].time\n")
        self.assertIn("aisef2/journal/fold.py:2 reads an event's wall-clock time: recorded, never folded", opa.recency_sites(self.root))
        self.assertFalse(opa.proofs(self.root)["NO_RECENCY_EVIDENCE_SELECTION"]["static"])

    def test_R6_a_row_before_its_stage_a_second_decision_an_uncited_row_or_a_retry_before_the_charge_is_a_site(self):
        self.assertEqual(opa.journal_backing(self.root), [])
        self.write("aisef2/orchestrate/story_runner.py", RUNNER.replace("f\"proof:{'C1'}\"", 'f"proof:{story_id}"'))
        self.assertEqual(opa.journal_backing(self.root), [])   # an f-string label that unparses with single quotes
        src = RUNNER.replace(
            "    checks.append(gate.check(run, story_id, \"quality\", q.failure is None, \"ADEQUATE\"))\n", "").replace(
            "    rv = review(run, story_id, None, adapters.reviewer, ())",
            "    checks.append(gate.check(run, story_id, \"security\", True, \"early\"))\n    rv = review(run, story_id, None, adapters.reviewer, ())")
        self.write("aisef2/orchestrate/story_runner.py", src)
        ln = line_of(src, '    checks.append(gate.check(run, story_id, "security", True, "early"))')
        self.assertEqual(opa.journal_backing(self.root), [f"_attempt:{ln} gate row 'security' precedes its stage's typed call scan"])
        src = RUNNER.replace('    checks.append(gate.check(run, story_id, "developer", True, implemented.detail))\n',
                             '    gate.check(run, story_id, "developer", True, implemented.detail)\n')
        self.write("aisef2/orchestrate/story_runner.py", src)
        ln = line_of(src, '    gate.check(run, story_id, "developer", True, implemented.detail)')
        self.assertEqual(opa.journal_backing(self.root), [f"_attempt:{ln} a gate row is written and not collected into the decision"])
        self.write("aisef2/orchestrate/story_runner.py", RUNNER.replace("def _attempt(", "def _go("))
        self.assertEqual(opa.journal_backing(self.root), ["aisef2/orchestrate/story_runner.py::_attempt is missing"])
        self.assertEqual(opa.parent_execution_sites(self.root), ["aisef2/orchestrate/story_runner.py::_attempt is missing"])
        self.write("aisef2/orchestrate/story_runner.py", RUNNER.replace(
            "    decision_seq = gate.decision(run, checks, True)\n", "    decision_seq = gate.decision(run, checks, True)\n    gate.decision(run, checks, False)\n"))
        self.assertIn("_attempt: 2 gate decisions; exactly one is made per attempt", opa.journal_backing(self.root))
        self.write("aisef2/orchestrate/story_runner.py", RUNNER.replace("gate.decision(run, checks, True)", "gate.decision(run, [], True)"))
        self.assertIn("_attempt: the decision does not cite the collected checks", opa.journal_backing(self.root))
        self.write("aisef2/orchestrate/story_runner.py", RUNNER.replace(
            "    charge = budget.charge(run.events, story_id, policy.limits)\n    if charge.retry:\n        run.retry(story_id, policy.limits)\n",
            "    run.retry(story_id, policy.limits)\n    charge = budget.charge(run.events, story_id, policy.limits)\n"))
        self.assertIn("_attempt: a retry is decided by budget.charge over the journal before run.retry", opa.journal_backing(self.root))
        src = RUNNER.replace("gate.check(run, story_id, \"quality\"", "gate.check(run, story_id, \"vibes\"")
        self.write("aisef2/orchestrate/story_runner.py", src)
        ln = line_of(src, '    checks.append(gate.check(run, story_id, "vibes", q.failure is None, "ADEQUATE"))')
        self.assertEqual(opa.journal_backing(self.root), [f"_attempt:{ln} gate row 'vibes' has no stage evidence rule"])
        self.assertFalse(opa.proofs(self.root)["ALL_CONTROL_DECISIONS_JOURNAL_BACKED"]["static"])

    def test_every_kernel_rule_the_audit_relies_on_is_run(self):
        self.write("aisef2/control/raw.py", "def f(x):\n    return BehaviorVerdict\n")
        self.write("aisef2/control/res.py", "def f(p):\n    return p.result\n")
        self.write("aisef2/control/absent.py", ABSENCE_SNIPPET)
        self.write("aisef2/quality/__init__.py", "")
        self.write("aisef2/quality/at_parent.py", "def f(parent_rev):\n    return parent_rev\n")
        self.write("aisef2/orchestrate/side.py", "import aisef.control.gate\n")
        self.write("aisef2/control/counter.py", "def more(retry_count):\n    retry_count += 1\n    return retry_count\n")
        self.write("aisef2/control/taxo.py", "def f(g):\n    return g(retryable=True)\n")
        verdict, parent, retry = opa._kernel_rules(self.root)
        self.assertEqual({v.split()[0] for v in verdict}, {"NO_RAW_VERDICT_ROUTING", "RESULT_ONLY_THROUGH_BINDING", "NO_VERDICT_FROM_ABSENCE_DECLARATION"})
        self.assertEqual({v.split()[0] for v in parent}, {"CANDIDATE_ONLY_EXECUTION", "NO_DEVELOPER_ARTEFACT_AT_PARENT"})
        self.assertEqual({v.split()[0] for v in retry}, {"NO_SIDE_RETRY_COUNTER", "RETRYABLE_ONLY_IN_TAXONOMY"})

    def test_R1_and_R5_rely_on_the_kernel_rules_and_the_legacy_scan(self):
        self.write("aisef2/control/counter.py", "def more(retry_count):\n    retry_count += 1\n    return retry_count\n")
        pr = opa.proofs(self.root)
        self.assertFalse(pr["NO_SIDE_RETRY_COUNTER"]["static"])
        self.assertTrue(any("NO_SIDE_RETRY_COUNTER" in s for s in pr["NO_SIDE_RETRY_COUNTER"]["kernel_rules"]))
        self.write("aisef2/control/counter.py", "def more(x):\n    return x\n")
        self.write("aisef2/orchestrate/story_runner.py", "import aisef.control.gate\n" + RUNNER)
        pr = opa.proofs(self.root)
        self.assertFalse(pr["NO_OLD_GATE_AUTHORITY"]["static"])
        self.assertEqual(pr["NO_OLD_GATE_AUTHORITY"]["legacy_references_in_runtime"],
                         [{"path": "aisef2/orchestrate/story_runner.py", "line": 1, "kind": "LEGACY_IMPORT", "detail": "aisef.control.gate"}])
        prefix = ('PROOF NO_OLD_GATE_AUTHORITY does not hold statically: {"legacy_references_in_runtime": [{"detail": "aisef.control.gate", '
                  '"kind": "LEGACY_IMPORT", "line": 1, "path": "aisef2/orchestrate/story_runner.py"}], "v1_rows": ')
        self.assertTrue(any(p.startswith(prefix) for p in opa.check(self.root)), opa.check(self.root))


class Helpers(unittest.TestCase):
    """The AST helpers, each pinned where the tree-level cases cannot see a mutant."""

    def test_module_names_and_import_resolution(self):
        self.assertEqual(opa._module_name("aisef2/orchestrate/__init__.py"), "aisef2.orchestrate")
        self.assertEqual(opa._module_name("aisef2/orchestrate/gate.py"), "aisef2.orchestrate.gate")
        tree = ast.parse("import json\nimport os.path\nimport os.path as osp\nfrom aisef2.arch import enums as en\n")
        self.assertEqual(opa._imports(tree, "aisef2/x.py"), {"json": "json", "os": "os", "osp": "os.path", "en": "aisef2.arch.enums"})
        rel = ast.parse("from . import gate\nfrom .gate import check as gcheck\nfrom ..control import budget\n")
        self.assertEqual(opa._imports(rel, "aisef2/orchestrate/seam.py"),
                         {"gate": "aisef2.orchestrate.gate", "gcheck": "aisef2.orchestrate.gate.check", "budget": "aisef2.control.budget"})
        self.assertEqual(opa._imports(ast.parse("from . import gate\nfrom .gate import check\n"), "aisef2/orchestrate/__init__.py"),
                         {"gate": "aisef2.orchestrate.gate", "check": "aisef2.orchestrate.gate.check"})

    def test_qualification_definitions_and_digests(self):
        imports = {"gate": "aisef2.orchestrate.gate", "T": "aisef2.arch.enums.EventType"}
        self.assertEqual(opa._qualify("gate.check", imports, "aisef2/x.py", set()), "aisef2.orchestrate.gate.check")
        self.assertEqual(opa._qualify("gate", imports, "aisef2/x.py", set()), "aisef2.orchestrate.gate")
        self.assertEqual(opa._qualify("helper", {}, "aisef2/x.py", {"helper"}), "aisef2.x.helper")
        self.assertEqual(opa._qualify("helper.inner", {}, "aisef2/x.py", {"helper"}), "aisef2.x.helper.inner")
        self.assertEqual(opa._qualify("other.y", {}, "aisef2/x.py", {"helper"}), "other.y")
        tree = ast.parse("def f():\n    pass\n\n\nasync def af():\n    pass\n\n\nclass C:\n    x = 1\n\n    def m(self):\n        pass\n\n    async def am(self):\n        pass\n")
        self.assertEqual([n for n, _ in opa._defs(tree)], ["f", "af", "C", "C.m", "C.am"])
        self.assertEqual(opa._dotted(ast.parse("a.b.c").body[0].value), "a.b.c")
        self.assertIsNone(opa._dotted(ast.parse("a().b").body[0].value))
        a, b = ast.parse("def b():\n    pass\n\n\ndef a():\n    pass\n"), ast.parse("def a():\n    pass\n\n\ndef b():\n    pass\n")
        self.assertEqual(opa.def_digest(a), opa.def_digest(b))
        self.assertEqual(opa.def_digest(a), hashlib.sha256(b"a\nb").hexdigest())

    def test_py_files_are_sorted_unique_without_pycache_and_accept_a_file(self):
        root = tree({f"{p}/{c}.py": "" for p in ("zz", "aa") for c in "abcdefghijklm"} | {"aa/__pycache__/x.py": "", "single.py": ""})
        files = opa._py_files(root, ("zz/", "aa/", "single.py", "aa/"))
        self.assertEqual(files, sorted(files))
        self.assertEqual((len(files), len(set(files)), files[0], files[-1]), (27, 27, "aa/a.py", "zz/m.py"))
        self.assertNotIn("aa/__pycache__/x.py", files)
        self.assertIn("single.py", files)

    def test_legacy_imports_name_the_bare_package_and_its_modules(self):
        tree = ast.parse("import aisef\nfrom aisef import x\nimport aisef.control.gate as g\nfrom aisef.control import gate\nimport aisefx\nfrom aisefx import y\nimport json\n")
        self.assertEqual(sorted(opa.legacy_imports(tree)), [(1, "aisef"), (2, "aisef"), (3, "aisef.control.gate"), (4, "aisef.control")])

    def test_capabilities_see_both_spellings_of_the_event_enum(self):
        src = ("from aisef2.arch.enums import EventType\nfrom aisef2.arch.enums import EventType as T\nfrom aisef2.orchestrate import gate\n"
               "from aisef2.control.budget import Charge\n\n\ndef f(run, other):\n    run.append(EventType.GATE_DECISION, {})\n"
               "    run.append(T.STORY_COMMIT, {})\n    run.append(other.STORY_RETRY, {})\n    gate.check(run, 's', 'x', True, '')\n    return Charge(1)\n")
        tree = ast.parse(src)
        self.assertEqual(opa._capabilities(tree.body[-1], opa._imports(tree, "aisef2/x.py"), "aisef2/x.py", {"f"}),
                         {"events": {"GATE_DECISION", "STORY_COMMIT"}, "calls": {"aisef2.orchestrate.gate.check"}, "types": {"aisef2.control.budget.Charge"}})


class DecisionTable(unittest.TestCase):
    def test_a_synthetic_journal_gives_the_exact_table(self):
        E = collections.namedtuple("E", "seq type data source_seqs")
        s1 = {"story_id": "S1"}
        events = [E(1, "run/begin", {}, ()), E(2, "story/begin", s1, ()), E(3, "probe/evaluated", s1, ()),
                  E(4, "story/admitted", s1, (3,)), E(5, "gate/check", {"check": "S1:admission"}, ()),
                  E(6, "provider/result", s1, (5,)), E(7, "gate/check", {"check": "S1:developer"}, ()),
                  E(8, "probe/evaluated", s1, ()), E(9, "proof/verified", s1, (8,)),
                  E(10, "gate/check", {"check": "S1:proof:C1"}, ()), E(11, "tests/adequacy", s1, ()),
                  E(12, "gate/check", {"check": "S1:quality"}, ()), E(13, "gate/decision", {}, (12, 5, 10, 7)),
                  E(14, "failure/observed", s1, ()), E(15, "story/rollback", s1, (14,)), E(16, "story/retry", s1, (15,)),
                  E(17, "story/end", s1, ()),
                  E(18, "story/begin", s1, ()), E(19, "gate/check", {"check": "S1:admission"}, ()),
                  E(20, "gate/check", {"check": "resources"}, ()), E(21, "gate/decision", {}, (19, 20)),
                  E(22, "story/commit", s1, ()), E(23, "story/end", s1, ()),
                  E(24, "story/begin", {"story_id": "S2"}, ()), E(25, "story/rollback", {"story_id": "S2"}, ()),
                  E(26, "story/end", {"story_id": "S2"}, ())]
        table = opa.decision_table(events)
        row = lambda seq, decision, story, check, facts: {"seq": seq, "decision": decision, "story_id": story, "check": check, "facts": facts}  # noqa: E731
        self.assertEqual(table, [
            row(4, "story/admitted", "S1", None, [3]), row(5, "gate/check", "S1", "S1:admission", [4]),
            row(6, "provider/result", "S1", None, [5]), row(7, "gate/check", "S1", "S1:developer", [6]),
            row(9, "proof/verified", "S1", None, [8]), row(10, "gate/check", "S1", "S1:proof:C1", [9]),
            row(11, "tests/adequacy", "S1", None, [4]), row(12, "gate/check", "S1", "S1:quality", [11]),
            row(13, "gate/decision", None, None, [5, 7, 10, 12]), row(14, "failure/observed", "S1", None, [13]),
            row(15, "story/rollback", "S1", None, [14]), row(16, "story/retry", "S1", None, [15]),
            row(17, "story/end", "S1", None, [16]),
            row(19, "gate/check", "S1", "S1:admission", []), row(20, "gate/check", "resources", "resources", []),
            row(21, "gate/decision", None, None, [19, 20]), row(22, "story/commit", "S1", None, [21]),
            row(23, "story/end", "S1", None, [22]),
            row(25, "story/rollback", "S2", None, []), row(26, "story/end", "S2", None, [25])])
        self.assertEqual(opa.decision_problems(table),
                         ["gate/check at seq 19 rests on no journal fact", "gate/check at seq 20 rests on no journal fact",
                          "story/rollback at seq 25 rests on no journal fact"])
        self.assertEqual(opa.decision_problems([row(5, "gate/check", "S1", "S1:admission", [5, "4"])]),
                         ["gate/check at seq 5 cites 5, which is not before it", "gate/check at seq 5 cites 4, which is not before it"])

    def test_the_table_maps_every_decision_to_journal_facts_that_precede_it(self):
        from tests.v2 import test_p6_orchestration as e2e
        case = e2e.Orchestration("test_ORCH_1_an_end_to_end_story_completes_through_the_real_path")
        case.setUp()
        try:
            r = case.story(case.s1_plan(), "S1", case.s1_dev())
            self.assertTrue(r.committed)
            table = opa.decision_table(list(case.run.events))
        finally:
            case.doCleanups()
        kinds = [t["decision"] for t in table]
        for k in ("story/admitted", "provider/result", "proof/verified", "tests/adequacy", "gate/check", "gate/decision", "story/commit", "story/end"):
            self.assertIn(k, kinds, k)
        for t in table:
            self.assertTrue(t["facts"], t)
            self.assertTrue(all(f < t["seq"] for f in t["facts"]), t)
            self.assertTrue(all(isinstance(f, int) for f in t["facts"]), t)
        decision = next(t for t in table if t["decision"] == "gate/decision")
        rows = [t for t in table if t["decision"] == "gate/check"]
        self.assertEqual(sorted(decision["facts"]), sorted(t["seq"] for t in rows))
        self.assertEqual(opa.decision_problems(table), [])
        broken = [dict(t, facts=[t["seq"] + 1]) if t["decision"] == "gate/decision" else t for t in table]
        self.assertEqual(opa.decision_problems(broken), [f"gate/decision at seq {decision['seq']} cites {decision['seq'] + 1}, which is not before it"])
        self.assertIn("gate/check at seq", opa.decision_problems([dict(t, facts=[]) if t["decision"] == "gate/check" else t for t in table])[0])


if __name__ == "__main__":
    unittest.main()
