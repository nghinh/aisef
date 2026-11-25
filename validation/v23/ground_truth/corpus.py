"""B2 corpus: item model, manifest, §2.3 repo criteria (B2-GROUND-TRUTH-PROTOCOL-DRAFT, 2026-11-25 draft).

§2.1: "A corpus item MUST be the tuple `(repo snapshot, approved bundle, candidate, labelset)`" — here one JSON
object carrying every identity digest: the snapshot's commit SHA + archive sha256 (§2.3.6 "the snapshot, not the
live remote, is the measured object"), the approved bundle's `plan_hash` / `requirements sha256` (the workload
identity, B-M5), the candidate's diff-or-tree sha256, the recipe digest for seeded defects (§2.4) and the
labelset sha256 (§3). §2.2: the classes KNOWN_GOOD / IN_SCOPE_DEFECT / OUT_OF_SCOPE_DEFECT "all three MUST be
present per repo — the non-conflation requirement", each with its expected `delivery()` verdict fixed by the
class table, never hand-assigned.

§2.3 ("What a 'representative external repository' MUST satisfy (measurable before selection)") is validated by
`repo_criteria_problems` over MEASURED values "checked and recorded in `CORPUS-MANIFEST.json` before the repo is
proposed to the owner" — the measurement happens elsewhere; this checks the recorded numbers against the bounds.

    python3 -P validation/v23/ground_truth/corpus.py --check [MANIFEST.json]
        validate the manifest (default validation/v23/ground_truth/CORPUS-MANIFEST.json); exit 1 on any
        problem, a missing or unreadable manifest included (fail closed)
"""

from __future__ import annotations

import json
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.v23.ground_truth import canonical, hex_problems  # noqa: E402

SCHEMA = "aisef.v23.ground_truth.corpus/1"
MANIFEST_REL = "validation/v23/ground_truth/CORPUS-MANIFEST.json"
#: §2.2 item classes and the expected delivery() verdict each one fixes (OUT_OF_SCOPE_DEFECT passes BY DESIGN,
#: "reported separately as a by-design escape, never pooled with false-accepts")
CLASSES = ("KNOWN_GOOD", "IN_SCOPE_DEFECT", "OUT_OF_SCOPE_DEFECT")
EXPECTED_DELIVERY = {"KNOWN_GOOD": "PASS", "IN_SCOPE_DEFECT": "FAIL", "OUT_OF_SCOPE_DEFECT": "PASS"}
#: §2.5: Tier-0 results are "reported separately, labeled `tier: "seed"`" and never pooled into Tier-1
TIERS = ("seed", "external")
#: §2.1: the candidate is "one worktree state (or diff against the snapshot)"
CANDIDATE_KINDS = ("diff", "tree")
#: every identity digest a §2.1 item must carry: ((group, field) or (field,), hex length)
DIGESTS = (("repo", "commit_sha", 40), ("repo", "archive_sha256", 64),
           ("bundle", "plan_hash", 64), ("bundle", "requirements_sha256", 64),
           ("candidate", "sha256", 64), (None, "labelset_sha256", 64))


def build_manifest(items: list[dict]) -> dict:
    """CORPUS-MANIFEST.json content — deterministic: the same item set in any order yields the same manifest."""
    key = (lambda i: i.get("id", "") if isinstance(i, dict) and isinstance(i.get("id"), str) else "")
    return {"record": "AISEF V2.3 — B2 GROUND-TRUTH CORPUS MANIFEST",
            "schema": SCHEMA,
            "protocol": "docs/v2.3/drafts/B2-GROUND-TRUTH-PROTOCOL-DRAFT.md (draft of 2026-11-25, pre-freeze)",
            "items": sorted(items, key=key)}


def render(items: list[dict]) -> str:
    """The manifest file's exact bytes: canonical JSON + one trailing newline."""
    return canonical(build_manifest(items)) + "\n"


def _item_problems(n: int, item: Any, seen: set, by_repo: dict) -> list[str]:
    if not isinstance(item, dict):
        return [f"item #{n} is not an object: {type(item).__name__}"]
    name = item["id"] if isinstance(item.get("id"), str) and item.get("id") else f"#{n}"
    out = []
    if name == f"#{n}":
        out.append(f"item {name}: id must be a non-empty string")
    elif name in seen:
        out.append(f"item {name}: duplicate item id")
    else:
        seen.add(name)
    if item.get("tier") not in TIERS:
        out.append(f"item {name}: tier {item.get('tier')!r} not in {TIERS}")
    cls = item.get("class")
    if cls not in CLASSES:
        out.append(f"item {name}: class {cls!r} not in {CLASSES}")
    elif item.get("expected_delivery") != EXPECTED_DELIVERY[cls]:
        out.append(f"item {name}: expected_delivery {item.get('expected_delivery')!r} is not the §2.2 "
                   f"verdict {EXPECTED_DELIVERY[cls]!r} for {cls} (derived mechanically, never hand-assigned)")
    for group, field, length in DIGESTS:
        holder = item if group is None else (item.get(group) if isinstance(item.get(group), dict) else {})
        label = field if group is None else f"{group}.{field}"
        out += [f"item {name}: {p}" for p in hex_problems(label, holder.get(field), length)]
    repo = item.get("repo") if isinstance(item.get("repo"), dict) else {}
    if isinstance(repo.get("name"), str) and repo.get("name"):
        by_repo.setdefault(repo["name"], set()).add(cls)
    else:
        out.append(f"item {name}: repo.name must be a non-empty string")
    cand = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
    if cand.get("kind") not in CANDIDATE_KINDS:
        out.append(f"item {name}: candidate.kind {cand.get('kind')!r} not in {CANDIDATE_KINDS}")
    recipe = item.get("recipe_sha256")
    if cls in ("IN_SCOPE_DEFECT", "OUT_OF_SCOPE_DEFECT") or recipe is not None:
        # §2.4: "Every seeded defect MUST exist as a committed recipe"; a KNOWN_GOOD candidate may instead be
        # "taken as the known-good tree" (§2.1), so its recipe digest may be null
        out += [f"item {name}: {p}" for p in hex_problems("recipe_sha256", recipe, 64)]
    return out


