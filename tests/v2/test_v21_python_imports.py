"""V2.1 (B, V21-37): file_artifact's `python_imports` class counts import statements by syntax.

Release smoke #2 rolled back a correct story: the approved LedgerLock criterion BC-V22-S-10-a counted, with a line
regex, the docstring line `    from disk without trusting …` (ledgerlock/ledger.py:261) as an import outside the
allowed set (S6-SMOKE-2-FALSE-ROLLBACK-S10A). Here the real probe, on the LedgerLock reference package: the approved
regex contract reproduces the false refutation; both unapproved drafts (docs/v2.1/drafts/) are SATISFIED on it and
REFUTED by a real import outside the set (positive and negative controls). Offline: the probe reads a directory.

PM-11: a UTF-8 byte-order mark at the start of a file is the encoding's signature, not source text — CPython compiles
and imports such a file, so the count is the one of the same file without it (`ByteOrderMark`; `grep_count` reads the
same way). PM-4: a file the parser names no line for says `?`, never the word None. PM-3: a file the parser stops on
for its own limit is a typed refusal, never an exception and never a verdict (`ParserLimits`)."""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import BehaviorVerdict, Enforcement, MeasurementPoint, ObligationRole, Owner  # noqa: E402
from aisef2.control.owner import FailureCode, Retryability  # noqa: E402
from aisef2.control.routing import route  # noqa: E402
from aisef2.probe import file_artifact as fa  # noqa: E402
from aisef2.probe.protocol import ExecutionEnv, ObservationKind as K, RevisionRef, run_probe  # noqa: E402
from aisef2.product.contract import BehaviorContract  # noqa: E402
from aisef2.product.outcome import Executed, Unrunnable  # noqa: E402
from aisef2.product.spec import ProductProofSpec  # noqa: E402
from tests.v2 import test_c2_file_artifact as base  # noqa: E402   (helpers only: its test classes are not imported)

REFERENCE = ROOT / "tests/v2/fixtures/workloads/ledgerlock-reference/reference/ledgerlock"
APPROVED = next(c for c in json.loads((ROOT / "closure-evidence/v2/release/LEDGERLOCK-PROJECT.json").read_text(
    encoding="utf-8"))["contracts"] if c["id"] == "BC-V22-S-10-a")
DRAFTS = json.loads((ROOT / "docs/v2.1/drafts/LEDGERLOCK-BC-V22-S-10-a-r2.DRAFT.json").read_text(encoding="utf-8"))
SMOKE2_LINE = '\n\ndef _reread(path):\n    """Re-read the ledger\n    from disk without trusting any cached in-memory state."""\n    return path\n'


def observe(contract: dict, package: pathlib.Path) -> BehaviorVerdict | str:
    c = BehaviorContract.from_json(contract)
    spec = ProductProofSpec.create(contract_id=c.id, probe_id=fa.PROBE_ID, probe_digest=fa.DIGEST,
                                   probe_input={"subject": {"kind": c.subject.kind.value, "locator": c.subject.locator},
                                                "stimulus": c.stimulus, "observable": c.observable,
                                                "subject_absence": c.subject_absence.value},
                                   candidate_expectation=BehaviorVerdict.SATISFIED, compiler_id="test", compiler_digest="0" * 64)
    rec = run_probe(fa.FileArtifactProbe(), spec, RevisionRef("0" * 40, str(package.parent)),
                    ExecutionEnv(sys.executable, 30.0, Enforcement.FULL))
    return getattr(rec.result, "behavior_verdict", None) or str(rec.result)


