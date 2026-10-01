"""P1+ run history — every full-suite and CI attempt is recorded, and no failed attempt may disappear.

Owner decision "OWNER ACCEPTS P0 / AUTHORIZE P1" §3 and §5, as mechanism rather than intention:

* **append-only** — every committed version of the history must extend the previous one entry for entry, so a
  failed attempt cannot be dropped by editing the file, whether in the working tree or in a later commit;
* **a rerun never erases a failure** — a retry may satisfy a gate only when the failure it retries was classified
  into a class the preregistered policy marks retryable (ENVIRONMENT, PROVIDER) **and** the execution path has an
  approved retry count (resolved execution policy; `null` = none approved, never a default); any other case makes
  the rerun diagnostic only, and a later green attempt does not convert the failure;
* **V1-PF-001 stops the gate** — an attempt attributed to it must carry gate_effect STOP, except that after its WP-4.2
  replacement an exact legacy recurrence in the frozen V1 tree may carry RECORD_ONLY (a recorded, non-blocking FAIL —
  never a pass): owner ruling 2026-09-30, `V2-RETRY-POLICY-AMENDMENT-1.json`, derived from the attempt's typed
  `recurrence_facts` by `recurrence_effect`, failing closed to STOP on any missing or untyped fact;
* **one history per phase, closed by its seal** — once a phase's seal record exists (`P<n>-FINAL-SEAL.json`), its
  history must hold exactly the attempt count the seal names: nothing added, nothing removed. New attempts go to the
  first unsealed phase.

    python -P validation/v2/run_history.py record [--phase P2] <field=value> ...   # append one attempt
    python -P validation/v2/run_history.py --check                                 # every phase history
"""

from __future__ import annotations

import hashlib
import itertools
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
POLICY_REL = "closure-evidence/v2/V2-RETRY-POLICY.json"
#: append-only amendments overlaid on the preregistered policy (which stays byte-identical: the P1 seal binds it)
POLICY_AMENDMENTS = ("closure-evidence/v2/cycle2/V2-RETRY-POLICY-AMENDMENT-1.json",)
HISTORIES = {"P1": "closure-evidence/v2/P1-RUN-HISTORY.json", "P2": "closure-evidence/v2/P2-RUN-HISTORY.json",
             "P3": "closure-evidence/v2/P3-RUN-HISTORY.json", "P4": "closure-evidence/v2/P4-RUN-HISTORY.json",
             "P5": "closure-evidence/v2/P5-RUN-HISTORY.json", "P6": "closure-evidence/v2/P6-RUN-HISTORY.json",
             "P7": "closure-evidence/v2/P7-RUN-HISTORY.json", "P8": "closure-evidence/v2/P8-RUN-HISTORY.json",
             "P9": "closure-evidence/v2/P9-RUN-HISTORY.json", "P10": "closure-evidence/v2/P10-RUN-HISTORY.json",
             # Cycle 2 (WP-2.0.1): a history per Cycle-2 phase, under the same policy; Cycle-1 histories are sealed
             "C2-P0": "closure-evidence/v2/cycle2/C2-P0-RUN-HISTORY.json",
             # Cycle-2 lanes (owner ruling 2026-09-29, maximum safe parallel execution): one history per lane, each
             # closed by its lane closure when the lane was merged; the integration candidate's attempts go to the
             # integration history, the first one not closed
             "C2-P1": "closure-evidence/v2/cycle2/C2-P1-RUN-HISTORY.json",
             "C2-P2": "closure-evidence/v2/cycle2/C2-P2-RUN-HISTORY.json",
             "C2-P3": "closure-evidence/v2/cycle2/C2-P3-RUN-HISTORY.json",
             "C2-P4": "closure-evidence/v2/cycle2/C2-P4-RUN-HISTORY.json",
             "C2-INTEGRATION": "closure-evidence/v2/cycle2/C2-INTEGRATION-RUN-HISTORY.json",
             # C2-P5 (WP-2.5.1, WP-2.5.2): opened when the integration history was closed
             "C2-P5": "closure-evidence/v2/cycle2/C2-P5-RUN-HISTORY.json",
             # C2-P6 (QP-2.6): opened by the attempts of the C2-P5 acceptance commit
             "C2-P6": "closure-evidence/v2/cycle2/C2-P6-RUN-HISTORY.json",
             # opened when C2-P6 closed (owner ruling 2026-09-30 B): LANE-Q's three rungs in order, and LANE-X's C2-P10
             "C2-P7": "closure-evidence/v2/cycle2/C2-P7-RUN-HISTORY.json",
             "C2-P8": "closure-evidence/v2/cycle2/C2-P8-RUN-HISTORY.json",
             "C2-P9": "closure-evidence/v2/cycle2/C2-P9-RUN-HISTORY.json",
             "C2-P10": "closure-evidence/v2/cycle2/C2-P10-RUN-HISTORY.json",
             # the final integration candidate (LANE-Q + LANE-X): its gate, its requalification (R4) and the fresh Q4/Q5
             "C2-FINAL": "closure-evidence/v2/cycle2/C2-FINAL-RUN-HISTORY.json"}
