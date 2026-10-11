"""V2.1 mutation survivors, batch T24a: the shape check of a project bundle (`aisef2/app/bundle.py::shape_problems`).

The check is the accept/refuse boundary of every bundle tool (`load`, `seal`, `lint`, `explain`, `approve`, `migrate`) and
of `aisef run`. What a reader of it relies on, and what is pinned here:

* a wrongly typed or out-of-bounds field is a `BundleError` — never a `TypeError` (`cli.run` lists no TypeError: a
  traceback, exit 1, which a pipeline reads as a delivery FAIL), never a later "kernel objects do not load" and never a
  silent repair (`str(7)` as a name, a malformed `approvals` rewritten into a list);
* the refusal names the JSON path of the place that is wrong, then ': ', then the reason (`<path>: <reason>`: the grammar
  of every message of the function). Where two causes call for opposite recovery (a field to add, a field to remove) the
  reason says which. No sentence is asserted;
* the repository-confinement terms (a requirements document and a story test are paths relative to the repository root,
  a product root is one top-level name) are the first and, in `seal`/`lint`, the only gate;
* the digest and the verdict do not depend on JSON key order, and the problem named first does not depend on the
  process's hash seed.

Offline: no repository, no client, no provider."""

from __future__ import annotations

import copy
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle, bundle_cli  # noqa: E402
from tests.v2.test_app_run import project_bundle  # noqa: E402

BASELINE = "a" * 40
HEX = "b" * 64


class _Shape(unittest.TestCase):
    def setUp(self) -> None:
        self.bundle = project_bundle(BASELINE)

    def doc(self) -> dict:
        return copy.deepcopy(self.bundle)

    def refusal(self, doc) -> str:
        """The text of the BundleError `load` refuses `doc` with (any other outcome fails the test)."""
        with self.assertRaises(bundle.BundleError) as ctx:
            bundle.load(doc)
        return str(ctx.exception)

    def assert_refused_at(self, doc, where: str) -> str:
        """`doc` is refused with `<where>: <a reason>`: the path first, then the separator, then something. The
        operator of `aisef run` / `aisef bundle` reads `refused: <text>` and acts on it; a path with nothing after it
        says where and not what (the message grammar of every refusal of the shape check). No wording is asserted."""
        text = self.refusal(doc)
        self.assertTrue(text.startswith(where + ": "), text)
        self.assertTrue(text[len(where) + 2:].strip(), f"no reason follows the path: {text!r}")
        return text


class NameAndDescription(_Shape):
    """`name` and `description` are JSON strings. `load` would coerce them with `str()`: 7 becomes the project's name
    '7', None becomes the word 'None' in the instruction the developer model is given.

    Pins aisef2/app/bundle.py::shape_problems [7, 8, 78, 79]"""

    def test_a_name_or_a_description_that_is_not_a_string_is_refused_with_its_path(self):
        for key in ("name", "description"):
            for bad in (7, None, ["x"]):
                with self.subTest(key=key, bad=bad):
                    doc = self.doc()
                    doc[key] = bad
                    self.assert_refused_at(doc, f"$.{key}")


class ObjectLists(_Shape):
    """`requirements`, `contracts` and `approvals` are lists of objects: refused at the shape, with their own path.
    Without it a null is a TypeError out of the check (exit 1), a list of numbers surfaces only as the kernel
    constructors' "do not load" (no path) and a string or object in place of the list is accepted by the shape.

    Pins aisef2/app/bundle.py::shape_problems [11, 12, 31, 81]"""

    def test_each_list_of_objects_refuses_a_value_that_is_not_one(self):
        for key in ("requirements", "contracts", "approvals"):
            for bad in (None, [1], {}, ""):
                with self.subTest(key=key, bad=bad):
                    doc = self.doc()
                    doc[key] = bad
                    self.assert_refused_at(doc, f"$.{key}")

    def test_a_list_holding_one_non_object_among_objects_is_refused(self):
        for key in ("requirements", "contracts", "approvals"):
            with self.subTest(key=key):
                doc = self.doc()
                doc[key] = [*doc[key], 3]
                self.assert_refused_at(doc, f"$.{key}")

    def test_the_tools_refuse_a_malformed_list_as_a_bundle_error_and_never_repair_it(self):
        """`approve` returned `{**bundle, approvals: [*'', new]}` for approvals == '': a human-approval field of the
        wrong type silently rewritten into a list. A malformed list is refused, not repaired, and not a TypeError."""
        for key in ("contracts", "approvals"):
            for bad in (None, [1], ""):
                with self.subTest(key=key, bad=bad):
                    doc = self.doc()
                    doc[key] = bad
                    with self.assertRaises(bundle.BundleError):
                        bundle_cli.approve(doc, "BC-ADD", "human:tester", 1.0)


