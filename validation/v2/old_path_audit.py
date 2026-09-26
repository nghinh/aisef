"""WP-6.3 — the authority inventory, the no-dual-authority audit and the six removal proofs (owner authorization
"AISEF V2 — WP-6.3 EXECUTION AUTHORIZATION / OLD-PATH REMOVAL / NO DUAL AUTHORITY / P6 CLOSURE").

An *authority* is a path that can affect product truth, admission, a gate/block/retry decision, a failure owner,
retryability, budget consumption, a story's terminal state, evidence selection, merge/rollback/commit or
qualification. This module enumerates every candidate authority in `aisef/` (the frozen V1 tree), `aisef2/` (V2),
`validation/v2/` (checkers and evidence builders) and the command entrypoints, mechanically:

* V2: by AST, a function is control-capable when it appends a control event, calls a control function of the kernel
  (resolved through its imports, never by bare name), constructs a control result type, or is a control-critical
  projection's `step`. Reachability is the import graph from the supported V2 entrypoint,
  `aisef2/orchestrate/story_runner.py::run_story`.
* V1: every module of the V1 control plane (`aisef/control/`, `aisef/phases/`, `aisef/cli/`) is a row carrying a digest
  of its top-level definitions, and the gate / judge / decision symbols that once decided PASS, BLOCK, RETRY, FAIL,
  COMPLETE or product truth are rows of their own that must still resolve; any other module of `aisef/` that defines
  a control-vocabulary symbol is a candidate the inventory must name. Their reachability is the import graph: no
  runtime module of `aisef2/` or `validation/v2/` may import `aisef` — the poison tests prove it at runtime.
* Adapters: `aisef2/orchestrate/seam.py` and `validation/v2/gen_migration_table.py` are COMPATIBILITY_NONAUTHORITATIVE
  only while they import nothing of V1, construct only V2 inputs, and (the seam) run before the story's first event.

Every row is one of the closed dispositions ACTIVE_V2_AUTHORITY, COMPATIBILITY_NONAUTHORITATIVE, HISTORICAL_ONLY,
REMOVED, UNREACHABLE; a candidate that cannot be classified fails the audit, closed. `--check` compares the
committed inventory with reality in both directions: an authority reality holds that the inventory does not,
an inventory row that no longer resolves, a disposition that no longer matches, an old authority reachable again, an
adapter that touches V1, a function that draws on both V2 and a legacy authority (dual authority — agreement is no
excuse), a legacy fallback. The six proof results are exact booleans; the runtime halves (poisoning, the
adversarial developer-test, parent-execution, recency and side-counter cases, the decision → source-seq table) are
measured by tests/v2/test_no_dual_authority.py and bound by the P6-OLD-PATH-REMOVAL record.

    python -P validation/v2/old_path_audit.py --generate   # write closure-evidence/v2/P6-AUTHORITY-INVENTORY.json
    python -P validation/v2/old_path_audit.py --check      # compare inventory and reality, both directions
"""

from __future__ import annotations

import ast
import hashlib
import json
import pathlib
import re
import sys
from typing import Iterable

ROOT = pathlib.Path(__file__).resolve().parents[2]
INVENTORY_REL = "closure-evidence/v2/P6-AUTHORITY-INVENTORY.json"

KINDS = ("PRODUCT_TRUTH", "ADMISSION", "GATE_DECISION", "RETRY", "FAILURE_OWNER", "RETRYABILITY", "BUDGET",
         "TERMINAL_STATE", "EVIDENCE_SELECTION", "MERGE_ROLLBACK_COMMIT", "QUALIFICATION")
DISPOSITIONS = ("ACTIVE_V2_AUTHORITY", "COMPATIBILITY_NONAUTHORITATIVE", "HISTORICAL_ONLY", "REMOVED", "UNREACHABLE")
PROOFS = ("NO_OLD_GATE_AUTHORITY", "NO_DEVELOPER_TEST_PRODUCT_AUTHORITY", "NO_PARENT_DEVELOPER_EXECUTION",
          "NO_RECENCY_EVIDENCE_SELECTION", "NO_SIDE_RETRY_COUNTER", "ALL_CONTROL_DECISIONS_JOURNAL_BACKED")

V2_ENTRY = ("aisef2/orchestrate/story_runner.py", "run_story")
V1_ENTRY = ("aisef/cli/parser.py", "main")          # the console script `aisef = aisef.cli:main` (pyproject)
V2_RUNTIME = ("aisef2/",)                            # the trees that may never import V1
V2_CHECKERS = ("validation/v2/",)
V1_TREE = "aisef/"
V1_CONTROL_PLANE = ("aisef/control/", "aisef/phases/", "aisef/cli/")
#: a symbol elsewhere in aisef/ that carries control vocabulary is a candidate authority the inventory must name
V1_VOCABULARY = re.compile(r"gate|judge|verdict|decid|qualif|budget|retry|ledger|journal|outcome|proof|approv|block",
                           re.IGNORECASE)
ADAPTERS = ("aisef2/orchestrate/seam.py", "validation/v2/gen_migration_table.py")

