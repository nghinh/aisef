"""Owner ruling 2026-11-26 §3 condition 8: the FINAL, COMMITTED seq-14 ledger entry exists and matches the ruling
digest — "a draft-file hash alone is insufficient proof of ledger authorization". Always-run; reads the ledger AS
COMMITTED AT HEAD (git show), not the working file, and pins the append-only prefix (seq 13's canonical digest and
the strict 1..14 sequence). This file is deliberately OUTSIDE the seq-14 wiring patch's re-pinned set, so it is an
independent witness of the committed entry, not part of what it witnesses."""
import hashlib
import json
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.v23 import ledger_digest as ld  # noqa: E402

LEDGER_REL = "closure-evidence/v2/cycle2/RELEASE-DECISIONS.json"
#: the canonical ruling digest the owner authorized (ruling 2026-11-26 §3, byte-for-byte)
SEQ14_RULING_DIGEST = "3cc825e1d6de8d051e8e4ed4ecf4403c865f9a177a2529757f2d949b6625c2cc"
SEQ14_PATCH_SHA256 = "ed7a55d89368707dc1897d191a6e1fdd70ad8f5b70ab74ffec9dc21e4236baac"
#: append-only prefix pin: seq 13's canonical digest (the ROUND-AUTH ruling, measured 2026-11-26 pre-append)
SEQ13_DIGEST = "a1469d009f2456fccde4a3b3e3706a993e6bc1524b5512873dbcefe6ccec01f0"


class Seq14Committed(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        r = subprocess.run(["git", "show", f"HEAD:{LEDGER_REL}"], cwd=ROOT, capture_output=True, encoding="utf-8")
        assert r.returncode == 0, f"the ledger is not committed at HEAD: {r.stderr}"
        cls.committed = json.loads(r.stdout)
        cls.entries = cls.committed["entries"]

    def test_the_committed_entry_14_exists_and_matches_the_authorized_ruling_digest(self):
        e14 = [e for e in self.entries if e.get("seq") == 14]
        self.assertEqual(len(e14), 1, "exactly one seq-14 entry")
        self.assertEqual(hashlib.sha256(ld.canonical(e14[0])).hexdigest(), SEQ14_RULING_DIGEST,
                         "the committed seq-14 entry's canonical digest is not the one the owner authorized")
        self.assertEqual(e14[0]["decision"]["FILE_DIGESTS"]["patch_sha256_lf"], SEQ14_PATCH_SHA256)
        self.assertEqual(e14[0].get("approver"), "human:owner")
        self.assertIn("2026-11-26", e14[0].get("authority", ""),
                      "the authority text must carry the owner authorization date from the ruling message")

    def test_the_ledger_stays_append_only(self):
        self.assertEqual([e["seq"] for e in self.entries], list(range(1, 15)), "strictly 1..14, nothing else")
        e13 = next(e for e in self.entries if e["seq"] == 13)
        self.assertEqual(hashlib.sha256(ld.canonical(e13)).hexdigest(), SEQ13_DIGEST,
                         "entry 13 moved — history is immutable")

    def test_the_working_tree_ledger_equals_the_committed_one(self):
        live = json.loads((ROOT / LEDGER_REL).read_text(encoding="utf-8"))
        self.assertEqual(live, self.committed, "uncommitted ledger drift")


if __name__ == "__main__":
    unittest.main()
