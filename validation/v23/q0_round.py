"""v2.3 Q0-1: the distinct round-v2.3 Q0 qualification round (docs/v2.3/amendments/Q0-1-V23-ROUND.md).

History, never rewritten: the v2.2 Q0 record V22_REL (sha256 V22_SHA256). Its GATED test
(tests/v2/p0/test_checker_calibration.py::CheckerCalibration) is replayed at v2.2.0 by validation/v23/replay_v22.py,
where the record must regenerate byte-identically (replay_v22.Q0_REPLAYED).

Round v2.3: its own record, V23_REL — the SAME calibration (validation/v2/checker_calibration.run(): every checker passes
the clean tree, fails its committed known-bad fixture for the named reason, and an always-PASS mutant of it is
rejected) run on the HEAD tree inside `version_forward.in_round("v2.3")`, wrapped with the round's identity. The gated
counterpart tests/v23/test_v23_q0_round.py::Q0RoundV23 requires, with ledger seq 13 committed by the owner, that this
record exists and equals what the HEAD tree derives, that every checker is calibrated, that no v2.2 checker was
dropped, and that the v2.2 record is still its v2.2.0 bytes. Nothing here relaxes a checker: a W1-W6 edit that moves a
clean result leaves the round red until the checker is calibrated again (the amendment's delta table).

    python3 -P validation/v23/q0_round.py --check   # this tree vs V23_REL and the history; exit 1 on any problem
    python3 -P validation/v23/q0_round.py --write   # write V23_REL once: refused unless round v2.3 is open, every
                                                     # checker is calibrated and the file is absent (a re-seal is
                                                     # `git rm` + --write in one commit)
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

V22_REL = "closure-evidence/v2/v2.1/Q0-CHECKER-CALIBRATION.json"
#: the LF sha256 of V22_REL at v2.2.0 (da3ea33f) — and at every commit since: history, never rewritten
V22_SHA256 = "714625b14e8972f166b37a467b5f83761d1f2672d076e5f5f0f342e2eb91332c"
#: round v2.3's own record: a new file outside closure-evidence/ (Amendment A2 placement; the amendment argues why)
V23_REL = "docs/v2.3/evidence/q0-round/Q0-CHECKER-CALIBRATION-V23.json"
ROUND = "v2.3"
_CC = "aisef_v2_checker_calibration"      # the alias tests/v2/p0/test_checker_calibration.py loads it under


def cc():
    """validation/v2/checker_calibration.py, the one module both rounds calibrate with (shared with the v2.2 test)."""
    if _CC not in sys.modules:
        spec = importlib.util.spec_from_file_location(_CC, ROOT / "validation" / "v2" / "checker_calibration.py")
        sys.modules[_CC] = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sys.modules[_CC])
    return sys.modules[_CC]


def _lf_sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def run() -> dict:
    """checker_calibration.run() on this tree in round v2.3. Without L1-F5's `in_round` the round's own selection does
    not exist yet; the calibration then runs on the v2.2 rule — stricter for the round-aware cleans (currency_dag,
    mutation), so it can be red, never a false green — and the counterpart fails on the closed round anyway."""
    from validation.v2 import version_forward as vf
    with (vf.in_round(ROUND) if hasattr(vf, "in_round") else contextlib.nullcontext()):
        return cc().run()


def record(result: dict) -> dict:
    return {"record": "AISEF V2.3 — Q0 CHECKER CALIBRATION (round v2.3)", "round": ROUND,
            "history": {"path": V22_REL, "sha256": V22_SHA256, "replayed_at": "da3ea33f3b695aaca73e87a704145a0193aced23",
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


def problems(result: dict, root: pathlib.Path = ROOT, *, record_too: bool = True) -> list[str]:
    out = history_problems(root) + cc().problems_of(result) + dropped(result, root)
    if result["calibrated_count"] != len(cc().REGISTRY):
        out.append(f"calibrated {result['calibrated_count']} of {len(cc().REGISTRY)} registered checkers")
    return out + (record_problems(result, root) if record_too else [])


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--write" in argv:
        from tests.v23.test_v23_rounds import round_v23_missing
        closed = round_v23_missing()
        if closed:
            print("FAIL  refused: round v2.3 is not open: " + "; ".join(closed))
            return 1
    result = run()
    bad = problems(result, ROOT, record_too="--write" not in argv)
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