#: V1 modules by kind and replacement. Every module of the control plane is here (a module without a row fails
#: closed); the replacement names the V2 authority that decides the same fact now.
V1_MODULES: dict[str, tuple[tuple[str, ...], str]] = {
    "aisef/control/gate.py": (("GATE_DECISION", "PRODUCT_TRUTH"), "aisef2/orchestrate/gate.py + story_runner._attempt (gate rows and the cited decision)"),
    "aisef/control/machine_gate.py": (("GATE_DECISION", "ADMISSION"), "aisef2/plan/static_admission.py"),
    "aisef/control/obligation.py": (("PRODUCT_TRUTH",), "aisef2/product/outcome.py + aisef2/control/routing.py (through the seam's migration table only)"),
    "aisef/control/qualification.py": (("QUALIFICATION", "RETRY", "TERMINAL_STATE"), "aisef2/journal/projections/qualification_counters.py + aisef2/plan/drift.py"),
    "aisef/control/budget.py": (("BUDGET", "RETRY"), "aisef2/control/budget.py + aisef2/journal/projections/budgets.py"),
    "aisef/control/journal.py": (("EVIDENCE_SELECTION", "TERMINAL_STATE"), "aisef2/journal (format 3, seq-cited)"),
    "aisef/control/state.py": (("TERMINAL_STATE",), "aisef2/journal/projections/story_state.py"),
    "aisef/control/ledger.py": (("EVIDENCE_SELECTION",), "aisef2/journal (the journal is the ledger)"),
    "aisef/control/closure.py": (("GATE_DECISION", "QUALIFICATION"), "none in cycle 1: closure is QP-7 (not authorized)"),
    "aisef/control/reviewer_qual.py": (("GATE_DECISION", "QUALIFICATION"), "aisef2/orchestrate/review.py"),
    "aisef/control/preflight.py": (("ADMISSION",), "aisef2/plan/static_admission.py + aisef2/plan/story_admission.py"),
    "aisef/control/approvals.py": (("ADMISSION",), "aisef2/product/approval.py"),
    "aisef/control/proof.py": (("PRODUCT_TRUTH",), "aisef2/probe/protocol.py + aisef2/orchestrate/proof.py"),
    "aisef/control/outcome.py": (("GATE_DECISION",), "aisef2/product/outcome.py"),
    "aisef/control/tdd.py": (("PRODUCT_TRUTH", "ADMISSION"), "none: RED-at-parent is not V2 semantics (invariant IX)"),
    "aisef/control/acceptance.py": (("ADMISSION", "QUALIFICATION"), "aisef2/product/compiler.py"),
    "aisef/control/scheduler.py": (("TERMINAL_STATE",), "aisef2/plan/obligation.py (story graph)"),
    "aisef/control/worktree.py": (("MERGE_ROLLBACK_COMMIT",), "aisef2/orchestrate/workspace.py"),
    "aisef/control/findings.py": (("GATE_DECISION",), "aisef2/orchestrate/adapters.py::Finding"),
    "aisef/control/security.py": (("GATE_DECISION",), "aisef2/orchestrate/security.py"),
    "aisef/control/attribution.py": (("FAILURE_OWNER",), "aisef2/control/owner.py"),
    "aisef/control/defects.py": (("GATE_DECISION",), "aisef2/control/owner.py (typed taxonomy)"),
    "aisef/control/impact.py": (("ADMISSION",), "aisef2/plan/story_admission.py"),
    "aisef/control/cohort.py": (("QUALIFICATION",), "aisef2/journal/projections/qualification_counters.py"),
    "aisef/control/complexity.py": (("ADMISSION",), "aisef2/plan/obligation.py"),
    "aisef/control/normalize.py": (("ADMISSION", "PRODUCT_TRUTH"), "aisef2/product/contract.py + validation/v2/gen_migration_table.py (reads it as text)"),
    "aisef/control/identity.py": (("EVIDENCE_SELECTION",), "aisef2/runtime/runspec.py"),
    "aisef/control/planes.py": (("EVIDENCE_SELECTION",), "aisef2/runtime/runspec.py"),
    "aisef/control/replay.py": (("EVIDENCE_SELECTION",), "aisef2/journal (replay is the fold)"),
    "aisef/control/replay_manifest.py": (("EVIDENCE_SELECTION",), "aisef2/runtime/runspec.py"),
    "aisef/control/conformance.py": (("GATE_DECISION",), "validation/v2/freeze_conformance.py"),
    "aisef/control/invariants.py": (("GATE_DECISION",), "aisef2/invariants/registry.py"),
    "aisef/control/change.py": (("ADMISSION",), "aisef2/plan/drift.py"),
    "aisef/control/design_contract.py": (("ADMISSION",), "none: no design plane in cycle 1"),
    "aisef/control/experience.py": (("ADMISSION",), "none: no experience plane in cycle 1"),
    "aisef/control/onboarding.py": (("ADMISSION",), "none: no onboarding in cycle 1"),
    "aisef/control/bmad_status.py": (("TERMINAL_STATE",), "none: no BMAD in cycle 1"),
    "aisef/phases/implement.py": (("GATE_DECISION", "RETRY", "MERGE_ROLLBACK_COMMIT", "PRODUCT_TRUTH"), "aisef2/orchestrate/story_runner.py"),
    "aisef/phases/run.py": (("TERMINAL_STATE", "QUALIFICATION", "BUDGET"), "aisef2/orchestrate/story_runner.py + aisef2/runtime/run_scope.py"),
    "aisef/phases/qa.py": (("GATE_DECISION",), "aisef2/orchestrate/quality.py"),
    "aisef/phases/improve.py": (("GATE_DECISION", "RETRY"), "aisef2/orchestrate/story_runner.py"),
    "aisef/phases/deploy.py": (("GATE_DECISION",), "none in cycle 1: pre-deploy is QP-7"),
    "aisef/phases/plan.py": (("ADMISSION",), "aisef2/plan/obligation.py + static_admission.py"),
    "aisef/phases/story_split.py": (("ADMISSION",), "aisef2/plan/obligation.py"),
    "aisef/phases/mockup.py": (("ADMISSION",), "none: no mockup plane in cycle 1"),
    "aisef/phases/report.py": (("EVIDENCE_SELECTION",), "validation/v2 evidence records"),
    "aisef/cli/parser.py": (("GATE_DECISION", "ADMISSION", "TERMINAL_STATE"), "none: V2 has no console script in cycle 1"),
    "aisef/cli/implement.py": (("GATE_DECISION", "RETRY", "MERGE_ROLLBACK_COMMIT"), "aisef2/orchestrate/story_runner.py"),
    "aisef/cli/plan.py": (("ADMISSION",), "aisef2/plan"),
    "aisef/cli/closure.py": (("GATE_DECISION",), "none in cycle 1: closure is QP-7"),
    "aisef/cli/doctor.py": (("ADMISSION",), "aisef2/runtime/capability.py"),
    "aisef/cli/harness.py": (("PRODUCT_TRUTH",), "aisef2/probe"),
    "aisef/cli/dashboard.py": (("EVIDENCE_SELECTION",), "validation/v2 evidence records"),
    "aisef/cli/memory.py": (("EVIDENCE_SELECTION",), "none: no memory plane in cycle 1"),
    "aisef/cli/_common.py": (("TERMINAL_STATE",), "aisef2/runtime/run_scope.py"),
    "aisef/cli/__init__.py": (("GATE_DECISION",), "none: V2 has no console script in cycle 1"),
    "aisef/cli/__main__.py": (("GATE_DECISION",), "none: V2 has no console script in cycle 1"),
    "aisef/control/__init__.py": ((), ""),
    "aisef/phases/__init__.py": ((), ""),
    "aisef/harness/guardrails.py": (("GATE_DECISION",), "aisef2/orchestrate/adapters.py (typed findings) + review/security stages"),
    "aisef/harness/mockup_verify.py": (("GATE_DECISION",), "none: no mockup plane in cycle 1"),
    "aisef/harness/observe.py": (("PRODUCT_TRUTH",), "aisef2/probe/protocol.py"),
    "aisef/harness/testlog.py": (("EVIDENCE_SELECTION",), "aisef2/quality/test_execution.py (typed result set)"),
    "aisef/harness/verify_image.py": (("GATE_DECISION",), "none: no mockup plane in cycle 1"),
    "aisef/harness/capabilities.py": (("ADMISSION",), "aisef2/runtime/capability.py"),
    "aisef/harness/ownership.py": (("MERGE_ROLLBACK_COMMIT",), "aisef2/runtime/story_scope.py"),
    "aisef/harness/process_owner.py": (("TERMINAL_STATE",), "aisef2/runtime/process_range.py"),
    "aisef/harness/routing.py": (("ADMISSION",), "aisef2/runtime/capability.py"),
    "aisef/harness/tools.py": (("GATE_DECISION",), "aisef2/runtime/tool.py"),
    "aisef/harness/sandbox.py": (("MERGE_ROLLBACK_COMMIT",), "aisef2/orchestrate/adapters.py::confine"),
    "aisef/harness/runlog.py": (("EVIDENCE_SELECTION",), "aisef2/journal"),
    "aisef/harness/context.py": (("ADMISSION",), "none"),
    "aisef/harness/prompts.py": (("ADMISSION",), "none"),
    "aisef/harness/server_identity.py": (("EVIDENCE_SELECTION",), "aisef2/runtime/runspec.py"),
    "aisef/harness/aria.py": (("PRODUCT_TRUTH",), "none: no browser probe in cycle 1"),
    "aisef/harness/browser.py": (("PRODUCT_TRUTH",), "none: no browser probe in cycle 1"),
    "aisef/harness/mockup_map.py": (("ADMISSION",), "none: no mockup plane in cycle 1"),
    "aisef/memory.py": (("EVIDENCE_SELECTION",), "none: no memory plane in cycle 1"),
    "aisef/memory_bench.py": (("EVIDENCE_SELECTION",), "none"),
    "aisef/config.py": (("ADMISSION", "BUDGET"), "aisef2/orchestrate/story_runner.py::Policy"),
    "aisef/_compat.py": ((), ""),
    "aisef/clients/base.py": (("RETRY", "BUDGET"), "aisef2/orchestrate/adapters.py (typed capability protocols)"),
    "aisef/clients/stream.py": (("RETRY",), "aisef2/orchestrate/adapters.py"),
    "aisef/kit/registry.py": (("ADMISSION",), "none"),
    "aisef/kit/security_filter.py": (("GATE_DECISION",), "aisef2/orchestrate/security.py (typed scanner findings)"),
    "aisef/kit/skill_scan.py": (("GATE_DECISION",), "none: no skill plane in cycle 1"),
    "aisef/clients/compile.py": (("GATE_DECISION",), "aisef2/orchestrate/adapters.py (typed developer answer)"),
    "aisef/clients/synthetic.py": (("GATE_DECISION", "BUDGET"), "aisef2/orchestrate/adapters.py (typed capability protocols)"),
    "aisef/codebase/__init__.py": ((), ""),
}
#: the former gate / judge / decision symbols (R1): each must still resolve, each is poisoned at runtime
V1_SYMBOLS: dict[str, tuple[str, ...]] = {
    "aisef/control/gate.py": ("StoryGate", "evaluate", "judge_only", "review_waiver", "authoritative_baseline"),
    "aisef/control/machine_gate.py": ("check_all", "check_stories", "check_prd", "GateResult"),
    "aisef/control/obligation.py": ("judge", "evaluate", "blocking", "row"),
    "aisef/control/qualification.py": ("qualify", "_qualify_run", "_qualify_repair", "_qualify_pre_deploy", "Verdict", "Decision"),
    "aisef/control/budget.py": ("BudgetGuard", "BudgetLedger", "BudgetExceeded"),
    "aisef/control/reviewer_qual.py": ("judge_only_audit", "classify", "judgements"),
    "aisef/control/proof.py": ("classify", "run_proves_red", "executed_green"),
    "aisef/control/tdd.py": ("proven_red_before_green", "runs_before_last_green"),
    "aisef/control/closure.py": ("probe_upstream_gates", "probe_stories_done", "probe_judge_only_semantics"),
    "aisef/control/journal.py": ("reconcile_story", "reconcile_all"),
    "aisef/control/state.py": ("StateStore", "SprintState"),
    "aisef/phases/implement.py": ("run_attempt", "verify_candidate", "run_baseline", "run_nop", "freeze_candidate"),
    "aisef/phases/run.py": ("run_sprint", "_qualify_wave", "run_verify_only", "run_epic"),
    "aisef/cli/implement.py": ("cmd_run", "cmd_verify", "cmd_qa", "cmd_predeploy", "cmd_improve"),
    "aisef/cli/parser.py": ("main",),
    "aisef/harness/guardrails.py": ("Verdict", "check_completion"),
}
#: a validation module whose function is a checker or an evidence builder: never imported by aisef2 (UNREACHABLE)
V2_CHECKER_KIND = ("EVIDENCE_SELECTION",)

