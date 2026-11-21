"""validation/v23/ledger_digest.py: the canonical ruling digest of the seq 13 drafts (R1, R2 unchanged; R3 as stated)."""
from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.v23 import ledger_digest as LD  # noqa: E402

R1 = "docs/v2.3/drafts/LEDGER-SEQ-13-DRAFT.md"
R1_DIGEST = "824091110a8bb0fcf8726e889f4ff0c3f11e8f102dfa18f028e343a968caa79b"
R2 = "docs/v2.3/drafts/LEDGER-SEQ-13-DRAFT-R2.md"
R2_DIGEST = "a7fa9f97c6a324f3f1d53df2ca42cd8c46135751977bcdafa5c3d63716daa940"
R3 = "docs/v2.3/drafts/LEDGER-SEQ-13-DRAFT-R3.md"
R3_PATCH = "docs/v2.3/drafts/SEQ13-WIRING-R3.patch"


class Digest(unittest.TestCase):
    def test_R1_is_unchanged_and_digests_as_recorded(self):
        (e,) = LD.entries((ROOT / R1).read_text(encoding="utf-8"))
        self.assertEqual(LD.digest(e), R1_DIGEST)

    def test_R2_and_R3_digest_as_their_text_states_each_new(self):
        seen = {R1_DIGEST}
        for rel in (R2, R3):
            with self.subTest(rel):
                text = (ROOT / rel).read_text(encoding="utf-8")
                (e,) = LD.entries(text)
                stated = re.findall(r"canonical ruling digest[^`]*`([0-9a-f]{64})`", text)
                self.assertEqual(stated, [LD.digest(e)])
                self.assertNotIn(LD.digest(e), seen)
                seen.add(LD.digest(e))
                self.assertEqual((e["seq"], e["id"], e["approver"]), (13, "AISEF_V2_3_QUALIFICATION_ROUND_AUTHORIZED", "human:owner"))
                self.assertTrue(e["authority"].startswith("<") and e["authority"].endswith(">"), "authority stays a placeholder")
                self.assertFalse({"signature", "approved_at", "date"} & set(e), "no signature or approval date in a draft")

    def test_R2_is_unchanged_and_R3_names_its_wiring_patch(self):
        (e2,) = LD.entries((ROOT / R2).read_text(encoding="utf-8"))
        self.assertEqual(LD.digest(e2), R2_DIGEST)
        (e3,) = LD.entries((ROOT / R3).read_text(encoding="utf-8"))
        patch = hashlib.sha256((ROOT / R3_PATCH).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        self.assertIn(f"{R3_PATCH} (sha256 {patch})", e3["decision"]["GATED_TEST_WIRING"])
        self.assertTrue({k: v for k, v in e3["decision"].items() if k not in ("GATED_TEST_WIRING", "SEALING_GATE")}.items()
                        >= {k: v for k, v in e2["decision"].items() if k in ("QUALIFICATION_ROUND", "BRANCH", "SCOPE")}.items())
        self.assertEqual((e3["subject_to"], e3["cost"]), (e2["subject_to"], e2["cost"]))

    def test_the_digest_covers_the_ruling_only(self):
        (e,) = LD.entries((ROOT / R1).read_text(encoding="utf-8"))
        shuffled = json.loads(json.dumps(dict(reversed(list(e.items())))))
        self.assertEqual(LD.digest(shuffled), R1_DIGEST)                       # key order and layout are not content
        self.assertEqual(LD.digest(dict(e, authority="owner: approved")), R1_DIGEST)   # the owner's words are outside
        for k in LD.FIELDS:
            changed = json.loads(json.dumps(e))
            changed[k] = {"x": 1} if k == "decision" else (14 if k == "seq" else "changed")
            self.assertNotEqual(LD.digest(changed), R1_DIGEST, k)
        with self.assertRaises(KeyError):
            LD.digest({k: v for k, v in e.items() if k != "cost"})

    def test_the_cli_refuses_a_file_without_a_ruling(self):
        self.assertEqual(LD.main([str(ROOT / "docs/v2.3/W1-DESIGN.md")]), 1)
        self.assertEqual(LD.main([str(ROOT / R1)]), 0)


if __name__ == "__main__":
    unittest.main()
