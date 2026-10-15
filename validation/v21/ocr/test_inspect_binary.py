"""validation/v21/ocr/inspect_binary.py: a printed string counts as held by the binary only where it lies outside the
build info the Go toolchain stamped in (which alone carries the version and the head of the commit).

Run by hand, from the repository root:  python3 -B validation/v21/ocr/test_inspect_binary.py
It is not part of the suite and not a kill file: validation/v21 is outside mutation.COPY, so a tests/v2 module importing
the tool would not even load in the mutation tree (as validation/v21/test_reach.py)."""

from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.v21.ocr import inspect_binary as ib  # noqa: E402


class HeldAsData(unittest.TestCase):
    def test_a_string_only_the_build_info_carries_is_not_held_as_data_of_the_binary(self):
        stamp = ib.INFO_START + b"mod\tgithub.com/x/ocr\tv1.12.12\t\nbuild\tvcs.revision=182898cf522da3d0\n" + ib.INFO_END
        got = ib.held_as_data(b"\0code\0" + stamp + b"\0pad\0" + stamp)       # the toolchain's stamp is in the file twice
        self.assertEqual(got["v1.12.12"], {"in_file": 2, "outside_build_info": 0})
        self.assertEqual(got["182898c"], {"in_file": 2, "outside_build_info": 0})
        self.assertEqual(got["2026-10-05T00:00:00Z"], {"in_file": 0, "outside_build_info": 0})

    def test_a_string_the_builder_set_lies_outside_it_and_is_counted_there(self):
        stamp = ib.INFO_START + b"mod\tgithub.com/x/ocr\tv1.12.12\t\n" + ib.INFO_END
        got = ib.held_as_data(b"182898c\0go1.26.5\0v1.12.12\0" + stamp + b"\x002026-10-05T00:00:00Z\0")
        self.assertEqual(got["v1.12.12"], {"in_file": 2, "outside_build_info": 1})
        self.assertEqual(got["182898c"], {"in_file": 1, "outside_build_info": 1})
        self.assertEqual(got["2026-10-05T00:00:00Z"], {"in_file": 1, "outside_build_info": 1})

    def test_a_stamp_that_is_not_closed_is_all_inside_and_two_halves_do_not_join_into_a_string(self):
        got = ib.held_as_data(b"v1.12" + ib.INFO_START + b"junk" + ib.INFO_END + b".12\0" + ib.INFO_START + b"v1.12.12 no end")
        self.assertEqual(got["v1.12.12"], {"in_file": 1, "outside_build_info": 0})


if __name__ == "__main__":
    unittest.main()
