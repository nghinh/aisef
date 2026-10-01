"""Q4 — the fresh 100,000-trace differential on the exact candidate (owner's "P8 / QP-8 EXECUTION AUTHORIZATION";
RFC §27; F1, F2, F11).

    python -P validation/qualification/q4.py --freeze                  # SUBJECT.json: the frozen subject and the preregistered model
    python -P validation/qualification/q4.py --chunk K [--attempt N]   # one chunk: seeds K*10000 .. K*10000+9999 -> chunks/chunk-K.json

Every trace is a run the P3 generator builds from its own model of RFC §17 (tests/v2/p3/journal_gen.py, journal
format 3, the failure pool widened to the whole taxonomy), reconstructed through the kernel's journal reader. For each
of the six control-critical projections (the closed list, F11) three answers are compared: the kernel's incremental
projection (Folder.advance over the events), the kernel's from-scratch fold of the whole journal, and the independent
reference model (tests/v2/refmodel, which imports nothing of the kernel; validation/v2/refmodel_independence.py bars
it). Equal, canonically, or a divergence. On every tenth seed the same triple is compared at every journal prefix.
A trace ends in exactly one terminal class: MATCHED, DIVERGENCE, INVARIANT_VIOLATION (an InvariantError escaped; the
nine invariants are armed at tier ROOT by importing tests.v2) or EXCEPTION (anything else escaped). A seed with no
terminal class is a silent skip, which the aggregator finds. Nothing is retried, nothing is dropped, nothing is
reclassified after the fact: a chunk record is written once, and a rerun is a new attempt file beside the old one.

Cycle 2 (QP-2.7, owner ruling 2026-09-30): the same differential, fresh, on the Cycle-2 candidate (the QP-2.6 subject).
Changed here: the subject pointer, the output directory, and the one extension the Cycle-2 qualification plan names
(§5) — every probe/evaluated record names one of the active probe identities (the generator's `probe_ids`, a stream of
its own) and the coverage model gains the category `probe_id`, so the coverage names every active probe id. The
differential itself (the six projections compared three ways, the terminal classes, the prefix rule) is unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import pathlib
import platform
import socket
import sys
import time
import traceback

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.qualification import common as C  # noqa: E402

OUT_REL = "closure-evidence/v2/cycle2/Q4"
SEMANTIC_CANDIDATE = C.SEMANTIC_CANDIDATE   # the Cycle-2 candidate (QP-2.6)
KERNEL_TREE = C.KERNEL_TREE
#: the active probe identities (aisef2/probe/catalog.py), one named on each probe/evaluated record of a trace
PROBE_IDS = ("probe.cli_invocation", "probe.file_artifact", "probe.process_effect", "probe.python_callable_v2")
CHUNKS, CHUNK_SIZE, SEED_BASE = 10, 10_000, 0
TOTAL = CHUNKS * CHUNK_SIZE
PREFIX_EVERY = 10   # seeds with seed % 10 == 0: the triple compared at every journal prefix (10,000 traces)
CLASSES = ("MATCHED", "DIVERGENCE", "INVARIANT_VIOLATION", "EXCEPTION")   # what a worker assigns; SILENT_SKIP is the aggregator's
PILOT_SEEDS = (100_000, 102_000)   # the design pilot that established reachability: outside the schedule, never counted

#: the identity every chunk binds: the kernel modules the differential exercises, the reference models, the generator,
#: this harness — one digest each, and one over all of them
KERNEL_FILES = ("aisef2",)   # every module of the kernel: the tree the candidate froze, digested file by file
REFERENCE_FILES = ("tests/v2/refmodel",)
GENERATOR_FILES = ("tests/v2/p3/journal_gen.py", "tests/v2/p3/test_reference_models.py")
HARNESS_FILES = ("validation/qualification/q4.py", "validation/qualification/q4_aggregate.py", "validation/qualification/q4_run.sh")

# --------------------------------------------------------------------------------------------- the preregistered model

TAXONOMY_CODES = ("PROBE_UNRUNNABLE", "PROBE_INVALID_SPEC", "CONTRACT_UNSATISFIED", "SUBJECT_ABSENT_AT_CANDIDATE", "PRECONDITION_BROKEN",
                  "PLAN_CONTRADICTION", "POST_MERGE_REGRESSION", "POST_MERGE_SUBJECT_LOST", "NON_CONTROLLER_SIGNAL", "MISSING_CREDENTIAL",
                  "INVALID_CREDENTIAL", "PROVIDER_UNAVAILABLE", "UNKNOWN", "VERIFIER_DISAGREEMENT", "PROBE_MISMATCH", "MERGE_CONFLICT",
                  "TESTS_UNRUNNABLE", "TESTS_INADEQUATE", "REVIEW_FINDING", "SECURITY_FINDING", "CAPABILITY_UNRUNNABLE",
                  "RESOURCE_ACQUISITION_FAILED")
#: the pool an active story draws from: the generator's format-3 pool plus NON_CONTROLLER_SIGNAL (V2-003), so every
#: taxonomy code is drawn; the blocked dispositions and the post-merge codes come from the generator's own tables
ACTIVE_POOL = ("CONTRACT_UNSATISFIED", "SUBJECT_ABSENT_AT_CANDIDATE", "PROVIDER_UNAVAILABLE", "PROBE_UNRUNNABLE", "INVALID_CREDENTIAL",
               "MISSING_CREDENTIAL", "UNKNOWN", "VERIFIER_DISAGREEMENT", "PROBE_MISMATCH", "MERGE_CONFLICT", "TESTS_UNRUNNABLE",
               "TESTS_INADEQUATE", "REVIEW_FINDING", "SECURITY_FINDING", "CAPABILITY_UNRUNNABLE", "RESOURCE_ACQUISITION_FAILED",
               "NON_CONTROLLER_SIGNAL")
OWNERS = ("DEVELOPER", "PLAN", "ENVIRONMENT", "PROVIDER", "INTEGRATION", "REVIEW", "SECURITY")
PREREGISTERED = {
    "disposition": ["READY", "PRE_SATISFIED", "PRECONDITION_BROKEN", "PLAN_CONTRADICTION", "PROBE_UNRUNNABLE", "PROBE_INVALID"],
    "admission": ["admitted", "blocked", "developer_call_permitted", "developer_call_not_permitted"],
    "owner": list(OWNERS),
    "fault_kind": list(TAXONOMY_CODES),
    "retryability": ["retryable", "not_retryable"],
    "outcome": ["commit", "rollback", "retry", "commit_after_retry", "rollback_after_retry", "rollback_at_max_attempts",
                "post_merge_failure", "blocked_then_retry", "blocked_then_rollback"],
    "budget_owner": ["DEVELOPER", "REVIEW", "SECURITY"],
    "drift": ["attributed", "unattributed"],
    "gate": ["check_passed", "check_failed", "decision_passed", "decision_failed"],
    "invariant": ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX"],
    "interruption": ["none", "interrupted", "abandoned", "interrupted_during_disposal", "ended_after_interrupt", "second_interrupt_abandons",
                     "dispose_then_end", "end_without_dispose"],
    "run_terminal": ["ENDED", "ABANDONED"],
    "story_terminal": ["COMMIT", "ROLLBACK"],
    "event_type": ["run/begin", "plan/frozen", "story/begin", "probe/evaluated", "story/admitted", "story/plan-drift", "provider/request",
                   "invariant/violated", "failure/observed", "gate/check", "gate/decision", "story/commit", "story/rollback", "story/retry",
                   "story/dispose", "story/end", "run/interrupted", "run/dispose-begin", "run/end"],
    "compound_pair": [f"{a}|{b}" for a, b in itertools.combinations(sorted(TAXONOMY_CODES), 2)],   # two distinct codes in one trace, sorted
    "same_story_pair": ["same_story_two_codes", "same_story_repeated_code", "retry_then_other_code", "retry_then_same_code"],
    "probe_id": list(PROBE_IDS),   # Cycle 2 (CYCLE2-QUALIFICATION-PLAN §5): the coverage names every active probe id
}
TERMINAL_CLASSES = CLASSES + ("SILENT_SKIP",)


def stories_of(seed: int) -> int:
    return 3 + seed % 5


def generate(seed: int) -> str:
    from tests.v2.p3 import journal_gen as gen
    return gen.journal(seed, stories=stories_of(seed), journal_format=3, failures=ACTIVE_POOL, probe_ids=PROBE_IDS)


# ------------------------------------------------------------------------------------------------------ identity

def _file_digests(rels) -> dict[str, str]:
    out = {}
    for rel in rels:
        p = ROOT / rel
        files = sorted(x for x in p.rglob("*.py") if "__pycache__" not in x.parts) if p.is_dir() else [p]
        for f in files:
            if f.exists():
                out[f.relative_to(ROOT).as_posix()] = hashlib.sha256(f.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    return out


def _over(digests: dict[str, str]) -> str:
    return hashlib.sha256("\n".join(f"{k} {v}" for k, v in sorted(digests.items())).encode()).hexdigest()


def identity() -> dict:
    kernel, reference, generator, harness = (_file_digests(x) for x in (KERNEL_FILES, REFERENCE_FILES, GENERATOR_FILES, HARNESS_FILES))
    import freeze_manifest as fm   # validation/v2, on the path through common
    eff, links, broken = fm.lineage(ROOT)
    dirty = [ln for ln in C.git("status", "--porcelain", "--", "aisef2", "tests/v2", "validation").splitlines() if ln.strip()]
    return {
        "semantic_candidate": SEMANTIC_CANDIDATE, "kernel_tree": KERNEL_TREE,
        "execution_commit": C.git("rev-parse", "HEAD"), "head_kernel_tree": C.git("rev-parse", "HEAD:aisef2"),
        "kernel_tree_is_the_candidates": C.git("rev-parse", "HEAD:aisef2") == KERNEL_TREE,
        "candidate_kernel_tree": C.git("rev-parse", f"{SEMANTIC_CANDIDATE}:aisef2"),
        "working_tree_clean": not dirty, "dirty": dirty,
        "kernel_digest": _over(kernel), "reference_digest": _over(reference), "generator_digest": _over(generator),
        "harness_digest": _over(harness), "files": {"kernel": kernel, "reference": reference, "generator": generator, "harness": harness},
        "rfc": {"effective_normative_digest": eff.get("rfc_normative_digest"), "effective_freeze_table_digest": eff.get("freeze_table_digest"),
                "lineage_end": pathlib.Path(links[-1]["record"]).name if links else None, "broken_links": broken},
        "seed_schedule": {"base": SEED_BASE, "chunks": CHUNKS, "chunk_size": CHUNK_SIZE, "total": TOTAL,
                          "ranges": [[SEED_BASE + k * CHUNK_SIZE, SEED_BASE + (k + 1) * CHUNK_SIZE - 1] for k in range(CHUNKS)],
                          "prefix_every": PREFIX_EVERY},
        "generator": {"journal_format": 3, "stories": "3 + seed % 5", "max_attempts": 3, "failures": list(ACTIVE_POOL),
                      "probe_ids": list(PROBE_IDS)},
        "active_catalog": _active_catalog(),
        "python": platform.python_version(), "platform": platform.system().lower(),
    }


def _active_catalog() -> dict:
    from aisef2.probe import catalog
    return {k.value: {"probe_id": e.probe_id, "digest": e.probe_digest} for k, e in sorted(catalog.active().items(), key=lambda kv: kv[0].value)}


def one_kernel_identity(ident: dict) -> str:
    """The one identity every chunk must share: candidate, tree, and the four digests."""
    return _over({k: ident[k] for k in ("semantic_candidate", "kernel_tree", "head_kernel_tree", "kernel_digest", "reference_digest",
                                         "generator_digest", "harness_digest")})


def subject_problems(ident: dict) -> list[str]:
    out = []
    if not ident["kernel_tree_is_the_candidates"]:
        out.append(f"HEAD's aisef2 tree {ident['head_kernel_tree']} is not the candidate's {KERNEL_TREE}")
    if ident["candidate_kernel_tree"] != KERNEL_TREE:
        out.append("the semantic candidate's aisef2 tree is not the frozen one")
    if not ident["working_tree_clean"]:
        out.append(f"the working tree is dirty under aisef2, tests/v2 or validation: {ident['dirty'][:5]}")
    if ident["rfc"]["broken_links"]:
        out.append(f"broken lineage links: {ident['rfc']['broken_links']}")
    if sorted(e["probe_id"] for e in ident["active_catalog"].values()) != sorted(PROBE_IDS):
        out.append(f"the active catalog {ident['active_catalog']} is not the probe set the coverage names {PROBE_IDS}")
    return out


# ---------------------------------------------------------------------------------------------- the differential

def _answers(events):
    """(incremental, from-scratch, model) canonical answers per projection id — REFUSED where the kernel or the model
    refuses the journal. Raised errors propagate: an InvariantError is an invariant violation, anything else an
    exception of the trace."""
    from aisef2.arch.enums import ControlProjection as P
    from aisef2.journal.fold import Folder, ProjectionError, fold
    from aisef2.journal.projections import PROJECTIONS
    from aisef2.product.contract import canonical, plain
    from tests.v2.refmodel import MODELS, Refused
    out = {}
    plain_events = [plain(e) for e in events]
    for pid, model in MODELS.items():
        proj = PROJECTIONS[P(pid)]
        folder, incremental = Folder(proj), None
        try:
            for e in events:
                incremental = folder.advance(e)
            incremental = canonical(incremental if events else proj.initial())
        except ProjectionError:
            incremental = "REFUSED"
        try:
            scratch = canonical(fold(proj, events))
        except ProjectionError:
            scratch = "REFUSED"
        try:
            reference = canonical(model(plain_events))
        except Refused:
            reference = "REFUSED"
        out[pid] = (incremental, scratch, reference)
    return out


def _prefix_divergences(events) -> list[dict]:
    """The triple at every prefix n, per projection: the first n where the three differ (one entry per projection)."""
    from aisef2.arch.enums import ControlProjection as P
    from aisef2.journal.fold import Folder, ProjectionError, fold
    from aisef2.journal.projections import PROJECTIONS
    from aisef2.product.contract import canonical, plain
    from tests.v2.refmodel import MODELS, Refused
    out = []
    plain_events = [plain(e) for e in events]
    for pid, model in MODELS.items():
        proj = PROJECTIONS[P(pid)]
        folder, inc_state, refused_at = Folder(proj), canonical(proj.initial()), None
        for n in range(len(events) + 1):
            if n and refused_at is None:
                try:
                    inc_state = canonical(folder.advance(events[n - 1]))
                except ProjectionError:
                    refused_at = n
            inc = "REFUSED" if refused_at is not None else inc_state
            try:
                scratch = canonical(fold(proj, events[:n]))
            except ProjectionError:
                scratch = "REFUSED"
            try:
                ref = canonical(model(plain_events[:n]))
            except Refused:
                ref = "REFUSED"
            if not (inc == scratch == ref):
                out.append({"projection": pid, "prefix": n, "incremental": inc, "from_scratch": scratch, "reference": ref})
                break
    return out


def coverage_of(events, answers: dict) -> tuple[dict, list[str]]:
    """The preregistered categories one trace exercises (each key once per trace) and the compound pairs it holds."""
    hit: dict[str, set] = {k: set() for k in PREREGISTERED}
    hit["event_type"] = {e.type for e in events}
    stories: dict[str, dict] = {}
    committed: set[str] = set()
    run_events = [e for e in events if e.type.startswith("run/")]
    for e in events:
        d = e.data
        t = e.type
        if t == "story/admitted":
            hit["disposition"] |= set(d["dispositions"].values())
            hit["admission"].add("admitted" if d["admitted"] else "blocked")
            hit["admission"].add("developer_call_permitted" if d["developer_call_permitted"] else "developer_call_not_permitted")
            st = stories.setdefault(d["story_id"], {"codes": [], "attempts": 0, "outcomes": [], "blocked": False})
            st["attempts"] += 1
            st["blocked"] = not d["admitted"]
        elif t == "failure/observed":
            hit["fault_kind"].add(d["code"])
            hit["owner"].add(d["owner"])
            hit["retryability"].add("retryable" if d["retryable"] else "not_retryable")
            st = stories.setdefault(d["story_id"], {"codes": [], "attempts": 0, "outcomes": [], "blocked": False})
            st["codes"].append(d["code"])
            if d["story_id"] in committed and d["code"].startswith("POST_MERGE"):
                hit["outcome"].add("post_merge_failure")
        elif t in ("story/commit", "story/rollback", "story/retry"):
            st = stories.setdefault(d["story_id"], {"codes": [], "attempts": 0, "outcomes": [], "blocked": False})
            outcome = t.split("/")[1]
            st["outcomes"].append(outcome)
            hit["outcome"].add(outcome)
            if outcome == "commit":
                committed.add(d["story_id"])
                if "retry" in st["outcomes"][:-1]:
                    hit["outcome"].add("commit_after_retry")
            if outcome == "rollback":
                if "retry" in st["outcomes"][:-1]:
                    hit["outcome"].add("rollback_after_retry")
                if st["attempts"] >= 3:
                    hit["outcome"].add("rollback_at_max_attempts")
                if st["blocked"]:
                    hit["outcome"].add("blocked_then_rollback")
            if outcome == "retry" and st["blocked"]:
                hit["outcome"].add("blocked_then_retry")
        elif t == "provider/request":
            hit["budget_owner"].add(d["budget_owner"])
        elif t == "story/plan-drift":
            hit["drift"].add("unattributed" if d["attributed_to"] == "UNATTRIBUTED" else "attributed")
        elif t == "gate/check":
            hit["gate"].add("check_passed" if d["passed"] else "check_failed")
        elif t == "gate/decision":
            hit["gate"].add("decision_passed" if d["passed"] else "decision_failed")
        elif t == "invariant/violated":
            hit["invariant"].add(d["invariant"])
        elif t == "probe/evaluated" and (d.get("record") or {}).get("probe_id"):
            hit["probe_id"].add(d["record"]["probe_id"])
    # interruption pattern, from the run events in order
    kinds = [(e.type, e.data.get("abandoned")) for e in run_events]
    names = [k for k, _ in kinds]
    if "run/interrupted" not in names:
        hit["interruption"].add("none")
    else:
        hit["interruption"].add("interrupted")
        if ("run/interrupted", True) in kinds:
            hit["interruption"].add("abandoned")
            if names.count("run/interrupted") >= 2:
                hit["interruption"].add("second_interrupt_abandons")
        first = names.index("run/interrupted")
        if "run/dispose-begin" in names[:first]:
            hit["interruption"].add("interrupted_during_disposal")
        if "run/end" in names[first:]:
            hit["interruption"].add("ended_after_interrupt")
    if "run/end" in names:
        hit["interruption"].add("dispose_then_end" if "run/dispose-begin" in names else "end_without_dispose")
    # terminal states, from the terminal_state answer (the kernel's and the model's agree when the trace matched)
    try:
        terminal = json.loads(answers["terminal_state"][2]) if answers["terminal_state"][2] != "REFUSED" else None
    except (KeyError, ValueError):
        terminal = None
    if isinstance(terminal, dict):
        if terminal.get("run") in PREREGISTERED["run_terminal"]:
            hit["run_terminal"].add(terminal["run"])
        for v in (terminal.get("stories") or {}).values():
            if v in PREREGISTERED["story_terminal"]:
                hit["story_terminal"].add(v)
    codes = sorted({c for st in stories.values() for c in st["codes"]})
    pairs = [f"{a}|{b}" for a, b in itertools.combinations(codes, 2)]
    for st in stories.values():
        if len(st["codes"]) >= 2:
            hit["same_story_pair"].add("same_story_two_codes" if len(set(st["codes"])) >= 2 else "same_story_repeated_code")
            if "retry" in st["outcomes"]:
                first_retry = st["outcomes"].index("retry")
                # the code the retry answered vs the codes of the later attempt(s)
                hit["same_story_pair"].add("retry_then_other_code" if len(set(st["codes"])) >= 2 else "retry_then_same_code")
                del first_retry
    return {k: sorted(v) for k, v in hit.items()}, pairs


def evaluate(seed: int) -> dict:
    """One trace, one terminal class, and what it covered. Never raises for a trace's own fault: an InvariantError is
    INVARIANT_VIOLATION, any other escape is EXCEPTION, both retained with their traceback."""
    from aisef2.errors import InvariantError
    from aisef2.journal.format3 import reconstruct
    row = {"seed": seed, "stories": stories_of(seed)}
    try:
        text = generate(seed)
        row["trace_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
        events = reconstruct(text).events
        row["events"] = len(events)
        answers = _answers(events)
        divergent = {pid: {"incremental": a, "from_scratch": b, "reference": c} for pid, (a, b, c) in answers.items() if not (a == b == c)}
        prefix = _prefix_divergences(events) if seed % PREFIX_EVERY == 0 else None
        row["prefix_checked"] = prefix is not None
        row["refused"] = any(a == "REFUSED" for (a, _, _) in answers.values())
        cov, pairs = coverage_of(events, answers)
        row["coverage"], row["pairs"] = cov, pairs
        if divergent or prefix:
            row["class"] = "DIVERGENCE"
            row["divergence"] = {"projections": divergent, "prefix": prefix, "journal": text,
                                 "events": [{"seq": e.seq, "type": e.type, "data": json.loads(json.dumps(e.data, default=str)), "source_seqs": list(e.source_seqs)}
                                            for e in events],
                                 "answers": {pid: {"incremental": a, "from_scratch": b, "reference": c} for pid, (a, b, c) in answers.items()}}
        else:
            row["class"] = "MATCHED"
    except InvariantError as e:
        row["class"] = "INVARIANT_VIOLATION"
        row["error"] = {"type": type(e).__name__, "message": str(e), "traceback": traceback.format_exc()[-4000:]}
    except BaseException as e:  # noqa: BLE001 — every escape is accounted, none is silent (owner §14)
        if isinstance(e, (KeyboardInterrupt, SystemExit)):
            raise
        row["class"] = "EXCEPTION"
        row["error"] = {"type": type(e).__name__, "message": str(e)[:2000], "traceback": traceback.format_exc()[-4000:]}
    return row


# --------------------------------------------------------------------------------------------------- the chunk

def run_chunk(k: int, *, attempt: int = 1, out_dir: pathlib.Path) -> dict:
    import tests.v2 as tier   # arms invariants I–IX at tier ROOT for this process (fails closed)
    start, end = SEED_BASE + k * CHUNK_SIZE, SEED_BASE + (k + 1) * CHUNK_SIZE   # [start, end)
    ident = identity()
    problems = subject_problems(ident)
    record = {
        "record": "AISEF V2 — Q4 chunk", "chunk": k, "attempt": attempt, "seed_range": [start, end - 1], "requested": CHUNK_SIZE,
        "subject_problems": problems, "identity": ident, "one_kernel_identity": one_kernel_identity(ident),
        "invariants_armed": _armed(tier.ARMED),
        "worker": {"host": socket.gethostname(), "pid": os.getpid(), "python": platform.python_version(), "platform": platform.system().lower()},
        "started": C.now(),
    }
    if problems:
        record.update(attempted=0, terminal=0, counters={c: 0 for c in CLASSES}, rows=[], finished=C.now(), status="UNRUNNABLE")
        return record
    C.render(record)   # the header must be a record before any trace runs: a value that cannot be written is found here, not after 10,000 traces
    t0 = time.perf_counter()
    counters = {c: 0 for c in CLASSES}
    counters.update(matched_with_refusal=0, prefix_traces=0)
    coverage: dict[str, dict[str, int]] = {k_: {} for k_ in PREREGISTERED}
    pairs: dict[str, int] = {}
    rows, divergences, violations, exceptions = [], [], [], []
    events_total = 0
    for seed in range(start, end):
        r = evaluate(seed)
        counters[r["class"]] += 1
        if r["class"] == "MATCHED" and r.get("refused"):
            counters["matched_with_refusal"] += 1
        if r.get("prefix_checked"):
            counters["prefix_traces"] += 1
        events_total += r.get("events", 0)
        for cat, keys in (r.get("coverage") or {}).items():
            for key in keys:
                coverage[cat][key] = coverage[cat].get(key, 0) + 1
        for p in r.get("pairs") or []:
            pairs[p] = pairs.get(p, 0) + 1
        rows.append([seed, r["class"], r.get("events"), (r.get("trace_sha256") or "")[:16]])
        if r["class"] == "DIVERGENCE":
            divergences.append({k_: v for k_, v in r.items() if k_ not in ("coverage", "pairs")})
        elif r["class"] == "INVARIANT_VIOLATION":
            violations.append({"seed": seed, **r["error"]})
        elif r["class"] == "EXCEPTION":
            exceptions.append({"seed": seed, **r["error"]})
    coverage["compound_pair"] = pairs
    record.update(attempted=len(rows), terminal=len(rows), counters=counters, events_total=events_total, coverage=coverage, rows=rows,
                  divergences=divergences, invariant_violations=violations, exceptions=exceptions,
                  seconds=round(time.perf_counter() - t0, 1), finished=C.now(),
                  status="GREEN" if counters["MATCHED"] == CHUNK_SIZE == len(rows) else "FAILED")
    record["digest"] = C.sha_text(json.dumps({k_: v for k_, v in record.items() if k_ != "digest"}, sort_keys=True, default=str))
    return record


def _armed(armed) -> dict:
    """What tests.v2 armed for this process, in JSON form (the registry holds enums in a frozenset)."""
    tier = getattr(armed, "tier", None)
    ids = getattr(armed, "invariants", None) or ()
    return {"tier": getattr(tier, "value", str(tier)), "invariants": sorted(getattr(i, "value", str(i)) for i in ids), "count": len(ids)}


def chunk_path(out_dir: pathlib.Path, k: int, attempt: int) -> pathlib.Path:
    return out_dir / (f"chunk-{k}.json" if attempt == 1 else f"chunk-{k}.attempt-{attempt}.json")


def freeze() -> dict:
    """SUBJECT.json: the frozen subject, the preregistered model, and the design pilot's reachability evidence."""
    import tests.v2  # noqa: F401 — invariants armed for the pilot too
    ident = identity()
    pilot: dict[str, dict[str, int]] = {k: {} for k in PREREGISTERED}
    pilot_pairs: dict[str, int] = {}
    counters = {c: 0 for c in CLASSES}
    for seed in range(*PILOT_SEEDS):
        r = evaluate(seed)
        counters[r["class"]] += 1
        for cat, keys in (r.get("coverage") or {}).items():
            for key in keys:
                pilot[cat][key] = pilot[cat].get(key, 0) + 1
        for p in r.get("pairs") or []:
            pilot_pairs[p] = pilot_pairs.get(p, 0) + 1
    pilot["compound_pair"] = pilot_pairs
    unreached = {cat: [k for k in keys if pilot[cat].get(k, 0) == 0] for cat, keys in PREREGISTERED.items()}
    unreached = {cat: v for cat, v in unreached.items() if v}
    return {
        "record": "AISEF V2 — Q4 SUBJECT (frozen before the first trace)", "authority": "owner's P8 / QP-8 EXECUTION AUTHORIZATION (2026-09-28) §1, §4, §19, §21",
        "frozen_at": C.now(), "identity": ident, "one_kernel_identity": one_kernel_identity(ident), "subject_problems": subject_problems(ident),
        "terminal_classes": list(TERMINAL_CLASSES), "preregistered": PREREGISTERED,
        "preregistered_counts": {k: len(v) for k, v in PREREGISTERED.items()},
        "design_pilot": {"seeds": list(PILOT_SEEDS), "note": "outside the schedule, never counted in the 100,000; establishes that every preregistered "
                                                                "category is reachable by the generator before the run", "counters": counters,
                         "coverage": pilot, "unreached": unreached},
        "rule": "a preregistered category with zero samples in the 100,000 leaves Q4 incomplete; nothing is added to or removed from the "
                "preregistered lists after the run starts",
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunk", type=int)
    ap.add_argument("--attempt", type=int, default=1)
    ap.add_argument("--freeze", action="store_true")
    ap.add_argument("--out", default=OUT_REL)
    a = ap.parse_args(argv)
    out_dir = ROOT / a.out
    if a.freeze:
        rec = freeze()
        p = out_dir / "SUBJECT.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(C.render(rec), encoding="utf-8")
        print(f"wrote {p}: unreached {rec['design_pilot']['unreached']} problems {rec['subject_problems']}")
        return 1 if rec["design_pilot"]["unreached"] or rec["subject_problems"] else 0
    if a.chunk is None or not 0 <= a.chunk < CHUNKS:
        ap.error(f"--chunk 0..{CHUNKS - 1} or --freeze")
    p = chunk_path(out_dir / "chunks", a.chunk, a.attempt)
    if p.exists():
        print(f"REFUSED: {p} exists — a chunk record is written once; a rerun is a new --attempt")
        return 2
    rec = run_chunk(a.chunk, attempt=a.attempt, out_dir=out_dir / "chunks")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(C.render(rec), encoding="utf-8")
    c = rec["counters"]
    print(f"chunk {a.chunk} attempt {a.attempt}: {rec['status']} — attempted {rec['attempted']} terminal {rec['terminal']} "
          f"{ {k: c[k] for k in CLASSES} } refused-matches {c.get('matched_with_refusal')} prefix {c.get('prefix_traces')} in {rec.get('seconds')} s")
    return 0 if rec["status"] == "GREEN" else 1


if __name__ == "__main__":
    sys.exit(main())