class RequirementsDocumentPath(_Shape):
    """`requirements_document.path` is a non-empty string, relative to the repository root, with no '..' component.
    `seal` and `lint` never ask git, so this is the only check there (git is a second line at run time).

    Pins aisef2/app/bundle.py::shape_problems [16, 51, 52]"""

    def test_a_path_that_is_not_inside_the_repository_is_refused_with_its_path(self):
        for bad in ("", "/etc/passwd", "../x.md", "docs/../../x.md", "docs/..", "..", 7, None):
            with self.subTest(path=bad):
                doc = self.doc()
                doc["requirements_document"]["path"] = bad
                self.assert_refused_at(doc, "$.requirements_document.path")


class RequirementsDocumentDigest(_Shape):
    """`requirements_document.sha256` is 64 lowercase hex characters: the form that makes the later comparison with
    the document's digest meaningful (an unequal string can never match, and `lint` would have said READY).

    Pins aisef2/app/bundle.py::shape_problems [17, 53]"""

    def test_a_digest_that_is_not_64_lowercase_hex_is_refused_with_its_path(self):
        # too short, too long, the wrong case, not hex, 64 hex characters followed by a newline (`match` for `fullmatch`
        # accepts it, and `{64,}` accepts the 65), then the two non-strings
        for bad in ("", "abc", "a" * 63, "a" * 65, "A" * 64, "g" * 64, "a" * 64 + "\n", 7, None):
            with self.subTest(sha256=bad):
                doc = self.doc()
                doc["requirements_document"]["sha256"] = bad
                self.assert_refused_at(doc, "$.requirements_document.sha256")


class RequirementsDocumentCause(_Shape):
    """A requirements document that is not exactly {path, sha256} says which field is missing and which is not a
    field of it: opposite recoveries (add one, remove the other), so a swapped or an empty cause sends the operator
    the wrong way. The path and the cause are separated, so '$.requirements_document.sha256' is never read as
    a field called 'sha256missing'.

    Pins aisef2/app/bundle.py::shape_problems [67, 82, 95, 96, 97, 105, 106, 112, 113]"""

    def test_a_missing_field_is_reported_missing(self):
        for field in ("path", "sha256"):
            with self.subTest(field=field):
                doc = self.doc()
                del doc["requirements_document"][field]
                text = self.assert_refused_at(doc, f"$.requirements_document.{field}")
                reason = text[len(f"$.requirements_document.{field}: "):]
                self.assertIn("missing", reason)
                self.assertNotIn("not a field", reason)

    def test_a_field_that_is_not_one_is_reported_as_not_a_field(self):
        for field in ("zzz", ""):      # '' is a key like another: it must not be read as one of the missing fields
            with self.subTest(field=field):
                doc = self.doc()
                doc["requirements_document"][field] = "x"
                text = self.assert_refused_at(doc, f"$.requirements_document.{field}")
                reason = text[len(f"$.requirements_document.{field}: "):]
                self.assertIn("not a field", reason)
                self.assertNotIn("missing", reason)


class PlanIsAnObject(_Shape):
    """A `plan` that is not an object is refused with its path. (The kernel-object handler of `load` would refuse it
    too, as "do not load" with a TypeError's text and no path: the path is what this branch adds.)

    Pins aisef2/app/bundle.py::shape_problems [58]"""

    def test_a_plan_that_is_not_an_object_is_refused_with_its_path(self):
        for bad in ([], None, "PLAN-CALC"):
            with self.subTest(plan=bad):
                doc = self.doc()
                doc["plan"] = bad
                self.assert_refused_at(doc, "$.plan")


