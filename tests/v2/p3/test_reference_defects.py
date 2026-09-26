"""WP-3.5 — REF-1: an injected projection defect is caught by the independent reference model.

One realistic defect per projection, each the shape of a rule the RFC makes load-bearing; the differential over
generated and edited traces (test_reference_models.py) must see every one, and see none on the real projections.
"""

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import ControlProjection as P  # noqa: E402
from aisef2.journal.format3 import reconstruct  # noqa: E402 — every format, each read as written (V2-005)
from aisef2.journal.event import JournalError  # noqa: E402
from aisef2.journal.projections import PROJECTIONS  # noqa: E402
from tests.v2.p3 import journal_gen as gen  # noqa: E402
from tests.v2.p3.test_reference_models import MODELS, mutated, model_answer, projection_answer, text_of  # noqa: E402


def defective(pid, step):
    """The projection `pid` with its step replaced by `step(original, state, event)`."""
    base = PROJECTIONS[P(pid)]
    return type("Defective", (), {"id": base.id, "version": base.version, "initial": staticmethod(base.initial),
                                  "step": staticmethod(lambda state, event: step(base.step, state, event))})()


def _commit_from_begin(orig, state, event):
    if event.type == "story/commit" and state.get(event.data["story_id"], {}).get("state") == "BEGIN":
        return {**state, event.data["story_id"]: {**state[event.data["story_id"]], "state": "COMMIT",
                                                  "outcome": "COMMIT"}}
    return orig(state, event)


def _latest_not_cited(orig, state, event):
    if event.type in ("story/rollback", "story/retry"):
        cur = state[event.data["story_id"]]
        return {**state, event.data["story_id"]: {**cur, "cited": True}}  # keeps the latest failure's owner
    return orig(state, event)


def _charges_anything(orig, state, event):
    if event.type == "provider/request":
        dev = state["developer"].get(event.data["story_id"], {"requests": 0, "criteria": {}})
        crit = dict(dev["criteria"])
        for c in event.data["criteria"]:
            crit[c] = crit.get(c, 0) + 1
        return {**state, "developer": {**state["developer"], event.data["story_id"]: {"requests": dev["requests"] + 1,
                                                                                      "criteria": crit}}}
    return orig(state, event)


def _budget_ignores_retryable(orig, state, event):
    if event.type == "failure/observed" and event.data["story_id"] in state:
        return {**state, event.data["story_id"]: {"budget": event.data["owner"], "failure_seq": event.seq}}
    return orig(state, event)


def _retry_ends_retry(orig, state, event):
    new = orig(state, event)
    if event.type == "story/end" and state["pending"].get(event.data["story_id"]) == "RETRY":
        return {**new, "stories": {**new["stories"], event.data["story_id"]: "RETRY"}}
    return new


def _counts_every_admission(orig, state, event):
    new = orig(state, event)
    if event.type == "story/admitted" and event.data["story_id"] in state["admissions"]:
        key = f"{event.data['story_id']}#{event.seq}"  # keeps a retried story's earlier admission too
        admissions = {**new["admissions"], key: state["admissions"][event.data["story_id"]]}
        from aisef2.journal.projections.qualification_counters import metrics
        return {**new, "admissions": admissions, "metrics": metrics(new["roles"], admissions, new["drift"])}
    return new


DEFECTS = {"story_state": _commit_from_begin, "failure_owner": _latest_not_cited, "budgets": _charges_anything,
           "retry_target": _budget_ignores_retryable, "terminal_state": _retry_ends_retry,
           "qualification_counters": _counts_every_admission}


def divergences(pid, projection, seeds=range(200)) -> int:
    n = 0
    for seed in seeds:
        text = gen.journal(seed, stories=3 + seed % 5) if seed % 2 == 0 else text_of(mutated(seed))
        try:
            events = reconstruct(text).events
        except JournalError:
            continue
        n += projection_answer(projection, events) != model_answer(MODELS[pid], events)
    return n


class InjectedDefects(unittest.TestCase):
    def test_REF_1_every_injected_projection_defect_is_caught(self):
        self.assertEqual(sorted(DEFECTS), sorted(MODELS))
        for pid, step in DEFECTS.items():
            with self.subTest(defect=step.__name__):
                self.assertGreater(divergences(pid, defective(pid, step)), 0)
                self.assertEqual(divergences(pid, PROJECTIONS[P(pid)], range(0, 200, 7)), 0)


if __name__ == "__main__":
    unittest.main()
