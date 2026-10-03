"""V2.0 release smoke — the authoritative developer context (owner ruling 'AISEF V2 — CONTINUE RELEASE EXECUTION / OWNER
RULING FOR RISK-G7-1', option 2: correct the workload context before preregistration).

    python -P validation/qualification/release_workload.py --write   # derive the release-smoke repository + the two records
    python -P validation/qualification/release_workload.py --check   # the records, the repository and the invariants hold

Attempts 3 and 4 failed after the developer consumed superseded V1/BMAD planning output that the LedgerLock repository
holds at the plan's baseline (`_bmad-output/`). The release smoke therefore runs on a snapshot of that baseline that
holds only what a POSITIVE authority policy admits (`AUTHORITY`): the frozen requirements, package and repository
metadata, the product's own source and tests (none exist at the baseline). The plan, the story's obligations and the
approved contracts reach the developer through the release bundle — never through files in the workspace.

A path is removed by its PROVENANCE, never by its content: when the commit that introduced it is one of the earlier
methodology's tool runs (`METHODOLOGY`, the V1 AISEF setup/init/plan commits) AND its path falls in a named category
of that tool's output (`CATEGORIES`). A path introduced by the authored-input commit is kept; a path matching only one
of the two conditions is ambiguous — kept, and reported. Nothing is edited: a kept file is byte-identical.

Derivation: the baseline's tree minus the removed paths must equal the tree of an existing commit of the source
workload — here the authored-input commit itself — or the derivation stops (no synthetic commit is made). The
release-smoke repository holds that one commit and nothing else (fetched alone: no object of a removed path is
reachable, not even through history). The source repository is only read.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

POLICY_REL = "closure-evidence/v2/release/V2-RELEASE-WORKLOAD-CONTEXT-POLICY.json"
DERIVATION_REL = "closure-evidence/v2/release/V2-RELEASE-WORKLOAD-DERIVATION.json"
AUTHORITY_RULING = "owner ruling 'AISEF V2 — CONTINUE RELEASE EXECUTION / OWNER RULING FOR RISK-G7-1' (2026-10-03), option 2"
#: the approved plan's baseline (PLAN-V2.2-CORRECTION-1) in the preserved LedgerLock workload
SOURCE_SHA = "136a68dcdc3f416b2a76c561a7df12d1282ad4d5"
#: the commit that authored the workload's inputs: "docs: initial LedgerLock requirements (...)"
AUTHORED_INPUT = "6a8d60c0bd3d1fa47ed4e97dd80fc0f4b645332a"
#: the earlier methodology's tool runs, each with its subject line as recorded in the source workload
METHODOLOGY = {
    "35f33e789e178aa77a4fd5c6c6a1b00201e03212": "evidence: initial AISEF plan attempt, machine-gate failures captured "
                                                "(the output of V1 `aisef setup` / `aisef init` / `aisef plan`)",
    "8ff9f133c4579fbeeb2a9d2ed22852cbe5370a19": "epics.md: split to 16 stories — second plan attempt passed (V1 `aisef plan`)",
    "1621a2bce231d158c08a3b60e6c9b4f4b96ec8d0": "W1-LEDGERLOCK-PLAN-V2: V1 story files edited (acceptance criteria)",
    "136a68dcdc3f416b2a76c561a7df12d1282ad4d5": "W1-LEDGERLOCK-PLAN-V2.1: V1 story files edited (usage-error ownership)",
}
#: the positive policy: the only sources the developer's context derives from (owner ruling §2)
AUTHORITY = [
    {"source": "frozen current requirements", "carrier": "docs/requirements.md at the baseline (its sha256 is bound by the bundle)"},
    {"source": "current approved plan, story and PlanObligations", "carrier": "the release bundle — told to the developer in the prompt; not a workspace file"},
    {"source": "current approved public product contracts", "carrier": "the release bundle's contracts, as their public facts in the prompt"},
    {"source": "current product source", "carrier": "the bundle's product roots in the workspace (none exist at the baseline)"},
    {"source": "legitimate tests and package metadata", "carrier": "tests under the product roots, pyproject.toml, as normal story scope allows"},
]
#: what each kept path is, by the authored-input commit that introduced it
KEPT = {
    "docs/requirements.md": ("REQUIREMENTS", "the frozen requirements"),
    "pyproject.toml": ("PACKAGE_METADATA", "the product's package metadata"),
    ".gitignore": ("REPOSITORY_METADATA", "authored with the requirements"),
    "README.md": ("PRODUCT_SUMMARY", "authored with the requirements; a five-line product summary that defers to docs/requirements.md — "
                                    "not named by the positive policy, so ambiguous: kept and reported (owner ruling §4)"),
}
#: categories of the earlier methodology's output: (path or directory prefix, category, what it is)
CATEGORIES = [
    ("_bmad-output/", "V1_BMAD_PLANNING_OUTPUT", "the V1 BMAD planning output (PRD, architecture, epics, stories, approvals, "
                                                "mockups, plan transcripts) — superseded by the approved V2 plan"),
    ("evidence/", "V1_TOOL_RUN_LOGS", "logs and planning checkpoints of the V1 `aisef doctor/setup/init/plan` runs"),
    ("AGENTS.md", "V1_SETUP_AGENT_RULES", "agent rules generated by `aisef setup` (its own header says so): the V1 workflow "
                                          "(write_scope, story gates, BMAD customisation) — auto-loaded by coding clients as instructions"),
    ("CLAUDE.md", "V1_SETUP_AGENT_RULES", "the same generated rules under the second name coding clients auto-load"),
    (".claude/", "V1_SETUP_AGENT_SKILLS", "skills and commands installed by `aisef setup` (BMAD, UI, security), loadable by the client"),
    (".ai/", "V1_TOOL_CONFIGURATION", "the V1 `aisef init` project configuration (test/lint commands, sandbox)"),
    (".DS_Store", "OS_METADATA", "macOS Finder metadata committed with the V1 plan attempt"),
]
INVARIANTS = ("REQUIREMENTS_CHANGED", "PLAN_CHANGED", "PRODUCT_SPECS_CHANGED", "PRODUCT_SOURCE_BASELINE_CHANGED",
              "MANDATORY_ACCEPTANCE_CHANGED")


def source_repo() -> pathlib.Path:
    from validation.qualification import p10 as P10
    return P10.LEDGERLOCK_REPO


#: the release-smoke repository: outside any repository, beside the preserved source workload
RELEASE_REPO = pathlib.Path("/Users/nghinh/Downloads/projects/ledgerlock-v2-release-smoke")


def _git(repo: pathlib.Path, *args: str, check: bool = True) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, encoding="utf-8")
    if check and r.returncode != 0:
        raise SystemExit(f"git {' '.join(args[:3])} in {repo}: {r.stderr.strip()[:300]}")
    return r.stdout if r.returncode == 0 else ""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def tree_entries(repo: pathlib.Path, rev: str) -> list[tuple[str, str, str]]:
    """(mode, blob, path) of every file of `rev`, sorted by path."""
    out = []
    for line in _git(repo, "ls-tree", "-r", "--full-tree", rev).splitlines():
        meta, path = line.split("\t", 1)
        mode, _kind, blob = meta.split()
        out.append((mode, blob, path))
    return sorted(out, key=lambda e: e[2])


def digest(entries: list[tuple[str, str, str]]) -> str:
    """The workload digest: sha256 of the canonical JSON list of [mode, blob, path] — content-addressed by git's blobs."""
    return _sha(json.dumps([list(e) for e in entries], separators=(",", ":")).encode())


