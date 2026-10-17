"""`aisef bundle`: the project bundle's own tools — outside a run, no provider, no repository written.

    aisef bundle init [--example NAME] --out DIR            an example to start from: DIR/authoring.json, DIR/repo/
    aisef bundle seal AUTHORING.json --repo REPO --out B    every hash and spec id computed: the bundle, unapproved
                     [--keep-approvals-from OLD]            (an earlier bundle's approvals that still bind are kept)
    aisef bundle approve B --contract ID --approver human:NAME --out B2    one contract approved, by its human
    aisef bundle lint B                                     approvals, admission (RFC §12), calibration, clause coverage
    aisef bundle explain B                                  per story: each criterion, its contract, probe and class
    aisef bundle migrate IN --out OUT     a bundle of an earlier release, its plan re-bound to this release's spec ids
    aisef bundle continue B --from-run DIR [--expect-anchor A] --out B2   the stories DIR's run did not commit,
                     from what it did commit

`continue` (V2.1, proposal D): a run that was interrupted or stopped is never resumed in place and never modified. Its
journal says which stories committed and at which revision; the continuation's baseline is the last of them (journal
truth: a merge the journal never committed is reported and left out, never trusted). The committed stories' obligations
become one story's VERIFY obligations, proved again at that baseline by the kernel — with no developer call when they
hold; the one review request K-NOWORK-001 keeps for a story without developer work is the only provider spend of
inheriting — and the other stories run as they were. Contracts and approvals are
untouched (their semantics did not change). Run it against DIR/repo, the run's own clone, which holds the baseline,
with `aisef run --parent DIR` to record the lineage. A bundle or kernel that changed is a new project, not a continuation.

**The journal is read by the rule of `aisef run --verify`** (the same functions): it reads; it is the journal RUN.json
names (digest and length); it reconstructs (every event, the hash chain, the sequence); and no control projection the
kernel's writer enforces refuses it (`verify._projection_refusal`). A torn last line is the approved exception: it is
what a run killed mid-append leaves, and a continuation is for it — the reader's verified prefix is taken, the cut is
reported (`cut_event`) and its effects are reconciled against git, never assumed undone. Each way it can fail is told
apart (`JournalRefused.code`, in the text of `refused:`), because what the operator does differs:

    EVIDENCE_UNREADABLE   a file of the run exists or is named and cannot be read (permission, I/O, not there), or
                          the run's directory cannot be searched or listed
    EVIDENCE_MALFORMED    it was read and is not what a run writes (not text, a line, a format, a record: a RUN.json or
                          RUN.started.json that is not UTF-8 is damage — the kernel writes ASCII, a kill cannot make it)
    EVIDENCE_INTEGRITY    the journal is not the one that was written (hash chain, sequence, RUN.json's digest or length)
    EVIDENCE_PROJECTION   a valid chain the kernel's writer would have refused (a story that commits twice, ...)
    EVIDENCE_MISSING      nothing to continue from or to authenticate with: no run record, the record names no journal,
                          the journal committed no story; or the operator gave --expect-anchor and the run has no
                          EVIDENCE.json
    EVIDENCE_MISMATCH     --expect-anchor, or the manifest, is not what the run directory holds

Without `--expect-anchor` a continuation proves consistency, not authenticity (the run directory is writable by its
operator's user: docs/v2.1/ANCHOR-THREAT-MODEL.md), and the report says `anchor_checked: false`. A refusal writes
nothing, and the run is never modified.

The authoring document (AUTHORING_FORMAT, schema: docs/v2.1/bundle-authoring.schema.json) is the bundle without what
the kernel derives: no requirement, contract or plan hash, no spec id, no approval. `seal` derives them with the
kernel's own constructors and this release's probe catalog; it never approves — an approval is a human's statement
about one contract (`approve`, one contract per command, the approver named `human:<name>`). The tools cannot tell who
types the command: keep the bundle and these commands away from the developer agent. Exit status: 0 done (lint:
READY), 1 lint NOT_READY, 2 refused input.

`migrate` — V2.1 (ARCHITECTURE-EXCEPTION-V2-007): a ProductProofSpec binds its probe's capability (id, version, classes), no longer
the bytes of its source. A bundle written for 2.0.0 names spec ids compiled under 2.0.0's source digests, so its plan
names specs this release does not compile; `migrate` re-binds each obligation to the spec its own approved contract
compiles to now. The contracts, approvals, requirements and facts are untouched — nothing is re-approved, because the
contract semantics an approval binds did not change. An obligation whose spec no known release compiles from one of
the bundle's approved contracts is refused, never guessed. The input is never written."""

from __future__ import annotations

import argparse
import dataclasses
import json
import pathlib
import re
import shlex
import sys
from typing import Mapping

from aisef2.app import bundle as B
from aisef2.app import lineage
from aisef2.arch.enums import ObligationRole, Polarity, SubjectAbsence, SubjectKind
from aisef2.plan.obligation import EXPECTED_AT_PARENT, NOT_PREREGISTERED, Plan, PlanObligation
from aisef2.probe import catalog
from aisef2.probe.calibration import calibration_for, executing
from aisef2.product.approval import ContractApproval, Requirement, binding_problems
from aisef2.product.compiler import COMPILER_DIGEST, COMPILER_ID, ProbeRef, compile_spec, expectation_for
from aisef2.product.contract import BehaviorContract, Subject, plain
from aisef2.product.spec import ProductProofSpec

AUTHORING_FORMAT = "aisef-v2-authoring/1"
AUTHORING_KEYS = ("format", "name", "description", "requirements_document", "product_roots", "baseline", "requirements",
                  "contracts", "stories")
CONTRACT_KEYS = ("id", "requirement_ids", "subject", "stimulus", "observable", "polarity", "subject_absence", "rationale")
CRITERION_KEYS = ("id", "contract", "role", "depends_on", "why", "facts")
EXAMPLES = pathlib.Path(__file__).resolve().parent / "examples"      # <name>.json: {readme, authoring, repo: {path: text}}

