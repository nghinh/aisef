"""V2.1 (owner B-03, batch T27a): kill tests for the survivors of aisef2/probe/file_artifact.py's `python_imports` class,
in `FileArtifactProbe.observe`, `facts_of` and `import_facts`.

The earlier kill files run `python_imports` only over the LedgerLock reference package and the calibration fixtures: a
tree of `.py` files that all parse, a subject that exists, one statement per module. No test ran a python_imports
observation over an absent path, over a tree holding a non-Python file, over a file that is not UTF-8, or read the
facts of the observation, so each of those decisions could change unseen. Each class below names the target and the
mutants it pins; the tests drive `observe` / `run_probe` and read the written facts, never a sentence.

Facts are the evidence of an observation (`Observation.detail`); `classify_failure` keeps only the verdict, so the
facts are read by the calibration record and by an author debugging a refutation. What is asserted is therefore their
machine-read names and values (path, mode, files, locations, the file that broke the count), and the decision the
`present` flag carries into `observe`.
"""

from __future__ import annotations

import ast
import contextlib
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import BehaviorVerdict, ContractSatisfaction, SubjectAbsence  # noqa: E402
from aisef2.probe import file_artifact as fa  # noqa: E402
from aisef2.probe.protocol import ObservationKind as K, RevisionRef, run_probe  # noqa: E402
from aisef2.product.outcome import Executed, IndeterminateReason, contract_satisfaction  # noqa: E402
from tests.v2 import test_c2_file_artifact as base  # noqa: E402   (helpers only: its test classes are not imported)

S, R = BehaviorVerdict.SATISFIED, BehaviorVerdict.REFUTED
DECIDABLE, REQUIRES = SubjectAbsence.ABSENCE_IS_DECIDABLE, SubjectAbsence.REQUIRES_SUBJECT
P = fa.FileArtifactProbe()
ENV = base.ENV
STIM = {"imports_outside": {"stdlib": True, "allowed": []}}
INDETERMINATE = Executed(BehaviorVerdict.INDETERMINATE, IndeterminateReason.PRECONDITION_ABSENT)


def spec(locator: str, matches: int, stimulus: dict = STIM, *, absence=REQUIRES, expectation=S):
    return base.spec(locator, {"matches": matches}, stimulus, absence=absence, expectation=expectation)


def nul_line(data: bytes) -> str:
    """What the facts must say where a NUL byte's line would be, on this interpreter: the line its own parser names
    for the source, or `?` when it names none (a SyntaxError without one from Python 3.12, a ValueError before)."""
    try:
        ast.parse(data.decode("utf-8"))
    except (SyntaxError, ValueError) as e:
        line = getattr(e, "lineno", None)
        return "?" if line is None else str(line)
    return "parses"


class Tmp(unittest.TestCase):
    """A scratch directory per class, removed at the end."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="aisef2-t27a-")
        cls.addClassCleanup(cls._tmp.cleanup)
        cls.dir = pathlib.Path(cls._tmp.name)


class AbsentSubject(Tmp):
    """An absent path is SUBJECT_ABSENT carrying what zero import statements give: SATISFIED when the contract says
    matches 0, REFUTED when it says more; ABSENCE_IS_DECIDABLE then decides with it, REQUIRES_SUBJECT drops it for
    INDETERMINATE(PRECONDITION_ABSENT) — the rule grep_count has (test_FA_2), for the class V21-37 added.
    Pins aisef2/probe/file_artifact.py::FileArtifactProbe.observe [105, 128]."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.repo = base.Repo(cls.dir / "repo")
        cls.rev = cls.repo.commit({"app/main.py": base.MAIN})
        cls.ref = base.at(cls.repo.path, cls.rev)

    def test_a_decidable_prohibition_over_an_absent_package_takes_the_verdict_of_zero_statements(self):
        s = spec("path:vendor", 0, absence=DECIDABLE)
        o = P.observe(s, self.ref, ENV)
        self.assertEqual((o.kind, o.verdict), (K.SUBJECT_ABSENT, S))
        result = run_probe(P, s, self.ref, ENV).result
        self.assertEqual(result, Executed(S))
        self.assertIs(contract_satisfaction(result, s), ContractSatisfaction.SATISFIED)
        s = spec("path:vendor", 2, absence=DECIDABLE)
        o = P.observe(s, self.ref, ENV)
        self.assertEqual((o.kind, o.verdict), (K.SUBJECT_ABSENT, R))
        self.assertEqual(run_probe(P, s, self.ref, ENV).result, Executed(R))

    def test_requires_subject_drops_the_offered_verdict_for_either_count(self):
        for matches in (0, 2):
            with self.subTest(matches=matches):
                s = spec("path:vendor", matches, absence=REQUIRES)
                self.assertEqual(run_probe(P, s, self.ref, ENV).result, INDETERMINATE)


