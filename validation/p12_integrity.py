"""Phase 12 — differential trace integrity report.

For every chunk: what was DIRECTLY_RECORDED by the chunk, what is DERIVABLE_FROM_RAW_EVIDENCE (the reference model is
deterministic and cheap: replaying the chunk's seeds reproduces the model side; for a MATCHED trace the kernel's
compared fields equal the model's by the harness's own definition), and what is NOT_AVAILABLE (the kernel's event
stream of matched traces was not persisted before the per-trace rows were added). Then the consolidated view:
ranges, sums, terminal classes, transition coverage against the T1–T35 table (docs/ASSURANCE-KERNEL.md §6) with the
first seed observing each, and saturation by 10k. Never edits a chunk.

    python3 validation/p12_integrity.py --out closure-evidence/hardening/phase12/integrity.json
"""
from __future__ import annotations

import argparse
import glob
import gzip
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tests.hardening import differential as D  # noqa: E402

#: model event/outcome → T-ids of docs/ASSURANCE-KERNEL.md §6 that the step exercises (an interpretation table, stated)
T_OF = {
    ("DEVELOP_CHANGED", "PASS"): ["T5", "T13"], ("DEVELOP_SCOPE_VIOLATION", "PASS"): ["T12", "T13"],
    ("DEVELOP_NOOP", "NOOP"): ["T6"], ("DEVELOP_NOOP", "PASS"): ["T6'"], ("DEVELOP_NOOP", "QUALITY_BLOCK"): ["T6"],
    ("DEVELOP_MAX_TURNS_WORK", "PASS"): ["T7", "T13"], ("DEVELOP_MAX_TURNS_UNTOUCHED", "NOOP"): ["T8"], ("DEVELOP_MAX_TURNS_UNTOUCHED", "PASS"): ["T8", "T6'"],
    ("DEVELOP_TIMEOUT", "INFRA_FAILURE"): ["T9"], ("DEVELOP_CRASH", "INFRA_FAILURE"): ["T9"], ("DEVELOP_RATE_LIMIT", "INFRA_FAILURE"): ["T9"],
    ("DEVELOP_CONTEXT", "ENVIRONMENT_FAILURE"): ["T9"], ("DEVELOP_AUTH", "AUTH_FAILURE"): ["T10"], ("DEVELOP_TRUNK_COMMIT", "ISOLATION_BREACH"): ["T11"],
    ("DEVELOP_ZERO_OUTPUT", "NOOP"): ["T6"], ("DEVELOP_ZERO_OUTPUT", "ENVIRONMENT_FAILURE"): ["T9"], ("DEVELOP_BUDGET", "HUMAN_REQUIRED"): ["T27"],
    ("TEST_PASS", "PASS"): ["T15"], ("TEST_FAIL", "QUALITY_BLOCK"): ["T15"], ("TEST_UNRUNNABLE", "ENVIRONMENT_FAILURE"): ["T16"],
    ("DEVELOP_MAX_TURNS_UNTOUCHED", "QUALITY_BLOCK"): ["T8"], ("DEVELOP_CONTEXT", "INFRA_FAILURE"): ["T9"], ("REVIEW_BLOCK_UNBOUND", "UNRUNNABLE"): ["T20"],
    ("REVIEW_PASS", "PASS"): ["T17"], ("REVIEW_BLOCK", "QUALITY_BLOCK"): ["T18"], ("REVIEW_BLOCK_OUTSIDE", "QUALITY_BLOCK"): ["T18"],
    ("REVIEW_BLOCK_UNBOUND", "QUALITY_BLOCK"): ["T18"], ("REVIEW_STUCK", "PLAN_CONFLICT"): ["T19"],
    ("REVIEW_MUTATE", "UNRUNNABLE"): ["T20"], ("REVIEW_MALFORMED", "UNRUNNABLE"): ["T20"], ("REVIEW_UNRUNNABLE", "UNRUNNABLE"): ["T20"],
    ("REVIEW_COMMIT", "UNRUNNABLE"): ["T20"], ("REVIEW_BUDGET", "HUMAN_REQUIRED"): ["T27"],
    ("SECURITY_PASS", "PASS"): ["T22"], ("SECURITY_BLOCK", "QUALITY_BLOCK"): ["T22"], ("SECURITY_UNRUNNABLE", "UNRUNNABLE"): ["T23"],
    ("SECURITY_MALFORMED", "UNRUNNABLE"): ["T23"], ("SECURITY_BUDGET", "HUMAN_REQUIRED"): ["T27"],
    ("GATE_EVALUATE", "PASS"): ["T24"], ("GATE_EVALUATE", "QUALITY_BLOCK"): ["T25", "T3"], ("GATE_EVALUATE", "UNRUNNABLE"): ["T26"],
    ("GATE_EVALUATE", "PLAN_CONFLICT"): ["T28"], ("GATE_EVALUATE", "REVIEW_UNRUNNABLE"): ["T21"], ("GATE_EVALUATE", "SECURITY_UNRUNNABLE"): ["T21"],
    ("MERGE", "PASS"): ["T29"], ("MERGE_OK", "PASS"): ["T29"], ("MERGE", "MERGE_CONFLICT"): ["T30"],
}
#: transitions the single-story differential cannot reach by construction (run-level or human-level); named with the deterministic evidence that covers them
UNREACHABLE_HERE = {
    "T1": "claim by a live process — run loop (tests/test_run.py, test_state.py TestLeaseEdges)",
    "T2": "reclaim of an orphaned claim — reconcile (tests/test_dogfood_ledgerlock.py, scan8a TestSS49)",
    "T4": "unattributed out-of-scope dirt blocks — hygiene (tests/hardening/test_ownership.py, scan8a TestSS37)",
    "T14": "pre-staged out-of-scope paths at freeze — tests/test_implement.py (freeze) / scan8a TestSS15",
    "T31": "process death — crash recovery (tests/test_crash_recovery.py, compound CF-05)",
    "T32": "contract change — epoch (tests/test_worktree.py TestNhanhCuKhiTieuChiDoi, compound CF-13)",
    "T33": "owner arbitration — compound CF-13 / test_approvals TestCascade",
    "T34": "run end commit + worktree removal — tests/test_run.py",
    "T30": "merge conflict — the synthetic merge never conflicts; tests/test_worktree.py (merge conflict), tests/test_run.py",
}