# ------------------------------------------------------------------------------------------ V2 control vocabulary

CONTROL_EVENTS = {"GATE_DECISION": ("GATE_DECISION",), "GATE_CHECK": ("GATE_DECISION",),
                  "STORY_COMMIT": ("MERGE_ROLLBACK_COMMIT", "TERMINAL_STATE"),
                  "STORY_ROLLBACK": ("MERGE_ROLLBACK_COMMIT", "TERMINAL_STATE"), "STORY_RETRY": ("RETRY",),
                  "FAILURE_OBSERVED": ("FAILURE_OWNER",), "STORY_ADMITTED": ("ADMISSION",),
                  "PLAN_STATIC_ADMITTED": ("ADMISSION",), "PROOF_VERIFIED": ("PRODUCT_TRUTH",),
                  "TESTS_ADEQUACY": ("GATE_DECISION",), "PROVIDER_REQUEST": ("BUDGET",),
                  "STORY_PLAN_DRIFT": ("QUALIFICATION",)}
CONTROL_FUNCTIONS = {
    "aisef2.control.owner.classify": ("FAILURE_OWNER", "RETRYABILITY"), "aisef2.control.owner.flatten": ("FAILURE_OWNER",),
    "aisef2.control.routing.route": ("PRODUCT_TRUTH", "FAILURE_OWNER"), "aisef2.control.routing.row_for": ("PRODUCT_TRUTH",),
    "aisef2.product.outcome.contract_satisfaction": ("PRODUCT_TRUTH",), "aisef2.product.outcome.classify_failure": ("PRODUCT_TRUTH",),
    "aisef2.probe.protocol.bound_result": ("PRODUCT_TRUTH",), "aisef2.probe.protocol.run_probe": ("PRODUCT_TRUTH",),
    "aisef2.product.compiler.compile_spec": ("PRODUCT_TRUTH",), "aisef2.control.budget.charge": ("BUDGET", "RETRY"),
    "aisef2.plan.story_admission.admit_story": ("ADMISSION",), "aisef2.plan.story_admission.classify": ("ADMISSION",),
    "aisef2.plan.drift.continue_story": ("ADMISSION",), "aisef2.plan.drift.plan_quality": ("QUALIFICATION",),
    "aisef2.plan.static_admission.admit": ("ADMISSION",), "aisef2.journal.fold.fold": ("EVIDENCE_SELECTION",),
    "aisef2.journal.format3.verified_proof": ("EVIDENCE_SELECTION", "PRODUCT_TRUTH"),
    "aisef2.journal.format3.verified_payload": ("PRODUCT_TRUTH",),
    "aisef2.quality.adequacy.assemble": ("GATE_DECISION",), "aisef2.quality.adequacy.may_block": ("GATE_DECISION",),
    "aisef2.orchestrate.proof.prove": ("PRODUCT_TRUTH",), "aisef2.orchestrate.merge.reprove": ("PRODUCT_TRUTH",),
    "aisef2.orchestrate.merge.merge": ("MERGE_ROLLBACK_COMMIT",), "aisef2.orchestrate.review.review": ("GATE_DECISION",),
    "aisef2.orchestrate.security.scan": ("GATE_DECISION",), "aisef2.orchestrate.quality.assess": ("GATE_DECISION",),
    "aisef2.orchestrate.gate.check": ("GATE_DECISION",), "aisef2.orchestrate.gate.decision": ("GATE_DECISION",),
    "aisef2.orchestrate.story_runner.run_story": ("GATE_DECISION", "TERMINAL_STATE"),
    "aisef2.orchestrate.seam.admit_legacy": ("ADMISSION",), "aisef2.orchestrate.seam.resolve": ("ADMISSION",),
    "aisef2.runtime.run_scope.RunScope.retry": ("RETRY",), "aisef2.runtime.run_scope.RunScope.state": ("EVIDENCE_SELECTION",),
}
CONTROL_TYPES = {
    "aisef2.control.owner.Classification": ("FAILURE_OWNER", "RETRYABILITY"), "aisef2.control.routing.Route": ("PRODUCT_TRUTH",),
    "aisef2.control.budget.Charge": ("BUDGET", "RETRY"), "aisef2.plan.story_admission.Decision": ("ADMISSION",),
    "aisef2.plan.story_admission.StoryAdmissionResult": ("ADMISSION",), "aisef2.plan.drift.StoryContinuation": ("ADMISSION",),
    "aisef2.plan.drift.PlanDrift": ("QUALIFICATION",), "aisef2.orchestrate.proof.Proof": ("PRODUCT_TRUTH",),
    "aisef2.orchestrate.merge.Merged": ("MERGE_ROLLBACK_COMMIT",), "aisef2.orchestrate.review.Review": ("GATE_DECISION",),
    "aisef2.orchestrate.security.Scan": ("GATE_DECISION",), "aisef2.orchestrate.quality.Quality": ("GATE_DECISION",),
    "aisef2.orchestrate.story_runner.Attempt": ("TERMINAL_STATE",), "aisef2.orchestrate.story_runner.StoryResult": ("TERMINAL_STATE",),
}
PROJECTION_KINDS = {"budgets": ("BUDGET",), "story_state": ("TERMINAL_STATE",), "failure_owner": ("FAILURE_OWNER",),
                    "retry_target": ("RETRY",), "terminal_state": ("TERMINAL_STATE",),
                    "qualification_counters": ("QUALIFICATION",)}
#: engineering-quality names (R2): whatever is bound from these may never reach a product call
QUALITY_SOURCES = {"aisef2.orchestrate.quality.assess", "aisef2.quality.test_execution.execute",
                   "aisef2.quality.relevance.measure", "aisef2.quality.vacuity.evaluate", "aisef2.quality.adequacy.assemble"}
