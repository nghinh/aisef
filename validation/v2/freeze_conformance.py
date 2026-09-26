"""WP-0.3 — F1–F11 conformance: every frozen item reports a definite state, and nothing passes by absence.

The **reference** for every check is extracted from the approved RFC itself, not transcribed. States:

* **PASS** — the implementation exists and equals the RFC reference.
* **FAIL** — it differs; or the RFC reference cannot be extracted; or a sub-check owned by a package in a phase
  already reached has no implementation (the ratchet); or a later-phase implementation has appeared before a real
  comparison exists for it (fail-closed: presence without evaluation is never a pass).
* **PENDING** — the shape belongs to a later phase and its implementation does not exist yet. A PENDING result
  always names the package that will implement it, and is never interpreted as PASS.

An item is PASS only if every sub-check is PASS; FAIL if any is FAIL; otherwise PENDING.

    python -P validation/v2/freeze_conformance.py            # write closure-evidence/v2/F-CONFORMANCE.json
    python -P validation/v2/freeze_conformance.py --check    # fail on FAIL, on a broken ratchet, or on staleness
"""

from __future__ import annotations

import ast
import dataclasses
import importlib
import inspect
import json
import pathlib
import re
import sys
from types import SimpleNamespace

ROOT = pathlib.Path(__file__).resolve().parents[2]
RFC_REL = "docs/architecture/AISEF-V2-ARCHITECTURE-RFC.md"
MANIFEST_REL = "docs/implementation/v2/cycle1-manifest.json"
OUT_REL = "closure-evidence/v2/F-CONFORMANCE.json"
NORMATIVE_MARK = "## 1. Executive architecture decision"
FROZEN_IDS = [f"F{i}" for i in range(1, 12)]

#: The phase the Cycle-1 implementation has reached. Every sub-check owned by a package in this phase or an earlier
#: one must PASS. Advanced by one reviewed line at each phase boundary.
# ponytail: a constant, not a progress database; move it into a progress record if phases start overlapping.
CURRENT_PHASE = "P6"

PASS, FAIL, PENDING = "PASS", "FAIL", "PENDING"


# --------------------------------------------------------------------------------------- RFC reference extraction

class RFC:
    def __init__(self, text: str):
        self.body = text[text.index(NORMATIVE_MARK):] if NORMATIVE_MARK in text else ""
        self.enums: dict[str, list[str]] = {}
        self.dataclasses: dict[str, list[str]] = {}
        self.dataclass_defaults: dict[str, dict[str, str]] = {}
        self.dataclass_frozen: dict[str, bool] = {}
        self.protocols: dict[str, list[str]] = {}
        self.protocol_members: dict[str, list[tuple[str, list[str] | None]]] = {}
        for block in re.findall(r"```python\n(.*?)```", self.body, re.S):
            try:
                tree = ast.parse(block)
            except SyntaxError:
                continue
            for n in ast.walk(tree):
                if not isinstance(n, ast.ClassDef):
                    continue
                bases = {getattr(b, "id", "") for b in n.bases}
                decos = {getattr(d, "id", "") for d in n.decorator_list} | \
                        {getattr(getattr(d, "func", None), "id", "") for d in n.decorator_list}
                if "Enum" in bases:
                    self.enums[n.name] = [t.id for s in n.body if isinstance(s, ast.Assign)
                                          for t in s.targets if isinstance(t, ast.Name)]
                elif "Protocol" in bases:
                    self.protocols[n.name] = [s.target.id if isinstance(s, ast.AnnAssign) else s.name
                                              for s in n.body if isinstance(s, ast.AnnAssign | ast.FunctionDef)]
                    self.protocol_members[n.name] = [
                        (s.target.id, None) if isinstance(s, ast.AnnAssign) else (s.name, [a.arg for a in s.args.args])
                        for s in n.body if isinstance(s, ast.AnnAssign | ast.FunctionDef)]
                elif "dataclass" in decos:
                    self.dataclasses[n.name] = [s.target.id for s in n.body if isinstance(s, ast.AnnAssign)]
                    self.dataclass_defaults[n.name] = {s.target.id: ast.unparse(s.value) for s in n.body
                                                       if isinstance(s, ast.AnnAssign) and s.value is not None}
                    self.dataclass_frozen[n.name] = any(
                        k.arg == "frozen" and getattr(k.value, "value", None) is True
                        for d in n.decorator_list for k in getattr(d, "keywords", []))

    def section(self, begin: str, end: str) -> str:
        if begin not in self.body or end not in self.body:
            return ""
        i = self.body.index(begin)
        return self.body[i:self.body.index(end, i)]

    def event_types(self) -> list[str]:
        s = self.section("### 20.1 Vocabulary", "### 20.2")
        return list(dict.fromkeys(re.findall(r"`([a-z]+/[a-z-]+)`", s)))

    def invariants(self) -> dict[str, str]:
        s = self.section("## 4. Top-level invariants", "## 5. Planes")
        return dict(re.findall(r"^\| \*\*([IVX]+)\*\* \| \*\*([^*]+?)\.\*\*", s, re.M))

    def control_projections(self) -> list[str]:
        s = self.section("## 21. Control-critical projections", "## 22.")
        line = next((ln for ln in s.splitlines() if "story state" in ln), "")
        return [re.sub(r"^\d+\.\s*", "", p.strip()).replace(" ", "_") for p in line.split("·") if p.strip()]

    def subject_kinds(self) -> list[str]:
        m = re.search(r"kind: Literal\[(.*?)\]", self.body)
        return re.findall(r'"([a-z_]+)"', m.group(1)) if m else []

    def cited_identities(self) -> list[str]:
        s = self.section("### 5.1 The four cited identities", "## 6.")
        return [" / ".join(re.findall(r"`([a-z_]+)`", row.split("|")[1]))
                for row in s.splitlines() if row.startswith("| `")]

    def lifetime_order(self) -> dict[str, list[str]]:
        s = self.section("### 18.1 Lifetime order", "## 19.")
        out = {}
        for key, marker in (("begin", "**Begin order (normative):**"),
                            ("shutdown", "**Successful shutdown order (normative):**")):
            if marker in s:
                tail = s[s.index(marker) + len(marker):]
                steps = []
                for ln in tail.splitlines():
                    m = re.match(r"^(\d+)\. (.+)$", ln.strip())
                    if m:
                        steps.append(m.group(2).rstrip(";."))
                    elif steps and ln.strip():
                        break
                out[key] = steps
        return out


# --------------------------------------------------------------------------------------- code side

def code_vocabularies() -> dict | None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    try:
        enums = importlib.import_module("aisef2.arch.enums")
    except ModuleNotFoundError:
        return None
    return {name: ([m.name for m in e], [m.value for m in e]) for name, (e, _i, _s) in enums.VOCABULARIES.items()} | \
        {"__invariant_titles__": ([], [f"{k.value}:{v}" for k, v in enums.INVARIANT_TITLE.items()])}


def symbol_present(module: str, attr: str | None) -> bool:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    try:
        mod = importlib.import_module(module)
    except ModuleNotFoundError:
        return False
    return attr is None or hasattr(mod, attr)


# --------------------------------------------------------------------------------------- sub-checks

def _phase_of(package: str, manifest: dict) -> str:
    return next(p["phase"] for p in manifest["work_packages"] if p["id"] == package)


def _reached(phase: str, manifest: dict) -> bool:
    order = [ph["id"] for ph in manifest["phases"]]
    return order.index(phase) <= order.index(CURRENT_PHASE)


