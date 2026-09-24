"""RFC §4 — the nine top-level invariants as a typed registry, armed per test tier (WP-5.5; F10).

An invariant without an enforcement mechanism is a documented intention, not an invariant (§4). Here every one of
I–IX is a typed `Invariant` naming its enforcement mechanisms by typed identifier — code the kernel runs
(`package.module:qualname`), a kernel static rule (`kernel_static_checks:RULE`), or a validation checker
(`validation/v2/<file>.py:function`) — and the test tiers it is armed in. `register()` resolves every mechanism and
refuses the registry, closed, on any of: an invariant of the nine omitted, an unknown or duplicate id, a title
that is not the frozen one, an invariant without a mechanism, a mechanism that resolves nowhere, an invariant not
declared for every tier, a tier whose package does not arm, a directory of tests that is not a tier, an
`InvariantError` that an `except Exception` could hold, or a rendered document that drifted from the registry.
`arm(tier)` registers and marks all nine armed for that tier in this process; a tier package arms in its
`__init__`, so ARMED(I..IX) precedes the first test module of the tier. `require_armed` is what a runtime guard
calls first: an unarmed process fails closed.

Runtime control here uses the typed identifiers only; the rendered document (docs/implementation/v2/INVARIANTS-V2.md)
is generated from the registry and checked against it, never the other way round.
"""

from __future__ import annotations

import ast
import hashlib
import importlib
import importlib.util
import pathlib
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from aisef2.arch.enums import INVARIANT_TITLE, InvariantId
from aisef2.errors import InvariantError

__all__ = ["Tier", "MechanismKind", "Mechanism", "Invariant", "REGISTRY", "UNCONTAINABLE", "RegistrationError",
           "Registered", "Armed", "resolve", "register", "arm", "armed", "require_armed", "render", "registry_digest",
           "mechanism_digest", "test_directories"]

ROOT = pathlib.Path(__file__).resolve().parents[2]
TESTS_V2 = "tests/v2"
DOC_REL = "docs/implementation/v2/INVARIANTS-V2.md"
STATIC_CHECKS_REL = "validation/v2/kernel_static_checks.py"


class RegistrationError(InvariantError):
    """The registry cannot be armed: fail closed (§4)."""


class Tier(Enum):
    """The V2 harness's test tiers: the tests/v2 root and every package under it that holds tests."""
    ROOT = "tests/v2"
    CONFORMANCE = "tests/v2/conformance"
    P0 = "tests/v2/p0"
    P1 = "tests/v2/p1"
    P2 = "tests/v2/p2"
    P3 = "tests/v2/p3"
    P4 = "tests/v2/p4"
    P5 = "tests/v2/p5"
    PLAN = "tests/v2/plan"


class MechanismKind(Enum):
    CODE = "code"                 # package.module:qualname — importable, the attribute present
    STATIC_RULE = "static-rule"   # kernel_static_checks:RULE — a rule of validation/v2/kernel_static_checks.py
    CHECKER = "checker"           # validation/v2/<file>.py:function — a validation script's entry point


@dataclass(frozen=True)
class Mechanism:
    id: str               # stable identifier
    kind: MechanismKind
    ref: str              # the typed reference `resolve` reads
    role: str             # what it enforces — for the rendered document only, never read for control


@dataclass(frozen=True)
class Invariant:
    id: InvariantId
    title: str                          # the frozen title (INVARIANT_TITLE)
    rfc: str                            # stable RFC identifier
    mechanisms: tuple[Mechanism, ...]
    tiers: tuple[Tier, ...]             # every tier: no tier-specific omission is allowed


ALL_TIERS: tuple[Tier, ...] = tuple(Tier)
C, S, K = MechanismKind.CODE, MechanismKind.STATIC_RULE, MechanismKind.CHECKER


def _inv(id_: InvariantId, rfc: str, *mechanisms: tuple[str, MechanismKind, str, str]) -> Invariant:
    return Invariant(id_, INVARIANT_TITLE[id_], rfc, tuple(Mechanism(*m) for m in mechanisms), ALL_TIERS)