#: what each earlier release compiled specs under: its active probes' digests and its compiler digest (2.0.0 =
#: tag v2.0.0 at ca26313: the source digests its shipped calibrations name; the compiler is unchanged since)
RELEASES: Mapping[str, dict] = {
    "2.0.0": {"compiler_digest": "f31a4602a61d412d834890f46dcc9ca4d0ce240a106a4772dc9a1e8e7fb8ea76",
              "probes": {SubjectKind.FILE_ARTIFACT: ("probe.file_artifact", "31465b73cbe2440e0e9f6b418665b6f4b1682ee7da2b8968357709daea5e5901"),
                         SubjectKind.PYTHON_CALLABLE: ("probe.python_callable_v2", "b1f25878d350b7848caddd8be01f09da63066876d5b3adb71af61ed9d874b3ae"),
                         SubjectKind.CLI_INVOCATION: ("probe.cli_invocation", "d42449fd8e3ac428758b78d2136e3f2280c2c97223385cdd4d87ec5885572f3f"),
                         SubjectKind.PROCESS_EFFECT: ("probe.process_effect", "815e4c865274d43a7c0467e3af3fbceb67f9086a84eb8f3d2074e43ac16f9273")}},
}


class MigrationError(B.BundleError):
    """The bundle cannot be re-bound: what it names is not what any known release compiled from its contracts."""


class JournalRefused(B.BundleError):
    """A continuation refused for what the run's evidence is. `code` names which failure (module docstring) and the text
    says what it is and what the operator does; it is raised before anything is written."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


#: what `format3.reconstruct` says (aisef2/journal/event.decode, format3.validate) when the chain or the sequence of
#: a journal is broken: the journal is not the one that was written. Every other refusal of the reader is its form.
_INTEGRITY = ("the chain does not link", "seq == index")


def _earlier(spec: ProductProofSpec, release: dict) -> str | None:
    """The id `spec`'s contract compiled to under `release`, or None (no probe of that release for its kind)."""
    kind = SubjectKind(spec.probe_input["subject"]["kind"])
    ref = release["probes"].get(kind)
    if ref is None:
        return None
    return ProductProofSpec.create(contract_id=spec.contract_id, probe_id=ref[0], probe_digest=ref[1],
                                   probe_input=spec.probe_input, candidate_expectation=spec.candidate_expectation,
                                   compiler_id=spec.compiler_id, compiler_digest=release["compiler_digest"]).id


def migrate(data: Mapping) -> tuple[dict, dict]:
    """(the re-bound bundle, the report). Refuses a bundle whose shape does not hold or whose plan names a spec that no
    known release compiles from one of its approved contracts."""
    if not isinstance(data, Mapping) or data.get("format") != B.FORMAT:
        raise MigrationError(f"not a project bundle of format {B.FORMAT}")
    B.shape_problems(data)
    try:
        requirements = {r["id"]: Requirement(**r) for r in data["requirements"]}
        contracts = [BehaviorContract.from_json(c) for c in data["contracts"]]
        approvals = tuple(ContractApproval(**a) for a in data["approvals"])
        plan = B._plan(data["plan"])
    except (KeyError, TypeError, ValueError) as e:
        raise MigrationError(f"the bundle's kernel objects do not load: {type(e).__name__}: {e}") from e
    refs = {kind: ProbeRef(e.probe_id, e.probe_digest) for kind, e in catalog.active().items()}
    current: dict[str, ProductProofSpec] = {}
    for c in contracts:
        try:
            current[c.id] = compile_spec(c, requirements=requirements, approvals=approvals, probes=refs)
        except ValueError as e:
            raise MigrationError(f"contract {c.id} does not compile: {e}") from e
    now = {s.id: s.id for s in current.values()}
    known = dict(now)
    origin = {s.id: "current" for s in current.values()}
    for name, release in RELEASES.items():
        for s in current.values():
            old = _earlier(s, release)
            if old is not None and old not in known:
                known[old], origin[old] = s.id, name
    obligations, mapped, unknown = [], {}, []
    for o in plan.obligations:
        new = known.get(o.product_proof_spec_id)
        if new is None:
            unknown.append(o.criterion_id)
            continue
        if new != o.product_proof_spec_id:
            mapped[o.product_proof_spec_id] = {"to": new, "from_release": origin[o.product_proof_spec_id]}
        obligations.append(dataclasses.replace(o, product_proof_spec_id=new))
    if unknown:
        raise MigrationError(f"{len(unknown)} obligation(s) name a spec no known release ({', '.join(RELEASES)} or this "
                             f"one) compiles from the bundle's approved contracts: {unknown[:5]}")
    new_plan = Plan.create(id=plan.id, baseline=plan.baseline, obligations=tuple(obligations),
                           plan_quality_policy=plan.plan_quality_policy)
    out = {**dict(data), "plan": plain(new_plan)}
    B.load(out)     # the result loads, every seal re-checked, under this release's probes
    report = {"specs_rebound": len(mapped), "obligations": len(obligations), "mapping": mapped,
              "plan_hash": {"from": plan.plan_hash, "to": new_plan.plan_hash},
              "unchanged": ["requirements", "contracts", "approvals", "facts", "stories", "requirements_document"]}
    return out, report


def _mint(contract: BehaviorContract, ref: ProbeRef, compiler_digest: str = COMPILER_DIGEST) -> ProductProofSpec:
    """The spec `contract` compiles to under `ref`: compile_spec's mapping, without its approval gate — the ids the
    tools name, and the review reproducer review_verify runs (never approved, never in a plan); `B.load` compiles every
    plan spec again through compile_spec, so a drift between the two is refused at load."""
    return ProductProofSpec.create(
        contract_id=contract.id, probe_id=ref.probe_id, probe_digest=ref.probe_digest,
        probe_input={"subject": {"kind": contract.subject.kind.value, "locator": contract.subject.locator},
                     "stimulus": contract.stimulus, "observable": contract.observable,
                     "subject_absence": contract.subject_absence.value},
        candidate_expectation=expectation_for(contract.polarity), compiler_id=COMPILER_ID, compiler_digest=compiler_digest)


