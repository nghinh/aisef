"""V2.1 mutation survivors, batch T19a — the `process_effect` controller script (`HARNESS`): what it does with a line
on the subject's answer channel the agent did not write, with a subject that dies, and with the facts of a step.

Real subjects in real processes (the probe's own subprocess boundary), on the fixtures of
tests/v2/test_probe_process_effect.py plus the few modules below. Each class pins one behaviour and says which
`HARNESS/<function>` mutants of aisef2/probe/process_effect.py it exists for.
"""

import os
import pathlib
import signal
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.probe.protocol import ObservationKind as K, RevisionRef, classify_failure  # noqa: E402
from aisef2.product.outcome import Executed, IndeterminateReason  # noqa: E402
from tests.v2 import test_probe_process_effect as base  # noqa: E402

S, R, I = base.S, base.R, base.I
BOOK = base.BOOK
spec, book, call, construct, step = base.spec, base.book, base.call, base.construct, base.step
facts_of = base.facts_of
WINDOW = 10     # a tamper or a death is concluded at once; a hang shows as the window's end, not as a CI timeout

#: One subject for every adversarial behaviour below. `_scribble` is what a hostile subject can always do in its own
#: process: write to every descriptor it holds besides 0-2. The agent's input pipe refuses a write; the pipe its
#: answers go to takes it.
RIOT_PY = '''
import json
import os
import sys

NUMBER = {}


def _scribble(line):
    for fd in range(3, 64):
        try:
            os.write(fd, line.encode("utf-8") + b"\\n")
        except OSError:
            pass


class Riot:
    def count(self):
        return 0

    def scribble(self, line):
        _scribble(line)
        return 1

    def scribble_and_die(self, line):
        _scribble(line)
        os._exit(0)

    def watch(self):
        # the subject shares its process with the agent: from the next call on it knows the pending request's number
        agent = sys.modules["__main__"]
        op_call = agent.OPS["call"]

        def numbered(r):
            NUMBER["n"] = r["n"]
            return op_call(r)
        agent.OPS["call"] = numbered
        return 1

    def forge_answer(self, value):
        # the answer to this very call, in the agent's own words and with the pending request's number
        _scribble(json.dumps({"returned": {"json": value}, "fired": False, "n": NUMBER["n"]}))
        return 1

    def die(self):
        import signal
        os.kill(os.getpid(), signal.SIGKILL)

    def arm_bye(self, mode):
        # the subject shares its process with the agent: it can change what the agent answers to the closing `bye`
        agent = sys.modules["__main__"]
        if mode == "key":
            agent.OPS["bye"] = lambda r: {"extra": 1}
        else:
            def bye(r):
                both = json.dumps({"n": r["n"]}) + "\\n" + json.dumps({"extra": 1}) + "\\n"
                os.write(agent.WOUT, both.encode("utf-8"))      # the genuine answer and a line after it, one write
                return {}
            agent.OPS["bye"] = bye
        return 1
'''
FORGES_ON_IMPORT_PY = '''
import os

for _fd in range(3, 64):
    try:
        os.write(_fd, b"forged while the module is imported\\n")
    except OSError:
        pass
os._exit(0)
'''
FORGES_ON_RESOLVE_PY = '''
import os


def __getattr__(name):
    if name == "Riot":
        for fd in range(3, 64):
            try:
                os.write(fd, b"forged while the name is resolved\\n")
            except OSError:
                pass
        os._exit(0)
    raise AttributeError(name)
'''
SITECHECK_PY = '''
import sys

sys.exit(0 if sys.flags.no_site else 7)
'''
PRODUCT = {**base.PRODUCT, "store/riot.py": RIOT_PY, "store/forges.py": FORGES_ON_IMPORT_PY,
           "store/forges_late.py": FORGES_ON_RESOLVE_PY, "store/sitecheck.py": SITECHECK_PY}


class _Product(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        d = tempfile.TemporaryDirectory(prefix="aisef2-kills3-t19a-", ignore_cleanup_errors=True)
        cls.addClassCleanup(d.cleanup)
        cls.at = RevisionRef(base.SHA, base.checkout(d.name, PRODUCT))

    def see(self, s):
        return base.P.observe(s, self.at, base.env())

    def riot(self, scenario, observable=None):
        return spec("store.riot:Riot", scenario, observable or {"returns": 0}, window=WINDOW)

    def assert_tamper_fact(self, o):
        """The whole observation is the tamper fact: observed and refuted, the facts only the subject's presence and
        the reason — nothing the scenario would otherwise have said."""
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, R), o.detail)
        f = facts_of(o)
        self.assertEqual(sorted(f), ["subject", "tampered"], o.detail)
        self.assertEqual(f["subject"], "present")
        # the operator is told WHY it was refuted: the tamper reason is a non-empty report (PM-8 keeps the facts in the
        # operator's probe-observation artifact, app/diagnostics). Emptied (the mutant), the operator reads only the
        # bare `tampered` key. Pins HARNESS/answer_to [10] — the reason string — by behaviour, not its exact wording.
        self.assertTrue(f["tampered"], o.detail)