def manifest_problems(manifest: Any) -> list[str]:
    """Fail-closed §2.1/§2.2 validation: a malformed manifest returns named problems, never crashes."""
    if not isinstance(manifest, dict):
        return [f"manifest is not an object: {type(manifest).__name__}"]
    out = [] if manifest.get("schema") == SCHEMA else [f"manifest schema {manifest.get('schema')!r} is not {SCHEMA!r}"]
    items = manifest.get("items")
    if not isinstance(items, list):
        return out + [f"manifest items is not a list: {type(items).__name__}"]
    seen: set = set()
    by_repo: dict = {}
    for n, item in enumerate(items):
        out += _item_problems(n, item, seen, by_repo)
    for repo_name in sorted(by_repo):
        missing = [c for c in CLASSES if c not in by_repo[repo_name]]
        if missing:
            out.append(f"repo {repo_name}: §2.2 non-conflation requires all three classes per repo; missing {missing}")
    return out


# --------------------------------------------------------------------------------------- §2.3 repo criteria

#: §2.3.4 "OSI-approved license permitting local modification and analysis" — a closed allowlist of OSI-approved
#: SPDX ids; a license outside it is a named problem for a human to rule on, never a silent accept (fail closed).
# ponytail: closed allowlist; extend by one line when an owner-approved candidate carries another OSI id
OSI_APPROVED = frozenset({
    "MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "MPL-2.0", "Zlib", "Python-2.0", "Unlicense",
    "GPL-2.0-only", "GPL-2.0-or-later", "GPL-3.0-only", "GPL-3.0-or-later", "LGPL-2.1-only", "LGPL-2.1-or-later",
    "LGPL-3.0-only", "LGPL-3.0-or-later", "AGPL-3.0-only", "AGPL-3.0-or-later", "EPL-2.0"})

#: §2.3.2/§2.3.3/§2.3.5 booleans and the value each must measure (`is`-checked: a truthy string is not a measurement)
FLAGS = (("build_clean", True), ("suite_green_linux", True), ("suite_green_macos", True), ("offline", True),
         ("probe_criterion_ran", True), ("in_aisef_history", False), ("shares_workload_identity", False))


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def repo_criteria_problems(measured: Any) -> list[str]:
    """§2.3 bounds over recorded measured values. Keys: `loc` (§2.3.1: 1,000–200,000 lines), `build_clean` +
    `suite_green_linux` + `suite_green_macos` + `offline` + `suite_seconds` (§2.3.2: green on both, offline,
    "one full suite run < 10 minutes"), `probe_criterion_ran` (§2.3.3: one criterion written and run before
    selection), `license_spdx` (§2.3.4), `in_aisef_history` + `shares_workload_identity` (§2.3.5 independence),
    `commit_sha` + `archive_sha256` (§2.3.6 pinning). A missing or mistyped value is a problem (fail closed)."""
    if not isinstance(measured, dict):
        return [f"measured values are not an object: {type(measured).__name__}"]
    out = []
    loc = measured.get("loc")
    if not _number(loc) or not 1000 <= loc <= 200000:
        out.append(f"loc must be a measured number in 1000..200000 (§2.3.1): {loc!r}")
    for key, want in FLAGS:
        if measured.get(key) is not want:
            out.append(f"{key} must be the measured value {want} (§2.3): {measured.get(key)!r}")
    secs = measured.get("suite_seconds")
    if not _number(secs) or not 0 < secs < 600:
        out.append(f"suite_seconds must be a measured number in (0, 600) — '< 10 minutes' (§2.3.2): {secs!r}")
    if measured.get("license_spdx") not in OSI_APPROVED:
        out.append(f"license_spdx {measured.get('license_spdx')!r} is not in the known OSI-approved set (§2.3.4)")
    out += hex_problems("commit_sha", measured.get("commit_sha"), 40)
    out += hex_problems("archive_sha256", measured.get("archive_sha256"), 64)
    return out


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    args = [a for a in argv if a != "--check"]
    path = pathlib.Path(args[0]) if args else ROOT / MANIFEST_REL
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"FAIL  {path}: unreadable or not JSON (fail closed): {e}")
        return 1
    bad = manifest_problems(manifest)
    for p in bad:
        print(f"FAIL  {p}")
    items = manifest.get("items") if isinstance(manifest, dict) and isinstance(manifest.get("items"), list) else []
    print(f"B2 corpus manifest {path}: {len(items)} item(s), {len(bad)} problem(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