def _vocab(name: str, rfc_members: list[str], code, *, by_value: bool = False) -> dict:
    if not rfc_members:
        return {"state": FAIL, "detail": f"RFC reference for {name} could not be extracted"}
    if code is None or name not in code:
        return {"state": None, "detail": f"{name} absent from aisef2.arch.enums"}
    got = code[name][1] if by_value else code[name][0]
    if got != rfc_members:
        missing = [m for m in rfc_members if m not in got]
        extra = [m for m in got if m not in rfc_members]
        return {"state": FAIL, "detail": f"{name} differs from the RFC", "missing": missing, "extra": extra,
                "order_differs": not missing and not extra}
    return {"state": PASS, "detail": f"{name} equals the RFC ({len(got)} members)"}


def _shape(module: str, attr: str | None, reference) -> dict:
    if not reference:
        return {"state": FAIL, "detail": "RFC reference for this shape could not be extracted"}
    if not symbol_present(module, attr):
        return {"state": None, "detail": f"{module}{'.' + attr if attr else ''} not implemented", "rfc_reference": reference}
    return {"state": FAIL, "rfc_reference": reference,
            "detail": f"{module}{'.' + attr if attr else ''} exists but no conformance comparison has been written for "
                      "it — presence without evaluation is never a pass"}


def _invariants_armed(reference: list[str] | None) -> dict:
    """F10 (WP-5.5): I..IX registered with resolved mechanisms and armed in every test tier — evaluated by
    registering the registry (which fails closed on any defect) and importing every tier package, then reading
    what is armed. Never a pass by presence."""
    if not reference:
        return {"state": FAIL, "detail": "RFC reference for the invariant set could not be extracted"}
    if not symbol_present("aisef2.invariants.registry", "arm"):
        return {"state": None, "detail": "aisef2.invariants.registry.arm not implemented", "rfc_reference": reference}
    reg = importlib.import_module("aisef2.invariants.registry")
    try:
        registered = reg.register()
    except reg.RegistrationError as e:
        return {"state": FAIL, "detail": f"registration refused: {e}", "rfc_reference": reference}
    ids = [i.id.value for i in registered.invariants]
    if ids != reference:
        return {"state": FAIL, "detail": "the registry's invariants differ from the RFC's", "rfc_reference": reference,
                "implemented": ids}
    for tier in reg.Tier:
        importlib.import_module(tier.value.replace("/", "."))
    armed = reg.armed()
    unarmed = [t.value for t in reg.Tier if set(armed.get(t, ())) != set(reg.InvariantId)]
    if unarmed:
        return {"state": FAIL, "detail": f"not armed in every tier: {unarmed}", "rfc_reference": reference}
    mechanisms = {i.id.value: [m.ref for m in i.mechanisms] for i in registered.invariants}
    return {"state": PASS, "rfc_reference": reference, "mechanisms": mechanisms, "tiers": [t.value for t in reg.Tier],
            "detail": f"I..IX registered with {sum(len(v) for v in mechanisms.values())} resolved mechanisms and armed "
                      f"in {len(armed)} of {len(reg.Tier)} tiers"}


def _fields(module: str, attr: str, reference: list[str] | None) -> dict:
    """A dataclass shape: its field names, in order, against the RFC's own class block."""
    if not reference:
        return {"state": FAIL, "detail": "RFC reference for this shape could not be extracted"}
    if not symbol_present(module, attr):
        return {"state": None, "detail": f"{module}.{attr} not implemented", "rfc_reference": reference}
    cls = getattr(importlib.import_module(module), attr)
    if not dataclasses.is_dataclass(cls):
        return {"state": FAIL, "detail": f"{module}.{attr} is not a dataclass", "rfc_reference": reference}
    got = [f.name for f in dataclasses.fields(cls)]
    if got != reference:
        return {"state": FAIL, "detail": f"{attr} fields differ from the RFC", "rfc_reference": reference,
                "implemented": got}
    return {"state": PASS, "detail": f"{attr} fields equal the RFC in order ({len(got)})"}


def _protocol_matches_rfc(rfc: RFC, module: str, name: str) -> dict:
    """A Protocol shape: attribute and method names in order, and each method's parameters, against the RFC block."""
    reference = rfc.protocol_members.get(name)
    if not reference:
        return {"state": FAIL, "detail": f"RFC reference for {name} could not be extracted"}
    ref = [[m, p] for m, p in reference]
    if not symbol_present(module, name):
        return {"state": None, "detail": f"{module}.{name} not implemented", "rfc_reference": ref}
    cls = getattr(importlib.import_module(module), name)
    if not getattr(cls, "_is_protocol", False):
        return {"state": FAIL, "detail": f"{module}.{name} is not a typing.Protocol", "rfc_reference": ref}
    got = [[m, None] for m in cls.__dict__.get("__annotations__", {})] + \
          [[m, list(inspect.signature(v).parameters)] for m, v in cls.__dict__.items()
           if inspect.isfunction(v) and not m.startswith("_")]
    if got != ref:
        return {"state": FAIL, "detail": f"{name} members or signatures differ from the RFC", "rfc_reference": ref,
                "implemented": got}
    return {"state": PASS, "detail": f"{name} equals the RFC: {len(got)} members, signatures included"}


def _calibration_contracts_match_rfc(rfc: RFC) -> dict:
    """F5's two calibration contracts: both dataclass shapes, in order, and the falsifiability mechanism literal."""
    names = ("ProbeCapabilityCalibration", "SpecFalsifiabilityEvidence")
    refs = {n: rfc.dataclasses.get(n) for n in names}
    m = re.search(r"mechanism: Literal\[(.*?)\]", rfc.section("#### 9.1.2", "**Why the split.**"))
    mechanisms = re.findall(r'"([a-z_]+)"', m.group(1)) if m else []
    if not all(refs.values()) or not mechanisms:
        return {"state": FAIL, "detail": "RFC reference for the calibration contracts could not be extracted"}
    subs = {n: _fields("aisef2.probe.calibration", n, refs[n]) for n in names}
    if any(r["state"] is None for r in subs.values()):
        return {"state": None, "detail": "aisef2.probe.calibration not implemented", "rfc_reference": refs}
    got = list(getattr(importlib.import_module("aisef2.probe.calibration"), "MECHANISMS", ()))
    problems = [f"{n}: {r['detail']}" for n, r in subs.items() if r["state"] != PASS]
    if got != mechanisms:
        problems.append(f"mechanisms {got} differ from the RFC {mechanisms}")
    if problems:
        return {"state": FAIL, "detail": "; ".join(problems), "rfc_reference": refs, "rfc_mechanisms": mechanisms}
    return {"state": PASS, "detail": "both calibration contracts and the mechanism literal equal the RFC"}


def _event_envelope_matches_rfc(rfc: RFC) -> dict:
    """F1: the `Event` envelope — its field names in order, the RFC's defaults, and frozenness."""
    base = _fields("aisef2.journal.event", "Event", rfc.dataclasses.get("Event"))
    if base["state"] != PASS:
        return base
    cls = importlib.import_module("aisef2.journal.event").Event
    want = rfc.dataclass_defaults.get("Event", {})
    got = {f.name: repr(f.default) for f in dataclasses.fields(cls) if f.default is not dataclasses.MISSING}
    if got != want:
        return {"state": FAIL, "detail": "Event defaults differ from the RFC", "rfc_reference": want, "implemented": got}
    if cls.__dataclass_params__.frozen is not rfc.dataclass_frozen.get("Event"):
        return {"state": FAIL, "detail": "Event frozenness differs from the RFC"}
    return {"state": PASS, "detail": f"Event fields, defaults {sorted(got)} and frozenness equal the RFC"}


def _norm(text: str) -> str:
    return re.sub(r"[\s`*]", "", text).lower()