#: the record that closes a phase's history: a FINAL SEAL for P1-P6; for P7, the owner's acceptance of the corrected
#: candidate's Q0-Q3 (there is no P7 seal builder — P7 qualifies, it does not seal)
SEALS = {"P1": "closure-evidence/v2/P1-FINAL-SEAL.json", "P2": "closure-evidence/v2/P2-FINAL-SEAL.json",
         "P3": "closure-evidence/v2/P3-FINAL-SEAL.json", "P4": "closure-evidence/v2/P4-FINAL-SEAL.json",
         "P5": "closure-evidence/v2/P5-FINAL-SEAL.json", "P6": "closure-evidence/v2/P6-FINAL-SEAL.json",
         "P7": "closure-evidence/v2/P7-ACCEPTANCE.json", "P8": "closure-evidence/v2/P8-ACCEPTANCE.json",
         "P9": "closure-evidence/v2/P9-ACCEPTANCE.json", "P10": "closure-evidence/v2/P10-ACCEPTANCE.json",
         # Cycle 2: C2-P0 by the owner's acceptance (2026-09-29); each lane by its lane closure, written when the lane
         # was merged into the integration candidate — a closure of the lane's attempts, not an owner acceptance
         "C2-P0": "closure-evidence/v2/cycle2/C2-P0-ACCEPTANCE.json",
         "C2-P1": "closure-evidence/v2/cycle2/C2-P1-LANE-CLOSURE.json",
         "C2-P2": "closure-evidence/v2/cycle2/C2-P2-LANE-CLOSURE.json",
         "C2-P3": "closure-evidence/v2/cycle2/C2-P3-LANE-CLOSURE.json",
         "C2-P4": "closure-evidence/v2/cycle2/C2-P4-LANE-CLOSURE.json",
         # the integration history, by its closure when C2-P5 began (not an owner acceptance)
         "C2-INTEGRATION": "closure-evidence/v2/cycle2/C2-INTEGRATION-CLOSURE.json",
         # C2-P5, by the owner's acceptance of the corrected PLAN-V2.2 (2026-09-30)
         "C2-P5": "closure-evidence/v2/cycle2/C2-P5-ACCEPTANCE.json",
         # C2-P6, by its closure when the requalified QP-2.6 was GREEN (owner ruling 2026-09-30 B: automatic downstream)
         "C2-P6": "closure-evidence/v2/cycle2/C2-P6-CLOSURE.json"}
HISTORY_REL = HISTORIES["P1"]
RESULTS = ("PASS", "FAIL")
GATE_EFFECTS = ("COUNTS", "DIAGNOSTIC_ONLY", "STOP", "RECORD_ONLY")


def _load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_policy(root: pathlib.Path = ROOT) -> dict:
    """The preregistered policy with its amendments overlaid (an absent amendment adds nothing: fail closed)."""
    policy = _load(root / POLICY_REL)
    for rel in POLICY_AMENDMENTS:
        if (root / rel).exists():
            amendment = _load(root / rel)
            policy.setdefault("known_defect_lifecycle", {}).update(amendment.get("known_defect_lifecycle", {}))
            policy["amendments"] = [*policy.get("amendments", []), rel]
    return policy


