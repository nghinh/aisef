"""Phase 16 — evidence schema versioning. Records written by ≤ 1.7.6 carry only `detail.candidate` (schema 1);
they are migrated on read to an identity with `schema_version = 1` and nothing but the candidate (provenance kept,
nothing invented) — so they LOAD, they can be SHOWN, and they never SCORE under the new gate: old evidence must
never silently satisfy a new gate. The archived LedgerLock 1.7.4 replays are the corpus."""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
import tests  # noqa: E402,F401
from aisef.control import replay as R  # noqa: E402
from aisef.control.gate import _stale_for, evaluate  # noqa: E402
from aisef.control.outcome import Outcome  # noqa: E402
from aisef.control.identity import SCHEMA_VERSION, EvidenceIdentity  # noqa: E402
from aisef.harness.observe import NOTE, TOOL_RUN, EvidenceStore  # noqa: E402

ARCHIVE = ROOT / "closure-evidence" / "dogfood" / "ledgerlock-run2"
FILES = sorted(ARCHIVE.rglob("*.evidence.jsonl"))


def _identity_now(ev, sid: str) -> EvidenceIdentity:
    """The identity a NEW gate would decide on for this story: its candidate of record, its recorded epoch, and a
    real tree / config / environment / baseline — every field the decider binds on."""
    note = ev.last(NOTE, "story:contract")
    return EvidenceIdentity(story_id=sid, story_epoch=str((note.detail if note else {}).get("fingerprint") or "e"),
                            candidate_sha=ev.candidate or "c" * 40, tree_state_digest="tree", verifier_config_digest="cfg",
                            environment_digest="env", baseline_root="r" * 40, stage="gate")


#: the checks the gate scores FROM RECORDS; review and security are scored from the attempt's inputs, which this
#: test replays from the archived `gate:input` — their records are covered by the `last_fresh` assertions
SCORED = ("test", "lint")


def _gate_under(ev, sid: str, now: EvidenceIdentity):
    """The CURRENT gate over this evidence, deciding on `now`, with the inputs the archived run recorded."""
    kw = R.kwargs_from(ev.of(NOTE, R.GATE_INPUT)[-1].detail)
    return evaluate(sid, ev, **{**kw, "identity": now})


class _Archive(unittest.TestCase):
    def setUp(self):
        self.assertTrue(FILES, f"no archived evidence under {ARCHIVE}")
        self._tmp = tempfile.TemporaryDirectory(); self.root = Path(self._tmp.name)
        self.stores: list[tuple[str, EvidenceStore, Path]] = []
        for path in FILES:
            sid = path.name[: -len(".evidence.jsonl")]
            store = EvidenceStore(self.root / path.parent.name)
            store.root.mkdir(parents=True, exist_ok=True)
            shutil.copy(path, store.root / f"{sid}.jsonl")
            self.stores.append((sid, store, path))

    def tearDown(self):
        self._tmp.cleanup()


class TestArchivedEvidenceLoadsAndNeverScores(_Archive):
    def test_every_archived_event_loads_as_schema_1(self):
        for sid, store, path in self.stores:
            lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
            ev = store.read(sid)
            self.assertEqual(len(ev.events), len(lines), f"{path.name}: every line loads")
            self.assertTrue(ev.events)
            for e in ev.events:
                self.assertEqual(EvidenceIdentity.of(e, sid).schema_version, 1, f"{path.name} seq {e.seq}: migrated, never invented")
                self.assertEqual(e.identity, {}, "the file is not rewritten: the record itself stays schema 1")

    def test_no_archived_record_is_fresh_for_control(self):
        for sid, store, path in self.stores:
            ev = store.read(sid); now = _identity_now(ev, sid)
            names = {e.name for e in ev.of(TOOL_RUN)}
            self.assertTrue(names, path.name)
            for name in names:
                self.assertIsNone(ev.last_fresh(TOOL_RUN, name, now), f"{path.name}: {name} is legacy — never fresh")
            gate = _gate_under(ev, sid, now)
            self.assertFalse(gate.passed, f"{path.name}: the gate never passes on legacy evidence")
            scored = {c.name: c.outcome for c in gate.checks if c.name in SCORED}
            self.assertTrue(scored, path.name)
            self.assertEqual([n for n, o in scored.items() if o is Outcome.PASSED], [],
                             f"{path.name}: a legacy record can be shown, never scored — {scored}")

    def test_the_gate_states_legacy_and_passes_nothing(self):
        for sid, store, path in self.stores:
            ev = store.read(sid); now = _identity_now(ev, sid)
            stale = _stale_for(ev, now)
            bound = {e.name for e in ev.of(TOOL_RUN) if EvidenceIdentity.of(e, sid).bound}
            self.assertTrue(bound, f"{path.name}: the archive has candidate-bound checks")
            self.assertTrue(stale, f"{path.name}: the legacy checks are STATED, not silently dropped")
            self.assertLessEqual(set(stale), bound, "only candidate-bound records can be stale")
            for name in ("test", "lint"):
                if name in bound:
                    self.assertIn(name, stale, f"{path.name}: {name} is stated")
            for name, why in stale.items():
                self.assertIn("schema 1", why, f"{path.name}: {name}: {why}")


class TestSchema2RoundTripAndMixedFiles(_Archive):
    def test_a_schema_2_record_round_trips(self):
        sid, store, _ = self.stores[0]
        now = _identity_now(store.read(sid), sid)
        EvidenceStore(store.root.parent, identity=now).tool_run(sid, "test", ok=True)
        e = store.read(sid).of(TOOL_RUN, "test")[-1]
        self.assertEqual(e.identity.get("schema_version"), SCHEMA_VERSION)
        self.assertEqual(EvidenceIdentity.of(e, sid), now)

    def test_a_mixed_file_scores_only_the_new_records(self):
        sid, store, _ = self.stores[0]
        ev0 = store.read(sid); now = _identity_now(ev0, sid)
        legacy_names = {e.name for e in ev0.of(TOOL_RUN)}
        self.assertIn("test", legacy_names)
        EvidenceStore(store.root.parent, identity=now).tool_run(sid, "test", ok=True)     # the new run's record
        ev = store.read(sid)
        fresh = ev.last_fresh(TOOL_RUN, "test", now)
        self.assertIsNotNone(fresh); self.assertEqual(fresh.identity.get("schema_version"), SCHEMA_VERSION)
        others = legacy_names - {"test"}
        for name in others:
            self.assertIsNone(ev.last_fresh(TOOL_RUN, name, now), f"{name}: still only legacy — still scores nothing")
        scored = {c.name: c.outcome for c in _gate_under(ev, sid, now).checks if c.name in SCORED}
        self.assertIs(scored["test"], Outcome.PASSED, "the new run's record scores")
        self.assertEqual([n for n, o in scored.items() if o is Outcome.PASSED], ["test"], f"only the new record: {scored}")


if __name__ == "__main__":
    unittest.main()