def _refs() -> dict:
    return {kind: ProbeRef(e.probe_id, e.probe_digest) for kind, e in catalog.active().items()}


def _shell_word(path: pathlib.Path | str, *, windows: bool = sys.platform == "win32") -> str:
    """`path` as one word of the command line the operator pastes: as it is when their shell takes it so, else quoted —
    single quotes on POSIX, double quotes on Windows around a path that holds whitespace (a Windows path holds no `"`)."""
    text = str(path)
    if windows:
        return f'"{text}"' if any(c.isspace() for c in text) else text
    # shlex.quote's safe set is ASCII-only, and a path of letters of any script needs no quoting: judge it as `a`s
    masked = "".join("a" if c.isalnum() else c for c in text)
    return text if shlex.quote(masked) == masked else shlex.quote(text)


def _closed(obj, keys: tuple[str, ...], where: str) -> None:
    if not isinstance(obj, Mapping) or sorted(obj) != sorted(keys):
        held = sorted(obj) if isinstance(obj, Mapping) else type(obj).__name__
        raise B.BundleError(f"{where}: an object of exactly {list(keys)} (it holds {held})")


def seal(authoring: Mapping, *, repo: pathlib.Path | None = None, approvals=()) -> tuple[dict, dict]:
    """(the sealed bundle, the report): every hash and spec id derived from the authoring document by the kernel's own
    constructors; `approvals` (a bundle's) kept when they still bind both hashes, the others named as dropped.
    The baseline "HEAD" and the requirements document's sha256 are read from `repo`."""
    _closed(authoring, AUTHORING_KEYS, "$")
    if authoring["format"] != AUTHORING_FORMAT:
        raise B.BundleError(f"$.format: {AUTHORING_FORMAT}")
    from aisef2.app import run as R
    baseline = authoring["baseline"]
    if baseline == "HEAD":
        if repo is None:
            raise B.BundleError("$.baseline: HEAD is resolved in --repo, and none was given")
        head = R.git(repo, "rev-parse", "--verify", "HEAD^{commit}")
        if head.returncode != 0:
            raise B.BundleError(f"{repo}: not a git repository with a commit ({head.stderr.strip()[:200]})")
        baseline = head.stdout.strip()
    doc = authoring["requirements_document"]
    if not isinstance(doc, Mapping) or not isinstance(doc.get("path"), str) or set(doc) - {"path", "sha256"}:
        raise B.BundleError("$.requirements_document: an object of path and, without --repo, its sha256")
    sha = doc.get("sha256")
    if repo is not None:
        blob = R.git(repo, "cat-file", "blob", f"{baseline}:{doc['path']}")
        if blob.returncode != 0:
            raise B.BundleError(f"$.requirements_document.path: {doc['path']} is not in {repo} at {baseline[:12]}")
        sha = R._sha(blob.stdout.encode("utf-8"))      # exactly as the run checks it (run.check_repository)
    try:
        requirements = [Requirement.create(**r) for r in authoring["requirements"]]
        contracts = []
        for n, c in enumerate(authoring["contracts"]):
            _closed(c, CONTRACT_KEYS, f"$.contracts[{n}]")
            contracts.append(BehaviorContract.create(
                id=c["id"], requirement_ids=tuple(c["requirement_ids"]),
                subject=Subject(SubjectKind(c["subject"]["kind"]), c["subject"]["locator"]),
                stimulus=c["stimulus"], observable=c["observable"], polarity=Polarity(c["polarity"]),
                subject_absence=SubjectAbsence(c["subject_absence"]), rationale=c["rationale"]))
    except (KeyError, TypeError, ValueError) as e:
        raise B.BundleError(f"a requirement or contract does not hold: {type(e).__name__}: {e}") from e
    by_id = {c.id: c for c in contracts}
    refs = _refs()
    obligations, facts, stories = [], {}, {}
    if not isinstance(authoring["stories"], Mapping) or not authoring["stories"]:
        raise B.BundleError("$.stories: an object of story id -> {depends_on, tests, criteria}")
    for sid, s in authoring["stories"].items():
        _closed(s, ("depends_on", "tests", "criteria"), f"$.stories.{sid}")
        stories[sid] = {"depends_on": s["depends_on"], "tests": s["tests"]}
        for n, cr in enumerate(s["criteria"]):
            where = f"$.stories.{sid}.criteria[{n}]"
            _closed(cr, CRITERION_KEYS, where)
            contract = by_id.get(cr["contract"])
            if contract is None:
                raise B.BundleError(f"{where}.contract: {cr['contract']!r} is not a contract of the document")
            ref = refs.get(contract.subject.kind)
            if ref is None:
                raise B.BundleError(f"{where}: no active probe observes {contract.subject.kind.value}")
            try:
                role = ObligationRole(cr["role"])
                obligations.append(PlanObligation(cr["id"], _mint(contract, ref).id, sid, role, EXPECTED_AT_PARENT[role],
                                                  tuple(cr["depends_on"]), cr["why"]))
            except (KeyError, TypeError, ValueError) as e:
                raise B.BundleError(f"{where}: {type(e).__name__}: {e}") from e
            facts[cr["id"]] = cr["facts"]
    try:
        plan = Plan.create(id=f"PLAN-{authoring['name']}", baseline=baseline, obligations=tuple(obligations),
                           plan_quality_policy=NOT_PREREGISTERED)
    except ValueError as e:
        raise B.BundleError(f"the plan does not hold: {e}") from e
    reqs = {r.id: r for r in requirements}
    kept, dropped = [], []
    for a in approvals:
        try:
            ap = ContractApproval(**a)
        except (TypeError, ValueError) as e:
            raise B.BundleError(f"an approval to keep does not load: {e}") from e
        c, r = by_id.get(ap.contract_id), reqs.get(ap.requirement_id)
        (kept if c is not None and r is not None and not binding_problems(ap, r, c) else dropped).append(ap)
    bundle = B.dump(name=authoring["name"], description=authoring["description"], requirements_path=doc["path"],
                    requirements_sha256=sha or "", product_roots=authoring["product_roots"], requirements=requirements,
                    contracts=contracts, approvals=kept, plan=plan, facts=facts, stories=stories)
    B.shape_problems(bundle)
    return bundle, {"plan_hash": plan.plan_hash, "specs": len({o.product_proof_spec_id for o in obligations}),
                    "approvals_kept": len(kept), "approvals_dropped": [f"{a.contract_id}/{a.requirement_id}" for a in dropped],
                    "to_approve": unapproved(bundle)}