def introduced_by(repo: pathlib.Path, rev: str) -> dict[str, str]:
    """Path -> the commit (in `rev`'s history) that added it."""
    out: dict[str, str] = {}
    commit = None
    for line in _git(repo, "log", "--diff-filter=A", "--name-only", "--format=@%H", rev).splitlines():
        if line.startswith("@"):
            commit = line[1:]
        elif line:
            out.setdefault(line, commit)      # newest first: a path re-added later keeps its latest introduction
    return out


def category(path: str) -> tuple[str, str] | None:
    for prefix, name, what in CATEGORIES:
        if path == prefix or (prefix.endswith("/") and path.startswith(prefix)):
            return name, what
    return None


def classify(entries: list[tuple[str, str, str]], origin: dict[str, str]) -> dict:
    """Every path of the source: kept (authored input, or ambiguous), or removed (methodology output by both provenance and
    category)."""
    kept, removed, ambiguous = [], [], []
    for mode, blob, path in entries:
        by = origin.get(path)
        cat = category(path)
        if by == AUTHORED_INPUT and cat is None:
            kind, why = KEPT.get(path, ("AUTHORED_INPUT", "introduced by the authored-input commit"))
            row = {"path": path, "mode": mode, "blob": blob, "category": kind, "why": why, "introduced_by": by}
            kept.append(row)
            if path not in KEPT or "ambiguous" in why:
                ambiguous.append({**row, "reason": "kept: not named by the positive policy"})
        elif by in METHODOLOGY and cat is not None:
            removed.append({"path": path, "mode": mode, "blob": blob, "category": cat[0], "introduced_by": by})
        else:
            row = {"path": path, "mode": mode, "blob": blob, "category": "AMBIGUOUS", "introduced_by": by,
                   "why": "provenance and category disagree", "reason": "kept (owner ruling §4)"}
            kept.append(row)
            ambiguous.append(row)
    return {"kept": kept, "removed": removed, "ambiguous": ambiguous}


