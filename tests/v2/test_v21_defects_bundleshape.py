"""V2.1 (owner B-03, survivor audit batch T24a): aisef2/app/bundle.py::shape_problems — a bundle's repository
confinement is read the way every platform the project supports reads a path.

Requirement (module docstring and the refusals' own wording): a bundle is one JSON document that is sealed on one
machine and run on another, and the project supports Windows. `requirements_document.path` and a story's `tests` are
paths "relative to the repository root", and a product root is "a top-level name of the project's own source tree".
Before the fix the three terms read the POSIX spelling only (`startswith('/')`, `PurePosixPath(...).parts`, `'/' in
root`), so what a Windows runner reads as absolute or as climbing out of the repository — a drive, a UNC share, a
backslash `..` — was sealed and loaded: `C:/x/t.py`, `C:\\x\\t.py`, `\\\\srv\\share\\t.py`, `..\\t.py`,
`tests\\..\\..\\t.py` as a test path or the requirements document, `a\\b`, `C:`, `..\\x` as a product root. (The
kernel's own `DeveloperTests` already reads `\\` as a separator; it refuses only `os.path.isabs`, which is the
running platform's reading, and in the middle of a run.)

What a consumer relies on, and what these tests assert:

* a path that is absolute or climbs out of the repository on ANY platform's reading is refused at load, at seal and
  by the CLI (exit 2), with the JSON path of the place that is wrong and the cause its POSIX form already had;
* what the POSIX reading refused is still refused, and nothing the POSIX reading accepted among the strings that
  hold no backslash and no colon is newly refused (an exhaustive comparison with the previous rule);
* what stays inside the repository on every platform is still accepted: the exact set refused is the one listed in
  `OUTSIDE_*` / `ROOTS_REFUSED_*`, the exact set accepted the one in `INSIDE` / `ROOTS_ACCEPTED`, both sides of the
  boundary.

Not covered, on purpose: a character that is not an ASCII letter before a colon (`1:x`) is a drive to Python 3.12+'s
`ntpath` and not to 3.11's `pathlib`; and what only a Windows API does with a name (reserved device names, trailing
dots and spaces, alternate data streams, a colon inside a name) — none of it is absolute or climbs out on the
readings above, and none of it is pinned either way here."""

from __future__ import annotations

import contextlib
import copy
import io
import itertools
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle, bundle_cli  # noqa: E402
from tests.v2.test_app_run import project_bundle  # noqa: E402

BASELINE = "a" * 40
HEX = "b" * 64

#: absolute, or climbing out of the repository, on a POSIX reading — refused before the fix and after it
OUTSIDE_POSIX = ("/etc/passwd", "/abs/t.py", "//srv/t.py", "../t.py", "tests/../../t.py", "tests/../tests/t.py",
                 "tests/..", "..")
#: ... on a Windows reading only — accepted before the fix: a drive (absolute or drive-relative), a UNC share or a
#: device path, a rooted path, and `..` between backslashes (or between a backslash and a slash)
OUTSIDE_WINDOWS = ("C:/x/t.py", "C:\\x\\t.py", "c:t.py", "C:", "\\\\srv\\share\\t.py", "//srv/share/t.py",
                   "\\\\?\\C:\\x\\t.py", "\\\\.\\pipe\\x", "\\\\srv", "\\x\\t.py", "\\t.py", "..\\t.py",
                   "tests\\..\\..\\t.py", "tests\\..", "..\\", "tests/..\\t.py", "tests\\../t.py")
#: neither absolute nor climbing out on any reading: accepted before the fix and after it. `a\\b.py` is a nested
#: relative path to a Windows runner and one file name to a POSIX one — inside the repository either way.
INSIDE = ("t.py", "C", "C.py", "tests/test_add.py", "./tests/test_add.py", "tests//test_add.py",
          "tests/./test_add.py", "tests/", "a..b/t.py", "..t.py", "t..", "tests/...", "tests\\test_add.py",
          "tests/sub\\t.py")

#: a product root is ONE top-level name on every platform: no separator of either, not `.` / `..`, no drive
ROOTS_REFUSED_POSIX = ("/", "/app", "a/b", "app/", ".", "..")
ROOTS_REFUSED_WINDOWS = ("a\\b", "app\\", "\\app", "..\\x", "C:", "c:app", "C:\\", "C:/", "\\\\srv\\share")
ROOTS_ACCEPTED = ("app", "tests", "my-pkg", "pkg.v2", "a..b", "..a", "A", "C")