QUALITY_TYPES = {"DeveloperTests", "TestExecution", "Vacuity", "Relevance", "EngineeringTestAdequacy", "Assembly",
                 "AdequacyOutcome", "TestsPolicy", "Quality", "Runner", "Dependencies"}
PRODUCT_SINKS = {"aisef2.orchestrate.proof.prove", "aisef2.orchestrate.merge.reprove", "aisef2.control.routing.route",
                 "aisef2.probe.protocol.bound_result", "aisef2.product.outcome.contract_satisfaction",
                 "aisef2.probe.protocol.run_probe", "aisef2.journal.format3.verified_payload",
                 "aisef2.plan.story_admission.admit_story", "aisef2.product.compiler.compile_spec"}
PRODUCT_NAMES = {"BehaviorVerdict", "ContractSatisfaction", "ProbeRecord", "ProductProofSpec", "VerifiedProof",
                 "bound_result", "route", "contract_satisfaction", "run_probe", "verified_payload", "prove", "reprove"}
#: R4: control modules, where wall-clock time, directory order and a mutable name are never evidence
CONTROL_MODULES = ("aisef2/control/", "aisef2/plan/", "aisef2/journal/", "aisef2/orchestrate/story_runner.py",
                   "aisef2/orchestrate/gate.py", "aisef2/orchestrate/merge.py", "aisef2/orchestrate/proof.py",
                   "aisef2/orchestrate/review.py", "aisef2/orchestrate/security.py", "aisef2/orchestrate/quality.py",
                   "aisef2/orchestrate/seam.py")
RECENCY_ATTRS = {"st_mtime", "st_ctime", "st_atime", "getmtime", "getctime", "listdir", "iterdir", "glob", "rglob",
                 "scandir"}
RECENCY_KEYS = re.compile(r"latest|newest|most_recent|last_modified|mtime|ctime|\btime\b", re.IGNORECASE)
#: the journal writers stamp `Event.time`; nothing else in a control module may import or read wall-clock time
TIME_WRITERS = ("aisef2/journal/writer.py", "aisef2/journal/event.py", "aisef2/journal/format2.py", "aisef2/journal/format3.py")
#: R6: the stage each gate row summarises and the typed call that must precede it in the runner
STAGE_EVIDENCE = {"admission": "admit_story", "developer": "implement", "candidate": "move", "quality": "assess",
                  "merge": "merge", "post-merge": "move", "resources": "acquire"}
STAGE_PREFIX_EVIDENCE = {"proof:": "prove", "post-merge:": "reprove", "review": "review", "security": "scan"}


# ------------------------------------------------------------------------------------------ AST helpers

def _lf(path: pathlib.Path) -> str:
    return path.read_bytes().replace(b"\r\n", b"\n").decode("utf-8")


def _module_name(rel: str) -> str:
    return rel[:-3].replace("/", ".").removesuffix(".__init__")


