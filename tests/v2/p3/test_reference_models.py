"""WP-3.5 — the independent reference models (RFC §21, §27 Q1; F11). REF-1 and REF-2 are here.

The models (tests/v2/refmodel/) were authored in a separate work session, from the RFC and
docs/implementation/v2/P3-PROJECTION-SEMANTICS.md only, without the projection source;
validation/v2/refmodel_independence.py bars them from importing it. This module is the harness: calibration and the
differential against the implementation over generated and edited traces — the kill set for the models' mutation
targets. Injected projection defects (REF-1) are in test_reference_defects.py.
"""

import importlib.util
import json
import pathlib
import random
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import ControlProjection as P  # noqa: E402
from aisef2.journal.format3 import reconstruct  # noqa: E402 — every format, each read as written (V2-005)
from aisef2.journal.event import GENESIS, Event, JournalError, carried, encode, link  # noqa: E402
from aisef2.journal.fold import ProjectionError, fold  # noqa: E402
from aisef2.journal.projections import PROJECTIONS  # noqa: E402
from aisef2.product.contract import canonical, plain  # noqa: E402
from tests.v2.p3 import journal_gen as gen  # noqa: E402
from tests.v2.refmodel import CALIBRATIONS, MODELS, Refused, Run  # noqa: E402

_s = importlib.util.spec_from_file_location("p3_refmodel_independence",
                                            ROOT / "validation" / "v2" / "refmodel_independence.py")
independence = importlib.util.module_from_spec(_s)
_s.loader.exec_module(independence)
REFUSED = "REFUSED"


def model_answer(model, events):
    """The model's canonical answer (JSON text: 1.0 and 1 differ), or REFUSED."""
    try:
        return canonical(model([plain(e) for e in events] if events and isinstance(events[0], Event) else events))
    except Refused:
        return REFUSED


def projection_answer(projection, events):
    try:
        return canonical(fold(projection, events))
    except ProjectionError:
        return REFUSED


def expected_of(case, key="expected"):
    return REFUSED if case[key] == REFUSED else canonical(case[key])


def calibration_problems(model, cases) -> list[str]:
    """A model is calibrated when, on every known input, it gives the RFC-derived answer and rejects the answer a
    defective implementation gives. A case whose wrong answer equals its expected one calibrates nothing."""
    out = [] if cases else ["no calibration case"]
    for c in cases:
        got = model_answer(model, c["events"])
        if expected_of(c, "wrong") == expected_of(c):
            out.append(f"{c['name']}: its wrong answer equals the expected one")
        if got != expected_of(c):
            out.append(f"{c['name']}: answered {'REFUSED' if got == REFUSED else 'another state'}, not the expected")
        if got == expected_of(c, "wrong"):
            out.append(f"{c['name']}: agrees with the defective answer")
    return out


def stored(events):
    """Stored text for plain event dicts (a calibration input), chained from GENESIS."""
    out, prev = [], GENESIS
    for e in events:
        ev = Event(e["seq"], e["type"], e["data"], e["time"], e["ignorable"], tuple(e["source_seqs"]))
        prev = link(prev, ev)
        out.append(encode(ev, prev))
    return "".join(out)


def text_of(specs):
    out, prev = [], GENESIS
    for n, (type_, data, cites) in enumerate(specs):
        ev = Event(n, type_, carried(type_, data), float(n), False, tuple(cites))
        prev = link(prev, ev)
        out.append(encode(ev, prev))
    return "".join(out)


