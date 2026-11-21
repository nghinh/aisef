"""Released-V2 evidence guard (CODE-AUDIT #52 (b); COMPATIBILITY-MATRIX CT-6, CR-13).

The V1 guard (validation/v2/v1_evidence_guard.py) excludes closure-evidence/v2/, and that includes the released
v2.0/v2.1/v2.2 records. This guard checks them the V1 way, with git objects (a Windows autocrlf checkout compares
correctly):

* **protected set:** every git-tracked file under closure-evidence/v2/ at tag v2.2.0 (`RELEASED`), and every one at the
  v2.3 branch base (`BRANCH_BASE`, CT-6). Additions are allowed: a new path is not a released record (a working-tree
  addition is what CI's closure-evidence clean step after the suite catches, #52 (a));
* (1) the baseline agrees with tag v2.2.0 (count + listing digest), so a baseline edit fails;
  (2) HEAD keeps every protected blob: a committed edit or deletion fails;
  (3) the working tree has no change to a protected file.

Grade: DETECTIVE (no in-process layer for v2/). A detected change fails closed; restoring the file is maintenance.

CIGOV-R1 OPEN (docs/v2.3/amendments/CIGOV-R1.md): the release-decision ledger closure-evidence/v2/cycle2/
RELEASE-DECISIONS.json is a protected blob here, while CT-5 / CR-14 let it take entries seq 13+. So the planned owner
appends (ROUND-AUTH seq 13, the v2.3.0 PRODUCTION_PUBLISH entry) FAIL this guard. #52 (b) / CT-6 conflict with CT-5
until the owner or integrator decides; this guard has no exception for that path, and must not get one.

    python -P validation/v23/released_evidence_guard.py --check           # exit 1 on any violation
    python -P validation/v23/released_evidence_guard.py --baseline OUT    # write the baseline (never overwrites)
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCOPE = "closure-evidence/v2"
RELEASED = "da3ea33f3b695aaca73e87a704145a0193aced23"      # tag v2.2.0, the last released record set
BRANCH_BASE = "399b775f420870f0d085022ad0a3f561f73839ab"   # origin/master the v2.3 branch is based on (CT-6)
BASELINE_REL = "docs/v2.3/evidence/released-evidence/V2.2.0-RELEASED-EVIDENCE-BASELINE.json"
RULE = "sha256 over sorted lines '<path>\\t<blob>\\n'"


def _git(root: pathlib.Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, encoding="utf-8", check=True).stdout


def entries(rev: str, root: pathlib.Path = ROOT) -> dict[str, str]:
    """path -> blob id of every tracked file under SCOPE at `rev`."""
    out = {}
    for rec in _git(root, "ls-tree", "-r", "-z", "--end-of-options", rev, "--", SCOPE).split("\0"):
        if rec:
            meta, path = rec.split("\t", 1)
            out[path] = meta.split()[2]
    return out


def digest(listing: dict[str, str]) -> str:
    return hashlib.sha256("".join(f"{p}\t{b}\n" for p, b in sorted(listing.items())).encode()).hexdigest()


def build_baseline(root: pathlib.Path = ROOT, source: str = RELEASED) -> dict:
    at = entries(source, root)
    return {"baseline": "AISEF V2 RELEASED-EVIDENCE BASELINE", "item": "CODE-AUDIT #52 (b); COMPATIBILITY-MATRIX CT-6",
            "scope": f"every git-tracked file under {SCOPE}/ at the source revision; additions are not released records",
            "source_revision": _git(root, "rev-parse", "--verify", "--end-of-options", source + "^{commit}").strip(),
            "source_role": "tag v2.2.0", "file_count": len(at), "files_digest_sha256": digest(at),
            "files_digest_rule": RULE, "comparison_key": "git blob id (platform-independent)",
            "checked_by": "validation/v23/released_evidence_guard.py --check (tests.yml unit job, after the suite)"}


def committed_changes(source: str, root: pathlib.Path = ROOT, at_source: dict[str, str] | None = None) -> list[str]:
    """Every SCOPE blob at `source` edited or deleted at HEAD (additions allowed)."""
    at_source = entries(source, root) if at_source is None else at_source
    at_head = entries("HEAD", root)
    return [f"committed {'deletion' if p not in at_head else 'mutation'} of released evidence ({source[:12]}): {p}"
            for p, b in sorted(at_source.items()) if at_head.get(p) != b]


def working_tree_changes(protected: set[str], root: pathlib.Path = ROOT) -> list[str]:
    recs = _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=no", "--", SCOPE).split("\0")
    out, i = [], 0
    while i < len(recs):
        rec, i = recs[i], i + 1
        if not rec:
            continue
        paths = [rec[3:]]
        if rec[0] in "RC":          # a rename or copy: the next record is its source path
            paths.append(recs[i])
            i += 1
        out += [f"working-tree change to released evidence: {rec[:2]} {p}" for p in paths if p in protected]
    return out


def check(root: pathlib.Path = ROOT, baseline_rel: str = BASELINE_REL, source: str = RELEASED,
          base: str | None = BRANCH_BASE) -> list[str]:
    found: list[str] = []
    try:
        at_source = entries(source, root)
    except subprocess.CalledProcessError:
        return [f"released revision {source[:12]} is not available (shallow clone?): cannot verify (fail closed)"]
    try:
        b = json.loads((root / baseline_rel).read_text(encoding="utf-8"))
        if (b["source_revision"], b["file_count"], b["files_digest_sha256"]) != (source, len(at_source), digest(at_source)):
            found.append(f"{baseline_rel} does not agree with {source[:12]} (the baseline itself was altered)")
    except (OSError, ValueError, KeyError, TypeError) as e:
        found.append(f"{baseline_rel} is missing or unreadable: {e}")
    found += committed_changes(source, root, at_source)
    protected = set(at_source)
    if base is not None:
        try:
            at_base = entries(base, root)
        except subprocess.CalledProcessError:
            return found + [f"branch base {base[:12]} is not available (shallow clone?): cannot verify (fail closed)"]
        found += committed_changes(base, root, at_base)
        protected |= set(at_base)
    return found + working_tree_changes(protected, root)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["--baseline"] and len(argv) == 2:
        b = build_baseline()
        with open(argv[1], "x", encoding="utf-8") as f:
            f.write(json.dumps(b, indent=1) + "\n")
        print(f"wrote {argv[1]}: {b['file_count']} released files at {b['source_revision'][:12]}")
        return 0
    if argv != ["--check"]:
        print(__doc__)
        return 2
    found = check()
    for p in found[:50]:
        print(f"FAIL  {p}")
    if len(found) > 50:
        print(f"... and {len(found) - 50} more")
    print("released-V2 evidence guard (DETECTIVE): " + ("FAIL" if found else "PASS"))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