def _imports(tree: ast.Module, rel: str) -> dict[str, str]:
    """local name -> qualified name it is bound to by an import, absolute (relative imports resolved)."""
    pkg = _module_name(rel).rsplit(".", 1)[0] if not rel.endswith("__init__.py") else _module_name(rel)
    out: dict[str, str] = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                out[(a.asname or a.name).split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
                if a.asname:
                    out[a.asname] = a.name
        elif isinstance(n, ast.ImportFrom):
            base = n.module or ""
            if n.level:
                parts = pkg.split(".")
                base = ".".join(parts[:len(parts) - n.level + 1] + ([n.module] if n.module else []))
            for a in n.names:
                out[a.asname or a.name] = f"{base}.{a.name}"
    return out


def _dotted(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        head = _dotted(node.value)
        return f"{head}.{node.attr}" if head else None
    return None


def _qualify(name: str, imports: dict[str, str], rel: str, local_defs: set[str]) -> str:
    """The qualified name a dotted reference resolves to: through an import, a local definition, or itself."""
    head, _, rest = name.partition(".")
    if head in imports:
        return imports[head] + (f".{rest}" if rest else "")
    if head in local_defs:
        return f"{_module_name(rel)}.{name}"
    return name


def _defs(tree: ast.Module) -> list[tuple[str, ast.AST]]:
    """(qualified-in-module name, node) for every top-level function, class and class method."""
    out = []
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append((n.name, n))
        elif isinstance(n, ast.ClassDef):
            out.append((n.name, n))
            out += [(f"{n.name}.{m.name}", m) for m in n.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]
    return out


def def_digest(tree: ast.Module) -> str:
    """sha256 over the sorted top-level definition names: a module row goes stale when its shape changes."""
    names = sorted(name for name, _ in _defs(tree))
    return hashlib.sha256("\n".join(names).encode()).hexdigest()


def _py_files(root: pathlib.Path, prefixes: Iterable[str]) -> list[str]:
    out = []
    for prefix in prefixes:
        base = root / prefix
        if base.is_file():
            out.append(prefix)
            continue
        out += [p.relative_to(root).as_posix() for p in base.rglob("*.py") if "__pycache__" not in p.parts]
    return sorted(set(out))


def legacy_imports(tree: ast.Module) -> list[tuple[int, str]]:
    """(line, module) of every import of the frozen V1 kernel."""
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out += [(n.lineno, a.name) for a in n.names if a.name == "aisef" or a.name.startswith("aisef.")]
        elif isinstance(n, ast.ImportFrom) and n.module and (n.module == "aisef" or n.module.startswith("aisef.")):
            out.append((n.lineno, n.module))
    return out


# ------------------------------------------------------------------------------------------ the V2 side

def _capabilities(node: ast.AST, imports: dict[str, str], rel: str, local_defs: set[str]) -> dict[str, set[str]]:
    """What a function draws on: control events appended, control functions called, control types constructed."""
    events, calls, types = set(), set(), set()
    for n in ast.walk(node):
        if isinstance(n, ast.Attribute) and n.attr in CONTROL_EVENTS and _dotted(n.value) in ("T", "EventType"):
            events.add(n.attr)
        elif isinstance(n, ast.Call):
            name = _dotted(n.func)
            if name:
                q = _qualify(name, imports, rel, local_defs)
                if q in CONTROL_FUNCTIONS:
                    calls.add(q)
                if q in CONTROL_TYPES:
                    types.add(q)
    return {"events": events, "calls": calls, "types": types}


def v2_reality(root: pathlib.Path = ROOT) -> list[dict]:
    """Every control-capable function of aisef2 and validation/v2, with what makes it one."""
    rows = []
    reachable = reachable_modules(root)
    for prefix in (*V2_RUNTIME, *V2_CHECKERS):
        for rel in _py_files(root, (prefix,)):
            tree = ast.parse(_lf(root / rel))
            imports = _imports(tree, rel)
            local_defs = {name for name, _ in _defs(tree)}
            projection = rel.startswith("aisef2/journal/projections/")
            for name, node in _defs(tree):
                caps = _capabilities(node, imports, rel, local_defs)
                kinds: set[str] = set()
                for e in caps["events"]:
                    kinds.update(CONTROL_EVENTS[e])
                for c in caps["calls"]:
                    kinds.update(CONTROL_FUNCTIONS[c])
                for t in caps["types"]:
                    kinds.update(CONTROL_TYPES[t])
                qualified = f"{_module_name(rel)}.{name}"
                if qualified in CONTROL_FUNCTIONS:
                    kinds.update(CONTROL_FUNCTIONS[qualified])
                if projection and name.endswith(".step"):
                    kinds.update(PROJECTION_KINDS.get(rel.rsplit("/", 1)[1][:-3], ()))
                if not kinds and rel in ADAPTERS:       # an adapter's every function is inventoried: it shapes admission inputs
                    kinds.add("ADMISSION")
                if not kinds:
                    continue
                rows.append({"id": f"{rel}::{name}", "path": rel, "symbol": name,
                             "authority_kind": sorted(kinds, key=KINDS.index),
                             "capabilities": {k: sorted(v) for k, v in caps.items()},
                             "reachable": rel in reachable, "tree": "aisef2" if rel.startswith("aisef2/") else "validation"})
    return rows


def reachable_modules(root: pathlib.Path = ROOT, entry: tuple[str, str] = V2_ENTRY) -> set[str]:
    """Modules of aisef2 import-reachable from the entry module (a package __init__ reached is its package)."""
    files = _py_files(root, V2_RUNTIME)
    by_module = {_module_name(rel): rel for rel in files}
    seen, todo = set(), [entry[0]] if entry[0] in files else []
    while todo:
        rel = todo.pop()
        if rel in seen:
            continue
        seen.add(rel)
        tree = ast.parse(_lf(root / rel))
        for q in set(_imports(tree, rel).values()):
            parts = q.split(".")
            for k in range(len(parts), 0, -1):  # the longest prefix that is a module
                mod = ".".join(parts[:k])
                if mod in by_module:
                    todo.append(by_module[mod])
                    break
    return seen


# ------------------------------------------------------------------------------------------ the V1 side

def v1_reality(root: pathlib.Path = ROOT) -> list[dict]:
    """Every module of the V1 control plane, every named former gate/judge symbol, and every other module of aisef/
    that defines control vocabulary — each with its definition digest and whether its symbols resolve."""
    rows = []
    plane = set(_py_files(root, V1_CONTROL_PLANE))
    for rel in _py_files(root, (V1_TREE,)):
        tree = ast.parse(_lf(root / rel))
        defs = {name for name, _ in _defs(tree)}
        vocabulary = sorted(d for d in defs if V1_VOCABULARY.search(d.split(".")[-1]))
        if rel not in plane and not vocabulary:
            continue
        rows.append({"id": f"{rel}::<module>", "path": rel, "symbol": "<module>", "def_digest": def_digest(tree),
                     "definitions": len(defs), "vocabulary": vocabulary})
        for sym in V1_SYMBOLS.get(rel, ()):
            rows.append({"id": f"{rel}::{sym}", "path": rel, "symbol": sym, "resolves": sym in defs})
    return rows


def entrypoints(root: pathlib.Path = ROOT) -> dict:
    """The console scripts pyproject declares: the V1 one, and whether any names aisef2."""
    p = root / "pyproject.toml"
    text = p.read_text(encoding="utf-8") if p.exists() else ""
    m = re.search(r'^\s*aisef\s*=\s*"([^"]+)"', text, re.M)
    section = text.split("[project.scripts]", 1)
    others = re.findall(r'^\s*([A-Za-z0-9_-]+)\s*=\s*"([A-Za-z0-9_.]+:[A-Za-z0-9_]+)"', section[1].split("[")[0], re.M) if len(section) == 2 else []
    return {"console_scripts": dict(others), "v1_console_script": m.group(1) if m else None,
            "v2_console_script": any(v.startswith("aisef2") for _, v in others)}


# ------------------------------------------------------------------------------------------ legacy references

def legacy_references(root: pathlib.Path = ROOT) -> list[dict]:
    """Every function of the runtime and checker trees that names anything bound from an `aisef` import: DUAL_AUTHORITY
    when it also draws on V2 control, LEGACY_FALLBACK when the reference sits in an except handler or an if-branch that
    returns, LEGACY_REFERENCE otherwise. Plus every module-level import of aisef in those trees."""
    out = []
    for rel in _py_files(root, (*V2_RUNTIME, *V2_CHECKERS)):
        tree = ast.parse(_lf(root / rel))
        imports = _imports(tree, rel)
        legacy_names = {local for local, q in imports.items() if q == "aisef" or q.startswith("aisef.")}
        for line, mod in legacy_imports(tree):
            out.append({"path": rel, "line": line, "kind": "LEGACY_IMPORT", "detail": mod})
        if not legacy_names:
            continue
        local_defs = {name for name, _ in _defs(tree)}
        for name, node in _defs(tree):
            refs = [n for n in ast.walk(node) if isinstance(n, ast.Name) and n.id in legacy_names]
            if not refs:
                continue
            caps = _capabilities(node, imports, rel, local_defs)
            v2 = bool(caps["events"] or caps["calls"] or caps["types"])
            fallback = any(isinstance(h, ast.ExceptHandler) and any(x is r for x in ast.walk(h) for r in refs)
                           for h in ast.walk(node)) or any(
                isinstance(i, ast.If) and any(isinstance(s, ast.Return) for s in ast.walk(i))
                and any(x is r for x in ast.walk(i) for r in refs) for i in ast.walk(node))
            kind = "DUAL_AUTHORITY" if v2 else "LEGACY_FALLBACK" if fallback else "LEGACY_REFERENCE"
            out.append({"path": rel, "line": node.lineno, "kind": kind, "detail": f"{name} names {sorted({r.id for r in refs})}"})
    return out


def test_legacy_imports(root: pathlib.Path = ROOT) -> list[dict]:
    """Test modules that import aisef: historical reproducers, listed so the inventory names them."""
    out = []
    for rel in _py_files(root, ("tests/v2/",)):
        tree = ast.parse(_lf(root / rel))
        for line, mod in legacy_imports(tree):
            out.append({"path": rel, "line": line, "module": mod})
    return out


# ------------------------------------------------------------------------------------------ adapters

def adapter_conditions(root: pathlib.Path = ROOT) -> dict[str, dict]:
    """The seam and the migration-table generator: COMPATIBILITY_NONAUTHORITATIVE only under measured conditions."""
    out = {}
    for rel in ADAPTERS:
        p = root / rel
        if not p.exists():
            out[rel] = {"exists": False}
            continue
        tree = ast.parse(_lf(p))
        imports = _imports(tree, rel)
        legacy = legacy_imports(tree)
        names = {q.rsplit(".", 1)[-1] for q in imports.values()}
        touches_quality = bool(names & QUALITY_TYPES)
        names_hdr = any(isinstance(n, ast.Constant) and n.value == "HUMAN_DECLARATION_REQUIRED" for n in ast.walk(tree))
        cond = {"exists": True, "imports_v1": legacy,
                "constructs_only_v2_inputs": bool(names & {"ObligationRole", "Polarity", "SubjectAbsence"}) or rel.startswith("validation/"),
                "touches_engineering_quality": touches_quality}
        if rel == ADAPTERS[0]:   # the seam refuses the rows the generator leaves undeclared, before the story's first event
            cond["refuses_human_declaration_required"] = names_hdr
            cond["before_the_first_event"] = _seam_before_first_event(root)
        else:                    # the generator reads V1 as text and emits HUMAN_DECLARATION_REQUIRED instead of inferring
            cond["emits_human_declaration_required"] = names_hdr
            cond["reads_v1_as_text_only"] = not legacy and any(
                isinstance(n, ast.Call) and _dotted(n.func) in ("ast.parse",) for n in ast.walk(tree))
        out[rel] = cond
    return out


def _seam_before_first_event(root: pathlib.Path) -> bool:
    """In run_story, admit_legacy is called before any journal append or plan freeze."""
    tree = ast.parse(_lf(root / V2_ENTRY[0]))
    fn = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == V2_ENTRY[1]), None)
    if fn is None:
        return False
    order = [_dotted(n.func) for n in ast.walk(fn) if isinstance(n, ast.Call)]
    order = [o for o in order if o]
    seam = next((i for i, o in enumerate(order) if o.endswith("admit_legacy")), None)
    first_write = next((i for i, o in enumerate(order) if o.endswith((".append", "_freeze_plan", "_attempt"))), None)
    return seam is not None and (first_write is None or seam < first_write)


# ------------------------------------------------------------------------------------------ the inventory

