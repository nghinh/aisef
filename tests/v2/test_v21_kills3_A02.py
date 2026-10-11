"""Audit batch A02: refusals of `aisef2/app/bundle_cli.py::seal` whose identifying elements are fused by a lost separator
or whose stage is named by one frame only.

What an operator fixing an authoring document reads is one line on stderr, `refused: <message>`, and nothing parses it.
The requirements below are therefore about *identifying elements staying separate tokens* — the locator the author
searches for in the file, the cause class, the key or value to fix — and about the stage being named where the kernel's
own detail does not name it. They are not about wording: no sentence is compared, no connective prose is pinned, and
the punctuation between two tokens is free (any run of non-word characters delimits them; only *no* delimiter fails).

Offline and deterministic: the authoring document of the shipped `calc-1-story` example, sealed with a literal baseline
and the requirements document's sha256 (no repository, no git, no provider).
"""

from __future__ import annotations

import copy
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle, bundle_cli  # noqa: E402


def authoring() -> dict:
    """The calc-1-story example's authoring document, resolved without a repository."""
    doc = json.loads((bundle_cli.EXAMPLES / "calc-1-story.json").read_text(encoding="utf-8"))["authoring"]
    doc["baseline"] = "a" * 40
    doc["requirements_document"] = {"path": "docs/requirements.md", "sha256": "b" * 64}
    return doc


def refusal(doc: dict) -> str:
    """The message of the BundleError seal raises for `doc` (anything else, or no refusal, fails the test)."""
    try:
        bundle_cli.seal(doc)
    except bundle.BundleError as e:
        return str(e)
    raise AssertionError("seal did not refuse the document")


class AContractThatBreaksItsKeySetIsLocatedByItsOwnPath(unittest.TestCase):
    """The closed-key refusal of one contract is raised by `_closed` inside seal's requirement/contract block and
    re-wrapped there with the cause class in front of it, so the author's only statement of WHICH contract is malformed
    (`$.contracts[n]`) comes straight after that class. It must stay a token of its own, delimited from the class, and
    carry the index of the broken contract (1), not of its neighbour.

    Pins aisef2/app/bundle_cli.py::seal [122]; the path's own pieces [119, 120] are killed with it."""

    def test_the_locator_of_the_second_contract_is_delimited_from_the_cause_class(self):
        a = authoring()
        broken = copy.deepcopy(a["contracts"][0])
        broken["id"] = "BC-TWO"
        broken["spec"] = "PPS-x"          # a key no contract has
        a["contracts"].append(broken)
        msg = refusal(a)
        m = re.search(r"(?P<cls>\w+)\W+\$\.contracts\[(?P<n>\d+)\](?!\w)", msg)
        self.assertIsNotNone(m, msg)
        self.assertEqual((m["cls"], m["n"]), ("BundleError", "1"), msg)

    def test_the_unbroken_contract_alone_is_sealed(self):
        """The other side of the decision: the same document without the extra key is not refused, and both of its
        contracts are in the bundle (so the refusal above is the extra key's and nothing else's)."""
        a = authoring()
        second = copy.deepcopy(a["contracts"][0])
        second["id"] = "BC-TWO"
        a["contracts"].append(second)
        sealed, _ = bundle_cli.seal(a)
        self.assertEqual([c["id"] for c in sealed["contracts"]], [c["id"] for c in a["contracts"]])


class ACriterionRefusalKeepsItsLocatorItsCauseClassAndItsDetailApart(unittest.TestCase):
    """A criterion the kernel's constructors refuse is reported as three tokens in this order: the path of the
    criterion in the authoring file, the class of the failure, and the kernel's detail, which names the key the author
    must fix (`depends_on`) or the value that is wrong (the role). Losing a delimiter fuses two of them into one word
    (`criteria[0]PlanError`, `PlanErrordepends_on`) and the key stops being something to look for in the file.

    Pins aisef2/app/bundle_cli.py::seal [149]; the first separator [148] and the `ValueError` entry of the except tuple
    [104] are killed with it. The fusion of [149] is visible in the key-led detail: a quoted value (the role case) is
    delimited by its own quotes and reads on either way, so that case checks the same three tokens but cannot tell."""

    WHERE = r"\$\.stories\.S1\.criteria\[0\]"

    def parts(self, msg: str) -> re.Match:
        m = re.fullmatch(rf"(?P<where>{self.WHERE})\W+(?P<cls>\w+)\W+(?P<detail>.+)", msg, re.DOTALL)
        self.assertIsNotNone(m, msg)
        return m

    def test_the_key_the_author_must_fix_is_a_word_of_its_own_after_the_cause_class(self):
        a = authoring()
        a["stories"]["S1"]["criteria"][0]["depends_on"] = [""]       # an id that names nothing: PlanError at depends_on
        m = self.parts(refusal(a))
        self.assertEqual(m["cls"], "PlanError")
        self.assertRegex(m["detail"], r"(?<!\w)depends_on(?!\w)")

    def test_a_role_outside_the_vocabulary_is_named_by_its_value_after_the_cause_class(self):
        a = authoring()
        a["stories"]["S1"]["criteria"][0]["role"] = "BOGUS"
        m = self.parts(refusal(a))
        self.assertEqual(m["cls"], "ValueError")
        self.assertIn("BOGUS", m["detail"])


class AValueThePlanCannotEncodeIsRefusedAsTheStageThatRefusedIt(unittest.TestCase):
    """A lone surrogate (half of an emoji pair a copy-paste cut, written as `\\ud83d` in the JSON) in a criterion's
    prose is accepted by every constructor before the plan; it is refused when the plan's hash is computed, with the
    codec's own message — which names neither the plan nor the field, and whose position is an offset into the plan's
    canonical form, not into the file. The stage frame is then the only thing that tells the author which stage of seal
    refused the document (the same input in a requirement is framed as the requirement/contract stage).

    Pins aisef2/app/bundle_cli.py::seal [127]."""

    def test_the_refusal_names_the_plan(self):
        a = authoring()
        a["stories"]["S1"]["criteria"][0]["why"] = "introduces 1.1 \ud83d"
        self.assertIn("plan", refusal(a).lower())


if __name__ == "__main__":
    unittest.main()