def unapproved(bundle: Mapping) -> list[dict]:
    """Each (contract, requirement it cites) no approval of the bundle binds, with the two hashes an approval binds."""
    reqs = {r["id"]: Requirement(**r) for r in bundle["requirements"]}
    approvals = [ContractApproval(**a) for a in bundle["approvals"]]
    out = []
    for c in (BehaviorContract.from_json(x) for x in bundle["contracts"]):
        for rid in c.requirement_ids:
            r = reqs.get(rid)
            if r is None or not any(not binding_problems(a, r, c) for a in approvals):
                out.append({"contract": c.id, "requirement": rid, "contract_hash": c.contract_hash,
                            "requirement_hash": r.requirement_hash if r else None})
    return out


def approve(bundle: Mapping, contract_id: str, approver: str, at: float) -> dict:
    """The bundle with `approver`'s approval of `contract_id` against every requirement it cites (already binding
    ones are not repeated). The kernel's ContractApproval refuses an approver that is not `human:<name>`."""
    B.shape_problems(bundle)
    c = next((BehaviorContract.from_json(x) for x in bundle["contracts"] if x["id"] == contract_id), None)
    if c is None:
        raise B.BundleError(f"no contract {contract_id!r} in the bundle")
    reqs = {r["id"]: Requirement(**r) for r in bundle["requirements"]}
    have = [ContractApproval(**a) for a in bundle["approvals"]]
    new = []
    for rid in c.requirement_ids:
        if rid not in reqs:
            raise B.BundleError(f"{contract_id} cites {rid}, which is not a requirement of the bundle")
        if not any(not binding_problems(a, reqs[rid], c) for a in have):
            try:
                new.append(plain(ContractApproval(rid, reqs[rid].requirement_hash, c.id, c.contract_hash, approver, at, ())))
            except ValueError as e:
                raise B.BundleError(str(e)) from e
    return {**dict(bundle), "approvals": [*bundle["approvals"], *new]}


def _spec_rows(bundle: Mapping) -> dict[str, dict]:
    """criterion -> what the plan's obligation proves, compiled without the approval gate (ids only)."""
    contracts = {c["id"]: BehaviorContract.from_json(c) for c in bundle["contracts"]}
    refs, registry, cals = _refs(), catalog.registry(), None
    from aisef2.app import run as R
    cals = R.calibrations()
    spec_contract = {_mint(c, refs[c.subject.kind]).id: c for c in contracts.values() if c.subject.kind in refs}
    rows = {}
    for o in B._plan(bundle["plan"]).obligations:
        c = spec_contract.get(o.product_proof_spec_id)
        row = {"story": o.story_id, "role": o.role.value, "spec": o.product_proof_spec_id, "contract": c and c.id}
        if c is not None:
            spec = _mint(c, refs[c.subject.kind])
            probe = next(e for e in catalog.CATALOG if e.active and e.probe_id == spec.probe_id)
            cls = registry.observation_class(spec.probe_id, spec.probe_digest, spec)
            row |= {"probe": spec.probe_id, "class": cls, "polarity": c.polarity.value,
                    "subject": f"{c.subject.kind.value} {c.subject.locator}",
                    "calibrated": cls is not None and calibration_for(cals, probe.probe_id, executing(probe.factory), cls) is not None}
        rows[o.criterion_id] = row
    return rows


def coverage(bundle: Mapping) -> dict:
    """Per requirement: the clauses the plan's criteria declare (facts.clause) and the criteria; a requirement no
    criterion covers is UNCOVERED. Only the clauses an author declared are known here: a clause never written into a
    criterion's facts is not seen, and the report says so."""
    by_req: dict[str, dict] = {r["id"]: {"clauses": [], "criteria": []} for r in bundle["requirements"]}
    stray = []
    for cid, f in bundle["facts"].items():
        try:
            rec = by_req.get(f.get("requirement"))
        except TypeError:      # a list or an object: no requirement id, so a criterion citing none of the bundle's
            rec = None
        if rec is None:
            stray.append(cid)
            continue
        rec["criteria"].append(cid)
        rec["clauses"].append((f.get("clause"), cid))

    def by_clause(declared: list) -> dict:
        """clause -> criteria. Every clause of a bundle that loads is a string; one that is not (a missing one beside
        "1.1", a number, a list: `load` refuses it and lint says so) must not make this report unprintable, so it is
        keyed as it is while the keys hash and order (json.dumps(sort_keys=True) orders them), else by its JSON text."""
        out: dict = {}
        try:
            for clause, cid in declared:
                out.setdefault(clause, []).append(cid)
            sorted(out)
        except TypeError:
            out = {}
            for clause, cid in declared:
                out.setdefault(clause if isinstance(clause, str) else json.dumps(clause, sort_keys=True, default=str),
                               []).append(cid)
        return out

    return {"requirements": {rid: {"status": "COVERED" if v["criteria"] else "UNCOVERED",
                                   "clauses": by_clause(v["clauses"]), "criteria": v["criteria"]}
                             for rid, v in by_req.items()},
            "criteria_citing_no_requirement_of_the_bundle": stray,
            "limit": "clauses are the ones the criteria's facts declare; AISEF does not parse the requirements document"}