#: the one noun that names each RFC lifetime step (§18.1); each must occur in the RFC step and in the code's step
LIFETIME_KEYS = {"begin": ("lease", "open", "journalwriter", "runspec", "execution"),
                 "shutdown": ("storyscope", "run/dispose-begin", "run/end", "journalwriter", "clean", "lease")}


def _lifetime_matches_rfc(rfc: RFC, code) -> dict:
    """F8: the begin and shutdown orders the RFC states, in order, are the orders RunScope declares and executes; the
    lease is released last; a StoryScope owns no journal writer."""
    order = rfc.lifetime_order()
    if len(order.get("begin", [])) != 5 or len(order.get("shutdown", [])) != 6:
        return {"state": FAIL, "detail": "RFC reference for the lifetime order could not be extracted"}
    if code is None:
        return {"state": FAIL, "detail": "the kernel vocabulary (aisef2.arch.enums) does not load"}
    if not symbol_present("aisef2.runtime.run_scope", "RunScope"):
        return {"state": None, "detail": "aisef2.runtime.run_scope.RunScope not implemented", "rfc_reference": order}
    rs = importlib.import_module("aisef2.runtime.run_scope")
    declared = {"begin": list(rs.BEGIN_ORDER), "shutdown": list(rs.SHUTDOWN_ORDER)}
    for part, keys in LIFETIME_KEYS.items():
        if len(declared[part]) != len(keys):
            return {"state": FAIL, "detail": f"RunScope declares {len(declared[part])} {part} steps; the RFC has "
                                             f"{len(keys)}", "rfc_reference": order, "implemented": declared}
        off = [i for i, k in enumerate(keys) if k not in _norm(order[part][i]) or k not in _norm(declared[part][i])]
        if off:
            return {"state": FAIL, "detail": f"{part} steps {off} differ from the RFC's order", "rfc_reference": order,
                    "implemented": declared}
    import tempfile
    from aisef2.arch.enums import Enforcement
    from aisef2.runtime.capability import verified
    from aisef2.runtime.runspec import resolve
    with tempfile.TemporaryDirectory(prefix="aisef2-f8-") as d:
        run = rs.RunScope(d, "f8", spec=lambda: resolve([verified("kernel", b"f8", Enforcement.FULL)], {}, "0" * 40))
        run.begin()
        run.shutdown()
        executed = run.trace
    if executed != declared["begin"] + declared["shutdown"]:
        return {"state": FAIL, "detail": "RunScope does not execute the order it declares", "executed": executed}
    scope_src = (ROOT / "aisef2/runtime/story_scope.py").read_text(encoding="utf-8")
    if re.search(r"JournalWriter|aisef2\.journal\.writer|aisef2\.journal\.format2 import .*Writer", scope_src):
        return {"state": FAIL, "detail": "StoryScope names a journal writer (§18: it emits through the run's journal)"}
    return {"state": PASS, "detail": "begin (5) and shutdown (6) orders equal the RFC's, declared and executed; the lease "
                                     "is released last; StoryScope owns no journal writer"}


def _runspec_matches_rfc(rfc: RFC) -> dict:
    """F9: RunSpec and CapabilityIdentity are the RFC's shapes; the four cited identities exist where the RFC puts them;
    runspec_hash binds grade and enforcement and the aggregate is the minimum grade."""
    ids = rfc.cited_identities()
    want = {n: rfc.dataclasses.get(n) for n in ("RunSpec", "CapabilityIdentity")}
    if len(ids) != 4 or not all(want.values()):
        return {"state": FAIL, "detail": "RFC reference for the identities and RunSpec could not be extracted"}
    if not symbol_present("aisef2.runtime.runspec", "RunSpec"):
        return {"state": None, "detail": "aisef2.runtime.runspec.RunSpec not implemented",
                "rfc_reference": {"identities": ids, "RunSpec": want["RunSpec"]}}
    import dataclasses
    rsp = importlib.import_module("aisef2.runtime.runspec")
    cap = importlib.import_module("aisef2.runtime.capability")
    got = {"RunSpec": [f.name for f in dataclasses.fields(rsp.RunSpec)],
           "CapabilityIdentity": [f.name for f in dataclasses.fields(cap.CapabilityIdentity)]}
    if got != want:
        return {"state": FAIL, "detail": "RunSpec / CapabilityIdentity fields differ from the RFC", "rfc_reference": want,
                "implemented": got}
    from aisef2.arch.enums import Enforcement as E, EventType as T, IdentityGrade as G
    from aisef2.journal import event as ev, format2 as f2
    spec_fields = [f.name for f in dataclasses.fields(importlib.import_module("aisef2.product.spec").ProductProofSpec)]
    where = {"semantic_hash": "semantic_hash" in spec_fields,
             "plan_hash": "plan_hash" in ev.SCHEMAS[T.PLAN_FROZEN.value].required,
             "parent_sha / candidate_sha": ev.SCHEMAS[T.STORY_BEGIN.value].required.get("parent") is ev._sha
             and ev.SCHEMAS[T.STORY_COMMIT.value].required.get("revision") is ev._sha,
             "runspec_hash": "runspec_hash" in f2.SCHEMAS[T.RUN_SPEC_RESOLVED.value].required}
    if sorted(where) != sorted(ids) or not all(where.values()):
        return {"state": FAIL, "detail": "a cited identity is missing where the RFC puts it", "identities": where}
    k = cap.verified("kernel", b"f9", E.FULL)
    a = rsp.resolve([k, cap.opaque("combo", E.FULL, route="r")], {}, "0" * 40)
    b = rsp.resolve([cap.verified("kernel", b"f9", E.PARTIAL), cap.opaque("combo", E.FULL, route="r")], {}, "0" * 40)
    if a.aggregate_min_grade is not G.OPAQUE or a.runspec_hash == b.runspec_hash or rsp.comparable(a, b)[0] \
            or rsp.q6_eligible(a):
        return {"state": FAIL, "detail": "runspec_hash, the aggregate grade or comparability do not bind what §23 says"}
    return {"state": PASS, "detail": "RunSpec and CapabilityIdentity equal the RFC; the four cited identities are bound; "
                                     "the aggregate is the minimum grade; enforcement enters runspec_hash and "
                                     "comparability; OPAQUE bars Q6"}


def _failure_taxonomy_matches_rfc(rfc: RFC) -> dict:
    """F1 (V2-005): FailureCode is exactly the RFC §22.1 table, in order — one owner and one retryability per code,
    fixed in the taxonomy; formats 1 and 2 carry only the codes the table marks with first format 1."""
    rows = re.findall(r"^\| `([A-Z_]+)` \| `([A-Z]+)` \| `([A-Z_]+)` \| (\d)", rfc.section("### 22.1", "## 23."), re.M)
    if not rows:
        return {"state": FAIL, "detail": "RFC §22.1 failure taxonomy table could not be extracted"}
    if not symbol_present("aisef2.control.owner", "V2_005_CODES"):
        return {"state": None, "detail": "aisef2.control.owner does not carry the V2-005 taxonomy", "rfc_reference": rows}
    ow = importlib.import_module("aisef2.control.owner")
    problems = []
    if [c.value for c in ow.FailureCode] != [c for c, *_ in rows]:
        problems.append(f"FailureCode members differ from §22.1: implemented {[c.value for c in ow.FailureCode]}")
    got = {c.value: (k.owner.value, k.retryability.value) for c, k in ow.TAXONOMY.items()}
    problems += [f"{c}: RFC ({o}, {r}), implemented {got.get(c)}" for c, o, r, _ in rows if got.get(c) != (o, r)]
    first = {c: f for c, _, _, f in rows}
    if set(ow.FORMAT_2_CODES) != {c for c, f in first.items() if f == "1"}:
        problems.append("FORMAT_2_CODES is not exactly the codes §22.1 marks with first format 1")
    if set(ow.V2_005_CODES) != {c for c, f in first.items() if f == "3"}:
        problems.append("V2_005_CODES is not exactly the codes §22.1 marks with first format 3")
    if set(ow.FORMAT_2_CODES) & set(ow.V2_005_CODES) or set(ow.FORMAT_2_CODES) | set(ow.V2_005_CODES) != set(got):
        problems.append("FORMAT_2_CODES and V2_005_CODES do not partition FailureCode")
    if problems:
        return {"state": FAIL, "detail": "the failure taxonomy differs from RFC §22.1", "problems": problems}
    return {"state": PASS, "detail": f"FailureCode equals the RFC §22.1 table: {len(rows)} codes, each with its owner and "
                                     f"retryability; {len(ow.FORMAT_2_CODES)} carried by formats 1 and 2, "
                                     f"{len(ow.V2_005_CODES)} by format 3 only"}


