"""P10 / QP-10 — LedgerLock as a DEVELOPMENT / REGRESSION benchmark (owner's "P10 / QP-10 EXECUTION AUTHORIZATION";
RFC §28-§30; final cycle-1 package).

    python -P validation/qualification/p10.py --run              # the regression run: workload frozen, compiled, admitted, executed if admitted
    python -P validation/qualification/p10.py --conformance start|end

Three things live here and nowhere in the kernel (P10 adds no frozen item; the aisef2 tree stays the candidate's):

1. The **recorder**: `Workload` (LedgerLock is DEVELOPMENT_REGRESSION and its cohort state is DEVELOPMENT; every
   transition toward SEALED, HOLDOUT or EVALUATING is refused by the state machine), `RunVerdict` (delivery and plan
   quality, two fields and nothing that could hold one score; `overall_verdict` refuses), `plan_quality_verdict_of`
   (NOT_CLAIMED unless every threshold was preregistered before the run started), and `Recorder.record` (refuses a
   generalization claim other than NONE, a sample size, a seal, a holdout, a score).
2. The **workload**: LedgerLock PLAN-V2.1 — 16 stories, 77 criteria as frozen for V1 (W1-PLAN-V2.1-FREEZE.json, plan
   commit 136a68d, requirements sha256 3a6a9995…) — written as V2 BehaviorContracts with their TRUE subject kinds
   (RFC §7: python_callable, cli_invocation, file_artifact, process_effect) and compiled by the kernel's own compiler,
   then put to the StaticPlanAdmissionEngine. The kernel decides what it can prove; nothing here bypasses it.
3. The **execution**: through the current authoritative path (story_runner) with a live developer and reviewer over
   OpenCode on the declared route, if — and only if — the plan is admitted. A plan that is not admitted never reaches
   delivery: delivery_verdict = NOT_REACHED, typed by the engine's nine checks. Nothing is replayed, retuned or repaired.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from enum import Enum

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.qualification import common as C  # noqa: E402

OUT_REL = "closure-evidence/v2/P10"
SEMANTIC_CANDIDATE = "7114177834da5a7e4a0fc2c7f8fa9d067e0abaa2"
KERNEL_TREE = "4d6081940f5b9dae47439f73f0157161e028d804"
LEDGERLOCK_REPO = pathlib.Path("/Users/nghinh/Downloads/projects/ledgerlock-aiseftest-run2")
LEDGERLOCK_PLAN_COMMIT = "136a68dcdc3f416b2a76c561a7df12d1282ad4d5"     # W1-LEDGERLOCK-PLAN-V2.1 (branch plan-v2.1), the baseline
REQUIREMENTS_SHA256 = "3a6a99959bbc6cf39c4d4afa9c2de222925fdcaad30aaf3fa2d04ee446597ecc"
V1_AUDIT_REL = "closure-evidence/hardening/W1-PLAN-V2.1-AUDIT.json"       # the 77 criteria as V1 froze them (read, never edited)
V1_FREEZE_REL = "closure-evidence/hardening/W1-PLAN-V2.1-FREEZE.json"
P2_CALIBRATION_REL = "closure-evidence/v2/P2-CALIBRATION.json"
HARNESS_FILES = ("validation/qualification/p10.py", "validation/qualification/p10_run.sh")

# =============================================================================================== 1. the recorder

BENCHMARK_CLASS = "DEVELOPMENT_REGRESSION"
GENERALIZATION_CLAIM = "NONE"
DELIVERY_VERDICTS = ("PASS", "FAIL", "NOT_REACHED")
PLAN_QUALITY_VERDICTS = ("PASS", "FAIL", "NOT_CLAIMED")


class CohortState(Enum):        # RFC §28: SEALED -> EVALUATING -> EXPOSED -> DEVELOPMENT, one way
    SEALED = "SEALED"
    EVALUATING = "EVALUATING"
    EXPOSED = "EXPOSED"
    DEVELOPMENT = "DEVELOPMENT"


_FORWARD = {CohortState.SEALED: CohortState.EVALUATING, CohortState.EVALUATING: CohortState.EXPOSED, CohortState.EXPOSED: CohortState.DEVELOPMENT}


class SealingRefused(Exception):
    """A development / regression workload asked to become a sealed or holdout cohort (RFC §30)."""


class ClaimRefused(Exception):
    """A record asked to carry what LedgerLock cannot back: a generalization claim, a sample size, one score (RFC §28-§30)."""


@dataclass(frozen=True, slots=True)
class Workload:
    id: str
    benchmark_class: str
    state: CohortState

    def transition(self, to: "CohortState | str") -> "Workload":
        """The only moves RFC §28 allows are forward along SEALED -> EVALUATING -> EXPOSED -> DEVELOPMENT; DEVELOPMENT is
        terminal, and a DEVELOPMENT_REGRESSION workload never leaves it. HOLDOUT is a name for a sealed cohort: refused."""
        name = to.value if isinstance(to, CohortState) else str(to)
        if self.benchmark_class == BENCHMARK_CLASS or self.state is CohortState.DEVELOPMENT:
            if name == CohortState.DEVELOPMENT.value:
                return self
            raise SealingRefused(f"{self.id} is a {BENCHMARK_CLASS} workload in state DEVELOPMENT: it cannot become {name} "
                                 "(RFC §30: permanently development; no re-labelling is available and none may be sought)")
        target = CohortState(name)
        if _FORWARD.get(self.state) is not target:
            raise SealingRefused(f"{self.id}: {self.state.value} -> {name} is not a forward move of RFC §28")
        return Workload(self.id, self.benchmark_class, target)

    def seal(self) -> "Workload":
        return self.transition("SEALED")


LEDGERLOCK = Workload("LedgerLock", BENCHMARK_CLASS, CohortState.DEVELOPMENT)


@dataclass(frozen=True, slots=True)
class RunVerdict:
    """RFC §29: two verdicts, separately. There is no third field, no score and no way to add one (slots)."""
    delivery_verdict: str
    plan_quality_verdict: str

    def __post_init__(self) -> None:
        if self.delivery_verdict not in DELIVERY_VERDICTS:
            raise ClaimRefused(f"delivery_verdict is one of {DELIVERY_VERDICTS}")
        if self.plan_quality_verdict not in PLAN_QUALITY_VERDICTS:
            raise ClaimRefused(f"plan_quality_verdict is one of {PLAN_QUALITY_VERDICTS}")


def overall_verdict(verdict: RunVerdict):
    raise ClaimRefused("delivery and plan quality are never collapsed into one score (RFC §29: the distinction is mandatory)")


def delivery_verdict_of(events: list, *, plan_admitted: bool) -> str:
    """From the run's journal alone — no plan-quality input exists here (P10-1). NOT_REACHED when the plan was not
    admitted or no story reached its gate decision; PASS when every story's last outcome is COMMIT; FAIL otherwise."""
    if not plan_admitted:
        return "NOT_REACHED"
    outcomes: dict[str, str] = {}
    decided = False
    for e in events:
        t, d = e["type"], e["data"]
        if t == "gate/decision":
            decided = True
        if t in ("story/commit", "story/rollback", "story/retry"):
            outcomes[d["story_id"]] = t.split("/")[1].upper()
    if not decided or not outcomes:
        return "NOT_REACHED"
    return "PASS" if all(v == "COMMIT" for v in outcomes.values()) else "FAIL"