class ForgedLine(_Product):
    """A line on the subject's answer channel that the agent did not write — not JSON, JSON that is not an object, an
    object with another request's number — is the tamper fact (RFC §9; B1): never SATISFIED, never a harness failure,
    never a deadline; the observation's facts are the subject's presence and the reason, nothing else. Pins
    aisef2/probe/process_effect.py::HARNESS/answer_to [4, 5, 8, 9] (the foreign-line test and the tamper answer it
    returns, whose key `answered` and `ended` read), ::HARNESS/answered [5] (a tamper answer to a call is not the
    call's answer) and ::HARNESS/ended [4, 12, 25, 27, 32] (the tamper facts)."""

    FORMS = {"a line that is not JSON": "not json", "JSON that is not an object": "[1]",
             "an object that answers another request": '{"n": 99999}'}

    def test_a_line_the_agent_did_not_write_is_the_tamper_fact(self):
        for form, line in self.FORMS.items():
            with self.subTest(form=form):
                s = self.riot([construct(), call("scribble", line), call("count")])
                o = self.see(s)
                self.assert_tamper_fact(o)
                self.assertEqual(classify_failure(s, o), Executed(R))


class ForgerThatDies(_Product):
    """A subject that forges a line and then dies in the same breath is still the tamper fact, in each phase the
    controller reads an answer in: while the module is imported, while the name is resolved, during a call. With the
    agent alive the closing exchange would rebuild the fact from the genuine answer left in the channel; with the
    agent gone nothing does, so the tamper facts the controller reported at the line are all there is. Pins
    aisef2/probe/process_effect.py::HARNESS/ended [13, 26]."""

    def test_each_phase_reports_the_tamper_and_the_reason(self):
        phases = {"importing the module": ("store.forges:Riot", [construct(), call("count")]),
                  "resolving the name": ("store.forges_late:Riot", [construct(), call("count")]),
                  "during a call": ("store.riot:Riot", [construct(), call("scribble_and_die", "forged"), call("count")])}
        for phase, (locator, scenario) in phases.items():
            with self.subTest(phase=phase):
                s = spec(locator, scenario, {"returns": 0}, window=WINDOW)
                o = self.see(s)
                self.assert_tamper_fact(o)
                self.assertEqual(classify_failure(s, o), Executed(R))


@unittest.skipUnless(os.name == "posix", "a signal ending a process is POSIX: on Windows a self-kill is a positive "
                                         "exit status, which is a hard exit")
class SignalKilledSubject(_Product):
    """A subject's process ended by a signal the controller did not send is NON_CONTROLLER_SIGNAL (EXECUTED +
    INDETERMINATE), naming the signal: never a verdict, never REFUTED, never UNRUNNABLE (RFC §9.3, V2-003). The
    controller derives it from the death itself. Pins aisef2/probe/process_effect.py::HARNESS/ended [6, 14, 28]."""

    def test_a_death_by_signal_is_indeterminate_and_names_the_signal(self):
        s = self.riot([construct(), call("die"), call("count")])
        o = self.see(s)
        self.assertEqual((o.kind, o.verdict), (K.NON_CONTROLLER_SIGNAL, None), o.detail)
        # the number is the identifying element; the sentence around it is not the contract
        self.assertRegex(o.detail, rf"\bsignal {int(signal.SIGKILL)}\b")
        self.assertEqual(classify_failure(s, o), Executed(I, IndeterminateReason.NON_CONTROLLER_SIGNAL))