def _journal_format_3_matches_rfc(rfc: RFC) -> dict:
    """F1 (V2-005): journal format 3 carries a schema for every event type of §20.1; a format-3 provider/request
    requires budget_owner; formats 1 and 2 are unchanged (18 and 25 writable types, no budget_owner)."""
    want = rfc.event_types()
    if len(want) != 29:
        return {"state": FAIL, "detail": f"RFC §20.1 names {len(want)} event types, not 29"}
    if not symbol_present("aisef2.journal.format3", "SCHEMAS"):
        return {"state": None, "detail": "aisef2.journal.format3 not implemented", "rfc_reference": want}
    ev = importlib.import_module("aisef2.journal.event")
    f2 = importlib.import_module("aisef2.journal.format2")
    f3 = importlib.import_module("aisef2.journal.format3")
    problems = []
    if sorted(f3.SCHEMAS) != sorted(want) or sorted(f3.WRITABLE) != sorted(want):
        problems.append(f"format 3 schemas {sorted(set(want) - set(f3.SCHEMAS))} missing, {sorted(set(f3.SCHEMAS) - set(want))} extra")
    if (f3.FORMAT, tuple(f3.KNOWN_FORMATS)) != (3, (1, 2, 3)):
        problems.append(f"format 3 declares {f3.FORMAT}, knows {f3.KNOWN_FORMATS}")
    if "budget_owner" not in f3.SCHEMAS["provider/request"].required:
        problems.append("a format-3 provider/request does not require budget_owner")
    if (len(ev.SCHEMAS), len(f2.WRITABLE)) != (18, 25):
        problems.append(f"formats 1 and 2 changed: {len(ev.SCHEMAS)} and {len(f2.WRITABLE)} writable types")
    if "budget_owner" in ev.SCHEMAS["provider/request"].required or "budget_owner" in f2.SCHEMAS.get(
            "provider/request", ev.SCHEMAS["provider/request"]).required:
        problems.append("a format-1 or format-2 provider/request requires budget_owner")
    if not all(callable(getattr(f3, n, None)) for n in ("reconstruct", "validate", "verified_proof", "declared_format")):
        problems.append("format 3 lacks reconstruct / validate / verified_proof / declared_format")
    if problems:
        return {"state": FAIL, "detail": "journal format 3 differs from RFC §20.1 / §35", "problems": problems}
    return {"state": PASS, "detail": "format 3 carries a schema for all 29 event types; provider/request requires "
                                     "budget_owner under format 3 only; formats 1 (18) and 2 (25) unchanged"}


def _projections_match_rfc(rfc: RFC) -> dict:
    """F11: exactly the RFC's six control-critical projections, as a closed, read-only registry a gate reads by
    ControlProjection only."""
    want = rfc.control_projections()
    if len(want) != 6:
        return {"state": FAIL, "detail": "RFC reference for the six projections could not be extracted"}
    if not symbol_present("aisef2.journal.projections", "PROJECTIONS"):
        return {"state": None, "detail": "aisef2.journal.projections not implemented", "rfc_reference": want}
    mod = importlib.import_module("aisef2.journal.projections")
    reg = mod.PROJECTIONS
    got = [k.value for k in reg]
    if got != want:
        return {"state": FAIL, "detail": "the projection registry differs from the RFC's closed list",
                "rfc_reference": want, "implemented": got}
    bad = [k.value for k, p in reg.items() if getattr(p, "id", None) != k.value or isinstance(p.version, bool)
           or not isinstance(p.version, int) or not callable(p.initial) or not callable(p.step)]
    if bad:
        return {"state": FAIL, "detail": f"projections without an id, integer version, initial and step: {bad}"}
    try:
        reg["seventh"] = None
        return {"state": FAIL, "detail": "the registry accepts a seventh entry"}
    except TypeError:
        pass
    try:
        mod.project(None, want[0])
        return {"state": FAIL, "detail": "project() accepts a projection id that is not a ControlProjection"}
    except mod.ProjectionError:
        pass
    return {"state": PASS, "detail": "six projections equal the RFC's closed list in order; read-only registry; a "
                                     "gate reads them by ControlProjection only"}


def _timeout_semantics_match_rfc(rfc: RFC) -> dict:
    """F5 as amended by ARCHITECTURE-EXCEPTION-V2-002 (§9.2): a harness timeout is UNRUNNABLE; a subject that exceeds
    its bounded observation window is EXECUTED with the verdict the spec's observable assigns — never a default, never
    UNRUNNABLE. The reference is §9.2's own text; the implementation is exercised through the protocol."""
    section = rfc.section("### 9.2 Harness timeout vs subject observation deadline", "## 10. Two-axis")
    needed = ("`UNRUNNABLE`, owner **`ENVIRONMENT`**", "⇒ **`EXECUTED`**", "subject timeout ⇒ `REFUTED`",
              "`INVALID_SPEC`")
    if not section or not all(n in section for n in needed):
        return {"state": FAIL, "detail": "RFC reference (§9.2 harness timeout vs subject deadline) could not be extracted"}
    if not symbol_present("aisef2.probe.protocol", "ObservationKind"):
        return {"state": None, "detail": "aisef2.probe.protocol not implemented"}
    from aisef2.arch.enums import BehaviorVerdict as V, ProbeExecutionStatus as PES
    from aisef2.probe import protocol as P
    kinds = {k.name for k in P.ObservationKind}
    if "SUBJECT_DEADLINE" not in kinds:
        return {"state": FAIL, "detail": "the protocol cannot express a subject observation deadline"}
    spec = SimpleNamespace(probe_input={"subject_absence": "REQUIRES_SUBJECT"})
    problems = []
    for missing in (None, V.INDETERMINATE):
        try:
            P.Observation(P.ObservationKind.SUBJECT_DEADLINE, missing)
            problems.append(f"a subject deadline accepts {missing!r} (a default verdict)")
        except P.InvariantError:
            pass
    for v in (V.SATISFIED, V.REFUTED):
        r = P.classify_failure(spec, P.Observation(P.ObservationKind.SUBJECT_DEADLINE, v))
        if r.status is not PES.EXECUTED or r.behavior_verdict is not v:
            problems.append(f"a subject deadline with verdict {v.value} became {r}")
    if P.classify_failure(spec, P.Observation(P.ObservationKind.HARNESS_FAILED, detail="t")).status \
            is not PES.UNRUNNABLE:
        problems.append("a harness timeout is not UNRUNNABLE")
    if problems:
        return {"state": FAIL, "detail": "; ".join(problems)}
    return {"state": PASS, "detail": "harness timeout -> UNRUNNABLE; subject deadline -> EXECUTED with the spec's "
                                     "verdict, no default (§9.2)"}