def lint(bundle: Mapping) -> dict:
    """READY when every contract is approved, the plan is admitted (the nine static checks, with this release's
    calibrations) and every requirement is covered; otherwise NOT_READY and why."""
    B.shape_problems(bundle)
    out = {"to_approve": unapproved(bundle), "coverage": coverage(bundle)}
    rows = _spec_rows(bundle)
    out["criteria_without_calibration"] = sorted(c for c, r in rows.items() if r.get("calibrated") is False)
    out["criteria_without_contract"] = sorted(c for c, r in rows.items() if r["contract"] is None)
    if out["to_approve"]:
        out["admission"] = "not run: an unapproved contract does not compile (approve it, then lint again)"
    else:
        from aisef2.app import run as R
        try:
            out["admission"] = R.admit(B.load(bundle), R.calibrations())
        except B.BundleError as e:
            out["admission"] = {"admitted": False, "failed": [{"check": "load", "problems": [str(e)]}]}
    uncovered = [r for r, v in out["coverage"]["requirements"].items() if v["status"] == "UNCOVERED"]
    ready = (not out["to_approve"] and isinstance(out["admission"], dict) and out["admission"]["admitted"]
             and not uncovered and not out["coverage"]["criteria_citing_no_requirement_of_the_bundle"])
    return {"verdict": "READY" if ready else "NOT_READY", **out}


def explain(bundle: Mapping) -> dict:
    """Per story, in plan order: each criterion with its role, requirement clause, contract, probe, class, polarity,
    whether its class is calibrated at the bytes that run and whether its contract is approved — `approved` is null
    for a criterion with no contract (its obligation names a spec none of the bundle's contracts compiles to): there is
    none to be approved, `lint` lists it in `criteria_without_contract`, and no `approve` could name it."""
    B.shape_problems(bundle)
    pending = {x["contract"] for x in unapproved(bundle)}
    rows = _spec_rows(bundle)
    out: dict[str, list] = {}
    for cid, row in rows.items():
        f = bundle["facts"].get(cid, {})
        out.setdefault(row["story"], []).append({"criterion": cid, **{k: v for k, v in row.items() if k != "story"},
                                                 "requirement": f.get("requirement"), "clause": f.get("clause"),
                                                 "clause_text": f.get("clause_text"),
                                                 "approved": None if row["contract"] is None else row["contract"] not in pending})
    return {"project": bundle["name"], "stories": out}


def init(example: str, out: pathlib.Path) -> None:
    """`example`'s authoring document at out/authoring.json and its repository's files under out/repo/ (a new
    directory: the operator makes it a git repository and commits it — the baseline `seal` reads)."""
    doc = _read(EXAMPLES / f"{example}.json")
    try:
        out.mkdir(parents=True)
    except FileExistsError:
        raise B.BundleError(f"{out} exists: init writes a new directory and never into one") from None
    for rel, text in doc["repo"].items():
        (out / "repo" / rel).parent.mkdir(parents=True, exist_ok=True)
        _create(out / "repo" / rel, text)
    _write_new(out / "authoring.json", doc["authoring"])


def _record(run_dir: pathlib.Path) -> tuple[dict, bool]:
    """(the run's record, whether it is RUN.json). A run killed before its record has only RUN.started.json (V2.1);
    a record that is not there, or that does not parse (a kill during its write), is the next best evidence. One that
    is there and cannot be read is not: it is refused (`EVIDENCE_UNREADABLE`), never demoted to the weaker record —
    which binds no journal digest. One that is not text is damage (the kernel writes ASCII; a kill cuts, never garbles):
    `EVIDENCE_MALFORMED`, never a record that "does not parse"."""
    from aisef2.app import run as R
    cut = []
    for name, recorded in (("RUN.json", True), (R.STARTED, False)):
        try:
            rec = json.loads((run_dir / name).read_text(encoding="utf-8"))
        except UnicodeDecodeError as e:
            raise JournalRefused("EVIDENCE_MALFORMED", f"{run_dir}: no run record — {run_dir / name} is not text "
                                 f"({e.reason}): it is damage, not a write a kill cut; restore it from a faithful copy "
                                 "of the run directory (or, if it is to be given up, remove it: the run is then "
                                 "continued from what it still names) — nothing was written") from None
        except OSError as e:
            if lineage.not_there(e):
                continue
            raise JournalRefused("EVIDENCE_UNREADABLE", f"{run_dir / name} cannot be read ({type(e).__name__}: "
                                 f"{e.strerror or e}): restore read access to it (or a faithful copy of the run "
                                 "directory) and run the command again — the run is never modified and nothing was "
                                 "written") from None
        except ValueError:
            cut.append(name)
            continue
        if not isinstance(rec, dict):     # valid JSON that is no record is damage, not a kill during a write
            raise JournalRefused("EVIDENCE_MALFORMED", f"{run_dir / name} is not a run record (a JSON object): restore "
                                 "it from a faithful copy of the run directory — nothing was written")
        if not recorded:    # V2.1: a run killed before its record still names its identities
            rec["journal"] = {"path": "run/journals/aisef-run.jsonl"}
        return rec, recorded
    if cut:
        raise JournalRefused("EVIDENCE_MALFORMED", f"{run_dir}: no run record ({' and '.join(cut)} cut: not JSON) — "
                             "nothing identifies the run; run the bundle itself again")
    raise JournalRefused("EVIDENCE_MISSING", f"{run_dir}: no run record (neither RUN.json nor {R.STARTED} is there) — "
                         "nothing identifies the run; run the bundle itself again")