class ProductRoots(_Shape):
    """A product root is one top-level name of the project's own source tree. '.' and '..' are not names: a root
    that matches no changed file turns the review's required scope and the owner attribution into vacuous values
    while the bundle seals and lints READY.

    Pins aisef2/app/bundle.py::shape_problems [86, 87, 98, 99]"""

    def test_a_dot_root_is_refused(self):
        for roots in (["."], ["app", "."], [".", "app"]):
            with self.subTest(roots=roots):
                doc = self.doc()
                doc["product_roots"] = roots
                self.assert_refused_at(doc, "$.product_roots")

    def test_a_parent_root_is_refused(self):
        for roots in ([".."], ["app", ".."], ["..", "app"]):
            with self.subTest(roots=roots):
                doc = self.doc()
                doc["product_roots"] = roots
                self.assert_refused_at(doc, "$.product_roots")


class StoryObject(_Shape):
    """A story is an object of exactly `depends_on` and `tests`, in any key order (a JSON object is unordered and the
    bundle's digest is over sorted keys). A story that is not an object, or holds another key (an authoring
    document's `criteria`, passed where a sealed bundle is expected), is refused with the story's path — and the
    keys it does hold, which is what tells the operator that.

    Pins aisef2/app/bundle.py::shape_problems [71, 90, 101]"""

    def test_the_key_order_of_a_story_is_not_significant(self):
        doc = self.doc()
        story = doc["stories"]["S1"]
        doc["stories"]["S1"] = {"tests": story["tests"], "depends_on": story["depends_on"]}
        self.assertEqual(list(doc["stories"]["S1"]), ["tests", "depends_on"])
        self.assertEqual(bundle.load(doc).digest, bundle.load(self.doc()).digest)

    def test_a_story_that_is_not_an_object_is_refused_as_a_bundle_error(self):
        for bad in (None, 7, "ab", ["depends_on", "tests"]):
            with self.subTest(story=bad):
                doc = self.doc()
                doc["stories"]["S1"] = bad
                self.assert_refused_at(doc, "$.stories.S1")

    def test_a_story_holding_another_key_is_refused_naming_the_key(self):
        doc = self.doc()
        doc["stories"]["S1"]["criteria"] = []
        text = self.assert_refused_at(doc, "$.stories.S1")
        self.assertIn("criteria", text)

    def test_a_story_without_a_key_is_refused_with_its_path(self):
        """Missing one of the two keys; and one key replaced by another (two keys, not these two: a count of keys
        is not the rule, the names are)."""
        for story in ({"tests": ["tests/test_add.py"]}, {"depends_on": []},
                      {"depends_on": [], "criteria": []}, {"tests": ["tests/test_add.py"], "criteria": []}):
            with self.subTest(keys=sorted(story)):
                doc = self.doc()
                doc["stories"]["S1"] = story
                self.assert_refused_at(doc, "$.stories.S1")


class StoryLists(_Shape):
    """A story's `depends_on` is a list of non-empty strings; the refusal names which of the story's two lists
    (`depends_on` or `tests`) is the wrong one. A `tests` entry is a path relative to the repository root: the kernel
    refuses only an absolute one (and in the middle of a run), so a '..' component is this check's alone — and
    `DeveloperTests.owns` compares the un-normalised string, so a '..' path charges the developer for the author's
    mistake.

    Pins aisef2/app/bundle.py::shape_problems [63, 94, 102, 103, 110, 111]"""

    def test_depends_on_that_is_not_a_list_of_strings_is_refused_with_its_own_path(self):
        for bad in ("S1", [1], [""], None):
            with self.subTest(depends_on=bad):
                doc = self.doc()
                doc["stories"]["S1"]["depends_on"] = bad
                self.assert_refused_at(doc, "$.stories.S1.depends_on")

    def test_a_test_path_outside_the_repository_is_refused_naming_the_path(self):
        for bad in ("/abs/t.py", "../t.py", "tests/../tests/test_add.py", "tests/..", ".."):
            for tests in (["tests/test_add.py", bad], [bad, "tests/test_add.py"]):     # every entry is checked
                with self.subTest(tests=tests):
                    doc = self.doc()
                    doc["stories"]["S1"]["tests"] = tests
                    text = self.assert_refused_at(doc, "$.stories.S1.tests")
                    self.assertIn(bad, text)


