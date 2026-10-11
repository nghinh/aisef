"""V2.1 mutation-survivor batch T21a — the controller script of `aisef2/probe/cli_invocation.py` (HARNESS) on real
checkouts: the agent's channel, the pre-step that ends the process, the controller's own exit, and the reason an
absent subject is given.

The controller (B1) asks the subject's process (the agent) for one operation at a time over a pair of pipes and
builds every fact itself. These tests drive the real probe against a checkout whose entry function reaches the
agent's globals (`import __main__`, as `stallbye` does in test_c2_cli_invocation) and writes on the agent's reply
descriptor itself: what it writes there is tampering, and tampering is REFUTED — for every class, with the facts
`{subject: "present", tampered: <reason>}` and nothing of an invocation whose answer was not the agent's.

Pins (aisef2/probe/cli_invocation.py::HARNESS/...):
  answer_to [4, 5, 8, 9]            invoke [4, 35]            finish [2, 4, 5]
  main [29, 54, 55, 56, 83, 84, 85, 114]   (the main invocation answered by something else)
  main [43, 44, 69, 70, 97]         (a pre-step that ends the process by itself)
  deadline [0]                      (a controller that has concluded ends by itself)
  inside [3], main [10]             (the note on an absent subject says what is true)
"""

import json
import os
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import BehaviorVerdict  # noqa: E402
from aisef2.probe.cli_invocation import CliInvocationProbe  # noqa: E402
from aisef2.probe.protocol import ObservationKind as K, RevisionRef, run_probe  # noqa: E402
from aisef2.product.outcome import Executed, IndeterminateReason  # noqa: E402
from tests.v2 import test_c2_cli_invocation as base  # noqa: E402  (builders only: no test class is imported)

S, R, I = BehaviorVerdict.SATISFIED, BehaviorVerdict.REFUTED, BehaviorVerdict.INDETERMINATE
EXITS_0, BLOCKS = {"exit_code": 0}, {"blocks": True}
#: A window that is generous for an invocation that answers at once, and short for a controller that waits for it;
#: WATCHDOG bounds the controller's start (READY, DISPATCHED) and, after the window, what a silent controller is given.
WINDOW, WATCHDOG = 3, 10

#: The subject: an entry function that writes on the agent's reply descriptor (`WOUT`, the agent's own copy of the
#: pipe to the controller). `request` is the agent's global for the request being served: its number is the call's own.
STRAYER = '''
import json
import os

import __main__


def _put(*lines):
    os.write(__main__.WOUT, b"".join(lines))


def _answer(n):
    return (json.dumps({"n": n, "raw": 0, "code": 0, "raised": None}) + "\\n").encode("utf-8")


def _line(n):
    return (json.dumps({"n": n}) + "\\n").encode("utf-8")


def main(argv):
    cmd, n = argv[0], __main__.request["n"]
    if cmd == "junk":        # a line that is not JSON
        _put(b"this is not json\\n")
    elif cmd == "jsonlist":  # JSON that is not an object
        _put(b"[1, 2]\\n")
    elif cmd == "wrongn":    # an object numbered otherwise than the request, with no answer fields
        _put(_line(999))
    elif cmd == "stray":     # a complete answer to the call's own number; the real answer then trails it
        _put(_answer(n))
    elif cmd == "straybye":  # the call's answer, an answer to the closing request, and one more line
        _put(_answer(n), _line(n + 1), _line(n + 2))
    elif cmd == "junkexit":  # a stray line, then the process ends: nothing real trails it
        _put(b"this is not json\\n")
        os._exit(3)
    elif cmd == "byeexit":   # the agent is gone at the closing exchange
        __main__.OPS["bye"] = lambda r: os._exit(0)
    return 0
'''
FILES = {**base.PRODUCT, "app/strayer.py": STRAYER}


def build(parent: str, name: str, files: dict) -> str:
    root = pathlib.Path(parent, name)
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")
    return str(root)


class _Checkouts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp = tempfile.TemporaryDirectory(prefix="aisef2-t21a-", ignore_cleanup_errors=True)
        cls.addClassCleanup(tmp.cleanup)
        cls.root = tmp.name
        cls.at = RevisionRef(base.SHA, build(tmp.name, "product", FILES))

    def see(self, s, at=None, e=None, probe=None):
        return (probe or base.P).observe(s, at or self.at, e or base.env())

    def result(self, s, at=None, e=None):
        return run_probe(base.P, s, at or self.at, e or base.env()).result

    def revision(self, name, files):
        return RevisionRef(base.SHA, build(self.root, name, files))


def facts(o):
    return json.loads(o.detail)


class _Tampering(_Checkouts):
    def assert_tampered(self, o, why=""):
        """OBSERVED/REFUTED with exactly the facts of a present subject whose answer was not the agent's."""
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, R), f"{why} {o.kind} {o.detail}")
        f = facts(o)
        self.assertEqual(sorted(f), ["subject", "tampered"], f"{why} {o.detail}")   # no exit code, streams, pre, ...
        self.assertEqual(f["subject"], "present", why)
        self.assertIsInstance(f["tampered"], str, why)


