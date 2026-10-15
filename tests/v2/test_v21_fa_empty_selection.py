"""V2.1 (owner decision 2026-10-15, PM-9) — a selection of no file is an absent subject, and the contract's own
`subject_absence` decides: `grep_count` and `python_imports` over a path that is in the tree but selects no file are
SUBJECT_ABSENT like a path that is not in the tree, so REQUIRES_SUBJECT drops the count for
INDETERMINATE(PRECONDITION_ABSENT) and ABSENCE_IS_DECIDABLE keeps the verdict zero matches always gave.

Before this change a directory holding no `.py`, or one file the suffixes do not take, was OBSERVED with `files: 0` and
a count of zero: SATISFIED for every prohibition — `matches: 0` — whatever the contract declared, while the very same
contract over a path that was not there was INDETERMINATE. Every branch of the policy is pinned here, by what the
observation says and what `run_probe` makes of it:

* which situations are a selection of none: a directory of files the suffixes do not take, one file they do not take,
  a directory of directories (a plain tree: git holds no empty directory), a path not in the tree — on both read paths;
* which are not, and keep the verdict they always had: an empty file, a file of the byte-order mark alone, a file the
  count cannot read (binary: `grep_count` skips it and names it, `python_imports` cannot parse it), a directory with
  a file among others, every mix of `suffixes` the grammar has — the grammar has no `exclude`;
* the declaration, both values, against both counts (0 and more) and both classes, on the observation (kind, verdict)
  and on the result (`Executed(...)`) and the contract satisfaction a decision reads;
* the classes that have no selection (`exists`, `content`) are not touched;
* a generated family of trees, the reference being a count written here, independently of the probe: whatever the
  tree, the observation is absent exactly when no file is selected and is the reference's count otherwise.
"""

from __future__ import annotations

import ast
import codecs
import itertools
import pathlib
import random
import re
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import (  # noqa: E402
    BehaviorVerdict, ContractSatisfaction, MeasurementPoint, ObligationRole, StoryAdmissionDisposition, SubjectAbsence,
)
from aisef2.control.owner import FailureCode, Owner  # noqa: E402
from aisef2.control.routing import row_for  # noqa: E402
from aisef2.probe import file_artifact as fa  # noqa: E402
from aisef2.probe.protocol import ObservationKind as K, RevisionRef, run_probe  # noqa: E402
from aisef2.product.outcome import Executed, IndeterminateReason, InvalidSpec, contract_satisfaction  # noqa: E402
from tests.v2 import test_c2_file_artifact as base  # noqa: E402   (helpers only: its test classes are not imported)

S, R = BehaviorVerdict.SATISFIED, BehaviorVerdict.REFUTED
DECIDABLE, REQUIRES = SubjectAbsence.ABSENCE_IS_DECIDABLE, SubjectAbsence.REQUIRES_SUBJECT
INDETERMINATE = Executed(BehaviorVerdict.INDETERMINATE, IndeterminateReason.PRECONDITION_ABSENT)
P = fa.FileArtifactProbe()
ENV = base.ENV
BOM = codecs.BOM_UTF8
GREP = {"grep": "^import telemetry", "suffixes": [".py"]}
IMPORTS = {"imports_outside": {"stdlib": True, "allowed": []}}
CLASSES = (("grep_count", GREP), ("python_imports", IMPORTS))

FILES = {
    "docs/README.md": b"import telemetry\n",        # text the grep would match, if the suffix selected it
    "docs/data.json": b"{}\n",
    "note/notes.md": b"import telemetry\n",
    "pkg/__init__.py": b"",                         # an empty module: a file, so a subject
    "pkg/a.py": b"import json\n",
    "dirty/a.py": b"import telemetry\nimport requests\n",
    "bin/x.py": b"import os\x00\n",                 # a NUL byte: binary for the grep, no module for the parser
    "bom/b.py": BOM,                                # the byte-order mark alone
}