def _semantic_hash_binds_subject_absence(rfc: RFC) -> dict:
    """F4 freezes the inputs to semantic_hash *including SubjectAbsence*: two contracts differing only in their
    declaration must compile to different semantic hashes."""
    row = next((ln for ln in rfc.section("## Normative freeze table", "## Adversarial").splitlines()
                if ln.startswith("| **F4**")), "")
    if "semantic_hash" not in row or "SubjectAbsence" not in row:
        return {"state": FAIL, "detail": "RFC reference (F4 row naming semantic_hash and SubjectAbsence) not found"}
    if not symbol_present("aisef2.product.compiler", "compile_spec"):
        return {"state": None, "detail": "aisef2.product.compiler.compile_spec not implemented"}
    from aisef2.arch.enums import Polarity, SubjectAbsence, SubjectKind
    from aisef2.product.approval import ContractApproval, Requirement
    from aisef2.product.compiler import ProbeRef, compile_spec
    from aisef2.product.contract import BehaviorContract, Subject
    req = Requirement.create(id="R", text="conformance", source="F4")
    hashes = {}
    for absence in SubjectAbsence:
        c = BehaviorContract.create(id="C", requirement_ids=("R",), subject=Subject(SubjectKind.FILE_ARTIFACT, "x"),
                                    stimulus={}, observable={"condition": "exists"}, polarity=Polarity.MUST_NOT_HOLD,
                                    subject_absence=absence, rationale="F4 conformance")
        a = ContractApproval("R", req.requirement_hash, "C", c.contract_hash, "human:conformance", 0.0, ())
        hashes[absence.value] = compile_spec(c, requirements={"R": req}, approvals=[a],
                                             probes={SubjectKind.FILE_ARTIFACT: ProbeRef("p", "d")}).semantic_hash
    if len(set(hashes.values())) != len(hashes):
        return {"state": FAIL, "detail": "semantic_hash does not bind SubjectAbsence", "hashes": hashes}
    return {"state": PASS, "detail": "semantic_hash differs for REQUIRES_SUBJECT and ABSENCE_IS_DECIDABLE"}


def _satisfaction_matches_rfc(rfc: RFC) -> dict:
    """F2 freezes the ContractSatisfaction derivation. The reference is the RFC's own §10.1 function, executed as
    written against the implementation's enums, and compared with `aisef2.product.outcome.contract_satisfaction`
    over every legal probe result and both candidate expectations. (The executed text is this repository's approved
    RFC; nothing external runs.)"""
    block = next((b for b in re.findall(r"```python\n(.*?)```", rfc.section("### 10.1", "### 10.2"), re.S)
                  if "def contract_satisfaction" in b), None)
    if block is None:
        return {"state": FAIL, "detail": "RFC reference (§10.1 contract_satisfaction) could not be extracted"}
    if not symbol_present("aisef2.product.outcome", "contract_satisfaction"):
        return {"state": None, "detail": "aisef2.product.outcome.contract_satisfaction not implemented"}
    from enum import Enum
    from types import SimpleNamespace
    from aisef2.arch.enums import BehaviorVerdict as V, ContractSatisfaction, ProbeExecutionStatus
    from aisef2.product import outcome as O

    class RFCInvariantError(Exception):
        pass
    ns = {"Enum": Enum, "ProbeExecutionStatus": ProbeExecutionStatus, "BehaviorVerdict": V,
          "InvariantError": RFCInvariantError, "ProbeResult": object, "ProductProofSpec": object}
    exec(compile(block, "RFC §10.1", "exec"), ns)  # noqa: S102 — the approved RFC's normative function
    reference = ns["contract_satisfaction"]

    def outcome(fn, result, spec):
        try:
            return fn(result, spec).value
        except (RFCInvariantError, O.InvariantError):
            return "InvariantError"
    results = [O.Executed(V.SATISFIED), O.Executed(V.REFUTED),
               O.Executed(V.INDETERMINATE, O.IndeterminateReason.PRECONDITION_ABSENT),
               O.Unrunnable("x"), O.InvalidSpec("x")]
    table, diffs = [], []
    for r in results:
        for e in (V.SATISFIED, V.REFUTED):
            spec = SimpleNamespace(candidate_expectation=e)
            want, got = outcome(reference, r, spec), outcome(O.contract_satisfaction, r, spec)
            table.append([r.status.value, getattr(r, "behavior_verdict", None) and r.behavior_verdict.value, e.value, want])
            if want != got:
                diffs.append({"result": repr(r), "expectation": e.value, "rfc": want, "implemented": got})
    if diffs or {c.value for c in ContractSatisfaction} != {row[3] for row in table} - {"InvariantError"}:
        return {"state": FAIL, "detail": "contract_satisfaction differs from the RFC §10.1 function", "diffs": diffs}
    return {"state": PASS, "detail": f"equals the RFC §10.1 function on all {len(table)} (result, expectation) pairs",
            "table": table}


class _StillRange:
    """A finished process range for the F5 §9.3 check: one exit status, and the ledger of what the controller sent."""

    def __init__(self, returncode, ledger):
        self.returncode, self.ledger = returncode, list(ledger)

    def wait(self, timeout=None):
        return self.returncode


def _signal_provenance_matches_rfc(rfc: RFC) -> dict:
    """F5 as amended by ARCHITECTURE-EXCEPTION-V2-003 (§9.3): after DISPATCHED the controller's own signal ledger
    decides, never the signal number. The controller's own signal is an interruption with no result; a signal it did
    not send is EXECUTED + INDETERMINATE(NON_CONTROLLER_SIGNAL) — never UNRUNNABLE, never ENVIRONMENT, never a
    verdict. The reference is §9.3's own text; the implementation is exercised on both paths (SIG-PROBE-8, -10)."""
    section = rfc.section("### 9.3 Signal provenance after dispatch", "## 10. Two-axis")
    needed = ("the controller's ledger holds the terminating signal", "an **interruption**, not a measurement",
              "`INDETERMINATE(NON_CONTROLLER_SIGNAL)`", "**MUST NOT** be `UNRUNNABLE`",
              "**MUST NOT** keep a second signal ledger")
    if not section or not all(n in section for n in needed):
        return {"state": FAIL, "detail": "RFC reference (§9.3 signal provenance after dispatch) could not be extracted"}
    if not symbol_present("aisef2.probe.python_callable", "_after_dispatch"):
        return {"state": None, "detail": "the reference probe's post-dispatch path is not implemented"}
    from aisef2.arch.enums import ProbeExecutionStatus as PES
    from aisef2.probe import protocol as P, python_callable as pc
    from aisef2.product import outcome as O
    spec = SimpleNamespace(probe_input={"subject_absence": "REQUIRES_SUBJECT"})
    problems, sig = [], -15
    if "NON_CONTROLLER_SIGNAL" not in {k.name for k in P.ObservationKind}:
        return {"state": FAIL, "detail": "the protocol cannot express a signal the controller did not send"}
    try:  # the same exit status the controller did not cause: an observation, indeterminate, with a typed reason
        observation = pc._ended_without_result(_StillRange(sig, []))
        result = P.classify_failure(spec, observation)
        if observation.kind is not P.ObservationKind.NON_CONTROLLER_SIGNAL or observation.verdict is not None:
            problems.append(f"a signal the controller did not send was observed as {observation.kind.value}")
        if (result.status, getattr(result, "reason", None)) != (PES.EXECUTED, O.IndeterminateReason.NON_CONTROLLER_SIGNAL):
            problems.append(f"a signal the controller did not send became {result}")
    except P.ProbeInterrupted:
        problems.append("a signal the controller did not send was read as an interruption")
    stopped = _StillRange(sig, [{"stage": "terminate", "signal": "SIGTERM"}])
    for what, offered in (("a signal exit", None), ("a completed observation", P.Observation(
            P.ObservationKind.OBSERVED, __import__("aisef2.arch.enums", fromlist=["x"]).BehaviorVerdict.REFUTED,
            detail="{}"))):
        try:  # the same exit status, this controller's own signal: an interruption, and no result at all
            made = pc._after_dispatch(stopped, offered if offered is not None
                                      else pc._ended_without_result(stopped))
            problems.append(f"the controller's own stop produced a result from {what}: {made.kind.value}")
        except P.ProbeInterrupted:
            pass
    if problems:
        return {"state": FAIL, "detail": "signal provenance differs from RFC §9.3", "problems": problems}
    return {"state": PASS, "detail": "the same signal exit is an interruption when this controller's ledger holds it "
                                     "and EXECUTED + INDETERMINATE(NON_CONTROLLER_SIGNAL) when it does not"}


