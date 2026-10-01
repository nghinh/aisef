"""WP-3.2 — format compatibility (RFC §20 property 4, §35; F1). FORMAT-1 and FORMAT-2 are here.

Kill set for `compat.py::reconstruct`. Every fixture is committed (tests/v2/fixtures/journal/) and rebuilt by
tests/v2/p3/journal_fixtures.py; the committed bytes must equal the build.
"""

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.journal import compat  # noqa: E402
from aisef2.journal.compat import Journal, UnknownRequiredEvent, reconstruct  # noqa: E402
from aisef2.journal.event import GENESIS, SCHEMAS, JournalError, validate  # noqa: E402
from tests.v2.p3.journal_fixtures import DIR, FIXTURES  # noqa: E402


def committed(name):
    return (DIR / f"{name}.jsonl").read_bytes().decode("utf-8")


class Fixtures(unittest.TestCase):
    def test_the_committed_fixtures_are_the_build(self):
        self.assertEqual(sorted(p.stem for p in DIR.glob("*.jsonl")), sorted(FIXTURES))
        for name, (text, _) in FIXTURES.items():
            with self.subTest(fixture=name):
                self.assertEqual(committed(name), text)
                self.assertNotIn("\r", committed(name))

    def test_each_fixture_reads_as_expected(self):
        for name, (_, (outcome, detail)) in FIXTURES.items():
            with self.subTest(fixture=name):
                if outcome == "REFUSE":
                    with self.assertRaises(JournalError) as cm:
                        reconstruct(committed(name))
                    self.assertIn(detail, str(cm.exception))
                else:
                    j = reconstruct(committed(name))
                    self.assertEqual((j.skipped, j.torn_tail), (detail, outcome == "OK_TORN"))


class Compatibility(unittest.TestCase):
    def test_FORMAT_1_an_unknown_required_event_refuses_reconstruction(self):
        for name in ("unknown_required", "mixed_stream_new_required"):
            with self.subTest(fixture=name), self.assertRaisesRegex(
                    UnknownRequiredEvent, r"^seq \d: unknown event type 'story/checkpoint' is not marked ignorable — "
                                          r"this reader refuses to reconstruct the journal \(§20\.4\)$"):
                reconstruct(committed(name))

    def test_FORMAT_2_an_unknown_ignorable_event_is_skipped_and_reconstruction_goes_on(self):
        j = reconstruct(committed("unknown_ignorable"))
        self.assertEqual(([e.seq for e in j.events], j.skipped, j.length), ([0, 1, 3, 4], (2,), 5))
        self.assertEqual([e.type for e in j.events], ["run/begin", "story/begin", "failure/observed", "story/retry"])
        self.assertEqual(j.events[-1].source_seqs, (3,))  # a citation across the skipped seq still resolves
        mixed = reconstruct(committed("mixed_stream_new_ignorable"))
        self.assertEqual(([e.seq for e in mixed.events], mixed.skipped), ([0, 2, 4, 5], (1, 3)))

    def test_a_newer_log_never_produces_a_silent_wrong_state(self):
        # whatever an older reader returns is exactly the known events, each valid; everything else is refused
        for name, (text, (outcome, _)) in FIXTURES.items():
            with self.subTest(fixture=name):
                try:
                    j = reconstruct(text)
                except JournalError:
                    self.assertEqual(outcome, "REFUSE")
                    continue
                self.assertNotEqual(outcome, "REFUSE")
                self.assertTrue(all(e.type in SCHEMAS and not e.ignorable for e in j.events))
                self.assertEqual(sorted([e.seq for e in j.events] + list(j.skipped)), list(range(j.length)))

    def test_a_known_type_marked_ignorable_is_refused_not_skipped(self):
        with self.assertRaisesRegex(JournalError, "^failure/observed is a required event in format 1; it is never "
                                                  "ignorable$"):
            reconstruct(committed("known_type_marked_ignorable"))

    def test_the_format_is_declared_once_at_seq_0(self):
        with self.assertRaisesRegex(JournalError, "^run/begin: journal format 2 is not format 1: refused, never read "
                                                  "under another format$"):
            reconstruct(committed("version_mismatch"))
        with self.assertRaisesRegex(JournalError, "^run/begin at seq 2: a journal begins with run/begin, and only once$"):
            reconstruct(committed("mixed_stream_second_declaration"))
        with self.assertRaisesRegex(JournalError, r"^story/begin: fields missing \[\], not in the schema \['attempt'\]$"):
            reconstruct(committed("newer_schema_field"))

    def test_a_torn_tail_is_reported_and_never_decoded(self):
        j = reconstruct(committed("torn_tail"))
        self.assertEqual((j.torn_tail, [e.type for e in j.events]), (True, ["run/begin", "story/begin"]))
        whole = FIXTURES["known_log"][0]
        self.assertFalse(reconstruct(whole).torn_tail)
        self.assertEqual(reconstruct(""), compat.EMPTY)

    def test_a_known_log_reconstructs_with_its_heads(self):
        j = reconstruct(committed("known_log"))
        self.assertEqual((len(j.events), j.skipped, j.torn_tail, j.length), (4, (), False, 4))
        prior = []
        for e in j.events:
            validate(e, prior)
            prior.append(e)
        self.assertEqual((j.head(0), j.head(), j.head(4), j.head(2)), (GENESIS, j.chain[-1], j.chain[3], j.chain[1]))
        for bad in (-1, 5):
            with self.subTest(length=bad), self.assertRaisesRegex(JournalError, f"^no prefix of length {bad} in a "
                                                                              "journal of 4$"):
                j.head(bad)
        self.assertEqual(compat.EMPTY.head(), GENESIS)
        with self.assertRaisesRegex(JournalError, "^a journal is read as text$"):
            reconstruct(b"bytes")
        self.assertIsInstance(j, Journal)


if __name__ == "__main__":
    unittest.main()
