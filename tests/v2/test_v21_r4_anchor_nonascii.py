"""B-03 round 4 — `review_verify._canon`: an approved outcome that holds ordinary non-ASCII text is spelled as written.

`_canon` spells the outcome inside an anchor's reason, and the reason is what the developer's retry prompt prints for
a blocked story: its identifying elements are the approved contracts (`(BC-..., BC-...)` at its end), which the
statement states as `anchor_why` and nowhere else (`detail` has no `contracts` key; the artifact keeps them whole).
Since round 3 the statement bounds `anchor_why` by its JSON ENCODING (WHY_MAX = 160): a non-ASCII letter that is
escaped (`\\u1ec7`, six characters, seven after the statement's own escaping) costs six to seven times what it costs
when written, and the ids are what the cut takes first.

Campaign 5 left `_canon`'s `ensure_ascii=False` -> `True` SURVIVED with the audit "lossless either way, no reader
depends on the unescaped text". Two independent re-verifications refuted it: with the escape, a 30-character
Vietnamese message with ten accented letters is enough to cut the second contract's id out of the statement (an outcome
of ASCII letters loses them only beyond 83 characters). The requirement: a message of ordinary length in the user's
language does not evict the contracts the block rests on from the statement, and the contract's own spelling
(`contract.canonical`, which is `ensure_ascii=False`) is the one used.

Known limit, not tested (it is round 3's bound, marked by `elided.anchor_why`, and the artifact keeps the whole): an
outcome of more than ~80 characters evicts the ids from the statement in either spelling."""

from __future__ import annotations

import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import review_verify as V  # noqa: E402
from aisef2.product import contract as C  # noqa: E402
from tests.v2 import test_v21_kills3_T16a as T  # noqa: E402 — the module: its tests are not collected again

IDS = ("BC-V22-S-9-d", "BC-V22-S-9-e")
CONFIRMED = V.Verification(V.CONFIRMED, "the probe refutes it", "probe.cli_invocation", "REFUTED")
ARTIFACT = V.Artifact("review-findings/S1.1.0.json", "0" * 64, 1234)
MESSAGES = ("Lỗi: không đọc được tệp sổ cái", "Không tìm thấy tệp: dữ liệu bị hỏng", "tệp thiếu → exit 3")


def anchored(text: str):
    """(anchor, statement) of a finding that states, for a clause approved by two contracts, their common outcome."""
    outcome = {"stdout": text}
    rows = [(T.contract(i, T.CLI, {"argv": [str(n)]}, outcome), T.CLAUSE, "t") for n, i in enumerate(IDS)]
    finding = T.finding({"argv": ["c"]}, outcome, T.CLI, clause=T.CLAUSE)
    a = V.anchor(finding, T.project(*rows))
    return a, json.loads(V.detail(finding, CONFIRMED, a, ARTIFACT))


class AnOutcomeInTheUsersLanguage(unittest.TestCase):
    def test_it_anchors_to_both_contracts(self):         # the premise: the same decision with or without the text
        for text in MESSAGES:
            with self.subTest(text=text):
                a, _ = anchored(text)
                self.assertEqual(a.status, V.ANCHORED)
                self.assertEqual(sorted(a.contracts), sorted(IDS))

    def test_the_reason_holds_the_message_as_written_and_in_the_contracts_own_spelling(self):
        for text in MESSAGES:
            with self.subTest(text=text):
                a, _ = anchored(text)
                self.assertIn(text, a.reason)
                self.assertIn(C.canonical({"stdout": text}), a.reason)

    def test_the_statement_still_names_every_contract_and_says_nothing_was_cut(self):
        for text in MESSAGES:
            with self.subTest(text=text):
                _, statement = anchored(text)
                for contract_id in IDS:
                    self.assertIn(contract_id, statement["anchor_why"])
                self.assertNotIn("anchor_why", statement.get("elided", {}))

    def test_the_same_message_in_ascii_is_the_control(self):
        _, statement = anchored("Loi: khong doc duoc tep so cai")
        for contract_id in IDS:
            self.assertIn(contract_id, statement["anchor_why"])


if __name__ == "__main__":
    unittest.main()
