"""B1 gap kills for `aisef2/app/bundle_cli.py::_record` (v2.2 release-gate mutation campaign).

Each test pins operator-facing refusal text of `_record` that a surviving mutant destroys: the diagnosis parenthetical
of EVIDENCE_UNREADABLE (L855-856) and the record names of the "cut" EVIDENCE_MALFORMED refusal (L869). The B1 audit
classed all three WEAK_ASSERT: frozen kill tests execute these lines with assertions too loose to fail, and the
B1SurvivorKills docstring (test_v21_pw_lineage_continue.py) rules this text a contract. The unreadable OSError here is
crafted, not met on the filesystem, so the asserted type name and strerror are the same on every platform (and as
root). Offline, hermetic: `_record` reads only RUN.json / RUN.started.json, so a bare temporary directory is a run
directory to it — no run, no client, no provider."""

from __future__ import annotations

import errno
import pathlib
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle_cli  # noqa: E402
from aisef2.app import run as R  # noqa: E402


class RecordRefusalText(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def unreadable(self) -> bundle_cli.JournalRefused:
        """`_record` over a RUN.json whose read raises a crafted PermissionError: EACCES is not `lineage.not_there`
        (not in _NOT_THERE, winerror None), so L855's EVIDENCE_UNREADABLE raise runs — deterministically, with
        type(e).__name__ == 'PermissionError', e.strerror == 'Permission denied' and str(e) == '[Errno 13] ...: path'."""
        err = OSError(errno.EACCES, "Permission denied", str(self.tmp / "RUN.json"))
        with mock.patch.object(pathlib.Path, "read_text", side_effect=err):
            with self.assertRaises(bundle_cli.JournalRefused) as c:
                bundle_cli._record(self.tmp)
        return c.exception

    # kills: L855 string ': ' emptied — the only observable effect is this separator inside the refusal text
    def test_the_unreadable_diagnosis_separates_the_error_type_from_its_text(self):
        err = self.unreadable()
        self.assertEqual(err.code, "EVIDENCE_UNREADABLE")
        # the mutant fuses the type name into the strerror: '(PermissionErrorPermission denied)' — a fused word
        # names neither the type nor the error, so the smallest stable substring is the type name with its separator
        self.assertIn("(PermissionError: ", str(err))

    # kills: L856 Or swapped — {e.strerror or e} becomes {e or e.strerror}; e (no __bool__/__len__) is always truthy,
    # so the mutant always renders str(e) ('[Errno 13] Permission denied: path') in place of the bare strerror
    def test_the_unreadable_diagnosis_carries_the_bare_strerror_not_the_whole_error(self):
        err = self.unreadable()
        self.assertEqual(err.code, "EVIDENCE_UNREADABLE")
        # the bare strerror closes the parenthetical directly before the what-to-do tail; under the mutant the
        # errno prefix and the quoted path sit between them, so this exact text is destroyed
        self.assertIn("(PermissionError: Permission denied): restore read access", str(err))

    # kills: L869 string ' and ' emptied — with BOTH records cut, join() needs its separator ('RUN.json and
    # RUN.started.json', not the fused 'RUN.jsonRUN.started.json'); the frozen tests cut one record (join is a no-op)
    # or assert text the mutant keeps
    def test_two_cut_records_are_named_as_two_words_not_fused(self):
        (self.tmp / "RUN.json").write_text('{"format": "aisef-v2-run-rec', encoding="utf-8")
        (self.tmp / R.STARTED).write_text("", encoding="utf-8")
        with self.assertRaises(bundle_cli.JournalRefused) as c:
            bundle_cli._record(self.tmp)
        self.assertEqual(c.exception.code, "EVIDENCE_MALFORMED")
        # a fused word is not either record's name (T01b L362): both names, told apart, are the contract
        self.assertIn(f"no run record (RUN.json and {R.STARTED} cut: not JSON)", str(c.exception))


if __name__ == "__main__":
    unittest.main()