def plan_quality_metrics(events: list, roles: dict[str, str]) -> dict:
    """RFC §29's three metrics and the descriptive counts of owner §18 — projections of the journal, descriptive only."""
    introduce = [c for c, r in roles.items() if r == "INTRODUCE"]
    pre = set()
    story_dispositions: dict[str, dict] = {}
    attributed = unattributed = 0
    retries: dict[str, int] = {}
    outcomes: dict[str, str] = {}
    budgets: dict[str, int] = {}
    for e in events:
        t, d = e["type"], e["data"]
        if t == "story/admitted":
            story_dispositions[d["story_id"]] = dict(d["dispositions"])
            pre |= {c for c, v in d["dispositions"].items() if v == "PRE_SATISFIED" and roles.get(c) == "INTRODUCE"}
        elif t == "story/plan-drift":
            if d.get("attributed_to") == "UNATTRIBUTED":
                unattributed += 1
            else:
                attributed += 1
        elif t == "story/retry":
            retries[d["story_id"]] = retries.get(d["story_id"], 0) + 1
        elif t in ("story/commit", "story/rollback"):
            outcomes[d["story_id"]] = t.split("/")[1].upper()
        elif t == "provider/request":
            budgets[d.get("budget_owner", "?")] = budgets.get(d.get("budget_owner", "?"), 0) + 1
    fully = [s for s, disp in story_dispositions.items()
             if disp and all(v == "PRE_SATISFIED" for c, v in disp.items() if roles.get(c) == "INTRODUCE") and any(roles.get(c) == "INTRODUCE" for c in disp)]
    return {"introduce_obligations": len(introduce), "pre_satisfied_introduce": len(pre),
            "pre_satisfied_introduce_ratio": (len(pre) / len(introduce)) if introduce else None,
            "fully_pre_satisfied_stories": len(fully), "fully_pre_satisfied_story_ids": sorted(fully),
            "unattributed_plan_drift": unattributed, "attributed_plan_drift": attributed,
            "delivery_complete_stories": sorted(s for s, o in outcomes.items() if o == "COMMIT"),
            "failed_stories": sorted(s for s, o in outcomes.items() if o == "ROLLBACK"), "retries": retries, "provider_requests_by_budget": budgets,
            "note": "observations of the journal; without preregistered thresholds they produce no plan-quality PASS/FAIL"}


def plan_quality_verdict_of(metrics: dict, policy, *, policy_preregistered_at: float | None, run_started_at: float) -> str:
    """NOT_CLAIMED unless a complete PlanQualityPolicy was preregistered strictly before the run started (P10-4, P10-5)."""
    thresholds = (policy.max_pre_satisfied_introduce_ratio, policy.max_fully_pre_satisfied_stories, policy.max_unattributed_plan_drift)
    if any(t is None for t in thresholds) or policy_preregistered_at is None or policy_preregistered_at >= run_started_at:
        return "NOT_CLAIMED"
    ratio = metrics.get("pre_satisfied_introduce_ratio") or 0.0
    ok = (ratio <= policy.max_pre_satisfied_introduce_ratio and metrics["fully_pre_satisfied_stories"] <= policy.max_fully_pre_satisfied_stories
          and metrics["unattributed_plan_drift"] <= policy.max_unattributed_plan_drift)
    return "PASS" if ok else "FAIL"


def preregistered_policy(out_dir: pathlib.Path):
    """The PlanQualityPolicy the owner preregistered for LedgerLock before this run, if any: a committed file that
    names its thresholds and the time it was written. Absent -> NOT_PREREGISTERED (RFC §29: no framework threshold)."""
    from aisef2.plan.obligation import NOT_PREREGISTERED, PlanQualityPolicy
    p = out_dir / "PLAN-QUALITY-POLICY.json"
    if not p.exists():
        return NOT_PREREGISTERED, None, None
    d = json.loads(p.read_text(encoding="utf-8"))
    return (PlanQualityPolicy(d.get("max_pre_satisfied_introduce_ratio"), d.get("max_fully_pre_satisfied_stories"), d.get("max_unattributed_plan_drift")),
            d.get("preregistered_at"), p.relative_to(ROOT).as_posix())


class Recorder:
    """The evidence recorder: what a LedgerLock record may say. Mechanical, not prose."""
    FORBIDDEN_KEYS = frozenset({"qualification_sample_size", "generalization_sample_size", "sample_size", "sealed", "holdout", "overall_verdict",
                                "overall_score", "score", "cohort_seal", "external_validity", "generalization"})

    def record(self, **fields) -> dict:
        for k in fields:
            if k in self.FORBIDDEN_KEYS:
                raise ClaimRefused(f"a LedgerLock record cannot carry {k!r}: no sample size, seal, holdout or single score exists for a development benchmark")
        if fields.get("benchmark_class") != BENCHMARK_CLASS:
            raise ClaimRefused(f"benchmark_class is {BENCHMARK_CLASS} and nothing else")
        if fields.get("generalization_claim") != GENERALIZATION_CLAIM:
            raise ClaimRefused(f"generalization_claim is {GENERALIZATION_CLAIM}: LedgerLock backs no generalization (RFC §28.6, §30)")
        if fields.get("cohort_state") != CohortState.DEVELOPMENT.value:
            raise ClaimRefused("cohort_state is DEVELOPMENT")
        verdict = fields.get("verdict")
        if not isinstance(verdict, RunVerdict):
            raise ClaimRefused("the verdict is a RunVerdict: delivery and plan quality, separately")
        out = dict(fields)
        out["verdict"] = {"delivery_verdict": verdict.delivery_verdict, "plan_quality_verdict": verdict.plan_quality_verdict}
        out["delivery_verdict"], out["plan_quality_verdict"] = verdict.delivery_verdict, verdict.plan_quality_verdict
        return out


# =============================================================================================== 2. the workload

#: RFC §31: a V1 proof mode enters V2 only through the seam and the generated migration table (P6-MIGRATION-TABLE.json):
#: role and polarity come from the table's row, SubjectAbsence only from the declaration each contract carries here.
MIGRATION_TABLE_REL = "closure-evidence/v2/P6-MIGRATION-TABLE.json"
FR_TITLES = {"FR-1": "NFC key normalization", "FR-2": "SHA-256 hash chain over canonical bytes", "FR-3": "Idempotent replay by rid",
             "FR-4": "Conflict detection by rid", "FR-5": "Tombstone semantics for delete", "FR-6": "End-to-end verify from disk",
             "FR-7": "Verifier does not trust in-memory cache", "FR-8": "Atomic apply_batch", "FR-9": "Deterministic snapshot",
             "FR-10": "Repair truncated tail only", "FR-11": "CLI subcommands", "FR-12": "Exact exit-code contract",
             "FR-13": "fsync before return", "FR-14": "No network, no subprocess, no extra files"}
WITHIN = 30
NFD_E, NFC_E = "é", "é"
LINE = {"op": "put", "key": "k", "value": {"v": 1}, "ts": 100, "id": "r1", "hash": "", "prev_hash": ""}


