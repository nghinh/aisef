"""Minimal scripted agent for the paired memory harness.

The directive forbids calling a real client unless credentials are
provided; none were. The harness therefore uses a deterministic scripted
agent whose:

- ``decide()`` consumes a scenario ``fixture`` plus the prior attempt's
  reasoning trace and emits an ``Attempt``: a list of small
  ``Decision`` records, gate results, ``verifier_findings``, errors, and
  arm-level heuristic checks. All inputs are JSON-serialisable.
- ``consume_memory()`` returns a deterministic yes/no/no-op tuple given a
  memory packet under arm B, or always ``False`` under arm A, or always
  raises ``ArmUnavailable`` under arm C.

The agent has no LLM call. It produces the *same* Attempt from the *same*
fixture plus state. Memory effects are simulated by replaying the
``scripted_outcomes`` block of each fixture: for arm A the harness
applies the scripted outcomes verbatim, for arm B it consults the local
memory to decide whether the existing convention/failure patterns apply
(that decision is *deterministic* because `LocalMemory.recall` is
deterministic given fixed state), for arm C no scripted outcomes are
produced (the arm reports unavailable).

This is a **scripted simulation**, not a causal efficacy measurement.
The directive explicitly says: "Need minimal llm-stub for scripted
simulation but do not call real client unless credentials provided;
treat as unavailable otherwise." The stub is the minimum required to
exercise the runner/scorer paths without an external API call.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

ARM_A = "A"
ARM_B = "B"
ARM_C = "C"


class ArmUnavailable(RuntimeError):
    """Raised when the C arm cannot satisfy the request."""


@dataclass(frozen=True)
class Decision:
    kind: str  # e.g., "uses_convention", "uses_failure_pattern", "review_blocks"
    target: str  # e.g., a memory record id
    score: float = 0.0
    note: str = ""


@dataclass(frozen=True)
class GateResult:
    gate: str
    outcome: str  # "PASS" | "FAIL" | "INVALID" | "BUDGET"
    note: str = ""


@dataclass(frozen=True)
class Attempt:
    arm: str
    scenario_id: str
    attempt_index: int
    decisions: tuple[Decision, ...]
    gate_results: tuple[GateResult, ...] = ()
    verifier_findings: tuple[tuple[str, str], ...] = ()
    errors: tuple[str, ...] = ()
    repeated_error_id: str | None = None
    budget_used: float = 0.0
    chars_injected: int = 0
    latencies_ms: tuple[float, ...] = ()
    outcome: str = "UNKNOWN"  # PASS/FAIL/BUDGET/UNAVAILABLE
    signature: str = ""

    def to_dict(self) -> dict:
        return {
            "arm": self.arm,
            "scenario_id": self.scenario_id,
            "attempt_index": self.attempt_index,
            "decisions": [{"kind": d.kind, "target": d.target, "score": d.score, "note": d.note}
                          for d in self.decisions],
            "gate_results": [{"gate": g.gate, "outcome": g.outcome, "note": g.note}
                             for g in self.gate_results],
            "verifier_findings": [{"id": vid, "kind": vkind} for vid, vkind in self.verifier_findings],
            "errors": list(self.errors),
            "repeated_error_id": self.repeated_error_id,
            "budget_used": round(self.budget_used, 6),
            "chars_injected": self.chars_injected,
            "latencies_ms": list(self.latencies_ms),
            "outcome": self.outcome,
            "signature": self.signature,
        }


def _signature(arm: str, scenario_id: str, n: int, payload: Any) -> str:
    body = {"arm": arm, "scenario_id": scenario_id, "attempt": n, "payload": payload}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False,
                                    default=str).encode("utf-8")).hexdigest()[:16]


def scripted_arm_A(fixture: dict, scenario_id: str, attempt_index: int) -> Attempt:
    """Arm A: memory off. Replay the scripted ``uses_*`` decision literally.

    The scripted outcomes describe a deterministic agent, so under arm A the
    harness reads them in order and records the same decision each attempt.
    This is the **baseline**: it cannot benefit from memory because it has
    no memory. Whatever repeated-error rate shows here is *baseline*.

    Note: scripted-outcome replay is invariant across attempts. The harness
    still runs N attempts per scenario to compute the variance contributed
    by the harness itself (deterministic), not by the agent.
    """
    sequence = fixture.get("story_sequence", [])
    if attempt_index >= len(sequence):
        # extra attempts are replay rolls of the last story
        outcome = fixture.get("scripted_outcomes", [])[-1] if fixture.get("scripted_outcomes") else {}
    else:
        outcome = fixture.get("scripted_outcomes", [{} for _ in sequence])[attempt_index]
    decisions = []
    if outcome.get("uses_convention"):
        decisions.append(Decision("uses_convention", "CONVENTION_BOUNDED_RETRY"))
    if outcome.get("uses_failure_pattern"):
        decisions.append(Decision("uses_failure_pattern", "FAILURE_MIGRATION_TX"))
    if outcome.get("review_blocks"):
        decisions.append(Decision("review_blocks", "REVIEW_NULL_BOUNDARY"))
    if outcome.get("security_blocks"):
        decisions.append(Decision("security_blocks", "SECURITY_AUTHZ_OWNERSHIP"))
    if outcome.get("reuses_tool_env"):
        decisions.append(Decision("reuses_tool_env", "TOOL_ENV_ISOLATED"))
    if outcome.get("uses_old_advice"):
        decisions.append(Decision("uses_old_advice", "ARCH_OLD"))

    gates = (GateResult("scope", "PASS", ""),
             GateResult("read-only-fallback", "PASS" if outcome.get("uses_old_advice") is False or
                       not outcome.get("supersession_event") else "FAIL",
                       "would re-read superseded advice"))
    findings = (
        ("F2P", "f2p_pass" if outcome.get("f2p_pass") is None
         else f"{outcome.get('f2p_pass')}/{outcome.get('f2p_total')}"),
    ) if "f2p_pass" in outcome else ()
    rep_id = outcome.get("repeated_error_id")
    attempted = Attempt(
        arm=ARM_A, scenario_id=scenario_id, attempt_index=attempt_index,
        decisions=tuple(decisions), gate_results=gates,
        verifier_findings=findings,
        repeated_error_id=rep_id,
        budget_used=float(outcome.get("budget_used", 0.0)),
        chars_injected=0, latencies_ms=(0.0,),
        outcome="PASS" if not rep_id else "FAIL",
        signature=_signature(ARM_A, scenario_id, attempt_index,
                              {"outcome": outcome, "decisions": [d.__dict__ for d in decisions]}),
    )
    return attempted


def scripted_arm_B(fixture: dict, scenario_id: str, attempt_index: int,
                   memory_payload: dict | None) -> Attempt:
    """Arm B: local memory on. The scripted agent consults memory.

    A real agent would call `LocalMemory.recall(...)`; here we simulate
    that by replaying the *deterministic* content of the local store, then
    emitting decisions consistent with ``scripted_outcomes`` AND with what
    the memory packet contained. The repeated_error_id comes from
    ``expected_repeated_behavior_id`` if memory lacked the relevant
    record; otherwise no repeated error.
    """
    base = scripted_arm_A(fixture, scenario_id, attempt_index)
    chars = 0
    packet_selected_refs: list[str] = []
    packet_selected_ids: list[str] = []
    if memory_payload and isinstance(memory_payload, dict):
        chars = int(memory_payload.get("chars", 0))
        for s in memory_payload.get("selected", []) or []:
            if isinstance(s, dict):
                packet_selected_refs.append(s.get("source", ""))
                packet_selected_ids.append(s.get("id", ""))
            else:
                packet_selected_refs.append("")
                packet_selected_ids.append("")

    relevant_source_refs = {record["source_ref"] for record in fixture.get("memory_records", [])}
    memory_had_relevant = any(ref in relevant_source_refs for ref in packet_selected_refs)
    expected_repeated_id = fixture.get("expected_repeated_behavior_id")
    rep_id = None if memory_had_relevant else expected_repeated_id
    augmented_decisions = list(base.decisions)
    if memory_had_relevant:
        for _sid, ref in zip(packet_selected_ids, packet_selected_refs, strict=True):
            for record in fixture.get("memory_records", []):
                if record.get("source_ref") == ref:
                    augmented_decisions.append(Decision("memory_recalled", record["id"]))
                    break

    supersede_event = fixture.get("scripted_outcomes", [{}])[min(attempt_index,
                          len(fixture.get("scripted_outcomes", [])) - 1)].get("supersession_event")
    if supersede_event and memory_had_relevant:
        active_id = supersede_event.get("active_id", "ARCH_OLD")
        augmented_decisions = [d for d in augmented_decisions if d.target != active_id] + \
            [Decision("uses_new_advice", "ARCH_NEW")]

    findings = list(base.verifier_findings)
    if rep_id:
        findings.append(("repeated_error", f"missed {rep_id}"))

    return Attempt(
        arm=ARM_B, scenario_id=scenario_id, attempt_index=attempt_index,
        decisions=tuple(augmented_decisions), gate_results=base.gate_results,
        verifier_findings=tuple(findings),
        errors=base.errors,
        repeated_error_id=rep_id,
        budget_used=base.budget_used + 0.02 * (chars > 0),
        chars_injected=chars,
        latencies_ms=(float(memory_payload.get("latency_ms", 0.0)) if memory_payload else 0.0,),
        outcome=base.outcome if not rep_id else "FAIL",
        signature=_signature(ARM_B, scenario_id, attempt_index,
                              {"selected_refs": packet_selected_refs,
                               "decisions": [d.__dict__ for d in augmented_decisions],
                               "rep": rep_id}),
    )


def scripted_arm_C(fixture: dict, scenario_id: str, attempt_index: int) -> Attempt:
    """Arm C: OpenViking.

    Per the parent directive, C must never be silently downgraded. The
    `OpenVikingAdapter` is not implemented in this harness (ADR-007 R2
    leaves the remote adapter deferred). C therefore raises
    ``ArmUnavailable`` rather than returning a fake result; the runner
    catches this and records ``status='unavailable'``.
    """
    raise ArmUnavailable(
        f"arm C (OpenViking) unavailable for scenario {scenario_id}; not downgrading to local."
    )


def _expected_relevant_ids(fixture: dict) -> Iterable[str]:
    for record in fixture.get("memory_records", []):
        yield record.get("id", "")


def consume_memory(arm: str) -> bool:
    """Whether the agent can consult memory in this arm. A=no, B=yes, C=no."""
    if arm == ARM_A:
        return False
    if arm == ARM_B:
        return True
    if arm == ARM_C:
        # C has its own provider, not local
        return False
    raise ValueError(f"unknown arm: {arm!r}")


def arm_label(arm: str) -> str:
    return {ARM_A: "memory off (baseline)", ARM_B: "memory on, local only",
            ARM_C: "memory on, OpenViking (unavailable)"}[arm]