class _ExitFirstRange:
    """A process range for the F5 §9.4 check whose exit is known before its output is read: `wait` answers at once,
    and the protocol lines become readable only after `wait` has been asked — the lifecycle channel first, always.
    Records whether the stream was exhausted when the exit was first asked for."""

    ledger: list = []

    def __init__(self, lines, returncode):
        import threading
        self._asked, self._lines, self.returncode = threading.Event(), list(lines), returncode
        self.exhausted_when_asked: list[bool] = []
        self._exhausted = False
        self.output = self._stream()

    def _stream(self):
        self._asked.wait(5)          # nothing is readable before the exit has been reported
        yield from self._lines
        self._exhausted = True

    def start(self):
        return self

    def wait(self, timeout=None):
        self.exhausted_when_asked.append(self._exhausted)
        self._asked.set()
        return self.returncode

    def release(self):
        pass


def _stream_lifecycle_matches_rfc(rfc: RFC) -> dict:
    """F5 as amended by ARCHITECTURE-EXCEPTION-V2-006 (§9.4): the protocol stream and the process lifecycle are
    independent facts. Structurally: the anchor gives up its copy of the target's output writer after the spawn, and
    the probe reads its protocol through one pump — no exit-driven reader. Behaviourally, on a range whose exit is
    reported before any line can be read: a complete protocol is observed as written, and a harness that wrote nothing
    is concluded not to have started only once its stream has closed."""
    section = rfc.section("### 9.4 Protocol stream vs process lifecycle", "## 10. Two-axis")
    needed = ("**MUST NOT** itself manufacture a protocol end of file", "pump-completion barrier",
              "**only** when the stream has closed, the exit has been reported", "No timing window **MAY** decide")
    if not section or not all(n in section for n in needed):
        return {"state": FAIL, "detail": "RFC reference (§9.4 protocol stream vs process lifecycle) could not be extracted"}
    if not symbol_present("aisef2.probe.python_callable", "_pump"):
        return {"state": None, "detail": "the reference probe's protocol reader is not implemented"}
    import os
    import sys as _sys
    import tempfile
    from unittest import mock
    from aisef2.arch.enums import BehaviorVerdict as V, ProbeExecutionStatus as PES
    from aisef2.probe import python_callable as pc
    from aisef2.probe.protocol import ExecutionEnv, RevisionRef, bound_result, run_probe
    from aisef2.product.spec import ProductProofSpec
    problems = []
    anchor = ast.parse((ROOT / "aisef2/runtime/range_anchor.py").read_text(encoding="utf-8"))
    fns = {n.name: n for n in anchor.body if isinstance(n, ast.FunctionDef)}
    release = fns.get("_release_output")
    dup2_to_stderr = release is not None and any(
        isinstance(n, ast.Call) and ast.unparse(n.func) == "os.dup2" and len(n.args) == 2 and ast.unparse(n.args[1]) == "2"
        for n in ast.walk(release))
    called = "main" in fns and any(isinstance(n, ast.Call) and ast.unparse(n.func) == "_release_output"
                                   for n in ast.walk(fns["main"]))
    if not (dup2_to_stderr and called):
        problems.append("the anchor keeps its copy of the target's output writer: the stream's end of file is not the target's")
    watch = next((n for n in ast.walk(ast.parse(inspect.getsource(pc))) if isinstance(n, ast.FunctionDef) and n.name == "_watch"), None)
    threads = [n for n in ast.walk(watch) if isinstance(n, ast.Call) and ast.unparse(n.func) == "threading.Thread"] if watch else []
    targets = [ast.unparse(k.value) for t in threads for k in t.keywords if k.arg == "target"]
    if targets != ["_pump"]:
        problems.append(f"the protocol is read by {targets or 'no reader'}, not by the one pump: an exit can end it")
    with tempfile.TemporaryDirectory(prefix="f5-9-4-") as root:
        spec = ProductProofSpec.create(
            contract_id="F5-9.4", probe_id=pc.PROBE_ID, probe_digest=pc.DIGEST,
            probe_input={"subject": {"kind": "python_callable", "locator": "app.calc:add"}, "stimulus": {},
                         "observable": {"condition": "exists", "within_s": 10}, "subject_absence": "ABSENCE_IS_DECIDABLE"},
            candidate_expectation=V.SATISFIED, compiler_id="conformance", compiler_digest="c" * 64)
        at, env = RevisionRef("0" * 40, root), ExecutionEnv(_sys.executable, 10, pc.Enforcement.PARTIAL)
        tags = [f"{pc._MARK} {t} n0nce {b}\n" for t, b in (("READY", ""), ("DISPATCHED", ""),
                                                           ("RESULT", '{"subject": "present", "resolved": true}'))]
        for name, lines, want in (("a complete protocol, exit reported first", tags, (PES.EXECUTED, "SATISFIED")),
                                  ("nothing written, exit 0 reported first", [], (PES.UNRUNNABLE, None))):
            fake = _ExitFirstRange(lines, 0)
            with mock.patch.multiple(pc, ProcessRange=mock.Mock(return_value=fake),
                                     secrets=mock.Mock(token_hex=mock.Mock(return_value="n0nce"))):
                record = run_probe(pc.PythonCallableProbe(), spec, at, env)
            result = bound_result(record, spec=spec, revision=at.sha, enforcement=env.required_enforcement)
            got = (result.status, getattr(getattr(result, "behavior_verdict", None), "value", None))
            if got != want:
                problems.append(f"{name}: {got[0].value}/{got[1]} instead of {want[0].value}/{want[1]}")
            if fake.exhausted_when_asked[:1] not in ([], [True]):
                problems.append(f"{name}: the exit was asked for before the stream had closed")
        if not os.path.isdir(root):
            problems.append("the conformance checkout vanished")
    if problems:
        return {"state": FAIL, "detail": "protocol stream vs process lifecycle differs from RFC §9.4", "problems": problems}
    return {"state": PASS, "detail": "the anchor holds no copy of the output writer; one pump reads the protocol; with the "
                                     "exit reported first a complete protocol is observed as written, and 'did not "
                                     "start' is concluded only after the stream closed"}