class Controls(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def package(self, extra: str = "") -> pathlib.Path:
        root = pathlib.Path(self._tmp.name) / f"c{len(list(pathlib.Path(self._tmp.name).iterdir()))}"
        shutil.copytree(REFERENCE, root / "ledgerlock", ignore=shutil.ignore_patterns("__pycache__"))
        with open(root / "ledgerlock" / "ledger.py", "a", encoding="utf-8") as f:
            f.write(extra)
        return root / "ledgerlock"

    def test_the_approved_regex_reproduces_the_false_rollback(self):
        self.assertEqual(observe(APPROVED, self.package()), BehaviorVerdict.SATISFIED)
        self.assertEqual(observe(APPROVED, self.package(SMOKE2_LINE)), BehaviorVerdict.REFUTED)   # V21-37

    def test_each_draft_holds_on_the_smoke2_shape_and_refutes_a_real_import(self):
        for name, option in DRAFTS["options"].items():
            with self.subTest(name):
                self.assertEqual(observe(option["contract"], self.package()), BehaviorVerdict.SATISFIED)
                self.assertEqual(observe(option["contract"], self.package(SMOKE2_LINE)), BehaviorVerdict.SATISFIED)
                self.assertEqual(observe(option["contract"], self.package("\nimport yaml\n")), BehaviorVerdict.REFUTED)
                self.assertEqual(observe(option["contract"], self.package("\nfrom requests.adapters import HTTPAdapter\n")),
                                 BehaviorVerdict.REFUTED)
                self.assertEqual(observe(option["contract"], self.package("\n# import yaml\nx = 'import yaml'\n")),
                                 BehaviorVerdict.SATISFIED)

    def test_the_two_drafts_differ_where_the_draft_says(self):
        a, b = (DRAFTS["options"][k]["contract"] for k in ("A_enumerated", "B_stdlib"))
        self.assertEqual(observe(a, self.package("\nimport sqlite3\n")), BehaviorVerdict.REFUTED)     # not in §10's list
        self.assertEqual(observe(b, self.package("\nimport sqlite3\n")), BehaviorVerdict.SATISFIED)   # in the stdlib
        self.assertEqual(observe(a, self.package("\nimport unittest\n")), BehaviorVerdict.REFUTED)    # the noted deviation

    def test_a_file_that_does_not_parse_is_no_count(self):
        for data in (b"def (:\n", b"\xef\xbb\xbfdef (:\n"):     # a BOM neither hides a syntax error nor moves its line
            with self.subTest(data=data):
                facts = fa.import_facts({"stdlib": True, "allowed": []}, [("x.py", data)])
                self.assertNotIn("matches", facts)
                self.assertEqual(facts["unparsable"], "x.py:1")
                self.assertEqual(fa.verdict_of("python_imports", {"matches": 0}, facts), BehaviorVerdict.REFUTED)
        later = fa.import_facts({"stdlib": True, "allowed": []}, [("x.py", b"import os\n\ndef (:\n")])
        self.assertEqual(later["unparsable"], "x.py:3")                 # the parser's own line, not a constant

    def test_a_line_the_parser_does_not_name_is_a_question_mark_never_the_word_none(self):
        # A NUL byte is a ValueError out of ast.parse up to Python 3.11 and a SyntaxError with no line from 3.12; both
        # are driven here on every interpreter, and the real NUL on this one, against what its parser says.
        real = fa.ast.parse
        for name, raised, want in (("SyntaxError, no line", SyntaxError("source code string cannot contain null bytes"),
                                    "x.py:?"),
                                   ("ValueError", ValueError("source code string cannot contain null bytes"), "x.py:?"),
                                   ("SyntaxError at line 0", SyntaxError("x", ("x.py", 0, 1, "t", 0, 1)), "x.py:0"),
                                   ("SyntaxError at line 7", SyntaxError("x", ("x.py", 7, 1, "t", 7, 2)), "x.py:7")):
            with self.subTest(name), mock.patch.object(fa.ast, "parse", side_effect=raised):
                f = fa.import_facts({"stdlib": True, "allowed": []}, [("x.py", b"a = 1\n")])
                self.assertEqual(f, {"present": True, "unparsable": want})
        data = b"import os\nx = '\x00'\n"
        line, parsed = None, False
        try:
            real(data.decode("utf-8"))
            parsed = True               # an interpreter that takes a NUL byte: then there is a count to give
        except (SyntaxError, ValueError) as e:
            line = getattr(e, "lineno", None)
        f = fa.import_facts({"stdlib": True, "allowed": []}, [("x.py", data)])
        if parsed:
            self.assertIn("matches", f)
        else:
            self.assertEqual(f["unparsable"], f"x.py:{'?' if line is None else line}")
            self.assertNotIn("None", f["unparsable"])

    def test_the_grammar_is_closed(self):
        ok = {"imports_outside": {"stdlib": True, "allowed": []}}
        self.assertEqual(fa.observation_class({"matches": 0, "within_s": 5}, ok), "python_imports")
        for bad in ({"imports_outside": {"stdlib": "yes", "allowed": []}}, {"imports_outside": {"allowed": []}},
                    {"imports_outside": {"stdlib": True, "allowed": ["a.b"]}}, {**ok, "grep": "x"},
                    {**ok, "suffixes": ["py"]}):
            with self.subTest(bad=bad):
                self.assertIsNone(fa.observation_class({"matches": 0, "within_s": 5}, bad))
        self.assertIsNone(fa.observation_class({"matches": 0}, ok))      # no window: no meaning


BOM = b"\xef\xbb\xbf"
OUTSIDE = {"stdlib": True, "allowed": []}


class ByteOrderMark(unittest.TestCase):
    """PM-11: a UTF-8 byte-order mark at the start of a file is a signature, not source text. CPython's tokenizer drops
    it, so a file that starts with one compiles and imports; the count is the one of the same file without it. Only a
    *leading* mark is dropped: anywhere else U+FEFF is the syntax error it is for CPython. `content` stays over the
    exact bytes of the blob, the mark included (a fix at the read layer would change what a digest means)."""

    SOURCES = (b"import os\n", b"import requests\n", b"import os\nfrom yaml import x\n", b'"""doc"""\n', b"",
               b"\n\nimport requests\n", b"import requests\r\nx = 1\r\n", b"# \xef\xbb\xbf in a comment\nimport requests\n",
               b"s = '\xef\xbb\xbf'\nimport requests\n", b"def (:\n", b"# caf\xe9\n")
    FILES = {"pkg/stdlib.py": BOM + b"import os\n", "pkg/outside.py": BOM + b"import requests\n"}

    def refs(self) -> dict:
        """The same two files read from a repository's object store and from a plain directory."""
        tmp = tempfile.TemporaryDirectory(prefix="aisef2-pm11-")
        self.addCleanup(tmp.cleanup)
        repo = base.Repo(pathlib.Path(tmp.name) / "repo")
        refs = {"object_store": base.at(repo.path, repo.commit(self.FILES))}
        plain = pathlib.Path(tmp.name) / "plain"
        for rel, data in self.FILES.items():
            (plain / rel).parent.mkdir(parents=True, exist_ok=True)
            (plain / rel).write_bytes(data)
        refs["directory"] = RevisionRef("0" * 40, str(plain))
        return refs

    def test_a_leading_mark_changes_nothing_in_the_facts(self):
        for src in self.SOURCES:
            with self.subTest(src=src):
                self.assertEqual(fa.import_facts(OUTSIDE, [("m.py", BOM + src)]), fa.import_facts(OUTSIDE, [("m.py", src)]))

    def test_the_marked_file_is_counted_not_refuted(self):
        f = fa.import_facts(OUTSIDE, [("m.py", BOM + b"import os\n"), ("n.py", BOM + b"\n\nimport requests\n"), ("e.py", BOM)])
        self.assertNotIn("unparsable", f)
        self.assertEqual((f["files"], f["matches"], f["locations"]), (3, 1, [["n.py", 3, ["requests"]]]))
        only = fa.import_facts(OUTSIDE, [("e.py", BOM)])      # a file of the mark alone: an empty module
        self.assertEqual((only["files"], only["matches"]), (1, 0))

    def test_only_a_leading_mark_is_dropped(self):
        for name, data, where in (("mid-file", b"x = 1\n" + BOM + b"import os\n", "m.py:2"),
                                  ("two marks", BOM + BOM + b"import os\n", "m.py:1"),
                                  ("after a blank line", b"\n" + BOM + b"import os\n", "m.py:2")):
            with self.subTest(name):
                f = fa.import_facts(OUTSIDE, [("m.py", data)])
                self.assertEqual(f["unparsable"], where)
                self.assertNotIn("matches", f)

    def test_the_verdict_is_the_one_cpython_gives_the_same_bytes(self):
        # the oracle is this interpreter's compiler on the bytes, not a table: the probe parses what Python reads
        for name, data in (("plain", b"import os\n"), ("mark", BOM + b"import os\n"), ("mark only", BOM),
                           ("two marks", BOM + BOM + b"import os\n"), ("mid-file", b"x = 1\n" + BOM + b"import os\n"),
                           ("mark and a syntax error", BOM + b"def (:\n"), ("mark in a comment", BOM + b"# \xef\xbb\xbf\n")):
            with self.subTest(name):
                try:
                    compile(data, "m.py", "exec")
                    compiles = True
                except SyntaxError:
                    compiles = False
                self.assertEqual("matches" in fa.import_facts(OUTSIDE, [("m.py", data)]), compiles)

    def test_a_mark_does_not_make_a_file_utf8_that_is_not(self):
        # a UTF-8 mark followed by bytes that are not UTF-8, and a UTF-16 / UTF-32 mark: not UTF-8, so no count — the
        # facts say so, whichever mark came first (the file itself is the answer, never a harness failure)
        cases = {"utf-8 mark, then latin-1": BOM + b"import os\n# caf\xe9\n",
                 "utf-16-le mark": b"\xff\xfe" + "import os\n".encode("utf-16-le"),
                 "utf-16-be mark": b"\xfe\xff" + "import os\n".encode("utf-16-be"),
                 "utf-32-le mark": b"\xff\xfe\x00\x00" + "import os\n".encode("utf-32-le"),
                 "utf-16-le mark, no NUL byte": b"\xff\xfe" + "\u4e2d".encode("utf-16-le")}
        for name, data in cases.items():
            with self.subTest(name):
                self.assertEqual(fa.import_facts(OUTSIDE, [("u.py", data)]), {"present": True, "undecodable": "u.py"})
        for name in ("utf-16-le mark, no NUL byte", "utf-8 mark, then latin-1"):      # the text class says the same
            with self.subTest(grep=name):
                self.assertEqual(fa.grep_facts(re.compile("import"), [("u.py", cases[name])]),
                                 {"present": True, "undecodable": "u.py", "skipped_binary": []})

    def test_each_reader_decides_a_marked_file_by_its_imports(self):
        probe, env, stim = fa.FileArtifactProbe(), base.ENV, {"imports_outside": OUTSIDE}
        for read, ref in self.refs().items():
            for locator, matches, count, verdict in (("path:pkg/stdlib.py", 0, 0, BehaviorVerdict.SATISFIED),
                                                     ("path:pkg/stdlib.py", 1, 0, BehaviorVerdict.REFUTED),
                                                     ("path:pkg/outside.py", 1, 1, BehaviorVerdict.SATISFIED),
                                                     ("path:pkg/outside.py", 0, 1, BehaviorVerdict.REFUTED),
                                                     ("path:pkg", 1, 1, BehaviorVerdict.SATISFIED)):
                with self.subTest(read=read, locator=locator, matches=matches):
                    s = base.spec(locator, {"matches": matches}, stim)
                    o = probe.observe(s, ref, env)
                    f = base.facts(o)
                    self.assertEqual((o.kind, f["read"], o.verdict), (K.OBSERVED, read, verdict))
                    self.assertNotIn("unparsable", f)
                    self.assertEqual(f["matches"], count)
                    self.assertEqual(run_probe(probe, s, ref, env).result, Executed(verdict))

    def test_content_stays_over_the_exact_bytes_the_mark_included(self):
        probe, env = fa.FileArtifactProbe(), base.ENV
        data = self.FILES["pkg/stdlib.py"]
        for read, ref in self.refs().items():
            for digest, verdict in ((hashlib.sha256(data).hexdigest(), BehaviorVerdict.SATISFIED),
                                    (hashlib.sha256(data[len(BOM):]).hexdigest(), BehaviorVerdict.REFUTED)):
                with self.subTest(read=read, verdict=verdict.name):
                    o = probe.observe(base.spec("path:pkg/stdlib.py", {"sha256": digest}), ref, env)
                    self.assertEqual((o.kind, o.verdict), (K.OBSERVED, verdict))

    def test_a_line_anchor_holds_on_the_first_line_of_a_marked_file(self):
        # grep_count reads the mark the same way: `^import requests` is line 1's text, with or without the signature,
        # and the lines keep their numbers; a mark that is not leading is a character of its line
        pattern = re.compile(r"^import requests")
        marked = fa.grep_facts(pattern, [("a.py", BOM + b"import requests\nx = 1\n"), ("b.py", b"import requests\n"),
                                         ("c.py", b"x = 1\nimport requests\n"), ("d.py", b"x = 1\n" + BOM + b"import requests\n")])
        self.assertEqual((marked["matches"], marked["locations"]), (3, [["a.py", 1], ["b.py", 1], ["c.py", 2]]))
        only = fa.grep_facts(re.compile("^$"), [("e.py", BOM)])
        self.assertEqual((only["files"], only["matches"], only["skipped_binary"]), (1, 0, []))
        mid = fa.grep_facts(re.compile("\ufeff"), [("d.py", b"x = 1\n" + BOM + b"y\n")])
        self.assertEqual(mid["locations"], [["d.py", 2]])
        for read, ref in self.refs().items():
            with self.subTest(read=read):
                s = base.spec("path:pkg/outside.py", {"matches": 1}, {"grep": r"^import requests"})
                o = fa.FileArtifactProbe().observe(s, ref, base.ENV)
                self.assertEqual((o.kind, o.verdict, base.facts(o)["matches"]), (K.OBSERVED, BehaviorVerdict.SATISFIED, 1))


LIMITS = {"RecursionError": RecursionError("maximum recursion depth exceeded during compilation"),
          "MemoryError": MemoryError("Parser stack overflowed - Python source too complex to parse")}


class ParserLimits(unittest.TestCase):
    """PM-3: the parser may stop on its own limit (`RecursionError`, `MemoryError`) for a file that is valid Python —
    a long operator chain, an `elif` ladder, nested lambdas. That says nothing about the file: it is a refusal (a typed
    harness failure the file is named in), not an exception out of the probe and not a verdict — no count, no REFUTED,
    no developer charged. A syntax error, a NUL byte and a file that is not UTF-8 stay the file's own answers. Both
    exception types are raised here on every interpreter by making `ast.parse` raise what CPython raises; the real
    sources, the run path and the thresholds measured on the host are in test_v21_fa_parser_limits.py."""

    FILES = {"pkg/a_ok.py": b"import json\n", "pkg/deep.py": b"import os\nx = 1\n", "pkg/z_ok.py": b"import yaml\n"}

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="aisef2-pm3-")
        cls.addClassCleanup(cls._tmp.cleanup)
        root = pathlib.Path(cls._tmp.name)
        repo = base.Repo(root / "repo")
        cls.refs = {"object_store": base.at(repo.path, repo.commit(cls.FILES))}
        plain = root / "plain"
        for rel, data in cls.FILES.items():
            (plain / rel).parent.mkdir(parents=True, exist_ok=True)
            (plain / rel).write_bytes(data)
        cls.refs["directory"] = RevisionRef("0" * 40, str(plain))

    @staticmethod
    def stops_on(name: str, exc: BaseException):
        """`ast.parse` as it is, except that it stops on `exc` for the file named `name`."""
        real = fa.ast.parse

        def parse(source, filename="<unknown>", *a, **k):
            if filename == name:
                raise exc
            return real(source, filename, *a, **k)
        return mock.patch.object(fa.ast, "parse", parse)

    def test_a_limit_is_a_refusal_that_names_the_file_the_limit_and_the_way_out(self):
        for kind, exc in LIMITS.items():
            with self.subTest(limit=kind), self.stops_on("pkg/deep.py", exc):
                with self.assertRaises(fa.Refused) as caught:
                    fa.import_facts(OUTSIDE, [("pkg/a_ok.py", b"import json\n"), ("pkg/deep.py", b"x = 1\n"),
                                              ("pkg/z_ok.py", b"import yaml\n")])
            said = str(caught.exception)
            v = sys.version_info
            for part in ("'pkg/deep.py'", kind, f"python {v.major}.{v.minor}", "not refuted", "changes nothing",
                         "shallower"):
                self.assertIn(part, said)
            self.assertNotIn("pkg/a_ok.py", said)           # it is the file the parser stopped on that is named

    def test_the_probe_answers_unrunnable_on_both_readers_and_gives_no_verdict(self):
        probe, spec = fa.FileArtifactProbe(), base.spec("path:pkg", {"matches": 1}, {"imports_outside": OUTSIDE},
                                                        expectation=BehaviorVerdict.SATISFIED,
                                                        absence=base.REQUIRES)
        for read, ref in self.refs.items():
            for kind, exc in LIMITS.items():
                with self.subTest(read=read, limit=kind), self.stops_on("pkg/deep.py", exc):
                    o = probe.observe(spec, ref, base.ENV)                  # must not raise
                    self.assertEqual((o.kind, o.verdict), (K.HARNESS_FAILED, None))
                    self.assertIn("'pkg/deep.py'", o.detail)
                    self.assertNotIn('"matches"', o.detail)                 # no count was established
                    result = run_probe(probe, spec, ref, base.ENV).result   # must not raise
                    self.assertIsInstance(result, Unrunnable)
                    self.assertEqual(result.detail, o.detail)
                    self.assertFalse(hasattr(result, "behavior_verdict"))   # no verdict of any kind

    def test_the_refusal_routes_to_the_environment_never_to_the_developer(self):
        # PROBE_UNRUNNABLE is the one failure code of a harness that could not look: owner ENVIRONMENT, at every
        # measurement point; the retry it allows is the ENVIRONMENT budget's, bounded by the run's own limit, and never
        # charged to the developer (the budget is the owner's; control/budget.py). It is not INVALID_SPEC: the spec is
        # fine, and no other code of the taxonomy says "this input, this limit: do not run it again".
        spec = base.spec("path:pkg", {"matches": 1}, {"imports_outside": OUTSIDE}, expectation=BehaviorVerdict.SATISFIED,
                         absence=base.REQUIRES)
        ref = self.refs["object_store"]
        with self.stops_on("pkg/deep.py", LIMITS["MemoryError"]):
            result = run_probe(fa.FileArtifactProbe(), spec, ref, base.ENV).result
        for point in (MeasurementPoint.CANDIDATE, MeasurementPoint.POST_MERGE, MeasurementPoint.PARENT):
            for role in (ObligationRole.INTRODUCE, ObligationRole.PRESERVE, ObligationRole.VERIFY):
                with self.subTest(point=point.value, role=role.value):
                    failure = route(result, spec, point, role).failure
                    self.assertEqual((failure.code, failure.owner), (FailureCode.PROBE_UNRUNNABLE, Owner.ENVIRONMENT))
                    self.assertIs(failure.retryability, Retryability.RETRYABLE)
                    self.assertIs(failure.budget, Owner.ENVIRONMENT)
                    self.assertIsNot(failure.owner, Owner.DEVELOPER)

    def test_a_syntax_error_is_still_the_files_own_answer(self):
        # the distinction the owner asked for: what the parser says about the file is REFUTED and named with its line;
        # what stops the parser is not. Real sources for the first, a limit raised for the second, in one tree.
        spec = base.spec("path:pkg", {"matches": 1}, {"imports_outside": OUTSIDE}, expectation=BehaviorVerdict.SATISFIED,
                         absence=base.REQUIRES)
        with tempfile.TemporaryDirectory(prefix="aisef2-pm3-syn-") as d:
            root = pathlib.Path(d)
            for rel, data in {"pkg/a_bad.py": b"import os\n\ndef (:\n", "pkg/z_deep.py": b"x = 1\n"}.items():
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_bytes(data)
            ref = RevisionRef("0" * 40, str(root))
            with self.stops_on("pkg/z_deep.py", LIMITS["RecursionError"]):
                o = fa.FileArtifactProbe().observe(spec, ref, base.ENV)
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, BehaviorVerdict.REFUTED))
        self.assertEqual(base.facts(o)["unparsable"], "pkg/a_bad.py:3")

    def test_the_first_file_in_tree_order_that_gives_no_count_decides(self):
        # as for a file that is not UTF-8: the tree is read in its own order and the first file with no count to give
        # decides, whichever way it gives none (the order is the reader's listing: deterministic for a revision)
        syntax = ("a.py", b"def (:\n")
        deep = ("b.py", b"x = 1\n")
        with self.stops_on("b.py", LIMITS["RecursionError"]):
            self.assertEqual(fa.import_facts(OUTSIDE, [syntax, deep]), {"present": True, "unparsable": "a.py:1"})
            with self.assertRaises(fa.Refused):
                fa.import_facts(OUTSIDE, [deep, syntax])

    def test_only_python_imports_parses_so_only_it_can_hit_a_parser_limit(self):
        for spec in (base.spec("path:pkg", {"matches": 1}, {"grep": "^import json"}, expectation=BehaviorVerdict.SATISFIED),
                     base.spec("path:pkg/a_ok.py"), base.spec("path:pkg/a_ok.py", {"sha256": "0" * 64})):
            for read, ref in self.refs.items():
                with self.subTest(read=read, observable=dict(spec.probe_input["observable"])), \
                        mock.patch.object(fa.ast, "parse", side_effect=RecursionError("never reached")):
                    o = fa.FileArtifactProbe().observe(spec, ref, base.ENV)
                    self.assertIn(o.kind, (K.OBSERVED, K.SUBJECT_ABSENT))
                    self.assertIsNotNone(o.verdict)


if __name__ == "__main__":
    unittest.main()
