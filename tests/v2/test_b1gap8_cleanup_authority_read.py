"""B1 amendment-9 anchor — _read asks ps for the whole host table (the "-A" flag).

cleanup_authority._read, an out-of-scope stale target re-measured per the owner final directive, left an audited
WEAK_ASSERT survivor: L167 dropping "-A" from the ps argv makes ps list only the invoker's own session instead of
the full host table, and the real-ps kill test observed the smaller table but asserted too weakly to notice. This
pins _read's exact argv so the "-A" drop is a deterministic, platform-independent kill. (_win_rows L187
validate=True->False is EQUIVALENT — the L190-191 canonical round-trip backstop — and is dispositioned by a
positional audit, not a test.) Shipped code is correct; this assertion fails only on a regression. No product change."""
from __future__ import annotations

import unittest
from unittest import mock

from validation.v2 import cleanup_authority as ca


class ReadUsesTheFullHostTable(unittest.TestCase):
    @unittest.skipUnless(ca.POSIX, "the ps argv path is POSIX-only")
    def test_read_asks_ps_for_the_whole_host_table(self):
        seen = {}

        class FakePopen:
            def __init__(self, argv, **kw):
                seen["argv"] = list(argv)
                self.pid = 4242
                self.returncode = 0

            def communicate(self):
                return (b"4242 1 4242 Mon Jan  1 00:00:00 2024 ps\n", b"")

        with mock.patch.object(ca.subprocess, "Popen", FakePopen):
            ca._read()
        self.assertEqual(seen["argv"][0], "ps")
        self.assertIn("-A", seen["argv"],
                      f"_read must ask ps for the whole host table (-A); argv was {seen['argv']}")


if __name__ == "__main__":
    unittest.main()
