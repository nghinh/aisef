"""Candidate evidence for the 2.1 requalification (B-03), derived at THIS tree and written ONLY to a new versioned
directory — never over a sealed record, never read by anything that decides a release.

    python3 -P validation/v21/candidate_evidence.py OUT [--only REL ...]

OUT is a new directory under closure-evidence/v2.1-candidate/ (or outside the repository). For each sealed record a
red record-binding test compares with the tree (docs/v2.1/RED-SUITE.md), the record's own generator derives what it
would hold now; the copy goes to OUT/<the record's path>, and OUT/CANDIDATE-MANIFEST.json names the commit, the
environment, the command, each copy's sha256, the sealed record's sha256 and the JSON paths where they differ.

What this does not do: replace a sealed record (that is the owner's decision, and some records are write-once by
rule); re-run mutation testing (320 stale targets, ~32 h of one worker: a new phase the owner must design); rewrite
the historical conformance record; change an oracle (the Q5 corpus). Those are listed in the manifest as NOT
GENERATED, with why. Every consumer — the tests, q0/q2, the release gate — reads the sealed fixed paths only."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import pathlib
import platform
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
CANDIDATES = ROOT / "closure-evidence" / "v2.1-candidate"
MANIFEST = "CANDIDATE-MANIFEST.json"


def _load(rel: str):
    spec = importlib.util.spec_from_file_location("cand_" + pathlib.Path(rel).stem, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _json(doc: dict) -> str:
    return json.dumps(doc, indent=1, ensure_ascii=False) + "\n"


def _p2_static_admission() -> str:
    p2 = _load("validation/v2/p2_evidence.py")
    return p2.render(p2.static_admission())


def _p5_proposal() -> str:
    return _json(_load("validation/qualification/p10_contracts.py").record())


def _p5_acceptance() -> str:
    return _json(_load("validation/qualification/p5_acceptance.py").record())


def _plan_correction() -> str:
    return _json(_load("validation/qualification/c2_plan_correction.py").record())


def _release_inventory() -> str:
    opa = _load("validation/v2/old_path_audit.py")
    return opa.render(opa.inventory())


def _checker_calibration() -> str:
    cc = _load("validation/v2/checker_calibration.py")
    return cc.render(cc.run())


def _k_nowork(out: pathlib.Path, rel: str) -> str:
    """K-NOWORK-001's own writer, its output path pointed into OUT (it re-runs its cases under both kernels, ~13 min)."""
    kn = _load("validation/qualification/c2_k_nowork_001.py")
    target = out / rel
    kn.OUT_REL = os.path.relpath(target, ROOT)
    if not (ROOT / kn.OUT_REL).resolve().is_relative_to(out.resolve()):
        raise SystemExit("refused: the writer's path is not inside the candidate directory")
    target.parent.mkdir(parents=True, exist_ok=True)
    kn.write()
    return target.read_text(encoding="utf-8")


#: sealed path -> (how to derive it now, what a replacement of the sealed record needs beyond the copy)
GENERATED = {
    "closure-evidence/v2/P2-STATIC-ADMISSION.json": (_p2_static_admission, "mechanical; a sealed P2 record: the owner's decision"),
    "closure-evidence/v2/cycle2/P5-PLAN-V2.2-PROPOSAL.json": (
        _p5_proposal, "immutable by rule (p5_acceptance: its blob is the accepted candidate's): a ruling on the admission "
                      "engine digest, or a new v2.1 proposal"),
    "closure-evidence/v2/cycle2/C2-P5-ACCEPTANCE.json": (_p5_acceptance, "write-once (--write refuses an existing file)"),
    "closure-evidence/v2/cycle2/PLAN-V2.2-CORRECTION-1.json": (
        _plan_correction, "mechanical, but bound by K-NOWORK-001 and pinned by the delivery-experiment preregistrations"),
    "closure-evidence/v2/release/AUTHORITY-INVENTORY.json": (
        _release_inventory, "two new PRODUCT_TRUTH authorities outside run_story to accept (bundle_cli.migrate, "
                            "review_verify.verify); INVENTORY_SHA256 and test_no_dual_authority's release delta edited by hand"),
    "closure-evidence/v2/Q0-CHECKER-CALIBRATION.json": (
        _checker_calibration, "only after mutation, P2 and the inventory are current; its known-bad observation changes"),
    "closure-evidence/v2/cycle2/K-NOWORK-001-REHEARSAL.json": (None, "after the plan correction (it is BOUND)"),
}
NOT_GENERATED = {
    "closure-evidence/v2/release/S2-MUTATION.json (+ P2/P6/cycle2 P1 mutation records)":
        "320 targets stale (whole-module digests), 7482 mutants, ~32 h of one worker; mutation.py writes the fixed records "
        "and its reuse proof needs byte-identical targets: a new phase in RECORDS/SUPERSEDED — the owner's design",
    "closure-evidence/v2/cycle2/C2-ORCHESTRATION-CONFORMANCE-REPAIR.json":
        "historical; release_differences tolerates only V2.0's changed files: a ruling naming the v2.1 changes",
    "validation/qualification/q5.py corpus item post-merge-regression (release/Q5-RC2/CORPUS.json frozen)":
        "an oracle: V21-38 proves PRESERVE at the candidate, so the item's expected outcome and model calls change — the "
        "owner's decision; the frozen 2.0 corpus is never edited",
}