class CanonicalOrder(_Shape):
    """Which problem is named first, and in which order the unknown story ids are listed, is the same in every
    process: sorted, never the order of a set (which follows the process's hash seed). Forty distinct key sets: a
    set-ordered implementation passes all of them with probability 2^-40 (the first) and 6^-40 (the second), and the
    sorted one never fails. One assertion over all of them: the failure names no hash-dependent subtest.

    Pins aisef2/app/bundle.py::shape_problems [15, 45]"""

    def test_the_first_problem_of_a_requirements_document_is_the_alphabetically_first(self):
        out_of_order = []
        for i in range(40):
            doc = self.doc()
            doc["requirements_document"][f"x{i}b"] = "v"
            doc["requirements_document"][f"x{i}a"] = "v"
            text = self.refusal(doc)
            if not text.startswith(f"$.requirements_document.x{i}a: "):
                out_of_order.append(i)
        self.assertEqual(out_of_order, [])

    def test_the_unknown_stories_of_a_depends_on_are_listed_sorted(self):
        out_of_order = []
        for i in range(40):
            doc = self.doc()
            ids = [f"UNK{i:02d}c", f"UNK{i:02d}a", f"UNK{i:02d}b"]
            doc["stories"]["S1"]["depends_on"] = ids
            text = self.assert_refused_at(doc, "$.stories.S1.depends_on")
            if any(x not in text for x in ids) or [text.index(x) for x in sorted(ids)] != sorted(text.index(x) for x in ids):
                out_of_order.append(i)
        self.assertEqual(out_of_order, [])


class SealRoute(unittest.TestCase):
    """`aisef bundle seal` without --repo never reads the requirements document: the shape check at the end of `seal`
    is the only gate of its path and digest, and the sha256 refusal is the operator's recovery message when the
    authoring document gives none.

    Pins aisef2/app/bundle.py::shape_problems [16, 17, 51, 52, 53, 63, 86, 87, 94, 98, 99, 102, 103]: the same
    mutants as the classes above, by the tool's route (the classes above kill them through `load`)."""

    def authoring(self, **document) -> dict:
        a = json.loads((bundle_cli.EXAMPLES / "calc-1-story.json").read_text(encoding="utf-8"))["authoring"]
        a["baseline"] = BASELINE
        a["requirements_document"] = {"path": "docs/requirements.md", **document}
        return a

    def test_the_example_seals_with_a_digest_given(self):
        sealed, _ = bundle_cli.seal(self.authoring(sha256=HEX))
        self.assertEqual(sealed["requirements_document"], {"path": "docs/requirements.md", "sha256": HEX})

    def test_without_a_digest_and_without_a_repository_the_refusal_names_the_digest(self):
        with self.assertRaises(bundle.BundleError) as ctx:
            bundle_cli.seal(self.authoring())
        text = str(ctx.exception)
        self.assertTrue(text.startswith("$.requirements_document.sha256: "), text)
        self.assertTrue(text[len("$.requirements_document.sha256: "):].strip(), text)

    def refused_by_seal(self, authoring: dict, where: str) -> None:
        with self.assertRaises(bundle.BundleError) as ctx:
            bundle_cli.seal(authoring)
        self.assertTrue(str(ctx.exception).startswith(where + ": "), str(ctx.exception))

    def test_a_requirements_path_that_leaves_the_repository_is_not_sealed(self):
        for bad in ("../x.md", "/etc/passwd", "docs/../../x.md"):
            with self.subTest(path=bad):
                a = self.authoring(sha256=HEX)
                a["requirements_document"]["path"] = bad
                self.refused_by_seal(a, "$.requirements_document.path")

    def test_a_story_test_path_that_leaves_the_repository_is_not_sealed(self):
        for bad in ("../t.py", "/abs/t.py"):
            with self.subTest(path=bad):
                a = self.authoring(sha256=HEX)
                a["stories"]["S1"]["tests"] = [bad]
                self.refused_by_seal(a, "$.stories.S1.tests")

    def test_a_dot_or_parent_product_root_is_not_sealed(self):
        for bad in (".", ".."):
            with self.subTest(root=bad):
                a = self.authoring(sha256=HEX)
                a["product_roots"] = ["app", bad]
                self.refused_by_seal(a, "$.product_roots")


if __name__ == "__main__":
    unittest.main()
