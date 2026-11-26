"""V2.1 mutation: the execution-order table `mutation.py run --order` reads (docs/v2.1/MUTATION-RUNNER-V2.md §7.2),
derived from a committed T0 sweep record and from nothing else.

    python -P validation/v2/execution_order.py --record SWEEP.jsonl MEASURED_ON OUT.json   # a sweep's JSONL -> its record
    python -P validation/v2/execution_order.py --write SWEEP.json TABLE.json   # the table, from a record committed at HEAD
    python -P validation/v2/execution_order.py --write-freq RECORD.json TABLE.json   # RULE-2: the kill-frequency table,
                                                                                     # from a mutation record committed at HEAD
    python -P validation/v2/execution_order.py --check TABLE.json              # the table is what its record derives now
                                                                               # (either rule, read from the table itself)

The T0 sweep record (committed, e.g. under closure-evidence/v2/v2.1/): {"record", "measured_on": the 40-hex commit the
sweep ran at, "rows": [every line of the sweep's JSONL, as written]}; a row is one (null mutant, kill file) pair run
through the runner's own T0: {"module", "null": sha256 of `mutation.null_mutant(module source, func)`, "file",
"targets", "rows": [its T0 row: {"role": "t0", "outcome", "seconds", ...}], "original", "error", ...}.

RULE: a V2.1 target whose null mutant, at the tree the table is derived on, has a PASS T0 row for every kill file runs
its kill set in ascending T0 seconds, ties by declared position; each entry names the record (`from`: path, sha256) and
the seconds. Every other target is listed under `declared_order`, with why, and runs in declared order. The order
decides only which reproduced FAIL comes first, never a class (§7.1); `kill_tests` stays the declared list (ORD-4).

RULE-2 (owner ruling 2026-11-26 §2, versioned `kill-frequency/1`, BESIDE the T0 rule, never replacing it): each target
of a COMMITTED mutation record runs its recorded kill set in descending frequency of the record's `killed_by` files,
ties by declared position. The record is a CITED SOURCE for ordering only — never qualified measurement evidence;
admissibility, enumeration, kill confirmation and every verdict rule are untouched. `--check` re-derives whichever
rule the table itself declares (`rule_id`), byte for byte, from its committed source.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.v2 import mutation as m  # noqa: E402

RULE = "ascending T0 seconds of each kill file on the target's null mutant, ties by declared position"
RULE2 = ("descending kill frequency of each kill file in a committed mutation record's killed_by fields, "
         "ties by declared position")
RULE2_ID = "kill-frequency/1"


def render(doc: dict) -> str:
    return json.dumps(doc, indent=1, ensure_ascii=False) + "\n"


def sweep_record(jsonl: pathlib.Path, measured_on: str) -> dict:
    """The committed record of a sweep's JSONL output: its lines, unchanged, and the commit the sweep ran at."""
    if not re.fullmatch(r"[0-9a-f]{40}", measured_on):
        raise SystemExit(f"MEASURED_ON must be a full commit id: {measured_on!r}")
    return {"record": "AISEF V2.1 — T0 SWEEP: every distinct (null mutant, kill file) pair of the V2.1 targets, run "
                      "through the runner's own T0", "measured_on": measured_on,
            "rows": [json.loads(x) for x in jsonl.read_text(encoding="utf-8").splitlines() if x.strip()]}


def _source(root: pathlib.Path, rel: str, at: str | None) -> str:
    """The target's source: the working tree, or its bytes at commit `at` (round v2.3, W1-DESIGN §2.6: the table is
    verified against the round its sweep served, not against a later tree whose edits the F5 states account for)."""
    if at is None:
        return (root / rel).read_text(encoding="utf-8")
    return subprocess.run(["git", "-C", str(root), "show", f"{at}:{rel}"], capture_output=True,
                          encoding="utf-8", check=True).stdout


def table(root: pathlib.Path, sweep_rel: str, targets: dict[str, list[str]] | None = None, *,
          at: str | None = None) -> dict:
    """The table RULE derives from the record at `root / sweep_rel` for `targets` (default: mutation.V21_TARGETS)."""
    raw = (root / sweep_rel).read_bytes()
    rec, src = json.loads(raw), {"path": sweep_rel, "sha256": hashlib.sha256(raw).hexdigest()}
    t0: dict[tuple[str, str, str], float | None] = {}
    for r in rec["rows"]:
        key = (r["module"], r["null"], r["file"])
        if key in t0:
            raise SystemExit(f"{sweep_rel}: two rows for {key}")
        row = [x for x in r["rows"] if x.get("role") == "t0"]
        t0[key] = row[0]["seconds"] if len(row) == 1 and row[0]["outcome"] == "PASS" and not r.get("error") else None
    orders, declared = {}, {}
    for target, kill in sorted((m.V21_TARGETS if targets is None else targets).items()):
        rel, func = target.split("::")
        null = hashlib.sha256(m.null_mutant(_source(root, rel, at), func).encode()).hexdigest()
        if missing := [f for f in kill if t0.get((rel, null, f)) is None]:
            declared[target] = f"no PASS T0 row on its null mutant {null[:16]} for {missing}"
            continue
        files = sorted(kill, key=lambda f: t0[rel, null, f])   # sorted() is stable: ties keep the declared position
        orders[target] = {"files": files, "seconds": [t0[rel, null, f] for f in files], "from": src}
    return {"table": "AISEF V2.1 — MUTATION EXECUTION ORDER", "tool": "validation/v2/execution_order.py", "rule": RULE,
            "from": {**src, "measured_on": rec["measured_on"]}, "orders": orders, "declared_order": declared}