REGISTRY: tuple[Invariant, ...] = (
    _inv(InvariantId.I, "§4 row I",
         ("I.approval-binds-both-hashes", C, "aisef2.product.approval:require_approved",
          "a contract is compiled only with a ContractApproval binding the requirement hash and the contract hash"),
         ("I.binding-problems", C, "aisef2.product.approval:binding_problems",
          "an edited requirement or contract no longer matches its approval"),
         ("I.no-prose-control", S, "kernel_static_checks:NO_PROSE_CONTROL",
          "no kernel control path reads Requirement.text or a rationale"),
         ("I.sealed-record", C, "aisef2.probe.protocol:ProbeRecord",
          "authority derives from admission: a record's digest binds it; an edited record is a new record")),
    _inv(InvariantId.II, "§4 row II",
         ("II.harness-owned-probes", C, "aisef2.probe.protocol:run_probe",
          "verdicts come from harness-owned probes on a ProductProofSpec, never from developer test topology"),
         ("II.seq-not-time", S, "kernel_static_checks:NO_TIME_IN_PROJECTIONS",
          "no projection reads wall-clock time; control folds over seq"),
         ("II.from-scratch-fold", C, "aisef2.journal.fold:fold",
          "every control state is the pure fold of the journal prefix"),
         ("II.one-signal-authority", S, "kernel_static_checks:ONE_SIGNAL_AUTHORITY",
          "no control on an event bus: one authority for controller signal provenance"),
         ("II.deterministic-child-env", C, "aisef2.probe.protocol:ExecutionEnv",
          "a probe runs with what the harness gives it: interpreter, timeout, required enforcement"),
         ("II.runspec-hash", C, "aisef2.runtime.runspec:runspec_hash",
          "the resolved run identity is a content hash of capabilities, grade and settings")),
    _inv(InvariantId.III, "§4 row III",
         ("III.verifier-scope", C, "aisef2.runtime.story_scope:StoryScope",
          "the verifier's resources are acquired by its own scope and released in reverse order"),
         ("III.bound-result", C, "aisef2.probe.protocol:bound_result",
          "a decision reads a sealed ProbeRecord bound to the spec, the revision and the enforcement level"),
         ("III.result-only-through-binding", S, "kernel_static_checks:RESULT_ONLY_THROUGH_BINDING",
          "no kernel module reads a bare probe result"),
         ("III.confinement-from-env", C, "aisef2.probe.protocol:ExecutionEnv",
          "confinement is the typed ExecutionEnv the harness builds, never a passable developer parameter"),
         ("III.developer-tests-are-not-product-proof", C, "aisef2.quality.adequacy:assemble",
          "developer tests assemble engineering-test adequacy; nothing there reaches a product proof")),
    _inv(InvariantId.IV, "§4 row IV",
         ("IV.taxonomy", C, "aisef2.control.owner:classify",
          "owner and retryability are read from the typed taxonomy alone"),
         ("IV.charge-from-journal", C, "aisef2.control.budget:charge",
          "a retry charges the failure owner's own budget, decided from the journal projections"),
         ("IV.retryable-only-in-taxonomy", S, "kernel_static_checks:RETRYABLE_ONLY_IN_TAXONOMY",
          "retryability is fixed once, in the taxonomy"),
         ("IV.no-side-retry-counter", S, "kernel_static_checks:NO_SIDE_RETRY_COUNTER",
          "budgets are projections, never side counters"),
         ("IV.adequacy-charges-only-inadequate", C, "aisef2.quality.adequacy:assemble",
          "INCOMPLETE, UNRUNNABLE, ENVIRONMENT and INTEGRATION never charge the developer")),
    _inv(InvariantId.V, "§4 row V",
         ("V.comparable", C, "aisef2.runtime.runspec:comparable",
          "comparability requires the same capability tuples, grades and enforcement identity"),
         ("V.runspec-hash", C, "aisef2.runtime.runspec:runspec_hash",
          "the same frozen inputs give the same run identity"),
         ("V.capability-identity", C, "aisef2.runtime.capability:CapabilityIdentity",
          "a capability is identified by grade and binding tuple, never by a label alone"),
         ("V.capability-resolved", C, "aisef2.runtime.runspec:RunSpec.resolved",
          "the resolved capabilities and run identity are journaled (capability/resolved, run/spec-resolved)")),
    _inv(InvariantId.VI, "§4 row VI",
         ("VI.full-sha", C, "aisef2.probe.protocol:RevisionRef",
          "a revision is a full 40-hex SHA, never a name or an abbreviation"),
         ("VI.revision-in-runspec", C, "aisef2.runtime.runspec:resolve",
          "the run's source revision is the full SHA"),
         ("VI.journal-append-only", C, "aisef2.journal.format2:JournalWriter2",
          "the journal has no update or delete verb; seq is the index"),
         ("VI.record-digest", C, "aisef2.probe.protocol:ProbeRecord",
          "verdict identity fields are sealed by record_digest"),
         ("VI.semantic-hash", C, "aisef2.product.spec:ProductProofSpec",
          "a proof spec carries its semantic_hash"),
         ("VI.frozen-artefacts", K, "validation/v2/freeze_manifest.py:check",
          "a frozen artefact that drifts from the manifest identity is detected")),
    _inv(InvariantId.VII, "§4 row VII",
         ("VII.flatten-to-unknown", C, "aisef2.control.owner:flatten",
          "a value from outside the taxonomy becomes UNKNOWN, the original kept as data"),
         ("VII.typed-classify", C, "aisef2.control.owner:classify",
          "an untyped code is refused, never mapped by its text"),
         ("VII.no-prose-control", S, "kernel_static_checks:NO_PROSE_CONTROL",
          "no kernel control path reads prose"),
         ("VII.no-raw-verdict-routing", S, "kernel_static_checks:NO_RAW_VERDICT_ROUTING",
          "control routes on the derived ContractSatisfaction, never on a raw verdict"),
         ("VII.typed-collection-causes", C, "aisef2.quality.test_execution:classify",
          "a runner's report is read as typed causes, never as prose")),
    _inv(InvariantId.VIII, "§4 row VIII",
         ("VIII.evidence-admission", C, "aisef2.invariants.evidence:admit",
          "an evidence field admits only a harness-produced typed record; context is refused"),
         ("VIII.evidence-field", C, "aisef2.invariants.evidence:EvidenceField",
          "the typed field that carries evidence, admitted on construction"),
         ("VIII.journal-event", C, "aisef2.journal.event:Event",
          "a harness-produced record: typed, JSON-lossless, validated at the append site")),
    _inv(InvariantId.IX, "§4 row IX",
         ("IX.candidate-only-execution", S, "kernel_static_checks:CANDIDATE_ONLY_EXECUTION",
          "engineering-quality code names no parent revision and drives no git"),
         ("IX.no-developer-artefact-at-parent", S, "kernel_static_checks:NO_DEVELOPER_ARTEFACT_AT_PARENT",
          "no kernel module runs developer artefacts against a revision, and none imports the V1 gates"),
         ("IX.probe-refuses-test-artefacts", C, "aisef2.product.contract:names_test_artefact",
          "a probe input naming a developer test artefact is refused"),
         ("IX.probe-api", C, "aisef2.probe.protocol:run_probe",
          "the probe API takes a spec, a revision and an env: no developer path, command or test"),
         ("IX.candidate-side-vacuity", C, "aisef2.quality.vacuity:evaluate",
          "the only engineering-quality counterfactual runs at the candidate, never at the parent")),
)