class _Shape(unittest.TestCase):
    def setUp(self) -> None:
        self.bundle = project_bundle(BASELINE)

    def doc(self, *, tests=None, document_path=None, roots=None) -> dict:
        doc = copy.deepcopy(self.bundle)
        if tests is not None:
            doc["stories"]["S1"]["tests"] = tests
        if document_path is not None:
            doc["requirements_document"]["path"] = document_path
        if roots is not None:
            doc["product_roots"] = roots
        return doc

    def refusal(self, doc) -> str:
        """The text of the BundleError `load` refuses `doc` with (a traceback of another kind fails the test)."""
        with self.assertRaises(bundle.BundleError) as ctx:
            bundle.load(doc)
        return str(ctx.exception)

    def refused_at(self, doc, where: str) -> str:
        text = self.refusal(doc)
        self.assertTrue(text.startswith(where + ": "), text)
        self.assertTrue(text[len(where) + 2:].strip(), f"no reason follows the path: {text!r}")
        return text


class WindowsFormsAreRefusedLikeTheirPosixForms(_Shape):
    """The confinement of a path and of a root, on every platform (shape_problems, hence `load`)."""

    def test_a_story_test_path_that_is_not_inside_the_repository_is_refused_naming_it(self):
        for bad in OUTSIDE_POSIX + OUTSIDE_WINDOWS:
            with self.subTest(tests=bad):
                text = self.refused_at(self.doc(tests=["tests/test_add.py", bad]), "$.stories.S1.tests")
                self.assertIn(repr(bad), text)

    def test_a_requirements_document_path_that_is_not_inside_the_repository_is_refused(self):
        for bad in OUTSIDE_POSIX + OUTSIDE_WINDOWS:
            with self.subTest(path=bad):
                self.refused_at(self.doc(document_path=bad), "$.requirements_document.path")

    def test_a_product_root_that_is_not_one_top_level_name_is_refused(self):
        for bad in ROOTS_REFUSED_POSIX + ROOTS_REFUSED_WINDOWS:
            with self.subTest(root=bad):
                self.refused_at(self.doc(roots=["app", bad]), "$.product_roots")

    def test_the_cause_of_a_windows_form_is_the_cause_of_its_posix_form(self):
        """Same refusal class: the same sentence around the (repr of the) path — never a second wording to learn."""
        posix = {"C:/x/t.py": "/x/t.py", "\\x\\t.py": "/x/t.py", "..\\t.py": "../t.py",
                 "tests\\..\\..\\t.py": "tests/../../t.py", "\\\\srv\\share\\t.py": "//srv/share/t.py"}
        for win, pos in posix.items():
            with self.subTest(path=win):
                a = self.refusal(self.doc(tests=[win])).replace(repr(win), "<path>")
                b = self.refusal(self.doc(tests=[pos])).replace(repr(pos), "<path>")
                self.assertEqual(a, b)
                self.assertEqual(self.refusal(self.doc(document_path=win)), self.refusal(self.doc(document_path=pos)))
        for win, pos in (("a\\b", "a/b"), ("..\\x", "../x"), ("C:", "/")):
            with self.subTest(root=win):
                self.assertEqual(self.refusal(self.doc(roots=[win])), self.refusal(self.doc(roots=[pos])))

    def test_what_stays_inside_the_repository_on_every_platform_is_still_accepted(self):
        for ok in INSIDE:
            with self.subTest(path=ok):
                p = bundle.load(self.doc(tests=["tests/test_add.py", ok], document_path=ok))
                self.assertEqual((p.stories["S1"]["tests"], p.requirements_path), (["tests/test_add.py", ok], ok))

    def test_product_roots_that_are_single_names_are_still_accepted(self):
        p = bundle.load(self.doc(roots=list(ROOTS_ACCEPTED)))
        self.assertEqual(p.product_roots, ROOTS_ACCEPTED)