def _v1_tree(root: pathlib.Path) -> str | None:
    got = subprocess.run(["git", "rev-parse", "HEAD:aisef"], cwd=root, capture_output=True, encoding="utf-8")
    return got.stdout.strip() if got.returncode == 0 else None


def replacement_complete(lifecycle: dict, root: pathlib.Path) -> bool:
    """Every replacement evidence file holds its stated fact."""
    for ev in lifecycle.get("replacement", {}).get("evidence", []) or [None]:
        if not ev or not (root / ev["path"]).exists():
            return False
        value = _load(root / ev["path"]).get(ev["key"])
        if "equals" in ev and value != ev["equals"]:
            return False
        if "has" in ev and not (isinstance(value, dict) and ev["has"] in value):
            return False
    return True


def recurrence_effect(entry: dict, entries: list[dict], policy: dict, root: pathlib.Path = ROOT,
                      v1_tree: str | None = None) -> tuple[str, list[str]]:
    """The gate effect a recorded V1-PF-001 recurrence must carry: RECORD_ONLY only when every fact of an exact legacy
    recurrence after the replacement is typed on the attempt and holds; STOP otherwise, with the reasons."""
    lc = policy.get("known_defect_lifecycle", {}).get(entry.get("known_defect"))
    if not lc:
        return "STOP", ["no lifecycle for this defect in the policy"]
    why = []
    if not replacement_complete(lc, root):
        why.append(f"the {lc.get('replacement', {}).get('work_package')} replacement is not complete")
    facts = entry.get("recurrence_facts")
    if not isinstance(facts, dict) or not facts.get("failing"):
        return "STOP", why + ["no typed recurrence facts"]
    legacy, v2, v2_tests = lc["legacy_code_prefix"], lc["v2_code_prefix"], lc["v2_test_prefix"]
    for f in facts["failing"]:
        frames = f.get("product_frames") or []
        if f.get("error_type") != lc["error_type"] or not frames or frames[-1] != lc["component"]:
            why.append(f"{f.get('test')}: not the known signature ({f.get('error_type')} at {frames[-1:] or 'no frame'})")
        if not frames or not all(x.startswith(legacy) for x in frames) or any(x.startswith(v2) for x in frames):
            why.append(f"{f.get('test')}: a product frame outside the frozen V1 tree")
        if any(x.startswith(v2_tests) for x in f.get("test_frames") or []) or str(f.get("test", "")).startswith(v2_tests):
            why.append(f"{f.get('test')}: a V2 test")
    tree = v1_tree if v1_tree is not None else _v1_tree(root)
    if facts.get("v1_product_tree") != lc["frozen_v1_tree"] or tree != lc["frozen_v1_tree"]:
        why.append(f"the V1 tree is not the frozen one (attempt {facts.get('v1_product_tree')}, here {tree})")
    if facts.get("cycle1_evidence_changed") is not False or entry.get("v1_evidence_changed") is not False:
        why.append("Cycle-1 evidence changed, or its state is not recorded")
    q = facts.get("v2_process_range_qualification") or {}
    qp = root / q["path"] if q.get("path") else None
    if not qp or not qp.exists() or hashlib.sha256(qp.read_bytes().replace(b"\r\n", b"\n")).hexdigest() != q.get("sha256") \
            or _load(qp).get("verdict") != "GREEN":
        why.append("no GREEN V2 process-range qualification bound by path and sha256")
    if any(x.startswith(v2) for e in entries for f in ((e.get("recurrence_facts") or {}).get("failing") or [])
           for x in f.get("product_frames") or []):
        why.append("the history holds the error in the V2 path")
    return ("STOP", why) if why else ("RECORD_ONLY", [])


