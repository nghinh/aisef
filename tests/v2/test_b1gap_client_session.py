"""B1 gap kill tests for aisef2/app/client.py::session (mutation campaign, one test per surviving mutant).
Offline and hermetic: the tripwire refusal fires before any process range is built, so no client is ever looked
up or started."""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import client  # noqa: E402


class ClientSessionTripwireRefusal(unittest.TestCase):
    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(t.name).resolve()

    # kills: L328 string 'session ' emptied
    def test_the_tripwire_refusal_names_the_session_as_a_session(self):
        # The refusal text is not free prose: it is stored into story_errors -> RUN.json (whose bytes feed the
        # evidence-manifest digest), so the `session {name}` label is a semantic value. Assert the smallest
        # stable substrings the mutant destroys: `via session s-1` and the per-hit default label
        # `session s-1: contract BC-1` (both collapse to bare `s-1` when the 'session ' literal is emptied).
        budget = client.Budget({k: 9 for k in client.Budget.KEYS}, {k: 0 for k in client.Budget.KEYS}, self.tmp / "logs")
        needle = "SEALED-STIMULUS-0123456789"       # >= tripwire.MIN_NEEDLE canonical chars
        log = self.tmp / "logs" / "s-1.jsonl"
        with self.assertRaises(client.SessionRefused) as ctx:
            client.session("s-1", f"prompt carrying {needle} verbatim", str(self.tmp), log, 1.0,
                           model="prov/m", env={"PATH": "/nowhere"}, budget=budget, turn_cap=3,
                           exe=str(self.tmp / "opencode"), needles={needle: "BC-1"})
        msg = str(ctx.exception)
        self.assertIn("via session s-1", msg)                       # tripwire.refusal L138: `via {where}`
        self.assertIn("session s-1: contract BC-1 (26 chars)", msg)  # tripwire.refusal L135: h.get('file', where)
        self.assertNotIn(needle, msg)       # the refusal names the contract, never the sealed value
        self.assertFalse(log.exists())      # refused before anything starts: no evidence stream is written


if __name__ == "__main__":
    unittest.main()
