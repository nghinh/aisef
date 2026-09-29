"""WP-2.2.1 — the pure functions of `aisef2/probe/cli_invocation.py`: observation classes, shapes, verdicts over
fixture facts, the marker-file parser, placeholder substitution, the evaluation-directory layout. In-process, no
subprocess: the kill set for those mutation targets (validation/v2/mutation.py, phase C2-P2)."""

import hashlib
import json
import os
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import BehaviorVerdict, Enforcement  # noqa: E402
from aisef2.probe import cli_invocation as ci  # noqa: E402
from aisef2.product.spec import ProductProofSpec  # noqa: E402

S, R = BehaviorVerdict.SATISFIED, BehaviorVerdict.REFUTED
ARGV = {"argv": ["verify"]}
W = {"within_s": 5}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def spec(locator="app:__main__", observable=None, stimulus=None, kind="cli_invocation"):
    return ProductProofSpec.create(
        contract_id="BC", probe_id=ci.PROBE_ID, probe_digest=ci.DIGEST,
        probe_input={"subject": {"kind": kind, "locator": locator}, "stimulus": stimulus or ARGV,
                     "observable": observable or {"exit_code": 0, **W}, "subject_absence": "REQUIRES_SUBJECT"},
        candidate_expectation=S, compiler_id="t", compiler_digest="c" * 64)


