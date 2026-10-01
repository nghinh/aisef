"""RFC §28, §29, §30 — the preregistration record: its schema, validator and hash, and the identity it is sealed under.

A preregistration is written and hashed before any run. It freezes, each as its own content (`FROZEN_INPUTS`, RFC §28
order): kernel identity; workload identity; requirements; plan policy; execution profile (content-addressed, §23);
prompts; model route; run count; thresholds; oracle; metrics; and the PlanQualityPolicy (§29). `frozen_inputs` maps each
name to the sha256 of its canonical content; `preregistration_hash` is the sha256 of the whole record.

* The execution profile is a resolved RunSpec's content (`execution_profile`). `runspec_of` re-resolves it through
  aisef2.runtime.runspec and refuses content that does not re-derive itself: the profile is addressed by its content,
  its aggregate grade is computed, never declared.
* A workload is identified by its frozen identity — requirements sha256, plan baseline, plan hash — and two identities
  sharing any one component are the same workload (`shared`). A name is metadata, never identity.
* `DEVELOPMENT_REGRESSION` lists the workloads that are development / regression benchmarks permanently (RFC §30):
  LedgerLock, by the identity its frozen records carry. validation/v2/cohort_static_checks.py binds every value to the
  file it is read from.
"""

from __future__ import annotations

import re
from dataclasses import fields
from enum import Enum
from typing import Any, Mapping

from aisef2.arch.enums import Enforcement, IdentityGrade
from aisef2.plan.obligation import PlanQualityPolicy
from aisef2.product.contract import digest, freeze, plain
from aisef2.runtime.capability import CapabilityIdentity
from aisef2.runtime.runspec import RunSpec, resolve

SCHEMA = "aisef2.cohort.preregistration/1"
_HEX40 = re.compile(r"[0-9a-f]{40}")
_HEX64 = re.compile(r"[0-9a-f]{64}")


class Refusal(Enum):  # cohort-local: carried in no event, so no F1 payload enum gains a member
    PREREGISTRATION_INVALID = "PREREGISTRATION_INVALID"
    OPAQUE_PROFILE = "OPAQUE_PROFILE"
    DEVELOPMENT_REGRESSION = "DEVELOPMENT_REGRESSION"
    WORKLOAD_DEMOTED = "WORKLOAD_DEMOTED"
    WORKLOAD_OBSERVED = "WORKLOAD_OBSERVED"
    WORKLOAD_ALREADY_SEALED = "WORKLOAD_ALREADY_SEALED"
    PREREGISTRATION_REUSED = "PREREGISTRATION_REUSED"
    COHORT_INCONSISTENT = "COHORT_INCONSISTENT"
    NOT_FORWARD = "NOT_FORWARD"
    NOT_EVALUATING = "NOT_EVALUATING"
    PREREGISTRATION_STALE = "PREREGISTRATION_STALE"
    RUN_DUPLICATE = "RUN_DUPLICATE"
    RUNS_COMPLETE = "RUNS_COMPLETE"
    GENERALIZATION_REFUSED = "GENERALIZATION_REFUSED"


class CohortRefused(Exception):
    """A typed refusal: `code` names the rule that refused, `why` the facts."""

    def __init__(self, code: Refusal, why: str) -> None:
        super().__init__(f"{code.value}: {why}")
        self.code = code
        self.why = why


def _hex40(v: Any) -> bool:
    return isinstance(v, str) and _HEX40.fullmatch(v) is not None


def _hex64(v: Any) -> bool:
    return isinstance(v, str) and _HEX64.fullmatch(v) is not None