def entry_problems(entries: list[dict], policy: dict, root: pathlib.Path = ROOT, v1_tree: str | None = None) -> list[str]:
    classes = set(policy["retryable_classes"]) | set(policy["diagnostic_only_classes"])
    out = []
    for i, e in enumerate(entries, 1):
        tag = f"entry {i}"
        if e.get("seq") != i:
            out.append(f"{tag}: seq must be {i}, found {e.get('seq')}")
        if len(e.get("commit", "")) != 40:
            out.append(f"{tag}: commit must be a full SHA")
        if e.get("result") not in RESULTS:
            out.append(f"{tag}: result must be one of {RESULTS}")
        if not isinstance(e.get("v1_evidence_changed"), bool):
            out.append(f"{tag}: v1_evidence_changed must be recorded as a bool")
        if e.get("gate_effect") not in GATE_EFFECTS:
            out.append(f"{tag}: gate_effect must be one of {GATE_EFFECTS}")
        if e.get("result") == "PASS":
            if e.get("classification") is not None or e.get("failing_tests"):
                out.append(f"{tag}: a PASS carries no classification and no failing tests")
            if e.get("v1_evidence_changed"):
                out.append(f"{tag}: V1 evidence changed, so this attempt cannot be a PASS")
        else:
            if e.get("classification") not in classes:
                out.append(f"{tag}: a FAIL must be classified into {sorted(classes)}")
            if not e.get("failing_tests"):
                out.append(f"{tag}: a FAIL must name what failed")
            if not e.get("classification_evidence"):
                out.append(f"{tag}: a classification must cite its evidence")
            permitted = e.get("classification") in policy["retryable_classes"]
            if e.get("retry_permitted") is not permitted:
                out.append(f"{tag}: retry_permitted must be {permitted} for class {e.get('classification')}")
            if e.get("known_defect") in policy["stop_on_recurrence"] and e.get("gate_effect") != "STOP":
                effect, why = recurrence_effect(e, entries, policy, root, v1_tree)
                if not (effect == "RECORD_ONLY" and e.get("gate_effect") == "RECORD_ONLY"):
                    out.append(f"{tag}: {e['known_defect']} recurred — gate_effect must be STOP ({'; '.join(why) or 'not RECORD_ONLY'})")
        if e.get("gate_effect") == "RECORD_ONLY" and (e.get("result") != "FAIL"
                                                      or e.get("known_defect") not in policy.get("known_defect_lifecycle", {})):
            out.append(f"{tag}: RECORD_ONLY is only a failed attempt's effect, for a known defect with a lifecycle")
        r = e.get("retry_of")
        if r is not None:
            prior = entries[r - 1] if isinstance(r, int) and 1 <= r < i else None
            if prior is None or prior.get("result") != "FAIL":
                out.append(f"{tag}: retry_of must name an earlier FAIL")
            elif (prior.get("commit"), prior.get("where"), prior.get("job")) != (e.get("commit"), e.get("where"), e.get("job")):
                out.append(f"{tag}: a retry must be of the same commit, place and job")
            elif not prior.get("retry_permitted") and e.get("gate_effect") != "DIAGNOSTIC_ONLY":
                out.append(f"{tag}: retries a {prior.get('classification')} failure — it is diagnostic only")
    counted: dict[tuple, int] = {}
    for e in entries:
        if e.get("retry_of") is not None and e.get("gate_effect") == "COUNTS":
            key = (e.get("commit"), e.get("where"), e.get("job"))
            counted[key] = counted.get(key, 0) + 1
            approved = approved_retry_count(policy, e.get("where"))
            if approved is None:
                out.append(f"entry {e.get('seq')}: no approved retry count for phase-gate:{e.get('where')} — "
                           "the retry is diagnostic only")
            elif counted[key] > approved:
                out.append(f"entry {e.get('seq')}: more gate-counting retries than the approved {approved} "
                           f"for {key[0][:12]} {key[1]}")
    return out


def approved_retry_count(policy: dict, where: str | None) -> int | None:
    """The approved retry count for a phase-gate path, or None when none is approved (never a default)."""
    return policy["retry_count"]["approved_counts_by_execution_path"].get(f"phase-gate:{where}")


def append_only_problems(versions: list[list[dict]]) -> list[str]:
    """Each version must extend the one before it, entry for entry. Oldest first."""
    out = []
    for n, (old, new) in enumerate(itertools.pairwise(versions), 1):
        if new[:len(old)] != old:
            gone = [e.get("seq") for e in old if e not in new]
            out.append(f"history version {n + 1} does not extend version {n}: attempts removed or rewritten {gone}")
    return out