class PosixReadingIsUnchanged(_Shape):
    """Over every string of the alphabet `a . /` up to length 5 (no backslash, no colon: the strings whose reading is
    the same on every platform) the refusal is exactly the previous rule's — `startswith('/')` or a `..` component
    for a path, a `/` or `.` or `..` for a root."""

    WORDS = [w for n in range(1, 6) for w in map("".join, itertools.product("a./", repeat=n))]

    def refuses(self, doc) -> bool:
        try:
            bundle.shape_problems(doc)
        except bundle.BundleError:
            return True
        return False

    def test_paths(self):
        wrong = []
        for w in self.WORDS:
            before = w.startswith("/") or ".." in pathlib.PurePosixPath(w).parts
            for doc in (self.doc(tests=[w]), self.doc(document_path=w)):
                if self.refuses(doc) != before:
                    wrong.append(w)
        self.assertEqual(wrong, [])

    def test_roots(self):
        wrong = [w for w in self.WORDS if self.refuses(self.doc(roots=[w])) != ("/" in w or w in (".", ".."))]
        self.assertEqual(wrong, [])

    def test_a_requirements_document_path_that_is_not_a_non_empty_string_is_still_refused(self):
        for bad in ("", 7, None, ["docs/requirements.md"]):
            with self.subTest(path=bad):
                doc = self.doc()
                doc["requirements_document"]["path"] = bad     # `doc(document_path=None)` would leave it alone
                self.refused_at(doc, "$.requirements_document.path")


class ByTheToolsRoute(_Shape):
    """`aisef bundle seal` and `explain` never ask git about these three fields: the shape check is their gate."""

    def authoring(self, **changes) -> dict:
        a = json.loads((bundle_cli.EXAMPLES / "calc-1-story.json").read_text(encoding="utf-8"))["authoring"]
        a["baseline"] = BASELINE
        a["requirements_document"] = {"path": "docs/requirements.md", "sha256": HEX}
        a.update(changes)
        return a

    def refused_by_seal(self, authoring: dict, where: str) -> None:
        with self.assertRaises(bundle.BundleError) as ctx:
            bundle_cli.seal(authoring)
        self.assertTrue(str(ctx.exception).startswith(where + ": "), str(ctx.exception))

    def test_seal_refuses_a_windows_path_in_the_requirements_document(self):
        for bad in OUTSIDE_WINDOWS:
            with self.subTest(path=bad):
                a = self.authoring()
                a["requirements_document"]["path"] = bad
                self.refused_by_seal(a, "$.requirements_document.path")

    def test_seal_refuses_a_windows_story_test_path(self):
        for bad in OUTSIDE_WINDOWS:
            with self.subTest(path=bad):
                a = self.authoring()
                a["stories"]["S1"]["tests"] = ["tests/test_add.py", bad]
                self.refused_by_seal(a, "$.stories.S1.tests")

    def test_seal_refuses_a_windows_product_root(self):
        for bad in ROOTS_REFUSED_WINDOWS:
            with self.subTest(root=bad):
                self.refused_by_seal(self.authoring(product_roots=["app", bad]), "$.product_roots")

    def test_seal_still_seals_the_example_with_single_names_and_inside_paths(self):
        a = self.authoring(product_roots=list(ROOTS_ACCEPTED))
        a["requirements_document"]["path"] = "docs/a..b/requirements.md"
        sealed, _ = bundle_cli.seal(a)
        self.assertEqual((sealed["product_roots"], sealed["requirements_document"]["path"]),
                         (sorted(ROOTS_ACCEPTED), "docs/a..b/requirements.md"))

    def test_the_cli_answers_refused_with_exit_2_not_a_traceback(self):
        with tempfile.TemporaryDirectory() as d:
            cases = {"ok": self.bundle,
                     "path": self.doc(document_path="C:\\x\\requirements.md"),
                     "test": self.doc(tests=["..\\t.py"]),
                     "root": self.doc(roots=["a\\b"])}
            codes = {}
            for name, doc in cases.items():
                f = pathlib.Path(d) / f"{name}.json"
                f.write_text(json.dumps(doc), encoding="utf-8")
                err = io.StringIO()
                with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                    codes[name] = (bundle_cli.main(["explain", str(f)]), err.getvalue().startswith("refused: $."))
            self.assertEqual(codes, {"ok": (0, False), "path": (2, True), "test": (2, True), "root": (2, True)})


if __name__ == "__main__":
    unittest.main()