def _name(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


def _count(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v >= 1


def _names(v: Any) -> bool:
    return isinstance(v, (list, tuple)) and bool(v) and all(_name(x) for x in v) and len(set(v)) == len(v)


#: Every frozen input with the shape of its content, in RFC §28 order; None: validated by its own function below.
SHAPES: dict[str, Any] = {
    "kernel": {"aisef2_tree": _hex40},
    "workload": {"name": _name, "plan_baseline": _hex40, "plan_hash": _hex64},
    "requirements": {"sha256": _hex64},
    "plan_policy": {"sha256": _hex64},
    "execution_profile": None,
    "prompts": {"sha256": _hex64},
    "model_route": {"capability": _name, "route": _name},
    "run_count": _count,
    "thresholds": {"delivery": _name},
    "oracle": {"sha256": _hex64},
    "metrics": _names,
    "plan_quality_policy": None,
}
FROZEN_INPUTS = tuple(SHAPES)
IDENTITY = ("requirements_sha256", "plan_baseline", "plan_hash")

#: RFC §30 — DEVELOPMENT / REGRESSION workloads, permanently: never sealed, never re-labelled. Identified by the frozen
#: identity their records carry; the label only names the entry in a refusal.
DEVELOPMENT_REGRESSION: tuple[dict[str, str], ...] = (
    {"label": "LedgerLock",
     "requirements_sha256": "3a6a99959bbc6cf39c4d4afa9c2de222925fdcaad30aaf3fa2d04ee446597ecc",
     "plan_baseline": "136a68dcdc3f416b2a76c561a7df12d1282ad4d5",
     "plan_hash": "bc71a701dd84f7227e8a474b9c9e0aec05ca3e10c0eb53168bcdba0bb8242a32",
     "requirements_source": "tests/v2/fixtures/workloads/ledgerlock-reference/REQUIREMENTS.md",
     "workload_record": "closure-evidence/v2/P10/WORKLOAD.json",
     "workload_record_sha256": "d43211043dd141d388250eb756e2e6d40720093d8f091042944da4babd861463"},
)


def execution_profile(spec: RunSpec) -> dict:
    """The content-addressed execution profile of a resolved RunSpec: its content, and the hash that addresses it."""
    return {"capabilities": [c.content() for c in spec.capabilities],
            "aggregate_min_grade": spec.aggregate_min_grade.value, "settings": plain(spec.settings),
            "runspec_hash": spec.runspec_hash}


def runspec_of(profile: Any) -> RunSpec:
    """The RunSpec an execution profile denotes, re-resolved from its content; refused unless the content re-derives
    exactly itself — capabilities, aggregate grade, settings and hash (RFC §23: the grade is computed, never declared)."""
    try:
        caps = [CapabilityIdentity(c["name"], IdentityGrade(c["grade"]), c["tuple"], Enforcement(c["enforcement"]))
                for c in profile["capabilities"]]
        settings = dict(profile["settings"])
        revision = settings.pop("revision")["value"]
        spec = resolve(caps, settings, revision)
    except (KeyError, TypeError, ValueError) as e:
        raise CohortRefused(Refusal.PREREGISTRATION_INVALID, f"execution_profile: {e!r}") from None
    if execution_profile(spec) != plain(profile):
        raise CohortRefused(Refusal.PREREGISTRATION_INVALID, "execution_profile does not re-derive from its content")
    return spec


def policy_of(value: Any) -> PlanQualityPolicy:
    """The preregistered PlanQualityPolicy (§29): exactly its three thresholds, each None or a valid limit."""
    if not isinstance(value, Mapping) or set(value) != {f.name for f in fields(PlanQualityPolicy)}:
        raise CohortRefused(Refusal.PREREGISTRATION_INVALID, "plan_quality_policy is malformed")
    try:
        return PlanQualityPolicy(**value)
    except ValueError as e:
        raise CohortRefused(Refusal.PREREGISTRATION_INVALID, f"plan_quality_policy: {e}") from None


def problems(record: Any) -> list[str]:
    """Every way `record` is not a preregistration; [] when it is one."""
    if not isinstance(record, Mapping):
        return ["a preregistration is a JSON object"]
    want = {"schema", "cohort_id", *FROZEN_INPUTS}
    out = [f"missing {k}" for k in sorted(want - set(record))] + [f"unknown {k}" for k in sorted(set(record) - want)]
    if record.get("schema") != SCHEMA:
        out.append(f"schema is not {SCHEMA}")
    if not _name(record.get("cohort_id")):
        out.append("cohort_id is not a name")
    for key, shape in SHAPES.items():
        if key not in record or shape is None:
            continue
        value = record[key]
        if callable(shape):
            ok = shape(value)
        else:
            ok = isinstance(value, Mapping) and set(value) == set(shape) and all(f(value[k]) for k, f in shape.items())
        if not ok:
            out.append(f"{key} is malformed")
    for key, check in (("execution_profile", runspec_of), ("plan_quality_policy", policy_of)):
        if key in record:
            try:
                check(record[key])
            except CohortRefused as e:
                out.append(e.why)
    if not out:
        bound = {c.name: c.tuple_.get("route") for c in runspec_of(record["execution_profile"]).capabilities}
        if bound.get(record["model_route"]["capability"]) != record["model_route"]["route"]:
            out.append("model_route is not a route the execution profile binds")
    return out


def validate(record: Any) -> Mapping[str, Any]:
    """The frozen preregistration, or PREREGISTRATION_INVALID naming every problem."""
    found = problems(record)
    if found:
        raise CohortRefused(Refusal.PREREGISTRATION_INVALID, "; ".join(found))
    return freeze(record)


def preregistration_hash(record: Mapping[str, Any]) -> str:
    return digest(record)


def frozen_inputs(record: Mapping[str, Any]) -> dict[str, str]:
    """RFC §28 `frozen_inputs`: each frozen input's name -> the sha256 of its canonical content."""
    return {k: digest(record[k]) for k in FROZEN_INPUTS}


def workload_identity(record: Mapping[str, Any]) -> dict[str, str]:
    """The frozen workload identity a preregistration names."""
    return {"requirements_sha256": record["requirements"]["sha256"],
            "plan_baseline": record["workload"]["plan_baseline"], "plan_hash": record["workload"]["plan_hash"]}


def shared(a: Mapping[str, str], b: Mapping[str, str]) -> list[str]:
    """The identity components two workload identities share; any one makes them the same workload."""
    return [k for k in IDENTITY if a[k] == b[k]]


def development_regression(record: Mapping[str, Any]) -> str | None:
    """Why the workload `record` names is a DEVELOPMENT_REGRESSION workload (RFC §30), or None."""
    identity = workload_identity(record)
    for entry in DEVELOPMENT_REGRESSION:
        same = shared(identity, entry)
        if same:
            return f"{entry['label']} is a development / regression benchmark permanently (RFC §30); same {', '.join(same)}"
    return None
