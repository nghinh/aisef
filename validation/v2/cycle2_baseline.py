"""WP-2.0.1 — the Cycle-2 baseline guard: Cycle 1 is immutable, Cycle 2 has separate identities.

Owner authorization "AISEF V2 — CYCLE-2 OWNER DECISIONS / WP-2.0.1 AUTHORIZATION" (2026-09-28). The guard writes and
checks `closure-evidence/v2/cycle2/CYCLE2-FREEZE-MANIFEST.json`:

* **inherited Cycle-1 identities** — the semantic candidate, its `aisef2` tree, the closing commit, the Cycle-1 probe
  id and digest, the RFC digests and lineage, the F1–F11 statuses and the attempt counts at freeze;
* **the immutable set** — every seal, acceptance and run history of Cycle 1, the P6 migration table, the P2
  calibration record, the V1 evidence baseline, the RFC approval/amendment/exception records, the Q0–Q3, Q4, Q5,
  P10 and P7-FINDING-001 evidence trees, and the two source files the Cycle-1 probe digest is computed from
  (`aisef2/probe/protocol.py`, `aisef2/probe/python_callable.py`) — each with its sha256 (CRLF normalised to LF, so
  a Windows autocrlf checkout compares equal) and its git blob id; a tree also records its tracked file set;
* **the immutable-parent / candidate rules** (R1–R7 below), as text and as the checks that enforce them;
* **the owner-decision record** (`OWNER-DECISIONS.json`, DECISION-1..6) bound by sha256;
* **the Cycle-2 manifest**, structurally validated, whose `architecture_baseline` must equal the inherited identities.

`--check` recomputes every immutable hash, compares each tree's tracked set with git (an addition or a deletion in a
Cycle-1 evidence tree fails), verifies the live Cycle-1 probe digest still equals the frozen one, verifies the
decision record and the manifest, and fails on any drift of the record's own content. A detected change is never
repaired here: the Cycle-1 file is restored from history, and nothing of Cycle 2 may cite the changed version.

    python -P validation/v2/cycle2_baseline.py --write    # refuses on any problem
    python -P validation/v2/cycle2_baseline.py --check
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
OUT_REL = "closure-evidence/v2/cycle2/CYCLE2-FREEZE-MANIFEST.json"
DECISIONS_REL = "closure-evidence/v2/cycle2/OWNER-DECISIONS.json"
MANIFEST_REL = "docs/implementation/v2/cycle2/cycle2-manifest.json"
RFC_FREEZE_REL = "closure-evidence/v2/AISEF-V2-FREEZE-MANIFEST.json"
F_CONFORMANCE_REL = "closure-evidence/v2/F-CONFORMANCE.json"

PARENT_COMMIT = "7114177834da5a7e4a0fc2c7f8fa9d067e0abaa2"
PARENT_AISEF2_TREE = "4d6081940f5b9dae47439f73f0157161e028d804"
CYCLE1_CLOSING_COMMIT = "503b3a22f872c212d237e70f03aaba7d83f54d67"
CYCLE1_PROBE = {"id": "probe.python_callable",
                "digest": "1961e84d913edc687bdb52f6c6cd0f034e86f2d1dadd9e89fa76757a51dc35bf"}
PROBE_SOURCES = ("aisef2/probe/protocol.py", "aisef2/probe/python_callable.py")
DECISION_IDS = tuple(f"DECISION-{i}" for i in range(1, 7))

IMMUTABLE_FILES = (
    *(f"closure-evidence/v2/P{i}-FINAL-SEAL.json" for i in range(1, 7)),
    *(f"closure-evidence/v2/P{i}-ACCEPTANCE.json" for i in range(7, 11)),
    *(f"closure-evidence/v2/P{i}-RUN-HISTORY.json" for i in range(1, 11)),
    "closure-evidence/v2/P6-MIGRATION-TABLE.json",
    "closure-evidence/v2/P2-CALIBRATION.json",
    "closure-evidence/v2/V1-EVIDENCE-BASELINE.json",
    RFC_FREEZE_REL,
)
IMMUTABLE_GLOBS = ("closure-evidence/v2/AISEF-V2-RFC-*.json", "closure-evidence/v2/ARCHITECTURE-EXCEPTION-*.json")
IMMUTABLE_TREES = ("closure-evidence/v2/Q0-Q3", "closure-evidence/v2/Q4", "closure-evidence/v2/Q5",
                   "closure-evidence/v2/P10", "closure-evidence/v2/P7-FINDING-001")

RULES = (
    "R1 parent: the Cycle-2 line starts at the Cycle-1 semantic candidate 7114177 (aisef2 tree 4d6081); a Cycle-2 "
    "candidate is a commit whose aisef2 tree differs from it and that passes this guard.",
    "R2 probe: the Cycle-1 probe sources (aisef2/probe/protocol.py, aisef2/probe/python_callable.py) stay "
    "byte-identical to the parent's blobs, so probe.python_callable keeps digest 1961e84d… and every Cycle-1 "
    "ProductProofSpec / semantic_hash stays bound to it (DECISION-6).",
    "R3 evidence: every file of the immutable set is byte-identical (CRLF-normalised) and no file is added to or "
    "removed from a Cycle-1 evidence tree; a mutation is restored from history, never accepted.",
    "R4 identities: Cycle-2 code lives in new modules (a second probe identity never edits a Cycle-1 one) and "
    "Cycle-2 evidence under closure-evidence/v2/cycle2/; a Cycle-2 record names its own commit and aisef2 tree and "
    "never reuses a Cycle-1 identity.",
    "R5 seals: the P4/P5/P6 seals and the P7/P8/P9/P10 acceptances are never re-signed, re-generated or "
    "re-interpreted; a Cycle-2 acceptance is a new record.",
    "R6 catalogue: exactly one active probe per subject kind compiles (F4); a superseded identity stays registered "
    "for the evidence bound to it (aisef2/probe/catalog.py).",
    "R7 guard: if a Cycle-2 change would require editing a frozen item (F1–F11), the probe protocol or ProbeResult "
    "shape, the harness/subject split, enforcement or execution-status semantics, owner routing or the compiler "
    "contract: STOP and draft an Architecture Exception; nothing is implemented around it.",
)


def _norm(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n")


def file_identity(path: pathlib.Path) -> dict:
    data = _norm(path.read_bytes())
    return {"sha256": hashlib.sha256(data).hexdigest(),
            "git_blob": hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()}


def _git(root: pathlib.Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, encoding="utf-8", check=True).stdout


def tracked(root: pathlib.Path, tree: str) -> list[str]:
    return sorted(p for p in _git(root, "ls-files", "-z", "--", tree).split("\0") if p)


def _load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --------------------------------------------------------------------------------------- build

def enumerate_files(root: pathlib.Path, files=IMMUTABLE_FILES, globs=IMMUTABLE_GLOBS) -> list[str]:
    out = set(files)
    for g in globs:
        out |= {p.relative_to(root).as_posix() for p in root.glob(g)}
    return sorted(out)


def build(root: pathlib.Path = ROOT, *, files=IMMUTABLE_FILES, globs=IMMUTABLE_GLOBS, trees=IMMUTABLE_TREES,
          manifest_sha: str | None = None) -> dict:
    """The freeze manifest as recomputed from `root`. Missing files are recorded as problems, never invented."""
    rfc = _load(root / RFC_FREEZE_REL) if (root / RFC_FREEZE_REL).is_file() else {}
    fconf = _load(root / F_CONFORMANCE_REL) if (root / F_CONFORMANCE_REL).is_file() else {}
    histories = {}
    for i in range(7, 11):
        p = root / f"closure-evidence/v2/P{i}-RUN-HISTORY.json"
        if p.is_file():
            histories[f"P{i}"] = len(_load(p)["entries"])
    immutable: dict[str, dict] = {}
    for rel in enumerate_files(root, files, globs):
        immutable[rel] = file_identity(root / rel) if (root / rel).is_file() else {"missing": True}
    tree_sets: dict[str, list[str]] = {}
    for tree in trees:
        members = tracked(root, tree)
        tree_sets[tree] = members
        for rel in members:
            immutable[rel] = file_identity(root / rel) if (root / rel).is_file() else {"missing": True}
    sources = {rel: (file_identity(root / rel) if (root / rel).is_file() else {"missing": True}) for rel in PROBE_SOURCES}
    decisions = root / DECISIONS_REL
    manifest = root / MANIFEST_REL
    return {
        "record": "AISEF V2 — CYCLE-2 FREEZE MANIFEST",
        "work_package": "WP-2.0.1",
        "authority": "owner decision 'AISEF V2 — CYCLE-2 OWNER DECISIONS / WP-2.0.1 AUTHORIZATION' (2026-09-28): "
                     "the Cycle-2 architecture study accepted for implementation planning; the Cycle-1 semantic "
                     "baseline immutable",
        "cycle1": {
            "semantic_candidate": PARENT_COMMIT,
            "aisef2_tree": PARENT_AISEF2_TREE,
            "closing_commit": CYCLE1_CLOSING_COMMIT,
            "probe": dict(CYCLE1_PROBE),
            "probe_sources": sources,
            "rfc": {k: rfc.get(k) for k in ("rfc_normative_digest", "freeze_table_digest")}
                   | {"lineage": [r.get("record") for r in rfc.get("approval_lineage", [])]},
            "f_conformance_at_freeze": {i["id"]: i["state"] for i in fconf.get("items", []) if "id" in i},
            "attempt_histories_at_freeze": histories,
            "verified_by": ["validation/v2/freeze_manifest.py (RFC)", "validation/v2/freeze_conformance.py (F1–F11)",
                            "validation/v2/run_history.py (histories, seals)", "validation/v2/v1_evidence_guard.py (V1)"],
        },
        "immutable": {
            "hash": "sha256 over the file bytes with CRLF normalised to LF; git_blob = sha1 of the git blob header "
                    "and the same bytes",
            "files": immutable,
            "trees": tree_sets,
        },
        "rules": list(RULES),
        "owner_decisions": {
            "path": DECISIONS_REL,
            "sha256": _sha(decisions) if decisions.is_file() else None,
            "ids": list(DECISION_IDS),
        },
        "cycle2_manifest": {
            "path": MANIFEST_REL,
            "sha256_at_freeze": manifest_sha if manifest_sha is not None else (_sha(manifest) if manifest.is_file() else None),
            "architecture_baseline_must_equal": ["cycle1_semantic_candidate", "cycle1_aisef2_tree",
                                                 "cycle1_closing_commit", "cycle1_probe"],
        },
    }


def render(record: dict) -> str:
    return json.dumps(record, indent=1, ensure_ascii=False) + "\n"


# --------------------------------------------------------------------------------------- problems

def manifest_problems(manifest: dict) -> list[str]:
    """Structural validity of the Cycle-2 manifest and its agreement with the inherited identities."""
    out = []
    phases = {p.get("id") for p in manifest.get("phases", [])}
    ids = [w.get("id") for w in manifest.get("work_packages", [])]
    if len(set(ids)) != len(ids):
        out.append("cycle2 manifest: duplicate work-package ids")
    for w in manifest.get("work_packages", []):
        if w.get("phase") not in phases:
            out.append(f"cycle2 manifest: {w.get('id')} names an unknown phase {w.get('phase')!r}")
        for d in w.get("dependencies", []):
            if d not in ids:
                out.append(f"cycle2 manifest: {w.get('id')} depends on an unknown package {d!r}")
    barrier = {p.get("id"): p.get("barrier") for p in manifest.get("phases", [])}
    for pid in phases:
        seen, cur = set(), pid
        while cur is not None:
            if cur in seen:
                out.append(f"cycle2 manifest: phase barriers cycle through {pid}")
                break
            seen.add(cur)
            cur = barrier.get(cur)
    ab = manifest.get("architecture_baseline", {})
    for key, want in (("cycle1_semantic_candidate", PARENT_COMMIT), ("cycle1_aisef2_tree", PARENT_AISEF2_TREE),
                      ("cycle1_closing_commit", CYCLE1_CLOSING_COMMIT), ("cycle1_probe", CYCLE1_PROBE)):
        if ab.get(key) != want:
            out.append(f"cycle2 manifest: architecture_baseline.{key} != the inherited identity")
    return out


def decisions_problems(record: dict) -> list[str]:
    out = []
    got = {d.get("id"): d for d in record.get("decisions", [])}
    for did in DECISION_IDS:
        if did not in got:
            out.append(f"owner decisions: {did} missing")
        elif not got[did].get("verdict") or not got[did].get("owner_text"):
            out.append(f"owner decisions: {did} has no verdict or no owner text")
    return out


def check(root: pathlib.Path = ROOT, *, files=IMMUTABLE_FILES, globs=IMMUTABLE_GLOBS, trees=IMMUTABLE_TREES,
          live_probe_digest: str | None = None) -> list[str]:
    committed = root / OUT_REL
    if not committed.is_file():
        return [f"{OUT_REL} is missing"]
    rec = _load(committed)
    out = []
    # 1. every immutable file, as recorded
    for rel, ident in rec.get("immutable", {}).get("files", {}).items():
        p = root / rel
        if ident.get("missing"):
            out.append(f"immutable file recorded as missing: {rel}")
        elif not p.is_file():
            out.append(f"immutable file deleted: {rel}")
        elif file_identity(p) != ident:
            out.append(f"immutable file changed: {rel}")
    # 2. the trees' tracked sets
    for tree, members in rec.get("immutable", {}).get("trees", {}).items():
        try:
            now = tracked(root, tree)
        except (OSError, subprocess.CalledProcessError) as e:
            out.append(f"cannot list {tree}: {type(e).__name__}")
            continue
        for rel in sorted(set(now) - set(members)):
            out.append(f"file added to a Cycle-1 evidence tree: {rel}")
        for rel in sorted(set(members) - set(now)):
            out.append(f"file removed from a Cycle-1 evidence tree: {rel}")
    # 3. the record equals a fresh build (its manifest sha is a snapshot, carried over)
    fresh = build(root, files=files, globs=globs, trees=trees,
                  manifest_sha=rec.get("cycle2_manifest", {}).get("sha256_at_freeze"))
    if fresh != rec:
        out.append(f"{OUT_REL} differs from a fresh build (an identity, a rule, a decision record or a member set "
                   "changed)")
    # 4. the live Cycle-1 probe digest
    if live_probe_digest is None:
        from aisef2.probe import python_callable as pc
        live_probe_digest = pc.DIGEST
    if live_probe_digest != CYCLE1_PROBE["digest"]:
        out.append(f"the Cycle-1 probe digest changed: live {live_probe_digest[:12]} != frozen "
                   f"{CYCLE1_PROBE['digest'][:12]} (R2)")
    # 5. decisions and manifest
    decisions = root / DECISIONS_REL
    if not decisions.is_file():
        out.append(f"{DECISIONS_REL} is missing")
    else:
        out += decisions_problems(_load(decisions))
    manifest = root / MANIFEST_REL
    if not manifest.is_file():
        out.append(f"{MANIFEST_REL} is missing")
    else:
        out += manifest_problems(_load(manifest))
    return out


def write_problems(record: dict) -> list[str]:
    out = [f"missing at write: {rel}" for rel, ident in record["immutable"]["files"].items() if ident.get("missing")]
    out += [f"missing at write: {rel}" for rel, ident in record["cycle1"]["probe_sources"].items() if ident.get("missing")]
    if record["owner_decisions"]["sha256"] is None:
        out.append(f"missing at write: {DECISIONS_REL}")
    if record["cycle2_manifest"]["sha256_at_freeze"] is None:
        out.append(f"missing at write: {MANIFEST_REL}")
    if len(record["cycle1"]["f_conformance_at_freeze"]) != 11:
        out.append("F-CONFORMANCE.json does not list F1–F11")
    return out


def verify_parent(root: pathlib.Path = ROOT) -> list[str]:
    """At write time only: the parent commit's tree and blobs, read from history, equal the constants and the files."""
    out = []
    tree = _git(root, "rev-parse", f"{PARENT_COMMIT}:aisef2").strip()
    if tree != PARENT_AISEF2_TREE:
        out.append(f"{PARENT_COMMIT[:7]}:aisef2 is {tree[:12]}, not {PARENT_AISEF2_TREE[:12]}")
    for rel in PROBE_SOURCES:
        blob = _git(root, "rev-parse", f"{PARENT_COMMIT}:{rel}").strip()
        if blob != file_identity(root / rel)["git_blob"]:
            out.append(f"{rel} differs from the parent's blob {blob[:12]} (R2)")
    return out


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--write" in argv:
        record = build()
        problems = write_problems(record) + verify_parent() + decisions_problems(_load(ROOT / DECISIONS_REL)) \
            + manifest_problems(_load(ROOT / MANIFEST_REL))
        for p in problems:
            print(f"FAIL  {p}")
        if problems:
            return 1
        (ROOT / OUT_REL).parent.mkdir(parents=True, exist_ok=True)
        (ROOT / OUT_REL).write_text(render(record), encoding="utf-8")
        print(f"wrote {OUT_REL}: {len(record['immutable']['files'])} immutable files, "
              f"{len(record['immutable']['trees'])} trees, probe {CYCLE1_PROBE['digest'][:12]}")
        return 0
    problems = check()
    for p in problems:
        print(f"FAIL  {p}")
    print(f"cycle-2 baseline guard: {'FAIL' if problems else 'PASS'}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