def _authentic(run_dir: pathlib.Path, expect: str) -> None:
    """`--verify`'s `--expect-anchor`, applied to a continuation: the anchor of the manifest the run wrote is the one the
    operator kept outside the run directory, and the manifest is what the directory holds."""
    from aisef2.app import run as R
    try:
        stored = json.loads((run_dir / R.MANIFEST).read_text(encoding="utf-8"))
    except OSError as e:
        if lineage.not_there(e):
            raise JournalRefused("EVIDENCE_MISSING", f"{run_dir} has no {R.MANIFEST}: nothing binds its evidence to an "
                                 f"anchor, so the expected anchor {expect[:12]} cannot be checked — a run killed before "
                                 "its record has none; without --expect-anchor a continuation proves consistency only"
                                 ) from None
        raise JournalRefused("EVIDENCE_UNREADABLE", f"{run_dir / R.MANIFEST} cannot be read ({type(e).__name__}: "
                             f"{e.strerror or e}): restore read access to it and run the command again") from None
    except ValueError:
        stored = None
    if not isinstance(stored, dict) or not isinstance(stored.get("files", {}), dict):
        raise JournalRefused("EVIDENCE_MISMATCH", f"{run_dir / R.MANIFEST} is not an evidence manifest: the expected "
                             f"anchor {expect[:12]} cannot be reproduced from it")
    anchor = R.anchor_of(stored)
    if anchor != expect:
        raise JournalRefused("EVIDENCE_MISMATCH", f"{run_dir}: the evidence anchor is {anchor[:12]}, not the "
                             f"{expect[:12]} expected: this is not the run that printed it, or its evidence was "
                             "rewritten")
    try:
        fresh = R.evidence_manifest(run_dir)
    except OSError as e:
        raise JournalRefused("EVIDENCE_UNREADABLE", f"{run_dir}: an evidence file cannot be read ({type(e).__name__}): "
                             f"{e.filename}") from None
    if stored != fresh:
        changed = sorted(k for k in set(stored.get("files", {})) | set(fresh["files"])
                         if stored.get("files", {}).get(k) != fresh["files"].get(k))
        raise JournalRefused("EVIDENCE_MISMATCH", f"{run_dir}: the evidence manifest does not match the run directory: "
                             f"{changed[:5]} — evidence was changed after the run wrote it")


def _journal(run_dir: pathlib.Path, rec: dict, recorded: bool):
    """The run's journal (a `format3.Journal`), under the rule of `aisef run --verify` (module docstring): read, the
    digest and length RUN.json names, reconstructed, and no control projection refuses it — the verifier's own
    `_projection_refusal`. A torn last line is returned as the reader gives it (`torn_tail`): the approved policy."""
    from aisef2.app import run as R
    from aisef2.app.verify import _projection_refusal
    from aisef2.journal import format3
    j = rec.get("journal")
    path = j.get("path") if isinstance(j, dict) else None
    if not isinstance(path, str) or not path:
        raise JournalRefused("EVIDENCE_MISSING", f"{run_dir}: the record names no journal (the run ended before it "
                             "began): there is nothing to continue from — run the bundle itself again")
    where = run_dir / path
    try:
        data = where.read_bytes()
    except OSError as e:
        raise JournalRefused("EVIDENCE_UNREADABLE", f"{where} cannot be read ({type(e).__name__}: {e.strerror or e}): "
                             "restore read access to it, or the journal from a faithful copy of the run directory, and "
                             "run the command again — the run is never modified and nothing was written") from None
    if recorded and (R._sha(data) != j.get("sha256") or data.count(b"\n") != j.get("lines")):
        raise JournalRefused("EVIDENCE_INTEGRITY", f"{where} is not the journal {run_dir / 'RUN.json'} names (its digest "
                             "or length differs): it was changed or replaced after the run ended — restore it from a "
                             "faithful copy; `aisef run --verify` on the run refuses it the same way")
    try:
        journal = format3.reconstruct(data.decode("utf-8"))
    except Exception as e:  # noqa: BLE001 — each refusal of the reader is a class of failure, told apart
        broken = any(m in str(e) for m in _INTEGRITY)
        raise JournalRefused(
            "EVIDENCE_INTEGRITY" if broken else "EVIDENCE_MALFORMED",
            f"{where}: {type(e).__name__}: {e}"[:400] + (
                " — its hash chain or sequence is broken: the journal is not the one that was written; restore it "
                "from a faithful copy" if broken else
                " — what is there is not a journal this reader accepts (damage, another format, another kernel's "
                "events); restore it from a faithful copy, or run the bundle itself again")) from None
    refused = _projection_refusal(journal.events)
    if refused is not None:
        pid, kind, seq, why = refused
        raise JournalRefused("EVIDENCE_PROJECTION", f"{where} violates the control projections the kernel's writer "
                             f"enforces: {pid} refuses {kind} at seq {seq}: {why}"[:480] +
                             " — no kernel wrote it, and nothing is carried from it; `aisef run --verify` refuses it "
                             "the same way")
    return journal


