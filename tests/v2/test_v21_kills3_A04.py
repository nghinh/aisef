"""V2.1 (owner B-03, audit batch A04): refusals of `aisef bundle seal` / `aisef bundle approve` whose reason the
mutation campaign could drop without any test noticing. The batch holds 14 survivors the triage proposed to audit; two
groups of them turned out to lose what an operator is refused *for*, and are pinned here:

* `_closed` [8]  — a closed object is refused with its path as a field of its own, then the reason;
* `approve` [14], [20] — an id the bundle does not hold, and a cited requirement it does not hold, are each refused
  saying which kind of thing is missing.

The other eleven are audited (no test): see the report beside this file."""

from __future__ import annotations

import contextlib
import copy
import io
import json
import pathlib
import re
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle as B  # noqa: E402
from aisef2.app import bundle_cli  # noqa: E402

EXAMPLE = json.loads((bundle_cli.EXAMPLES / "calc-1-story.json").read_text(encoding="utf-8"))["authoring"]


def authoring() -> dict:
    """The shipped one-story example, made sealable without a repository: a full baseline sha and the requirements
    document's sha256 are given instead of being read from `--repo`."""
    a = copy.deepcopy(EXAMPLE)
    a["baseline"] = "a" * 40
    a["requirements_document"]["sha256"] = "0" * 64
    return a


class Tmp(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = pathlib.Path(self._tmp.name)

    def tool(self, *argv) -> tuple[int, str]:
        """(exit status, stderr) of `aisef bundle <argv>`."""
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            code = bundle_cli.main([str(a) for a in argv])
        return code, err.getvalue()


class ClosedObjectRefusal(Tmp):
    """`_closed` (every object of an authoring document is a closed key set): the refusal names the object by its
    JSONPath as the message's first field, and then why — the keys it must hold exactly and the keys it holds. What the
    operator edits is the object at that path; a path that runs into the key list that follows it (`...criteria[0]['id',
    ...]`) reads as another path. Pins aisef2/app/bundle_cli.py::_closed [8]. Not pinned, on purpose: the order the
    held keys are listed in [7], the label of the held list [9], the closing parenthesis [10] (audited)."""

    def refusal(self, doc) -> str:
        with self.assertRaises(B.BundleError) as c:
            bundle_cli.seal(doc)
        return str(c.exception)

    def test_the_path_is_the_first_field_then_the_keys_expected_and_the_keys_held(self):
        a = authoring()
        criterion = a["stories"]["S1"]["criteria"][0]
        del criterion["why"]                    # a key the object must hold and does not
        criterion["spec"] = "PPS-x"             # a key it holds and must not
        path, delimiter, reason = self.refusal(a).partition(": ")
        self.assertEqual((path, delimiter), ("$.stories.S1.criteria[0]", ": "))
        for key in bundle_cli.CRITERION_KEYS:   # what it must hold, each key named
            self.assertIn(repr(key), reason)
        # which list is which: `why` is named only by what is expected, `spec` only by what is held, expected first
        self.assertEqual((reason.count(repr("why")), reason.count(repr("spec"))), (1, 1))
        self.assertLess(reason.index(repr("why")), reason.index(repr("spec")))

    def test_every_level_of_the_document_is_refused_by_its_own_path(self):
        root, story = authoring(), authoring()
        root["not_a_field"] = 1
        story["stories"]["S1"]["not_a_field"] = 1
        for doc, where in ((root, "$"), (story, "$.stories.S1")):
            with self.subTest(where):
                path, delimiter, reason = self.refusal(doc).partition(": ")
                self.assertEqual((path, delimiter), (where, ": "))
                self.assertIn(repr("not_a_field"), reason)

    def test_a_contract_of_the_document_is_refused_by_its_path_inside_seals_own_wrapper(self):
        a = authoring()
        a["contracts"][0]["not_a_field"] = 1
        # seal re-embeds this refusal in "a requirement or contract does not hold: ...": the path is not the first
        # field there, but it still stands as a field of its own, and the key it refused is named
        msg = self.refusal(a)
        self.assertIn("$.contracts[0]: ", msg)
        self.assertIn(repr("not_a_field"), msg.partition("$.contracts[0]: ")[2])

    def test_the_operator_gets_the_refusal_on_stderr_exit_2_and_no_file(self):
        a = authoring()
        a["stories"]["S1"]["criteria"][0]["spec"] = "PPS-x"
        (self.tmp / "authoring.json").write_text(json.dumps(a), encoding="utf-8")
        code, err = self.tool("seal", self.tmp / "authoring.json", "--out", self.tmp / "b.json")
        self.assertEqual(code, 2)
        self.assertTrue(err.startswith("refused: $.stories.S1.criteria[0]: "), err)
        self.assertFalse((self.tmp / "b.json").exists())


class ApproveRefusals(Tmp):
    """`approve` refuses, through the command and writing nothing, (a) a contract id the bundle does not hold and (b) a
    contract that cites a requirement the bundle does not hold — and each says which kind of thing is missing, because
    nothing else tells them apart (one exception type, one exit status). Pins aisef2/app/bundle_cli.py::approve [14],
    [20]. Not pinned, on purpose: where the contract is missing from ("in the bundle", [15] — the operator named the
    bundle on the command line) and the wording around the two ids."""

    def setUp(self) -> None:
        super().setUp()
        self.sealed, _ = bundle_cli.seal(authoring())

    def approve(self, doc, contract) -> tuple[int, str]:
        (self.tmp / "in.json").write_text(json.dumps(doc), encoding="utf-8")
        out = self.tmp / "out.json"
        code, err = self.tool("approve", self.tmp / "in.json", "--contract", contract, "--approver", "human:t",
                              "--out", out)
        self.assertFalse(out.exists(), "a refused approval writes no file")
        return code, err

    def test_a_contract_id_the_bundle_does_not_hold_is_refused_saying_there_is_no_such_contract(self):
        code, err = self.approve(self.sealed, "BC-NOPE")
        self.assertEqual(code, 2)
        self.assertTrue(err.startswith("refused: "), err)
        self.assertIn("BC-NOPE", err)
        self.assertIn("no contract", err)       # the cause, as opposed to a cited requirement that is missing

    def test_a_contract_citing_a_requirement_the_bundle_does_not_hold_names_both_and_says_so(self):
        cited = self.sealed["contracts"][0]["requirement_ids"][0]       # R-1
        code, err = self.approve({**self.sealed, "requirements": []}, "BC-ADD")
        self.assertEqual(code, 2)
        tokens = re.findall(r"[\w-]+", err)     # the two ids are tokens of their own, not run together
        self.assertIn("BC-ADD", tokens)
        self.assertIn(cited, tokens)
        self.assertIn("not a requirement", err)  # the cause, as opposed to a contract id that is missing


if __name__ == "__main__":
    unittest.main()