def derive() -> dict:
    """The derivation, re-computed from the source workload; refuses unless the sanitised tree is an existing commit's."""
    src = source_repo()
    entries = tree_entries(src, SOURCE_SHA)
    c = classify(entries, introduced_by(src, SOURCE_SHA))
    target = tree_entries(src, AUTHORED_INPUT)
    if sorted(((r["mode"], r["blob"], r["path"]) for r in c["kept"]), key=lambda e: e[2]) != target:
        raise SystemExit("the sanitised baseline is not the tree of an existing commit of the workload: STOP (no synthetic "
                         "commit is made)")
    return {"source": {"repository": str(src), "sha": SOURCE_SHA, "tree": _git(src, "rev-parse", f"{SOURCE_SHA}^{{tree}}").strip(),
                       "digest": digest(entries), "files": len(entries)},
            "derived": {"repository": str(RELEASE_REPO), "sha": AUTHORED_INPUT,
                        "tree": _git(src, "rev-parse", f"{AUTHORED_INPUT}^{{tree}}").strip(), "digest": digest(target),
                        "files": len(target), "rule": "the source tree minus the removed paths, equal byte for byte (git blobs) "
                                                      "to the tree of the authored-input commit; that commit is the release-smoke workload"},
            **c}


def materialise() -> list[str]:
    """Create RELEASE_REPO holding exactly AUTHORED_INPUT (fetched alone), or verify the one that exists."""
    if not RELEASE_REPO.exists():
        RELEASE_REPO.mkdir(parents=True)
        _git(RELEASE_REPO, "init", "-q", "-b", "main")
    if not _git(RELEASE_REPO, "for-each-ref").strip():      # initialised here and still empty: fetch the one commit
        _git(RELEASE_REPO, "fetch", "-q", "--no-tags", "--no-write-fetch-head", "--update-head-ok", str(source_repo()),
             f"{AUTHORED_INPUT}:refs/heads/main")
        _git(RELEASE_REPO, "checkout", "-q", "-f", "main")
    return repository_problems()