def _steps(events: list[str]) -> list[tuple[str, str]]:
    out = []
    for e in events:
        if "->" in e:
            a, b = e.split("->", 1); out.append((a, b))
    return out


def _sequence_transitions(steps: list[tuple[str, str]], terminal: str) -> list[str]:
    """Transitions a single pair cannot name: T6' (a no-op decision followed by grading of the frozen candidate with
    no new developer session), T21 (the reviewer still absent after its budget — the story's terminal names it),
    T29 (the merge — the model records no merge event; `done` is the merge)."""
    out = []
    for i, (a, _b) in enumerate(steps):
        if a == "DEVELOP_NOOP" and i + 1 < len(steps) and steps[i + 1][0].startswith("TEST_"):
            out.append("T6'")
    if terminal.startswith(("blocked:REVIEW_UNRUNNABLE", "blocked:SECURITY_UNRUNNABLE")):
        out.append("T21")
    if terminal == "done":
        out.append("T29")
    return out



def _rows_file(summary_file: str) -> Path | None:
    """The per-trace rows beside a chunk summary: `<name>.rows.jsonl` or its gzipped form (the repo keeps the gzipped
    form: 7 MB → 350 KB per chunk); None when the chunk ran before the rows existed — its metrics are then
    DERIVABLE_FROM_RAW_EVIDENCE or NOT_AVAILABLE, never guessed."""
    base = Path(summary_file).with_suffix(".rows.jsonl")
    if base.is_file():
        return base
    gz = base.with_suffix(".jsonl.gz")
    return gz if gz.is_file() else None


