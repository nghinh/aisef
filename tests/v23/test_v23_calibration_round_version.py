"""PE8-2 (owner ruling 2026-11-27): the calibration record is named and resolved by this round's ROUND_VERSION
(2.3.0.dev0), decoupled from pyproject (still 2.2.0). `resolve()` takes the NEWEST record of a version <= the round
version and reports ITS state — it never silently falls back to an older, still-current record to manufacture a PASS.

The controls here exercise the round-version mechanism itself (naming, ordering, --state keys, no-fallback, the
legacy-name boundary) and do NOT need the real v2.3 record, so they pass now. The consequential assertions that go
green only once `--write` lays down closure-evidence/v2/release/V2.3.0.dev0-PROBE-CALIBRATIONS.json live in the
companion file test_v23_calibration_rows.py.
"""

from __future__ import annotations

import contextlib
import io
import json
import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.v23.test_v23_calibration_rows import V220, V230, commit, data_clone
from validation.qualification import release_calibration as rc


class RecordVersion(unittest.TestCase):
    def test_record_version_is_the_round_version_while_pyproject_trails_then_follows_it(self):
        self.assertEqual(rc._version(), "2.2.0")                      # the premise: pyproject trails the round
        self.assertEqual(rc._record_version(), "2.3.0.dev0")
        for pv in ("2.3.0", "2.4.0"):                                # once pyproject catches up, the record follows it
            with mock.patch.object(rc, "_version", lambda *a, _pv=pv, **k: _pv):
                self.assertEqual(rc._record_version(), pv)

    def test_the_record_is_named_and_ordered_by_the_round_version(self):
        self.assertEqual(rc.record_rel(rc._record_version()), V230)
        self.assertGreater(rc._vkey(rc._record_version()), rc._vkey("2.2.0"))

    def test_state_reports_both_the_round_and_package_version(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc.main(["--state"])
        d = json.loads(out.getvalue())
        self.assertEqual((d["round_version"], d["package_version"]), ("2.3.0.dev0", "2.2.0"))


class NoSpuriousGreen(unittest.TestCase):
    def test_with_no_v2_3_record_present_resolve_never_reports_a_v2_3_record_as_measured(self):
        with data_clone() as t:                                      # the world before this round's record was laid down
            (t / V230).unlink()
            commit(t)
            self.assertFalse((t / V230).exists())
            rel, state, _ = rc.resolve()
            self.assertFalse(state == "MEASURED" and rel == V230)    # no spurious green on a record that is absent
            self.assertEqual((rel, state), (V220, "INVALIDATED"))    # cites the frozen V2.2.0, which the PE8 kernel no longer matches


class NoFallback(unittest.TestCase):
    def test_an_invalid_v2_3_record_is_cited_and_never_falls_back_to_the_older_v2_2_0_record(self):
        """The critical control: a V2.3.0.dev0 record that is present but NOT current must be what resolve() cites. It
        must never reach past it to an older, still-valid record to report a current state."""
        with data_clone() as t:
            doc = json.loads((t / V220).read_text(encoding="utf-8"))
            doc["identity"] = {"round": "v2.3", "dirty": True}       # a committed v2.3 record, but written from a dirty tree
            (t / V230).write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
            commit(t)
            rel, state, _ = rc.resolve()
            self.assertEqual(rel, V230)                              # the newest (v2.3) record ...
            self.assertNotEqual(rel, V220)                           # ... never the older V2.2.0 it supersedes
            self.assertIn(state, ("INVALIDATED", "UNRESOLVED"))      # and reported by its own non-current state


class LegacyName(unittest.TestCase):
    def test_a_v2_3_named_record_without_the_v2_3_round_identity_is_a_legacy_blob_never_measured(self):
        """The round label is in the file's identity, not its name: a V2.3.0.dev0-named record lacking identity.round
        == v2.3 is judged as a legacy (v2.2.0-committed) blob, which it is not, so INVALIDATED — never MEASURED."""
        for name, identity in {"no identity": None, "wrong round": {"round": "v2.2", "dirty": False}}.items():
            with self.subTest(name), data_clone() as t:
                doc = json.loads((t / V220).read_text(encoding="utf-8"))
                if identity is None:
                    doc.pop("identity", None)
                else:
                    doc["identity"] = identity
                (t / V230).write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
                commit(t)
                rel, state, _ = rc.resolve()
                self.assertEqual(rel, V230)                          # still the newest, judged as a legacy blob
                self.assertNotEqual(state, "MEASURED")
                self.assertIn(state, ("INVALIDATED", "UNRESOLVED"))


if __name__ == "__main__":
    unittest.main()