def _routing_matches_rfc(rfc: RFC) -> dict:
    """F2 freezes the owner routing table, keyed by measurement point since ARCHITECTURE-EXCEPTION-V2-001.

    References, all parsed from the RFC: the §10 table ("owner on failure"), its two normative routing sentences,
    and the §10.3 table (measurement point x outcome x role -> owner). Checked on the implementation at every
    measurement point and role: MUST_HOLD rows directly, MUST_NOT_HOLD by polarity symmetry (§10.1)."""
    s10 = rfc.section("## 10. Two-axis proof outcomes", "### 10.1")
    s103 = rfc.section("### 10.3 Owner routing by measurement point", "## 11.")
    rows10 = re.findall(r"^\| (EXECUTED|UNRUNNABLE|INVALID_SPEC|\*\(absent\)\*) \| (SATISFIED|REFUTED|INDETERMINATE|—) "
                        r"\| [^|]+ \| ([^|]+) \|$", s10, re.M)
    rows103 = re.findall(r"^\| (PARENT|CANDIDATE|POST_MERGE|any) \| ([^|]+) \| ([^|]+) \| ([^|]+) \| ([^|]+) \|$",
                         s103, re.M)
    rules = ("Only `UNRUNNABLE` **MAY** route to `ENVIRONMENT`", "`UNRUNNABLE` **MUST NOT** route to `DEVELOPER`",
             "**MUST NOT** be inferred\nfrom an `INDETERMINATE` reason alone")
    if len(rows10) != 6 or len(rows103) < 8 or not all(r in s10 + s103 for r in rules) \
            or "SATISFIED` at the candidate or after merge is not a failure" not in s103:
        return {"state": FAIL, "detail": "RFC reference (§10 table and rules, §10.3 table) could not be extracted"}
    if not symbol_present("aisef2.control.routing", "route"):
        return {"state": None, "detail": "aisef2.control.routing.route not implemented"}
    from itertools import product
    from types import SimpleNamespace
    from aisef2.arch.enums import BehaviorVerdict as V, MeasurementPoint as MP, ObligationRole, Owner
    from aisef2.control import routing as RT
    from aisef2.product import outcome as O
    owners = {o.value for o in Owner}
    hold, hold_not = SimpleNamespace(candidate_expectation=V.SATISFIED), SimpleNamespace(candidate_expectation=V.REFUTED)
    pa = O.Executed(V.INDETERMINATE, O.IndeterminateReason.PRECONDITION_ABSENT)
    ncs = O.Executed(V.INDETERMINATE, O.IndeterminateReason.NON_CONTROLLER_SIGNAL)  # §9.3, V2-003
    outcome_of = {"`INDETERMINATE(PRECONDITION_ABSENT)`": [pa], "`UNSATISFIED`": [O.Executed(V.REFUTED)],
                  "`INDETERMINATE(NON_CONTROLLER_SIGNAL)`": [ncs],
                  "`SATISFIED`, `UNSATISFIED`": [O.Executed(V.SATISFIED), O.Executed(V.REFUTED)],
                  "probe `UNRUNNABLE`": [O.Unrunnable("x")]}
    roles_of = {"INTRODUCE": [ObligationRole.INTRODUCE],
                "PRESERVE, VERIFY": [ObligationRole.PRESERVE, ObligationRole.VERIFY],
                "any admitted": list(ObligationRole), "any": list(ObligationRole)}
    problems, table = [], []

    def got(result, point, role):
        r = RT.route(result, hold, point, role)
        return (r.failure.owner.value if r.failure else None), r

    # §10.3, row by row
    for point, outcome, role, meaning, owner_cell in rows103:
        points = list(MP) if point == "any" else [MP(point)]
        want = next((n for n in owners if re.search(rf"\b{n}\b", owner_cell)), None)
        for p_, result, role_ in product(points, outcome_of.get(outcome.strip(), []), roles_of.get(role.strip(), [])):
            owner, r = got(result, p_, role_)
            table.append(["§10.3", p_.value, outcome.strip(), role_.value, owner, r.decided_by,
                          r.disposition and r.disposition.value])
            if "StoryAdmission disposition" in meaning:
                ok = r.failure is None and r.decided_by == RT.STORY_ADMISSION
            elif meaning.strip().startswith(("READY", "PRECONDITION_BROKEN")):
                ok = owner == want and r.disposition is not None and r.disposition.value == meaning.split()[0]
            else:
                ok = owner == want
            if not ok:
                problems.append(f"§10.3 {p_.value} {outcome.strip()} {role_.value}: RFC {want or meaning.strip()}, "
                                f"implemented {owner}")
        if not outcome_of.get(outcome.strip()) or not roles_of.get(role.strip()):
            problems.append(f"§10.3 row not understood: {point} | {outcome} | {role}")
    # §10.3: SATISFIED at the candidate or after merge is not a failure
    for p_ in (MP.CANDIDATE, MP.POST_MERGE):
        if got(O.Executed(V.SATISFIED), p_, None)[0] is not None:
            problems.append(f"{p_.value}: SATISFIED is charged to an owner")
    # §10 table: the rows §10.3 does not refine
    make = {("UNRUNNABLE", "—"): O.Unrunnable("x"), ("INVALID_SPEC", "—"): O.InvalidSpec("x"), ("*(absent)*", "—"): None}
    for status, verdict, cell in rows10:
        if (status, verdict) not in make:
            continue
        allowed = {n for n in owners if re.search(rf"\b{n}\b", cell)} or None
        for p_ in MP:
            owner, r = got(make[(status, verdict)], p_, None)
            table.append(["§10", p_.value, status, None, owner, r.decided_by, None])
            if (allowed is None and (r.failure is not None or r.decided_by is not None)) or \
                    (allowed is not None and owner not in allowed):
                problems.append(f"§10 {p_.value} {status}: RFC '{cell.strip()}', implemented {owner}")
    # §10.1: polarity symmetry at every point and role
    flip = {V.SATISFIED: V.REFUTED, V.REFUTED: V.SATISFIED}
    for p_, role_, v in product(MP, ObligationRole, (V.SATISFIED, V.REFUTED)):
        if RT.route(O.Executed(v), hold_not, p_, role_) != RT.route(O.Executed(flip[v]), hold, p_, role_):
            problems.append(f"{p_.value}/{role_.value}: MUST_NOT_HOLD {v.value} routes unlike MUST_HOLD {flip[v].value}")
    # §10 normative sentences, over everything routed above
    if {row[2] for row in table if row[4] == "ENVIRONMENT"} - {"UNRUNNABLE", "probe `UNRUNNABLE`"}:
        problems.append("a probe outcome other than UNRUNNABLE routes to ENVIRONMENT")
    if any(row[2] in ("UNRUNNABLE", "probe `UNRUNNABLE`") and row[4] == "DEVELOPER" for row in table):
        problems.append("UNRUNNABLE routes to DEVELOPER")
    if problems:
        return {"state": FAIL, "detail": "routing differs from the RFC §10 / §10.3 tables", "problems": problems,
                "table": table}
    return {"state": PASS, "detail": f"equals the RFC §10 and §10.3 tables on {len(table)} (point, outcome, role) "
                                     "rows, polarity-symmetric", "table": table}