def inventory(root: pathlib.Path = ROOT) -> dict:
    """Reality, classified: every row with the closed disposition the evidence gives it."""
    refs = legacy_references(root)
    conditions = adapter_conditions(root)
    legacy_in_runtime = [r for r in refs if r["path"].startswith(V2_RUNTIME)]
    v2_rows, v1_rows = v2_reality(root), v1_reality(root)
    rows = []
    for r in v2_rows:
        adapter = r["path"] in ADAPTERS
        cond = conditions.get(r["path"], {})
        if adapter and cond.get("exists") and not cond.get("imports_v1") and cond.get("constructs_only_v2_inputs") \
                and not cond.get("touches_engineering_quality") \
                and (cond.get("refuses_human_declaration_required") and cond.get("before_the_first_event")
                     or cond.get("emits_human_declaration_required") and cond.get("reads_v1_as_text_only")):
            disposition, reach, evidence = "COMPATIBILITY_NONAUTHORITATIVE", [f"{V2_ENTRY[0]}::{V2_ENTRY[1]} (before its first event)"], \
                f"adapter conditions: {json.dumps(cond, sort_keys=True)}"
        elif adapter:
            disposition, reach, evidence = "UNCLASSIFIABLE", [], f"adapter conditions violated: {json.dumps(cond, sort_keys=True)}"
        elif r["tree"] == "aisef2":
            disposition = "ACTIVE_V2_AUTHORITY"
            reach = [f"{V2_ENTRY[0]}::{V2_ENTRY[1]}"] if r["reachable"] else ["V2 plan-level or runtime API (not imported by run_story)"]
            evidence = f"AST: {json.dumps(r['capabilities'], sort_keys=True)}; import graph from run_story: {'reachable' if r['reachable'] else 'not reachable'}"
        else:
            disposition, reach = "UNREACHABLE", [f"validation CLI: python -P {r['path']}"]
            evidence = f"AST: {json.dumps(r['capabilities'], sort_keys=True)}; never imported by aisef2 (import graph)"
        rows.append({"id": r["id"], "path": r["path"], "symbol": r["symbol"], "authority_kind": r["authority_kind"],
                     "reachable_from": reach, "disposition": disposition, "replacement": None, "evidence": evidence})
    plane_reachable = bool(legacy_in_runtime)
    for r in v1_rows:
        if r["symbol"] == "<module>":
            kinds, replacement = V1_MODULES.get(r["path"], (None, None))
            if kinds is None:
                disposition, evidence = "UNCLASSIFIABLE", f"a module of the V1 tree with control vocabulary {r['vocabulary']} has no row in V1_MODULES"
                kinds = []
            else:
                disposition = "UNREACHABLE" if not plane_reachable else "UNCLASSIFIABLE"
                evidence = (f"def_digest {r['def_digest']} over {r['definitions']} definitions; no runtime module of aisef2 or "
                            f"validation/v2 imports aisef (import graph); poisoned at runtime by tests/v2/test_no_dual_authority.py")
            rows.append({"id": r["id"], "path": r["path"], "symbol": "<module>", "authority_kind": list(kinds),
                         "reachable_from": [f"{V1_ENTRY[0]}::{V1_ENTRY[1]} (the frozen V1 console script; not a V2 entrypoint)"],
                         "disposition": disposition, "replacement": replacement or None, "evidence": evidence,
                         "def_digest": r["def_digest"]})
        else:
            kinds, replacement = V1_MODULES[r["path"]]      # every V1_SYMBOLS module has its V1_MODULES row (a test holds it)
            disposition = ("UNREACHABLE" if r["resolves"] else "REMOVED") if not plane_reachable else "UNCLASSIFIABLE"
            rows.append({"id": r["id"], "path": r["path"], "symbol": r["symbol"], "authority_kind": list(kinds),
                         "reachable_from": [f"{V1_ENTRY[0]}::{V1_ENTRY[1]} (the frozen V1 console script; not a V2 entrypoint)"],
                         "disposition": disposition, "replacement": replacement,
                         "evidence": ("resolves in the frozen tree (AST); " if r["resolves"] else "no longer defined; ")
                                     + "unreachable from V2 (import graph); poisoned at runtime"})
    for t in test_legacy_imports(root):
        rows.append({"id": f"{t['path']}::<import {t['module']}>", "path": t["path"], "symbol": f"<import {t['module']}>",
                     "authority_kind": [], "reachable_from": ["a test module only"], "disposition": "HISTORICAL_ONLY",
                     "replacement": None,
                     "evidence": f"line {t['line']}: a historical reproducer of a V1 defect; the test tree is not a runtime authority path"})
    ep = entrypoints(root)
    rows.append({"id": "pyproject.toml::console_script aisef", "path": "pyproject.toml", "symbol": f"aisef = {ep['v1_console_script']}",
                 "authority_kind": ["GATE_DECISION", "ADMISSION", "TERMINAL_STATE"],
                 "reachable_from": ["the operating system: the installed V1 console script"],
                 "disposition": "UNREACHABLE" if ep["v1_console_script"] == "aisef.cli:main" and not ep["v2_console_script"] else "UNCLASSIFIABLE",
                 "replacement": "none: V2 has no console script in cycle 1; run_story is the supported V2 entrypoint",
                 "evidence": f"pyproject scripts {json.dumps(ep['console_scripts'], sort_keys=True)}; the V2 tree never imports aisef"})
    rows.sort(key=lambda r: r["id"])
    return {"record": "AISEF V2 — P6 AUTHORITY INVENTORY (WP-6.3)", "tool": "validation/v2/old_path_audit.py",
            "v2_entry": f"{V2_ENTRY[0]}::{V2_ENTRY[1]}", "v1_entry": f"{V1_ENTRY[0]}::{V1_ENTRY[1]}",
            "dispositions": DISPOSITIONS, "kinds": KINDS, "rows": rows, "legacy_references": refs,
            "adapters": conditions, "entrypoints": ep,
            "summary": {d: sum(1 for r in rows if r["disposition"] == d) for d in (*DISPOSITIONS, "UNCLASSIFIABLE")}}


def inventory_digest(inv: dict) -> str:
    return hashlib.sha256(json.dumps(inv["rows"], sort_keys=True, ensure_ascii=False).encode()).hexdigest()


# ------------------------------------------------------------------------------------------ the six proofs (static)

def _function(root: pathlib.Path, rel: str, name: str) -> ast.FunctionDef | None:
    tree = ast.parse(_lf(root / rel))
    return next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name), None)


def _kernel_rules(root: pathlib.Path) -> tuple[list[str], list[str], list[str]]:
    """The kernel static rules this audit relies on, run over `root`."""
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import kernel_static_checks as ks  # noqa: E402
    return (ks.check(root, ("NO_RAW_VERDICT_ROUTING", "RESULT_ONLY_THROUGH_BINDING", "NO_VERDICT_FROM_ABSENCE_DECLARATION")),
            ks.check(root, ("CANDIDATE_ONLY_EXECUTION", "NO_DEVELOPER_ARTEFACT_AT_PARENT")),
            ks.check(root, ("NO_SIDE_RETRY_COUNTER", "RETRYABLE_ONLY_IN_TAXONOMY")))


def developer_test_flows(root: pathlib.Path = ROOT) -> list[str]:
    """R2: in every function of aisef2, no name bound from an engineering-quality call is an argument of a product
    call, and no module of aisef2/quality names a product-truth symbol."""
    out = []
    for rel in _py_files(root, V2_RUNTIME):
        tree = ast.parse(_lf(root / rel))
        imports = _imports(tree, rel)
        local_defs = {name for name, _ in _defs(tree)}
        if rel.startswith("aisef2/quality/"):
            for n in ast.walk(tree):
                if isinstance(n, ast.Name) and n.id in PRODUCT_NAMES:
                    out.append(f"{rel}:{n.lineno} engineering-quality code names {n.id!r}")
        for name, node in _defs(tree):
            tainted: set[str] = set()
            for n in ast.walk(node):
                if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call):
                    q = _qualify(_dotted(n.value.func) or "", imports, rel, local_defs)
                    if q in QUALITY_SOURCES or q.rsplit(".", 1)[-1] in QUALITY_TYPES:
                        for t in n.targets:
                            for x in ast.walk(t):
                                if isinstance(x, ast.Name):
                                    tainted.add(x.id)
            if not tainted:
                continue
            for n in ast.walk(node):
                if isinstance(n, ast.Call):
                    q = _qualify(_dotted(n.func) or "", imports, rel, local_defs)
                    if q in PRODUCT_SINKS:
                        used = {x.id for a in (*n.args, *(k.value for k in n.keywords)) for x in ast.walk(a) if isinstance(x, ast.Name)}
                        if used & tainted:
                            out.append(f"{rel}:{n.lineno} {name}: engineering-quality result {sorted(used & tainted)} flows into {q}")
    return out