def continue_from(data: Mapping, run_dir: pathlib.Path, *, leave_out_unidentified: bool = False,
                  expect_anchor: str | None = None) -> tuple[dict, dict]:
    """(the continuation bundle, the report) of `data`'s run in `run_dir` (module docstring). What the run did that its
    journal does not confirm is reconciled against git and the journal's operation identities (app/lineage); a commit
    on main nothing identifies is refused unless `leave_out_unidentified` (the report names it either way).
    `expect_anchor`: the evidence anchor the run printed (as `--verify --expect-anchor`), checked before anything of
    the run is read."""
    from aisef2.app import run as R
    project = B.load(data)
    try:
        child, state = lineage.continued_by(run_dir)
    except lineage.LineageRefused as e:     # the run's claims cannot be listed: a refusal, not "no claims"
        raise JournalRefused("EVIDENCE_UNREADABLE", str(e)) from None
    if state == lineage.BEGUN:
        raise B.BundleError(f"{run_dir} is already continued by {child}, which began: continue the lineage from it")
    held = None
    if child == lineage.UNREADABLE_CLAIM:   # the claim cannot be read: whose child it is, is not known — UNREAD, with why
        held = {"run": child, "state": lineage.UNREAD, "why": lineage.claim_unread(run_dir)}
    elif child:
        held = {"run": child, "state": state,
                **({"why": lineage.child_evidence(pathlib.Path(child))[1]} if state == lineage.UNREAD else {})}
    if expect_anchor is not None:
        _authentic(run_dir, expect_anchor)
    rec, recorded = _record(run_dir)
    if rec.get("bundle_digest") != project.digest:
        raise B.BundleError(f"{run_dir} is a run of another bundle: a continuation is of the same project")
    if rec.get("kernel_digest") != R.kernel_digest():
        raise B.BundleError(f"{run_dir} ran another kernel ({str(rec.get('kernel_digest'))[:12]}): a new project, "
                            "not a continuation")
    journal = _journal(run_dir, rec, recorded)
    events = journal.events
    commits = [(e.data["story_id"], e.data["revision"]) for e in events if e.type == "story/commit"]
    if not commits:
        raise JournalRefused("EVIDENCE_MISSING", f"{run_dir} committed no story: run the bundle itself again")
    done = [s for s, _ in commits]
    baseline = commits[-1][1]
    repo = run_dir / "repo"
    if R.git(repo, "cat-file", "-e", f"{baseline}^{{commit}}").returncode != 0:
        raise B.BundleError(f"{repo} does not hold the journal's last commit {baseline[:12]}")
    reconciled = lineage.reconcile(run_dir, list(events), baseline, bool(journal.torn_tail))
    if reconciled["unidentified"] and not leave_out_unidentified:
        raise B.BundleError(f"{run_dir}: what the journal does not confirm includes commits nothing identifies — "
                            f"{[(i['commit'][:12], i['why']) for i in reconciled['unidentified']][:5]}; inspect them, then "
                            "--leave-out-unidentified to continue without them")
    blob = R.git(repo, "cat-file", "blob", f"{baseline}:{project.requirements_path}")
    if blob.returncode != 0 or R._sha(blob.stdout.encode("utf-8")) != project.requirements_sha256:
        raise B.BundleError(f"the requirements document at {baseline[:12]} is not the bundle's: a new project")
    carried = "CARRIED"
    while carried in project.stories:
        carried += "_"
    plan = project.plan
    anchor = R.anchor_in(run_dir)
    obligations = []
    for o in plan.obligations:
        if o.story_id in done:
            obligations.append(PlanObligation(o.criterion_id, o.product_proof_spec_id, carried, ObligationRole.VERIFY,
                                              EXPECTED_AT_PARENT[ObligationRole.VERIFY], o.depends_on,
                                              f"carried: {o.story_id} committed it in the run anchored "
                                              f"{anchor[:16] if anchor else 'without a manifest'} ({o.criterion_id})"))
        else:
            obligations.append(o)
    new_plan = Plan.create(id=f"{plan.id}-continued", baseline=baseline, obligations=tuple(obligations),
                           plan_quality_policy=plan.plan_quality_policy)
    stories = {carried: {"depends_on": [], "tests": sorted({t for s in done for t in project.stories[s]["tests"]})}}
    for sid, s in project.stories.items():
        if sid not in done:
            deps = list(dict.fromkeys(carried if d in done else d for d in s["depends_on"]))
            stories[sid] = {"depends_on": deps, "tests": list(s["tests"])}
    out = {**dict(data), "plan": plain(new_plan), "stories": stories,
           "description": f"{data['description']} — continued from the run anchored {anchor or '(no manifest)'}"}
    B.load(out)
    account = lineage.lineage_account(run_dir)      # the lineage ending at the run, as `aisef run --parent` will account it
    report = {"carried": done, "carried_as": carried, "baseline": baseline, "run": str(run_dir), "evidence_anchor": anchor,
              "recorded": recorded, "anchor_checked": expect_anchor is not None,
              "already_continued_by": held,
              # a torn last line is the reader's verified prefix; the torn event's EFFECTS are not assumed undone —
              # they are among `unconfirmed`, reconciled against git (app/lineage)
              "torn_tail": bool(journal.torn_tail), "cut_event": reconciled["cut_event"],
              "unconfirmed": reconciled["items"], "left_out_unidentified": bool(reconciled["unidentified"]),
              # what the lineage's readable parts spent (`known`), which run spent it, and the lineage's `total` — None
              # while anything is not known; `unread` is what `aisef run --parent` is refused on, whatever flag
              "spend": {"known": {k: account[k] for k in lineage.SPEND}, "total": account["total"]},
              "spend_by_run": [{k: r[k] for k in ("run", *lineage.SPEND, "unaccounted", "recorded")} |
                               ({"superseded": True} if r.get("superseded") else {}) for r in account["runs"]],
              "unaccounted": account["unaccounted"], "unread": account["unread"],
              "run_parent_refused": None if not account["unread"] else
              "evidence of the lineage is there and cannot be read, so what it spent is not known (not 0): `aisef run "
              "--parent` starts no paid work (no flag accepts it) until it is readable again — its permissions, or a "
              "faithful copy of the run directory at the path named; where that cannot be done this lineage cannot be "
              "continued (a run without --parent inherits nothing): " + "; ".join(account["unread"])[:1000],
              "in_flight": None if not reconciled["items"] else
              f"{len(reconciled['items'])} effect(s) the journal does not confirm are left out of the continuation's "
              f"baseline {baseline[:12]} (each identified in `unconfirmed`); their stories run again",
              "remaining": [s for s in project.stories if s not in done],
              "next": f"aisef run --project <this bundle> --repo {_shell_word(repo)} --parent {_shell_word(run_dir)} "
                      "--settings S --out NEW"}
    return out, report