def freq_table(root: pathlib.Path, record_rel: str) -> dict:
    """The RULE-2 table derived from the mutation record at `root / record_rel` and from nothing else: per target,
    the entry's own `kill_tests` in descending `killed_by` frequency over its results (sorted() is stable: ties keep
    the declared position). A round record's last entry per target is its newest (read-time supersession); an entry
    with no kill set orders nothing. Deterministic: the same record bytes derive byte-identical tables."""
    raw = (root / record_rel).read_bytes()
    rec, src = json.loads(raw), {"path": record_rel, "sha256": hashlib.sha256(raw).hexdigest()}
    entries = rec.get("entries") if isinstance(rec.get("entries"), list) else rec.get("targets")
    if not isinstance(entries, list):
        raise SystemExit(f"{record_rel}: not a mutation record (no `entries` or `targets` list)")
    newest = {e["target"]: e for e in entries if isinstance(e, dict) and isinstance(e.get("target"), str)}
    orders = {}
    for target, e in sorted(newest.items()):
        kill = e.get("kill_tests")
        if not isinstance(kill, list) or not kill or not all(isinstance(f, str) for f in kill):
            continue
        count = dict.fromkeys(kill, 0)
        for r in e.get("results") or []:
            kb = r.get("killed_by") if isinstance(r, dict) else None
            f = kb.get("file") if isinstance(kb, dict) else None   # a non-dict killed_by orders nothing, never crashes
            if f in count:
                count[f] += 1
        files = sorted(kill, key=lambda f: -count[f])   # sorted() is stable: ties keep the declared position
        orders[target] = {"files": files, "kills": [count[f] for f in files], "from": src, "rule": RULE2_ID}
    return {"table": "AISEF V2.3 — MUTATION EXECUTION ORDER (RULE-2)", "tool": "validation/v2/execution_order.py",
            "rule": RULE2, "rule_id": RULE2_ID, "from": src, "orders": orders}


def _committed_record(path: pathlib.Path) -> str:
    rel, commit = m.committed(ROOT, path, path.read_bytes())
    if not commit:
        raise SystemExit(f"{rel} is not a file committed at HEAD: the table is derived from a committed record only")
    return rel


def check(table_path: pathlib.Path, *, at: str | None = None) -> list[str]:
    """[] when the table's source record is committed at HEAD and the table is byte for byte what it derives now,
    by the rule the table itself declares: no `rule_id` is the T0 rule, `rule_id` RULE2_ID is RULE-2, anything else
    is refused (fail closed) (`at`: derive the T0 rule's null mutants from the sources at that commit — the round
    the table serves)."""
    rule2 = False
    try:
        doc = json.loads(table_path.read_text(encoding="utf-8"))
        rule2 = isinstance(doc, dict) and "rule_id" in doc
        if rule2 and doc["rule_id"] != RULE2_ID:
            return [f"{table_path} declares an unknown rule_id {doc['rule_id']!r} (known: {RULE2_ID!r}) — fail closed"]
        rel = _committed_record(ROOT / doc["from"]["path"])
        derived = render(freq_table(ROOT, rel) if rule2 else table(ROOT, rel, at=at))
    except SystemExit as e:
        return [str(e)]
    except (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.CalledProcessError) as e:
        return [f"{table_path} or its {'source' if rule2 else 'sweep'} record cannot be read: {e!r}"]
    return [] if table_path.read_text(encoding="utf-8") == derived else \
        [f"{table_path} is not what {rel} derives now — re-run {'--write-freq' if rule2 else '--write'}"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--record", nargs=3, metavar=("SWEEP_JSONL", "MEASURED_ON", "OUT"))
    mode.add_argument("--write", nargs=2, metavar=("SWEEP_RECORD", "TABLE"))
    mode.add_argument("--write-freq", nargs=2, metavar=("MUTATION_RECORD", "TABLE"))
    mode.add_argument("--check", metavar="TABLE")
    a = ap.parse_args(argv)
    if a.record:
        jsonl, measured_on, out = a.record
        text = render(sweep_record(pathlib.Path(jsonl), measured_on))
        with pathlib.Path(out).open("x", encoding="utf-8") as f:   # a record is never replaced
            f.write(text)
        return 0
    if a.write:
        doc = table(ROOT, _committed_record(pathlib.Path(a.write[0])))
        pathlib.Path(a.write[1]).write_text(render(doc), encoding="utf-8")
        print(f"{len(doc['orders'])} targets ordered, {len(doc['declared_order'])} in declared order")
        return 0
    if a.write_freq:
        doc = freq_table(ROOT, _committed_record(pathlib.Path(a.write_freq[0])))
        pathlib.Path(a.write_freq[1]).write_text(render(doc), encoding="utf-8")
        print(f"{len(doc['orders'])} targets ordered by kill frequency ({RULE2_ID})")
        return 0
    problems = check(pathlib.Path(a.check))
    for p in problems:
        print(f"FAIL  {p}")
    print("execution order: " + ("FAIL" if problems else "PASS"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