class MainInvocationAnsweredByTheSubject(_Tampering):
    """A line on the agent's channel that is not the agent's answer to the request — not JSON, not an object, or an
    object numbered otherwise — is tampering with the observation, in the main invocation: OBSERVED and REFUTED for
    every class, with the facts `{subject: 'present', tampered}`. The subject never gets a crash of the controller
    (UNRUNNABLE, owner ENVIRONMENT) for it, and never an exit code, streams, pre, before or files it did not earn.

    Pins HARNESS/answer_to [4, 8, 9], invoke [35], main [29, 54, 55, 83, 85, 114]; and, bounded by the window and
    the watchdog, answer_to [5] and invoke [4] (a tampered answer taken for an agent that is gone: the controller then
    waits for an agent that lives, and the verdict is the harness's silence, not the refutation)."""

    def run_main(self, cmd, observable):
        s = base.spec("app.strayer:main", observable, {"argv": [cmd]}, window=WINDOW)
        return self.see(s, e=base.env(timeout=WATCHDOG))

    def test_a_line_that_is_not_an_answer_to_the_request_refutes_every_class(self):
        for cmd in ("junk", "jsonlist", "wrongn"):
            with self.subTest(cmd=cmd):
                self.assert_tampered(self.run_main(cmd, EXITS_0), cmd)

    def test_blocks_is_refuted_too_and_the_result_is_executed_refuted(self):
        o = self.run_main("junk", BLOCKS)
        self.assert_tampered(o, "blocks")
        s = base.spec("app.strayer:main", EXITS_0, {"argv": ["wrongn"]}, window=WINDOW)
        self.assertEqual(self.result(s, e=base.env(timeout=WATCHDOG)), Executed(R))

    def test_with_nothing_real_behind_the_stray_line_the_facts_still_say_tampered(self):
        """The stray line, then the process ends: the closing exchange has no real answer to restore the marker
        from, so the facts the main invocation built are the ones of the verdict. Pins main [56, 84]."""
        self.assert_tampered(self.run_main("junkexit", EXITS_0), "junkexit")


class StrayAnswerInAPreStep(_Tampering):
    """The same tampering in a pre-step: the observation is REFUTED at once with the same facts. The controller does
    not take the subject for gone and does not wait for the window: with `blocks`, whose expired window is
    SATISFIED, a tampering subject would otherwise satisfy the contract.

    Pins HARNESS/answer_to [5], invoke [4] (their verdict-flipping position), and answer_to [4, 8, 9], invoke [35]."""

    def run_pre(self, cmd, observable):
        s = base.spec("app.strayer:main", observable, {"argv": ["ok"], "pre": [{"argv": [cmd]}]}, window=WINDOW)
        return self.see(s)

    def test_a_pre_step_that_writes_a_stray_answer_refutes_exits_and_blocks(self):
        for cmd in ("junk", "wrongn"):
            for name, observable in (("exits", EXITS_0), ("blocks", BLOCKS)):
                with self.subTest(cmd=cmd, observable=name):
                    self.assert_tampered(self.run_pre(cmd, observable), f"{cmd} {name}")


class ClosingExchange(_Tampering):
    """After the invocation the controller asks the agent to close the exchange; when the agent's own answers are not
    the only lines on its channel the observation is REFUTED with the facts of a present subject that tampered —
    for `exits` and `blocks` — and an agent that is simply gone at that point is not tampering.

    Pins HARNESS/finish [2, 4, 5]."""

    def test_a_complete_answer_to_the_calls_own_number_refutes(self):
        for name, observable in (("exits", EXITS_0), ("blocks", BLOCKS)):
            with self.subTest(observable=name):
                s = base.spec("app.strayer:main", observable, {"argv": ["stray"]}, window=WINDOW)
                self.assert_tampered(self.see(s), name)

    def test_a_stray_line_that_pre_answers_the_closing_request_and_one_more_line_refute(self):
        for name, observable in (("exits", EXITS_0), ("blocks", BLOCKS)):
            with self.subTest(observable=name):
                s = base.spec("app.strayer:main", observable, {"argv": ["straybye"]}, window=WINDOW)
                self.assert_tampered(self.see(s), name)

    def test_an_agent_that_is_gone_at_the_closing_exchange_is_not_tampering(self):
        s = base.spec("app.strayer:main", EXITS_0, {"argv": ["byeexit"]}, window=WINDOW)
        o = self.see(s)
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S), o.detail)
        f = facts(o)
        self.assertNotIn("tampered", f)
        self.assertEqual((f["subject"], f["exit_code"], f["raised"]), ("present", 0, None))


