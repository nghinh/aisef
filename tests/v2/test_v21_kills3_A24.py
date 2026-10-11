"""V2.1 (owner B-03, kill round 3, batch A24): the survivors of aisef2/app/bundle.py::shape_problems that the triage
proposed to audit and whose audit found a reader and a contract the mutant breaks. Both are refusals of a *story* of
a sealed bundle, read by the operator on stderr (`aisef bundle lint|explain|approve|migrate`, `aisef run --project`):

* a story's test path that is absolute or climbs out of the repository is refused saying *which rule it broke*, not
  only which value it was (the sealed bundle's `"tests": [path, ...]` is documented nowhere else at the point of
  refusal);
* a story object that holds other keys than depends_on and tests is refused with the keys it holds *set apart from the
  keys it must have* — two lists in one line, and the label is what says which is which.

The other survivors of the batch (the closing parenthesis, the order of the held keys) have no reader that depends on
them and are audited, not tested (the batch report names what was checked)."""

from __future__ import annotations

import contextlib
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

from aisef2.app import bundle, bundle_cli  # noqa: E402


def bundle_of(stories) -> dict:
    """A sealed-bundle document whose only problem, if any, is in `stories` (shape_problems reads no kernel object)."""
    return {"format": bundle.FORMAT, "name": "calc", "description": "d",
            "requirements_document": {"path": "docs/requirements.md", "sha256": "0" * 64},
            "product_roots": ["app"], "requirements": [], "contracts": [], "approvals": [], "plan": {}, "facts": {},
            "stories": stories}


# What a reader is told about a story's test path that is refused: that it must be relative to / stay inside the
# repository root. A class of words, not the sentence: any statement of the rule passes, an empty or generic
# ("is not allowed") tail does not.
RULE = r"relative|repo|root|inside|within|outside|project|tree|absolute|parent|escape|climb"


def refusal(stories) -> str:
    """The text of the BundleError `shape_problems` raises for `stories`."""
    try:
        bundle.shape_problems(bundle_of(stories))
    except bundle.BundleError as e:
        return str(e)
    raise AssertionError(f"not refused: {stories!r}")


class AStoryTestPathOutsideTheRepositoryIsRefusedWithTheRuleItBroke(unittest.TestCase):
    """Pins aisef2/app/bundle.py::shape_problems [104]. `/abs/t.py`, `../t.py` and `tests/../tests/t.py` are refused
    under the field's JSON path and the offending value (the first is what locates the mistake). The rule is what
    tells the operator how to correct it — the last of the three is a path that *looks* relative — so it is the cause
    class a reader needs after the value: that a story's test is a path relative to the repository root. Without it
    the line is `$.stories.S1.tests: 'tests/../tests/t.py'` and states no rule at all."""

    def test_a_valid_path_is_not_refused(self):
        self.assertIsNone(bundle.shape_problems(bundle_of({"S1": {"depends_on": [], "tests": ["tests/test_add.py"]}})))

    def test_each_refusal_gives_the_field_the_value_and_then_the_rule(self):
        for bad in ("/abs/t.py", "../t.py", "tests/../tests/t.py"):
            with self.subTest(bad):
                msg = refusal({"S1": {"depends_on": [], "tests": ["tests/test_add.py", bad]}})
                head = f"$.stories.S1.tests: {bad!r}"
                self.assertTrue(msg.startswith(head), msg)
                self.assertRegex(msg[len(head):].lower(), RULE, f"no rule follows the value: {msg!r}")


class TheHeldKeysOfAStoryAreSetApartFromTheKeysItMustHave(unittest.TestCase):
    """Pins aisef2/app/bundle.py::shape_problems [107] (and [101], [90], which die of the same assertions). A story left
    with its authoring key `criteria` is refused naming the story, what it must hold (depends_on and tests) and what
    it holds. The two lists are told apart by the word that introduces the second: with it gone the held keys follow
    `tests` directly — `...depends_on and tests['criteria', 'depends_on', 'tests'])` — and read as a subscript of the
    field `tests`, not as the keys of the object."""

    def test_the_held_keys_follow_a_label_of_their_own(self):
        msg = refusal({"S1": {"depends_on": [], "tests": [], "criteria": []}})
        self.assertTrue(msg.startswith("$.stories.S1: "), msg)
        held = re.search(r"\[[^\]]*\]", msg)
        self.assertIsNotNone(held, f"the keys the story holds are not listed: {msg!r}")
        for key in ("criteria", "depends_on", "tests"):
            self.assertIn(key, held.group())
        rule = msg[len("$.stories.S1: "):held.start()] + msg[held.end():]
        for key in ("depends_on", "tests"):
            self.assertIn(key, rule, f"the keys the story must hold are not named: {msg!r}")
        label = msg[:held.start()].rpartition("tests")[2]
        self.assertRegex(label, "[A-Za-z]{2,}", f"the held keys are glued to the rule: {msg!r}")


class TheOperatorReadsTheRefusalOnStderr(unittest.TestCase):
    """The reader of both texts: `aisef bundle lint` refuses a sealed bundle whose story does not hold (exit 2, no
    report) and prints the text `shape_problems` raised, after `refused: `."""

    def test_lint_prints_the_text_and_exits_2(self):
        for stories in ({"S1": {"depends_on": [], "tests": ["../t.py"]}},
                        {"S1": {"depends_on": [], "tests": [], "criteria": []}}):
            with self.subTest(stories), tempfile.TemporaryDirectory() as t:
                path = pathlib.Path(t) / "bundle.json"
                path.write_text(json.dumps(bundle_of(stories)), encoding="utf-8")
                out, err = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    code = bundle_cli.main(["lint", str(path)])
                self.assertEqual((code, out.getvalue()), (2, ""))
                self.assertEqual(re.sub(r"^refused: ", "", err.getvalue().strip()), refusal(stories))


if __name__ == "__main__":
    unittest.main()