class ClosingExchange(_Product):
    """After the last step the controller says `bye` and the answer is exactly its request number with nothing else
    on the channel; anything else makes the whole observation the tamper fact, whatever the scenario's facts said.
    Pins aisef2/probe/process_effect.py::HARNESS/finish [2, 4, 5]: the bye test all three, the forged-answer test
    [2, 4] (its [5] depends on whether the agent's own bye answer has already arrived) and answer_to [5]."""

    def test_the_control_without_any_tamper_is_satisfied(self):
        o = self.see(self.riot([construct(), call("count")]))
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S), o.detail)

    def test_a_subject_that_answers_its_own_call_is_caught_when_the_genuine_answer_turns_up(self):
        # the forged answer is the pending request's own: it is believed at the call, and the agent's genuine answer
        # to the same request then arrives in the slot of `bye`. The forged value satisfies the observable and the
        # genuine one does not: the verdict must not be the forgery's
        s = self.riot([construct(), call("watch"), call("forge_answer", 7)], {"returns": 7})
        o = self.see(s)
        self.assert_tamper_fact(o)
        self.assertEqual(classify_failure(s, o), Executed(R))

    def test_a_bye_answered_with_more_than_its_number_is_the_tamper_fact(self):
        for form, mode in (("another key in the answer", "key"), ("a line queued after the answer", "queued")):
            with self.subTest(form=form):
                s = self.riot([construct(), call("arm_bye", mode)], {"returns": 1})
                o = self.see(s)         # on its own the scenario is satisfied: the call returned 1
                self.assert_tamper_fact(o)
                self.assertEqual(classify_failure(s, o), Executed(R))


class StepTraceOutcome(_Product):
    """Every completed step's trace entry is {i, kind, outcome: "ok"}: the outcome is the step's machine-read status
    (`run` and `_raises_hold` read it by its `refuted:` / `raised:` prefixes, so a blank is neither). `write` and
    `edit_jsonl` are the two kinds whose success entry nothing else asserts. Pins
    aisef2/probe/process_effect.py::HARNESS/do_write [4] and ::HARNESS/do_edit [24]."""

    def test_write_and_edit_jsonl_complete_with_ok(self):
        two = [call("append", "a", 1, "r1"), call("append", "b", 2, "r2")]
        scenario = book(*two, step("edit_jsonl", path=BOOK, line=1, field="value", value=99),
                        step("write", path="<ws>/note.txt", text="x"), call("verify"))
        o = self.see(spec("store.book:Book", scenario, {"returns": {"ok": False, "first_bad": 1}}, window=WINDOW))
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S), o.detail)
        trace = facts_of(o)["trace"]
        self.assertEqual(trace[3], {"i": 3, "kind": "edit_jsonl", "outcome": "ok"})
        self.assertEqual(trace[4], {"i": 4, "kind": "write", "outcome": "ok"})


class LineCount(_Product):
    """`count_lines` is the number of newline-terminated lines plus one for an unterminated last one: a terminated
    two-record file has 2, an empty file 0 — for the `line_count` file shape and for edit_jsonl's bound ("has no line
    N"). Pins aisef2/probe/process_effect.py::HARNESS/count_lines [2]."""

    def files(self, scenario, shape):
        return self.see(spec("store.book:Book", scenario, {"files": {BOOK: shape}}, window=WINDOW))

    def test_a_terminated_file_has_as_many_lines_as_records(self):
        two = book(call("append", "a", 1, "r1"), call("append", "b", 2, "r2"))
        o = self.files(two, {"line_count": 2})
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S), o.detail)
        self.assertEqual(facts_of(o)["files"]["book.jsonl"]["line_count"], 2)

    def test_an_empty_file_has_no_lines(self):
        o = self.files([step("workspace", files={"book.jsonl": {"text": ""}})], {"line_count": 0})
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S), o.detail)
        self.assertEqual(facts_of(o)["files"]["book.jsonl"]["line_count"], 0)

    def test_edit_jsonl_one_past_the_last_terminated_line_has_no_such_line(self):
        two = [call("append", "a", 1, "r1"), call("append", "b", 2, "r2")]
        edit = step("edit_jsonl", path=BOOK, line=2, field="key", value="x")
        o = self.see(spec("store.book:Book", book(*two, edit, call("count")), {"returns": 2}, window=WINDOW))
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, R), o.detail)
        refuted = facts_of(o)["refuted"]
        self.assertEqual((refuted["step"], refuted["kind"]), (3, "edit_jsonl"))
        self.assertIn("has no line 2", refuted["why"])


class SubprocessIsolation(_Product):
    """A subprocess step runs the revision's module under the isolation of the agent and the controller: `-I -S -B`
    — no `site`, so the interpreter's site-packages are not on the child's path and the step does not depend on what
    the host has installed. Pins aisef2/probe/process_effect.py::HARNESS/do_subprocess [8]."""

    def test_the_child_runs_without_site(self):
        o = self.see(spec("store.book:Book", book(step("subprocess", argv=["-m", "store.sitecheck"]), call("count")),
                          {"returns": 0}, window=WINDOW))
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S), o.detail)
        self.assertEqual(facts_of(o)["trace"][1], {"i": 1, "kind": "subprocess", "outcome": "ok", "exit": 0})


if __name__ == "__main__":
    unittest.main()