def spec(locator: str, matches: int, stimulus: dict, absence: SubjectAbsence = REQUIRES, expectation=S):
    return base.spec(locator, {"matches": matches}, stimulus, absence=absence, expectation=expectation)


class Trees(unittest.TestCase):
    """The same files on both read paths: a repository (the object store at a revision) and a plain directory (a
    calibration fixture's way). The plain one also holds a directory of directories, which git cannot."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="aisef2-pm9-")
        cls.addClassCleanup(cls._tmp.cleanup)
        d = pathlib.Path(cls._tmp.name)
        repo = base.Repo(d / "repo")
        cls.store = base.at(repo.path, repo.commit(FILES))
        plain = d / "plain"
        for rel, data in FILES.items():
            (plain / rel).parent.mkdir(parents=True, exist_ok=True)
            (plain / rel).write_bytes(data)
        (plain / "emptydirs" / "sub").mkdir(parents=True)
        cls.plain = RevisionRef("0" * 40, str(plain))
        cls.reads = (("object_store", cls.store), ("directory", cls.plain))


class SelectionOfNone(Trees):
    """The situations that select no file, each over both classes, both counts, both declarations, both reads."""

    #: (locator, a path of the tree?) — a path that is in the tree selects none; a path that is not has no selection
    EMPTY = (("path:docs", True), ("path:note/notes.md", True), ("path:note", True), ("path:vendor", False),
             ("path:docs/missing.py", False))

    def test_every_branch_is_an_absent_subject_decided_by_the_declaration(self):
        n = 0
        for (read, ref), (cls, stim), (locator, in_tree), matches, absence in itertools.product(
                self.reads, CLASSES, self.EMPTY, (0, 1, 3), (REQUIRES, DECIDABLE)):
            s = spec(locator, matches, stim, absence)
            offered = S if matches == 0 else R           # what zero matches say of the observable
            with self.subTest(read=read, cls=cls, locator=locator, matches=matches, absence=absence.value):
                o = P.observe(s, ref, ENV)
                self.assertEqual((o.kind, o.verdict), (K.SUBJECT_ABSENT, offered))
                f = base.facts(o)
                self.assertEqual((f["read"], f["present"], f["path"]), (read, False, locator[5:]))
                self.assertNotIn("matches", f)        # nothing was counted: no zero to be read as a count
                if in_tree:
                    self.assertEqual(f["files"], 0)   # the path is there; it selects no file
                    self.assertEqual(f["suffixes"], [".py"])
                else:
                    self.assertNotIn("files", f)
                result = run_probe(P, s, ref, ENV).result
                self.assertEqual(result, INDETERMINATE if absence is REQUIRES else Executed(offered))
                sat = contract_satisfaction(result, s)
                if absence is REQUIRES:
                    self.assertIs(sat, ContractSatisfaction.INDETERMINATE)
                else:
                    self.assertIs(sat, ContractSatisfaction.SATISFIED if matches == 0 else ContractSatisfaction.UNSATISFIED)
                n += 1
        self.assertEqual(n, 2 * 2 * 5 * 3 * 2)

    def test_a_directory_of_directories_selects_none_on_the_plain_tree(self):
        for cls, stim in CLASSES:
            for absence in (REQUIRES, DECIDABLE):
                with self.subTest(cls=cls, absence=absence.value):
                    o = P.observe(spec("path:emptydirs", 0, stim, absence), self.plain, ENV)
                    self.assertEqual((o.kind, o.verdict), (K.SUBJECT_ABSENT, S))
                    f = base.facts(o)
                    self.assertEqual((f["present"], f["files"], f["mode"], f["read"]), (False, 0, "040000", "directory"))
                    self.assertEqual(run_probe(P, spec("path:emptydirs", 0, stim, absence), self.plain, ENV).result,
                                     INDETERMINATE if absence is REQUIRES else Executed(S))

    def test_a_file_the_suffixes_do_not_take_is_the_same_as_none_and_a_file_they_take_is_a_subject(self):
        for suffixes, locator, selects in (([".py"], "path:note/notes.md", False), ([".md"], "path:note/notes.md", True),
                                           ([".md", ".py"], "path:note/notes.md", True), ([".py"], "path:pkg/a.py", True),
                                           ([".json"], "path:pkg/a.py", False), ([".pyi"], "path:pkg/a.py", False)):
            s = spec(locator, 0, {"grep": "never matches here", "suffixes": suffixes})
            with self.subTest(suffixes=suffixes, locator=locator):
                for _, ref in self.reads:
                    o = P.observe(s, ref, ENV)
                    self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S) if selects else (K.SUBJECT_ABSENT, S))
                    self.assertEqual(run_probe(P, s, ref, ENV).result, Executed(S) if selects else INDETERMINATE)

    def test_the_default_selection_of_each_class_is_what_is_empty(self):
        # grep_count without suffixes selects every file: docs is not empty for it; python_imports selects .py: it is
        for _, ref in self.reads:
            o = P.observe(spec("path:docs", 1, {"grep": "^import telemetry"}), ref, ENV)
            self.assertEqual((o.kind, o.verdict, base.facts(o)["files"], base.facts(o)["matches"]), (K.OBSERVED, S, 2, 1))
            o = P.observe(spec("path:docs", 0, IMPORTS), ref, ENV)
            self.assertEqual((o.kind, o.verdict), (K.SUBJECT_ABSENT, S))
            self.assertEqual(base.facts(o)["suffixes"], [".py"])      # the default is said: it is what selected none
            o = P.observe(spec("path:docs", 0, {"grep": "x", "suffixes": []}), ref, ENV)   # [] is the default, not none
            self.assertEqual((o.kind, base.facts(o)["files"]), (K.OBSERVED, 2))
            # an explicit `suffixes` replaces the default, it does not add to it: README.md parses as one import of an
            # outside module (the text is Python), data.json is not taken
            o = P.observe(spec("path:docs", 1, {**IMPORTS, "suffixes": [".md"]}), ref, ENV)
            self.assertEqual((o.kind, o.verdict, base.facts(o)["files"], base.facts(o)["matches"]), (K.OBSERVED, S, 1, 1))

    def test_there_is_no_way_to_exclude_and_none_is_asked_for(self):
        for stim in ({"grep": "x", "exclude": [".md"]}, {"grep": "x", "suffixes": [".py"], "exclude": [".md"]},
                     {**IMPORTS, "exclude": [".md"]}, {"grep": "x", "allow_empty": True}, {"grep": "x", "non_empty": True}):
            with self.subTest(stimulus=stim):
                s = spec("path:docs", 0, stim)
                o = P.observe(s, self.store, ENV)
                self.assertEqual((o.kind, o.verdict), (K.UNSUPPORTED, None))
                self.assertIsInstance(run_probe(P, s, self.store, ENV).result, InvalidSpec)

    def test_a_refusal_outranks_absence_and_a_cap_is_only_for_what_is_selected(self):
        with mock.patch.object(fa, "FILE_CAP", 5):
            # docs/README.md (17 bytes) is selected by a grep without suffixes: over the cap, refused, never a verdict
            o = P.observe(spec("path:docs", 0, {"grep": "x"}), self.store, ENV)
            self.assertEqual((o.kind, o.verdict), (K.HARNESS_FAILED, None))
            self.assertIn("per-file cap", o.detail)
            # with `.py` nothing of docs is selected, so nothing is read: absent, not refused
            o = P.observe(spec("path:docs", 0, GREP), self.store, ENV)
            self.assertEqual((o.kind, o.verdict), (K.SUBJECT_ABSENT, S))
            self.assertEqual(run_probe(P, spec("path:docs", 0, GREP), self.store, ENV).result, INDETERMINATE)


class WhatTheOperatorMeets(Trees):
    """The routes an emptied directory takes are the routes an absent path always took (§10.3, routing.py): it is the
    same outcome, INDETERMINATE(PRECONDITION_ABSENT), with nothing new in the table."""

    def test_an_empty_selection_routes_exactly_as_an_absent_path_does(self):
        for cls, stim in CLASSES:
            empty = run_probe(P, spec("path:docs", 0, stim, REQUIRES), self.store, ENV).result
            absent = run_probe(P, spec("path:vendor", 0, stim, REQUIRES), self.store, ENV).result
            s = spec("path:docs", 0, stim, REQUIRES)
            self.assertEqual(empty, absent)
            self.assertEqual(empty, INDETERMINATE)
            with self.subTest(cls=cls):
                # at the parent the role decides (RFC §10.3): INTRODUCE expects the subject to be absent before the
                # story; PRESERVE and VERIFY cannot be proved over a subject that is gone — the plan is broken
                intro = row_for(empty, s, MeasurementPoint.PARENT, ObligationRole.INTRODUCE)
                self.assertEqual((intro.failure, intro.disposition), (None, StoryAdmissionDisposition.READY))
                for role in (ObligationRole.PRESERVE, ObligationRole.VERIFY):
                    r = row_for(empty, s, MeasurementPoint.PARENT, role)
                    self.assertEqual((r.failure.code, r.failure.owner, r.disposition),
                                     (FailureCode.PRECONDITION_BROKEN, Owner.PLAN,
                                      StoryAdmissionDisposition.PRECONDITION_BROKEN))
                # after the developer's change: the subject the story was to establish is not there
                r = row_for(empty, s, MeasurementPoint.CANDIDATE, ObligationRole.VERIFY)
                self.assertEqual((r.failure.code, r.failure.owner),
                                 (FailureCode.SUBJECT_ABSENT_AT_CANDIDATE, Owner.DEVELOPER))
                # after the merge: a subject that was there is lost
                r = row_for(empty, s, MeasurementPoint.POST_MERGE, ObligationRole.VERIFY)
                self.assertEqual((r.failure.code, r.failure.owner),
                                 (FailureCode.POST_MERGE_SUBJECT_LOST, Owner.INTEGRATION))

    def test_the_declaration_that_decides_is_the_contracts_own_so_a_decidable_prohibition_is_a_verdict(self):
        for cls, stim in CLASSES:
            s = spec("path:docs", 0, stim, DECIDABLE)
            result = run_probe(P, s, self.store, ENV).result
            self.assertEqual(result, Executed(S))
            for point in MeasurementPoint:
                with self.subTest(cls=cls, point=point.value):
                    r = row_for(result, s, point, ObligationRole.VERIFY)
                    self.assertIsNone(r.failure)                      # SATISFIED: nothing to charge, nobody blocked


class WhatIsStillASubject(Trees):
    """A selection that holds a file is a subject whatever the file holds, and the verdict is the one the count always
    gave: OBSERVED, under either declaration, with `files` at least one."""

    # (locator, class, M, verdict, key facts)
    CASES = (
        ("path:pkg", "grep_count", 0, S, {"files": 2, "matches": 0}),
        ("path:pkg", "grep_count", 1, R, {"files": 2, "matches": 0}),
        ("path:pkg", "python_imports", 0, S, {"files": 2, "matches": 0}),
        ("path:pkg", "python_imports", 1, R, {"files": 2, "matches": 0}),
        ("path:pkg/__init__.py", "grep_count", 0, S, {"files": 1, "matches": 0}),       # an empty file is a file
        ("path:pkg/__init__.py", "python_imports", 0, S, {"files": 1, "matches": 0}),
        ("path:dirty", "grep_count", 1, S, {"files": 1, "matches": 1}),
        ("path:dirty", "grep_count", 0, R, {"files": 1, "matches": 1}),
        ("path:dirty", "python_imports", 2, S, {"files": 1, "matches": 2}),
        ("path:dirty", "python_imports", 0, R, {"files": 1, "matches": 2}),
        ("path:bom/b.py", "grep_count", 0, S, {"files": 1, "matches": 0}),              # the mark alone: an empty module
        ("path:bom/b.py", "python_imports", 0, S, {"files": 1, "matches": 0}),
        ("path:bin/x.py", "grep_count", 0, S, {"files": 1, "matches": 0, "skipped_binary": ["bin/x.py"]}),
    )

    def test_the_verdict_is_what_it_always_was_for_every_declaration_and_read(self):
        stim = dict(CLASSES)
        for (locator, cls, matches, want, key), absence, (read, ref) in itertools.product(
                self.CASES, (REQUIRES, DECIDABLE), self.reads):
            s = spec(locator, matches, stim[cls], absence)
            with self.subTest(locator=locator, cls=cls, matches=matches, absence=absence.value, read=read):
                o = P.observe(s, ref, ENV)
                self.assertEqual((o.kind, o.verdict), (K.OBSERVED, want))
                f = base.facts(o)
                self.assertEqual({k: f[k] for k in key}, key)
                self.assertIs(f["present"], True)
                self.assertEqual(run_probe(P, s, ref, ENV).result, Executed(want))

    def test_a_selection_of_binary_files_alone_is_not_what_PM_9_decided(self):
        # decision needed, said in the report: grep_count over a selection whose every file is binary counted nothing
        # either, but a file is selected, so this change leaves it SATISFIED (as python_imports leaves its REFUTED)
        o = P.observe(spec("path:bin", 0, GREP, REQUIRES), self.store, ENV)
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S))
        self.assertEqual(base.facts(o)["skipped_binary"], ["bin/x.py"])
        o = P.observe(spec("path:bin", 0, IMPORTS, REQUIRES), self.store, ENV)
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, R))
        self.assertRegex(base.facts(o)["unparsable"], r"^bin/x\.py:")

    def test_the_classes_with_no_selection_are_not_touched(self):
        for absence, (read, ref) in itertools.product((REQUIRES, DECIDABLE), self.reads):
            with self.subTest(absence=absence.value, read=read):
                for locator in ("path:docs", "path:note/notes.md", "path:pkg/__init__.py"):
                    s = base.spec(locator, {"condition": "exists"}, absence=absence)
                    o = P.observe(s, ref, ENV)
                    self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S))
                s = base.spec("path:docs", {"sha256": "0" * 64}, absence=absence)       # content of a directory: a tree
                o = P.observe(s, ref, ENV)
                self.assertEqual((o.kind, o.verdict, base.facts(o)["kind"]), (K.OBSERVED, R, "tree"))
                s = base.spec("path:vendor", {"condition": "exists"}, absence=absence)  # absent path: unchanged
                self.assertEqual((P.observe(s, ref, ENV).kind, P.observe(s, ref, ENV).verdict), (K.SUBJECT_ABSENT, R))


class GeneratedTrees(unittest.TestCase):
    """The family: random trees of up to four files, and the answer a count written here, with none of the probe's
    code, gives. Selected by suffix as the grammar says; absent exactly when nothing is selected."""

    NAMES = ("a.py", "b.py", "m.pyi", "README.md", "data.json", "sub/c.py", "sub/d.txt", "sub/e.py", "x_py", "t.PY")
    BODIES = (b"", BOM, b"import os\n", b"import telemetry\nx = 1\n", b"# import telemetry\n", b"import requests, yaml\n",
              b"def (:\n", b"\x00\x01", b"caf\xe9\n", b"from . import x\nimport telemetry as t\n", b"line\r\ntelemetry\r\n")
    SUFFIXES = (None, [], [".py"], [".md"], [".py", ".md"], [".json"], [".txt", ".pyi"], [".PY"])

    @staticmethod
    def reference(files: dict, cls: str, stim: dict):
        """(selected files, the count or None when unestablished) — plain Python, written for this test."""
        default = [".py"] if cls == "python_imports" else []
        suffixes = stim.get("suffixes") or default
        chosen = {k: v for k, v in files.items() if not suffixes or any(k.endswith(s) for s in suffixes)}
        total = 0
        for name in sorted(chosen):
            data = chosen[name]
            if cls == "grep_count":
                if b"\0" in data:
                    continue
                try:
                    text = data.decode("utf-8-sig")
                except UnicodeDecodeError:
                    return chosen, None
                total += sum(1 for line in text.splitlines() if re.search(stim["grep"], line))
            else:
                try:
                    tree = ast.parse(data.decode("utf-8-sig"))
                except (UnicodeDecodeError, SyntaxError, ValueError):
                    return chosen, None
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        mods = [a.name for a in node.names]
                    elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                        mods = [node.module]
                    else:
                        continue
                    if {m.split(".")[0] for m in mods} - set(sys.stdlib_module_names):
                        total += 1
        return chosen, total

    def test_absent_exactly_when_nothing_is_selected_and_the_reference_count_otherwise(self):
        rng = random.Random(9)
        seen = {"absent": 0, "counted": 0, "unestablished": 0}
        with tempfile.TemporaryDirectory(prefix="aisef2-pm9-gen-") as d:
            ref = RevisionRef("0" * 40, d)       # one plain tree: each generated directory is a path under it
            for n in range(40):
                root = pathlib.Path(d) / f"t{n}"
                root.mkdir()
                files = {name: rng.choice(self.BODIES) for name in rng.sample(self.NAMES, rng.randint(0, 4))}
                for name, data in files.items():
                    (root / name).parent.mkdir(parents=True, exist_ok=True)
                    (root / name).write_bytes(data)
                for cls, stim in CLASSES:
                    stim = {k: v for k, v in stim.items() if k != "suffixes"}
                    suffixes = rng.choice(self.SUFFIXES)
                    if suffixes is not None:
                        stim["suffixes"] = suffixes
                    chosen, count = self.reference(files, cls, stim)
                    matches = rng.choice((0, 1, 2)) if count is None else rng.choice((count, count, count + 1))
                    for absence in (REQUIRES, DECIDABLE):
                        s = spec(f"path:{root.name}", matches, stim, absence)
                        with self.subTest(tree=n, cls=cls, files=sorted(files), suffixes=suffixes, matches=matches,
                                          absence=absence.value):
                            o = P.observe(s, ref, ENV)
                            if not chosen:
                                want_kind, want = K.SUBJECT_ABSENT, S if matches == 0 else R
                                seen["absent"] += 1
                            elif count is None:
                                want_kind, want = K.OBSERVED, R
                                seen["unestablished"] += 1
                            else:
                                want_kind, want = K.OBSERVED, S if matches == count else R
                                seen["counted"] += 1
                            self.assertEqual((o.kind, o.verdict), (want_kind, want))
                            result = run_probe(P, s, ref, ENV).result
                            self.assertEqual(result, INDETERMINATE if want_kind is K.SUBJECT_ABSENT and absence is REQUIRES
                                             else Executed(want))
        # the family reaches every branch (a family that never hit one would prove nothing about it)
        self.assertTrue(all(v >= 5 for v in seen.values()), seen)


class TheCapabilityMoved(unittest.TestCase):
    """The rule of a class changed what its observations mean, so the capability a spec binds moved with it
    (ARCHITECTURE-EXCEPTION-V2-007: bumped by hand when a verdict rule changes)."""

    def test_the_capability_version_is_three_and_the_digest_names_it(self):
        import hashlib
        import json
        self.assertEqual(fa.CAPABILITY_VERSION, 3)
        self.assertEqual(fa.DIGEST, hashlib.sha256(json.dumps([fa.PROBE_ID, 3, list(fa.CLASSES)]).encode()).hexdigest())
        # a spec compiled against the previous capability is another spec: its id does not carry over
        old = hashlib.sha256(json.dumps([fa.PROBE_ID, 2, list(fa.CLASSES)]).encode()).hexdigest()
        self.assertNotEqual(old, fa.DIGEST)
        a = base.spec("path:docs", {"matches": 0}, GREP, absence=REQUIRES)
        b = base.spec("path:docs", {"matches": 0}, GREP, absence=REQUIRES, probe=mock.Mock(id=fa.PROBE_ID, digest=old))
        self.assertNotEqual(a.id, b.id)


if __name__ == "__main__":
    unittest.main()