class PreStepThatEndsTheProcess(_Checkouts):
    """A pre-step is part of the state the observable is measured over. When the subject's process ends itself during
    one — a hard exit — the observation is REFUTED with that step's index, even when the exit code is the very code
    the observable expects (a setup that crashed with it is not the product satisfying the contract), and never a
    failure of the controller (UNRUNNABLE, owner ENVIRONMENT). A pre-step the process ends by a signal the controller
    did not send is NON_CONTROLLER_SIGNAL, exactly as the same signal in the main invocation.

    Pins HARNESS/main [43, 44, 69, 97] and [70]."""

    def test_a_hard_exit_during_a_pre_step_refutes_even_when_its_code_is_the_expected_one(self):
        pre = [{"argv": ["echo", "one"]}, {"argv": ["hard", "3"]}]
        s = base.spec("app.cli:main", {"exit_code": 3}, {"argv": ["echo"], "pre": pre})
        o = self.see(s)
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, R), o.detail)
        f = facts(o)   # the fields a reader relies on; the record may carry more
        self.assertEqual({k: f.get(k) for k in ("subject", "exit_code", "hard_exit", "pre_failed")},
                         {"subject": "present", "exit_code": 3, "hard_exit": True, "pre_failed": 1})
        self.assertEqual(self.result(s), Executed(R))

    def test_a_hard_exit_during_a_pre_step_refutes_whatever_the_observable_says(self):
        pre = [{"argv": ["hard", "3"]}]
        for name, observable in (("exits, another code", {"exit_code": 0}), ("blocks", BLOCKS)):
            with self.subTest(observable=name):
                o = self.see(base.spec("app.cli:main", observable, {"argv": ["echo"], "pre": pre}))
                self.assertEqual((o.kind, o.verdict), (K.OBSERVED, R), o.detail)
                self.assertEqual(facts(o).get("pre_failed"), 0)

    @unittest.skipUnless(os.name == "posix", "a process that ends itself by a signal (Windows has no signal exit)")
    def test_a_pre_step_that_ends_the_process_by_a_signal_is_a_non_controller_signal(self):
        s = base.spec("app.cli:main", EXITS_0, {"argv": ["echo"], "pre": [{"argv": ["selfterm"]}]})
        o = self.see(s)
        self.assertEqual((o.kind, o.verdict), (K.NON_CONTROLLER_SIGNAL, None), o.detail)
        self.assertIn("signal 15", o.detail)
        self.assertEqual(self.result(s), Executed(I, IndeterminateReason.NON_CONTROLLER_SIGNAL))


class AConcludedControllerEndsByItself(_Checkouts):
    """The controller's deadline timer must not keep its process alive: once the observation has concluded the process
    ends by itself and the range is empty without anyone signalling it, however long the declared window is. Were the
    timer a non-daemon thread, every normal observation would leave a controller waiting out its window and the
    caller's `release` would have to signal it — a signal in the one signal-authority ledger (§9.3) of an
    observation nobody interrupted.

    Pins HARNESS/deadline [0]."""

    def test_the_range_is_empty_without_a_signal_long_before_the_window_closes(self):
        ranges, empty = [], []

        def on_range(run):
            real = run.release
            ranges.append(run)

            def release():
                empty.append(run.wait_empty(20.0))   # a bound, not a delay: it returns as soon as the range is empty
                real()
            run.release = release
        s = base.spec("app.cli:main", EXITS_0, {"argv": ["echo", "hi"]}, window=600)
        o = self.see(s, probe=CliInvocationProbe(on_range=on_range))
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S), o.detail)
        self.assertEqual(empty, [True])
        self.assertEqual(ranges[0].ledger, [])


class TheNoteOfAnAbsentSubject(_Checkouts):
    """`resolves only outside the revision` is the reason of an absence and is given exactly when the name resolves
    on the controller's own path and nowhere in the revision. A namespace package of the revision, and a package of
    the revision that shadows a standard-library one yet lacks the submodule, are absent *inside* the revision: the
    same SUBJECT_ABSENT, without that note (it would blame the environment for a name the revision itself holds).

    Pins HARNESS/inside [3], main [10]."""

    NOTE = "outside the revision"   # the identifying element of "resolves only outside the revision"

    def absent(self, at, locator):
        o = self.see(base.spec(locator), at=at)
        self.assertEqual((o.kind, o.verdict), (K.SUBJECT_ABSENT, R), o.detail)
        return o

    def test_the_note_is_given_for_a_name_that_resolves_only_outside(self):
        at = self.revision("empty", {"README.md": "no product yet\n"})
        self.assertIn(self.NOTE, self.absent(at, "json.tool:__main__").detail)

    def test_a_namespace_package_of_the_revision_is_inside_it(self):
        at = self.revision("namespace", {"ns/mod.py": "def main(argv):\n    return 0\n"})   # no ns/__init__.py
        self.assertNotIn(self.NOTE, self.absent(at, "ns:main").detail)

    def test_a_package_that_shadows_a_stdlib_one_is_not_blamed_on_the_environment(self):
        at = self.revision("shadow", {"json/__init__.py": ""})   # holds json, not json.tool
        self.assertNotIn(self.NOTE, self.absent(at, "json.tool:__main__").detail)


if __name__ == "__main__":
    unittest.main()