def repository_problems() -> list[str]:
    if not (RELEASE_REPO / ".git").is_dir():
        return [f"{RELEASE_REPO} is not a repository"]
    out = []
    refs = _git(RELEASE_REPO, "for-each-ref", "--format=%(refname) %(objectname)").split("\n")
    if [r for r in refs if r] != [f"refs/heads/main {AUTHORED_INPUT}"]:
        out.append(f"the release-smoke repository's refs are not exactly main = {AUTHORED_INPUT[:12]}: {refs}")
    if _git(RELEASE_REPO, "rev-list", "--all").split() != [AUTHORED_INPUT]:
        out.append("the release-smoke repository holds history beyond the one commit")
    if _git(RELEASE_REPO, "status", "--porcelain", "--ignored"):
        out.append("the release-smoke repository's worktree is not the commit's")
    have = set(_git(RELEASE_REPO, "cat-file", "--batch-all-objects", "--batch-check=%(objectname)").split())
    want = {line.split()[0] for line in _git(RELEASE_REPO, "rev-list", "--objects", "--all").splitlines() if line}
    if have != want:
        out.append(f"the release-smoke repository holds {len(have - want)} object(s) not reachable from the commit")
    return out


def invariants() -> dict:
    """The owner's sanitation invariants (§4), each measured by comparing the release-smoke bundle (the derived
    baseline) with the same bundle built on the approved baseline: everything but the plan's baseline must be equal,
    and the plan mapped back to the approved baseline must be the approved re-bound plan exactly."""
    from aisef2.app import bundle
    from validation.qualification import c2_p9
    from validation.qualification import release_acceptance as A
    from validation.qualification import release_bundle as rb
    src = source_repo()
    smoke, approved = rb.build(), rb.build(baseline=SOURCE_SHA)
    s_doc, a_doc = smoke["bundle"], approved["bundle"]
    s_prj, a_prj = bundle.load(s_doc), bundle.load(a_doc)
    rec = smoke["record"]
    roots = sorted(c2_p9.PROJECT)
    product = {r: [_git(src, "rev-parse", f"{rev}:{r}", check=False).strip() or None for rev in (SOURCE_SHA, AUTHORED_INPUT)]
               for r in roots}
    specs = {k: (s.id, s.semantic_hash, s.probe_id, s.probe_digest) for k, s in s_prj.specs.items()}
    suite_s, suite_a = A.suite(s_prj), A.suite(a_prj)
    same = {k: s_doc[k] == a_doc[k] for k in sorted(s_doc) if k != "plan"}
    plan_rest = {k: s_doc["plan"][k] == a_doc["plan"][k] for k in sorted(s_doc["plan"]) if k not in ("baseline", "plan_hash")}
    return {
        "REQUIREMENTS_CHANGED": "NO" if same["requirements"] and same["requirements_document"]
        and rec["requirements_document"]["sha256"] == rec["requirements_document"]["frozen"] else "YES",
        "PLAN_CHANGED": "NO" if all(plan_rest.values()) and rec["workload"]["only_the_baseline_moved"]
        and rec["rebinding"]["only_spec_ids_moved"] and same["stories"] and same["facts"] else "YES",
        "PRODUCT_SPECS_CHANGED": "NO" if specs == {k: (s.id, s.semantic_hash, s.probe_id, s.probe_digest) for k, s in a_prj.specs.items()}
        and same["contracts"] and same["approvals"] else "YES",
        "PRODUCT_SOURCE_BASELINE_CHANGED": "NO" if all(a == b for a, b in product.values()) and same["product_roots"] else "YES",
        "MANDATORY_ACCEPTANCE_CHANGED": "NO" if suite_s == suite_a and len(suite_s) == len(s_prj.specs) else "YES",
        "evidence": {
            "fields_equal_between_the_two_bundles": same, "plan_fields_equal_but_the_baseline": plan_rest,
            "requirements_document": rec["requirements_document"],
            "plan": {"plan_id": rec["bundle"]["plan_id"], "plan_hash_for_the_smoke": rec["bundle"]["plan_hash"],
                     "plan_hash_on_the_approved_baseline": approved["record"]["bundle"]["plan_hash"],
                     "workload_rebinding": rec["workload"],
                     "probe_identity_rebinding": {k: v for k, v in rec["rebinding"].items() if k != "spec_ids"}},
            "product_proof_specs": {"count": len(specs), "digest": _sha(json.dumps(sorted(specs.items())).encode())},
            "product_roots_at_source_and_derived": product,
            "acceptance_suite": {"count": len(suite_s), "sha256": _sha(json.dumps(suite_s, sort_keys=True).encode())},
            "bundle_digest_for_the_smoke": rec["bundle"]["digest"],
        },
    }


