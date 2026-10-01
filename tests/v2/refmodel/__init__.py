"""WP-3.5 — independent reference models of the six control-critical projections (RFC §21, F11).

Each module is written from docs/implementation/v2/P3-PROJECTION-SEMANTICS.md (normative) and the frozen RFC alone,
never from the projections it checks, and imports nothing but the standard library and this package. A model takes
the whole reconstructed journal as plain event dicts and returns the projection's final state in the spec's JSON
shape, or raises `Refused` where the spec says the projection refuses. No model reads `time`.

`CALIBRATION` (one list per module): known journals, the state the spec prescribes for each (or "REFUSED"), and the
answer an implementation with one named defect would give instead — RFC §21: a reference model is calibrated by
being observed producing the opposite answer on a known input.
"""

import copy


class Refused(Exception):
    """The spec says the projection refuses this journal: it has no state for it."""


#: RFC §22 — the taxonomy fixes owner and retryable per code; calibration journals carry them as the writer would.
TAXONOMY = {
    "PROBE_UNRUNNABLE": ("ENVIRONMENT", True),
    "PROBE_INVALID_SPEC": ("INTEGRATION", False),
    "CONTRACT_UNSATISFIED": ("DEVELOPER", True),
    "SUBJECT_ABSENT_AT_CANDIDATE": ("DEVELOPER", True),
    "PRECONDITION_BROKEN": ("PLAN", False),
    "PLAN_CONTRADICTION": ("PLAN", False),
    "POST_MERGE_REGRESSION": ("INTEGRATION", False),
    "POST_MERGE_SUBJECT_LOST": ("INTEGRATION", False),
    "MISSING_CREDENTIAL": ("ENVIRONMENT", True),
    "INVALID_CREDENTIAL": ("ENVIRONMENT", False),
    "PROVIDER_UNAVAILABLE": ("PROVIDER", True),
    "UNKNOWN": ("INTEGRATION", False),
    # ARCHITECTURE-EXCEPTION-V2-005 (owner resolution §7) — journal format 3 only
    "VERIFIER_DISAGREEMENT": ("INTEGRATION", False),
    "PROBE_MISMATCH": ("INTEGRATION", False),
    "MERGE_CONFLICT": ("INTEGRATION", False),
    "TESTS_UNRUNNABLE": ("ENVIRONMENT", True),
    "TESTS_INADEQUATE": ("DEVELOPER", True),
    "REVIEW_FINDING": ("REVIEW", True),
    "SECURITY_FINDING": ("SECURITY", True),
    "CAPABILITY_UNRUNNABLE": ("ENVIRONMENT", True),
    "RESOURCE_ACQUISITION_FAILED": ("ENVIRONMENT", True),
}
#: RFC §13 — dispositions that block a story's admission.
BLOCKING = frozenset({"PRECONDITION_BROKEN", "PLAN_CONTRADICTION", "PROBE_UNRUNNABLE", "PROBE_INVALID"})
SHA = "a" * 40


