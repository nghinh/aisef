"""The project bundle: everything a run proves a project against, as one JSON document (`FORMAT`).

    {"format": "aisef-v2-project/1", "name": ..., "description": ...,
     "requirements_document": {"path": "docs/requirements.md", "sha256": ...},
     "product_roots": ["pkg", "tests"],
     "requirements": [Requirement content, with its requirement_hash],
     "contracts": [BehaviorContract.to_json()],
     "approvals": [ContractApproval content],
     "plan": {Plan content, with its plan_hash; obligations with their roles and expected parents},
     "facts": {criterion_id: {"requirement", "section", "clause", "clause_text", "subject"}},
     "stories": {story_id: {"depends_on": [story_id, ...], "tests": [path, ...]}}}

Loading re-checks every seal (a requirement, contract or plan whose hash does not bind its content is refused by the
kernel's own constructors), requires a human approval binding each contract to each requirement it cites, compiles
every contract with THIS release's probe catalog, and refuses a plan that names a spec no approved contract compiles
to. `facts` are public by construction — what the developer may be told; a probe's stimulus, observable or
expectation is never among them (`load` refuses a fact field outside FACT_FIELDS).
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
from dataclasses import dataclass
from typing import Any, Mapping

from aisef2.arch.enums import ObligationRole, ParentExpectation
from aisef2.plan.obligation import Plan, PlanObligation, PlanQualityPolicy
from aisef2.probe import catalog
from aisef2.product.approval import ContractApproval, Requirement
from aisef2.product.compiler import ProbeRef, compile_spec
from aisef2.product.contract import BehaviorContract, plain
from aisef2.product.spec import ProductProofSpec

FORMAT = "aisef-v2-project/1"
FACT_FIELDS = ("requirement", "section", "clause", "clause_text", "subject")
KEYS = ("format", "name", "description", "requirements_document", "product_roots", "requirements", "contracts",
        "approvals", "plan", "facts", "stories")


class BundleError(ValueError):
    """The bundle is not a project this release can run: refused, never repaired."""


_HEX64 = re.compile(r"[0-9a-f]{64}")


def _strings(v, where: str, *, empty: bool = True) -> list[str]:
    """`v` as a list of non-empty strings — never a string read as its letters."""
    if not isinstance(v, list) or not all(isinstance(x, str) and x for x in v) or (not empty and not v):
        raise BundleError(f"{where}: a{'' if empty else ' non-empty'} list of non-empty strings, not {type(v).__name__}")
    return v


def shape_problems(data: Mapping) -> None:
    """The bundle's JSON types, checked before any kernel constructor sees them; the first problem names its path.

    A bundle is sealed on one machine and run on another, and the project supports Windows: a path is confined to the
    repository on every platform's reading. `/` and `\\` both separate; a leading separator, a drive (`C:/x`, `C:x`)
    or a UNC share makes a path absolute, and a `..` component climbs out of the root. A product root is one name:
    none of those, and no separator at all."""

    def outside(p: str) -> bool:
        w = pathlib.PureWindowsPath(p)      # its reading of `/` and `..` is the POSIX one, plus `\` and drives
        return bool(w.drive or w.root or ".." in w.parts)

    for k in ("name", "description"):
        if not isinstance(data[k], str):
            raise BundleError(f"$.{k}: a string")
    for k in ("requirements", "contracts", "approvals"):
        if not isinstance(data[k], list) or not all(isinstance(x, Mapping) for x in data[k]):
            raise BundleError(f"$.{k}: a list of objects")
    doc = data["requirements_document"]
    if not isinstance(doc, Mapping):
        raise BundleError("$.requirements_document: an object of exactly path and sha256")
    for k in sorted({"path", "sha256"} ^ set(doc)):
        raise BundleError(f"$.requirements_document.{k}: {'missing' if k in ('path', 'sha256') else 'not a field of it'}")
    path = doc["path"]
    if not isinstance(path, str) or not path or outside(path):
        raise BundleError("$.requirements_document.path: a path relative to the repository root")
    if not isinstance(doc["sha256"], str) or not _HEX64.fullmatch(doc["sha256"]):
        raise BundleError("$.requirements_document.sha256: 64 lowercase hex characters")
    roots = _strings(data["product_roots"], "$.product_roots", empty=False)
    if any("/" in r or "\\" in r or r in (".", "..") or pathlib.PureWindowsPath(r).drive for r in roots):
        raise BundleError("$.product_roots: top-level names of the project's own source tree")
    if not isinstance(data["plan"], Mapping):
        raise BundleError("$.plan: an object")
    facts = data["facts"]
    if not isinstance(facts, Mapping) or not all(isinstance(v, Mapping) for v in facts.values()):
        raise BundleError("$.facts: an object of criterion id -> its public facts")
    stories = data["stories"]
    if not isinstance(stories, Mapping):
        raise BundleError("$.stories: an object of story id -> {depends_on, tests}")
    for sid, s in stories.items():
        if not isinstance(s, Mapping) or sorted(s) != ["depends_on", "tests"]:
            raise BundleError(f"$.stories.{sid}: an object of exactly depends_on and tests"
                              + (f" (it holds {sorted(s)})" if isinstance(s, Mapping) else ""))
        unknown = sorted(set(_strings(s["depends_on"], f"$.stories.{sid}.depends_on")) - set(stories))
        if unknown:
            raise BundleError(f"$.stories.{sid}.depends_on: names stories the bundle does not hold: {unknown}")
        for t in _strings(s["tests"], f"$.stories.{sid}.tests"):
            if outside(t):
                raise BundleError(f"$.stories.{sid}.tests: {t!r} is not a path relative to the repository root")


@dataclass(frozen=True)
class Project:
    name: str
    description: str
    requirements_path: str
    requirements_sha256: str
    product_roots: tuple[str, ...]
    requirements: dict[str, Requirement]
    contracts: dict[str, BehaviorContract]
    approvals: tuple[ContractApproval, ...]
    specs: dict[str, ProductProofSpec]          # spec id -> spec, compiled under this release's probes
    plan: Plan
    facts: dict[str, dict]                      # criterion -> its public facts
    stories: dict[str, dict]                    # story -> {"depends_on": [...], "tests": [...]}
    digest: str                                 # sha256 of the bundle's canonical JSON

    def order(self) -> list[str]:
        """The plan's stories in dependency order (ties by name); a cycle is refused."""
        stories = sorted({o.story_id for o in self.plan.obligations})
        done: set[str] = set()
        out: list[str] = []
        while len(out) < len(stories):
            ready = [s for s in stories if s not in done
                     and not (set(self.stories[s]["depends_on"]) & set(stories)) - done]
            if not ready:
                raise BundleError("the plan's story graph has a cycle")
            out.append(ready[0])
            done.add(ready[0])
        return out


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _plan(d: Mapping) -> Plan:
    obligations = tuple(PlanObligation(o["criterion_id"], o["product_proof_spec_id"], o["story_id"],
                                       ObligationRole(o["role"]), ParentExpectation(o["expected_parent"]),
                                       tuple(o["depends_on"]), o["ownership_rationale"]) for o in d["obligations"])
    policy = PlanQualityPolicy(**d["plan_quality_policy"])
    return Plan(d["id"], d["baseline"], obligations, policy, d["plan_hash"])