def mutated(seed):
    """A generated run with one random edit — dropped, duplicated or swapped events, or a changed citation. Some
    edits make a journal the reader refuses; the rest are journals whose semantics a projection may refuse."""
    rng = random.Random(seed)
    specs = gen.specs(seed, stories=3)
    n = rng.randrange(1, len(specs))
    op = rng.choice(["drop", "duplicate", "swap", "cite", "unadmit", "overcharge", "stale_retry", "rebegin", "readmit",
                     "stranger"])
    if op == "readmit":  # an admission repeated in its attempt (a blocked one if there is one)
        at = [i for i, (t, _, _) in enumerate(specs) if t == "story/admitted"]
        blocked = [i for i in at if not specs[i][1]["admitted"]]
        i = rng.choice(blocked or at)
        specs = specs[:i + 1] + [specs[i]] + specs[i + 1:]
    elif op == "stranger":  # a failure of a story that never began
        specs = specs[:n] + [("failure/observed", {"story_id": "S-stranger", "code": "PROBE_UNRUNNABLE",
                                                   "detail": ""}, ())] + specs[n:]
    elif op == "overcharge":  # a developer request charging a criterion its admission did not record READY
        at = [i for i, (t, _, _) in enumerate(specs) if t == "provider/request"]
        if at:
            i = rng.choice(at)
            story = specs[i][1]["story_id"]
            adm = [d for t, d, _ in specs[:i] if t == "story/admitted" and d["story_id"] == story][-1]
            other = sorted(c for c, v in adm["dispositions"].items() if v != "READY") or ["C-unplanned"]
            specs[i] = (specs[i][0], {**specs[i][1], "criteria": sorted({*specs[i][1]["criteria"], rng.choice(other)})},
                        specs[i][2])
    elif op == "stale_retry":  # a failure appended after the one a retry cites
        at = [i for i, (t, _, _) in enumerate(specs) if t == "story/retry"]
        if at:
            i = rng.choice(at)
            story = specs[i][1]["story_id"]
            specs = specs[:i] + [("failure/observed", {"story_id": story, "code": rng.choice(
                ["INVALID_CREDENTIAL", "CONTRACT_UNSATISFIED", "PLAN_CONTRADICTION"]), "detail": "late"}, ())] + \
                [(t, d, tuple(c + 1 if c >= i else c for c in cites)) for t, d, cites in specs[i:]]
    elif op == "rebegin":  # a story that ended COMMIT or ROLLBACK begins again
        ended = [d["story_id"] for t, d, _ in specs if t in ("story/commit", "story/rollback")]
        if ended:
            end = max(i for i, (t, d, _) in enumerate(specs) if t == "story/end" and d["story_id"] in ended)
            specs = specs[:end + 1] + [("story/begin", {"story_id": specs[end][1]["story_id"], "parent": gen.SHA}, ())] \
                + specs[end + 1:]
    elif op == "unadmit":  # an attempt that skipped its admission, and what depended on it: the gate-ordering shape
        n = rng.choice([i for i, (t, _, _) in enumerate(specs) if t == "story/admitted"])
        story = specs[n][1]["story_id"]
        end = next((i for i in range(n, len(specs)) if specs[i][1].get("story_id") == story
                    and specs[i][0] in ("story/commit", "story/rollback", "story/retry")), len(specs))
        specs = [x for i, x in enumerate(specs) if not (i == n or n < i < end and x[1].get("story_id") == story
                                                         and x[0] in ("story/plan-drift", "provider/request"))]
    elif op == "drop":
        specs = specs[:n] + specs[n + 1:]
    elif op == "duplicate":
        specs = specs[:n] + [specs[n]] + specs[n:]
    elif op == "swap" and n + 1 < len(specs):
        specs[n], specs[n + 1] = specs[n + 1], specs[n]
    else:
        cites = [i for i, (t, _, _) in enumerate(specs) if t == "failure/observed"]
        at = [i for i, (t, _, c) in enumerate(specs) if c and t in ("story/rollback", "story/retry")]
        if cites and at:
            i = rng.choice(at)
            specs[i] = (specs[i][0], specs[i][1], (rng.choice([c for c in cites if c < i] or [0]),))
    fixed = []
    for i, (t, d, c) in enumerate(specs):  # a citation now past its event is dropped (the writer would refuse it)
        fixed.append((t, d, tuple(x for x in c if x < i)))
    return fixed


class Independence(unittest.TestCase):
    def test_the_models_import_nothing_of_the_implementation(self):
        self.assertEqual(independence.check(ROOT), [])
        for src in ("import aisef2.journal.projections\n", "from aisef2.journal import fold\n",
                    "from aisef2.journal.projections.budgets import Budgets\n", "import importlib\n",
                    "m = __import__('aisef2')\n", "from tests.v2.p3 import journal_gen\n"):
            with self.subTest(src=src):
                self.assertEqual(len(independence.violations("tests/v2/refmodel/x.py", src)), 1)

    def test_six_models_each_with_calibration(self):
        self.assertEqual(sorted(MODELS), sorted(p.value for p in P))
        self.assertEqual(sorted(CALIBRATIONS), sorted(MODELS))
        for pid, cases in CALIBRATIONS.items():
            with self.subTest(model=pid):
                self.assertGreaterEqual(len(cases), 3)
                self.assertTrue(all(expected_of(c, "wrong") != expected_of(c) for c in cases))