def differing_paths(a, b, at: str = "", limit: int = 60) -> list[str]:
    """The JSON paths where `a` and `b` differ (at most `limit`)."""
    if type(a) is not type(b) or not isinstance(a, (dict, list)):
        return [] if a == b else [at or "(root)"]
    out: list[str] = []
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append(f"{at}.{k}" if at else str(k))
            else:
                out += differing_paths(a[k], b[k], f"{at}.{k}" if at else str(k), limit)
            if len(out) >= limit:
                break
    else:
        if len(a) != len(b):
            return [f"{at}[len {len(a)} vs {len(b)}]"]
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            out += differing_paths(x, y, f"{at}[{i}]", limit)
            if len(out) >= limit:
                break
    return out[:limit]


def _sha(p: pathlib.Path) -> str | None:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None


def generate(out: pathlib.Path, only: list[str] | None = None) -> dict:
    out = out.absolute()
    if out.exists():
        raise SystemExit(f"refused: {out} exists — a candidate set is never rewritten")
    inside = out.resolve().is_relative_to(ROOT.resolve())
    if inside and not out.resolve().is_relative_to(CANDIDATES.resolve()):
        raise SystemExit(f"refused: inside the repository a candidate set lives under {CANDIDATES.relative_to(ROOT)}/ only")
    wanted = only or list(GENERATED)
    unknown = [r for r in wanted if r not in GENERATED]
    if unknown:
        raise SystemExit(f"refused: not a record this tool derives: {unknown}")
    sealed_before = {r: _sha(ROOT / r) for r in GENERATED}
    out.mkdir(parents=True)
    rows = {}
    for rel in wanted:
        build, needs = GENERATED[rel]
        started = time.monotonic()
        try:
            text = _k_nowork(out, rel) if build is None else build()
        except SystemExit as e:
            rows[rel] = {"generated": False, "why": f"the generator refused: {e}"[:600], "needs": needs}
            continue
        except Exception as e:  # noqa: BLE001 — a generator that fails is reported, never hidden
            rows[rel] = {"generated": False, "why": f"{type(e).__name__}: {e}"[:600], "needs": needs}
            continue
        target = out / rel
        if build is not None:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("x", encoding="utf-8", newline="\n") as f:
                f.write(text)
        sealed = ROOT / rel
        try:
            paths = differing_paths(json.loads(sealed.read_text(encoding="utf-8")), json.loads(text))
        except (OSError, ValueError) as e:
            paths = [f"(not comparable: {type(e).__name__})"]
        rows[rel] = {"generated": True, "sha256": _sha(target), "sealed_sha256": _sha(sealed),
                     "identical_to_sealed": _sha(target) == _sha(sealed), "differing_paths": paths,
                     "seconds": round(time.monotonic() - started, 1), "needs": needs}
    changed = [r for r in GENERATED if _sha(ROOT / r) != sealed_before[r]]
    if changed:     # never expected: the copy goes to OUT only — said loudly if it did not
        raise SystemExit(f"a SEALED record changed while deriving candidates: {changed} — restore it from git")
    commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, encoding="utf-8").stdout.strip()
    dirty = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=no"], capture_output=True,
                           encoding="utf-8").stdout.strip()
    manifest = {"format": "aisef-v2.1-candidate-evidence/1", "commit": commit, "tree_dirty": bool(dirty),
                "environment": {"system": platform.platform(), "python": platform.python_version(),
                                "executable": sys.executable},
                "command": " ".join(["python3", "-P", "validation/v21/candidate_evidence.py", *sys.argv[1:]]),
                "created": time.time(), "status": "CANDIDATE — not a sealed record, not approved, read by no release check",
                "artifacts": rows, "not_generated": NOT_GENERATED}
    (out / MANIFEST).write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("out", type=pathlib.Path)
    p.add_argument("--only", nargs="+", metavar="REL")
    a = p.parse_args(argv)
    m = generate(a.out, a.only)
    for rel, row in m["artifacts"].items():
        state = ("identical" if row["identical_to_sealed"] else f"differs at {len(row['differing_paths'])} path(s)") \
            if row["generated"] else "NOT generated: " + row["why"][:120]
        print(f"{rel}: {state}")
    return 0 if all(r["generated"] for r in m["artifacts"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