def dump(*, name: str, description: str, requirements_path: str, requirements_sha256: str, product_roots,
         requirements, contracts, approvals, plan: Plan, facts: Mapping, stories: Mapping) -> dict:
    """A bundle from kernel objects (the inverse of `load`)."""
    return {"format": FORMAT, "name": name, "description": description,
            "requirements_document": {"path": requirements_path, "sha256": requirements_sha256},
            "product_roots": sorted(product_roots), "requirements": [plain(r) for r in requirements],
            "contracts": [c.to_json() for c in contracts], "approvals": [plain(a) for a in approvals],
            "plan": plain(plan), "facts": {k: dict(v) for k, v in facts.items()},
            "stories": {k: {"depends_on": list(v["depends_on"]), "tests": list(v["tests"])} for k, v in stories.items()}}


def load(data: Mapping) -> Project:
    """The project a bundle describes, every seal re-checked and every spec compiled under this release's probes."""
    if not isinstance(data, Mapping) or data.get("format") != FORMAT:
        raise BundleError(f"not a project bundle of format {FORMAT}")
    if sorted(data) != sorted(KEYS):
        raise BundleError(f"a bundle holds exactly {sorted(KEYS)}; it holds {sorted(data)}")
    shape_problems(data)
    try:
        requirements = {r["id"]: Requirement(**r) for r in data["requirements"]}
        contracts = {c["id"]: BehaviorContract.from_json(c) for c in data["contracts"]}
        approvals = tuple(ContractApproval(**a) for a in data["approvals"])     # model_reviews: the approval's own tuple
        plan = _plan(data["plan"])
    except (KeyError, TypeError, ValueError) as e:
        raise BundleError(f"the bundle's kernel objects do not load: {type(e).__name__}: {e}") from e
    refs = {kind: ProbeRef(e.probe_id, e.probe_digest) for kind, e in catalog.active().items()}
    specs: dict[str, ProductProofSpec] = {}
    for c in contracts.values():
        try:
            s = compile_spec(c, requirements=requirements, approvals=approvals, probes=refs)
        except ValueError as e:     # an unapproved contract, a requirement it cites that is absent, no probe for it
            raise BundleError(f"contract {c.id} does not compile: {e}") from e
        specs[s.id] = s
    unknown = sorted({o.product_proof_spec_id for o in plan.obligations} - set(specs))
    if unknown:
        raise BundleError(f"the plan names {len(unknown)} spec(s) no approved contract compiles to under this release's "
                          f"probes: {unknown[:3]} — a bundle of an earlier release: `aisef bundle migrate`")
    criteria = {o.criterion_id for o in plan.obligations}
    facts = {k: dict(v) for k, v in data["facts"].items()}
    if set(facts) != criteria or any(set(v) != set(FACT_FIELDS) or not all(isinstance(x, str) for x in v.values())
                                     for v in facts.values()):
        raise BundleError(f"facts are the public fields {list(FACT_FIELDS)} (strings) of every plan criterion, and no other")
    stories = {k: {"depends_on": list(v["depends_on"]), "tests": list(v["tests"])} for k, v in data["stories"].items()}
    if set(stories) != {o.story_id for o in plan.obligations}:
        raise BundleError("stories are exactly the plan's stories")
    doc = data["requirements_document"]
    roots = tuple(data["product_roots"])     # shape_problems checked them: a non-empty list of top-level names
    project = Project(str(data["name"]), str(data["description"]), str(doc["path"]), str(doc["sha256"]), roots,
                      requirements, contracts, approvals, specs, plan, facts, stories,
                      hashlib.sha256(_canonical(dict(data))).hexdigest())
    project.order()     # a cycle is refused at load
    return project


def read(path: str | pathlib.Path) -> Project:
    """The project of the bundle file at `path`; a file that cannot be read or is not JSON is refused like any other
    bundle that does not hold."""
    try:
        text = pathlib.Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise BundleError(f"{path}: cannot be read ({type(e).__name__}: {e})") from e
    try:
        data = json.loads(text)
    except ValueError as e:
        raise BundleError(f"{path}: not JSON ({e})") from e
    return load(data)