#: What makes every one of the nine uncontainable (§4): the exception's structure, and the audit of the boundaries.
UNCONTAINABLE: tuple[Mechanism, ...] = (
    Mechanism("all.invariant-error-is-base-exception", C, "aisef2.errors:InvariantError",
              "derives from BaseException: no `except Exception` boundary can hold it"),
    Mechanism("all.except-boundary-audit", K, "validation/v2/except_boundaries.py:check",
              "every broad kernel except boundary re-raises it or cannot catch it; unknown patterns fail closed"),
)


# ------------------------------------------------------------------------------------------------ resolution

def _load_script(rel: str, root: pathlib.Path):
    path = root / rel
    if not path.exists():
        raise RegistrationError(f"{rel} does not exist")
    spec = importlib.util.spec_from_file_location("aisef2_invariants_" + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resolve(mechanism: Mechanism, root: pathlib.Path = ROOT) -> object:
    """The object a mechanism's typed reference names; RegistrationError when it resolves nowhere."""
    if not isinstance(mechanism, Mechanism) or not isinstance(mechanism.kind, MechanismKind):
        raise RegistrationError(f"{mechanism!r} is not a typed mechanism")
    target, sep, name = mechanism.ref.partition(":")
    if not sep or not target or not name:
        raise RegistrationError(f"{mechanism.id}: reference {mechanism.ref!r} is not <target>:<name>")
    if mechanism.kind is MechanismKind.CODE:
        try:
            obj: object = importlib.import_module(target)
        except ImportError as e:
            raise RegistrationError(f"{mechanism.id}: module {target!r} does not import: {e}") from None
        for part in name.split("."):
            if not hasattr(obj, part):
                raise RegistrationError(f"{mechanism.id}: {target}:{name} resolves nowhere")
            obj = getattr(obj, part)
        return obj
    if mechanism.kind is MechanismKind.STATIC_RULE:
        if target != "kernel_static_checks":
            raise RegistrationError(f"{mechanism.id}: static rules live in kernel_static_checks, not {target!r}")
        rules = _load_script(STATIC_CHECKS_REL, root).RULES
        if name not in rules:
            raise RegistrationError(f"{mechanism.id}: {name} is not a rule of {STATIC_CHECKS_REL}")
        return name
    module = _load_script(target, root)
    if not callable(getattr(module, name, None)):
        raise RegistrationError(f"{mechanism.id}: {target}:{name} resolves nowhere")
    return getattr(module, name)


# ------------------------------------------------------------------------------------------------ tiers

def test_directories(root: pathlib.Path = ROOT) -> frozenset[str]:
    """Every directory under tests/v2 that holds a test module, and the root itself: what must be a Tier."""
    base = root / TESTS_V2
    out = {TESTS_V2} if any(base.glob("test_*.py")) else set()
    for path in base.rglob("test_*.py"):
        out.add(path.parent.relative_to(root).as_posix())
    return frozenset(out)


def _arms(tier: Tier, root: pathlib.Path) -> bool:
    """The tier package's `__init__` calls `arm(Tier.<tier>)` at module level."""
    init = root / tier.value / "__init__.py"
    if not init.exists():
        return False
    for node in ast.walk(ast.parse(init.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", None)) == "arm":
            arg = node.args[0] if node.args else None
            if isinstance(arg, ast.Attribute) and isinstance(arg.value, ast.Name) and arg.value.id == "Tier" \
                    and arg.attr == tier.name:
                return True
    return False


# ------------------------------------------------------------------------------------------------ registration

@dataclass(frozen=True)
class Registered:
    invariants: tuple[Invariant, ...]
    digest: str              # of the registry's typed content
    mechanism_digest: str    # of the resolved mechanisms' identities (module files, rules, checker files)
    tiers: tuple[Tier, ...]


def registry_digest(registry: tuple[Invariant, ...] = REGISTRY) -> str:
    rows = [(i.id.value, i.title, i.rfc, tuple((m.id, m.kind.value, m.ref) for m in i.mechanisms),
             tuple(t.value for t in i.tiers)) for i in registry]
    rows.append(("uncontainable", tuple((m.id, m.kind.value, m.ref) for m in UNCONTAINABLE)))
    return hashlib.sha256(repr(rows).encode("utf-8")).hexdigest()


def _identity(mechanism: Mechanism, root: pathlib.Path) -> str:
    target, _, name = mechanism.ref.partition(":")
    if mechanism.kind is MechanismKind.CODE:
        rel = pathlib.Path(*target.split(".")).with_suffix(".py")
        path = root / rel
        if not path.exists():
            path = root / rel.with_suffix("") / "__init__.py"
    elif mechanism.kind is MechanismKind.STATIC_RULE:
        path = root / STATIC_CHECKS_REL
    else:
        path = root / target
    return f"{mechanism.id} {mechanism.ref} {hashlib.sha256(path.read_bytes()).hexdigest()}"


def mechanism_digest(registry: tuple[Invariant, ...] = REGISTRY, root: pathlib.Path = ROOT) -> str:
    lines = [_identity(m, root) for i in registry for m in i.mechanisms] + [_identity(m, root) for m in UNCONTAINABLE]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def register(registry: tuple[Invariant, ...] = REGISTRY, *, root: pathlib.Path = ROOT, doc: bool = True) -> Registered:
    """Validate the registry, closed, and resolve every mechanism. Raises RegistrationError on any defect."""
    if not isinstance(registry, tuple):
        raise RegistrationError("the registry is a tuple of invariants, closed at registration")
    ids = [i.id if isinstance(i, Invariant) else None for i in registry]
    if any(not isinstance(i, InvariantId) for i in ids):
        raise RegistrationError("an entry is not one of the nine typed invariants (unknown invariant)")
    if len(set(ids)) != len(ids):
        raise RegistrationError("duplicate invariant ids")
    if ids != list(InvariantId):
        raise RegistrationError(f"the registry holds exactly I..IX in order; got {[i.value for i in ids]}")
    for inv in registry:
        if inv.title != INVARIANT_TITLE[inv.id]:
            raise RegistrationError(f"{inv.id.value}: title {inv.title!r} is not the frozen {INVARIANT_TITLE[inv.id]!r}")
        if not inv.mechanisms:
            raise RegistrationError(f"{inv.id.value} has no enforcement mechanism: a documented intention, not an invariant")
        if tuple(inv.tiers) != ALL_TIERS:
            raise RegistrationError(f"{inv.id.value} is declared but not armed in every tier: "
                                    f"{[t.value for t in ALL_TIERS if t not in inv.tiers]}")
        for m in inv.mechanisms:
            resolve(m, root)
    for m in UNCONTAINABLE:
        resolve(m, root)
    if not issubclass(InvariantError, BaseException) or issubclass(InvariantError, Exception):
        raise RegistrationError("InvariantError must derive from BaseException and not from Exception (§4)")
    for tier in ALL_TIERS:
        if not _arms(tier, root):
            raise RegistrationError(f"tier {tier.value} does not arm I..IX in its package __init__")
    stray = test_directories(root) - {t.value for t in ALL_TIERS}
    if stray:
        raise RegistrationError(f"tests live outside every tier, unarmed: {min(stray)} ({len(stray)} director"
                                f"{'y' if len(stray) == 1 else 'ies'})")
    if doc:
        path = root / DOC_REL
        if not path.exists() or path.read_text(encoding="utf-8") != render(registry):
            raise RegistrationError(f"{DOC_REL} drifted from the registry (regenerate it: "
                                    "python -P validation/v2/invariants_doc.py)")
    return Registered(registry, registry_digest(registry), mechanism_digest(registry, root), ALL_TIERS)


# ------------------------------------------------------------------------------------------------ arming

@dataclass(frozen=True)
class Armed:
    tier: Tier
    invariants: frozenset[InvariantId]
    digest: str


_ARMED: dict[Tier, frozenset[InvariantId]] = {}


def arm(tier: Tier, *, registry: tuple[Invariant, ...] = REGISTRY, root: pathlib.Path = ROOT) -> Armed:
    """Register (fail closed) and mark all nine armed for `tier` in this process. Idempotent."""
    if not isinstance(tier, Tier):
        raise RegistrationError(f"{tier!r} is not a tier")
    registered = register(registry, root=root)
    ids = frozenset(i.id for i in registered.invariants)
    _ARMED[tier] = ids
    return Armed(tier, ids, registered.digest)


def armed() -> Mapping[Tier, frozenset[InvariantId]]:
    return MappingProxyType(dict(_ARMED))


def require_armed(invariant: InvariantId) -> None:
    """A runtime guard's first act: refuse to work in a process where its invariant is not armed (fail closed)."""
    if not isinstance(invariant, InvariantId) or not any(invariant in ids for ids in _ARMED.values()):
        raise InvariantError(f"invariant {getattr(invariant, 'value', invariant)} is not armed in this process: "
                             "its enforcement mechanism is absent, so nothing it guards may proceed (§4)",
                             invariant=getattr(invariant, "value", None))


# ------------------------------------------------------------------------------------------------ the document

def render(registry: tuple[Invariant, ...] = REGISTRY) -> str:
    """docs/implementation/v2/INVARIANTS-V2.md from the registry — edit the registry, not the document."""
    out = ["# AISEF V2 invariants I–IX (RFC §4, F10)", "",
           "Rendered from `aisef2/invariants/registry.py` by `validation/v2/invariants_doc.py` — edit the registry, "
           "not this file; `register()` refuses a registry this document has drifted from. Every invariant is armed "
           "in every tier below before the tier's first test module is imported; all are uncontainable: "
           "`InvariantError` derives from `BaseException` and every broad kernel `except` boundary re-raises it "
           "(`validation/v2/except_boundaries.py`).", "",
           "**Tiers:** " + ", ".join(f"`{t.value}`" for t in ALL_TIERS), "",
           "| # | invariant | RFC | mechanism | kind | reference | enforces |", "|---|---|---|---|---|---|---|"]
    for inv in registry:
        for n, m in enumerate(inv.mechanisms):
            first = f"**{inv.id.value}** | {inv.title} | {inv.rfc}" if n == 0 else " | | "
            out.append(f"| {first} | `{m.id}` | {m.kind.value} | `{m.ref}` | {m.role} |")
    out += ["", "## Uncontainable", "", "| mechanism | kind | reference | enforces |", "|---|---|---|---|"]
    out += [f"| `{m.id}` | {m.kind.value} | `{m.ref}` | {m.role} |" for m in UNCONTAINABLE]
    return "\n".join(out) + "\n"