class Run:
    """A calibration journal under construction. Every method appends one event and returns its seq. The journal
    declares format 1 unless told otherwise; a format-3 run's provider requests name their `budget_owner`."""

    def __init__(self, journal_format=1):
        self.events = []
        self.add("run/begin", {"journal_format": journal_format, "run_id": "refmodel-calibration"})

    def add(self, type_, data, cites=()):
        seq = len(self.events)
        # written, never read: the clock is the seq, and no model looks at it
        self.events.append(dict(seq=seq, type=type_, data=data, time=float(seq), ignorable=False,
                                source_seqs=list(cites)))
        return seq

    def plan(self, roles):
        return self.add("plan/frozen", {"plan_id": "PLAN-CAL", "plan_hash": "b" * 64, "roles": roles})

    def begin(self, story):
        return self.add("story/begin", {"story_id": story, "parent": SHA})

    def admit(self, story, dispositions):
        admitted = not any(d in BLOCKING for d in dispositions.values())
        return self.add("story/admitted", {"story_id": story, "parent": SHA, "admitted": admitted,
                                           "developer_call_permitted": admitted and "READY" in dispositions.values(),
                                           "dispositions": dispositions})

    def fail(self, story, code):
        owner, retryable = TAXONOMY[code]
        data = {"story_id": story, "code": code, "owner": owner, "retryable": retryable, "detail": f"{code} in {story}"}
        if code == "UNKNOWN":
            data["original"] = "OSError"
        return self.add("failure/observed", data)

    def request(self, story, criteria, budget_owner=None):
        data = {"story_id": story, "criteria": criteria}
        if budget_owner is not None:
            data["budget_owner"] = budget_owner
        return self.add("provider/request", data)

    def probe(self, story, criterion, verdict="SATISFIED"):
        """A `probe/evaluated` carrying a sealed-shaped record of the story's criterion (§10.1)."""
        record = {"spec_id": f"PPS-{criterion}", "semantic_hash": "c" * 64, "probe_id": "probe.x", "probe_digest": "d" * 64,
                  "revision": SHA, "enforcement": "FULL", "result": {"behavior_verdict": verdict, "reason": None},
                  "record_digest": "e" * 64}
        return self.add("probe/evaluated", {"story_id": story, "criterion_id": criterion, "record": record})

    def proof(self, story, criterion, verdict="SATISFIED"):
        """A format-3 `proof/verified` (V2-005 §3) citing two probe records of the story's criterion, both emitted here."""
        cites = [self.probe(story, criterion, verdict), self.probe(story, criterion, verdict)]
        return self.add("proof/verified", {"story_id": story, "criterion_id": criterion, "spec_id": f"PPS-{criterion}",
                                           "semantic_hash": "c" * 64, "candidate": SHA, "agreement": True,
                                           "verdict": verdict}, cites)

    def adequacy(self, story, outcome="ADEQUATE"):
        """A format-3 `tests/adequacy` (V2-005 §4) with both mandatory executions EXECUTED and PASSED."""
        ran = {"status": "EXECUTED", "outcome": "PASSED", "selection": "STORY_TESTS_RAN", "owner_on_failure": None,
               "reason": None}
        inadequate = outcome == "INADEQUATE"
        return self.add("tests/adequacy", {"story_id": story, "execution": ran, "vacuity": "NON_VACUOUS",
                                           "relevance": "RELEVANT", "regressions": ran, "outcome": outcome,
                                           "owner": "DEVELOPER" if inadequate else None, "may_block": inadequate,
                                           "developer_chargeable": inadequate})

    def drift(self, story, criterion, candidates):
        return self.add("story/plan-drift", {"story_id": story, "criterion_id": criterion, "spec_id": f"PPS-{criterion}",
                                             "attributed_to": candidates[0] if len(candidates) == 1 else "UNATTRIBUTED",
                                             "candidates": candidates})

    def commit(self, story):
        return self.add("story/commit", {"story_id": story, "revision": SHA})

    def rollback(self, story, failure):
        return self.add("story/rollback", {"story_id": story}, [failure])

    def retry(self, story, failure):
        return self.add("story/retry", {"story_id": story}, [failure])

    def close(self, story):
        self.add("story/dispose", {"story_id": story})
        return self.add("story/end", {"story_id": story})

    def case(self, name, expected, wrong):
        # each part copied on its own: no object is shared between a journal and the answers about it
        return {"name": name, "events": copy.deepcopy(self.events), "expected": copy.deepcopy(expected),
                "wrong": copy.deepcopy(wrong)}


from . import (  # noqa: E402 — the models import Refused and Run from this module
    budgets,
    failure_owner,
    qualification_counters,
    retry_target,
    story_state,
    terminal_state,
)

_MODULES = {"story_state": story_state, "failure_owner": failure_owner, "budgets": budgets,
            "retry_target": retry_target, "terminal_state": terminal_state,
            "qualification_counters": qualification_counters}
MODELS = {name: m.model for name, m in _MODULES.items()}
CALIBRATIONS = {name: m.CALIBRATION for name, m in _MODULES.items()}
