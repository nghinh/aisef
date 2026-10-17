"""`aisef bundle`: the project bundle's own tools — outside a run, no provider, no repository written.

    aisef bundle init [--example NAME] --out DIR            an example to start from: DIR/authoring.json, DIR/repo/
    aisef bundle seal AUTHORING.json --repo REPO --out B    every hash and spec id computed: the bundle, unapproved
                     [--keep-approvals-from OLD]            (an earlier bundle's approvals that still bind are kept,
                                                             unless their contract's evaluation changed since)
    aisef bundle approve B --contract ID --approver human:NAME --out B2    one contract approved, by its human
    aisef bundle lint B                                     approvals, admission (RFC §12), calibration, clause coverage
    aisef bundle explain B                                  per story: each criterion, its contract, probe and class
    aisef bundle migrate IN --out OUT     a bundle of an earlier release, its plan re-bound to this release's spec ids;
                     the candidate it writes is new and carries only the approvals whose contract still means what it
                     meant (the others are named, with the command that approves each — it signs nothing)
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
compiles to now. The contracts, requirements and facts are untouched. An obligation whose spec no known release
compiles from one of the bundle's approved contracts is refused, never guessed. The input is never written.

An approval binds a contract's hash, and a hash does not change when the probe's capability does. So `migrate` keeps
an approval only while the contract it approved is still evaluated as it was when the owner approved it (owner
decision 2026-10-15, item 1): for each contract whose spec came from an earlier release it reads the capability versions
between that release's (`RELEASES`) and this one's, and the changes each probe declares for them (`CAPABILITY_CHANGES`
in the probe module, copied by the catalog); a change that selects the contract — by its observation class and its
`subject_absence`, derived from the probe, no contract is named — withholds its approvals from the candidate, which is a
new bundle; the input and its approvals stay as they were, as history. A selector sees the contract, never the
repository: it selects every contract that could differ, so a change whose `when` needs a repository condition (a
directory without a .py file, a file that begins with a byte-order mark) selects the contracts that could meet it, and
the report names each change that selected a contract (`semantic_changes[].changes[].ref`) beside the condition. A
capability change nobody declared selects every contract of its probe, and so does a probe that declares no version.
What the rule rests on, and what it cannot see: an approval is kept on the identity rule above (the probe's id, version
and classes are the release's, no declared change selects the contract) — `approvals_kept_grounds` says, for each group
of kept approvals, which versions were read; `migrate` reads declarations and runs no probe, so a change to a probe
made without moving its CAPABILITY_VERSION and declaring it is not seen (`limits`). An approval that no longer binds
its requirement and contract hashes is not carried either. The report says what differs and when (`semantic_changes`),
what the owner must approve again, by which command and signing nothing (`needs_owner_reapproval`: the commands name
the candidate and the files they write, and keep `human:NAME` for the owner to replace — `approve` refuses the
placeholder), and which bundle this is (`candidate`: `bundle_digest` is the canonical digest `load` gives the project,
`file_sha256` the sha256 of the file's bytes). Exit status 0 is a migration performed: the candidate does not load until
its withheld contracts are approved, and `lint` says so (NOT_READY). `seal --keep-approvals-from` applies the same rule
to the approvals it keeps (`approvals_withheld_semantic`); a caller of `seal` that hands it approvals must hand it
`exposed` too (`exposure_of` the bundle they come from), or it refuses. Limit: a bundle an earlier build of `migrate`
already wrote carries its approvals as they were and says nothing of it — migrate again from the original, which is
never modified."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
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

#: what each earlier release compiled specs under: its active probes' (id, digest, capability version) and its compiler
#: digest (2.0.0 = tag v2.0.0 at ca26313: the source digests its shipped calibrations name; the compiler is unchanged
#: since). The capability version is the probe's CAPABILITY_VERSION counted from the release that introduced it:
#: 2.0.0 predates the counter and is version 1 for each probe — the classes it observed are the classes version 1 names
#: (file_artifact: exists, content, grep_count; python_callable_v2, cli_invocation and process_effect as they are).
RELEASES: Mapping[str, dict] = {
    "2.0.0": {"compiler_digest": "f31a4602a61d412d834890f46dcc9ca4d0ce240a106a4772dc9a1e8e7fb8ea76",
              "probes": {SubjectKind.FILE_ARTIFACT: ("probe.file_artifact", "31465b73cbe2440e0e9f6b418665b6f4b1682ee7da2b8968357709daea5e5901", 1),
                         SubjectKind.PYTHON_CALLABLE: ("probe.python_callable_v2", "b1f25878d350b7848caddd8be01f09da63066876d5b3adb71af61ed9d874b3ae", 1),
                         SubjectKind.CLI_INVOCATION: ("probe.cli_invocation", "d42449fd8e3ac428758b78d2136e3f2280c2c97223385cdd4d87ec5885572f3f", 1),
                         SubjectKind.PROCESS_EFFECT: ("probe.process_effect", "815e4c865274d43a7c0467e3af3fbceb67f9086a84eb8f3d2074e43ac16f9273", 1)}},
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


def _known(specs: Mapping[str, ProductProofSpec]) -> tuple[dict[str, str], dict[str, str]]:
    """(spec id -> the id this release compiles it to, spec id -> the release that compiled it) over `specs` (contract id
    -> the spec this release compiles it to): this release's own ids, then each earlier release's in order — an id two
    releases compile keeps the first attribution."""
    known = {s.id: s.id for s in specs.values()}
    origin = {s.id: "current" for s in specs.values()}
    for name, release in RELEASES.items():
        for s in specs.values():
            old = _earlier(s, release)
            if old is not None and old not in known:
                known[old], origin[old] = s.id, name
    return known, origin


def _earliest(names) -> str | None:
    """The earliest of release names (`RELEASES` order, "current" after them all), None for none."""
    order = [*RELEASES, "current"]
    return min(names, key=order.index, default=None)


def _origins(specs: Mapping[str, ProductProofSpec], plan: Plan) -> dict[str, str | None]:
    """contract id -> the release whose spec ids the plan names for it (the earliest, when two): a name of RELEASES, or
    "current". A contract no obligation names takes the bundle's earliest, and None (unknown) when the plan names none
    that a release compiles: a contract nobody evaluates is not known to be approved under this release."""
    known, origin = _known(specs)
    contract_of = {s.id: cid for cid, s in specs.items()}
    named: dict[str, set[str]] = {}
    for o in plan.obligations:
        new = known.get(o.product_proof_spec_id)
        if new is not None:
            named.setdefault(contract_of[new], set()).add(origin[o.product_proof_spec_id])
    bundle_wide = _earliest(n for names in named.values() for n in names)
    return {cid: _earliest(named.get(cid, ())) or bundle_wide for cid in specs}


def _declared(entry, version: int) -> Mapping | None:
    """The record of what capability `version` of `entry`'s probe changed, or None when the probe declares none or one that
    is not well formed (`summary`; `affects`: selectors of `classes` / `subject_absence`, each with `when`, `before`,
    `after`, and optionally a `ref`, the short name a report gives the change). What is not declared is not "nothing
    changed": the caller reads it as changing every contract of the probe — so this is total, whatever the probe's module
    holds: a record it cannot take is None, never an exception."""
    changes = entry.capability_changes
    rec = changes.get(version) if isinstance(changes, Mapping) else None
    if not isinstance(rec, Mapping) or set(rec) != {"summary", "affects"} or not isinstance(rec["summary"], str) \
            or not rec["summary"] or not isinstance(rec["affects"], (tuple, list)):
        return None
    allowed = {"classes": set(entry.classes), "subject_absence": {a.value for a in SubjectAbsence}}

    def well_formed(sel) -> bool:
        if not isinstance(sel, Mapping) or not {"when", "before", "after"} <= set(sel) \
                or not set(sel) <= {"classes", "subject_absence", "when", "before", "after", "ref"}:
            return False
        if not all(isinstance(sel[k], str) and sel[k] for k in ("when", "before", "after", "ref") if k in sel):
            return False
        return all(isinstance(sel[k], (tuple, list)) and sel[k] and all(isinstance(x, str) for x in sel[k])
                   and set(sel[k]) <= allowed[k] for k in allowed if k in sel)

    return rec if all(well_formed(sel) for sel in rec["affects"]) else None


def _assess(contracts: Mapping[str, BehaviorContract], specs: Mapping[str, ProductProofSpec],
            origins: Mapping[str, str | None]) -> dict[str, dict]:
    """contract id -> how it stands against the capability changes of its probe since the release `origins` names for
    it: the probe, the class the probe observes the spec as, the capability versions from and to, `consulted` (each
    version read, with the summary of its record and the number of selectors it declares) and `changes` (the ones that
    select the contract, by that class and its `subject_absence`; empty: by the declarations, it is evaluated as it was).
    A contract the plan names under this release's own ids, or one with no probe, is absent. Fail closed: a version with
    no declared record, a probe that declares no version, or one that is not the release's probe selects every contract
    of it; so does a class the probe cannot name."""
    active, registry, out = catalog.active(), catalog.registry(), {}
    for cid, c in contracts.items():
        name, entry, spec = origins.get(cid), active.get(c.subject.kind), specs.get(cid)
        if name == "current" or entry is None or spec is None:
            continue
        then = RELEASES.get(name, {}).get("probes", {}).get(c.subject.kind) if name else None
        base = then[2] if then else 1
        top = entry.capability_version
        cls = registry.observation_class(spec.probe_id, spec.probe_digest, spec)
        every = {"version": None, "ref": None, "when": "every use of the probe",
                 "before": "as the earlier release evaluated it",
                 "after": "as this release evaluates it: the difference is not declared, so it is not ruled out"}
        consulted: list[dict] = []
        if not isinstance(top, int) or isinstance(top, bool) or top < 1:
            hits = [{**every, "summary": f"{entry.probe_id} declares no capability version"}]
        elif then and then[0] != entry.probe_id:
            hits = [{**every, "summary": f"the release evaluated this contract with {then[0]} and this one with "
                                         f"{entry.probe_id}: their capabilities are not comparable"}]
        else:
            hits = []
            for version in range(base + 1, top + 1):
                rec = _declared(entry, version)
                if rec is None:
                    consulted.append({"version": version, "summary": None, "selectors": None})
                    hits.append({**every, "version": version, "summary": f"{entry.probe_id} capability {version} "
                                 "declares no well formed record of what it changed (CAPABILITY_CHANGES)"})
                    continue
                consulted.append({"version": version, "summary": rec["summary"], "selectors": len(rec["affects"])})
                hits += [{"version": version, "ref": sel.get("ref"), "summary": rec["summary"], "when": sel["when"],
                          "before": sel["before"], "after": sel["after"]} for sel in rec["affects"]
                         if (cls is None or "classes" not in sel or cls in sel["classes"])
                         and ("subject_absence" not in sel or c.subject_absence.value in sel["subject_absence"])]
        out[cid] = {"probe": entry.probe_id, "class": cls, "from": {"release": name, "capability_version": base},
                    "to": {"capability_version": top}, "consulted": consulted, "changes": hits}
    return out


def _selected(assessed: Mapping[str, dict]) -> dict[str, dict]:
    """The contracts of `_assess` that at least one change selects."""
    return {name: how for name, how in assessed.items() if how["changes"]}


def _exposure(contracts: Mapping[str, BehaviorContract], specs: Mapping[str, ProductProofSpec],
              origins: Mapping[str, str | None]) -> dict[str, dict]:
    """contract id -> what makes an approval given under the release `origins` names for it unsafe to carry over: `_assess`
    of the contracts at least one declared (or undeclared) change selects. A contract no change selects is absent."""
    return _selected(_assess(contracts, specs, origins))


def _group(assessed: Mapping[str, dict], contracts: Mapping[str, BehaviorContract], name: str) -> tuple:
    """What makes the grounds of two kept contracts one: the probe, the class, the contract's `subject_absence`, the release
    and the capability versions its approval was read between. A contract `_assess` did not reach is "current"."""
    how = assessed.get(name)
    if how is None:
        return ("current",)
    return (how["probe"], how["class"], contracts[name].subject_absence.value, how["from"]["release"],
            how["from"]["capability_version"], how["to"]["capability_version"])


def _ground(how: Mapping | None, key: tuple) -> dict:
    """The row of `_grounds` for the group `key` whose first contract `_assess` says `how` of."""
    if how is None:
        return {"probe": None, "class": None, "subject_absence": None, "from": {"release": "current"}, "to": None,
                "consulted": [], "ground": "the plan names this release's own spec ids for these contracts: there is no "
                                           "earlier release whose capability to compare"}
    then, now = how["from"]["capability_version"], how["to"]["capability_version"]
    return {"probe": how["probe"], "class": how["class"], "subject_absence": key[2], "from": how["from"], "to": how["to"],
            "consulted": how["consulted"],
            "ground": (f"capability {then} to {now}: {len(how['consulted'])} declared change(s) read, none selects class "
                       f"{how['class']} under {key[2]}" if then != now else
                       f"the probe is at capability {now}, the release's, and no change is declared for it: its version "
                       "did not move, so nothing could be (see `limits`)")}


def _grounds(kept: set[str], assessed: Mapping[str, dict], contracts: Mapping[str, BehaviorContract]) -> list[dict]:
    """The ground for each approval kept, `kept` the ids of the contracts they approve: one row per group read the same
    way (`_group`), the versions consulted among its fields, so that the owner sees what "no change selects it" was read
    from. Pure: it builds rows and changes nothing it is given."""
    keys = {name: _group(assessed, contracts, name) for name in sorted(kept)}
    return [{**_ground(assessed.get(next(n for n in keys if keys[n] == key)), key),
             "contracts": [n for n in keys if keys[n] == key]} for key in dict.fromkeys(keys.values())]


#: what a kept approval rests on, and what the rule cannot see (the report's `limits`)
LIMITS = (
    "A kept approval rests on the identity rule of ARCHITECTURE-EXCEPTION-V2-007: the probe's id, capability version and "
    "classes are the release's and no change declared for the versions between selects the contract. `migrate` reads "
    "those declarations and runs no probe: a change made to a probe's behaviour without moving its CAPABILITY_VERSION and "
    "declaring it in CAPABILITY_CHANGES is not seen, and a contract of such a probe is kept.",
    "A selector sees a contract, never the repository it is evaluated against: a change whose `when` needs a condition of "
    "the repository (an empty selection, a byte-order mark) selects the contracts that could meet it, whether or not the "
    "repository does.",
    "A bundle an earlier build of `migrate` wrote already names this release's spec ids and is read as approved under "
    "this release: migrate again from the original bundle.")


#: what identifies one approval among a bundle's: the contract and the requirement it binds, both hashes, who and when
APPROVAL_KEY = ("contract_id", "requirement_id", "contract_hash", "requirement_hash", "approver", "approved_at")


def _key(a: Mapping) -> tuple:
    return tuple(a[k] for k in APPROVAL_KEY)


def _binds(ap: ContractApproval, requirements: Mapping[str, Requirement], contracts: Mapping[str, BehaviorContract]) -> bool:
    """`ap` binds a requirement and a contract of the bundle at their current hashes (and so is a ground to keep it)."""
    r, c = requirements.get(ap.requirement_id), contracts.get(ap.contract_id)
    return r is not None and c is not None and not binding_problems(ap, r, c)


PLACEHOLDER = "human:NAME"      # the approver a printed command carries for its reader to replace; `approve` refuses it


def with_commands(report: Mapping, out: pathlib.Path | None = None) -> dict:
    """`report` (from `migrate`) with the commands that approve what the owner must approve again, one after the other:
    the first reads the candidate (`out`, the file it is written to; `candidate.json` when none is given), each next the
    file the one before wrote (`<stem>.approved-N<suffix>`, beside it), and `then` lints the last. Words as the operator's
    shell reads them (`_shell_word`); the approver is the one thing left to them. Nothing here signs anything. Kept out of
    `migrate` itself, which prints no command and reaches no shell quoting."""
    todo = report["needs_owner_reapproval"]
    if todo is None:
        return dict(report)
    first = out or pathlib.Path("candidate.json")
    here, rows = first, []
    for n, row in enumerate(todo["contracts"], 1):
        nxt = first.with_name(f"{first.stem}.approved-{n}{first.suffix}")
        rows.append({**row, "reads": str(here), "writes": str(nxt),
                     "command": f"aisef bundle approve {_shell_word(here)} --contract {_shell_word(row['contract'])} "
                                f"--approver {PLACEHOLDER} --out {_shell_word(nxt)}"})
        here = nxt
    return {**report, "needs_owner_reapproval": {
        **todo, "contracts": rows, "then": f"aisef bundle lint {_shell_word(here)}",
        "how": "nothing was signed. Each command writes a new file: the one it reads and one more approval, by the human "
               f"named in --approver, who has read the contract and the change above. Replace {PLACEHOLDER} by `human:` and "
               "your name (`approve` refuses the placeholder); run them in order, each reads what the one before wrote; "
               "`then` lints the last."}}


def migrate(data: Mapping) -> tuple[dict, dict]:
    """(the candidate bundle, the report). Refuses a bundle whose shape does not hold or whose plan names a spec that no
    known release compiles from one of its approved contracts. The candidate is a new bundle: its plan re-bound, and
    its approvals only those that still bind and whose contract no declared capability change evaluates differently
    (module docstring); the input and its approvals are never written. The commands that approve what it withholds are
    `with_commands`'s."""
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
    known, origin = _known(current)
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
    B.load(out)     # the trial: the re-bound plan, with every approval of the input, loads under this release's probes
    by_id = {c.id: c for c in contracts}
    assessed = _assess(by_id, current, _origins(current, plan))
    exposed = _selected(assessed)
    withheld = [(ap, "semantic" if ap.contract_id in exposed else "unbound") for ap in approvals
                if ap.contract_id in exposed or not _binds(ap, requirements, by_id)]
    dropped = {_key(plain(ap)) for ap, _ in withheld}
    candidate = {**out, "approvals": [a for a in data["approvals"] if _key(a) not in dropped]}
    # what the candidate lacks is exactly what was withheld: every contract a change selects, for each requirement it
    # cites, and what the input had unapproved — never less (a kept approval of an affected contract) or more
    lacks = {(r["contract"], r["requirement"]) for r in unapproved(candidate)}
    owed = {(cid, rid) for cid in exposed for rid in by_id[cid].requirement_ids} \
        | {(r["contract"], r["requirement"]) for r in unapproved(data)}
    if lacks != owed or len(candidate["approvals"]) + len(withheld) != len(data["approvals"]):
        raise MigrationError(f"the candidate's unapproved contracts {sorted(lacks ^ owed)[:5]} are not what the withheld "
                             f"approvals account for ({len(withheld)} withheld of {len(data['approvals'])})")
    rows = [{"contract": ap.contract_id, "requirement": ap.requirement_id, "approver": ap.approver,
             "approved_at": ap.approved_at, "contract_hash": ap.contract_hash, "requirement_hash": ap.requirement_hash,
             "why": why} for ap, why in withheld]
    changes = [{"contract": cid, "requirements": list(by_id[cid].requirement_ids),
                **e,
                "subject": f"{by_id[cid].subject.kind.value} {by_id[cid].subject.locator}",
                "subject_absence": by_id[cid].subject_absence.value, "polarity": by_id[cid].polarity.value,
                "observable": by_id[cid].to_json()["observable"], "stimulus": by_id[cid].to_json()["stimulus"],
                "approvals_in_input": [r for r in rows if r["contract"] == cid]} for cid, e in sorted(exposed.items())]
    reapprove = [{"contract": cid, "requirements": list(by_id[cid].requirement_ids),
                  "contract_hash": by_id[cid].contract_hash} for cid in sorted(exposed)]
    kept = {ap["contract_id"] for ap in candidate["approvals"]}
    report = {"specs_rebound": len(mapped), "obligations": len(obligations), "mapping": mapped,
              "plan_hash": {"from": plan.plan_hash, "to": new_plan.plan_hash},
              "unchanged": [k for k in ("requirements", "contracts", "approvals", "facts", "stories",
                                        "requirements_document") if candidate[k] == data[k]],
              "approvals_kept": len(candidate["approvals"]),
              "approvals_kept_grounds": _grounds(kept, assessed, by_id), "approvals_withheld": rows,
              "semantic_changes": changes,
              "needs_owner_reapproval": {"contracts": reapprove} if reapprove else None,
              "candidate": {"bundle_digest": hashlib.sha256(B._canonical(candidate)).hexdigest(),
                            "bundle_digest_is": "sha256 of the bundle's canonical JSON (sorted keys, no spaces), the "
                                                "digest `load` gives the project; `file_sha256`, when the command wrote "
                                                "the file, is the sha256 of that file's bytes",
                            "plan_id": new_plan.id, "plan_hash": new_plan.plan_hash, "contracts": len(contracts),
                            "approvals_kept": len(candidate["approvals"]), "contracts_to_approve": len(reapprove),
                            "loads": not reapprove},
              "limits": list(LIMITS)}
    return candidate, report


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


