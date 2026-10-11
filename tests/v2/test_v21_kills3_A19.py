"""A19 — aisef2/probe/process_effect.py, HARNESS/main: which absence reason a locator gets when the revision owns the
top-level name of the dotted module name (campaign-3 audit batch A19, survivor [15]).

The controller decides, before anything of the subject runs, whether the subject is absent. When the revision's own
search path does not resolve the module, it may look at the interpreter's path to tell "it exists nowhere" (no note)
from "it exists, but only outside the revision" (a note). It may look there only when the revision owns no top-level
name of that dotted name: the subject's process puts the revision first on `sys.path`, so a regular package or a plain
module the revision owns at the top level IS what that name means in the subject's process, and a submodule it lacks
does not resolve there at all — whatever the interpreter's own package of that name has. (A bare directory without
`__init__.py` is deliberately not pinned: a regular package further along the path wins over it in the subject's
process, so there the interpreter's module does resolve.)

The tests run the real probe (a controller process and the subject's process) over small checkouts.
"""

import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.probe.protocol import ObservationKind as K  # noqa: E402
from tests.v2 import test_probe_process_effect as base  # noqa: E402

LOCATOR = "json.decoder:JSONDecoder"   # `json` and `json.decoder` are the interpreter's own; no plain checkout names them
OUTSIDE = "resolves only outside the revision"
#: Layouts in which the revision owns the top-level name `json` without having `json.decoder`: each one shadows the
#: interpreter's own package of that name. The three ways a name is owned there: regular package, plain module, and a
#: package under `src/` (the other directory the subject's path and the controller's search both take).
SHADOWS = {
    "a regular package at the root": {"json/__init__.py": ""},
    "a plain module at the root": {"json.py": ""},
    "a regular package under src/": {"src/json/__init__.py": ""},
}
#: What the subject's process does with the revision first on its path (cli_invocation.AGENT, `sys.path[:0] = ...`):
#: exit 7 when `json.decoder` is not found, 0 when it imports.
PREMISE = ("import os, sys\n"
           "root = sys.argv[1]\n"
           "sys.path[:0] = [p for p in (root, os.path.join(root, 'src')) if os.path.isdir(p)]\n"
           "try:\n    import json.decoder\n"
           "except ModuleNotFoundError as e:\n    sys.exit(7 if e.name == 'json.decoder' else 8)\n"
           "sys.exit(0)\n")


def _checkout(files):
    holder = tempfile.TemporaryDirectory(prefix="aisef2-a19-", ignore_cleanup_errors=True)
    return holder, base.RevisionRef(base.SHA, base.checkout(holder.name, files))


class ATopLevelPackageTheRevisionOwnsIsTheRevisionsNamespace(unittest.TestCase):
    """Pins aisef2/probe/process_effect.py::HARNESS/main [15].

    `spec is None and PathFinder.find_spec(top, SEARCH) is None`: the interpreter's path is consulted only when the
    revision owns no such top-level name. A revision with its own (partial) `json` must get the absence of the
    revision's namespace — the note a module the revision lacks gets (empty) — and not the claim that `json.decoder`
    "resolves only outside the revision", which is false in the subject's process."""

    @classmethod
    def setUpClass(cls):
        cls.shadows = {}
        for label, files in SHADOWS.items():
            holder, cls.shadows[label] = _checkout(files)
            cls.addClassCleanup(holder.cleanup)
        holder, cls.plain = _checkout({"other/__init__.py": ""})
        cls.addClassCleanup(holder.cleanup)

    def see(self, at):
        s = base.spec(LOCATOR, [base.call(None)], {"returns": None})
        return base.P.observe(s, at, base.env())

    def test_the_premise_a_revision_package_hides_the_interpreters_submodule_from_the_subjects_process(self):
        """The subject's process puts the revision first: the shadowing name's lacking submodule is not found."""
        runs = [(label, at, 7) for label, at in self.shadows.items()] + [("a revision without it", self.plain, 0)]
        for label, at, expected in runs:
            with self.subTest(revision=label):
                done = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", PREMISE, at.root], stdin=subprocess.DEVNULL,
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                self.assertEqual(done.returncode, expected)

    def test_a_shadowed_package_lacking_the_submodule_is_absent_without_the_outside_note(self):
        for label, at in self.shadows.items():
            with self.subTest(revision=label):
                o = self.see(at)
                self.assertEqual((o.kind, o.verdict), (K.SUBJECT_ABSENT, base.R), o.detail)
                self.assertEqual(o.detail, "")   # the same reason class as a module the revision lacks (PE_6: nope:Book)

    def test_a_revision_that_owns_no_such_top_level_package_still_gets_the_outside_note(self):
        o = self.see(self.plain)
        self.assertEqual((o.kind, o.verdict), (K.SUBJECT_ABSENT, base.R), o.detail)
        self.assertEqual(o.detail, OUTSIDE)


if __name__ == "__main__":
    unittest.main()