def _read_rows(summary_file: str) -> list[dict]:
    rf = _rows_file(summary_file)
    if rf is None:
        return []
    opener = gzip.open if rf.suffix == ".gz" else open
    with opener(rf, "rt", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh]


def chunk_records(files: list[str]) -> list[dict]:
    recs = []
    for f in files:
        d = json.load(open(f, encoding="utf-8"))
        start = int(Path(f).stem.split("-")[-1]); n = d["traces"]

        rows = _read_rows(f)
        rec = {"chunk_id": Path(f).stem, "seed_start": start, "seed_end": start + n - 1, "trace_count": n,
               "runtime_s": d["elapsed_s"], "transition_count_model": d["model_transitions"], "stage_event_count_real": d["real_stage_events"],
               "matched": d["matched"], "mismatch_count": d["unexplained_count"] + sum(d["mismatched_attributed"].values()),
               "first_mismatch": (d["unexplained"][0]["seed"], d["unexplained"][0]["diff"]) if d["unexplained"] else None,
               "unexplained_seeds": [u["seed"] for u in d["unexplained"]],
               "recording": {"seed_range": "DIRECTLY_RECORDED", "trace_count": "DIRECTLY_RECORDED", "transition_count": "DIRECTLY_RECORDED (sum)",
                             "runtime": "DIRECTLY_RECORDED", "mismatch_count_and_records": "DIRECTLY_RECORDED",
                             "model_terminal_distribution": "DIRECTLY_RECORDED (rows)" if rows else "DERIVABLE_FROM_RAW_EVIDENCE (deterministic model replay of the seeds)",
                             "real_terminal_distribution": "DIRECTLY_RECORDED (rows)" if rows else "DERIVABLE: equals the model's for every MATCHED trace (terminal is a compared field); the unmatched trace's is recorded",
                             "transitions_exercised_model": "DIRECTLY_RECORDED (rows)" if rows else "DERIVABLE_FROM_RAW_EVIDENCE (model replay)",
                             "transitions_exercised_real": "DIRECTLY_RECORDED (rows)" if rows else "NOT_AVAILABLE (kernel event streams of matched traces were not persisted)",
                             "typed_outcomes_and_event_kinds": "DIRECTLY_RECORDED (rows)" if rows else "DERIVABLE_FROM_RAW_EVIDENCE (model replay; scenario vocabulary from the seed)"}}
        # model side: replay when rows are absent (deterministic; verified against the recorded unexplained record where one exists)
        model_term, real_term, t_hits, real_kinds, model_kinds, first_seen = Counter(), Counter(), Counter(), Counter(), Counter(), {}
        if rows:
            it = ((r["seed"], r["model_terminal"], r["real_terminal"], r["model_events"], r["real_events"]) for r in rows)
        else:
            def gen(start=start, n=n):
                for seed in range(start, start + n):
                    m = D.model_run(D.generate(seed))
                    yield seed, m.terminal, m.terminal, m.events, None      # real == model for matched (all but the recorded unexplained)
            it = gen()
        unexplained = {u["seed"]: u for u in d["unexplained"]}
        for seed, mt, rt, mev, rev in it:
            if seed in unexplained and rev is None:
                rt = unexplained[seed]["real"]["terminal"]
            model_term[mt.split(":")[0]] += 1; real_term[rt.split(":")[0]] += 1
            steps = _steps(mev)
            for a, b in steps:
                model_kinds[a] += 1
                for t in T_OF.get((a, b), []):
                    t_hits[t] += 1; first_seen.setdefault(t, seed)
            for t in _sequence_transitions(steps, mt):
                t_hits[t] += 1; first_seen.setdefault(t, seed)
            if rev:
                for e in rev:
                    real_kinds[e] += 1
        rec.update({"model_terminal_distribution": dict(model_term), "real_terminal_distribution": dict(real_term),
                    "transition_hits_model": dict(sorted(t_hits.items())), "first_seed_per_transition": first_seen,
                    "model_event_kinds": dict(model_kinds), "real_event_kinds": dict(real_kinds) if rows else "NOT_AVAILABLE",
                    "rows_recorded": bool(rows)})
        recs.append(rec)
    return recs