def exposure_of(old: Mapping) -> dict[str, dict]:
    """For `seal --keep-approvals-from`: contract id -> the declared capability changes that evaluate that contract of
    the earlier bundle `old` differently now (`_exposure`, the rule `migrate` applies), derived from the release its own
    plan was bound under. A contract of `old` no obligation names takes the earliest release its plan shows, and the
    earliest capability when the plan shows none a release compiles: an approval is never carried over on a release
    nobody can name."""
    try:
        contracts = {c["id"]: BehaviorContract.from_json(c) for c in old["contracts"]}
        plan = B._plan(old["plan"])
    except (KeyError, TypeError, ValueError) as e:
        raise B.BundleError(f"the bundle to keep approvals from does not load: {type(e).__name__}: {e}") from e
    refs = _refs()
    usable = {cid: c for cid, c in contracts.items() if c.subject.kind in refs}      # no probe: nothing to evaluate
    specs = {cid: _mint(c, refs[c.subject.kind]) for cid, c in usable.items()}
    return _exposure(usable, specs, _origins(specs, plan))


def seal(authoring: Mapping, *, repo: pathlib.Path | None = None, approvals=(), exposed: Mapping | None = None) -> tuple[dict, dict]:
    """(the sealed bundle, the report): every hash and spec id derived from the authoring document by the kernel's own
    constructors; `approvals` (a bundle's) kept when they still bind both hashes, the others named as dropped. An
    approval whose contract is in `exposed` (`exposure_of` the bundle they come from: a declared capability change
    evaluates it differently since) binds and is still not kept: it is named in `approvals_withheld_semantic`, and the
    contract is among `to_approve`. Approvals handed over without `exposed` are refused: kept by hash alone they would
    outlive a capability change that evaluates their contract differently (`exposed={}` says that none does). The
    baseline "HEAD" and the requirements document's sha256 are read from `repo`."""
    approvals = tuple(approvals)
    if approvals and exposed is None:
        raise B.BundleError("approvals to keep come with `exposed` (exposure_of the bundle they are from): kept by their "
                            "hashes alone they would outlive a capability change that evaluates their contract differently")
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
    kept, dropped, withheld = [], [], []
    for a in approvals:
        try:
            ap = ContractApproval(**a)
        except (TypeError, ValueError) as e:
            raise B.BundleError(f"an approval to keep does not load: {e}") from e
        c, r = by_id.get(ap.contract_id), reqs.get(ap.requirement_id)
        if c is None or r is None or binding_problems(ap, r, c):
            dropped.append(ap)
        elif ap.contract_id in (exposed or {}):
            withheld.append(ap)
        else:
            kept.append(ap)
    bundle = B.dump(name=authoring["name"], description=authoring["description"], requirements_path=doc["path"],
                    requirements_sha256=sha or "", product_roots=authoring["product_roots"], requirements=requirements,
                    contracts=contracts, approvals=kept, plan=plan, facts=facts, stories=stories)
    B.shape_problems(bundle)
    return bundle, {"plan_hash": plan.plan_hash, "specs": len({o.product_proof_spec_id for o in obligations}),
                    "approvals_kept": len(kept), "approvals_dropped": [f"{a.contract_id}/{a.requirement_id}" for a in dropped],
                    "approvals_withheld_semantic": [
                        {"contract": a.contract_id, "requirement": a.requirement_id, "approver": a.approver,
                         "approved_at": a.approved_at, "changes": exposed[a.contract_id]["changes"]} for a in withheld],
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
    ones are not repeated). The kernel's ContractApproval refuses an approver that is not `human:<name>`; this refuses
    the placeholder a printed command carries (`PLACEHOLDER`), which is no one."""
    if approver == PLACEHOLDER:
        raise B.BundleError(f"{PLACEHOLDER} is the placeholder of a printed command, not a person: write `human:` and your name")
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
    account = lineage.account_of(run_dir)
    report = {"carried": done, "carried_as": carried, "baseline": baseline, "run": str(run_dir), "evidence_anchor": anchor,
              "recorded": recorded, "anchor_checked": expect_anchor is not None,
              "already_continued_by": held,
              # a torn last line is the reader's verified prefix; the torn event's EFFECTS are not assumed undone —
              # they are among `unconfirmed`, reconciled against git (app/lineage)
              "torn_tail": bool(journal.torn_tail), "cut_event": reconciled["cut_event"],
              "unconfirmed": reconciled["items"], "left_out_unidentified": bool(reconciled["unidentified"]),
              "unaccounted": account["unaccounted"],
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
    s.add_argument("--keep-approvals-from", type=pathlib.Path,
                   help="an earlier bundle whose still-binding approvals stay, those of a contract a declared "
                        "capability change evaluates differently excepted (named in the report)")
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
    m = sub.add_parser("migrate", help="re-bind an earlier release's bundle to this release's spec ids; the approvals "
                                       "of a contract a declared capability change evaluates differently are withheld")
    m.add_argument("bundle", type=pathlib.Path)
    m.add_argument("--out", type=pathlib.Path, required=True, help="the migrated bundle (a new file; never the input)")
    a = p.parse_args(argv)
    try:
        if a.command == "init":
            init(a.example, a.out)
            print(json.dumps({"written": str(a.out), "next": _read(EXAMPLES / f"{a.example}.json")["readme"]}, indent=1))
            return 0
        if a.command == "seal":
            old = _read(a.keep_approvals_from) if a.keep_approvals_from else None
            keep = old["approvals"] if old is not None else ()
            doc, report = seal(_read(a.authoring), repo=a.repo, approvals=keep,
                               exposed=exposure_of(old) if old is not None else None)
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
        report = with_commands(report, a.out)
        try:        # the bytes as written (a text file on Windows is not the text encoded)
            report["candidate"]["file_sha256"] = hashlib.sha256(a.out.read_bytes()).hexdigest()
        except OSError:
            report["candidate"]["file_sha256"] = None
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