def subchecks(rfc: RFC, code) -> list[dict]:
    e = rfc.enums
    V = _vocab
    S = []

    def add(item, sid, owner, result):
        S.append({"item": item, "id": sid, "implemented_by": owner, **result})

    add("F1", "F1.event_vocabulary", "WP-0.2", V("EventType", rfc.event_types(), code, by_value=True))
    for n in ("Vacuity", "Relevance", "AdequacyOutcome", "TestExecutionStatus", "TestOutcome", "TestSelection"):
        add("F1", f"F1.payload_enum.{n}", "WP-0.2", V(n, e.get(n, []), code))
    add("F1", "F1.event_envelope", "WP-3.1", _event_envelope_matches_rfc(rfc))
    add("F1", "F1.failure_taxonomy", "WP-6.2", _failure_taxonomy_matches_rfc(rfc))
    add("F1", "F1.journal_format_3", "WP-6.2", _journal_format_3_matches_rfc(rfc))
    for n in ("ProbeExecutionStatus", "BehaviorVerdict", "ContractSatisfaction"):
        add("F2", f"F2.enum.{n}", "WP-0.2", V(n, e.get(n, []), code))
    add("F2", "F2.enum.MeasurementPoint", "WP-1.4", V("MeasurementPoint", e.get("MeasurementPoint", []), code))
    add("F2", "F2.contract_satisfaction_derivation", "WP-1.3", _satisfaction_matches_rfc(rfc))
    add("F2", "F2.owner_routing_table", "WP-1.4", _routing_matches_rfc(rfc))
    add("F3", "F3.owner_set", "WP-0.2", V("Owner", e.get("Owner", []), code))
    for n in ("Polarity", "SubjectAbsence"):
        add("F4", f"F4.enum.{n}", "WP-0.2", V(n, e.get(n, []), code))
    add("F4", "F4.subject_kinds", "WP-0.2", V("SubjectKind", rfc.subject_kinds(), code, by_value=True))
    add("F4", "F4.subject_shape", "WP-1.1",
        _fields("aisef2.product.contract", "Subject", rfc.dataclasses.get("Subject")))
    add("F4", "F4.behavior_contract_shape", "WP-1.1",
        _fields("aisef2.product.contract", "BehaviorContract", rfc.dataclasses.get("BehaviorContract")))
    add("F4", "F4.product_proof_spec_shape", "WP-1.2",
        _fields("aisef2.product.spec", "ProductProofSpec", rfc.dataclasses.get("ProductProofSpec")))
    add("F4", "F4.semantic_hash_binds_subject_absence", "WP-1.2", _semantic_hash_binds_subject_absence(rfc))
    add("F5", "F5.enum.Enforcement", "WP-0.2", V("Enforcement", e.get("Enforcement", []), code))
    add("F5", "F5.probe_protocol", "WP-2.1", _protocol_matches_rfc(rfc, "aisef2.probe.protocol", "Probe"))
    add("F5", "F5.harness_timeout_vs_subject_deadline", "WP-2.1", _timeout_semantics_match_rfc(rfc))
    add("F5", "F5.signal_provenance_after_dispatch", "WP-2.1", _signal_provenance_matches_rfc(rfc))
    add("F5", "F5.protocol_stream_vs_process_lifecycle", "WP-2.1", _stream_lifecycle_matches_rfc(rfc))
    add("F5", "F5.calibration_contracts", "WP-2.2", _calibration_contracts_match_rfc(rfc))
    for n in ("ObligationRole", "ParentExpectation"):
        add("F6", f"F6.enum.{n}", "WP-0.2", V(n, e.get(n, []), code))
    add("F6", "F6.plan_obligation_shape", "WP-2.3",
        _fields("aisef2.plan.obligation", "PlanObligation", rfc.dataclasses.get("PlanObligation")))
    add("F7", "F7.dispositions", "WP-0.2",
        V("StoryAdmissionDisposition", e.get("StoryAdmissionDisposition", []), code))
    add("F8", "F8.scopes_and_lifetime_order", "WP-4.3", _lifetime_matches_rfc(rfc, code))
    add("F9", "F9.enum.IdentityGrade", "WP-0.2", V("IdentityGrade", e.get("IdentityGrade", []), code))
    add("F9", "F9.cited_identities_and_runspec", "WP-4.4", _runspec_matches_rfc(rfc))
    inv = rfc.invariants()
    add("F10", "F10.invariant_ids", "WP-0.2", V("InvariantId", list(inv), code, by_value=True))
    titles = [f"{k}:{v}" for k, v in inv.items()]
    add("F10", "F10.invariant_titles", "WP-0.2", V("__invariant_titles__", titles, code, by_value=True))
    add("F10", "F10.invariants_armed_with_mechanisms", "WP-5.5", _invariants_armed(list(inv) if len(inv) == 9 else None))
    add("F11", "F11.closed_projection_list", "WP-0.2",
        V("ControlProjection", rfc.control_projections(), code, by_value=True))
    add("F11", "F11.projections_implemented", "WP-3.4", _projections_match_rfc(rfc))
    return S


def evaluate(rfc_text: str, code, manifest: dict) -> dict:
    rfc = RFC(rfc_text)
    subs = subchecks(rfc, code)
    ratchet = []
    for s in subs:
        required = _reached(_phase_of(s["implemented_by"], manifest), manifest)
        s["required_now"] = required
        if s["state"] is None:  # implementation absent
            if required:
                s["state"] = FAIL
                s["detail"] += f" — but {s['implemented_by']} is in a phase already reached ({CURRENT_PHASE}): FAIL, not PENDING"
                ratchet.append(s["id"])
            else:
                s["state"] = PENDING
    items = []
    for fid in FROZEN_IDS:
        mine = [s for s in subs if s["item"] == fid]
        states = {s["state"] for s in mine}
        state = FAIL if (not mine or FAIL in states) else PENDING if PENDING in states else PASS
        items.append({"id": fid, "state": state, "subchecks": [s["id"] for s in mine],
                      "pending_on": sorted({s["implemented_by"] for s in mine if s["state"] == PENDING})})
    return {
        "record": "AISEF V2 — F1–F11 CONFORMANCE",
        "work_package": "WP-0.3",
        "current_phase": CURRENT_PHASE,
        "reference": "extracted from the RFC normative body; never transcribed",
        "items": items,
        "subchecks": subs,
        "summary": {s: sum(1 for i in items if i["state"] == s) for s in (PASS, PENDING, FAIL)},
        "ratchet_violations": ratchet,
    }


def load_inputs(root: pathlib.Path = ROOT):
    return ((root / RFC_REL).read_text(encoding="utf-8"), code_vocabularies(),
            json.loads((root / MANIFEST_REL).read_text(encoding="utf-8")))


def problems_of(result: dict) -> list[str]:
    out = [f"{i['id']} FAIL" for i in result["items"] if i["state"] == FAIL]
    out += [f"{s['id']}: {s['detail']}" for s in result["subchecks"] if s["state"] == FAIL]
    out += [f"{s['id']} is required now but is {s['state']}" for s in result["subchecks"]
            if s["required_now"] and s["state"] != PASS and s["state"] != FAIL]
    if [i["id"] for i in result["items"]] != FROZEN_IDS:
        out.append("items are not exactly F1–F11")
    for i in result["items"]:
        if i["state"] not in (PASS, FAIL, PENDING):
            out.append(f"{i['id']} has no definite state")
        if i["state"] == PASS and i["pending_on"]:
            out.append(f"{i['id']} reports PASS while pending on {i['pending_on']}")
    return out


def render(result: dict) -> str:
    return json.dumps(result, indent=1, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    result = evaluate(*load_inputs())
    problems = problems_of(result)
    if "--check" in argv:
        committed = ROOT / OUT_REL
        if not committed.exists():
            problems.append(f"{OUT_REL} is missing")
        elif committed.read_text(encoding="utf-8") != render(result):
            problems.append(f"{OUT_REL} is stale: regenerate it")
    for i in result["items"]:
        print(f"{i['state']:8s} {i['id']:4s}" + (f"  pending on {', '.join(i['pending_on'])}" if i["pending_on"] else ""))
    for p in problems:
        print(f"FAIL  {p}")
    print(f"summary {result['summary']} | ratchet violations {len(result['ratchet_violations'])}")
    if "--check" not in argv and not problems:
        (ROOT / OUT_REL).write_text(render(result), encoding="utf-8")
        print(f"wrote {OUT_REL}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
