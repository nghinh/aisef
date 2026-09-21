"""P1+ run history — every full-suite and CI attempt is recorded, and no failed attempt may disappear.

Owner decision "OWNER ACCEPTS P0 / AUTHORIZE P1" §3 and §5, as mechanism rather than intention:

* **append-only** — every committed version of the history must extend the previous one entry for entry, so a
  failed attempt cannot be dropped by editing the file, whether in the working tree or in a later commit;
* **a rerun never erases a failure** — a retry may satisfy a gate only when the failure it retries was classified
  into a class the preregistered policy marks retryable (ENVIRONMENT, PROVIDER); any other class makes the rerun
  diagnostic only, and a later green attempt does not convert the failure;
* **V1-PF-001 stops the gate** — an attempt attributed to it must carry gate_effect STOP.

    python -P validation/v2/run_history.py record <field=value> ...   # append one attempt
    python -P validation/v2/run_history.py --check                    # schema, policy and append-only history
"""

from __future__ import annotations

import itertools
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
POLICY_REL = "closure-evidence/v2/V2-RETRY-POLICY.json"
HISTORY_REL = "closure-evidence/v2/P1-RUN-HISTORY.json"
RESULTS = ("PASS", "FAIL")
GATE_EFFECTS = ("COUNTS", "DIAGNOSTIC_ONLY", "STOP")


def _load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def entry_problems(entries: list[dict], policy: dict) -> list[str]:
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
                out.append(f"{tag}: {e['known_defect']} recurred — gate_effect must be STOP")
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
            if counted[key] > policy["max_gate_retries_per_attempt_chain"]:
                out.append(f"entry {e.get('seq')}: more gate-counting retries than the preregistered "
                           f"{policy['max_gate_retries_per_attempt_chain']} for {key[0][:12]} {key[1]}")
    return out


def append_only_problems(versions: list[list[dict]]) -> list[str]:
    """Each version must extend the one before it, entry for entry. Oldest first."""
    out = []
    for n, (old, new) in enumerate(itertools.pairwise(versions), 1):
        if new[:len(old)] != old:
            gone = [e.get("seq") for e in old if e not in new]
            out.append(f"history version {n + 1} does not extend version {n}: attempts removed or rewritten {gone}")
    return out


def gate_green(entries: list[dict], commit: str, where: str, job: str | None = None) -> bool:
    """Green only if the latest attempt passed and every earlier failure on it permitted a retry."""
    mine = [e for e in entries if (e["commit"], e["where"], e.get("job")) == (commit, where, job)]
    if not mine or mine[-1]["result"] != "PASS":
        return False
    return all(e["retry_permitted"] for e in mine[:-1] if e["result"] == "FAIL")


def committed_versions(root: pathlib.Path = ROOT) -> list[list[dict]]:
    revs = subprocess.run(["git", "log", "--reverse", "--format=%H", "--", HISTORY_REL], cwd=root,
                          capture_output=True, encoding="utf-8", check=True).stdout.split()
    out = []
    for rev in revs:
        shown = subprocess.run(["git", "show", f"{rev}:{HISTORY_REL}"], cwd=root, capture_output=True,
                               encoding="utf-8")
        if shown.returncode == 0:
            out.append(json.loads(shown.stdout)["entries"])
    return out


def check(root: pathlib.Path = ROOT) -> list[str]:
    policy = _load(root / POLICY_REL)
    path = root / HISTORY_REL
    if not path.exists():
        return [f"{HISTORY_REL} is missing"]
    current = _load(path)["entries"]
    return entry_problems(current, policy) + append_only_problems(committed_versions(root) + [current])


def record(fields: dict, root: pathlib.Path = ROOT) -> dict:
    path = root / HISTORY_REL
    doc = _load(path) if path.exists() else {
        "record": "AISEF V2 — P1 RUN HISTORY", "policy": POLICY_REL,
        "rule": "append-only; every full-suite and CI attempt, failed or not; see validation/v2/run_history.py",
        "entries": []}
    entry = {"seq": len(doc["entries"]) + 1, **fields}
    problems = entry_problems(doc["entries"] + [entry], _load(root / POLICY_REL))
    if problems:
        raise SystemExit("refusing to record: " + "; ".join(problems))
    doc["entries"].append(entry)
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
        fields = dict(a.split("=", 1) for a in argv[1:])
        entry = record({k: _value(v) for k, v in fields.items()})
        print(f"recorded attempt {entry['seq']}: {entry['result']} {entry['commit'][:12]} {entry['where']}")
        return 0
    problems = check()
    for p in problems:
        print(f"FAIL  {p}")
    print("run history: " + ("FAIL" if problems else "PASS"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