def parent_execution_sites(root: pathlib.Path = ROOT) -> list[str]:
    """R3: in the runner, the engineering-quality assessment runs after the verifier's checkout moved to the candidate,
    admission receives no developer-test input, and the seam names no engineering-quality type."""
    out = []
    fn = _function(root, V2_ENTRY[0], "_attempt")
    if fn is None:
        return ["aisef2/orchestrate/story_runner.py::_attempt is missing"]
    calls = [(n.lineno, _dotted(n.func) or "", n) for n in ast.walk(fn) if isinstance(n, ast.Call)]
    assess = [ln for ln, f, _ in calls if f.endswith("assess")]
    moves = [ln for ln, f, n in calls if f.endswith(".move") and n.args and _dotted(n.args[0]) == "verifier_wt"]
    if not assess or not moves or min(assess) < min(moves):
        out.append("story_runner._attempt: assess must follow the verifier checkout's move to the candidate")
    for ln, f, n in calls:
        if f.endswith("admit_story"):
            names = {x.id for a in (*n.args, *(k.value for k in n.keywords)) for x in ast.walk(a) if isinstance(x, ast.Name)}
            attrs = {x.attr for a in (*n.args, *(k.value for k in n.keywords)) for x in ast.walk(a) if isinstance(x, ast.Attribute)}
            if (names | attrs) & {"story_tests", "regression_tests", "runner", "deps"}:
                out.append(f"story_runner._attempt:{ln} admission receives developer-test input")
    seam = root / ADAPTERS[0]
    if seam.exists():
        for n in ast.walk(ast.parse(_lf(seam))):
            if isinstance(n, ast.Name) and n.id in QUALITY_TYPES:
                out.append(f"{ADAPTERS[0]}:{n.lineno} the seam names {n.id!r}")
    return out


def recency_sites(root: pathlib.Path = ROOT) -> list[str]:
    """R4: no control module reads wall-clock time (the journal writers stamp it, nothing folds it), a file's time, a
    directory listing, an ordering by recency, or an implicit HEAD. Ordering by journal seq is the journal's own."""
    out = []
    for rel in _py_files(root, CONTROL_MODULES):
        tree = ast.parse(_lf(root / rel))
        writer = rel in TIME_WRITERS
        for n in ast.walk(tree):
            if not writer and (isinstance(n, ast.Import) and any(a.name.split(".")[0] in ("time", "datetime", "glob") for a in n.names)
                               or isinstance(n, ast.ImportFrom) and (n.module or "").split(".")[0] in ("time", "datetime", "glob")):
                out.append(f"{rel}:{n.lineno} a control module imports wall-clock time or directory listing")
            elif not writer and (isinstance(n, ast.Attribute) and n.attr == "time"
                                 or isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant) and n.slice.value == "time"):
                out.append(f"{rel}:{n.lineno} reads an event's wall-clock time: recorded, never folded")
            elif isinstance(n, ast.Attribute) and n.attr in RECENCY_ATTRS:
                out.append(f"{rel}:{n.lineno} reads {n.attr}: file time or directory order is never evidence")
            elif isinstance(n, ast.Constant) and n.value == "HEAD":
                out.append(f"{rel}:{n.lineno} names HEAD: a control module holds full SHAs only")
            elif isinstance(n, ast.Call) and _dotted(n.func) in ("max", "min", "sorted") and any(
                    k.arg == "key" and RECENCY_KEYS.search(ast.unparse(k.value)) for k in n.keywords):
                out.append(f"{rel}:{n.lineno} orders by a recency key")
    return out


def journal_backing(root: pathlib.Path = ROOT) -> list[str]:
    """R6 (static): in the runner every gate row follows the typed call of its stage, every row is collected into the
    one list the decision cites, the decision is made once, and retry/rollback follow the journaled charge."""
    out = []
    fn = _function(root, V2_ENTRY[0], "_attempt")
    if fn is None:
        return ["aisef2/orchestrate/story_runner.py::_attempt is missing"]
    seq = [(n.lineno, _dotted(n.func) or "", n) for n in ast.walk(fn) if isinstance(n, ast.Call)]
    seq.sort(key=lambda x: x[0])
    for ln, f, n in seq:
        if f.endswith("gate.check") and len(n.args) >= 3:
            stage = n.args[2]
            label = stage.value if isinstance(stage, ast.Constant) else ast.unparse(stage)
            want = STAGE_EVIDENCE.get(label) or next((v for k, v in STAGE_PREFIX_EVIDENCE.items() if label.startswith(k) or label.startswith(f"f'{k}") or label.startswith(f'f"{k}')), None)
            if want is None:
                out.append(f"_attempt:{ln} gate row {label!r} has no stage evidence rule")
                continue
            before = [g for l2, g, _ in seq if l2 < ln and g.endswith(want)]
            if not before:
                out.append(f"_attempt:{ln} gate row {label!r} precedes its stage's typed call {want}")
    collected = {id(a) for _, f, n in seq if f == "checks.append" for a in n.args}
    for ln, f, n in seq:
        if f.endswith("gate.check") and id(n) not in collected:
            out.append(f"_attempt:{ln} a gate row is written and not collected into the decision")
    decisions = [(ln, n) for ln, f, n in seq if f.endswith("gate.decision")]
    if len(decisions) != 1:
        out.append(f"_attempt: {len(decisions)} gate decisions; exactly one is made per attempt")
    elif not (decisions[0][1].args and _dotted(decisions[0][1].args[1]) == "checks"):
        out.append("_attempt: the decision does not cite the collected checks")
    charge = [ln for ln, f, _ in seq if f.endswith("budget.charge")]
    retry = [ln for ln, f, _ in seq if f.endswith("run.retry")]
    if not charge or not retry or min(charge) > min(retry):
        out.append("_attempt: a retry is decided by budget.charge over the journal before run.retry")
    return out


def proofs(root: pathlib.Path = ROOT, inv: dict | None = None) -> dict:
    """The static halves of the six proofs, each an exact boolean with its evidence."""
    inv = inv or inventory(root)
    verdict_rules, parent_rules, retry_rules = _kernel_rules(root)
    legacy_runtime = [r for r in inv["legacy_references"] if r["path"].startswith(V2_RUNTIME + V2_CHECKERS)]
    v1_rows = [r for r in inv["rows"] if r["path"].startswith(V1_TREE) or r["path"] == "pyproject.toml"]
    flows, parent_sites, recency, backing = developer_test_flows(root), parent_execution_sites(root), recency_sites(root), journal_backing(root)
    return {
        "NO_OLD_GATE_AUTHORITY": {"static": not legacy_runtime and all(r["disposition"] in ("UNREACHABLE", "REMOVED") for r in v1_rows)
                                  and inv["summary"]["UNCLASSIFIABLE"] == 0,
                                  "legacy_references_in_runtime": legacy_runtime, "v1_rows": len(v1_rows),
                                  "runtime": "tests/v2/test_no_dual_authority.py::Poisoned (every V1 family raises; real ORCH fixtures unchanged)"},
        "NO_DEVELOPER_TEST_PRODUCT_AUTHORITY": {"static": not flows and not verdict_rules, "flows": flows, "kernel_rules": verdict_rules,
                                                "runtime": "tests/v2/test_no_dual_authority.py::DeveloperTestsNeverDecide"},
        "NO_PARENT_DEVELOPER_EXECUTION": {"static": not parent_sites and not parent_rules, "sites": parent_sites, "kernel_rules": parent_rules,
                                          "runtime": "tests/v2/test_no_dual_authority.py::NothingExecutesAtTheParent"},
        "NO_RECENCY_EVIDENCE_SELECTION": {"static": not recency, "sites": recency,
                                          "runtime": "tests/v2/test_no_dual_authority.py::OnlyExplicitReferencesSelectEvidence"},
        "NO_SIDE_RETRY_COUNTER": {"static": not retry_rules, "kernel_rules": retry_rules,
                                  "runtime": "tests/v2/test_no_dual_authority.py::RetryStateIsTheJournal"},
        "ALL_CONTROL_DECISIONS_JOURNAL_BACKED": {"static": not backing, "sites": backing,
                                                 "runtime": "tests/v2/test_no_dual_authority.py::EveryDecisionIsJournalBacked (decision -> source-seq table)"},
    }