class Calibration(unittest.TestCase):
    def test_every_model_is_calibrated(self):
        for pid, model in MODELS.items():
            with self.subTest(model=pid):
                self.assertEqual(calibration_problems(model, CALIBRATIONS[pid]), [])

    def test_every_calibration_input_is_a_real_journal(self):
        for pid, cases in CALIBRATIONS.items():
            for c in cases:
                with self.subTest(model=pid, case=c["name"]):
                    self.assertEqual([plain(e) for e in reconstruct(stored(c["events"])).events], c["events"])

    def test_the_implementation_reproduces_every_calibration_answer(self):
        for pid, cases in CALIBRATIONS.items():
            for c in cases:
                with self.subTest(model=pid, case=c["name"]):
                    events = reconstruct(stored(c["events"])).events
                    self.assertEqual(projection_answer(PROJECTIONS[P(pid)], events), expected_of(c))

    def test_REF_2_an_always_agree_model_fails_calibration(self):
        for pid, cases in CALIBRATIONS.items():
            answers = {json.dumps(c["events"], sort_keys=True): c["wrong"] for c in cases}

            def agreeing(events, answers=answers):  # mirrors the defective implementation, whatever it says
                got = answers[json.dumps(events, sort_keys=True)]
                if got == REFUSED:
                    raise Refused("mirrored")
                return got

            def constant(events, first=cases[0]["expected"]):  # agrees with one answer on every input
                if first == REFUSED:
                    raise Refused("constant")
                return first
            with self.subTest(model=pid):
                self.assertTrue(calibration_problems(agreeing, cases))
                if len({json.dumps(c["expected"], sort_keys=True) for c in cases}) > 1:
                    self.assertTrue(calibration_problems(constant, cases))
        self.assertEqual(calibration_problems(lambda e: {}, []), ["no calibration case"])


class Differential(unittest.TestCase):
    def test_implementation_equals_the_reference_model_over_generated_traces(self):
        for seed in range(120):
            events = reconstruct(gen.journal(seed, stories=3 + seed % 5)).events
            for pid, model in MODELS.items():
                with self.subTest(seed=seed, model=pid):
                    self.assertEqual(projection_answer(PROJECTIONS[P(pid)], events), model_answer(model, events))

    def test_implementation_equals_the_reference_model_at_every_prefix(self):
        for seed in range(30):
            events = reconstruct(gen.journal(seed, stories=2 + seed % 4)).events
            for pid, model in MODELS.items():
                with self.subTest(seed=seed, model=pid):
                    self.assertEqual([projection_answer(PROJECTIONS[P(pid)], events[:n]) for n in range(len(events) + 1)],
                                     [model_answer(model, events[:n]) for n in range(len(events) + 1)])

    def test_the_answer_does_not_depend_on_payload_key_order(self):
        def reordered(e):
            def rev(v):
                return {k: rev(v[k]) for k in reversed(list(v))} if isinstance(v, dict) else v
            return {**e, "data": rev(e["data"])}
        for seed in range(20):
            events = [plain(e) for e in reconstruct(gen.journal(seed)).events]
            for pid, model in MODELS.items():
                with self.subTest(seed=seed, model=pid):
                    self.assertEqual(model_answer(model, [reordered(e) for e in events]), model_answer(model, events))

    def test_an_admission_outside_its_one_place_is_refused_by_both(self):
        # an admission is legal once per attempt and only in BEGIN: a second one after a blocked admission, and one
        # after a rollback from BEGIN (no admission yet), are each refused whichever half of that rule decides it
        again = Run()
        again.begin("S1")
        again.admit("S1", {"C1": "PRECONDITION_BROKEN"})
        again.admit("S1", {"C1": "PRECONDITION_BROKEN"})
        late = Run()
        late.begin("S1")
        late.rollback("S1", late.fail("S1", "PRECONDITION_BROKEN"))
        late.admit("S1", {"C1": "READY"})
        for name, run in (("again", again), ("late", late)):
            events = reconstruct(stored(run.events)).events
            for pid, model in MODELS.items():
                with self.subTest(case=name, model=pid):
                    self.assertEqual(projection_answer(PROJECTIONS[P(pid)], events), model_answer(model, events))
            self.assertEqual(model_answer(MODELS[P.STORY_STATE.value], events), REFUSED)

    def test_on_edited_traces_both_refuse_or_both_agree(self):
        compared = refused = 0
        for seed in range(150):
            try:
                events = reconstruct(text_of(mutated(seed))).events
            except JournalError:
                continue
            for pid, model in MODELS.items():
                want = projection_answer(PROJECTIONS[P(pid)], events)
                with self.subTest(seed=seed, model=pid):
                    self.assertEqual(want, model_answer(model, events))
                compared += 1
                refused += want == REFUSED
        self.assertGreater(refused, 20)
        self.assertGreater(compared - refused, 20)


if __name__ == "__main__":
    unittest.main()