def gate_green(entries: list[dict], commit: str, where: str, job: str | None = None, policy: dict | None = None) -> bool:
    """Green only if the latest attempt passed and, when it follows failures, every failure permitted a retry and
    the path has an approved retry count the retries stayed within."""
    policy = policy or _load(ROOT / POLICY_REL)
    mine = [e for e in entries if (e["commit"], e["where"], e.get("job")) == (commit, where, job)]
    if not mine or mine[-1]["result"] != "PASS":
        return False
    failures = [e for e in mine[:-1] if e["result"] == "FAIL"]
    if not failures:
        return True
    approved = approved_retry_count(policy, where)
    return approved is not None and len(failures) <= approved and all(e["retry_permitted"] for e in failures)


def committed_versions(root: pathlib.Path = ROOT, rel: str = HISTORY_REL) -> list[list[dict]]:
    revs = subprocess.run(["git", "log", "--reverse", "--format=%H", "--", rel], cwd=root,
                          capture_output=True, encoding="utf-8", check=True).stdout.split()
    out = []
    for rev in revs:
        shown = subprocess.run(["git", "show", f"{rev}:{rel}"], cwd=root, capture_output=True, encoding="utf-8")
        if shown.returncode == 0:
            out.append(json.loads(shown.stdout)["entries"])
    return out


def seal_problems(phase: str, entries: list[dict], seal: dict | None) -> list[str]:
    """A sealed phase's history holds exactly the attempts its seal counted."""
    if seal is None:
        return []
    sealed = seal["attempt_history"]["total_attempts"]
    return [] if len(entries) == sealed else \
        [f"{phase} history is sealed at {sealed} attempts and now has {len(entries)}: attempts added or removed"]


def _seal(phase: str, root: pathlib.Path) -> dict | None:
    rel = SEALS.get(phase)
    return _load(root / rel) if rel and (root / rel).exists() else None


def open_phase(root: pathlib.Path = ROOT) -> str:
    """The first phase whose history is not sealed: where new attempts go."""
    return next(ph for ph in HISTORIES if _seal(ph, root) is None)


def check(root: pathlib.Path = ROOT) -> list[str]:
    policy = load_policy(root)
    if not (root / HISTORY_REL).exists():
        return [f"{HISTORY_REL} is missing"]
    out = []
    for phase, rel in HISTORIES.items():
        if not (root / rel).exists():
            continue
        current = _load(root / rel)["entries"]
        out += [f"{phase}: {p}" for p in entry_problems(current, policy)
                + append_only_problems(committed_versions(root, rel) + [current])]
        out += seal_problems(phase, current, _seal(phase, root))
    return out


def record(fields: dict, root: pathlib.Path = ROOT, phase: str | None = None) -> dict:
    phase = phase or open_phase(root)
    if _seal(phase, root) is not None:
        raise SystemExit(f"refusing to record: the {phase} history is sealed ({SEALS[phase]})")
    path = root / HISTORIES[phase]
    doc = _load(path) if path.exists() else {
        "record": f"AISEF V2 — {phase} RUN HISTORY", "policy": POLICY_REL,
        "rule": "append-only; every full-suite and CI attempt, failed or not; see validation/v2/run_history.py",
        "entries": []}
    entry = {"seq": len(doc["entries"]) + 1, **fields}
    problems = entry_problems(doc["entries"] + [entry], load_policy(root), root)
    if problems:
        raise SystemExit("refusing to record: " + "; ".join(problems))
    doc["entries"].append(entry)
    path.parent.mkdir(parents=True, exist_ok=True)   # a Cycle-2 history lives under closure-evidence/v2/cycle2/
    path.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return entry


def _value(v: str):
    try:
        return json.loads(v)
    except json.JSONDecodeError:
        return v


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["record"]:
        rest, phase = argv[1:], None
        if rest[:1] == ["--phase"]:
            phase, rest = rest[1], rest[2:]
        fields = dict(a.split("=", 1) for a in rest)
        entry = record({k: _value(v) for k, v in fields.items()}, phase=phase)
        print(f"recorded attempt {entry['seq']}: {entry['result']} {entry['commit'][:12]} {entry['where']}")
        return 0
    problems = check()
    for p in problems:
        print(f"FAIL  {p}")
    print("run history: " + ("FAIL" if problems else "PASS"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