def _read(path: pathlib.Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as e:
        raise B.BundleError(f"{path}: cannot be read as JSON ({type(e).__name__})") from e


def _create(path: pathlib.Path, text: str) -> None:
    """`text` to a NEW file, created exclusively (O_EXCL): every output of the bundle tools goes through here, so none
    ever writes over a file — not even one created between a check and the write."""
    try:
        with path.open("x", encoding="utf-8") as fh:
            fh.write(text)
    except FileExistsError:
        raise B.BundleError(f"{path} exists: the bundle tools write a new file and never overwrite one") from None


def _write_new(path: pathlib.Path, doc: dict) -> None:
    _create(path, json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="aisef bundle", description="The project bundle's own tools (no run, no provider).")
    sub = p.add_subparsers(dest="command", required=True)
    i = sub.add_parser("init", help="write an example (authoring document + its repository's files) to start from")
    i.add_argument("--example", default="calc-1-story", choices=sorted(p.stem for p in EXAMPLES.glob("*.json")))
    i.add_argument("--out", type=pathlib.Path, required=True, help="a new directory")
    s = sub.add_parser("seal", help="derive every hash and spec id: the bundle, unapproved")
    s.add_argument("authoring", type=pathlib.Path)
    s.add_argument("--repo", type=pathlib.Path, help="the project's repository: HEAD and the requirements document")
    s.add_argument("--keep-approvals-from", type=pathlib.Path, help="an earlier bundle whose still-binding approvals stay")
    s.add_argument("--out", type=pathlib.Path, required=True)
    ap = sub.add_parser("approve", help="approve one contract as a named human")
    ap.add_argument("bundle", type=pathlib.Path)
    ap.add_argument("--contract", required=True)
    ap.add_argument("--approver", required=True, help="human:<name> — the person approving")
    ap.add_argument("--out", type=pathlib.Path, required=True)
    for name, text in (("lint", "approvals, admission, calibration, clause coverage"), ("explain", "each criterion, plainly")):
        sub.add_parser(name, help=text).add_argument("bundle", type=pathlib.Path)
    c = sub.add_parser("continue", help="the stories a run did not commit, from what it did commit")
    c.add_argument("bundle", type=pathlib.Path)
    c.add_argument("--from-run", type=pathlib.Path, required=True)
    c.add_argument("--out", type=pathlib.Path, required=True)
    c.add_argument("--leave-out-unidentified", action="store_true",
                   help="continue although main holds commits no journaled operation identifies (they are left out)")
    c.add_argument("--expect-anchor", metavar="SHA256",
                   help="the evidence anchor the run printed, kept outside the run directory: refused when the run "
                        "cannot show it (without it a continuation proves consistency, not authenticity)")
    m = sub.add_parser("migrate", help="re-bind an earlier release's bundle to this release's spec ids")
    m.add_argument("bundle", type=pathlib.Path)
    m.add_argument("--out", type=pathlib.Path, required=True, help="the migrated bundle (a new file; never the input)")
    a = p.parse_args(argv)
    try:
        if a.command == "init":
            init(a.example, a.out)
            print(json.dumps({"written": str(a.out), "next": _read(EXAMPLES / f"{a.example}.json")["readme"]}, indent=1))
            return 0
        if a.command == "seal":
            keep = _read(a.keep_approvals_from)["approvals"] if a.keep_approvals_from else ()
            doc, report = seal(_read(a.authoring), repo=a.repo, approvals=keep)
            _write_new(a.out, doc)
            print(json.dumps({"written": str(a.out), **report}, indent=1, sort_keys=True))
            return 0
        if a.command == "approve":
            import time
            doc = approve(_read(a.bundle), a.contract, a.approver, time.time())
            _write_new(a.out, doc)
            print(json.dumps({"written": str(a.out), "approved": a.contract, "by": a.approver,
                              "still_to_approve": unapproved(doc)}, indent=1, sort_keys=True))
            return 0
        if a.command == "continue":
            if a.expect_anchor is not None and not re.fullmatch(r"[0-9a-f]{64}", a.expect_anchor):
                p.error("--expect-anchor is the 64-hex evidence anchor the run printed")
            doc, report = continue_from(_read(a.bundle), a.from_run, leave_out_unidentified=a.leave_out_unidentified,
                                        expect_anchor=a.expect_anchor)
            _write_new(a.out, doc)
            print(json.dumps({"written": str(a.out), **report}, indent=1, sort_keys=True))
            return 0
        if a.command in ("lint", "explain"):
            doc = _read(a.bundle)
            if not isinstance(doc, Mapping) or doc.get("format") != B.FORMAT or sorted(doc) != sorted(B.KEYS):
                raise B.BundleError(f"not a project bundle of format {B.FORMAT}")
            report = lint(doc) if a.command == "lint" else explain(doc)
            print(json.dumps(report, indent=1, sort_keys=True, default=str))
            return 0 if a.command == "explain" or report["verdict"] == "READY" else 1
        if a.out.exists():      # refused before any work; the exclusive create below is what guarantees it
            raise MigrationError(f"{a.out} exists: migrate writes a new file and never overwrites one")
        out, report = migrate(_read(a.bundle))
        _create(a.out, json.dumps(out, indent=1, sort_keys=True) + "\n")     # 2.0's bytes (non-ASCII escaped)
    except B.BundleError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    except (KeyError, TypeError, ValueError) as e:     # a document whose kernel objects do not hold
        print(f"refused: {type(e).__name__}: {e}"[:2000], file=sys.stderr)
        return 2
    print(json.dumps({"written": str(a.out), **report}, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
