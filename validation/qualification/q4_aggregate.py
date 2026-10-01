"""Q4 aggregation, calibration and conformance snapshots (owner's "P8 / QP-8 EXECUTION AUTHORIZATION" §5, §7, §11,
§15, §17, §20-§22, §29).

    python -P validation/qualification/q4_aggregate.py --calibrate           # §22: six defects detected, none of the 100,000 -> CALIBRATION.json
    python -P validation/qualification/q4_aggregate.py --conformance start   # F1-F11 and the V1 guard before the first trace -> CONFORMANCE-start.json
    python -P validation/qualification/q4_aggregate.py                       # the ten chunks -> DIFFERENTIAL.json (exit 0 only when GREEN)

The aggregator reads the chunk records only. Per chunk it re-derives every count from the rows (a seed with no
terminal class, or a seed of the schedule missing from the rows, is a silent skip — counted here, never by a worker),
requires requested == attempted == terminal == 10,000 with the categories reconciling exactly, and one kernel identity
across the ten chunks equal to the frozen subject's. Coverage is the sum over chunks against the preregistered lists
frozen in SUBJECT.json: a category with zero samples leaves Q4 incomplete. Nothing here reads the kernel's decisions
as an oracle; nothing here changes a chunk.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.qualification import common as C  # noqa: E402
from validation.qualification import q4  # noqa: E402

W0_REL, W0_SHA = "closure-evidence/hardening/AISEF-W0-QUALIFICATION.json", "a14c2f58083bd32dc7b7c3ce5e35bb22a4bba9e745d109538a877464df21fba3"
#: the rung below Q4, bound by digest: Cycle 2 (QP-2.7) — the QP-2.6 summary and the C2-P5 acceptance it qualified
P7_EVIDENCE = ("closure-evidence/v2/cycle2/Q0-Q3-R4/SUMMARY.json", "closure-evidence/v2/cycle2/C2-P5-ACCEPTANCE.json",
               "closure-evidence/v2/cycle2/P5-CONTRACT-APPROVALS.json")
SEALS = ("closure-evidence/v2/P4-FINAL-SEAL.json", "closure-evidence/v2/P5-FINAL-SEAL.json", "closure-evidence/v2/P6-FINAL-SEAL.json")


def _sha(rel: str) -> str | None:
    p = ROOT / rel
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


# ---------------------------------------------------------------------------------------------- reconciliation

def load_chunks(chunk_dir: pathlib.Path) -> dict[int, list[dict]]:
    """Every attempt of every chunk, by chunk, attempts in order."""
    out: dict[int, list[dict]] = {}
    for p in sorted(chunk_dir.glob("chunk-*.json")):
        rec = json.loads(p.read_text(encoding="utf-8"))
        rec["_file"] = p.relative_to(ROOT).as_posix()
        rec["_sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
        out.setdefault(int(rec["chunk"]), []).append(rec)
    for k in out:
        out[k].sort(key=lambda r: r["attempt"])
    return out


def attempts_observed(out_dir: pathlib.Path) -> dict[int, list[dict]]:
    """Every chunk attempt the runner started, from the owned-range records (owned/chunk-K.attempt-N.json), whether
    or not the worker wrote its record: an attempt with no chunk record is a harness failure, kept as one."""
    out: dict[int, list[dict]] = {}
    out_dir = out_dir.resolve()
    for p in sorted((out_dir / "owned").glob("chunk-*.attempt-*.json")):
        k, n = (int(x) for x in p.stem.replace("chunk-", "").replace("attempt-", "").split("."))
        o = json.loads(p.read_text(encoding="utf-8"))
        rec = q4.chunk_path(out_dir / "chunks", k, n)
        out.setdefault(k, []).append({"attempt": n, "owned_record": p.relative_to(ROOT).as_posix(), "exit": o.get("exit"),
                                      "owned_after": o.get("owned_after"), "escaped": len(o.get("escaped") or []), "released_empty": o.get("released_empty"),
                                      "chunk_record": rec.relative_to(ROOT).as_posix() if rec.exists() else None})
    return out


def reconcile(attempts: dict[int, list[dict]], subject: dict) -> tuple[dict, list[str]]:
    """The accepted attempt per chunk (the last one), every count re-derived from the rows, one identity, coverage."""
    problems: list[str] = []
    sched = subject["identity"]["seed_schedule"]
    ranges = {k: tuple(r) for k, r in enumerate(sched["ranges"])}
    if sorted(attempts) != list(range(sched["chunks"])):
        problems.append(f"chunks present {sorted(attempts)}, schedule needs {list(range(sched['chunks']))}")
    per_chunk, identities, seen_seeds = {}, set(), {}
    totals = {c: 0 for c in q4.TERMINAL_CLASSES}
    totals.update(requested=0, attempted=0, terminal=0, rows=0, events=0, matched_with_refusal=0, prefix_traces=0)
    coverage: dict[str, dict[str, int]] = {cat: {} for cat in subject["preregistered"]}
    for k, recs in sorted(attempts.items()):
        rec = recs[-1]
        start, end = ranges.get(k, (None, None))
        rows = rec.get("rows") or []
        seeds = [r[0] for r in rows]
        classes = [r[1] for r in rows]
        by_class = {c: classes.count(c) for c in q4.CLASSES}
        unknown = sorted({c for c in classes if c not in q4.CLASSES})
        dup_in_chunk = len(seeds) - len(set(seeds))
        expected = set(range(start, end + 1)) if start is not None else set()
        missing = sorted(expected - set(seeds))
        outside = sorted(set(seeds) - expected)
        silent = len(missing) + sum(1 for c_ in classes if c_ not in q4.CLASSES)   # a seed of the range with no terminal class
        ident = rec.get("one_kernel_identity")
        identities.add(ident)
        for s in seeds:
            seen_seeds.setdefault(s, []).append(k)
        c = rec.get("counters") or {}
        row_problems = []
        if tuple(rec.get("seed_range") or ()) != (start, end):
            row_problems.append(f"seed_range {rec.get('seed_range')} is not the schedule's {[start, end]}")
        if not (rec.get("requested") == rec.get("attempted") == rec.get("terminal") == len(rows) == sched["chunk_size"]):
            row_problems.append(f"requested {rec.get('requested')} attempted {rec.get('attempted')} terminal {rec.get('terminal')} rows {len(rows)}: not all {sched['chunk_size']}")
        if any(c.get(cl) != by_class[cl] for cl in q4.CLASSES):
            row_problems.append(f"counters {dict((cl, c.get(cl)) for cl in q4.CLASSES)} do not reconcile with the rows {by_class}")
        if sum(by_class.values()) != len(rows) or unknown:
            row_problems.append(f"rows carry classes outside the preregistered ones: {unknown}")
        if missing or outside or dup_in_chunk:
            row_problems.append(f"seeds: {len(missing)} of the range missing, {len(outside)} outside the range, {dup_in_chunk} duplicated")
        if ident != subject.get("one_kernel_identity"):
            row_problems.append(f"kernel identity {str(ident)[:12]} is not the frozen subject's {str(subject.get('one_kernel_identity'))[:12]}")
        if rec.get("status") != "GREEN":
            row_problems.append(f"status {rec.get('status')}")
        if rec.get("subject_problems"):
            row_problems.append(f"subject problems at the worker: {rec['subject_problems']}")
        if len(rec.get("divergences") or []) != by_class["DIVERGENCE"] or len(rec.get("invariant_violations") or []) != by_class["INVARIANT_VIOLATION"] \
                or len(rec.get("exceptions") or []) != by_class["EXCEPTION"]:
            row_problems.append("the retained evidence does not match the class counts")
        per_chunk[k] = {"file": rec["_file"], "sha256": rec["_sha256"], "digest": rec.get("digest"), "attempt": rec["attempt"],
                        "attempts_total": len(recs), "earlier_attempts": [{"file": r["_file"], "sha256": r["_sha256"], "status": r.get("status"),
                                                                            "attempted": r.get("attempted")} for r in recs[:-1]],
                        "seed_range": [start, end], "requested": rec.get("requested"), "attempted": rec.get("attempted"), "terminal": rec.get("terminal"),
                        "rows": len(rows), **by_class, "SILENT_SKIP": silent, "matched_with_refusal": c.get("matched_with_refusal"),
                        "prefix_traces": c.get("prefix_traces"), "events_total": rec.get("events_total"), "seconds": rec.get("seconds"),
                        "one_kernel_identity": ident, "worker": rec.get("worker"), "started": rec.get("started"), "finished": rec.get("finished"),
                        "status": rec.get("status"), "problems": row_problems}
        problems += [f"chunk {k}: {p}" for p in row_problems]
        for cl in q4.CLASSES:
            totals[cl] += by_class[cl]
        totals["SILENT_SKIP"] += silent
        totals["requested"] += rec.get("requested") or 0
        totals["attempted"] += rec.get("attempted") or 0
        totals["terminal"] += rec.get("terminal") or 0
        totals["rows"] += len(rows)
        totals["events"] += rec.get("events_total") or 0
        totals["matched_with_refusal"] += c.get("matched_with_refusal") or 0
        totals["prefix_traces"] += c.get("prefix_traces") or 0
        for cat, counts in (rec.get("coverage") or {}).items():
            for key, n in counts.items():
                coverage.setdefault(cat, {})[key] = coverage[cat].get(key, 0) + n
    dups = {s: ks for s, ks in seen_seeds.items() if len(ks) > 1}
    schedule_seeds = set(range(sched["base"], sched["base"] + sched["total"]))
    missing_all = sorted(schedule_seeds - set(seen_seeds))
    if dups:
        problems.append(f"{len(dups)} seeds appear in more than one chunk (first: {sorted(dups)[:5]})")
    if missing_all:
        problems.append(f"{len(missing_all)} seeds of the schedule have no terminal accounting (first: {missing_all[:5]})")
    if len(identities) != 1:
        problems.append(f"{len(identities)} kernel identities across the chunks, not one")
    if totals["MATCHED"] != sched["total"]:
        problems.append(f"matched {totals['MATCHED']}, not {sched['total']}")
    for cl in ("DIVERGENCE", "INVARIANT_VIOLATION", "EXCEPTION", "SILENT_SKIP"):
        if totals[cl]:
            problems.append(f"{cl} = {totals[cl]}")
    zero = {cat: [k for k in keys if coverage.get(cat, {}).get(k, 0) == 0] for cat, keys in subject["preregistered"].items()}
    zero = {cat: v for cat, v in zero.items() if v}
    if zero:
        problems.append(f"preregistered categories with zero samples: { {cat: len(v) for cat, v in zero.items()} }")
    summary = {"per_chunk": per_chunk, "totals": totals, "one_kernel_identity": {"identities": sorted(x for x in identities if x), "count": len(identities),
                                                                                  "equal_to_subject": identities == {subject.get("one_kernel_identity")}},
               "seeds": {"schedule": sched, "accounted": len(seen_seeds), "duplicated": len(dups), "missing": len(missing_all),
                         "contiguous": not missing_all and not dups and len(seen_seeds) == sched["total"]},
               "coverage": coverage, "coverage_summary": {cat: {"preregistered": len(keys), "reached": sum(1 for k in keys if coverage.get(cat, {}).get(k, 0)),
                                                                "min_samples": min((coverage.get(cat, {}).get(k, 0) for k in keys), default=None)}
                                                          for cat, keys in subject["preregistered"].items()},
               "zero_sample_categories": zero}
    return summary, problems


# -------------------------------------------------------------------------------------- conformance and guards

def conformance() -> dict:
    import freeze_conformance as fc
    import v1_evidence_guard as vg
    res = fc.evaluate(*fc.load_inputs(ROOT))
    probs = fc.problems_of(res)
    statuses = {item["id"]: item["state"] for item in res.get("items", [])}
    guard = vg.check(ROOT)
    return {"when": C.now(), "head": C.git("rev-parse", "HEAD"), "kernel_tree": C.git("rev-parse", "HEAD:aisef2"),
            "freeze_conformance": {"problems": probs, "statuses": statuses, "summary": res.get("summary"), "ratchet_violations": res.get("ratchet_violations"),
                                   "pass": not probs and all(v == "PASS" for v in statuses.values()) and len(statuses) == 11,
                                   "f1_f2_f11": {k: statuses.get(k) for k in ("F1", "F2", "F11")}},
            "v1_evidence_guard": {"problems": guard, "pass": not guard},
            "w0": {"path": W0_REL, "sha256": _sha(W0_REL), "expected": W0_SHA, "unchanged": _sha(W0_REL) == W0_SHA},
            "v1_product_tree": C.git("rev-parse", "HEAD:aisef")}


# ------------------------------------------------------------------------------------------------- calibration

def _swap(obj, key, fn):
    """A copy with fn applied to every value under `key`, at any depth."""
    if isinstance(obj, dict):
        return {k: (fn(v) if k == key else _swap(v, key, fn)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_swap(v, key, fn) for v in obj]
    return obj


def _defective(pid, key, fn):
    from tests.v2 import refmodel
    real = refmodel.MODELS[pid]

    def model(events):
        return _swap(real(events), key, fn)
    return model


def _first_seed_with(pid, predicate, seeds):
    from aisef2.journal.format3 import reconstruct
    from aisef2.product.contract import plain
    from tests.v2.refmodel import MODELS
    for s in seeds:
        ev = [plain(e) for e in reconstruct(q4.generate(s)).events]
        try:
            if predicate(MODELS[pid](ev)):
                return s
        except Exception:  # noqa: BLE001 — a refusing trace is not the one wanted
            continue
    return None


def calibrate() -> dict:
    """§22: before the differential is trusted, each named defect is shown to be detected — a defective reference
    model claiming a wrong owner, a wrong retry target, a wrong terminal state; a chunk with a dropped trace, a
    duplicated seed, another kernel digest. Design seeds only; no kernel change; the real models restored."""
    from tests.v2 import refmodel
    import tests.v2  # noqa: F401
    seeds = range(*q4.PILOT_SEEDS)
    out = {"record": "AISEF V2 — Q4 CALIBRATION (§22): six defects detected before the run", "when": C.now(),
           "seeds": "design seeds outside the schedule; none of the 100,000", "detections": {}}
    owners = list(q4.OWNERS)
    defects = {
        "wrong_owner": ("failure_owner", "owner", lambda v: owners[(owners.index(v) + 1) % len(owners)] if v in owners else v,
                        lambda ans: any(st.get("owner") for st in ans.values())),
        "wrong_retry_target": ("retry_target", "failure_seq", lambda v: v + 1 if isinstance(v, int) else v,
                               lambda ans: any(isinstance(st.get("failure_seq"), int) for st in ans.values())),
        "wrong_terminal_state": ("terminal_state", "run", lambda v: "ABANDONED" if v == "ENDED" else "ENDED",
                                 lambda ans: ans.get("run") in ("ENDED", "ABANDONED")),
    }
    for name, (pid, key, fn, wanted) in defects.items():
        seed = _first_seed_with(pid, wanted, seeds)
        control = q4.evaluate(seed)
        real = refmodel.MODELS[pid]
        refmodel.MODELS[pid] = _defective(pid, key, fn)
        try:
            got = q4.evaluate(seed)
        finally:
            refmodel.MODELS[pid] = real
        again = q4.evaluate(seed)
        detected = control["class"] == "MATCHED" and got["class"] == "DIVERGENCE" and pid in (got.get("divergence") or {}).get("projections", {}) \
            and again["class"] == "MATCHED"
        out["detections"][name] = {"projection": pid, "seed": seed, "control": control["class"], "with_defect": got["class"],
                                   "divergent_projections": sorted((got.get("divergence") or {}).get("projections", {})), "after_restore": again["class"],
                                   "detected": detected}
    # aggregation-level defects on a small synthetic schedule built from real evaluations
    small = {"identity": {"seed_schedule": {"base": q4.PILOT_SEEDS[0], "chunks": 2, "chunk_size": 5, "total": 10,
                                            "ranges": [[q4.PILOT_SEEDS[0], q4.PILOT_SEEDS[0] + 4], [q4.PILOT_SEEDS[0] + 5, q4.PILOT_SEEDS[0] + 9]]}},
             "one_kernel_identity": "IDENT", "preregistered": {}}

    def chunk(k, seeds_):
        rows = [[s, "MATCHED", 10, "x"] for s in seeds_]
        return {"chunk": k, "attempt": 1, "seed_range": small["identity"]["seed_schedule"]["ranges"][k], "requested": 5, "attempted": len(rows),
                "terminal": len(rows), "counters": {c: sum(1 for r in rows if r[1] == c) for c in q4.CLASSES}, "rows": rows, "status": "GREEN",
                "one_kernel_identity": "IDENT", "divergences": [], "invariant_violations": [], "exceptions": [], "coverage": {},
                "_file": f"synthetic-{k}", "_sha256": "0" * 64}
    base = q4.PILOT_SEEDS[0]
    good = {0: [chunk(0, range(base, base + 5))], 1: [chunk(1, range(base + 5, base + 10))]}
    _, ok = reconcile(good, small)
    dropped = copy.deepcopy(good)
    dropped[1][0]["rows"] = dropped[1][0]["rows"][:-1]      # one trace never accounted; the worker still claims 5 attempted
    dropped[1][0]["counters"]["MATCHED"] = 4
    dropped[1][0]["attempted"] = dropped[1][0]["terminal"] = 4
    s_drop, p_drop = reconcile(dropped, small)
    dup = copy.deepcopy(good)
    dup[1][0]["rows"][0][0] = base + 4                        # the seed chunk 0 already holds
    s_dup, p_dup = reconcile(dup, small)
    other = copy.deepcopy(good)
    other[1][0]["one_kernel_identity"] = "OTHER-KERNEL"
    s_oth, p_oth = reconcile(other, small)
    out["detections"]["dropped_trace"] = {"control_problems": ok, "problems": p_drop, "silent_skip": s_drop["totals"]["SILENT_SKIP"],
                                          "detected": not ok and s_drop["totals"]["SILENT_SKIP"] == 1 and bool(p_drop)}
    out["detections"]["duplicate_seed"] = {"control_problems": ok, "problems": p_dup, "duplicated": s_dup["seeds"]["duplicated"],
                                           "detected": not ok and s_dup["seeds"]["duplicated"] == 1 and bool(p_dup)}
    out["detections"]["kernel_digest_mismatch"] = {"control_problems": ok, "problems": p_oth, "identities": s_oth["one_kernel_identity"]["count"],
                                                   "detected": not ok and s_oth["one_kernel_identity"]["count"] == 2 and bool(p_oth)}
    out["all_detected"] = all(d["detected"] for d in out["detections"].values())
    out["harness_digest"] = q4.identity()["harness_digest"]
    return out


# ------------------------------------------------------------------------------------------------------- main

def aggregate(out_dir: pathlib.Path) -> dict:
    subject = json.loads((out_dir / "SUBJECT.json").read_text(encoding="utf-8"))
    start = out_dir / "CONFORMANCE-start.json"
    start_rec = json.loads(start.read_text(encoding="utf-8")) if start.exists() else None
    ident = q4.identity()
    attempts = load_chunks(out_dir / "chunks")
    summary, problems = reconcile(attempts, subject)
    observed = attempts_observed(out_dir)
    for k, obs in observed.items():
        if k in summary["per_chunk"]:
            summary["per_chunk"][k]["attempts_observed"] = obs
    residual = [o for obs in observed.values() for o in obs if o["owned_after"] or o["escaped"] or not o["released_empty"]]
    if residual:
        problems.append(f"{len(residual)} chunk attempt(s) left a residual or escaped process")
    end_rec = conformance()
    for when, rec in (("start", start_rec), ("end", end_rec)):
        if rec is None:
            problems.append(f"no conformance snapshot at {when}")
        elif not (rec["freeze_conformance"]["pass"] and rec["v1_evidence_guard"]["pass"] and rec["w0"]["unchanged"]):
            problems.append(f"conformance at {when}: F1-F11 {rec['freeze_conformance']['pass']}, V1 guard {rec['v1_evidence_guard']['pass']}, W0 {rec['w0']['unchanged']}")
    if q4.one_kernel_identity(ident) != subject["one_kernel_identity"]:
        problems.append("the identity at aggregation is not the frozen subject's")
    problems += [f"subject at aggregation: {p}" for p in q4.subject_problems(ident) if not p.startswith("the working tree is dirty")]
    # the rung below is bound only when it is GREEN for this candidate (C2-P7-P8-BINDING-CORRIGENDUM-1: a FAILED summary was bound)
    for rel in (r for r in P7_EVIDENCE if r.endswith("SUMMARY.json")):
        low = json.loads((ROOT / rel).read_text(encoding="utf-8")) if (ROOT / rel).exists() else {}
        if low.get("verdict") != "GREEN" or (low.get("subject") or {}).get("semantic_candidate") != q4.SEMANTIC_CANDIDATE:
            problems.append(f"the rung below ({rel}) is not GREEN for {q4.SEMANTIC_CANDIDATE[:7]}: "
                            f"{low.get('verdict')}, candidate {(low.get('subject') or {}).get('semantic_candidate')}")
    dirty_outside = [ln for ln in ident["dirty"] if not ln[3:].startswith(q4.OUT_REL)]
    if dirty_outside:
        problems.append(f"the working tree is dirty outside {q4.OUT_REL}: {dirty_outside[:5]}")
    calib = out_dir / "CALIBRATION.json"
    calib_rec = json.loads(calib.read_text(encoding="utf-8")) if calib.exists() else None
    if not (calib_rec and calib_rec.get("all_detected")):
        problems.append("no calibration with every defect detected")
    resources = out_dir / "RESOURCES.json"
    res_rec = json.loads(resources.read_text(encoding="utf-8")) if resources.exists() else None
    rec = {
        "record": "AISEF V2 — Q4 DIFFERENTIAL (100,000 fresh traces on the exact candidate)", "rung": "Q4",
        "authority": "owner's P8 / QP-8 EXECUTION AUTHORIZATION (2026-09-28)", "aggregated": C.now(),
        "semantic_candidate": q4.SEMANTIC_CANDIDATE, "kernel_tree": q4.KERNEL_TREE, "execution_commit": subject["identity"]["execution_commit"],
        "aggregation_head": ident["execution_commit"],
        "identity": {k: ident[k] for k in ("kernel_digest", "reference_digest", "generator_digest", "harness_digest", "head_kernel_tree", "rfc")},
        "one_kernel_identity": q4.one_kernel_identity(ident), "subject": {"path": f"{q4.OUT_REL}/SUBJECT.json", "sha256": _sha(f"{q4.OUT_REL}/SUBJECT.json"),
                                                                           "one_kernel_identity": subject["one_kernel_identity"], "frozen_at": subject["frozen_at"]},
        "seed_schedule": subject["identity"]["seed_schedule"], "generator": subject["identity"]["generator"],
        "chunks": summary["per_chunk"], "chunk_attempts_observed": {str(k): v for k, v in sorted(observed.items())}, "totals": summary["totals"], "seeds": summary["seeds"], "one_kernel_digest_assertion": summary["one_kernel_identity"],
        "coverage_summary": summary["coverage_summary"], "coverage": summary["coverage"], "zero_sample_categories": summary["zero_sample_categories"],
        "calibration": {"path": f"{q4.OUT_REL}/CALIBRATION.json", "sha256": _sha(f"{q4.OUT_REL}/CALIBRATION.json"),
                        "all_detected": bool(calib_rec and calib_rec.get("all_detected"))},
        "conformance": {"start": start_rec, "end": end_rec},
        "resources": res_rec, "p7_evidence": {rel: _sha(rel) for rel in P7_EVIDENCE}, "seals": {rel: _sha(rel) for rel in SEALS},
        "v1_evidence": {"baseline": _sha("closure-evidence/v2/V1-EVIDENCE-BASELINE.json"), "w0": _sha(W0_REL), "product_tree": C.git("rev-parse", "HEAD:aisef")},
        "problems": problems, "status": "GREEN" if not problems else "FAILED",
    }
    return rec


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--calibrate", action="store_true")
    ap.add_argument("--conformance", choices=("start", "end"))
    ap.add_argument("--out", default=q4.OUT_REL)
    a = ap.parse_args(argv)
    out_dir = ROOT / a.out
    out_dir.mkdir(parents=True, exist_ok=True)
    if a.calibrate:
        rec = calibrate()
        (out_dir / "CALIBRATION.json").write_text(C.render(rec), encoding="utf-8")
        print(f"calibration: { {k: v['detected'] for k, v in rec['detections'].items()} } all {rec['all_detected']}")
        return 0 if rec["all_detected"] else 1
    if a.conformance:
        rec = conformance()
        (out_dir / f"CONFORMANCE-{a.conformance}.json").write_text(C.render(rec), encoding="utf-8")
        print(f"conformance {a.conformance}: F1-F11 {'PASS' if rec['freeze_conformance']['pass'] else 'FAIL'}, "
              f"V1 guard {'PASS' if rec['v1_evidence_guard']['pass'] else 'FAIL'}, W0 {'unchanged' if rec['w0']['unchanged'] else 'CHANGED'}")
        return 0 if rec["freeze_conformance"]["pass"] and rec["v1_evidence_guard"]["pass"] and rec["w0"]["unchanged"] else 1
    rec = aggregate(out_dir)
    (out_dir / "DIFFERENTIAL.json").write_text(C.render(rec), encoding="utf-8")
    t = rec["totals"]
    print(f"Q4 {rec['status']}: matched {t['MATCHED']} divergence {t['DIVERGENCE']} invariant {t['INVARIANT_VIOLATION']} exception {t['EXCEPTION']} "
          f"silent {t['SILENT_SKIP']} of {t['requested']}; identities {rec['one_kernel_digest_assertion']['count']}; "
          f"zero-sample {list(rec['zero_sample_categories'])}")
    for p in rec["problems"]:
        print(f"  problem: {p}")
    return 0 if rec["status"] == "GREEN" else 1


if __name__ == "__main__":
    sys.exit(main())