class Classes(unittest.TestCase):
    def test_every_class_and_every_shape_is_recognised_and_nothing_else(self):
        cases = [
            ({"exit_code": 0, **W}, ARGV, "exits"),
            ({"exit_code": 2, **W}, {}, "exits"),
            ({"exit_code": -1, **W}, {"argv": [], "stdin": None, "workspace": {}, "pre": []}, "exits"),
            ({"blocks": True, **W}, ARGV, "blocks"),
            ({"exit_code": 0, "stdout": "x", **W}, ARGV, "exits_streams"),
            ({"exit_code": 0, "stderr": {"text": "x\n", "newline": "\r\n"}, **W}, ARGV, "exits_streams"),
            ({"exit_code": 0, "stdout": {"text": "x"}, "stderr": {"contains": ["a", "b"]}, **W}, ARGV, "exits_streams"),
            ({"exit_code": 0, "stdout": {"regex": "^a"}, **W}, ARGV, "exits_streams"),
            ({"exit_code": 0, "stdout": {"lines": 0}, **W}, ARGV, "exits_streams"),
            ({"exit_code": 0, "stdout": {"first_word": "verify"}, **W}, ARGV, "exits_streams"),
            ({"exit_code": 0, "files": {"<ws>/a.txt": {"sha256": "0" * 64}}, **W}, ARGV, "exits_files"),
            ({"exit_code": 0, "files": {"<ws>/a/b.txt": {"text": "x", "newline": "\n"}}, **W}, ARGV, "exits_files"),
            ({"exit_code": 0, "files": {"<ws>/a.txt": {"absent": True}, "<ws>/b": {"equals_before": True}}, **W}, ARGV,
             "exits_files"),
            ({"exit_code": 0, **W}, {"argv": ["<ws>/in"], "stdin": {"bytes_hex": "00ff"},
                                     "workspace": {"in": {"text": "a"}, "d/x.bin": {"bytes_hex": ""}},
                                     "pre": [{"argv": ["init"]}, {"argv": []}]}, "exits"),
        ]
        for observable, stimulus, cls in cases:
            with self.subTest(observable=observable, stimulus=stimulus):
                self.assertEqual(ci.observation_class(observable, stimulus), cls)
                self.assertEqual(ci.spec_class(spec("app:__main__", observable, stimulus)), cls)
        rejected = [
            ({"exit_code": 0}, ARGV), ({"exit_code": 0, "within_s": 0}, ARGV), ({"exit_code": 0, "within_s": True}, ARGV),
            ({"exit_code": "0", **W}, ARGV), ({"exit_code": True, **W}, ARGV), ({"exit_code": 1.0, **W}, ARGV),
            ({**W}, ARGV), ({"returns": 0, **W}, ARGV), ({"blocks": 1, **W}, ARGV), ({"blocks": True, "exit_code": 0, **W}, ARGV),
            ({"exit_code": 0, "stdout": 1, **W}, ARGV), ({"exit_code": 0, "stdout": {}, **W}, ARGV),
            ({"exit_code": 0, "stdout": {"prose": "ok"}, **W}, ARGV), ({"exit_code": 0, "stdout": {"contains": []}, **W}, ARGV),
            ({"exit_code": 0, "stdout": {"contains": [1]}, **W}, ARGV), ({"exit_code": 0, "stdout": {"contains": "a"}, **W}, ARGV),
            ({"exit_code": 0, "stdout": {"regex": 1}, **W}, ARGV), ({"exit_code": 0, "stdout": {"lines": -1}, **W}, ARGV),
            ({"exit_code": 0, "stdout": {"lines": True}, **W}, ARGV), ({"exit_code": 0, "stdout": {"first_word": "a b"}, **W}, ARGV),
            ({"exit_code": 0, "stdout": {"first_word": ""}, **W}, ARGV), ({"exit_code": 0, "stdout": {"lines": 1, "regex": "a"}, **W}, ARGV),
            ({"exit_code": 0, "stdout": {"text": "a", "newline": 1}, **W}, ARGV), ({"exit_code": 0, "stdin": "x", **W}, ARGV),
            ({"exit_code": 0, "files": {}, **W}, ARGV), ({"exit_code": 0, "files": [], **W}, ARGV),
            ({"exit_code": 0, "files": {"a.txt": {"absent": True}}, **W}, ARGV),
            ({"exit_code": 0, "files": {"<ws>/../a": {"absent": True}}, **W}, ARGV),
            ({"exit_code": 0, "files": {"<ws>/": {"absent": True}}, **W}, ARGV),
            ({"exit_code": 0, "files": {"<ws>/a": {"absent": False}}, **W}, ARGV),
            ({"exit_code": 0, "files": {"<ws>/a": {"sha256": "0" * 63}}, **W}, ARGV),
            ({"exit_code": 0, "files": {"<ws>/a": {"mode": "0644"}}, **W}, ARGV),
            ({"exit_code": 0, "files": {"<ws>/a": {}}, **W}, ARGV),
            ({"exit_code": 0, "files": {"<ws>/a": "x"}, **W}, ARGV), ({"exit_code": 0, "files": {"<ws>/a": []}, **W}, ARGV),
            ({"exit_code": 0, "files": {"<ws>xa": {"absent": True}}, **W}, ARGV),
            ({"exit_code": 0, "files": {"<ws>/a": {"absent": True, "sha256": "0" * 64}}, **W}, ARGV),
            ({"exit_code": 0, "files": {"<ws>/a": {"absent": True}}, "stdout": "", **W}, ARGV),
            ({"exit_code": 0, **W}, {"args": []}), ({"exit_code": 0, **W}, {"argv": "verify"}), ({"exit_code": 0, **W}, {"argv": [1]}),
            ({"exit_code": 0, **W}, {"argv": [], "stdin": "x"}), ({"exit_code": 0, **W}, {"argv": [], "stdin": {"bytes_hex": "0"}}),
            ({"exit_code": 0, **W}, {"argv": [], "stdin": {"text": 1}}), ({"exit_code": 0, **W}, {"argv": [], "stdin": {"text": "a", "x": 1}}),
            ({"exit_code": 0, **W}, {"argv": [], "workspace": []}), ({"exit_code": 0, **W}, {"argv": [], "workspace": {"../a": {"text": ""}}}),
            ({"exit_code": 0, **W}, {"argv": [], "workspace": {"/a": {"text": ""}}}), ({"exit_code": 0, **W}, {"argv": [], "workspace": {"a": "x"}}),
            ({"exit_code": 0, **W}, {"argv": [], "workspace": {"a b": {"text": ""}}}),
            ({"exit_code": 0, **W}, {"argv": [], "pre": [["a"]]}), ({"exit_code": 0, **W}, {"argv": [], "pre": [{"argv": ["a"], "stdin": None}]}),
            ({"exit_code": 0, **W}, {"argv": [], "pre": {"argv": []}}),
        ]
        for observable, stimulus in rejected:
            with self.subTest(observable=observable, stimulus=stimulus):
                self.assertIsNone(ci.observation_class(observable, stimulus))
        self.assertIsNone(ci.spec_class(spec(kind="python_callable")))
        for locator in ("app", "app/__main__.py:__main__", "app:a.b", "app-cli:main", "1app:main"):
            with self.subTest(locator=locator):
                self.assertIsNone(ci.spec_class(spec(locator)))
        self.assertEqual(ci.spec_class(spec("pkg.sub_mod:__main__")), "exits")
        self.assertEqual(ci.spec_class(spec("mod:main_entry")), "exits")

    def test_the_class_vocabulary_and_the_expired_window_verdicts(self):
        self.assertEqual(ci.CLASSES, ("exits", "exits_streams", "exits_files", "blocks"))
        self.assertEqual(ci.ON_DEADLINE, {"exits": R, "exits_streams": R, "exits_files": R, "blocks": S})
        self.assertEqual(ci.STREAM_SHAPES, ("text", "contains", "regex", "lines", "first_word"))
        self.assertEqual(ci.FILE_SHAPES, ("sha256", "text", "absent", "equals_before"))
        self.assertEqual((ci.PLACEHOLDER, ci.STREAM_CAP), ("<ws>", 8 * 1024 * 1024))
        p = ci.CliInvocationProbe()
        self.assertIs(p.enforcement(), Enforcement.PARTIAL)
        pre = p.harness_preconditions()
        self.assertEqual([line.split(":")[0] for line in pre], ["interpreter", "checkout", "evaluation directory", "protocol"])
        self.assertTrue(all(len(line) > 40 for line in pre))
        self.assertEqual(ci._is_int(3), True)
        self.assertEqual([ci._is_int(x) for x in (True, 3.0, "3", None)], [False] * 4)

    def test_contents_are_byte_exact(self):
        self.assertEqual(ci._bytes_of({"text": "a\nb\n", "newline": "\r\n"}), b"a\r\nb\r\n")
        self.assertEqual(ci._bytes_of({"text": "a\nb"}), b"a\nb")
        self.assertEqual(ci._bytes_of({"bytes_hex": "00FF10"}), b"\x00\xff\x10")
        self.assertEqual(ci._bytes_of({"text": "é"}), "é".encode("utf-8"))
        for ok in ({"text": ""}, {"text": "a", "newline": ""}, {"bytes_hex": ""}, {"bytes_hex": "ab"}):
            self.assertIs(ci._content_ok(ok), True, ok)
        for bad in ("a", {}, {"text": 1}, {"bytes_hex": "a"}, {"bytes_hex": "zz"}, {"text": "a", "bytes_hex": "ab"},
                    {"newline": "\n"}, {"text": "a", "newline": None}, {"text": "a", "newline": 1}, [], None):
            self.assertIs(ci._content_ok(bad), False, bad)
        for name in ("a", "a.txt", "a/b/c.bin", "_x-1"):
            self.assertIs(ci._name_ok(name), True, name)
        for name in ("", "/a", "a/", "../a", "a/../b", "a//b", ".", ".hidden", "a b", "-a", 1):
            self.assertIs(ci._name_ok(name), False, name)
        self.assertIs(ci._ws_key_ok("<ws>/a/b"), True)
        for key in ("<ws>", "<ws>/", "a", "<ws>/../a", "<ws>xa", "<WS>/a", 3):
            self.assertIs(ci._ws_key_ok(key), False, key)
        self.assertEqual(ci._ws_name("<ws>/a/b.txt"), "a/b.txt")
        self.assertIs(ci._argv_ok(["a", ""]), True)
        self.assertIs(ci._argv_ok([]), True)
        for argv in ("a", ["a", 1], None, ("a",)):
            self.assertIs(ci._argv_ok(argv), False, argv)

    def test_the_shape_and_stimulus_checks_answer_exactly_true_or_false(self):
        for stim in ({}, {"argv": []}, {"argv": ["a"], "stdin": None, "workspace": {}, "pre": []},
                     {"pre": [{"argv": ["a"]}, {"argv": []}]}, {"workspace": {"a": {"text": ""}}}, {"stdin": {"bytes_hex": ""}}):
            self.assertIs(ci._stimulus_ok(stim), True, stim)
        for stim in ({"args": []}, {"argv": "a"}, {"stdin": "x"}, {"stdin": {"text": 1}}, {"workspace": []},
                     {"workspace": {"a": "x"}}, {"workspace": {"/a": {"text": ""}}}, {"pre": {"argv": []}},
                     {"pre": [["a"]]}, {"pre": [{"argv": ["a"], "stdin": None}]}, {"pre": [{"argv": [1]}]}, {"pre": "a"}):
            self.assertIs(ci._stimulus_ok(stim), False, stim)
        for shape in ("", "x", {"text": "x"}, {"text": "x", "newline": "\r\n"}, {"contains": ["a"]}, {"regex": ""},
                      {"lines": 0}, {"first_word": "a"}):
            self.assertIs(ci._stream_shape_ok(shape), True, shape)
        for shape in ({}, [], 1, None, ["x"], {"text": 1}, {"contains": []}, {"contains": "a"}, {"regex": 1},
                      {"lines": -1}, {"lines": "1"}, {"first_word": ""}, {"first_word": "a b"}, {"first_word": 1},
                      {"prose": "x"}, {"lines": 1, "regex": "a"}, {"first_word": "a", "x": 1}):
            self.assertIs(ci._stream_shape_ok(shape), False, shape)
        for shape in ({"sha256": "0" * 64}, {"text": ""}, {"text": "a", "newline": ""}, {"absent": True}, {"equals_before": True}):
            self.assertIs(ci._file_shape_ok(shape), True, shape)
        for shape in ({}, "x", "", [], None, {"text": 1}, {"sha256": "0" * 63}, {"sha256": 1}, {"absent": False},
                      {"absent": 1}, {"equals_before": None}, {"mode": "0644"}, {"absent": True, "sha256": "0" * 64}):
            self.assertIs(ci._file_shape_ok(shape), False, shape)