def policy() -> dict:
    return {"record": "AISEF V2.0 — RELEASE-SMOKE WORKLOAD CONTEXT POLICY (positive authority; removal by provenance)",
            "authority": AUTHORITY_RULING,
            "rule": "for V2 release-smoke execution, superseded planning / implementation artifacts of earlier methodologies "
                    "are not developer authority: the developer's context derives only from `authoritative_sources`; a path of "
                    "the workload is removed only when the commit that introduced it is one of `methodology_commits` AND it is "
                    "in one of `removal_categories`; a path introduced by the authored-input commit is kept byte-identical; "
                    "any other path is ambiguous — kept and reported. Content is never searched for an answer.",
            "authoritative_sources": AUTHORITY, "authored_input_commit": AUTHORED_INPUT, "methodology_commits": METHODOLOGY,
            "removal_categories": [{"path": p, "category": c, "what": w} for p, c, w in CATEGORIES],
            "kept_paths": {p: {"category": c, "why": w} for p, (c, w) in KEPT.items()},
            "never": ["edit a kept file", "make a synthetic commit", "change requirements, contracts, ProductProofSpecs, the "
                      "approved plan or the frozen acceptance", "expose a probe's hidden stimulus or oracle to the developer",
                      "mutate the source workload or its preserved evidence"],
            "required_invariants": {k: "NO" for k in INVARIANTS},
            "generator": "validation/qualification/release_workload.py"}


def build() -> dict:
    d = derive()
    inv = invariants()
    problems = [f"{k} = {inv[k]}" for k in INVARIANTS if inv[k] != "NO"] + repository_problems()
    return {"policy": policy(),
            "derivation": {"record": "AISEF V2.0 — RELEASE-SMOKE WORKLOAD DERIVATION (LedgerLock, authoritative context)",
                           "authority": AUTHORITY_RULING, "policy": POLICY_REL, **d,
                           "removed_by_category": {c: sum(1 for r in d["removed"] if r["category"] == c) for _p, c, _w in CATEGORIES},
                           "removed_objects_absent_from_the_release_repository": not repository_problems(),
                           "invariants": inv, "problems": problems,
                           "verdict": "WORKLOAD_CONTEXT_SANITIZED" if not problems else "PROBLEMS"}}


def _render(o) -> str:
    return json.dumps(o, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", action="store_true")
    g.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    if a.write:
        problems = materialise()
        if problems:
            print("\n".join(problems), file=sys.stderr)
            return 1
    b = build()
    if a.write:
        (ROOT / POLICY_REL).write_text(_render(b["policy"]), encoding="utf-8")
        (ROOT / DERIVATION_REL).write_text(_render(b["derivation"]), encoding="utf-8")
        print(f"wrote {POLICY_REL} and {DERIVATION_REL}: {b['derivation']['verdict']} {b['derivation']['problems']}")
        return 0 if not b["derivation"]["problems"] else 1
    stale = [rel for rel, body in ((POLICY_REL, b["policy"]), (DERIVATION_REL, b["derivation"]))
             if not (ROOT / rel).exists() or (ROOT / rel).read_text(encoding="utf-8") != _render(body)]
    problems = b["derivation"]["problems"] + [f"{rel} is not the re-derived record" for rel in stale]
    print("release workload: " + ("PASS" if not problems else "FAIL " + "; ".join(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
