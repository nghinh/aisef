"""PROBE-IDENTITY RE-BINDING (V2.0 release charter, fix B1) — the one place the rule lives.

B1 changed the sources of three probes, hence their catalog digests, hence the id and semantic hash of every
ProductProofSpec compiled against them, and every hash computed over those (a plan's hash, a proposal's digest, a
contract-spec digest). Historical records keep the identities they were made with and stay byte-identical. A
re-derivation on this tree is CURRENT UP TO PROBE IDENTITY with such a record iff, fail closed:

1. every field at which they differ is a probe-identity field — a spec's probe digest, the spec id and semantic hash
   that bind it, a hash over those — or a provenance field the caller tolerates by its own exact rule (`compare`);
2. spec by spec (spec key): the same contract id and contract hash, the same probe id; the record's probe digest is
   the accepted one and the re-derived one is this tree's catalog digest for that probe (`spec_subst`);
3. with every re-derived spec id, semantic hash and probe digest replaced by the record's of the same spec key
   (`back`), the hashes over them recomputed (`plan_back`, the caller's digests) equal the record's EXACTLY.

A spec that breaks rule 2 gets no substitution, so its identities stay different and the comparison fails. Only
identity COMPARISONS are mapped back: a probe always runs a spec compiled under this tree's catalog.
"""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: the record the owner accepted PLAN-V2.2 by (C2-P5): its specs and catalog are the accepted identities
PROPOSAL_REL = "closure-evidence/v2/cycle2/P5-PLAN-V2.2-PROPOSAL.json"
ROW = ("contract_id", "contract_hash", "spec_hash_id", "semantic_hash", "probe_id", "probe_digest")
IDENTITY = ("spec_hash_id", "semantic_hash", "probe_digest")


def accepted_rows() -> dict[str, dict]:
    """The accepted specs by spec key, each with the fields of `ROW`."""
    doc = json.loads((ROOT / PROPOSAL_REL).read_text(encoding="utf-8"))
    return {s["spec_id"]: {k: s[k] for k in ROW} for s in doc["specs"]}


def accepted_digests() -> dict[str, str]:
    """The probe digests PLAN-V2.2 was accepted under: the accepted proposal's catalog."""
    doc = json.loads((ROOT / PROPOSAL_REL).read_text(encoding="utf-8"))
    return {p: e["digest"] for p, e in doc["identities"]["catalog"].items()}


def tree_digests() -> dict[str, str]:
    from aisef2.probe import catalog
    return {e.probe_id: e.probe_digest for e in catalog.CATALOG}


def rows(compiled: dict, contracts: dict) -> dict[str, dict]:
    """Spec key -> the `ROW` fields of a compiled spec and its contract (both keyed by spec key)."""
    return {k: {"contract_id": s.contract_id, "contract_hash": contracts[k].contract_hash, "spec_hash_id": s.id,
                "semantic_hash": s.semantic_hash, "probe_id": s.probe_id, "probe_digest": s.probe_digest}
            for k, s in compiled.items()}


def spec_subst(derived: dict[str, dict], committed: dict[str, dict], accepted: dict[str, str] | None = None,
               digests: dict[str, str] | None = None) -> dict[str, str]:
    """Rule 2: re-derived identity -> the record's, for each spec key whose contract and probe id are the record's and
    whose probe digest moved from the accepted digest to this tree's catalog digest for that probe."""
    accepted = accepted_digests() if accepted is None else accepted
    digests = tree_digests() if digests is None else digests
    out: dict[str, str] = {}
    for key in sorted(derived.keys() & committed.keys()):
        d, c = derived[key], committed[key]
        same = all(d.get(k) == c.get(k) for k in ("contract_id", "contract_hash", "probe_id"))
        moved = c.get("probe_digest") == accepted.get(c.get("probe_id")) != d.get("probe_digest") == digests.get(d.get("probe_id"))
        if same and moved:
            out.update({d[k]: c[k] for k in IDENTITY})
    return out


def back(obj, subst: dict[str, str]):
    """`obj` with every string (value or key) that `subst` names replaced by the record's."""
    if isinstance(obj, dict):
        return {subst.get(k, k): back(v, subst) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [back(v, subst) for v in obj]
    return subst.get(obj, obj) if isinstance(obj, str) else obj


def plan_back(plan, subst: dict[str, str], id: str | None = None):  # noqa: A002 — the Plan field's own name
    """Rule 3 for a plan: the same plan with each obligation's spec id mapped back, its hash recomputed."""
    from aisef2.plan.obligation import Plan
    return Plan.create(id=id or plan.id, baseline=plan.baseline, plan_quality_policy=plan.plan_quality_policy,
                       obligations=tuple(dataclasses.replace(o, product_proof_spec_id=subst.get(o.product_proof_spec_id, o.product_proof_spec_id))
                                         for o in plan.obligations))


def paths(a, b, at: str = "") -> list[str]:
    """The dotted paths where two JSON values differ."""
    if isinstance(a, dict) and isinstance(b, dict):
        return [p for k in sorted(set(a) | set(b)) for p in paths(a.get(k), b.get(k), f"{at}.{k}" if at else k)]
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [p for i, (x, y) in enumerate(zip(a, b, strict=True)) for p in paths(x, y, f"{at}[{i}]")]
    return [] if a == b else [at]


def _at(doc, path: str):
    for part in path.split("."):        # a tolerated path names dict keys only
        doc = doc.get(part) if isinstance(doc, dict) else None
    return doc


def compare(derived: dict, committed: dict, subst: dict[str, str], tolerated: dict[str, tuple]) -> dict:
    """Rule 1: `derived` mapped back by `subst` against `committed`. Current when every path still differing is a
    tolerated provenance path whose committed and derived values are exactly the (committed, derived) pair given."""
    diff = paths(back(derived, subst), committed)
    ok = all(p in tolerated and (_at(committed, p), _at(derived, p)) == tolerated[p] for p in diff)
    return {"differing_paths": diff, "identities_rebound": len(subst), "provenance_only": bool(diff) and ok, "current": ok}


def lf_sha_at(rev: str, rel: str) -> str | None:
    r = subprocess.run(["git", "-C", str(ROOT), "show", f"{rev}:{rel}"], capture_output=True)
    return hashlib.sha256(r.stdout.replace(b"\r\n", b"\n")).hexdigest() if r.returncode == 0 else None


def code_moved(rel: str, rev: str, only: tuple[str, ...]) -> bool:
    """`rel` on this tree differs from `rel` at `rev` in its top-level functions `only` and nowhere else (comments
    aside): the module was taught the re-binding there, so a record's sha256 of it is provenance that moved."""
    r = subprocess.run(["git", "-C", str(ROOT), "show", f"{rev}:{rel}"], capture_output=True, encoding="utf-8")

    def rest(src: str) -> str:
        tree = ast.parse(src)
        tree.body = [n for n in tree.body if not (isinstance(n, ast.FunctionDef) and n.name in only)]
        return ast.dump(tree)
    return r.returncode == 0 and rest(r.stdout) == rest((ROOT / rel).read_text(encoding="utf-8"))