class Verdicts(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory(prefix="aisef2-cli-facts-")
        self.addCleanup(self._d.cleanup)
        self.dir = pathlib.Path(self._d.name)

    def stream(self, data: bytes, *, name="out", size=None, truncated=False) -> dict:
        path = self.dir / name
        path.write_bytes(data)
        return {"path": str(path), "size": len(data) if size is None else size, "sha256": sha(data), "truncated": truncated}

    def facts(self, code=0, out=b"", err=b"", **more) -> dict:
        return {"subject": "present", "exit_code": code, "exit_status_raw": code, "raised": None,
                "stdout": self.stream(out, name="out"), "stderr": self.stream(err, name="err"), "pre": [], **more}

    def test_exits_compares_the_exit_code_and_nothing_else(self):
        self.assertIs(ci.verdict_of("exits", {"exit_code": 0}, self.facts(0, b"anything", b"x")), S)
        self.assertIs(ci.verdict_of("exits", {"exit_code": 2}, self.facts(2)), S)
        self.assertIs(ci.verdict_of("exits", {"exit_code": 2}, self.facts(3)), R)
        self.assertIs(ci.verdict_of("exits", {"exit_code": 0}, {"subject": "present", "exit_code": 0, "hard_exit": True}), S)
        self.assertIs(ci.verdict_of("exits", {"exit_code": 0}, {"subject": "present"}), R)   # no code at all

    def test_a_failed_pre_step_refutes_every_class_and_blocks_refutes_any_return(self):
        failed = {"subject": "present", "pre_failed": 1, "pre": [{"exit_code": 0}, {"exit_code": 2}]}
        for cls, observable in (("exits", {"exit_code": 0}), ("exits_streams", {"exit_code": 0, "stdout": ""}),
                                ("exits_files", {"exit_code": 0, "files": {"<ws>/a": {"absent": True}}}),
                                ("blocks", {"blocks": True})):
            with self.subTest(cls=cls):
                self.assertIs(ci.verdict_of(cls, observable, failed), R)
        self.assertIs(ci.verdict_of("blocks", {"blocks": True}, self.facts(0)), R)
        self.assertIs(ci.verdict_of("blocks", {"blocks": True}, self.facts(1)), R)
        self.assertIs(ci.verdict_of("exits", {"exit_code": 0}, {"subject": "present", "pre_failed": 0}), R)
        # a hard exit inside a pre-step carries the process's exit code, and the failed pre-step still decides
        hard_in_pre = {"subject": "present", "pre_failed": 0, "exit_code": 3, "hard_exit": True}
        self.assertIs(ci.verdict_of("exits", {"exit_code": 3}, hard_in_pre), R)
        self.assertIs(ci.verdict_of("exits", {"exit_code": 3}, {"subject": "present", "exit_code": 3, "hard_exit": True}), S)

    def test_stream_shapes_over_captured_bytes(self):
        f = self.facts(0, b"verify ok\r\nsecond\r\n", b"warn: x\n")
        cases = [
            ({"stdout": {"text": "verify ok\nsecond\n", "newline": "\r\n"}}, S),
            ({"stdout": {"text": "verify ok\nsecond\n"}}, R),
            ({"stdout": "verify ok\r\nsecond\r\n"}, S), ({"stdout": "verify ok\r\nsecond"}, R),
            ({"stdout": {"contains": ["verify", "second"]}}, S), ({"stdout": {"contains": ["verify", "third"]}}, R),
            ({"stdout": {"regex": r"^verify .*\bok\b"}}, S), ({"stdout": {"regex": r"^second"}}, R),
            ({"stdout": {"regex": r"(?m)^second"}}, S),
            ({"stdout": {"lines": 2}}, S), ({"stdout": {"lines": 1}}, R), ({"stderr": {"lines": 1}}, S),
            ({"stdout": {"first_word": "verify"}}, S), ({"stdout": {"first_word": "ok"}}, R),
            ({"stderr": {"first_word": "warn:"}}, S), ({"stderr": "warn: x\n"}, S), ({"stderr": ""}, R),
            ({"stdout": {"first_word": "verify"}, "stderr": {"contains": ["warn"]}}, S),
            ({"stdout": {"first_word": "verify"}, "stderr": {"contains": ["nope"]}}, R),
        ]
        for extra, verdict in cases:
            with self.subTest(observable=extra):
                self.assertIs(ci.verdict_of("exits_streams", {"exit_code": 0, **extra}, f), verdict)
                self.assertIs(ci.verdict_of("exits_streams", {"exit_code": 1, **extra}, f), R)   # the code counts too
        raw = self.facts(0, b"\xff\xfe abc\n", b"\xff")   # bytes that are not UTF-8: decoded with replacement, never an error
        self.assertIs(ci.verdict_of("exits_streams", {"exit_code": 0, "stdout": {"regex": "abc"}}, raw), S)
        self.assertIs(ci.verdict_of("exits_streams", {"exit_code": 0, "stdout": {"first_word": "��"}}, raw), S)
        self.assertIs(ci.verdict_of("exits_streams", {"exit_code": 0, "stderr": {"first_word": "x"}}, raw), R)
        self.assertIs(ci.verdict_of("exits_streams", {"exit_code": 0, "stderr": {"regex": "^�$"}}, raw), S)
        empty = self.facts(0, b"", b"")
        self.assertIs(ci.verdict_of("exits_streams", {"exit_code": 0, "stdout": "", "stderr": ""}, empty), S)
        self.assertIs(ci.verdict_of("exits_streams", {"exit_code": 0, "stdout": {"lines": 0}}, empty), S)
        self.assertIs(ci.verdict_of("exits_streams", {"exit_code": 0, "stdout": {"first_word": "a"}}, empty), R)
        self.assertIs(ci.verdict_of("exits_streams", {"exit_code": 0, "stdout": {"contains": [""]}}, empty), S)

    def test_a_stream_fact_names_a_prefix_a_truncation_or_no_file(self):
        f = self.facts(0, b"earlylate")
        f["stdout"]["size"] = 5   # the bytes captured when the invocation returned
        self.assertIs(ci.verdict_of("exits_streams", {"exit_code": 0, "stdout": "early"}, f), S)
        self.assertIs(ci.verdict_of("exits_streams", {"exit_code": 0, "stdout": "earlylate"}, f), R)
        flood = self.facts(0, b"x" * 16)
        flood["stdout"]["truncated"] = True
        self.assertIs(ci.verdict_of("exits_streams", {"exit_code": 0, "stdout": "x" * 16}, flood), R)
        self.assertIs(ci.verdict_of("exits_streams", {"exit_code": 0, "stdout": {"contains": ["xx"]}}, flood), S)
        gone = self.facts(0)
        gone["stdout"]["path"] = str(self.dir / "missing")
        self.assertIs(ci.verdict_of("exits_streams", {"exit_code": 0, "stdout": ""}, gone), S)
        self.assertIs(ci.verdict_of("exits_streams", {"exit_code": 0, "stdout": "a"}, gone), R)
        self.assertEqual(ci._stream_bytes({}), b"")
        prefix = self.stream(b"earlylate", name="prefix")
        self.assertEqual(ci._stream_bytes({"path": prefix["path"], "size": 3}), b"ear")
        self.assertEqual(ci._stream_bytes({"path": prefix["path"], "size": 99}), b"earlylate")

    def test_file_shapes_over_digests_before_and_after(self):
        present, other, absent = {"sha256": sha(b"data\n")}, {"sha256": sha(b"date\n")}, {"absent": True}
        f = self.facts(0, before={"kept": present, "made": absent, "gone": present, "changed": present},
                       files={"kept": present, "made": present, "gone": absent, "changed": other})
        cases = [
            ({"<ws>/made": {"sha256": sha(b"data\n")}}, S), ({"<ws>/made": {"sha256": sha(b"date\n")}}, R),
            ({"<ws>/made": {"text": "data\n", "newline": "\n"}}, S), ({"<ws>/made": {"text": "data\r\n"}}, R),
            ({"<ws>/made": {"text": "data\n", "newline": "\r\n"}}, R),
            ({"<ws>/gone": {"absent": True}}, S), ({"<ws>/made": {"absent": True}}, R),
            ({"<ws>/kept": {"equals_before": True}}, S), ({"<ws>/changed": {"equals_before": True}}, R),
            ({"<ws>/gone": {"equals_before": True}}, R), ({"<ws>/made": {"equals_before": True}}, R),
            ({"<ws>/never": {"absent": True}}, R), ({"<ws>/never": {"equals_before": True}}, R),
            ({"<ws>/kept": {"equals_before": True}, "<ws>/made": {"sha256": sha(b"data\n")}, "<ws>/gone": {"absent": True}}, S),
            ({"<ws>/kept": {"equals_before": True}, "<ws>/gone": {"sha256": sha(b"data\n")}}, R),
        ]
        for files, verdict in cases:
            with self.subTest(files=files):
                self.assertIs(ci.verdict_of("exits_files", {"exit_code": 0, "files": files}, f), verdict)
                self.assertIs(ci.verdict_of("exits_files", {"exit_code": 1, "files": files}, f), R)
        both_absent = self.facts(0, before={"x": absent}, files={"x": absent})
        self.assertIs(ci.verdict_of("exits_files", {"exit_code": 0, "files": {"<ws>/x": {"equals_before": True}}}, both_absent), S)
        no_before = self.facts(0, files={"x": present})   # a hard exit before MAIN: nothing recorded before
        self.assertIs(ci.verdict_of("exits_files", {"exit_code": 0, "files": {"<ws>/x": {"equals_before": True}}}, no_before), R)
        self.assertIs(ci.verdict_of("exits_files", {"exit_code": 0, "files": {"<ws>/x": {"sha256": sha(b"data\n")}}}, no_before), S)

    def test_facts_are_read_from_files_by_the_same_rules_the_child_uses(self):
        path = self.dir / "cap"
        path.write_bytes(b"y" * (ci.STREAM_CAP + 10))
        fact = ci._stream_fact(str(path))
        self.assertEqual((fact["size"], fact["truncated"], fact["sha256"]), (ci.STREAM_CAP, True, sha(b"y" * ci.STREAM_CAP)))
        small = self.dir / "small"
        small.write_bytes(b"abc")
        self.assertEqual(ci._stream_fact(str(small)), {"path": str(small), "size": 3, "truncated": False, "sha256": sha(b"abc")})
        self.assertEqual(ci._stream_fact(str(self.dir / "none")), {"path": str(self.dir / "none"), "size": 0, "truncated": False,
                                                                   "sha256": sha(b"")})
        self.assertEqual(ci._file_fact(str(small)), {"sha256": sha(b"abc")})
        self.assertEqual(ci._file_fact(str(self.dir / "none")), {"absent": True})
        self.assertEqual(ci._file_fact(str(self.dir)), {"absent": True})   # a directory is not a file
        self.assertEqual(ci._sha_file(str(small), 2), sha(b"ab"))
        self.assertEqual(ci._sha_file(str(small)), sha(b"abc"))


class Protocol(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory(prefix="aisef2-cli-proto-")
        self.addCleanup(self._d.cleanup)
        self.path = os.path.join(self._d.name, "protocol.log")

    def lines(self, text: str) -> dict:
        pathlib.Path(self.path).write_bytes(text.encode("utf-8"))
        return ci._protocol(self.path, "n0nce")

    def test_complete_lines_with_the_mark_and_this_nonce_only(self):
        text = ("AISEF2-PROBE READY n0nce\nnoise\nAISEF2-PROBE DISPATCHED n0nce \nAISEF2-PROBE PRE n0nce 0\n"
                "AISEF2-PROBE READY other\nOTHER RESULT n0nce {}\nAISEF2-PROBE MAIN n0nce {\"before\": {}}\r\n"
                'AISEF2-PROBE RESULT n0nce {"subject": "present", "exit_code": 0}\n')
        self.assertEqual(self.lines(text), {"READY": [""], "DISPATCHED": [""], "PRE": ["0"], "MAIN": ['{"before": {}}'],
                                            "RESULT": ['{"subject": "present", "exit_code": 0}']})
        self.assertEqual(self.lines(text + "AISEF2-PROBE END n0nce"), {**self.lines(text)})   # unterminated: not a line
        self.assertEqual(self.lines(text[:-1]).get("RESULT"), None)
        self.assertEqual(self.lines(""), {})
        self.assertEqual(ci._protocol(os.path.join(self._d.name, "absent"), "n0nce"), {})
        self.assertEqual(self.lines("AISEF2-PROBE PRE n0nce 0\nAISEF2-PROBE PRE n0nce 1\n"), {"PRE": ["0", "1"]})
        self.assertEqual(self.lines("AISEF2-PROBE\nAISEF2-PROBE READY\n"), {})
        self.assertEqual(self.lines("AISEF2-PROBE READY n0nce\xff\n"), {})
        # bytes that are not UTF-8 in the file: decoded with replacement, never an error, never a protocol line
        pathlib.Path(self.path).write_bytes(b"\xff\xfe junk\nAISEF2-PROBE READY n0nce\nAISEF2-PROBE PRE n0nce \xff\n")
        self.assertEqual(ci._protocol(self.path, "n0nce"), {"READY": [""], "PRE": ["�"]})

    def test_the_placeholder_is_substituted_at_the_head_of_an_entry_only(self):
        ws = os.path.join(self._d.name, "ws")
        self.assertEqual(ci._substitute(["<ws>", "<ws>/a", "<ws>/a/b.txt", "x<ws>/a", "<ws>x", "<w>", "plain"], ws),
                         [ws, os.path.join(ws, "a"), os.path.join(ws, "a", "b.txt"), "x<ws>/a", "<ws>x", "<w>", "plain"])
        self.assertEqual(ci._substitute([], ws), [])

    def test_public_facts_carry_no_capture_path(self):
        facts = {"stdout": {"path": "/x", "size": 1}, "stderr": {"path": "/y", "size": 0}, "exit_code": 0,
                 "pre": [{"stdout": {"path": "/p", "size": 2}, "exit_code": 0}, 3], "files": {"a": {"sha256": "0"}},
                 "before": {"a": {"absent": True}}}
        self.assertEqual(ci._public(facts), {"stdout": {"size": 1}, "stderr": {"size": 0}, "exit_code": 0,
                                             "pre": [{"stdout": {"size": 2}, "exit_code": 0}, 3],
                                             "files": {"a": {"sha256": "0"}}, "before": {"a": {"absent": True}}})
        self.assertNotIn("path", json.dumps(ci._public(facts)))

    def test_the_child_environment_is_scrubbed_and_pinned(self):
        e = ci._child_env("/tmp/ws")
        self.assertEqual((e["LC_ALL"], e["LANG"], e["PYTHONUTF8"], e["TZ"], e["HOME"], e["USERPROFILE"]),
                         ("C.UTF-8", "C.UTF-8", "1", "UTC", "/tmp/ws", "/tmp/ws"))
        self.assertEqual((e["PYTHONHASHSEED"], e["PYTHONDONTWRITEBYTECODE"], e["PYTHONIOENCODING"]), ("0", "1", "utf-8"))
        self.assertNotIn("PATH", e)
        self.assertNotIn("PYTHONPATH", e)

    def test_the_harness_command_line_pins_every_control(self):
        argv = ci._harness_argv("/py", "/w/request.json", "/w/pycache")
        self.assertEqual(argv, ["/py", "-I", "-B", "-X", "pycache_prefix=/w/pycache", "-X", "utf8=1", "-c", ci.HARNESS,
                                "/w/request.json"])

    def test_the_evaluation_directory_is_laid_out_byte_exactly(self):
        work = self._d.name
        stim = {"argv": ["run", "<ws>/in.txt", "<ws>"], "stdin": {"text": "a\nb", "newline": "\r\n"},
                "workspace": {"in.txt": {"text": "x\ny\n", "newline": "\r\n"}, "d/raw.bin": {"bytes_hex": "00ff"},
                              "a/b/c.bin": {"bytes_hex": "01"}, "a/b/d.bin": {"bytes_hex": "02"}},
                "pre": [{"argv": ["init", "<ws>/in.txt"]}]}
        ask, ws, pycache = ci._prepare(work, "/rev", "app:__main__", stim, ["in.txt", "out.txt"], "n0nce")
        self.assertEqual((ws, pycache, ask), (os.path.join(work, "ws"), os.path.join(work, "pycache"), os.path.join(work, "request.json")))
        self.assertEqual(os.listdir(pycache), [])
        self.assertEqual(pathlib.Path(ws, "in.txt").read_bytes(), b"x\r\ny\r\n")
        self.assertEqual(pathlib.Path(ws, "d", "raw.bin").read_bytes(), b"\x00\xff")
        self.assertEqual(pathlib.Path(ws, "a", "b", "c.bin").read_bytes() + pathlib.Path(ws, "a", "b", "d.bin").read_bytes(),
                         b"\x01\x02")   # nested directories are created as needed, an existing one is reused
        self.assertEqual(pathlib.Path(work, "stdin.bin").read_bytes(), b"a\r\nb")
        req = json.loads(pathlib.Path(ask).read_text(encoding="utf-8"))
        self.assertEqual(req["argv"], ["run", os.path.join(ws, "in.txt"), ws])
        self.assertEqual(req["pre"], [{"argv": ["init", os.path.join(ws, "in.txt")]}])
        self.assertEqual((req["mark"], req["nonce"], req["root"], req["locator"], req["work"], req["ws"]),
                         ("AISEF2-PROBE", "n0nce", "/rev", "app:__main__", work, ws))
        self.assertEqual((req["protocol"], req["cap"], req["stdin"], req["files"]),
                         (os.path.join(work, "protocol.log"), ci.STREAM_CAP, os.path.join(work, "stdin.bin"), ["in.txt", "out.txt"]))
        bare = tempfile.mkdtemp(prefix="aisef2-cli-bare-", dir=self._d.name)
        ask2, ws2, _ = ci._prepare(bare, "/rev", "app:__main__", {}, [], "n1")
        req2 = json.loads(pathlib.Path(ask2).read_text(encoding="utf-8"))
        self.assertEqual((req2["argv"], req2["pre"], req2["stdin"], req2["files"], os.listdir(ws2)), ([], [], None, [], []))
        self.assertFalse(os.path.exists(os.path.join(bare, "stdin.bin")))


if __name__ == "__main__":
    unittest.main()
