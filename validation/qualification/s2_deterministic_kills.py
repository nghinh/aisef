"""V2.0-S2: every mutant of the two OBS-S2-12 targets is killed by tests/v2/test_s2_kills_deterministic.py ALONE, with the
same verdict and the same failing tests under every string-hash seed (owner, 2026-10-05: 'A release qualification must
not knowingly depend on random ordering/chance').

    python -P validation/qualification/s2_deterministic_kills.py --write   # -> closure-evidence/v2/release/S2-DETERMINISTIC-KILLS.json
    python -P validation/qualification/s2_deterministic_kills.py --check   # re-derive; the committed record must be it

Each mutant runs in the tree validation/v2/mutation.py builds (its COPY), after the unmutated baseline passes under the
same seed, under the real-client guard (S2-REAL-CLIENT-RUN/R1: PATH without an `opencode` executable, the client's data,
state and cache directories in a scratch directory). The record holds no timing, so it is byte-reproducible."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from validation.v2 import mutation as m  # noqa: E402

KILLS = "tests/v2/test_s2_kills_deterministic.py"
TARGETS = ("aisef2/app/preflight.py::fingerprint_fields", "aisef2/app/client.py::Budget.spend")
SEEDS = ("0", "1", "2", "4242", "2147483647", "random")
OUT_REL = "closure-evidence/v2/release/S2-DETERMINISTIC-KILLS.json"
TIMEOUT_S = 120


def _sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def guarded_env(scratch: pathlib.Path, seed: str) -> dict:
    path = os.pathsep.join(d for d in os.environ.get("PATH", "").split(os.pathsep)
                           if d and not (pathlib.Path(d) / "opencode").exists() and not (pathlib.Path(d) / "opencode.exe").exists())
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env.update(PATH=path, PYTHONHASHSEED=seed, XDG_DATA_HOME=str(scratch / "data"), XDG_STATE_HOME=str(scratch / "state"),
               XDG_CACHE_HOME=str(scratch / "cache"))
    return env


def run(tree: pathlib.Path, env: dict) -> dict:
    """The kill file's verdict on the tree as it is: survived / assertion / error / timeout, and the tests that failed."""
    module = KILLS.removesuffix(".py").replace("/", ".")
    try:
        r = subprocess.run([sys.executable, "-m", "unittest", module], cwd=tree, env=env, capture_output=True, text=True,
                           encoding="utf-8", timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return {"kind": "timeout", "failed": []}
    failed = sorted(set(re.findall(r"^(?:FAIL|ERROR): (\S+ \(\S+\))", r.stderr, re.M)))
    if r.returncode == 0:
        return {"kind": "survived", "failed": failed}
    errored = re.search(r"^ERROR: ", r.stderr, re.M) or not failed   # an error, or a run that names no failing test
    return {"kind": "error" if errored else "assertion", "failed": failed}


def derive() -> dict:
    with tempfile.TemporaryDirectory() as t:
        tree, scratch = pathlib.Path(t) / "tree", pathlib.Path(t) / "xdg"
        for part in m.COPY:
            src = ROOT / part
            if src.is_dir():
                shutil.copytree(src, tree / part, ignore=shutil.ignore_patterns("__pycache__"))
            elif src.exists():
                (tree / part).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(src, tree / part)
        for d in ("data", "state", "cache"):
            (scratch / d).mkdir(parents=True)
        baseline = {s: run(tree, guarded_env(scratch, s)) for s in SEEDS}
        targets = []
        for target in TARGETS:
            rel, func = target.split("::")
            f = tree / rel
            orig = f.read_text(encoding="utf-8")
            results = []
            try:
                for desc, src in m.mutants(orig, func, m._enum_members(orig, tree)):
                    f.write_text(src, encoding="utf-8")
                    verdicts = {s: run(tree, guarded_env(scratch, s)) for s in SEEDS}
                    kinds = {v["kind"] for v in verdicts.values()}
                    results.append({"mutant": desc, "verdict": verdicts["0"],
                                    "same_under_every_seed": all(v == verdicts["0"] for v in verdicts.values()),
                                    "killed_under_every_seed": not kinds & {"survived", "timeout"}})
            finally:
                f.write_text(orig, encoding="utf-8")
            targets.append({"target": target, "source_sha256": hashlib.sha256(orig.encode()).hexdigest(),
                            "kill_set": m.S2_TARGETS[target], "mutants": len(results),
                            "killed_by_this_file_alone": sum(r["killed_under_every_seed"] for r in results),
                            "results": results})
    ok = (all(b["kind"] == "survived" for b in baseline.values())
          and all(r["killed_under_every_seed"] and r["same_under_every_seed"] for t in targets for r in t["results"]))
    return {"record": "AISEF V2.0 — S2 deterministic kills for OBS-S2-12's targets (owner, 2026-10-05)",
            "tool": "validation/qualification/s2_deterministic_kills.py", "kill_file": {"path": KILLS, "sha256": _sha(ROOT / KILLS)},
            "seeds": list(SEEDS), "guard": "PATH without an opencode executable; XDG_DATA_HOME/XDG_STATE_HOME/XDG_CACHE_HOME in a scratch directory",
            "baseline_passes_under_every_seed": all(b["kind"] == "survived" for b in baseline.values()),
            "targets": targets, "verdict": "PASS" if ok else "FAIL"}


def render(doc: dict) -> str:
    return json.dumps(doc, indent=1, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    doc, out = derive(), ROOT / OUT_REL
    if a.write:
        out.write_text(render(doc), encoding="utf-8")
    elif not out.exists() or out.read_text(encoding="utf-8") != render(doc):
        print(f"FAIL  {OUT_REL} is not what the tool derives now")
        return 1
    for t in doc["targets"]:
        print(f"{t['target']}: {t['killed_by_this_file_alone']}/{t['mutants']} killed by {KILLS} alone under seeds {', '.join(SEEDS)}")
    print(f"s2 deterministic kills: {doc['verdict']}")
    return 0 if doc["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