class SubjectFacts(Tmp):
    """A python_imports observation names its subject and what it was: the path in the tree and its mode — the
    directory that was walked, the file that was read, an executable read the same.
    Pins aisef2/probe/file_artifact.py::facts_of [45, 46, 73, 74]."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.repo = base.Repo(cls.dir / "repo")
        cls.repo.commit({"pkg/ok.py": b"import json\n"})
        cls.repo.index("pkg/tool.py", b"import json\n", "100755")
        cls.ref = base.at(cls.repo.path, cls.repo.commit_index("tool"))

    def test_the_facts_carry_the_path_and_the_mode_of_the_subject(self):
        for locator, path, mode in (("path:pkg", "pkg", "040000"), ("path:pkg/ok.py", "pkg/ok.py", "100644"),
                                    ("path:pkg/tool.py", "pkg/tool.py", "100755")):
            with self.subTest(locator=locator):
                o = P.observe(spec(locator, 0), self.ref, ENV)
                self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S))
                f = base.facts(o)
                self.assertEqual((f["path"], f["mode"]), (path, mode))


class DefaultSuffix(Tmp):
    """Without `suffixes` python_imports reads exactly the *.py files of the subject: a non-Python file next to the
    modules is neither parsed nor counted (it must not refute a correct package, nor add its text's `import` lines) —
    not one that merely resembles a module's name (`.pyi`, a name ending in `py` without the dot); an explicit
    `suffixes` replaces the default, it does not add to it.
    Pins aisef2/probe/file_artifact.py::facts_of [80, 81]."""

    NOT_PYTHON = ("d.txt", "NOTES.md", "stub.pyi", "script_py")

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.repo = base.Repo(cls.dir / "repo")
        cls.ref = base.at(cls.repo.path, cls.repo.commit({
            "pkg/a.py": b"import json\n", "pkg/NOTES.md": b"import yaml\n", "pkg/d.txt": b"not python (:\n",
            "pkg/stub.pyi": b"not python (:\n", "pkg/script_py": b"not python (:\n"}))

    def test_a_directory_is_judged_by_its_py_files_only(self):
        o = P.observe(spec("path:pkg", 0), self.ref, ENV)
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S))
        f = base.facts(o)
        self.assertEqual((f["files"], f["matches"], f["locations"]), (1, 0, []))
        self.assertNotIn("unparsable", f)

    def test_a_single_non_python_file_is_not_selected(self):
        for name in self.NOT_PYTHON:
            with self.subTest(name=name):
                o = P.observe(spec(f"path:pkg/{name}", 0), self.ref, ENV)
                self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S))
                f = base.facts(o)
                self.assertEqual((f["files"], f["matches"], f["locations"]), (0, 0, []))

    def test_explicit_suffixes_replace_the_default(self):
        o = P.observe(spec("path:pkg", 1, {**STIM, "suffixes": [".md"]}), self.ref, ENV)
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S))
        f = base.facts(o)
        self.assertEqual((f["files"], f["matches"], f["locations"]), (1, 1, [["pkg/NOTES.md", 1, ["yaml"]]]))


class ImportFacts(unittest.TestCase):
    """The facts of the count: files read, statements naming a top-level module outside `allowed` | stdlib, where each
    one is (file, line of the statement's first line, the outside modules, sorted) in tree order and at most
    `_LOCATIONS` of them, and which interpreter's stdlib decided. Relative imports are the project's own and not
    counted.
    Pins aisef2/probe/file_artifact.py::import_facts [8, 10, 11, 16, 18, 19, 26, 27, 29, 37, 47, 48, 49]."""

    OUTSIDE = {"stdlib": True, "allowed": ["numpy"]}

    def test_the_facts_count_statements_and_place_each_one(self):
        # one outside module per statement here: the order inside a statement is the sorting test's, not this one's.
        # Four statements in three files (the two counts differ); a statement spread over lines is placed at its first.
        f = fa.import_facts(self.OUTSIDE, [
            ("a.py", b"import os\nimport yaml\nimport os.path, requests\nfrom flask import (\n    Flask,\n    g,\n)\n"),
            ("b.py", b"from numpy.linalg import det\nfrom . import x\nfrom pkg.sub import y\n"),
            ("c.py", b"")])
        self.assertEqual({k: v for k, v in f.items() if k != "stdlib_of"},
                         {"present": True, "files": 3, "matches": 4,
                          "locations": [["a.py", 2, ["yaml"]], ["a.py", 3, ["requests"]], ["a.py", 4, ["flask"]],
                                        ["b.py", 3, ["pkg"]]]})
        self.assertEqual(fa.import_facts(self.OUTSIDE, [])["files"], 0)      # nothing read: the vacuity is visible

    def test_the_facts_name_the_interpreter_whose_stdlib_decided(self):
        f = fa.import_facts(self.OUTSIDE, [("a.py", b"import os\n")])
        v = sys.version_info
        self.assertIn(f"{v.major}.{v.minor}", f["stdlib_of"])

    def test_the_outside_modules_of_one_statement_are_sorted(self):
        names = [f"mod_{c}" for c in "qwertyuiopasdfghjk"]     # not in order; set order is the hash seed's
        f = fa.import_facts(self.OUTSIDE, [("a.py", f"import {', '.join(names)}\n".encode())])
        self.assertEqual((f["matches"], len(f["locations"])), (1, 1))
        self.assertEqual(f["locations"][0][2], sorted(names))

    def test_the_locations_are_capped_and_the_count_is_not(self):
        total = fa._LOCATIONS + 10
        f = fa.import_facts(self.OUTSIDE, [("big.py", "".join(f"import m{i}\n" for i in range(total)).encode())])
        self.assertEqual(f["matches"], total)
        self.assertEqual(len(f["locations"]), fa._LOCATIONS)
        self.assertEqual(f["locations"][0], ["big.py", 1, ["m0"]])
        self.assertEqual(f["locations"][-1], ["big.py", fa._LOCATIONS, [f"m{fa._LOCATIONS - 1}"]])


class UnestablishedCount(Tmp):
    """A selected file that is not UTF-8 or does not parse leaves the count unestablished: the observation is OBSERVED
    and REFUTED whatever M and whichever subject_absence the contract declares — never SUBJECT_ABSENT (a prohibition
    would be satisfied by an unreadable module), never INDETERMINATE, never an exception of the harness — and the facts
    name the file (and, for syntax, the line) and carry no `matches`.
    Pins aisef2/probe/file_artifact.py::import_facts [21, 32, 33, 34, 39, 40, 41, 42, 44] and [23]."""

    FILES = {"undec/ok.py": b"import yaml\n", "undec/latin1.py": b"# caf\xe9\n",
             "unpars/ok.py": b"import yaml\n", "unpars/bad.py": b"def (:\n",
             "unpars3/ok.py": b"import yaml\n", "unpars3/bad.py": b"import os\nimport sys\ndef (:\n",
             "nulbyte/ok.py": b"import yaml\n", "nulbyte/x.py": b"import os\nx = '\x00'\n"}
    # a NUL byte is a SyntaxError with no line from Python 3.12 (a ValueError before): the facts name the file and say
    # `?` where the line would be, never the text "None"; a syntax error names its own line (here the third). A name
    # that is not a Windows device name: the directory is `nulbyte`, not `nul`.
    WHICH = (("undec", "undecodable", "undec/latin1.py"), ("unpars", "unparsable", "unpars/bad.py:1"),
             ("unpars3", "unparsable", "unpars3/bad.py:3"),
             ("nulbyte", "unparsable", "nulbyte/x.py:" + nul_line(FILES["nulbyte/x.py"])))

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        repo = base.Repo(cls.dir / "repo")
        cls.refs = {"object_store": base.at(repo.path, repo.commit(cls.FILES))}
        plain = cls.dir / "plain"
        for rel, data in cls.FILES.items():
            (plain / rel).parent.mkdir(parents=True, exist_ok=True)
            (plain / rel).write_bytes(data)
        cls.refs["directory"] = RevisionRef("0" * 40, str(plain))

    def test_the_count_is_refuted_and_names_the_file_whatever_the_declared_absence(self):
        for read, ref in self.refs.items():
            for subject, key, want in self.WHICH:
                for absence, matches in ((DECIDABLE, 0), (DECIDABLE, 1), (REQUIRES, 0)):
                    s = spec(f"path:{subject}", matches, absence=absence)
                    with self.subTest(read=read, subject=subject, absence=absence.value, matches=matches):
                        o = P.observe(s, ref, ENV)
                        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, R))
                        f = base.facts(o)
                        self.assertEqual((f["read"], f[key]), (read, want))
                        self.assertNotIn("matches", f)
                        self.assertEqual(run_probe(P, s, ref, ENV).result, Executed(R))

    def test_a_nul_byte_is_no_count_and_no_crash_on_every_interpreter(self):
        # A NUL byte is a ValueError out of ast.parse up to Python 3.11 and a SyntaxError from 3.12; the second run
        # gives this interpreter the 3.11 behaviour.
        real = fa.ast.parse

        def parse_as_3_11(source, *a, **k):
            if "\0" in source:
                raise ValueError("source code string cannot contain null bytes")
            return real(source, *a, **k)

        for name, parser in (("this interpreter", contextlib.nullcontext()),
                             ("the 3.11 parser", mock.patch.object(fa.ast, "parse", parse_as_3_11))):
            with self.subTest(parser=name), parser:
                f = fa.import_facts(STIM["imports_outside"], [("ok.py", b"import json\n"), ("x.py", b"a = 1\x00\n")])
                self.assertIs(f["present"], True)
                want = "?" if name == "the 3.11 parser" else nul_line(b"a = 1\x00\n")   # never the text "None"
                self.assertEqual(f["unparsable"], f"x.py:{want}")
                self.assertNotIn("matches", f)
                self.assertEqual(fa.verdict_of("python_imports", {"matches": 0}, f), R)


if __name__ == "__main__":
    unittest.main()