# ------------------------------------------------------------------------------------------ R6: decision -> source seqs

#: the typed event each gate row summarises (the row's `check` is "<story>:<stage>[:<id>]")
ROW_EVIDENCE = {"admission": ("story/admitted",), "developer": ("provider/result",), "proof": ("proof/verified", "probe/evaluated"),
                "quality": ("tests/adequacy",), "review": ("provider/result",), "security": ("tool/result", "tool/invoked"),
                "merge": ("proof/verified",), "post-merge": ("proof/verified", "probe/evaluated"),
                "resources": ("story/resource-acquired", "story/begin"), "candidate": ("provider/result",)}
DECISIONS = ("story/admitted", "provider/result", "proof/verified", "tests/adequacy", "gate/check", "gate/decision",
             "failure/observed", "story/retry", "story/rollback", "story/commit", "story/end")


def decision_table(events) -> list[dict]:
    """Every control decision of a journal with the seqs of the journal facts it rests on: cited source seqs, and for
    a gate row the typed event of its stage that precedes it in the same attempt. Mechanical, from the journal alone."""
    table = []
    begins: dict[str, int] = {}
    for e in events:
        story = e.data.get("story_id")
        if e.type == "story/begin":
            begins[story] = e.seq
        if e.type not in DECISIONS:
            continue
        facts = list(e.source_seqs)
        since = begins.get(story, 0)
        if e.type == "gate/check":
            stage = e.data["check"].split(":", 2)[1] if ":" in e.data["check"] else e.data["check"]
            story = e.data["check"].split(":", 1)[0]
            since = begins.get(story, 0)
            wanted = ROW_EVIDENCE.get(stage, ())
            prior = [p for p in events if since <= p.seq < e.seq and p.type in wanted and p.data.get("story_id") == story]
            if prior:
                facts.append(prior[-1].seq)
        elif e.type in ("story/admitted",):
            facts += [p.seq for p in events if since <= p.seq < e.seq and p.type == "probe/evaluated" and p.data.get("story_id") == story]
        elif e.type == "tests/adequacy":
            facts += [p.seq for p in events if since <= p.seq < e.seq and p.type == "story/admitted" and p.data.get("story_id") == story]
        elif e.type in ("story/commit", "failure/observed"):
            facts += [p.seq for p in events if since <= p.seq < e.seq and p.type == "gate/decision"][-1:]
        elif e.type == "story/end":
            facts += [p.seq for p in events if since <= p.seq < e.seq and p.type in ("story/commit", "story/rollback", "story/retry") and p.data.get("story_id") == story][-1:]
        table.append({"seq": e.seq, "decision": e.type, "story_id": story, "check": e.data.get("check"),
                      "facts": sorted(set(facts))})
    return table


def decision_problems(table: list[dict]) -> list[str]:
    """Every decision rests on at least one journal fact, and every fact precedes it."""
    out = []
    for t in table:
        if not t["facts"]:
            out.append(f"{t['decision']} at seq {t['seq']} rests on no journal fact")
        for f in t["facts"]:
            if not isinstance(f, int) or f >= t["seq"]:
                out.append(f"{t['decision']} at seq {t['seq']} cites {f}, which is not before it")
    return out


# ------------------------------------------------------------------------------------------ the audit

def compare(committed: dict, reality: dict) -> list[str]:
    """Both directions: reality not in the inventory, inventory not in reality, dispositions that moved, digests that
    changed, symbols that no longer resolve, unclassifiable rows, legacy references, adapters touching V1."""
    out = []
    real = {r["id"]: r for r in reality["rows"]}
    kept = {r["id"]: r for r in committed.get("rows", [])}
    for rid in sorted(set(real) - set(kept)):
        out.append(f"UNENUMERATED authority: {rid} ({real[rid]['disposition']}) is in the tree and not in the inventory")
    for rid in sorted(set(kept) - set(real)):
        out.append(f"STALE inventory row: {rid} no longer resolves to an authority in the tree")
    for rid in sorted(set(real) & set(kept)):
        a, b = real[rid], kept[rid]
        if a["disposition"] != b["disposition"]:
            out.append(f"DISPOSITION moved: {rid} is {a['disposition']} in the tree, {b['disposition']} in the inventory")
        if a.get("def_digest") != b.get("def_digest"):
            out.append(f"SHAPE changed: {rid} def_digest differs from the inventory")
        if sorted(a["authority_kind"]) != sorted(b["authority_kind"]):
            out.append(f"KIND changed: {rid}")
    for r in reality["rows"]:
        if r["disposition"] not in DISPOSITIONS:
            out.append(f"UNCLASSIFIABLE: {r['id']}: {r['evidence']}")
        if r["disposition"] == "REMOVED" and kept.get(r["id"], {}).get("disposition") not in ("REMOVED", None):
            out.append(f"REMOVED without the inventory saying so: {r['id']}")
    for ref in reality["legacy_references"]:
        out.append(f"{ref['kind']}: {ref['path']}:{ref['line']} {ref['detail']} — an old authority is reachable again")
    for rel, cond in reality["adapters"].items():
        if cond.get("imports_v1"):
            out.append(f"ADAPTER touches V1: {rel} imports {cond['imports_v1']}")
    return out


def audit(root: pathlib.Path = ROOT) -> dict:
    """Reality, the six static proofs, and the comparison with the committed inventory."""
    inv = inventory(root)
    committed_path = root / INVENTORY_REL
    committed = json.loads(committed_path.read_text(encoding="utf-8")) if committed_path.exists() else {}
    problems = compare(committed, inv)
    if not committed_path.exists():
        problems.append(f"{INVENTORY_REL} is missing: generate it")
    pr = proofs(root, inv)
    for name in PROOFS:
        if not pr[name]["static"]:
            problems.append(f"PROOF {name} does not hold statically: {json.dumps({k: v for k, v in pr[name].items() if k not in ('static', 'runtime')}, sort_keys=True)[:500]}")
    return {"inventory": inv, "inventory_digest": inventory_digest(inv), "committed_digest": inventory_digest(committed) if committed.get("rows") else None,
            "proofs": pr, "problems": problems}


def check(root: pathlib.Path = ROOT) -> list[str]:
    return audit(root)["problems"]


def render(inv: dict) -> str:
    return json.dumps(inv, indent=1, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--generate" in argv:
        inv = inventory()
        bad = [r for r in inv["rows"] if r["disposition"] not in DISPOSITIONS]
        if bad:
            for r in bad:
                print(f"FAIL  UNCLASSIFIABLE {r['id']}: {r['evidence']}")
            print("old path audit: FAIL (not written)")
            return 1
        (ROOT / INVENTORY_REL).write_text(render(inv), encoding="utf-8")
        print(f"wrote {INVENTORY_REL}: {inv['summary']}")
    problems = check()
    for p in problems:
        print(f"FAIL  {p}")
    print("old path audit: " + ("FAIL" if problems else "PASS"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
