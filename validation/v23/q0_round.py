"""v2.3 Q0-1: the distinct round-v2.3 Q0 qualification round (docs/v2.3/amendments/Q0-1-V23-ROUND.md).

History, never rewritten: the v2.2 Q0 record V22_REL (sha256 V22_SHA256). Its GATED test
(tests/v2/p0/test_checker_calibration.py::CheckerCalibration) is replayed at v2.2.0 by validation/v23/replay_v22.py,
where the record must regenerate byte-identically (replay_v22.Q0_REPLAYED).

Round v2.3: its own record, V23_REL — the SAME calibration (validation/v2/checker_calibration.run(): every checker passes
the clean tree, fails its committed known-bad fixture for the named reason, and an always-PASS mutant of it is
rejected) run on the HEAD tree inside `version_forward.in_round("v2.3")`, wrapped with the round's identity. The gated
counterpart tests/v23/test_v23_q0_round.py::Q0RoundV23 requires, with ledger seq 13 committed by the owner, every rule
of `problems`: the v2.2 record still its v2.2.0 bytes, every checker calibrated, no v2.2 checker dropped, each v2.2
checker's contract kept (`contract_problems`, Q0P-1), the round's own module scope (`v23_scope_problems`, Q0P-2), and
this record present and equal to what the HEAD tree derives. Nothing here relaxes a checker: a W1-W6 edit that moves a
clean result leaves the round red until the checker is calibrated again (the amendment's delta table), and no edit of
a fixture, an expected reason or the scope list is accepted without a new q0_round.py (a new patch, a new ruling).

    python3 -P validation/v23/q0_round.py --check   # round open + this tree vs V23_REL and the history; exit 1 on any
                                                     # problem (CHECK_ARGV: the round-v2.3 Q0 guard, Q0P-3)
    python3 -P validation/v23/q0_round.py --write   # write V23_REL once: refused unless round v2.3 is open, every
                                                     # rule holds and the file is absent (a re-seal is `git rm` +
                                                     # --write in one commit)

Both print the per-checker delta against the v2.2 record (`delta`): what the owner reviews.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

V22_REL = "closure-evidence/v2/v2.1/Q0-CHECKER-CALIBRATION.json"
#: the LF sha256 of V22_REL at v2.2.0 (da3ea33f) — and at every commit since: history, never rewritten
V22_SHA256 = "714625b14e8972f166b37a467b5f83761d1f2672d076e5f5f0f342e2eb91332c"
#: v2.2.0, the commit whose bytes are the v2.2 contract (Q0P-1)
V22_COMMIT = "da3ea33f3b695aaca73e87a704145a0193aced23"
#: round v2.3's own record: a new file outside closure-evidence/ (Amendment A2 placement; the amendment argues why)
V23_REL = "docs/v2.3/evidence/q0-round/Q0-CHECKER-CALIBRATION-V23.json"
ROUND = "v2.3"
_CC = "aisef_v2_checker_calibration"      # the alias tests/v2/p0/test_checker_calibration.py loads it under
#: Q0P-3: the round-v2.3 Q0 guard, in place of `validation/v2/checker_calibration.py --check` (which no v2.3 tree
#: passes after the first W1a/W1b edit) in every guard set a round-v2.3 record runs (p5_acceptance GUARDS, ...)
CHECK_ARGV = ("validation/v23/q0_round.py", "--check")
#: Q0P-1: what a round may not change in a v2.2 checker's entry (plus its known-bad fixture file's v2.2.0 bytes)
CONTRACT = ("package", "fixture", "expected")
#: Q0P-2, round v2.3 only. v2.2's module rule (checker_calibration.uncovered_checker_modules) sees validation/v2 alone,
#: and Amendment A2 puts every new v2.3 module in validation/v23. There each module is a registered checker's source,
#: or one of these, ruled by ledger seq 13 (R5 Q0_ROUND) and ledger seq 14 (PIN-57 Option C): the round's own
#: calibration (as NOT_CHECKERS keeps checker_calibration.py) and the round's gate tools, each pinned by V23_PINNED
#: with its own always-run negative tests.
#: The list is closed: adding a module to it is a new q0_round.py, so a new patch and a new ruling.
NOT_CHECKERS_V23 = frozenset({"validation/v23/__init__.py", "validation/v23/ledger_digest.py",
                              "validation/v23/q0_round.py", "validation/v23/replay_v22.py",
                              # ledger seq 14 (PIN-57 Option C, owner ruling 2026-11-26 §3): the F5 recorder stays an
                              # owner-ruled non-checker ONLY while no gate consumes its observation data as
                              # qualification authority (docs/v2.3/evidence/PIN-57-MODULE-ROLES.md §3.3); that
                              # condition and its calibration are drift-pinned, always-run, by
                              # tests/v23/test_v23_unregistered_checkers.py
                              "validation/v23/observe.py",
                              # ledger seq 14 (owner ruling 2026-11-26 §3): B2 Tier-0 ground-truth tooling (protocol
                              # §8 prep) — tooling, not checkers: no gate consumes their output and no known-bad
                              # fixture exists (absence pinned by tests/v23/test_v23_unregistered_checkers.py).
                              # Promotion clause: when ground_truth/corpus.py --check becomes a gate at the B2
                              # manifest (W6), it enters cc.REGISTRY with a calibrated checker and leaves this list
                              # (a new q0_round.py, a new patch, a new ruling).
                              "validation/v23/ground_truth/__init__.py", "validation/v23/ground_truth/corpus.py",
                              "validation/v23/ground_truth/labels.py", "validation/v23/ground_truth/metrics.py"})
#: Q0P-2: the v2.3 code destructive_authority must scan (L1-AUTHCHK widens its SCOPES and ledgers the sites there)
V23_SCOPES = ("validation/v23", "tests/v23")
DA_REL = "validation/v2/destructive_authority.py"


def cc():
    """validation/v2/checker_calibration.py, the one module both rounds calibrate with (shared with the v2.2 test)."""
    if _CC not in sys.modules:
        spec = importlib.util.spec_from_file_location(_CC, ROOT / "validation" / "v2" / "checker_calibration.py")
        sys.modules[_CC] = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sys.modules[_CC])
    return sys.modules[_CC]


def _lf(b: bytes) -> bytes:
    return b.replace(b"\r\n", b"\n")


def _lf_sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(_lf(path.read_bytes())).hexdigest()


def run() -> dict:
    """checker_calibration.run() on this tree in round v2.3. Without L1-F5's `in_round` the round's own selection does
    not exist yet; the calibration then runs on the v2.2 rule — stricter for the round-aware cleans (currency_dag,
    mutation), so it can be red, never a false green — and the counterpart fails on the closed round anyway."""
    from validation.v2 import version_forward as vf
    with (vf.in_round(ROUND) if hasattr(vf, "in_round") else contextlib.nullcontext()):
        return cc().run()


def record(result: dict) -> dict:
    return {"record": "AISEF V2.3 — Q0 CHECKER CALIBRATION (round v2.3)", "round": ROUND,
            "history": {"path": V22_REL, "sha256": V22_SHA256, "replayed_at": V22_COMMIT,
                        "replay": "validation/v23/replay_v22.py"},
            "calibration": result}


def render(result: dict) -> str:
    return json.dumps(record(result), indent=1, ensure_ascii=False) + "\n"


def history_problems(root: pathlib.Path = ROOT) -> list[str]:
    """The v2.2 Q0 record is history: present and its v2.2.0 bytes (LF), or the round fails closed naming it."""
    p = root / V22_REL
    if not p.is_file():
        return [f"the v2.2 Q0 record {V22_REL} is missing (history: fail closed)"]
    if (got := _lf_sha256(p)) != V22_SHA256:
        return [f"the v2.2 Q0 record {V22_REL} is not its v2.2.0 bytes: sha256 {got}, history {V22_SHA256}"]
    return []


def record_problems(result: dict, root: pathlib.Path = ROOT) -> list[str]:
    """V23_REL against what this tree derives in round v2.3: missing, corrupted (not UTF-8 JSON) or stale."""
    p = root / V23_REL
    if not p.is_file():
        return [f"the round-v2.3 Q0 record {V23_REL} is missing"]
    try:
        text = p.read_text(encoding="utf-8")
        json.loads(text)
    except (UnicodeDecodeError, ValueError):
        return [f"the round-v2.3 Q0 record {V23_REL} is corrupted (not UTF-8 JSON)"]
    if text != render(result):
        return [f"the round-v2.3 Q0 record {V23_REL} is stale or corrupted: it is not what this tree derives in round v2.3"]
    return []


def dropped(result: dict, root: pathlib.Path = ROOT) -> list[str]:
    """Every checker the v2.2 record calibrated is still calibrated in round v2.3 (a round may add, never drop one)."""
    try:
        old = [c["checker"] for c in json.loads((root / V22_REL).read_text(encoding="utf-8"))["checkers"]]
    except (OSError, ValueError, KeyError, TypeError):
        return []     # history_problems names it
    now = {c["checker"] for c in result["checkers"] if c.get("calibrated")}
    return [f"v2.2 Q0 checker {n} is not calibrated in round v2.3" for n in old if n not in now]


def contract_problems(result: dict, root: pathlib.Path = ROOT, commit: str | None = None) -> list[str]:
    """Q0P-1: every checker of the v2.2 record keeps its v2.2 contract in round v2.3 — `package`, `fixture` and
    `expected` equal to the v2.2 record's, and its known-bad fixture file the LF bytes v2.2.0 (`commit`) committed. A
    weakened fixture or expected reason (`"expect": ""` matches every problem) keeps the round red, before and after
    the first write. No exception list: changing a contract needs a new q0_round.py, a new patch and a new ruling."""
    if history_problems(root):
        return []                       # history_problems names it; the contract is read from intact history only
    commit = commit or V22_COMMIT
    now = {c.get("checker"): c for c in result["checkers"]}
    out = []
    for o in json.loads((root / V22_REL).read_text(encoding="utf-8"))["checkers"]:
        name, n = o["checker"], now.get(o["checker"])
        if n is None:
            continue                    # dropped() names it
        out += [f"v2.2 Q0 checker {name}: {k} {n.get(k)!r} is not its v2.2 contract {o[k]!r}" for k in CONTRACT
                if n.get(k) != o[k]]
        blob = subprocess.run(["git", "-C", str(root), "show", f"{commit}:{o['fixture']}"], capture_output=True,
                              env=dict(os.environ, GIT_NO_REPLACE_OBJECTS="1"))
        p = root / o["fixture"]
        if blob.returncode != 0:
            out.append(f"v2.2 Q0 checker {name}: the v2.2.0 bytes of {o['fixture']} are unreadable (fail closed)")
        elif not p.is_file() or _lf(p.read_bytes()) != _lf(blob.stdout):
            out.append(f"v2.2 Q0 checker {name}: its known-bad fixture {o['fixture']} is not its v2.2.0 bytes")
    return out


def v23_scope_problems(root: pathlib.Path = ROOT) -> list[str]:
    """Q0P-2, round v2.3's own coverage of its own code: (a) every validation/v23 module is a registered checker's
    source or in NOT_CHECKERS_V23; (b) destructive_authority's SCOPES cover V23_SCOPES, so its calibrated clean
    requires every destructive site there to be ledgered; (c) no validation/v23 module calls a subprocess with text
    and no encoding (the calibrated v2_encoding_scanner's own scan; tests/v23 is scanned by tests/test_meta.py)."""
    c = cc()
    covered = {s for make in c.REGISTRY for s in make().sources}
    mods = sorted(p.relative_to(root).as_posix() for p in (root / "validation" / "v23").rglob("*.py"))
    out = [f"round v2.3: validation/v23 module with no calibration: {m}" for m in mods
           if m not in covered and m not in NOT_CHECKERS_V23]
    try:
        scopes = c._load("_q0_round_scopes_" + hashlib.sha256(str(root).encode()).hexdigest()[:16], root / DA_REL).SCOPES
    except Exception:                    # noqa: BLE001 — unreadable or broken: fail closed, named below
        scopes = ()
    out += [f"round v2.3: {DA_REL} SCOPES does not cover {s} (L1-AUTHCHK: widen SCOPES, ledger its sites)"
            for s in V23_SCOPES if s not in scopes]
    scan = c._load("_v1_test_meta_scanner", c.ROOT / "tests" / "test_meta.py").TestKhongDocDauRaBangBangMaCuaMay(
        "test_phep_quet_that_su_thay_duoc_loi")._thieu
    return out + [f"round v2.3: subprocess text without an encoding: {m} line {n}" for m in mods for n in scan(root / m)]


def delta(result: dict, root: pathlib.Path = ROOT) -> list[str]:
    """What round v2.3's calibration changes against the v2.2 record, field by field — what the owner reviews, rather
    than a new record of some 900 lines: `+ name` a checker the v2.2 record lacks, `- name` one this result lacks."""
    try:
        old = json.loads((root / V22_REL).read_text(encoding="utf-8"))
        was = {c["checker"]: c for c in old["checkers"]}
    except (OSError, ValueError, KeyError, TypeError):
        return [f"the v2.2 record {V22_REL} is unreadable"]
    now = {c["checker"]: c for c in result["checkers"]}
    out = [f"{k}: {old.get(k)!r} -> {result.get(k)!r}" for k in sorted(set(old) | set(result))
           if k != "checkers" and old.get(k) != result.get(k)]
    out += [f"- {n}" for n in was if n not in now] + [f"+ {n}" for n in now if n not in was]
    return out + [f"{n}.{k}: {was[n].get(k)!r} -> {c.get(k)!r}" for n, c in now.items() if n in was
                  for k in sorted(set(was[n]) | set(c)) if was[n].get(k) != c.get(k)]


def problems(result: dict, root: pathlib.Path = ROOT, *, record_too: bool = True) -> list[str]:
    out = (history_problems(root) + cc().problems_of(result) + dropped(result, root) + contract_problems(result, root)
           + v23_scope_problems(root))
    if result["calibrated_count"] != len(cc().REGISTRY):
        out.append(f"calibrated {result['calibrated_count']} of {len(cc().REGISTRY)} registered checkers")
    return out + (record_problems(result, root) if record_too else [])


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    from tests.v23 import test_v23_rounds as R
    closed = R.round_v23_missing()
    if closed and "--write" in argv:
        print("FAIL  refused: round v2.3 is not open: " + "; ".join(closed))
        return 1
    result = run()
    bad = ([f"round v2.3 is not open: {'; '.join(closed)}"] if closed else []) \
        + problems(result, ROOT, record_too="--write" not in argv)
    changed = delta(result, ROOT)
    print(f"round v2.3 Q0 against the v2.2 record {V22_REL}: {len(changed)} change(s)")
    for d in changed:
        print(f"DELTA {d}")
    for p in bad:
        print(f"FAIL  {p}")
    print(f"round v2.3 Q0: calibrated {result['calibrated_count']}/{result['checker_count']}")
    if "--write" in argv and not bad:
        (ROOT / V23_REL).parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(ROOT / V23_REL, "x", encoding="utf-8", newline="\n") as f:    # written once, never rewritten
                f.write(render(result))
        except FileExistsError:
            print(f"FAIL  refused: {V23_REL} exists")
            return 1
        print(f"wrote {V23_REL}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
