"""Mutation survivors of `aisef2/app/run.py::execute` (batch A13, audit batch).

Of the eight survivors of the batch, one is a refusal whose scope word is read by the operator and is not asserted by
any kill file; this file pins it. The other seven (the record literal's dead `stage` store, the two final newlines and
the two `sort_keys` of the evidence files, the `--parent` option name in the "no run record" refusal) are audited in
the batch report: nothing reads what they change.

A continuation whose lineage has spend no evidence accounts for starts no paid work (`aisef run --parent`, V2.1,
app/lineage). The refusal's reader is an operator who has to reconcile that spend; its entries do not say whose they
are (a preflight request "sent and never answered", a session "that started finished no step" carry no run name), so
the refusal itself must say that they are the *lineage's* — not the predecessor's alone.
"""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle, lineage, settings  # noqa: E402
from aisef2.app import run as R  # noqa: E402
from tests.v2 import test_app_run as base  # noqa: E402

#: what the grandparent's own evidence says it spent without a record (aisef2/app/lineage.py::account_of)
ENTRY = "preflight request 1 sent and never answered"


class LineageRefusalNamesItsScope(unittest.TestCase):
    """The predecessor is clean; its parent holds the spend nothing accounts for. Pins aisef2/app/run.py::execute [273]."""

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(t.name).resolve()
        self.grandparent = self.tmp / "grandparent"
        (self.grandparent / "preflight").mkdir(parents=True)
        # the ledger line the preflight writes before its first request (aisef2/app/preflight.py::run), never answered
        (self.grandparent / "preflight" / "LEDGER.jsonl").write_text(
            json.dumps({"n": 1, "event": "sent", "kind": "listing"}) + "\n", encoding="utf-8")
        (self.grandparent / "RUN.json").write_text("{}", encoding="utf-8")
        self.predecessor = self.tmp / "predecessor"
        self.predecessor.mkdir()
        (self.predecessor / "RUN.json").write_text(json.dumps({"continues": {"path": str(self.grandparent)}}), encoding="utf-8")
        self.project = bundle.load(base.project_bundle("0" * 40))
        self.settings = settings.load(base.SETTINGS)

    def refuse(self, name: str = "child") -> tuple[R.RunRefused, pathlib.Path]:
        out = self.tmp / name
        with self.assertRaises(R.RunRefused) as c:
            R.execute(self.project, self.settings, self.tmp / "source", out, predecessor=self.predecessor)
        return c.exception, out

    def assertNamesTheLineage(self, message: str) -> None:
        """What the operator who reconciles the spend needs from the text: the run named, whose spend it is, the way
        forward, and what is unaccounted. The predecessor's path is masked so that it cannot satisfy the scope word."""
        text = message.replace(str(self.predecessor), "<predecessor>")
        self.assertIn("<predecessor>", text)                   # the run the operator named
        self.assertIn("lineage", text)                         # whose spend it is: the lineage ending there, not that run
        self.assertIn("--accept-unaccounted", text)            # the way forward
        self.assertIn(ENTRY, text)                             # what is unaccounted

    def test_the_unaccounted_spend_is_the_lineage_s_and_the_entry_names_no_run(self):
        # the premises: the predecessor itself has nothing unaccounted; the lineage has one entry, and it names no run
        self.assertEqual(lineage.account_of(self.predecessor)["unaccounted"], [])
        self.assertEqual(lineage.lineage_account(self.predecessor, self.tmp / "child")["unaccounted"], [ENTRY])
        refused, _ = self.refuse()
        self.assertNamesTheLineage(str(refused))

    def test_the_refused_child_s_record_says_the_same_before_any_provider_request(self):
        refused, out = self.refuse()
        rec = json.loads((out / "RUN.json").read_text(encoding="utf-8"))
        self.assertEqual((rec["failure"]["type"], rec["failure"]["stage"]), ("RunRefused", "claim"))
        self.assertNamesTheLineage(rec["failure"]["detail"])   # the record is what is left once the terminal is gone
        self.assertIsNone(rec.get("preflight"))                # nothing was sent


if __name__ == "__main__":
    unittest.main()
