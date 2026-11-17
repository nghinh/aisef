"""B1 amendment-8 — the L253 thread-context guard, asserted hermetically in its own file.

The guard's kill set is tests/v2/p4/test_interruption.py, whose real-signal cases die with the process under a
mutated guard (no unittest summary -> INFRA, correctly fail-closed). This file carries the hermetic assertion —
install on the main thread, nothing off it, restore on exit, via signal.getsignal, no real SIGINT — appended to
the target's kill set: the runner walks past the INFRA file to a clean, confirmable FAIL ("a timeout or an
infrastructure fault never decides a kill and never hides a later valid one"). The controlled comparison
V2.2-L253-DISPOSITION.json remains the behavioural evidence. Shipped code is correct; these assertions fail only
if a regression reintroduces one of the audited mutations. No product change."""
from __future__ import annotations

import pathlib
import signal
import tempfile
import threading
import unittest

from aisef2.runtime.run_scope import RunScope

from tests.v2.p4.test_run_scope import spec


class SecondInterruptGuard(unittest.TestCase):
    def _scope(self, tmp):
        self.assertIs(threading.current_thread(), threading.main_thread())
        return RunScope(pathlib.Path(tmp) / "run-l253", "run-l253", spec=spec)

    def test_the_handler_is_installed_exactly_on_the_main_thread_and_restored(self):
        with tempfile.TemporaryDirectory(prefix="aisef2-l253-") as tmp:
            run = self._scope(tmp)
            before = signal.getsignal(signal.SIGINT)
            with run._second_interrupt_abandons():
                inside = signal.getsignal(signal.SIGINT)
                self.assertIsNot(inside, before,
                                 "on the main thread the guard must install the SIGINT->interrupt() handler")
                self.assertTrue(callable(inside))
            self.assertIs(signal.getsignal(signal.SIGINT), before, "the previous handler must be restored on exit")

    def test_off_the_main_thread_the_guard_installs_nothing_and_raises_nothing(self):
        with tempfile.TemporaryDirectory(prefix="aisef2-l253-") as tmp:
            run = self._scope(tmp)
            before = signal.getsignal(signal.SIGINT)
            seen: dict = {}

            def worker():
                try:
                    with run._second_interrupt_abandons():
                        seen["inside"] = signal.getsignal(signal.SIGINT)
                except BaseException as e:  # noqa: BLE001 — a mutated guard raises ValueError here; the test reports it
                    seen["raised"] = repr(e)
            t = threading.Thread(target=worker)
            t.start()
            t.join(10)
            self.assertNotIn("raised", seen, "off the main thread the guard must not touch signal handling")
            self.assertIs(seen.get("inside"), before, "off the main thread no handler may be installed")
            self.assertIs(signal.getsignal(signal.SIGINT), before)


if __name__ == "__main__":
    unittest.main()
