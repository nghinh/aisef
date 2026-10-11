"""V2.1 (B-03) mutation survivors, batch A21: the controller script of the `cli_invocation` probe
(`aisef2/probe/cli_invocation.py::HARNESS`, functions `conclude` and `main`).

Two requirements of the controller, each proved against the real script:

* the controller's own deadline closes the protocol file like every other ending: RESULT, then END — the closing
  line the module docstring lists among the closed set of lines the controller writes;
* a subject whose process ended by a signal is NON_CONTROLLER_SIGNAL (§9.3) whatever it left behind: the controller
  reports the signal from the process's wait status alone and never reads the captures of a subject that is gone.

No clock assertion: the deadline case lets the controller run to its own end (the subject returns long after the
window), so the protocol file is complete; the signal case is decided by the process's exit status.
"""

import json
import os
import pathlib
import secrets
import signal
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.probe import cli_invocation as ci  # noqa: E402
from aisef2.probe.protocol import ObservationKind as K, RevisionRef, run_probe  # noqa: E402
from aisef2.product.outcome import Executed  # noqa: E402
from tests.v2 import test_c2_cli_invocation as base  # noqa: E402

#: a subject that outlives any window the tests declare: it returns once the controller's deadline has spoken
SLOW = {"app/__init__.py": "", "app/__main__.py": "import time\n\ntime.sleep(2.5)\n"}

#: a subject that makes both of its captures unreadable (mode 000) and then ends its own process by SIGTERM
MUTE_THEN_DIE = {
    "app/__init__.py": "",
    "app/__main__.py": "import os\nimport signal\n\nos.fchmod(1, 0)\nos.fchmod(2, 0)\nos.kill(os.getpid(), signal.SIGTERM)\n",
}


def checkout(test: unittest.TestCase, files: dict) -> str:
    """`base.checkout(files)` — a directory holding `files`, written as it writes them — made inside a temporary
    directory the test itself cleans up (nothing is removed by path)."""
    d = tempfile.TemporaryDirectory(prefix="aisef2-rev-", ignore_cleanup_errors=True)
    test.addCleanup(d.cleanup)
    for rel, text in files.items():
        p = pathlib.Path(d.name, rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")
    return d.name


class DeadlineClosesTheProtocol(unittest.TestCase):
    """The deadline path writes `RESULT {"deadline": true}` and then `END` — the same closing line as the normal path.
    The controller is run to its own end by itself (no stop from the parent can cut the file short), and the file is
    read with the parent's own reader, `ci._protocol`, which keys every authentic line by its tag: the closed set is
    READY, DISPATCHED, MAIN, RESULT, END, each once; an END written with an empty tag is a line outside that set and
    END is missing. The exit status of the controller is not part of this: the parent reads it only when no RESULT
    was written.

    Pins aisef2/probe/cli_invocation.py::HARNESS/conclude [3]
    (also fails the HARNESS/main mutant `emit("MAIN")` -> `emit("")`, index 51: not claimed by this batch)
    """

    def run_controller(self, files, window):
        root = checkout(self, files)
        scratch = tempfile.TemporaryDirectory(prefix="aisef2-a21-", ignore_cleanup_errors=True)
        self.addCleanup(scratch.cleanup)
        work = os.path.join(scratch.name, "evaluation")
        os.mkdir(work)
        nonce, key = secrets.token_hex(16), secrets.token_hex(32)
        ask, ws, pycache = ci._prepare(work, root, "app:__main__", {"argv": []}, [], nonce, key, sys.executable, window)
        subprocess.run(ci._harness_argv(sys.executable, ask, pycache), cwd=ws, env=ci._child_env(ws),
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
        return ci._protocol(os.path.join(work, "protocol.log"), nonce, key)

    def test_the_deadline_is_followed_by_END_and_the_protocol_holds_only_its_documented_lines(self):
        seen = self.run_controller(SLOW, window=0.3)
        self.assertEqual(sorted(seen), ["DISPATCHED", "END", "MAIN", "READY", "RESULT"])
        self.assertEqual([json.loads(body) for body in seen["RESULT"]], [{"deadline": True}])
        self.assertEqual(seen["END"], [""])
        # the closing line: the deadline's RESULT is written first (both by the timer's one thread, in this order;
        # `_protocol` keys the tags in the order each first appears in the file)
        self.assertLess(list(seen).index("RESULT"), list(seen).index("END"))


@unittest.skipUnless(os.name == "posix" and hasattr(os, "geteuid") and os.geteuid() != 0,
                     "a mode-000 file is unreadable to the controller only on POSIX and not for root")
class SignalEndedSubjectIsReportedWhateverItsCapturesHold(unittest.TestCase):
    """A subject that made its own captures unreadable and then ended its process by a signal is still
    NON_CONTROLLER_SIGNAL: Executed(INDETERMINATE, NON_CONTROLLER_SIGNAL), owned by the product's side of §9.3 — never
    HARNESS_FAILED (UNRUNNABLE, ENVIRONMENT) because the controller tried to read the files of a process that is gone.
    The facts of a signal carry the signal and nothing read from the subject's captures: the controller reports it
    from the process's wait status alone.

    Pins aisef2/probe/cli_invocation.py::HARNESS/main [82]
    """

    def test_a_signal_with_unreadable_captures_is_still_the_signal(self):
        root = checkout(self, MUTE_THEN_DIE)
        at = RevisionRef(base.SHA, root)
        s = base.spec("app:__main__", base.EXIT0, {"argv": []})
        o = base.P.observe(s, at, base.env())
        self.assertEqual(o.kind, K.NON_CONTROLLER_SIGNAL, o.detail)
        self.assertIn(f"signal {int(signal.SIGTERM)}", o.detail)   # the signal itself, from the wait status
        self.assertEqual(run_probe(base.P, s, at, base.env()).result, Executed(base.I, base.NCS))


if __name__ == "__main__":
    unittest.main()
