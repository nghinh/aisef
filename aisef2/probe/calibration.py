"""RFC §9.1 — calibration: two contracts, each demonstrating CONTRAST to the candidate expectation (F5).

* **Contrast, not a fixed verdict** (§9.1, CAL-1). A counterexample must produce the verdict *opposite* to the spec's
  `candidate_expectation`: `SATISFIED` expected -> the counterexample must be `REFUTED`; `REFUTED` expected -> it must
  be `SATISFIED`. "Observed producing REFUTED" would qualify a probe that always returns REFUTED — for a
  MUST_NOT_HOLD contract that is exactly the probe calibration exists to reject.
* **`ProbeCapabilityCalibration`** (§9.1.1) qualifies a probe implementation *at a digest* for one observation class,
  against a committed positive fixture (the observable IS present) and a committed negative one (it is ABSENT). The
  positive fixture is the counterexample for a REFUTED expectation, the negative one for a SATISFIED expectation, so a
  record exists only when both contrasts are demonstrated: one record qualifies the class for both polarities, and a
  probe that cannot produce both verdicts is not qualified (`NotQualified`).
* **`SpecFalsifiabilityEvidence`** (§9.1.2) qualifies one spec against a controlled counterexample. It belongs to
  qualification (Q2), **never** to plan freeze (CAL-2): nothing in the planning plane takes it.

A fixture is a directory holding `request.json` — the probe input (subject, stimulus, observable, subject_absence) —
and `checkout/`, the revision the probe looks at.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass
from typing import Callable

from aisef2.arch.enums import BehaviorVerdict, Enforcement
from aisef2.errors import InvariantError
from aisef2.probe.protocol import ExecutionEnv, Probe, ProbeRegistry, RevisionRef, bound_result, run_probe
from aisef2.product.outcome import Executed
from aisef2.product.spec import ProductProofSpec

MECHANISMS = ("controlled_product_mutation", "fixture_construction", "other_qualified")
#: expectation -> the verdict a counterexample must produce (§9.1 general rule)
CONTRAST = {BehaviorVerdict.SATISFIED: BehaviorVerdict.REFUTED, BehaviorVerdict.REFUTED: BehaviorVerdict.SATISFIED}
#: A fixture checkout is not a commit; calibration names it by this placeholder revision.
FIXTURE_REVISION = "0" * 40


@dataclass(frozen=True, slots=True)
class ProbeCapabilityCalibration:
    probe_id: str
    probe_digest: str
    observation_class: str
    positive_fixture: str
    negative_fixture: str
    demonstrated_at: float


@dataclass(frozen=True, slots=True)
class SpecFalsifiabilityEvidence:
    spec_id: str
    semantic_hash: str
    mechanism: str
    counterexample_ref: str
    observed: BehaviorVerdict

    def __post_init__(self) -> None:
        if self.mechanism not in MECHANISMS:
            raise InvariantError(f"mechanism must be one of {MECHANISMS}")
        if not isinstance(self.observed, BehaviorVerdict):
            raise InvariantError("observed is a BehaviorVerdict")
        if not self.counterexample_ref:
            raise InvariantError("a counterexample is named by a journal or fixture locator")


class NotQualified(InvariantError):
    """The probe did not demonstrate contrast for this observation class; no calibration record exists."""


def demonstrates_contrast(expectation: BehaviorVerdict, observed: BehaviorVerdict) -> bool:
    """§9.1: the counterexample's verdict is the opposite of the expectation — never a fixed verdict."""
    if expectation not in CONTRAST:
        raise InvariantError("a candidate expectation is SATISFIED or REFUTED")
    return observed is CONTRAST[expectation]


def falsifiability_problems(evidence: SpecFalsifiabilityEvidence, spec: ProductProofSpec) -> list[str]:
    """Why `evidence` does not qualify `spec` (§9.1.2); empty when it does."""
    out = []
    if (evidence.spec_id, evidence.semantic_hash) != (spec.id, spec.semantic_hash):
        out.append("the evidence is for another spec or another semantic_hash")
    if not demonstrates_contrast(spec.candidate_expectation, evidence.observed):
        out.append(f"observed {evidence.observed.value} does not contrast with the expectation "
                   f"{spec.candidate_expectation.value}")
    return out


def fixture_spec(probe: Probe, fixture: pathlib.Path) -> ProductProofSpec:
    """The spec a fixture's request describes, bound to `probe`. It answers no contract: its expectation is a carrier."""
    request = json.loads((fixture / "request.json").read_text(encoding="utf-8"))
    return ProductProofSpec.create(contract_id=f"CALIBRATION:{fixture.name}", probe_id=probe.id,
                                   probe_digest=probe.digest, probe_input=request,
                                   candidate_expectation=BehaviorVerdict.SATISFIED, compiler_id="calibration",
                                   compiler_digest="0" * 64)


def calibrate(probe: Probe, observation_class: str, positive: pathlib.Path, negative: pathlib.Path,
              env: ExecutionEnv, clock: Callable[[], float], *, registry: ProbeRegistry,
              names: tuple[str, str] | None = None) -> ProbeCapabilityCalibration:
    """§9.1.1: run `probe` on both committed fixtures; issue a record only if both contrasts are demonstrated.

    The positive fixture must be observed SATISFIED — the counterexample for a REFUTED expectation — and the negative
    one REFUTED — the counterexample for a SATISFIED expectation. The observation class each fixture asks for is the
    harness registry's (PROBE-META-1), and each result is read through its bound record (PROBE-BIND-1). `names` are
    the committed fixture paths recorded.
    """
    problems = []
    for side, fixture, counter_for in (("positive", positive, BehaviorVerdict.REFUTED),
                                       ("negative", negative, BehaviorVerdict.SATISFIED)):
        spec = fixture_spec(probe, fixture)
        asked = registry.observation_class(probe.id, probe.digest, spec)
        if asked != observation_class:
            problems.append(f"{side} fixture asks for {asked!r}, not {observation_class!r}")
            continue
        at = RevisionRef(FIXTURE_REVISION, str((fixture / "checkout").resolve()))
        result = bound_result(run_probe(probe, spec, at, env), spec=spec, revision=at.sha,
                              enforcement=probe.enforcement())
        if not isinstance(result, Executed) or not demonstrates_contrast(counter_for, result.behavior_verdict):
            problems.append(f"{side} fixture observed {result} — no contrast with a {counter_for.value} expectation")
    if problems:
        raise NotQualified(f"{probe.id}@{probe.digest[:12]} is not qualified for {observation_class!r}: "
                           + "; ".join(problems))
    pos, neg = names or (str(positive), str(negative))
    return ProbeCapabilityCalibration(probe.id, probe.digest, observation_class, pos, neg, float(clock()))


def calibration_for(calibrations, probe_id: str, probe_digest: str, observation_class: str
                    ) -> ProbeCapabilityCalibration | None:
    """The record qualifying (probe id, digest, class), if any: a record for another digest qualifies nothing."""
    return next((c for c in calibrations if isinstance(c, ProbeCapabilityCalibration)
                 and (c.probe_id, c.probe_digest, c.observation_class) == (probe_id, probe_digest, observation_class)),
                None)


def calibration_env(interpreter: str) -> ExecutionEnv:
    return ExecutionEnv(interpreter, 30.0, Enforcement.PARTIAL)