def superseded(rerun_files: list[str]) -> dict[int, bool]:
    """Seeds re-run AFTER a fix (differential-p12-rerun-*.json with rows): seed → matched. A rerun never edits a chunk's
    record; the consolidated view reports the historical mismatches AND the effective ones after supersession."""
    out: dict[int, bool] = {}
    for f in rerun_files:
        for r in _read_rows(f):
            out[r["seed"]] = not r["diff"]
    return out


def consolidate(recs: list[dict], intended: list[int], rerun: dict[int, bool] | None = None) -> dict:
    rerun = rerun or {}
    recs = sorted(recs, key=lambda r: r["seed_start"])
    ranges = [(r["seed_start"], r["seed_end"]) for r in recs]
    overlap = any(ranges[i][1] >= ranges[i + 1][0] for i in range(len(ranges) - 1))
    missing = [s for s in intended if not any(r["seed_start"] == s for r in recs)]
    early = [r["chunk_id"] for r in recs if r["trace_count"] != 10000]
    t_total, first = Counter(), {}
    for r in recs:
        for t, n in r["transition_hits_model"].items():
            t_total[t] += n
            if t not in first or r["first_seed_per_transition"][t] < first[t]:
                first[t] = r["first_seed_per_transition"][t]
    all_t = [f"T{i}" for i in range(1, 35)] + ["T6'"]          # docs/ASSURANCE-KERNEL.md §6: T1–T34 and T6' — 35 rows
    coverage = {t: {"reachable_in_differential": t not in UNREACHABLE_HERE, "model_hits": t_total.get(t, 0), "first_seed": first.get(t),
                    "covered_by": UNREACHABLE_HERE.get(t, "differential" if t_total.get(t) else "UNHIT — targeted scenario required")} for t in all_t}
    saturation = []
    seen = set()
    for r in recs:
        new = [t for t in r["transition_hits_model"] if t not in seen]; seen.update(r["transition_hits_model"])
        saturation.append({"after_seeds": r["seed_end"] + 1, "transitions_seen": len(seen), "new_here": new})
    return {"total_traces": sum(r["trace_count"] for r in recs), "sum_equals_chunks": True,
            "total_transitions_model": sum(r["transition_count_model"] for r in recs), "total_stage_events_real": sum(r["stage_event_count_real"] for r in recs),
            "matched": sum(r["matched"] for r in recs), "mismatches": sum(r["mismatch_count"] for r in recs),
            "mismatches_effective_after_reruns": sum(1 for r in recs for u in (r.get("unexplained_seeds") or []) if not rerun.get(u, False)),
            "reruns": {"seeds": len(rerun), "matched": sum(1 for v in rerun.values() if v), "mismatched": sum(1 for v in rerun.values() if not v)},
            "seed_ranges": ranges, "ranges_overlap": overlap, "missing_intended_ranges": missing, "chunks_not_10000": early,
            "unique_model_terminal_classes": sorted({k for r in recs for k in r["model_terminal_distribution"]}),
            "unique_real_terminal_classes": sorted({k for r in recs for k in r["real_terminal_distribution"]}),
            "transition_coverage": coverage, "saturation_by_chunk": saturation,
            "unhit_reachable": [t for t, c in coverage.items() if c["reachable_in_differential"] and not c["model_hits"]]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default=str(ROOT / "closure-evidence/hardening/phase12/integrity.json"))
    ap.add_argument("--glob", default=str(ROOT / "closure-evidence/hardening/differential-p12-*[0-9].json"))
    ap.add_argument("--summary", default=str(ROOT / "closure-evidence/hardening/differential-p12-summary.json"), help="the W0 builder's input, derived from this consolidation")
    a = ap.parse_args(argv)
    files = sorted(f for f in glob.glob(a.glob) if "rerun" not in Path(f).name); t0 = time.time()
    rerun = superseded(sorted(glob.glob(str(Path(a.glob).parent / "differential-p12-rerun-*.json"))))
    recs = chunk_records(files)
    rep = {"generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "chunks": recs, "consolidated": consolidate(recs, list(range(0, 100000, 10000)), rerun),
           "T_of_interpretation": {f"{k[0]}->{k[1]}": v for k, v in T_OF.items()}, "elapsed_s": round(time.time() - t0, 1)}
    Path(a.out).write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    c = rep["consolidated"]
    print(json.dumps({k: c[k] for k in ("total_traces", "matched", "mismatches", "ranges_overlap", "missing_intended_ranges", "chunks_not_10000", "unhit_reachable")}))
    print("terminal classes model/real:", c["unique_model_terminal_classes"], c["unique_real_terminal_classes"])
    ok = (not c["mismatches_effective_after_reruns"] and not c["reruns"]["mismatched"] and not c["ranges_overlap"]
          and not c["missing_intended_ranges"] and not c["unhit_reachable"] and c["total_traces"] >= 100000)
    print("historical mismatches:", c["mismatches"], "| effective after reruns:", c["mismatches_effective_after_reruns"], "| reruns:", c["reruns"])
    chunks = [json.load(open(f, encoding="utf-8")) for f in files]
    # candidate-kernel evidence per seed (phase12/kernel-split.json): a chunk that ran on the candidate, or a seed re-run on it
    split_path = Path(a.out).parent / "kernel-split.json"
    split = json.loads(split_path.read_text(encoding="utf-8")) if split_path.is_file() else {"chunks": []}
    cand_chunks = {c["chunk"] for c in split["chunks"] if c.get("candidate_kernel")}
    direct_seeds = {s for f, d in zip(files, chunks, strict=True) if Path(f).stem.split("-")[-1] in cand_chunks
                    for s in range(int(Path(f).stem.split("-")[-1]), int(Path(f).stem.split("-")[-1]) + d["traces"])}
    kernel_evidence = {"chunks_on_the_candidate": sorted(cand_chunks), "seeds_direct": len(direct_seeds), "seeds_rerun_on_the_candidate": len(rerun),
                       "seeds_with_candidate_kernel_evidence": len(direct_seeds | set(rerun)),
                       "seeds_resting_on_the_measured_diff": c["total_traces"] - len(direct_seeds | set(rerun)),
                       "kernel_classes": {ch["chunk"]: ch["kernel_class"] for ch in split["chunks"]}}
    summary = {"phase": 12, "source": "validation/p12_integrity.py (this summary is derived from phase12/integrity.json — one consolidation)",
               "chunks": len(chunks), "traces": c["total_traces"], "matched": c["matched"],
               "unexplained": c["mismatches_effective_after_reruns"],
               "unexplained_historical": c["mismatches"],
               "unexplained_note": "historical = mismatches as the chunks recorded them (a chunk record is never edited); effective = after the targeted "
                                   "re-run of the minimum affected seed set following a registered fix superseded a seed's verdict with rows",
               "reruns": c["reruns"], "elapsed_s": round(sum(d["elapsed_s"] for d in chunks), 1),
               "model_transitions": sum(d["model_transitions"] for d in chunks), "real_stage_events": sum(d["real_stage_events"] for d in chunks),
               "known_deviations": sorted({k for d in chunks for k in (d.get("known_deviations") or [])}),
               "kernel_by_chunk": {Path(f).stem.split("-")[-1]: (d.get("kernel") or {}).get("head") for f, d in zip(files, chunks, strict=True)},
               "seed_ranges": [Path(f).stem.split("-")[-1] for f in files], "workers": chunks[0]["workers"] if chunks else 0,
               "candidate_kernel_evidence": kernel_evidence, "pass": ok}
    summary["traces_per_s"] = round(summary["traces"] / summary["elapsed_s"], 2) if summary["elapsed_s"] else 0
    Path(a.summary).write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
