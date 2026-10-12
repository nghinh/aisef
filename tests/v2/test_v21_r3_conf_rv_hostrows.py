"""B03-R3 conf, independent review: the host's mount table is what every pseudo file system is judged against (a super
block it holds is the host's, a peer group it holds is the host's). A table whose rows do not show their super block or
their peer groups rules nothing out; judging a mount against it would pass it. The owner's words
(docs/v2.1/decisions/B03-R3-conf.md §1): what cannot be established is refused or reported as isolation not
established. So such a table establishes nothing, as an unread one does.

Through `confine._judge` (the entry point), with the sandbox's own `/mq` mqueue and a host table that is whole but for
one field of one row."""

from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.v2 import test_v21_r3_conf_policy as policy  # noqa: E402 — the module: its tests are not collected again
from tests.v2 import v21_r3_conf_rows as rows  # noqa: E402

WHOLE = {"at": "/", "fs": "overlay", "dev": "0:57", "optional": ["shared:5"]}


class IncompleteHostTable(unittest.TestCase):
    """Requirement: one row of the host's table without a readable super block or without its peer groups makes every
    writable pseudo mount "not established" — the problem says so, never a pass and never "writable"."""

    def judged(self, host) -> list[str]:
        return policy.judged([rows.mount("/mq", "mqueue", optional="shared:77")], host)

    def test_the_table_that_is_whole_accepts_what_the_sandbox_made(self):
        self.assertEqual(self.judged([*rows.HOST, WHOLE]), [])

    def test_a_row_without_what_would_rule_it_out_establishes_nothing(self):
        broken = {
            "no super block": {k: v for k, v in WHOLE.items() if k != "dev"},
            "super block unparsed": {**WHOLE, "dev": "garbage"},
            "super block not text": {**WHOLE, "dev": None},
            "no peer groups": {k: v for k, v in WHOLE.items() if k != "optional"},
            "peer groups not a list": {**WHOLE, "optional": "shared:5"},
            "not a row": None,
        }
        for what, row in broken.items():
            with self.subTest(what=what):
                said = self.judged([*rows.HOST, row])
                self.assertEqual(len(said), 1, said)
                self.assertTrue(said[0].startswith("cannot establish that a writable mount belongs to the sandbox"), said)
                self.assertIn("isolation not established", said[0])
                self.assertIn("/mq: the host's mount table has a row", said[0])     # the mount, and the cause
                self.assertNotIn("writable outside", said[0])

    def test_a_table_whose_every_row_lacks_the_super_block_does_not_pass_a_mount_it_holds(self):
        """The wrong answer this pins against: rows without `dev` match nothing, so the host's own super block (here
        the mqueue the sandbox's /mq shows, 0:64) would be found nowhere and the mount accepted."""
        mount = policy.row("/mq", policy.LINES["host-mqueue"])
        bare = [{"at": h["at"], "fs": h["fs"]} for h in policy.HOST]
        said = policy.judged([mount], bare)
        self.assertEqual(len(said), 1, said)
        self.assertTrue(said[0].startswith("cannot establish"), said)
        self.assertEqual(policy.judged([mount], policy.HOST)[0].split(":")[0], "writable outside the workspace")


if __name__ == "__main__":
    unittest.main()