def line_hash_expected(prev_hash: str, line: dict) -> str:
    """requirements §3.2 / PLAN-V2.1 story 1.3: SHA-256(prev_hash || "|" || canonical bytes of the line with hash and
    prev_hash emptied), lowercase hex — the contract's expected value, derived from the frozen requirements."""
    emptied = {**line, "hash": "", "prev_hash": ""}
    canonical = json.dumps(emptied, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(prev_hash.encode("utf-8") + b"|" + canonical).hexdigest()


def pc(locator, *, args=None, returns=None, raises=None, exists=False, absence="REQUIRES_SUBJECT", note=""):
    stim = {} if exists else {"args": list(args or [])}
    obs = {"condition": "exists", "within_s": WITHIN} if exists else ({"raises": raises, "within_s": WITHIN} if raises else {"returns": returns, "within_s": WITHIN})
    return {"kind": "python_callable", "locator": locator, "stimulus": stim, "observable": obs, "absence": absence, "note": note}


def pc_unsupported(locator, observable: dict, *, args=None, note=""):
    """A python_callable subject whose observable the cycle-1 probe has no class for (bytes, a constant's value, an
    instance method's effect): written as the criterion says it, so the engine can say what it cannot prove."""
    return {"kind": "python_callable", "locator": locator, "stimulus": {"args": list(args or [])}, "observable": {**observable, "within_s": WITHIN},
            "absence": "REQUIRES_SUBJECT", "note": note}


def cli(argv, *, exit_code, stdout=None, stderr_prefix=None, setup=None, note=""):
    return {"kind": "cli_invocation", "locator": "ledgerlock:__main__", "stimulus": {"argv": list(argv), **({"setup": setup} if setup else {})},
            "observable": {"exit_code": exit_code, **({"stdout": stdout} if stdout is not None else {}), **({"stderr_line_prefix": stderr_prefix} if stderr_prefix else {}),
                           "within_s": WITHIN}, "absence": "REQUIRES_SUBJECT", "note": note}


def effect(locator, scenario: str, observable: dict, *, absence="REQUIRES_SUBJECT", note=""):
    return {"kind": "process_effect", "locator": locator, "stimulus": {"scenario": scenario}, "observable": {**observable, "within_s": WITHIN}, "absence": absence, "note": note}


def tree(pattern: str, note=""):
    return {"kind": "file_artifact", "locator": "ledgerlock:__path__", "stimulus": {"grep": pattern}, "observable": {"matches": 0, "within_s": WITHIN},
            "absence": "ABSENCE_IS_DECIDABLE", "note": note}


def test_gate(locator, scenario: str, observable: dict, note=""):
    """Criteria whose subject is a test run or a coverage gate: RFC §7 forbids a contract that names a test artefact —
    written as the plan says them, so the kernel's contract rule refuses them typed."""
    return {"kind": "process_effect", "locator": locator, "stimulus": {"scenario": scenario}, "observable": {**observable, "within_s": WITHIN},
            "absence": "REQUIRES_SUBJECT", "note": note}


H_A, H_B, H_G = line_hash_expected("a" * 64, LINE), line_hash_expected("b" * 64, LINE), line_hash_expected("GENESIS", LINE)
LINE_SET = {**LINE, "hash": "f" * 64, "prev_hash": "e" * 64}
V2: dict[str, dict] = {
    # ---- STORY-01-01
    "AC-STORY-01-01-1": pc("ledgerlock.format:normalize_key", args=[NFD_E], returns=NFC_E, note="one instance of 'any string s': the NFD form"),
    "AC-STORY-01-01-2": pc("ledgerlock.format:normalize_key", args=[NFC_E], returns=NFC_E),
    "AC-STORY-01-01-3": pc("ledgerlock:__file__", exists=True, note="the package imports from the checkout"),
    "AC-STORY-01-01-4": tree(r"^(import|from) (socket|subprocess|requests|http|urllib|asyncio|ssl|multiprocessing|ctypes|http\.server|http\.client|socketserver)"),
    "AC-STORY-01-01-5": tree(r"os\.system|subprocess\.|socket\."),
    "AC-STORY-01-01-6": pc("ledgerlock:Ledger", exists=True, note="the criterion names two symbols; the contract names the class"),
    "AC-STORY-01-01-7": cli(["verify", "<ledger>", "<extra-positional>"], exit_code=2, stdout=""),
    # ---- STORY-01-02
    "AC-STORY-01-02-1": pc_unsupported("ledgerlock.format:canonical_bytes", {"returns_bytes_hex": json.dumps({"op": "put", "key": "k", "value": 1, "ts": 1, "id": "r"}, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode().hex()},
                                       args=[{"op": "put", "key": "k", "value": 1, "ts": 1, "id": "r"}], note="returns bytes: not a JSON value the probe can compare"),
    "AC-STORY-01-02-2": pc_unsupported("ledgerlock.format:canonical_bytes", {"returns_bytes_hex": "identical to AC-STORY-01-02-1"}, args=[{"op": "put", "key": "k", "value": 1, "ts": 1, "id": "r"}]),
    "AC-STORY-01-02-3": pc_unsupported("ledgerlock.format:canonical_bytes", {"returns_bytes_hex": json.dumps({"k": NFC_E}, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode().hex()}, args=[{"k": NFC_E}]),
    "AC-STORY-01-02-4": pc_unsupported("ledgerlock.format:canonical_bytes", {"returns_bytes_hex": json.dumps({"a": 1, "b": 2}, sort_keys=True, separators=(",", ":")).encode().hex()}, args=[{"b": 2, "a": 1}]),
    "AC-STORY-01-02-5": pc_unsupported("ledgerlock.format:GENESIS", {"equals": "GENESIS"}, note="a constant's value: the probe observes callables"),
    "AC-STORY-01-02-6": pc_unsupported("ledgerlock.format:canonical_bytes", {"returns_bytes_hex": "stable across a json round trip"}, args=[{"op": "put"}]),
    # ---- STORY-01-03
    "AC-STORY-01-03-1": pc("ledgerlock.format:line_hash", args=["a" * 64, LINE], returns=H_A),
    "AC-STORY-01-03-2": pc("ledgerlock.format:line_hash", args=["b" * 64, LINE], returns=H_B, note="a distinct prev_hash gives the distinct digest"),
    "AC-STORY-01-03-3": pc("ledgerlock.format:line_hash", args=["a" * 64, LINE_SET], returns=H_A, note="hash fields already set are emptied"),
    "AC-STORY-01-03-4": pc("ledgerlock.format:line_hash", args=["a" * 64, LINE], returns=H_A, note="the same pair, the same digest"),
    "AC-STORY-01-03-5": pc("ledgerlock.format:line_hash", args=["GENESIS", LINE], returns=H_G),
    # ---- STORY-01-04
    "AC-STORY-01-04-1": pc_unsupported("ledgerlock.store:read_lines", {"returns_bytes_list": "N lines"}, args=["<jsonl with N lines>"], note="returns list[bytes] over a fixture file"),
    "AC-STORY-01-04-2": pc("ledgerlock.store:read_lines", args=["/nonexistent/ledgerlock/missing.jsonl"], raises="FileNotFoundError"),
    "AC-STORY-01-04-3": pc_unsupported("ledgerlock.store:read_lines", {"returns": [], "requires_fixture_file": "a zero-byte file at the argument path"}, args=["<empty file>"],
                                       note="the stimulus is a file the probe cannot create: no fixture facility in the cycle-1 probe"),
    "AC-STORY-01-04-4": effect("ledgerlock.store:write_atomic", "write two lines then read_lines", {"file_bytes": "concatenation", "lines": 2}),
    "AC-STORY-01-04-5": effect("ledgerlock.store:write_atomic", "os.replace patched to raise between temp write and replace", {"file_bytes": "unchanged"}),
    "AC-STORY-01-04-6": effect("ledgerlock.store:write_atomic", "observe the temp file's directory", {"temp_dir": "same as target"}),
    # ---- STORY-01-05 / 01-06 (Ledger instance methods over a JSONL file)
    "AC-STORY-01-05-1": effect("ledgerlock.ledger:Ledger.append", "fresh path; append put k {v:1} r1 100", {"lines": 1, "prev_hash": "GENESIS", "hash": "line_hash(GENESIS, line)"}),
    "AC-STORY-01-05-2": effect("ledgerlock.ledger:Ledger.append", "second append", {"prev_hash": "first line's hash"}),
    "AC-STORY-01-05-3": effect("ledgerlock.ledger:Ledger.append", "append with empty key on an empty ledger", {"raises": "ValueError", "file_created": False}),
    "AC-STORY-01-05-4": effect("ledgerlock.ledger:Ledger.append", "fresh instance over an existing JSONL", {"prev_hash": "tail of the file"}),
    "AC-STORY-01-05-5": effect("ledgerlock.ledger:Ledger.append", "a separate process opens the path after append", {"line_present": True, "final_byte": "\\n"}),
    "AC-STORY-01-06-1": effect("ledgerlock.ledger:Ledger.append", "same rid replay", {"replayed": True, "committed": False, "chain_length": "unchanged"}),
    "AC-STORY-01-06-2": effect("ledgerlock.ledger:Ledger.append", "different rid on a committed key", {"raises": "ConflictError", "file_bytes": "unchanged"}),
    "AC-STORY-01-06-3": effect("ledgerlock.ledger:Ledger.append", "put after a tombstone with a different rid", {"raises": "ConflictError"}),
    "AC-STORY-01-06-4": effect("ledgerlock.ledger:Ledger.append", "put after a tombstone with the same rid", {"replayed": True, "committed": False}),
    "AC-STORY-01-06-5": effect("ledgerlock.ledger:Ledger.append", "NFD key replay of an NFC-committed rid", {"replayed": True, "key": NFC_E}),
    # ---- STORY-02-01 / 02-02
    "AC-STORY-02-01-1": effect("ledgerlock.ledger:Ledger.verify", "N valid lines", {"returns": {"ok": True, "first_bad_index": None}}),
    "AC-STORY-02-01-2": effect("ledgerlock.ledger:Ledger.verify", "zero-byte JSONL", {"returns": {"ok": True, "first_bad_index": None}}),
    "AC-STORY-02-01-3": effect("ledgerlock.ledger:Ledger.verify", "missing JSONL path", {"raises": "FileNotFoundError"}),
    "AC-STORY-02-01-4": effect("ledgerlock.ledger:Ledger.verify", "hash of line i overwritten out of band", {"returns": {"ok": False, "first_bad_index": "i"}}),
    "AC-STORY-02-01-5": effect("ledgerlock.ledger:Ledger.verify", "value of line i mutated out of band", {"returns": {"ok": False, "first_bad_index": "i"}}),
    "AC-STORY-02-02-1": effect("ledgerlock.ledger:Ledger.snapshot", "put a, c, b", {"keys_order": ["a", "b", "c"], "stable": True}),
    "AC-STORY-02-02-2": effect("ledgerlock.ledger:Ledger.snapshot", "delete with a different rid conflicts; snapshot unchanged", {"returns": {"k": "v"}}),
    "AC-STORY-02-02-3": effect("ledgerlock.ledger:Ledger.snapshot", "tombstone on an uncommitted key", {"absent_key": "k2"}),
    "AC-STORY-02-02-4": effect("ledgerlock.ledger:Ledger.snapshot", "NFD put then NFC replay", {"returns": {NFC_E: "v"}}),
    "AC-STORY-02-02-5": effect("ledgerlock.ledger:Ledger.snapshot", "two instances over one chain", {"equal": True}),
    # ---- STORY-03-01 / 03-02
    "AC-STORY-03-01-1": effect("ledgerlock.ledger:Ledger.apply_batch", "3 conflict-free puts on an empty ledger", {"lines": 3, "first_prev_hash": "GENESIS", "verify_ok": True}),
    "AC-STORY-03-01-2": effect("ledgerlock.ledger:Ledger.apply_batch", "replay element then a new key", {"lines_added": 1}),
    "AC-STORY-03-01-3": effect("ledgerlock.ledger:Ledger.apply_batch", "conflict inside the batch at index 1", {"raises": "ConflictError", "batch_index": 1, "file_bytes": "unchanged"}),
    "AC-STORY-03-01-4": effect("ledgerlock.ledger:Ledger.apply_batch", "conflict at element 0", {"raises": "ConflictError", "batch_index": 0, "file_bytes": "unchanged"}),
    "AC-STORY-03-01-5": effect("ledgerlock.ledger:Ledger.apply_batch", "os.replace patched to raise", {"file_bytes": "unchanged", "verify_ok": True}),
    "AC-STORY-03-02-1": effect("ledgerlock.ledger:Ledger.repair_tail", "truncated final line over a valid chain", {"final_line_removed": True, "verify_ok": True, "final_byte": "\\n"}),
    "AC-STORY-03-02-2": effect("ledgerlock.ledger:Ledger.repair_tail", "clean JSONL", {"file_bytes": "unchanged"}),
    "AC-STORY-03-02-3": effect("ledgerlock.ledger:Ledger.repair_tail", "truncated tail and mid-chain corruption", {"file_bytes": "unchanged", "verdict": "earlier corruption"}),
    "AC-STORY-03-02-4": effect("ledgerlock.ledger:Ledger.repair_tail", "tail line parses, hash broken", {"file_bytes": "unchanged", "verdict": "corruption"}),
    # ---- STORY-04-01 / 04-02 / 04-03 (the CLI)
    "AC-STORY-04-01-1": cli(["snapshot", "<ledger>"], exit_code=2),
    "AC-STORY-04-01-2": cli(["verify"], exit_code=2, stdout=""),
    "AC-STORY-04-01-3": cli(["--help"], exit_code=0, note="stdout usage names verify, snapshot, apply, repair-tail"),
    "AC-STORY-04-01-4": cli(["verify", "<ledger>"], exit_code=0, stdout="", stderr_prefix="verify", setup="a fresh JSONL via Ledger.append"),
    "AC-STORY-04-01-5": cli(["snapshot", "<ledger>", "--out", "<snap>"], exit_code=0, stdout="", setup="a fresh JSONL", note="<snap> equals the canonical snapshot bytes"),
    "AC-STORY-04-01-6": cli(["apply", "--batch", "<batch.json>", "<ledger>"], exit_code=0, stdout="", setup="three conflict-free puts"),
    "AC-STORY-04-01-7": cli(["repair-tail", "<ledger>"], exit_code=0, stdout="", setup="a clean JSONL"),
    "AC-STORY-04-02-1": cli(["apply", "--batch", "<missing>", "<ledger>"], exit_code=3, stdout=""),
    "AC-STORY-04-02-2": cli(["apply", "--batch", "<b.json>", "<ledger>"], exit_code=4, stdout="", setup="conflict at element 0"),
    "AC-STORY-04-02-3": cli(["verify", "<ledger>"], exit_code=5, stdout="", setup="line 17 mutated out of band"),
    "AC-STORY-04-02-4": cli(["repair-tail", "<ledger>"], exit_code=5, stdout="", setup="mid-chain corruption at line 17"),
    "AC-STORY-04-03-1": cli(["verify", "<ledger>"], exit_code=0, stdout="", stderr_prefix="verify"),
    "AC-STORY-04-03-2": cli(["apply", "--batch", "<b.json>", "<ledger>"], exit_code=0, stdout="", stderr_prefix="apply"),
    "AC-STORY-04-03-3": cli(["snapshot", "<ledger>", "--out", "<snap>"], exit_code=0, stdout="", stderr_prefix="snapshot"),
    "AC-STORY-04-03-4": cli(["repair-tail", "<ledger>"], exit_code=0, stdout="", stderr_prefix="repair-tail"),
    "AC-STORY-04-03-5": cli(["<any success path>"], exit_code=0, stdout=""),
    # ---- STORY-05-01 / 05-02 / 05-03 (tests and gates as subjects)
    "AC-STORY-05-01-1": test_gate("tests.test_property_roundtrip:run", "50 seeded random mutation sequences", {"verify_ok": True, "snapshot_stable": True}),
    "AC-STORY-05-01-2": test_gate("tests.test_property_roundtrip:run", "a sequence that raises ConflictError", {"file_bytes": "unchanged past the prefix"}),
    "AC-STORY-05-01-3": test_gate("tests.test_property_roundtrip:run", "unittest discover and pytest", {"same_counts": True}),
    "AC-STORY-05-02-1": test_gate("coverage:report", "coverage run -m unittest discover; coverage report --include=ledgerlock/*", {"line_coverage_min": 85}),
    "AC-STORY-05-02-2": test_gate("pytest:main", "pytest vs unittest discover", {"same_counts": True}),
    "AC-STORY-05-02-3": test_gate("coverage:report", "tests/ excluded from measurement", {"excluded": "tests/"}),
    "AC-STORY-05-03-1": tree(r"^(import|from) (socket|subprocess|requests|http|urllib|asyncio|ssl|multiprocessing|ctypes|http\.server|http\.client|socketserver)", note="the same prohibition as AC-STORY-01-01-4, preserved"),
    "AC-STORY-05-03-2": tree(r"os\.system|subprocess\.|socket\.", note="the same prohibition as AC-STORY-01-01-5, preserved"),
}


def v1_rows() -> list[dict]:
    return json.loads((ROOT / V1_AUDIT_REL).read_text(encoding="utf-8"))["rows"]


def build_workload(baseline: str) -> dict:
    """PLAN-V2.1 as V2 objects, through the kernel: requirements, contracts (the contract rule may refuse), specs (the
    compiler may refuse), the plan, and the StaticPlanAdmissionEngine's nine checks. Every refusal is typed and kept."""
    from aisef2.arch.enums import ObligationRole, Polarity, SubjectAbsence, SubjectKind
    from aisef2.plan import static_admission as sa
    from aisef2.plan.obligation import EXPECTED_AT_PARENT, NOT_PREREGISTERED, Plan, PlanObligation
    from aisef2.probe.calibration import ProbeCapabilityCalibration
    from aisef2.probe.protocol import ProbeRegistry
    from aisef2.probe.python_callable import METADATA, PythonCallableProbe
    from aisef2.product.approval import ContractApproval, Requirement
    from aisef2.product.compiler import CompileError, ProbeRef, compile_spec
    from aisef2.product.contract import BehaviorContract, ContractError, Subject
    from aisef2.orchestrate import seam
    rows = v1_rows()
    assert len(rows) == 77 and set(V2) == {r["ac_id"] for r in rows}, "the V2 table covers exactly the 77 frozen criteria"
    table = json.loads((ROOT / MIGRATION_TABLE_REL).read_text(encoding="utf-8"))
    reqs = {fr: Requirement.create(id=fr, text=title, source=f"docs/requirements.md@{REQUIREMENTS_SHA256[:12]} (PRD {fr})") for fr, title in FR_TITLES.items()}
    contracts, approvals, specs, criteria = {}, [], {}, []
    probes = {SubjectKind.PYTHON_CALLABLE: ProbeRef(PythonCallableProbe.id, PythonCallableProbe.digest)}
    approver = "human:owner (P10 / QP-10 authorization 2026-09-28; the V2 form authored under it, the criteria as V1 froze them)"
    for r in rows:
        t = V2[r["ac_id"]]
        legacy = seam.resolve(r["ac_id"], r["proof_mode"], table, SubjectAbsence[t["absence"]])   # the seam: role and polarity from the table
        role, polarity = legacy.role.value, legacy.polarity.value
        entry = {"ac_id": r["ac_id"], "story": r["story"], "requirement": r["requirement"], "v1_mode": r["proof_mode"], "role": role, "polarity": polarity,
                 "subject_kind": t["kind"], "locator": t["locator"], "stimulus": t["stimulus"], "observable": t["observable"], "subject_absence": t["absence"],
                 "depends_on_stories": list(r["depends_on"]), "criterion": r["criterion"], "note": t.get("note", ""), "v2_status": None, "typed_refusal": None}
        try:
            c = BehaviorContract.create(id=f"BC-{r['ac_id']}", requirement_ids=(r["requirement"],), subject=Subject(SubjectKind(t["kind"]), t["locator"]),
                                        stimulus=t["stimulus"], observable=t["observable"], polarity=Polarity[polarity],
                                        subject_absence=SubjectAbsence[t["absence"]], rationale=r["criterion"])
        except ContractError as e:
            entry.update(v2_status="REFUSED_BY_CONTRACT_RULE", typed_refusal=f"ContractError: {e}")
            criteria.append(entry)
            continue
        contracts[c.id] = c
        a = ContractApproval(r["requirement"], reqs[r["requirement"]].requirement_hash, c.id, c.contract_hash, approver, 1790000000.0, ())
        approvals.append(a)
        try:
            s = compile_spec(c, requirements=reqs, approvals=approvals, probes=probes)
        except CompileError as e:
            entry.update(v2_status="REFUSED_BY_COMPILER", typed_refusal=f"CompileError: {e}", contract_hash=c.contract_hash)
            criteria.append(entry)
            continue
        specs[s.id] = s
        entry.update(v2_status="COMPILED", spec_id=s.id, semantic_hash=s.semantic_hash, contract_hash=c.contract_hash)
        criteria.append(entry)
    by_story: dict[str, list[str]] = {}
    for e in criteria:
        by_story.setdefault(e["story"], []).append(e["ac_id"])
    obligations = tuple(PlanObligation(e["ac_id"], e.get("spec_id") or f"NO-SPEC-{e['ac_id']}", e["story"], ObligationRole[e["role"]],
                                       EXPECTED_AT_PARENT[ObligationRole[e["role"]]], tuple(c for s in e["depends_on_stories"] for c in by_story.get(s, ())),
                                       f"{e['story']} owns {e['ac_id']} ({e['v1_mode']} / {e['requirement']}) as PLAN-V2.1 froze it") for e in criteria)
    plan = Plan.create(id="W1-LEDGERLOCK-PLAN-V2.1", baseline=baseline, obligations=obligations, plan_quality_policy=NOT_PREREGISTERED)
    cal = json.loads((ROOT / P2_CALIBRATION_REL).read_text(encoding="utf-8"))["calibrations"]
    cals = tuple(ProbeCapabilityCalibration(c["probe_id"], c["probe_digest"], c["observation_class"], c["positive_fixture"], c["negative_fixture"], c["demonstrated_at"]) for c in cal)
    inputs = sa.AdmissionInputs(reqs, contracts, tuple(approvals), specs, {SubjectKind.PYTHON_CALLABLE: PythonCallableProbe()}, cals, ProbeRegistry([METADATA]))
    result = sa.StaticPlanAdmissionEngine().admit(plan, inputs)
    admitted_specs = [e for e in criteria if e["v2_status"] == "COMPILED"]
    unsupported = [p for c in result.checks if c.name == "probe_calibration" for p in c.problems if "does not support" in p]
    for e in admitted_specs:
        if any(e["spec_id"] in p for p in unsupported):
            e["v2_status"], e["typed_refusal"] = "UNSUPPORTED_OBSERVATION", next(p for p in unsupported if e["spec_id"] in p)
    counts = {}
    for e in criteria:
        counts[e["v2_status"]] = counts.get(e["v2_status"], 0) + 1
    kinds = {}
    for e in criteria:
        kinds[e["subject_kind"]] = kinds.get(e["subject_kind"], 0) + 1
    return {"plan": {"id": plan.id, "plan_hash": plan.plan_hash, "baseline": baseline, "stories": len(by_story), "criteria": len(criteria),
                     "obligations_by_role": {r: sum(1 for e in criteria if e["role"] == r) for r in ("INTRODUCE", "PRESERVE", "VERIFY")},
                     "v1_plan_commit": LEDGERLOCK_PLAN_COMMIT, "v1_modes": {m: sum(1 for e in criteria if e["v1_mode"] == m) for m in sorted({e["v1_mode"] for e in criteria})},
                     "migration_table": {"path": MIGRATION_TABLE_REL, "sha256": _sha((ROOT / MIGRATION_TABLE_REL).read_bytes())}},
            "requirements": {fr: {"hash": reqs[fr].requirement_hash, "title": FR_TITLES[fr]} for fr in FR_TITLES},
            "criteria": criteria, "counts_by_v2_status": counts, "counts_by_subject_kind": kinds,
            "expressible_by_cycle1_probe": [e["ac_id"] for e in criteria if e["v2_status"] == "COMPILED"],
            "static_admission": {"engine_digest": result.engine_digest, "admitted": result.admitted, "result_digest": result.result_digest,
                                 "checks": [{"number": c.number, "name": c.name, "passed": c.passed, "problems": list(c.problems)} for c in result.checks]},
            "probe": {"id": PythonCallableProbe.id, "digest": PythonCallableProbe.digest, "kinds_with_a_probe": ["python_callable"],
                      "kinds_without_a_probe": sorted(k.value for k in SubjectKind if k is not SubjectKind.PYTHON_CALLABLE)}}


# =============================================================================================== 3. the execution profile

def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def opencode_identity() -> dict:
    exe = shutil.which("opencode")
    version = None
    if exe:
        try:
            version = subprocess.run([exe, "--version"], capture_output=True, text=True, encoding="utf-8", timeout=60).stdout.strip()
        except (OSError, subprocess.SubprocessError) as e:
            version = f"unavailable: {type(e).__name__}"
    cfg = pathlib.Path(os.environ.get("XDG_CONFIG_HOME") or (pathlib.Path.home() / ".config")) / "opencode" / "opencode.json"
    route, provider_digest, base_url = None, None, None
    if cfg.exists():
        try:
            d = json.loads(cfg.read_text(encoding="utf-8"))
            route = d.get("model")
            prov = d.get("provider", {}).get(str(route).split("/")[0], {}) if route else {}
            opts = {k: v for k, v in (prov.get("options") or {}).items() if k.lower() not in ("apikey", "api_key", "token", "secret")}
            base_url = opts.get("baseURL")
            provider_digest = _sha(json.dumps({"npm": prov.get("npm"), "options": opts, "models": sorted((prov.get("models") or {}).keys())}, sort_keys=True).encode())
        except (OSError, ValueError):
            pass
    return {"client": "opencode", "binary": exe, "binary_sha256": _sha(pathlib.Path(exe).read_bytes()) if exe else None, "version": version,
            "declared_route": route, "endpoint": base_url, "provider_config_digest_without_secrets": provider_digest,
            "grade": "OPAQUE", "why_opaque": "declared route and client only: no request was made, so no preflight fingerprint was measured (RFC §23)"}


def runspec_for(baseline: str, oc: dict, workload: dict) -> dict:
    from aisef2.arch.enums import Enforcement
    from aisef2.runtime.capability import opaque, verified
    from aisef2.runtime.runspec import resolve
    from validation.qualification import q4
    kernel = q4._over(q4._file_digests(("aisef2",)))
    git_exe = shutil.which("git")
    caps = [verified("kernel", kernel.encode(), Enforcement.FULL, tree=KERNEL_TREE),
            verified("python", pathlib.Path(sys.executable), Enforcement.PARTIAL, version=platform.python_version()),
            verified("git", pathlib.Path(git_exe), Enforcement.PARTIAL) if git_exe else opaque("git", Enforcement.PARTIAL, note="absent"),
            verified("probe.python_callable", workload["probe"]["digest"].encode(), Enforcement.PARTIAL),
            opaque("developer", Enforcement.PARTIAL, client="opencode", route=str(oc["declared_route"]), version=str(oc["version"])),
            opaque("reviewer", Enforcement.PARTIAL, client="opencode", route=str(oc["declared_route"]), version=str(oc["version"])),
            opaque("scanner", Enforcement.PARTIAL, tool="ruff", mode="lint as an informational scanner")]
    spec = resolve(caps, {"workload": {"value": "LedgerLock", "layer": "p10"}, "benchmark_class": {"value": BENCHMARK_CLASS, "layer": "p10"},
                          "plan_hash": {"value": workload["plan"]["plan_hash"], "layer": "plan"}, "requirements_sha256": {"value": REQUIREMENTS_SHA256, "layer": "workload"},
                          "limits": {"value": {"DEVELOPER": 1, "PLAN": 0, "ENVIRONMENT": 1, "PROVIDER": 1, "INTEGRATION": 0, "REVIEW": 1, "SECURITY": 1}, "layer": "p10"}}, baseline)
    return {"runspec_hash": spec.runspec_hash, "aggregate_min_grade": spec.aggregate_min_grade.value, "revision": spec.revision,
            "capabilities": [{"name": c.name, "grade": c.grade.value, "enforcement": c.enforcement.value, "binding": dict(c.tuple_)} for c in spec.capabilities],
            "kernel_digest": kernel, "q6_eligible": spec.aggregate_min_grade.value != "OPAQUE"}


# =============================================================================================== 4. the run

def ledgerlock_baseline() -> dict:
    """The workload's repository identity: the frozen plan commit is the baseline; requirements at that commit hash to
    the frozen value. Read only; nothing here writes to the LedgerLock repository."""
    from aisef2.orchestrate.workspace import git
    if not (LEDGERLOCK_REPO / ".git").exists():
        return {"repo": str(LEDGERLOCK_REPO), "present": False}
    head = git(LEDGERLOCK_REPO, "rev-parse", LEDGERLOCK_PLAN_COMMIT).stdout.strip()
    req = subprocess.run(["git", "-C", str(LEDGERLOCK_REPO), "show", f"{LEDGERLOCK_PLAN_COMMIT}:docs/requirements.md"], capture_output=True, encoding="utf-8", text=True)
    epics = subprocess.run(["git", "-C", str(LEDGERLOCK_REPO), "show", f"{LEDGERLOCK_PLAN_COMMIT}:_bmad-output/epics.md"], capture_output=True, encoding="utf-8", text=True)
    return {"repo": str(LEDGERLOCK_REPO), "present": True, "baseline": head, "baseline_is_the_plan_commit": head == LEDGERLOCK_PLAN_COMMIT,
            "requirements_sha256": _sha(req.stdout.encode("utf-8")), "requirements_match_frozen": _sha(req.stdout.encode("utf-8")) == REQUIREMENTS_SHA256,
            "epics_sha256": _sha(epics.stdout.encode("utf-8")), "tree": git(LEDGERLOCK_REPO, "rev-parse", f"{LEDGERLOCK_PLAN_COMMIT}^{{tree}}").stdout.strip()}


def historical_runs() -> list[dict]:
    out = []
    for name in ("1", "2", "3", "v21-run1", "v21-run2"):
        p = ROOT / f"closure-evidence/hardening/W1-LEDGERLOCK-{name}.json"
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        st = d.get("stories") or {}
        out.append({"run": name, "generated": d.get("generated"), "kernel": "V1 aisef 1.7.6 (f52df75, tree 4359f347)", "stories_recorded": len(st),
                    "done": sum(1 for v in st.values() if v.get("status") == "done"), "failed": sum(1 for v in st.values() if v.get("status") == "failed"),
                    "progress": d.get("progress"), "classification": "DEVELOPMENT / REGRESSION (V1, PLAN-V2 or V2.1; no generalization)"})
    return out


def run(out_dir: pathlib.Path) -> dict:
    from validation.qualification import q4_aggregate as A
    started = time.time()
    base = ledgerlock_baseline()
    if not base.get("present") or not base.get("requirements_match_frozen"):
        raise SystemExit(f"the LedgerLock workload is not where the freeze says or its requirements changed: {base}")
    workload = build_workload(base["baseline"])
    oc = opencode_identity()
    spec = runspec_for(base["baseline"], oc, workload)
    admitted = workload["static_admission"]["admitted"]
    events: list = []
    execution = {"attempted": admitted, "reason": None, "model_requests": 0, "provider_calls": 0}
    if admitted:
        execution["reason"] = "the plan was admitted; the live run through story_runner would start here"
        raise SystemExit("P10: the plan was admitted — the live path is not wired in this harness revision; stop and report")
    execution["reason"] = ("the StaticPlanAdmissionEngine did not admit the plan: no story begins, no provider request is made, delivery is not reached "
                           "(RFC §12: a plan freezes only if admitted)")
    roles = {e["ac_id"]: e["role"] for e in workload["criteria"]}
    delivery = delivery_verdict_of(events, plan_admitted=admitted)
    metrics = plan_quality_metrics(events, roles)
    policy, at, policy_path = preregistered_policy(out_dir)
    plan_quality = plan_quality_verdict_of(metrics, policy, policy_preregistered_at=at, run_started_at=started)
    verdict = RunVerdict(delivery, plan_quality)
    # the mechanical prohibitions, executed (not merely omitted), with their outcomes recorded
    prohibitions = {}
    for target in ("SEALED", "HOLDOUT", "EVALUATING"):
        try:
            LEDGERLOCK.transition(target)
            prohibitions[target] = "ACCEPTED (defect)"
        except SealingRefused as e:
            prohibitions[target] = f"REJECTED: {e}"
    try:
        Recorder().record(benchmark_class=BENCHMARK_CLASS, generalization_claim="POSITIVE", cohort_state="DEVELOPMENT", verdict=verdict)
        prohibitions["generalization_claim=POSITIVE"] = "ACCEPTED (defect)"
    except ClaimRefused as e:
        prohibitions["generalization_claim=POSITIVE"] = f"REJECTED: {e}"
    try:
        Recorder().record(benchmark_class=BENCHMARK_CLASS, generalization_claim="NONE", cohort_state="DEVELOPMENT", verdict=verdict, qualification_sample_size=1)
        prohibitions["qualification_sample_size"] = "ACCEPTED (defect)"
    except ClaimRefused as e:
        prohibitions["qualification_sample_size"] = f"REJECTED: {e}"
    try:
        overall_verdict(verdict)
        prohibitions["overall_verdict"] = "ACCEPTED (defect)"
    except ClaimRefused as e:
        prohibitions["overall_verdict"] = f"REJECTED: {e}"
    conf = A.conformance()
    p9 = {"closure-evidence/v2/Q5/REPRODUCTION.json": _sha((ROOT / "closure-evidence/v2/Q5/REPRODUCTION.json").read_bytes()),
          "closure-evidence/v2/P9-ACCEPTANCE.json": _sha((ROOT / "closure-evidence/v2/P9-ACCEPTANCE.json").read_bytes())}
    checks = workload["static_admission"]["checks"]
    failing = [c["name"] for c in checks if not c["passed"]]
    rec = Recorder().record(
        record="AISEF V2 — P10 LEDGERLOCK REGRESSION (DEVELOPMENT / REGRESSION BENCHMARK ONLY)", rung="P10 / QP-10",
        authority="owner's P10 / QP-10 EXECUTION AUTHORIZATION (2026-09-28)", written=C.now(),
        purpose="does the current framework regress on this known development workload? — not: how well would AISEF perform on unseen projects",
        semantic_candidate=SEMANTIC_CANDIDATE, aisef2_tree=KERNEL_TREE, head_kernel_tree=C.git("rev-parse", "HEAD:aisef2"),
        repository_execution_commit=C.git("rev-parse", "HEAD"), harness_digest=_harness_digest(),
        workload={"id": "LedgerLock", "benchmark_class": BENCHMARK_CLASS, "repository": base, "plan_freeze": V1_FREEZE_REL, "plan_commit": LEDGERLOCK_PLAN_COMMIT,
                  "requirements_sha256": REQUIREMENTS_SHA256, "criteria_source": V1_AUDIT_REL, "v2_table_digest": _sha(json.dumps(V2, sort_keys=True, ensure_ascii=False).encode())},
        requirements_hash=_sha(json.dumps({k: v["hash"] for k, v in workload["requirements"].items()}, sort_keys=True).encode()),
        plan_identity={"id": workload["plan"]["id"], "plan_hash": workload["plan"]["plan_hash"], "baseline": workload["plan"]["baseline"], "stories": workload["plan"]["stories"],
                       "criteria": workload["plan"]["criteria"], "obligations_by_role": workload["plan"]["obligations_by_role"], "v1_modes": workload["plan"]["v1_modes"]},
        execution_profile={"runspec_hash": spec["runspec_hash"], "aggregate_min_grade": spec["aggregate_min_grade"], "q6_eligible": spec["q6_eligible"],
                           "capabilities": spec["capabilities"], "model": oc, "probe": workload["probe"]},
        run_identity={"run_id": None, "journal": None, "note": "no RunScope began: the plan was not admitted; there is no journal to name"},
        static_admission=workload["static_admission"], workload_fit={"counts_by_v2_status": workload["counts_by_v2_status"], "counts_by_subject_kind": workload["counts_by_subject_kind"],
                                                                    "expressible_by_cycle1_probe": workload["expressible_by_cycle1_probe"], "kinds_without_a_probe": workload["probe"]["kinds_without_a_probe"]},
        execution=execution, cohort_state=CohortState.DEVELOPMENT.value, benchmark_class=BENCHMARK_CLASS, generalization_claim=GENERALIZATION_CLAIM,
        verdict=verdict, delivery_verdict_derivation="from the run's journal events and the plan admission only; no plan-quality input",
        plan_quality_metrics=metrics, plan_quality_policy={"preregistered": at is not None, "path": policy_path, "preregistered_at": at,
                                                            "thresholds": {"max_pre_satisfied_introduce_ratio": policy.max_pre_satisfied_introduce_ratio,
                                                                           "max_fully_pre_satisfied_stories": policy.max_fully_pre_satisfied_stories,
                                                                           "max_unattributed_plan_drift": policy.max_unattributed_plan_drift}},
        current_product_correctness={"stories_total": workload["plan"]["stories"], "stories_delivered": 0, "stories_failed": 0, "stories_pre_satisfied": 0, "retries": 0, "rollbacks": 0,
                                     "product_proof_results": [], "verifier_agreements": 0, "verifier_disagreements": 0, "engineering_adequacy": [], "review_findings": [],
                                     "security_findings": [], "post_merge_reproof": [], "note": "no story ran: nothing is summarised away; every count is zero because delivery was not reached"},
        prohibitions=prohibitions, regression_summary={
            "question": "does the cycle-1 V2 framework regress on LedgerLock?",
            "finding": f"the plan is not admitted by the V2 StaticPlanAdmissionEngine (checks failing: {failing}); {len(workload['expressible_by_cycle1_probe'])} of 77 criteria are "
                       "provable by the one cycle-1 probe kind (python_callable: exists / returns / raises over JSON arguments); the rest need cli_invocation, process_effect "
                       "and file_artifact probes the cycle-1 kernel does not implement, or observables (bytes, a constant's value, instance-method effects) the probe has no class for",
            "regression_relative_to_v1": "V1 (aisef 1.7.6) ran this plan end to end (best run 11/16 stories done); V2 cycle 1 reaches no story: a proof-kind coverage regression, "
                                         "typed by the engine, not a delivery verdict",
            "historical_runs": historical_runs(), "label": "DEVELOPMENT / REGRESSION; no generalization, no ranking of models or providers"},
        conformance=conf, p9_evidence=p9, p8_evidence={"closure-evidence/v2/Q4/DIFFERENTIAL.json": _sha((ROOT / "closure-evidence/v2/Q4/DIFFERENTIAL.json").read_bytes())},
        p7_evidence={rel: _sha((ROOT / rel).read_bytes()) for rel in A.P7_EVIDENCE}, seals={rel: _sha((ROOT / rel).read_bytes()) for rel in A.SEALS},
        v1_evidence={"baseline": _sha((ROOT / "closure-evidence/v2/V1-EVIDENCE-BASELINE.json").read_bytes()), "w0": _sha((ROOT / A.W0_REL).read_bytes()), "product_tree": C.git("rev-parse", "HEAD:aisef")},
        residual_processes={"from_journal": 0, "owned_range": "see the owned-run record beside this file"}, platform={"system": platform.system().lower(), "python": platform.python_version()},
        stop_rules={"kernel_tree_is_the_candidates": C.git("rev-parse", "HEAD:aisef2") == KERNEL_TREE, "plan_retuned": False, "kernel_repaired": False,
                    "historical_evidence_rewritten": False, "cohort_sealed": False, "generalization_claimed": False},
        finished=C.now(),
    )
    (out_dir / "WORKLOAD.json").write_text(C.render({"record": "AISEF V2 — P10 LedgerLock workload in V2 form (PLAN-V2.1's 77 criteria, their kinds, the kernel's typed answers)",
                                                     **{k: v for k, v in workload.items() if k != "static_admission"}, "static_admission": workload["static_admission"]}), encoding="utf-8")
    (out_dir / "LEDGERLOCK-REGRESSION.json").write_text(C.render(rec), encoding="utf-8")
    return rec


def _harness_digest() -> str:
    from validation.qualification import q4
    return q4._over(q4._file_digests(HARNESS_FILES))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--conformance", choices=("start", "end"))
    ap.add_argument("--out", default=OUT_REL)
    a = ap.parse_args(argv)
    out_dir = (ROOT / a.out) if not os.path.isabs(a.out) else pathlib.Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    import tests.v2  # noqa: F401 — invariants I–IX armed at tier ROOT
    if a.conformance:
        from validation.qualification import q4_aggregate as A
        rec = A.conformance()
        (out_dir / f"CONFORMANCE-{a.conformance}.json").write_text(C.render(rec), encoding="utf-8")
        ok = rec["freeze_conformance"]["pass"] and rec["v1_evidence_guard"]["pass"] and rec["w0"]["unchanged"]
        print(f"conformance {a.conformance}: F1-F11 {rec['freeze_conformance']['summary']} all {'PASS' if ok else 'FAIL'}")
        return 0 if ok else 1
    if a.run:
        if (out_dir / "LEDGERLOCK-REGRESSION.json").exists():
            print("REFUSED: LEDGERLOCK-REGRESSION.json exists — a rerun is a new attempt directory")
            return 2
        rec = run(out_dir)
        print(f"P10: delivery {rec['delivery_verdict']} plan_quality {rec['plan_quality_verdict']} generalization {rec['generalization_claim']} "
              f"benchmark {rec['benchmark_class']} admitted {rec['static_admission']['admitted']} fit {rec['workload_fit']['counts_by_v2_status']} "
              f"prohibitions { {k: v[:8] for k, v in rec['prohibitions'].items()} }")
        return 0
    ap.error("--run or --conformance")
    return 2


if __name__ == "__main__":
    sys.exit(main())
