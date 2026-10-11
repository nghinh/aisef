"""validation/qualification/v21_snapshot_delta.py on a toy repository: each kind of change after the snapshot gets its
targets and the reuse proof's verdict, data inside mutation.COPY is read, not read or not measured, and --check refuses
a table that is stale. Every rule of the tool has a case here that fails when the rule is taken out (the COVERED kinds
of --check hold no copy_data or copy_unread: --check builds without a read-set, where neither occurs without
copy_unmeasured, so adding them changes nothing --check can see)."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from validation.qualification import v21_snapshot_delta as D  # noqa: E402


COPY = ('aisef2', 'tests/v2', 'validation/v2', 'docs', 'pyproject.toml')


def _toy_mutation(targets: dict[str, list[str]], copy: tuple[str, ...] = COPY) -> str:
    """A toy validation/v2/mutation.py: the real generator, null mutant and enum lookup, with its own targets."""
    src = (ROOT / "validation/v2/mutation.py").read_text(encoding="utf-8")
    keep = {"_SWAP", "_inert", "_script", "_root", "mutants", "_enum_members", "null_mutant"}
    segs = [ast.get_source_segment(src, n) for n in ast.parse(src).body
            if getattr(n, "name", None) in keep or (isinstance(n, ast.Assign) and getattr(n.targets[0], "id", None) in keep)]
    return ("from __future__ import annotations\n\nimport ast\nimport copy\nimport pathlib\n\n" + "\n\n\n".join(segs)
            + f"\n\n\nCOPY = {copy!r}\nV21_TARGETS = {targets!r}\n")


TARGETS = {"aisef2/m.py::f": ["tests/v2/test_m.py"], "aisef2/m.py::g": ["tests/v2/test_m.py"],
           "aisef2/n.py::h": ["tests/v2/test_n.py"]}
M, N = "tests/v2/test_m.py", "tests/v2/test_n.py"
FILES = {
    "aisef2/__init__.py": "", "aisef2/m.py": "def f(x):\n    return x == 1\n\n\ndef g(x):\n    return x > 2\n",
    "aisef2/n.py": "def h(x):\n    return not x\n",
    "tests/__init__.py": "", "tests/v2/__init__.py": "", "tests/v2/helper.py": "VALUE = 1\n",
    "tests/v2/test_m.py": "from tests.v2 import helper\nDATA = 'docs/data.json'\n", "tests/v2/test_n.py": "X = 1\n",
    "docs/data.json": "{}\n", "docs/notes.md": "notes\n", "evidence/notes.md": "notes\n", "pyproject.toml": "[x]\n",
    "validation/__init__.py": "", "validation/v2/__init__.py": "", "validation/v2/mutation.py": _toy_mutation(TARGETS),
    "validation/v2/cleanup_authority.py": "X = 1\n", "validation/v2/owned_run.py": "X = 1\n",
    "validation/v2/execution_order.py": "from validation.v2 import mutation\n",
}
SAME = "same inputs (generator source, module source, enum members)"
MAY_READ = "data its kill tests may read (found statically; outside the proof's rules)"


def ran(kill_file: str, opened: tuple[str, ...] | list[str] = (), listed: tuple[str, ...] | list[str] = (),
        by: dict[str, list[str]] | None = None) -> dict:
    """A kill file's entry in a measured read-set: its own import opens it. `by`: listed_by (absent in an old record)."""
    return {"opened": [kill_file, *opened], "listed": [*listed], **({"listed_by": by} if by is not None else {})}


REG = "aisef2/invariants/registry.py"
SUB, NEW, FX = "tests/v2/sub", "tests/v2/new", "tests/v2/fx"
#: what registry.py has of the real one that matters: test_directories lists tests/v2 and keeps the set of parents of
#: the test modules; _arms walks a syntax tree (not a listing)
REG_SRC = """import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
TESTS_V2 = "tests/v2"


def test_directories(root=ROOT):
    base = root / TESTS_V2
    out = {TESTS_V2} if any(base.glob("test_*.py")) else set()
    for path in base.rglob("test_*.py"):
        out.add(path.parent.relative_to(root).as_posix())
    return frozenset(out)


def _arms(src):
    return [n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Call)]
"""
DIRS = ("tests/v2", SUB, NEW, FX)


def _git(repo: pathlib.Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@x"}
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8", check=True,
                          env=env).stdout.strip()


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class Toy(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.init({})

    def init(self, extra: dict[str, str]) -> None:
        """A fresh repository whose snapshot (self.base) is FILES with `extra` on top."""
        self.repo = pathlib.Path(tempfile.mkdtemp(dir=self._tmp.name)) / "repo"
        self.edit({**FILES, **extra})
        _git(self.repo, "init", "-q")
        self.base = self.commit("snapshot")

    def edit(self, files: dict[str, str]) -> None:
        for rel, text in files.items():
            (self.repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / rel).write_text(text, encoding="utf-8")

    def commit(self, msg: str) -> str:
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-qm", msg)
        return _git(self.repo, "rev-parse", "HEAD")

    def delta(self, files: dict[str, str], read_set: dict | None = None) -> dict:
        self.edit(files)
        head = self.commit("change")
        rs = None
        if read_set is not None:
            rs = self.repo / "readset.json"           # never committed: not a change of the delta
            rs.write_text(json.dumps({"commit": head, **read_set}), encoding="utf-8")
        doc, _ = D.build(self.repo, self.base, head, rs)
        self.assertEqual(len(doc["files"]), 1, doc["files"])
        return doc

    def verdicts(self, doc: dict) -> dict[str, str]:
        return {t: v["verdict"] for t, v in doc["targets"].items()}

    def stand(self) -> str:
        return f"a {self.base[:7]} result can stand at head"

    def provisional(self, n: int = 1) -> str:
        return (f"inside mutation.COPY, read-set not measured: {n} changed file(s) — the {self.base[:7]} result stands "
                f"only PROVISIONALLY until a measured read-set (an audit-hook run of its kill files: --read-set) clears them")

    # -- the proof's rules ------------------------------------------------------------------------------------------

    def test_a_product_change_re_measures_every_target_of_its_module_and_no_other(self):
        doc = self.delta({"aisef2/n.py": "def h(x):\n    return x\n"})
        row = doc["files"][0]
        self.assertEqual((row["kinds"], list(row["targets"]), row["remeasure"], row["names_changed"]),
                         (["product", D.UNMEASURED], ["aisef2/n.py::h"], ["aisef2/n.py::h"], ["h"]))
        self.assertEqual(row["read_set"]["provisional_except"], ["aisef2/n.py::h"])   # its own module: the proof decides
        self.assertEqual(self.verdicts(doc), {"aisef2/m.py::f": self.stand(), "aisef2/m.py::g": self.stand(),
                                              "aisef2/n.py::h": "re-measure: the target file changed since it was measured"})
        self.assertEqual(doc["records"][0]["reasons"], [
            {"why": "1 target module(s) changed: mutant counts and nulls re-derived", "targets": ["aisef2/n.py::h"],
             "files": ["aisef2/n.py"]}])
        self.assertEqual((doc["records"][0]["record"], doc["records"][0]["note"]),
                         (None, f"no closure-evidence/v2/v2.1/REQUALIFICATION-MANIFEST*.json at head has snapshot {self.base[:12]}"))

    def test_a_kill_set_change_in_mutation_py_re_measures_that_target(self):
        doc = self.delta({"validation/v2/mutation.py": _toy_mutation({**TARGETS, "aisef2/m.py::f": [M, N]})})
        self.assertEqual(doc["files"][0]["kinds"], ["harness"])
        self.assertEqual(self.verdicts(doc), {"aisef2/m.py::f": "re-measure: its kill set is not the current one",
                                              "aisef2/m.py::g": self.stand(), "aisef2/n.py::h": self.stand()})
        self.assertEqual(doc["files"][0]["names_changed"], ["V21_TARGETS"])
        self.init({})                                     # h's kill file at base only: its closure is still looked into
        self.edit({"validation/v2/mutation.py": _toy_mutation({**TARGETS, "aisef2/n.py::h": [M]}), N: "X = 2\n"})
        doc, _ = D.build(self.repo, self.base, self.commit("kill set"))
        rows = {r["path"]: r for r in doc["files"]}
        self.assertEqual((rows[N]["kinds"], rows[N]["targets"]),     # at head N is data inside COPY to M
                         (["kill_file", D.UNMEASURED], {"aisef2/n.py::h": ["removed from its kill set"]}))
        self.assertEqual(doc["targets"]["aisef2/n.py::h"]["verdict"],
                         "re-measure: its kill set is not the current one; kill tests changed: tests/v2/test_n.py")

    def test_targets_added_or_removed_in_mutation_py(self):
        doc = self.delta({"validation/v2/mutation.py": _toy_mutation(
            {"aisef2/m.py::f": [M], "aisef2/n.py::h": [N], "aisef2/n.py::h2": [N]})})
        b7 = self.base[:7]
        self.assertEqual(self.verdicts(doc), {
            "aisef2/m.py::f": self.stand(), "aisef2/m.py::g": "not a V2.1 target at head: nothing to re-measure",
            "aisef2/n.py::h": self.stand(), "aisef2/n.py::h2": f"re-measure: not a V2.1 target at {b7}, so no result of it exists"})
        self.assertEqual((doc["counts"]["not_at_head"], doc["counts"]["remeasure"], doc["counts"]["stand"]), (1, 1, 2))
        self.assertEqual(doc["records"][0]["reasons"], [
            {"why": "1 target(s) added", "targets": ["aisef2/n.py::h2"], "files": ["validation/v2/mutation.py"]},
            {"why": "1 target(s) removed", "targets": ["aisef2/m.py::g"], "files": ["validation/v2/mutation.py"]}])

    def test_a_generator_change_re_measures_the_targets_whose_mutants_differ(self):
        swap = "ast.Eq: ast.NotEq, "
        src = _toy_mutation(TARGETS)
        self.assertEqual(src.count(swap), 1)
        doc = self.delta({"validation/v2/mutation.py": src.replace(swap, "")})   # f (x == 1) loses its Eq swap
        self.assertEqual(self.verdicts(doc), {"aisef2/m.py::f": "re-measure: its mutants are not the current generator's",
                                              "aisef2/m.py::g": self.stand(), "aisef2/n.py::h": self.stand()})
        self.assertEqual((doc["targets"]["aisef2/m.py::g"]["generator"], doc["targets"]["aisef2/n.py::h"]["generator"]),
                         ("run at both: 2 and 2 mutants", "run at both: 2 and 2 mutants"))
        self.assertEqual(doc["files"][0]["names_changed"], ["_SWAP"])

    def test_a_generator_change_that_yields_the_same_mutants_lets_every_result_stand(self):
        old, new = "inert = [doc] if doc is not None else []", "inert = [] if doc is None else [doc]"
        src = _toy_mutation(TARGETS)
        self.assertEqual(src.count(old), 1)
        doc = self.delta({"validation/v2/mutation.py": src.replace(old, new)})
        self.assertEqual(set(self.verdicts(doc).values()), {self.stand()})
        self.assertEqual({t: v["generator"] for t, v in doc["targets"].items()},
                         {"aisef2/m.py::f": "run at both: 2 and 2 mutants", "aisef2/m.py::g": "run at both: 2 and 2 mutants",
                          "aisef2/n.py::h": "run at both: 2 and 2 mutants"})

    def test_an_imported_enum_change_reaches_the_importers_and_re_measures_where_mutants_differ(self):
        self.init({"aisef2/e.py": "from enum import Enum\n\n\nclass Color(Enum):\n    RED = 1\n    BLUE = 2\n",
                   "aisef2/m.py": "from aisef2.e import Color\n\n\ndef f(x):\n    return x is Color.RED\n\n\n"
                                  "def g(x):\n    return x > 2\n"})
        doc = self.delta({"aisef2/e.py": "from enum import Enum\n\n\nclass Color(Enum):\n    RED = 1\n    BLUE = 2\n"
                                         "    GREEN = 3\n"})
        row = doc["files"][0]
        imports = "its module imports this file (enum members: generator input)"
        self.assertEqual((row["kinds"], row["targets"]), (["product", D.UNMEASURED],
                                                          {"aisef2/m.py::f": [imports], "aisef2/m.py::g": [imports]}))
        self.assertEqual(self.verdicts(doc), {"aisef2/m.py::f": "re-measure: its mutants are not the current generator's",
                                              "aisef2/m.py::g": self.stand(), "aisef2/n.py::h": self.stand()})
        self.assertEqual(doc["targets"]["aisef2/m.py::g"]["generator"], "run at both: 2 and 2 mutants")
        self.assertEqual(doc["targets"]["aisef2/n.py::h"]["generator"], SAME)

    def test_a_module_importing_the_file_at_either_commit_is_reached(self):
        enum = "from enum import Enum\n\n\nclass Color(Enum):\n    RED = 1\n"
        uses = "from aisef2.e import Color\n\n\ndef f(x):\n    return x is Color.RED\n\n\ndef g(x):\n    return x > 2\n"
        imports = "its module imports this file (enum members: generator input)"
        for name, at_base, at_head in (("imported at base only", uses, FILES["aisef2/m.py"]),
                                       ("imported at head only", FILES["aisef2/m.py"], uses)):
            with self.subTest(name):
                self.init({"aisef2/e.py": enum, "aisef2/m.py": at_base})
                self.edit({"aisef2/e.py": enum + "    BLUE = 2\n", "aisef2/m.py": at_head})
                doc, _ = D.build(self.repo, self.base, self.commit("both"))
                row = {r["path"]: r for r in doc["files"]}["aisef2/e.py"]
                self.assertEqual(row["targets"], {"aisef2/m.py::f": [imports], "aisef2/m.py::g": [imports]})

    def test_a_kill_file_change_re_measures_the_targets_whose_kill_set_holds_it(self):
        doc = self.delta({N: "X = 2\n"})
        row = doc["files"][0]
        self.assertEqual((row["kinds"], row["targets"]), (["kill_file", D.UNMEASURED], {"aisef2/n.py::h": ["in its kill set"]}))
        self.assertEqual(doc["targets"]["aisef2/n.py::h"]["verdict"], "re-measure: kill tests changed: tests/v2/test_n.py")
        self.assertEqual(doc["counts"]["remeasure"], 1)

    def test_a_closure_only_change_re_measures_the_targets_whose_kill_tests_import_it(self):
        doc = self.delta({"tests/v2/helper.py": "VALUE = 2\n"})
        row = doc["files"][0]
        self.assertEqual((row["kinds"], sorted(row["targets"]), row["tests_or_harness"]),
                         (["kill_closure", D.UNMEASURED], ["aisef2/m.py::f", "aisef2/m.py::g"], [M]))
        self.assertEqual(self.verdicts(doc)["aisef2/m.py::f"], "re-measure: kill tests changed: tests/v2/helper.py")
        self.assertTrue(self.verdicts(doc)["aisef2/n.py::h"].endswith("can stand at head"))
        self.assertEqual((row["read_set"]["not_measured"], row["read_set"]["provisional_except"]),
                         ([N], ["aisef2/m.py::f", "aisef2/m.py::g"]))

    def test_the_closure_is_taken_at_both_commits_and_a_rename_has_both_sides(self):
        self.init({M: "from tests.v2 import helper\nFIX = 'tests/v2/fixtures'\n", "tests/v2/fixtures/old.json": "{}\n"})
        (self.repo / "tests/v2/fixtures/old.json").rename(self.repo / "tests/v2/fixtures/new.json")
        doc = self.delta({})
        row = doc["files"][0]
        self.assertEqual((row["from"], row["path"], row["status"]),
                         ("tests/v2/fixtures/old.json", "tests/v2/fixtures/new.json", "R100"))
        self.assertEqual(self.verdicts(doc)["aisef2/m.py::f"],
                         "re-measure: kill tests changed: tests/v2/fixtures/new.json, tests/v2/fixtures/old.json")

    def test_other_code_in_the_closure_is_reported_beside_a_verdict_it_does_not_change(self):
        self.init({M: "from tests.v2 import helper\nfrom validation.v2 import reader\n",
                   "validation/v2/reader.py": "DATA = 1\n"})
        doc = self.delta({"validation/v2/reader.py": "DATA = 2\n"})
        row = doc["files"][0]
        why = "in its kill tests' closure (code outside tests/: reported, not counted)"
        self.assertEqual((row["kinds"], row["targets"]), (["kill_closure", D.UNMEASURED],
                                                          {"aisef2/m.py::f": [why], "aisef2/m.py::g": [why]}))
        f = doc["targets"]["aisef2/m.py::f"]
        self.assertEqual((f["verdict"], f["other_code_changed"]), (self.stand(), ["validation/v2/reader.py"]))
        _, md = D.build(self.repo, self.base, "HEAD")
        self.assertIn("other code changed: validation/v2/reader.py", md)

    # -- outside the proof's rules ----------------------------------------------------------------------------------

    def test_a_harness_change_affects_every_target_in_its_own_row_and_the_proof_still_decides(self):
        doc = self.delta({"validation/v2/owned_run.py": "X = 2\n"})
        row = doc["files"][0]
        self.assertEqual((row["kinds"], sorted(row["targets"]), row["remeasure"]), (["harness"], sorted(TARGETS), []))
        self.assertEqual(doc["harness_changed"], [{"path": "validation/v2/owned_run.py", "names_changed": ["X"]}])
        self.assertEqual((doc["counts"]["remeasure"], doc["counts"]["affected_targets"]), (0, 3))
        note = (f"harness change: validation/v2/owned_run.py changed since {self.base[:7]} (the runner's code; the proof's "
                f"rules do not bind it)")
        self.assertEqual({t: v.get("outside_the_proof") for t, v in doc["targets"].items()}, dict.fromkeys(TARGETS, [note]))
        self.assertEqual({v["generator"] for v in doc["targets"].values()}, {SAME})
        _, md = D.build(self.repo, self.base, "HEAD")
        self.assertIn("every V2.1 target (3): harness change", md)
        for t in TARGETS:
            self.assertIn(f"| `{t}` | {self.stand()} | {note} |", md)

    def test_a_file_the_harness_imports_is_harness(self):
        self.init({"validation/v2/owned_run.py": "from validation.v2 import run_util\n", "validation/v2/run_util.py": "X = 1\n"})
        row = self.delta({"validation/v2/run_util.py": "X = 2\n"})["files"][0]
        self.assertEqual((row["kinds"], len(row["targets"])), (["harness"], 3))

    def test_an_evidence_only_change_outside_copy_affects_no_target(self):
        doc = self.delta({"evidence/notes.md": "more notes\n"})
        self.assertEqual((doc["files"][0]["kinds"], doc["files"][0]["targets"]), ([D.EVIDENCE], {}))
        self.assertNotIn("read_set", doc["files"][0])
        self.assertEqual((doc["counts"]["affected_targets"], doc["counts"]["remeasure"], doc["counts"]["provisional"]),
                         (0, 0, 0))

    def test_copy_is_taken_at_both_commits(self):
        less = tuple(c for c in COPY if c != "docs")
        for name, at_base, at_head, path in (("an entry at base only", COPY, less, "docs/notes.md"),
                                             ("an entry at head only", COPY, (*COPY, "evidence"), "evidence/notes.md")):
            with self.subTest(name):
                self.init({"validation/v2/mutation.py": _toy_mutation(TARGETS, at_base)})
                self.edit({"validation/v2/mutation.py": _toy_mutation(TARGETS, at_head), path: "changed\n"})
                doc, _ = D.build(self.repo, self.base, self.commit("copy"))
                row = {r["path"]: r for r in doc["files"]}[path]
                self.assertEqual((row["kinds"], row["read_set"]["not_measured"]), ([D.UNMEASURED], [M, N]))
                self.assertEqual(doc["counts"]["provisional"], 3)

    def test_code_that_reaches_no_target_has_its_own_kind(self):
        for path, text, kinds in (("tools/run.py", "X = 1\n", [D.CODE]), ("docs/run.sh", "echo\n", [D.CODE, D.UNMEASURED]),
                                  ("docs/runner", "#!/bin/sh\necho\n", [D.CODE, D.UNMEASURED]),
                                  ("docs/table.tsv", "a\tb\n", [D.UNMEASURED])):
            with self.subTest(path=path):
                self.init({})
                self.assertEqual(self.delta({path: text})["files"][0]["kinds"], kinds)

    def test_a_file_inside_copy_whose_reading_is_not_measured_makes_every_result_provisional(self):
        doc = self.delta({"docs/notes.md": "more notes\n"})
        row = doc["files"][0]
        self.assertEqual((row["kinds"], row["targets"]), ([D.UNMEASURED], {}))
        self.assertEqual(row["read_set"], {"read_by": {}, "not_measured": [M, N], "cleared": [], "provisional": 3,
                                           "provisional_except": []})
        self.assertEqual({t: (v["verdict"], v["read_set_not_measured"], v["outside_the_proof"])
                          for t, v in doc["targets"].items()}, dict.fromkeys(TARGETS, (self.stand(), 1, [self.provisional()])))
        self.assertEqual((doc["counts"]["stand"], doc["counts"]["provisional"], doc["read_set"]), (3, 3, None))
        _, md = D.build(self.repo, self.base, "HEAD")
        self.assertIn(f"the {self.base[:7]} results stand only PROVISIONALLY for every target until a measured read-set", md)
        self.assertIn("**3 of the 3 that can stand do so only PROVISIONALLY**", md)
        self.assertIn("Read-set of the kill files: **not measured**", md)
        for t in TARGETS:
            self.assertIn(f"| `{t}` | {self.stand()} | {self.provisional()} |", md)

    def test_a_re_measured_target_is_not_called_provisional(self):
        self.edit({"docs/notes.md": "x\n", "aisef2/n.py": "def h(x):\n    return x\n"})
        head = self.commit("two")
        doc, _ = D.build(self.repo, self.base, head)
        h = doc["targets"]["aisef2/n.py::h"]
        self.assertEqual(h["outside_the_proof"], ["inside mutation.COPY, read-set not measured: 1 changed file(s) — a "
                                                  "re-measure at head reads them as they are"])
        self.assertEqual(doc["counts"]["provisional"], 2)

    def test_data_a_kill_test_names_is_reported_and_its_result_stands_only_provisionally(self):
        doc = self.delta({"docs/data.json": "{\"x\": 1}\n"})
        row = doc["files"][0]
        self.assertEqual((row["kinds"], row["tests_or_harness"]), ([D.DATA, D.UNMEASURED], [M]))
        self.assertEqual(row["read_set"], {"read_by": {M: f"found statically: {M} names its path"}, "not_measured": [M, N],
                                           "cleared": [], "provisional": 3, "provisional_except": []})
        f = doc["targets"]["aisef2/m.py::f"]
        self.assertTrue(f["verdict"].endswith("can stand at head"))
        self.assertEqual(f["outside_the_proof"], ["data its kill tests may read changed (found statically): docs/data.json",
                                                  self.provisional()])
        self.assertEqual(doc["targets"]["aisef2/n.py::h"]["outside_the_proof"], [self.provisional()])
        self.assertEqual((doc["counts"]["provisional"], doc["counts"]["data_read"]), (3, 0))
        _, md = D.build(self.repo, self.base, "HEAD")
        self.assertIn("**3 of the 3 that can stand do so only PROVISIONALLY**", md)

    def test_data_found_statically_however_the_path_is_written(self):
        base = ("import glob\nimport os\nimport pathlib\nfrom tests.v2 import helper\n"
                "ROOT = pathlib.Path(__file__).parents[2]\n")
        cases = {
            "path parts, each quoted": ({M: base + "D = ROOT / 'docs' / 'sub' / 'data.json'\n"}, "docs/sub/data.json",
                                        "M", f"{M} names its path parts"),
            "a parent and the rest": ({M: base + "D = ROOT / 'docs/sub' / 'data.json'\n"}, "docs/sub/data.json",
                                      "M", f"{M} names its path parts"),
            "a parent and the basename": ({M: base + "P = ('docs/sub', 'data.json')\n"}, "docs/sub/x/data.json",
                                          "M", f"{M} names a parent directory and its name"),
            "held by a module the kill test imports": (
                {M: base + "from validation.v2 import reader\n", "validation/v2/reader.py": "DATA = 'docs/sub/data.json'\n"},
                "docs/sub/data.json", "M", "validation/v2/reader.py names its path"),
            "a glob of its directory": ({M: base + "A = sorted((ROOT / 'docs' / 'sub').glob('*.json'))\n"},
                                        "docs/sub/new.json", "A", f"{M} names a directory it lists"),
            "an iterdir of its directory": ({M: base + "A = list((ROOT / 'docs' / 'sub').iterdir())\n"},
                                            "docs/sub/new.json", "A", f"{M} names a directory it lists"),
            "the parts in source order": ({M: base + "A = sorted((ROOT / 'docs' / 'zone' / 'area').glob('*.json'))\n"},
                                          "docs/zone/area/new.json", "A", f"{M} names a directory it lists"),
            "a listing relative to the module's own directory": (
                {M: base + "from validation.v2 import reader\n",
                 "validation/v2/reader.py": "import pathlib\nA = sorted((pathlib.Path(__file__).parent / 'data').glob('*'))\n"},
                "validation/v2/data/new.json", "A", "validation/v2/reader.py names a directory it lists"),
            "a glob pattern's literal part": ({M: base + "A = glob.glob(str(ROOT / 'docs/sub/*.json'))\n"},
                                              "docs/sub/new.json", "A", f"{M} names a directory it lists"),
            "an iglob of its directory": ({M: base + "A = list(glob.iglob(os.path.join(ROOT, 'docs', 'sub', '*.json')))\n"},
                                          "docs/sub/new.json", "A", f"{M} names a directory it lists"),
            "a listdir of its directory": ({M: base + "A = os.listdir(ROOT / 'docs' / 'sub')\n"},
                                           "docs/sub/new.json", "A", f"{M} names a directory it lists"),
            "a scandir of its directory": ({M: base + "A = list(os.scandir(os.path.join(ROOT, 'docs', 'sub')))\n"},
                                           "docs/sub/new.json", "A", f"{M} names a directory it lists"),
            "an os.walk above it": ({M: base + "A = list(os.walk(os.path.join(ROOT, 'docs')))\n"},
                                    "docs/sub/deep/new.json", "A", f"{M} names a directory it lists"),
            "an os.fwalk above it": ({M: base + "A = list(os.fwalk(os.path.join(ROOT, 'docs')))\n"},
                                     "docs/sub/deep/new.json", "A", f"{M} names a directory it lists"),
            "a recursive glob above it": ({M: base + "A = sorted((ROOT / 'docs').rglob('*.json'))\n"},
                                          "docs/sub/deep/new.json", "A", f"{M} names a directory it lists"),
            "a ** pattern above it": ({M: base + "A = sorted((ROOT / 'docs').glob('**/*.json'))\n"},
                                      "docs/sub/deep/new.json", "A", f"{M} names a directory it lists"),
            "relative to the module's own directory": (
                {M: base + "from validation.v2 import reader\n",
                 "validation/v2/reader.py": "import pathlib\nD = pathlib.Path(__file__).parent / 'data' / 'x.json'\n"},
                "validation/v2/data/x.json", "M", "validation/v2/reader.py names its path parts"),
        }
        for name, (files, changed, status, how) in cases.items():
            with self.subTest(name):
                self.init({**files, **({changed: "{}\n"} if status == "M" else {})})
                row = self.delta({changed: "{\"x\": 2}\n"})["files"][0]
                self.assertEqual((row["status"], row["kinds"], row["read_set"]["read_by"], row["read_set"]["not_measured"]),
                                 (status, [D.DATA, D.UNMEASURED], {M: f"found statically: {how}"}, [M, N]))
                self.assertEqual(sorted(t for t, w in row["targets"].items() if MAY_READ in w), ["aisef2/m.py::f", "aisef2/m.py::g"])

    def test_data_is_looked_for_at_both_commits(self):
        reader = "validation/v2/reader.py"
        for name, at_base, at_head in (("named at base only", "D = 'docs/sub/data.json'\n", "D = None\n"),
                                       ("named at head only", "D = None\n", "D = 'docs/sub/data.json'\n")):
            with self.subTest(name):
                self.init({M: FILES[M] + "from validation.v2 import reader\n", reader: at_base, "docs/sub/data.json": "{}\n"})
                self.edit({reader: at_head, "docs/sub/data.json": "{\"x\": 2}\n"})
                doc, _ = D.build(self.repo, self.base, self.commit("both"))
                row = {r["path"]: r for r in doc["files"]}["docs/sub/data.json"]
                self.assertEqual(row["read_set"]["read_by"], {M: f"found statically: {reader} names its path"})

    def test_data_is_looked_for_in_the_kill_files_closure_at_both_commits(self):
        reader = "validation/v2/reader.py"
        imports = FILES[M] + "from validation.v2 import reader\n"
        for name, at_base, at_head in (("imported at base only", imports, FILES[M] + "Y = 1\n"),
                                       ("imported at head only", FILES[M], imports)):
            with self.subTest(name):
                self.init({M: at_base, reader: "D = 'docs/sub/data.json'\n", "docs/sub/data.json": "{}\n"})
                self.edit({M: at_head, "docs/sub/data.json": "{\"x\": 2}\n"})
                doc, _ = D.build(self.repo, self.base, self.commit("both"))
                row = {r["path"]: r for r in doc["files"]}["docs/sub/data.json"]
                self.assertEqual(row["read_set"]["read_by"], {M: f"found statically: {reader} names its path"})

    def test_a_name_alone_or_a_directory_never_listed_is_not_found(self):
        base = "import pathlib\nfrom tests.v2 import helper\nROOT = pathlib.Path(__file__).parents[2]\n"
        for name, files, changed in (
                ("the basename only", {M: base + "N = 'data.json'\n"}, "docs/sub/data.json"),
                ("a parent of one component and the basename", {M: base + "P = ('docs', 'data.json')\n"},
                 "docs/sub/data.json"),
                ("its directory, never listed", {M: base + "D = ROOT / 'docs' / 'sub'\n"}, "docs/sub/new.json"),
                ("a sibling's directory listed", {M: base + "A = list((ROOT / 'docs' / 'other').iterdir())\n"},
                 "docs/sub/new.json"),
                ("a listing of a variable, a file at the top",
                 {M: base + "A = sorted(pathlib.Path(ROOT).iterdir())\n"}, "pyproject.toml"),
                ("a directory named apart from a listing of a variable",
                 {M: base + "D = ROOT / 'docs' / 'sub'\nA = sorted(pathlib.Path(D).rglob('*'))\n"}, "docs/sub/new.json"),
                ("** outside a listing call is not a recursive glob",
                 {M: base + "A = sorted((ROOT / 'docs').glob('*.md'))\nNOTE = 'the **primary** corpus'\nB = '**'\n"},
                 "docs/sub/deep/new.json"),
                ("named by a closure file outside COPY (not in the runner's tree)",
                 {M: base + "from validation.qualification import q\n", "validation/qualification/__init__.py": "",
                  "validation/qualification/q.py": "D = 'docs/sub/data.json'\n"}, "docs/sub/data.json")):
            with self.subTest(name):
                self.init(files)
                row = self.delta({changed: "{}\n"})["files"][0]
                self.assertEqual((row["kinds"], row["read_set"]["read_by"], row["read_set"]["not_measured"]),
                                 ([D.UNMEASURED], {}, [M, N]))

    # -- the measured read-set --------------------------------------------------------------------------------------

    def test_a_measured_read_set_names_the_readers_and_clears_the_rest(self):
        doc = self.delta({"docs/notes.md": "x\n"}, {"kill_files": {M: ran(M, ["./docs/notes.md"]),
                                                                   N: ran(N, ["docs/data.json"], ["docs/sub"])}})
        row = doc["files"][0]
        self.assertEqual((row["kinds"], row["read_set"]), ([D.DATA], {
            "read_by": {M: "measured"}, "not_measured": [], "cleared": [N], "provisional": 0,
            "provisional_except": sorted(TARGETS)}))
        note = (f"data its kill tests read changed (measured): docs/notes.md — the {self.base[:7]} result is no ground "
                f"at head (the proof's rules do not cover data): re-measure it")
        self.assertEqual({t: v.get("outside_the_proof") for t, v in doc["targets"].items()},
                         {"aisef2/m.py::f": [note], "aisef2/m.py::g": [note], "aisef2/n.py::h": None})
        self.assertEqual({t: v["data_read"] for t, v in doc["targets"].items()},
                         {"aisef2/m.py::f": 1, "aisef2/m.py::g": 1, "aisef2/n.py::h": 0})
        self.assertEqual(row["targets"], dict.fromkeys(["aisef2/m.py::f", "aisef2/m.py::g"],
                                                       ["data its kill tests read (measured; outside the proof's rules)"]))
        self.assertEqual((doc["read_set"]["path"], doc["read_set"]["kill_files"], doc["counts"]["provisional"],
                          doc["counts"]["data_read"], doc["counts"]["stand"]), ("readset.json", 2, 0, 2, 3))
        _, md = D.build(self.repo, self.base, "HEAD", self.repo / "readset.json")
        self.assertIn("**2 of the 3 that can stand by the proof's rules have kill tests that read changed data inside "
                      f"`mutation.COPY` (measured)**: the proof's rules do not cover data, so a {self.base[:7]} result is no "
                      "ground for them at head; re-measure them.", md)
        self.assertIn("no target re-measured by the proof's rules; read by their kill tests (measured; outside the proof's "
                      "rules): re-measure 2: `aisef2/m.py::f`, `aisef2/m.py::g` |", md)
        self.assertNotIn("PROVISIONALLY", md)

    def test_a_re_measured_target_whose_kill_tests_read_changed_data_is_not_counted_again(self):
        self.edit({"docs/notes.md": "x\n", "aisef2/n.py": "def h(x):\n    return x\n"})
        head = self.commit("two")
        rs = self.repo / "readset.json"
        rs.write_text(json.dumps({"commit": head, "kill_files": {M: ran(M), N: ran(N, ["docs/notes.md"])}}), encoding="utf-8")
        doc, md = D.build(self.repo, self.base, head, rs)
        self.assertEqual(doc["targets"]["aisef2/n.py::h"]["outside_the_proof"],
                         ["data its kill tests read changed (measured): docs/notes.md"])
        self.assertEqual((doc["counts"]["data_read"], doc["counts"]["remeasure"]), (0, 1))
        self.assertNotIn("have kill tests that read changed data", md)
        self.assertNotIn("read by their kill tests (measured", md)

    def test_a_measurement_decides_over_a_static_finding(self):
        row = self.delta({"docs/data.json": "{\"x\": 1}\n"}, {"kill_files": {M: ran(M), N: ran(N)}})["files"][0]
        self.assertEqual((row["kinds"], row["targets"], row["read_set"]["read_by"], row["read_set"]["cleared"]),
                         ([D.UNREAD], {}, {}, [M, N]))

    def test_a_listed_directory_above_the_file_reads_it(self):
        for listed in ("docs", "docs/", "./docs/a", "."):      # "." is the tree's root
            with self.subTest(listed):
                self.init({})
                row = self.delta({"docs/a/b.md": "x\n"}, {"kill_files": {M: ran(M, listed=["docs/b"]),
                                                                         N: ran(N, listed=[listed])}})["files"][0]
                self.assertEqual((row["kinds"], row["read_set"]["read_by"], row["read_set"]["cleared"]),
                                 ([D.DATA], {N: "measured"}, [M]))

    def test_a_read_set_that_clears_every_kill_file_leaves_no_target(self):
        row = self.delta({"docs/notes.md": "x\n"}, {"kill_files": {M: ran(M), N: ran(N)}})["files"][0]
        self.assertEqual((row["kinds"], row["targets"], row["read_set"]["cleared"]), ([D.UNREAD], {}, [M, N]))

    def test_a_kill_file_missing_from_the_read_set_stays_not_measured(self):
        doc = self.delta({"docs/notes.md": "x\n"}, {"kill_files": {M: ran(M)}})
        row = doc["files"][0]
        self.assertEqual((row["kinds"], row["read_set"]["not_measured"], row["read_set"]["cleared"],
                          row["read_set"]["provisional_except"]), ([D.UNMEASURED], [N], [M], ["aisef2/m.py::f", "aisef2/m.py::g"]))
        self.assertEqual(doc["targets"]["aisef2/n.py::h"]["outside_the_proof"], [self.provisional()])

    def test_a_file_missing_at_head_is_never_cleared_by_a_run_at_head(self):
        (self.repo / "docs/notes.md").rename(self.repo / "docs/notes2.md")   # the source is not at head
        row = self.delta({}, {"kill_files": {M: ran(M), N: ran(N)}})["files"][0]
        self.assertEqual((row["status"], row["kinds"], row["read_set"]["not_measured"], row["read_set"]["cleared"]),
                         ("R100", [D.UNMEASURED], [M, N], []))
        self.init({})
        (self.repo / "docs/data.json").rename(self.repo.parent / "data.json")   # out of the repository; M names it: found statically
        row = self.delta({}, {"kill_files": {M: ran(M), N: ran(N)}})["files"][0]
        self.assertEqual((row["status"], row["kinds"], row["read_set"]["read_by"], row["read_set"]["not_measured"]),
                         ("D", [D.DATA, D.UNMEASURED], {M: f"found statically: {M} names its path"}, [M, N]))
        self.init({})
        (self.repo / "docs/data.json").rename(self.repo.parent / "data.json")   # out of the repository; M looked it up at head: it reads it
        row = self.delta({}, {"kill_files": {M: ran(M, ["docs/data.json"]), N: ran(N)}})["files"][0]
        self.assertEqual((row["kinds"], row["read_set"]["read_by"], row["read_set"]["not_measured"]),
                         ([D.DATA, D.UNMEASURED], {M: "measured"}, [N]))

    def test_a_read_set_of_another_commit_or_shape_is_refused(self):
        self.edit({"docs/notes.md": "x\n"})
        head = self.commit("change")
        rs = self.repo / "readset.json"
        rel = "is not a path relative to the tree root"
        for doc, why in (({"commit": self.base, "kill_files": {}}, "not at the head"),
                         ({"commit": head, "kill_files": {M: {"opened": "docs/notes.md", "listed": []}}}, "not a read-set"),
                         ({"commit": head}, "not a read-set"),
                         ({"commit": head, "kill_files": {M: ran(M, [f"/private/tmp/runner/{M}"])}},
                          f"{M}: '/private/tmp/runner/{M}' {rel}"),
                         ({"commit": head, "kill_files": {M: ran(M, ["tests/v2/../../docs/notes.md"])}},
                          f"{M}: 'tests/v2/../../docs/notes.md' {rel}"),
                         ({"commit": head, "kill_files": {M: ran(M, ["docs\\notes.md"])}}, f"{M}: 'docs\\\\notes.md' {rel}"),
                         ({"commit": head, "kill_files": {M: ran(M, ["docs//notes.md"])}}, f"{M}: 'docs//notes.md' {rel}"),
                         ({"commit": head, "kill_files": {M: ran(M, ["docs/./notes.md"])}}, f"{M}: 'docs/./notes.md' {rel}"),
                         ({"commit": head, "kill_files": {M: ran(M), N: ran(N, listed=["/private/tmp/runner/docs"])}},
                          f"{N}: '/private/tmp/runner/docs' {rel}"),
                         ({"commit": head, "kill_files": {M: {"opened": [f"/private/tmp/runner/{M}", "docs/notes.md"],
                                                              "listed": []}}}, f"{M}: '/private/tmp/runner/{M}' {rel}"),
                         ({"commit": head, "kill_files": {M: {"opened": ["docs/notes.md"], "listed": []}}},
                          f"{M}: its own path is not among the files it opened")):
            with self.subTest(why):
                rs.write_text(json.dumps(doc), encoding="utf-8")
                with self.assertRaises(SystemExit) as e:
                    D.build(self.repo, self.base, head, rs)
                self.assertIn(why, str(e.exception))

    # -- directories listed by registry.py (test_directories: only the set of directories that hold a test module) -------

    def listings(self, callers: dict[str, list[str]] | None = None, dirs=DIRS, **by) -> dict:
        """A measured read-set of M and N that listed `dirs`, each by REG alone — or by `callers` (dir -> files) —,
        with `by` (kill file -> the same for that kill file alone) over it."""
        mk = lambda f: ran(f, listed=dirs, by={d: (callers or {}).get(d, [REG]) for d in dirs})  # noqa: E731
        return {"kill_files": {f: by.get(f, mk(f)) for f in (M, N)}}

    def regdelta(self, files: dict[str, str], read_set: dict | None, base: dict[str, str] | None = None):
        """(doc, rows by path) of `files` changed over a snapshot that holds REG, a test module in tests/v2/sub and a
        fixture and no test module in tests/v2/fx; any number of changed files."""
        self.init({REG: REG_SRC, f"{SUB}/test_x.py": "X = 1\n", f"{FX}/data.json": "{}\n", **(base or {})})
        self.edit(files)
        head = self.commit("change")
        rs = None
        if read_set is not None:
            rs = self.repo / "readset.json"
            rs.write_text(json.dumps({"commit": head, **read_set}), encoding="utf-8")
        doc, _ = D.build(self.repo, self.base, head, rs)
        return doc, {r["path"]: r for r in doc["files"]}

    def outcome(self, row: dict) -> str:
        """`unread` (a measured read-set clears it for both kill files), `read` (both read it), or the split."""
        d, kinds = row.get("read_set", {}), set(row["kinds"]) - {D.CODE}
        if kinds == {D.UNREAD}:
            return "unread"
        if kinds == {D.DATA} and set(d["read_by"]) == {M, N}:
            return "read"
        return f"{sorted(d.get('read_by', {}))} read, {d.get('cleared')} cleared"

    def test_a_directory_listed_only_by_the_registry_is_not_read_by_a_file_that_cannot_change_its_result(self):
        for name, files in (("a test module beside another", {f"{SUB}/test_y.py": "X = 2\n"}),
                            ("a test module beside others in tests/v2 itself", {"tests/v2/test_y.py": "X = 2\n"}),
                            ("a test module changed, the only one of its directory", {f"{SUB}/test_x.py": "X = 3\n"}),
                            ("a fixture beside a test module", {f"{SUB}/data.json": "{}\n"}),
                            ("a fixture changed in a directory with no test module", {f"{FX}/data.json": "{\"x\": 1}\n"}),
                            ("a fixture in a directory new at head", {f"{NEW}/data.json": "{}\n"}),
                            ("a fixture in directories new at head", {f"{NEW}/deep/er/data.json": "{}\n"})):
            with self.subTest(name):
                (path,) = files
                doc, rows = self.regdelta(files, self.listings())
                self.assertEqual(self.outcome(rows[path]), "unread")
                self.assertEqual((rows[path]["read_set"]["cleared"], rows[path]["read_set"]["read_by"]), ([M, N], {}))
                self.assertTrue(doc["read_set"]["listing_discount"]["applies"])
                # the same change by a record that does not say who listed: read, as before the attribution existed
                _, rows = self.regdelta(files, {"kill_files": {f: ran(f, listed=DIRS) for f in (M, N)}})
                self.assertEqual(self.outcome(rows[path]), "read")

    def test_the_first_or_last_test_module_of_a_directory_is_read_through_the_registrys_listing(self):
        for name, files, base in (
                ("the first of a new directory", {f"{NEW}/test_z.py": "X = 1\n"}, None),
                ("the first of a directory that held a fixture", {f"{FX}/test_z.py": "X = 1\n"}, None),
                ("the last of a directory, removed", {f"{SUB}/test_x.py": None}, None),
                ("a test module renamed to another directory", {f"{SUB}/test_x.py": None, f"{NEW}/test_x.py": "X = 1\n"}, None),
                ("a directory named like a test module, new", {f"{NEW}/test_d.py/data.json": "{}\n"}, None)):
            with self.subTest(name):
                self.init({REG: REG_SRC, f"{SUB}/test_x.py": "X = 1\n", f"{FX}/data.json": "{}\n", **(base or {})})
                for rel, text in files.items():
                    if text is None:
                        _git(self.repo, "rm", "-q", "--", rel)    # the change removes it: git does, from tree and index
                self.edit({r: t for r, t in files.items() if t is not None})
                head = self.commit("change")
                rs = self.repo / "readset.json"
                rs.write_text(json.dumps({"commit": head, **self.listings()}), encoding="utf-8")
                doc, _ = D.build(self.repo, self.base, head, rs)
                rows = {p: r for r in doc["files"] for p in (r["path"], r.get("from")) if p}   # a rename has both
                self.assertTrue(doc["read_set"]["listing_discount"]["applies"])
                for path in files:
                    self.assertEqual(self.outcome(rows[path]), "read", path)
                    self.assertEqual(rows[path]["read_set"]["read_by"], {M: "measured", N: "measured"})

    def test_a_directory_listed_by_the_registry_and_by_another_caller_is_read(self):
        files = {f"{SUB}/test_y.py": "X = 2\n"}
        for name, callers in (("another file of the tree", [REG, M]), ("code with no file of the tree", [REG, "<native>"]),
                              ("another file alone", [M]), ("the registry named for nothing", []),
                              ("a file that only looks like it", ["tests/aisef2/invariants/registry.py"])):
            with self.subTest(name):
                _, rows = self.regdelta(files, self.listings({SUB: callers}))
                self.assertEqual(self.outcome(rows[f"{SUB}/test_y.py"]), "read")
        # per kill file, and per directory above the file: only the directories above it count
        _, rows = self.regdelta(files, self.listings(**{
            M: ran(M, listed=DIRS, by={d: [REG] for d in DIRS}),
            N: ran(N, listed=DIRS, by={**dict.fromkeys(DIRS, [REG]), SUB: [REG, N]})}))
        row = rows[f"{SUB}/test_y.py"]
        self.assertEqual((row["kinds"], row["read_set"]["read_by"], row["read_set"]["cleared"]), ([D.CODE, D.DATA], {N: "measured"}, [M]))
        _, rows = self.regdelta({"tests/v2/test_y.py": "X = 2\n"}, self.listings({SUB: [REG, N], NEW: [N]}))
        self.assertEqual(self.outcome(rows["tests/v2/test_y.py"]), "unread")   # tests/v2 alone is above it

    def test_a_file_the_kill_file_opened_or_a_directory_listed_without_attribution_is_read(self):
        files = {f"{SUB}/test_y.py": "X = 2\n"}
        _, rows = self.regdelta(files, self.listings(**{M: ran(M, [f"{SUB}/test_y.py"], DIRS, {d: [REG] for d in DIRS})}))
        row = rows[f"{SUB}/test_y.py"]   # opened: read whoever listed
        self.assertEqual((row["read_set"]["read_by"], row["read_set"]["cleared"]), ({M: "measured"}, [N]))
        for name, by in (("no listed_by", None), ("an empty listed_by", {}), ("only another directory", {NEW: [REG]}),
                         ("a directory of no listing", {"tests/v2": [REG], SUB: []})):
            with self.subTest(name):
                doc, rows = self.regdelta(files, {"kill_files": {f: ran(f, listed=DIRS, by=by) for f in (M, N)}})
                self.assertEqual(self.outcome(rows[f"{SUB}/test_y.py"]), "read")
                self.assertEqual(rows[f"{SUB}/test_y.py"]["read_set"]["read_by"], {M: "measured", N: "measured"})
                if not by:   # no listed_by in either: the table says so rather than that a rule was applied
                    self.assertEqual(doc["read_set"]["listing_discount"]["attributed"], 0)
                    _, md = D.build(self.repo, self.base, "HEAD", self.repo / "readset.json")
                    self.assertIn("the record has no `listed_by` for any kill file", md)
                    self.assertNotIn("only as the first or last test module", md)

    def test_a_file_outside_tests_v2_or_a_listing_outside_it_is_never_discounted(self):
        _, rows = self.regdelta({"docs/new.md": "x\n"}, self.listings(dirs=(*DIRS, "docs")))
        self.assertEqual(self.outcome(rows["docs/new.md"]), "read")   # docs listed by the registry's name, p not under tests/v2
        for d in ("tests", "."):
            with self.subTest(d):
                _, rows = self.regdelta({f"{SUB}/test_y.py": "X = 2\n"}, self.listings(dirs=(*DIRS, d)))
                self.assertEqual(self.outcome(rows[f"{SUB}/test_y.py"]), "read")   # a directory above tests/v2 listed too

    def test_test_directories_changed_between_base_and_head_turns_the_discount_off_and_the_table_says_why(self):
        files = {f"{SUB}/test_y.py": "X = 2\n"}
        doc, rows = self.regdelta(files, self.listings())
        self.assertEqual((doc["read_set"]["listing_discount"]["applies"], self.outcome(rows[f"{SUB}/test_y.py"])),
                         (True, "unread"))
        for name, edit, why in (
                ("its body changed", REG_SRC.replace('base.rglob("test_*.py")', 'base.rglob("*.py")'),
                 f"test_directories in {REG} differs between "),
                ("a decorator added", REG_SRC.replace("def test_directories", "@staticmethod\ndef test_directories"),
                 f"test_directories in {REG} differs between "),
                ("a listing added elsewhere in the file", REG_SRC + "\n\ndef names(d):\n    return sorted(__import__('os').listdir(d))\n",
                 f"{REG} lists a directory outside test_directories at "),
                ("the function removed", REG_SRC.replace("test_directories", "directories"),
                 f"{REG} has no single test_directories at "),
                ("not Python", "def (:\n", f"{REG} does not parse at ")):
            with self.subTest(name):
                doc, rows = self.regdelta({**files, REG: edit}, self.listings())
                d = doc["read_set"]["listing_discount"]
                self.assertEqual((d["applies"], self.outcome(rows[f"{SUB}/test_y.py"])), (False, "read"))
                self.assertIn(why, d["why"])
                _, md = D.build(self.repo, self.base, "HEAD", self.repo / "readset.json")
                self.assertIn("**Listing discount off**", md)
                self.assertIn(d["why"], md)
        # a change of the file that leaves the function (and every listing) alone does not turn it off
        doc, rows = self.regdelta({**files, REG: REG_SRC + "\n\nOTHER = 1\n"}, self.listings())
        self.assertEqual((doc["read_set"]["listing_discount"]["applies"], self.outcome(rows[f"{SUB}/test_y.py"])),
                         (True, "unread"))
        # ... nor a function with other lines in other places (the line numbers are not its source)
        doc, rows = self.regdelta({**files, REG: "\n\n" + REG_SRC}, self.listings())
        self.assertTrue(doc["read_set"]["listing_discount"]["applies"])

    def test_a_snapshot_without_the_registry_has_no_discount(self):
        self.init({})
        self.edit({f"{SUB}/test_y.py": "X = 2\n"})
        head = self.commit("change")
        rs = self.repo / "readset.json"
        rs.write_text(json.dumps({"commit": head, **self.listings()}), encoding="utf-8")
        doc, _ = D.build(self.repo, self.base, head, rs)
        d = doc["read_set"]["listing_discount"]
        self.assertEqual((d["applies"], d["why"], self.outcome(doc["files"][0])),
                         (False, f"{REG} has no single test_directories at {self.base[:7]}", "read"))

    def test_the_table_with_the_discount_is_re_derived_byte_for_byte(self):
        _, rows = self.regdelta({f"{SUB}/test_y.py": "X = 2\n", f"{NEW}/test_z.py": "X = 1\n"}, self.listings())
        head = _git(self.repo, "rev-parse", "HEAD")
        rs = self.repo / "readset.json"
        out = self.write_table(head, rs)
        doc = json.loads((out / "DELTA.json").read_text(encoding="utf-8"))
        self.assertEqual(doc["read_set"]["listing_discount"], {
            "applies": True, "attributed": 2, "why": f"test_directories in {REG} is the same at {self.base[:7]} and "
                                                      f"{head[:7]} and lists nowhere else there; tests/v2 directories "
                                                      f"whose membership of its result changes: 1"})
        md = (out / "DELTA.md").read_text(encoding="utf-8")
        self.assertIn("Listings by `aisef2/invariants/registry.py` (`test_directories`: only the set of directories "
                      "holding a `test_*.py`) read a changed file of `tests/v2` only as the first or last test module of a "
                      "directory (`listed_by` in 2 of 2 kill files)", md)
        self.assertEqual(D.check(self.repo, out), [])
        self.assertEqual(self.outcome(rows[f"{SUB}/test_y.py"]), "unread")
        self.assertEqual(self.outcome(rows[f"{NEW}/test_z.py"]), "read")

    def test_a_malformed_listed_by_is_refused_and_a_record_without_it_is_accepted(self):
        self.edit({f"{SUB}/test_y.py": "X = 2\n"})
        head = self.commit("change")
        rs = self.repo / "readset.json"
        rel = "is not a path relative to the tree root"
        for why, entry in (("not a read-set", {**ran(M), "listed_by": [REG]}),
                           ("not a read-set", {**ran(M), "listed_by": {"tests/v2": REG}}),
                           ("not a read-set", {**ran(M), "listed_by": {"tests/v2": [1]}}),
                           (f"{M}: '/private/tmp/runner/x.py' {rel}", {**ran(M), "listed_by": {"tests/v2": ["/private/tmp/runner/x.py"]}}),
                           (f"{M}: '/private/tmp/runner' {rel}", {**ran(M), "listed_by": {"/private/tmp/runner": [REG]}}),
                           (f"{M}: 'tests/../x' {rel}", {**ran(M), "listed_by": {"tests/v2": ["tests/../x"]}})):
            with self.subTest(why, entry=entry["listed_by"]):
                rs.write_text(json.dumps({"commit": head, "kill_files": {M: entry}}), encoding="utf-8")
                with self.assertRaises(SystemExit) as e:
                    D.build(self.repo, self.base, head, rs)
                self.assertIn(why, str(e.exception))
        rs.write_text(json.dumps({"commit": head, "kill_files": {M: ran(M, listed=["tests/v2"]), N: ran(
            N, listed=["tests/v2/"], by={"./tests/v2/": [REG, "<native>"]})}}), encoding="utf-8")
        got = D._read_set(rs, head)
        self.assertEqual((got[M][2], got[N][2]), ({}, {"tests/v2": frozenset({REG, "<native>"})}))

    # -- records ----------------------------------------------------------------------------------------------------

    def test_records_name_the_manifest_the_t0_pairs_the_execution_order_and_q0_to_re_derive(self):
        self.init({"validation/v2/checker_calibration.py": "OUT_REL = 'closure-evidence/Q0.json'\n"})
        ns: dict = {}
        exec(_toy_mutation(TARGETS), ns)   # noqa: S102 - the toy's own null_mutant (the repository's definition)
        null = {t: _sha(ns["null_mutant"](FILES[t.split("::")[0]], t.split("::")[1])) for t in TARGETS}
        t0 = {"measured_on": self.base, "rows": [
            {"module": t.split("::")[0], "null": null[t], "file": k, "rows": [{"role": "t0", "outcome": "PASS"}]}
            for t in ("aisef2/m.py::f",) for k in TARGETS[t]]}   # h's pair has no row at base either
        man = {"snapshot": self.base, "revision": 2, "harness": {"path": "validation/v2/mutation.py",
                                                                 "sha256": _sha(FILES["validation/v2/mutation.py"])},
               "versions": {"kill_files": {M: _sha(FILES[M]), N: _sha(FILES[N])}},
               "t0": {"path": "closure-evidence/T0.json"}, "execution_order": {"path": "closure-evidence/EO.json"}}
        man_rel = "closure-evidence/v2/v2.1/REQUALIFICATION-MANIFEST-2.json"
        self.edit({man_rel: json.dumps(man), "closure-evidence/T0.json": json.dumps(t0), M: FILES[M] + "Y = 1\n",
                   "validation/v2/mutation.py": _toy_mutation({**TARGETS, "aisef2/m.py::f": [M, N]})})
        doc, md = D.build(self.repo, self.base, self.commit("records"))
        rec = {r["record"]: r for r in doc["records"]}
        self.assertEqual(list(rec), [man_rel, "closure-evidence/T0.json", "closure-evidence/EO.json", "closure-evidence/Q0.json"])
        kill = {"why": "1 kill set(s) changed", "targets": ["aisef2/m.py::f"], "files": [N, "validation/v2/mutation.py"]}
        self.assertEqual(rec[man_rel]["reasons"], [
            kill, {"why": f"{M}: its sha256 at head is not the one the manifest binds", "files": [M]},
            {"why": "validation/v2/mutation.py: its sha256 at head is not the one the manifest binds",
             "files": ["validation/v2/mutation.py"]}])
        n16 = null["aisef2/m.py::f"][:16]
        self.assertEqual((rec["closure-evidence/T0.json"]["reasons"], rec["closure-evidence/T0.json"]["already_needed_at_base"]), ([
            {"why": f"the kill file changed since the sweep: aisef2/m.py null {n16} x {M}",
             "targets": ["aisef2/m.py::f", "aisef2/m.py::g"], "files": [M]},
            {"why": f"no PASS T0 row: aisef2/m.py null {n16} x {N}", "targets": ["aisef2/m.py::f"], "files": [N]}], 1))
        self.assertEqual(rec["closure-evidence/EO.json"]["reasons"], [
            kill, {"why": "2 T0 pair(s) to measure", "files": [M, N]},
            {"why": "closure-evidence/T0.json changed", "files": ["closure-evidence/T0.json"]}])
        self.assertEqual(rec["closure-evidence/Q0.json"]["reasons"], [
            {"why": "validation/v2/mutation.py: a checker, its source or its known-bad fixture changed",
             "files": ["validation/v2/mutation.py"]}])
        rows = {r["path"]: r["records"] for r in doc["files"]}
        self.assertEqual(rows["validation/v2/mutation.py"], [man_rel, "closure-evidence/EO.json", "closure-evidence/Q0.json"])
        self.assertEqual(rows[M], [man_rel, "closure-evidence/T0.json", "closure-evidence/EO.json"])
        self.assertIn("| `closure-evidence/Q0.json` | yes: re-derive the Q0 checker calibration |", md)
        self.assertEqual(rec["closure-evidence/Q0.json"]["note"], "not written at head")

    def test_a_kill_file_the_manifest_does_not_bind_is_a_reason(self):
        man_rel = "closure-evidence/v2/v2.1/REQUALIFICATION-MANIFEST-2.json"
        other = "closure-evidence/v2/v2.1/REQUALIFICATION-MANIFEST-3.json"   # sorted after: of another snapshot
        self.edit({man_rel: json.dumps({"snapshot": self.base, "versions": {"kill_files": {M: _sha(FILES[M])}}}),
                   other: json.dumps({"snapshot": "0" * 40, "versions": {"kill_files": {}}})})
        doc, _ = D.build(self.repo, self.base, self.commit("manifest"))
        self.assertEqual((doc["records"][0]["record"], doc["records"][0]["reasons"]),
                         (man_rel, [{"why": f"kill files the manifest does not bind: {N}", "files": [N]}]))

    def test_the_manifest_is_the_latest_revision_of_this_snapshot(self):
        prefix = "closure-evidence/v2/v2.1/REQUALIFICATION-MANIFEST"
        self.edit({f"{prefix}-3.json": json.dumps({"snapshot": self.base, "revision": 3}),   # sorts before the next
                   f"{prefix}.json": json.dumps({"snapshot": self.base, "revision": 2}),
                   f"{prefix}-1.json": json.dumps({"snapshot": self.base, "revision": None}),
                   f"{prefix}-4.json": json.dumps({"snapshot": "0" * 40, "revision": 4})})
        doc, _ = D.build(self.repo, self.base, self.commit("manifests"))
        self.assertEqual(doc["records"][0]["record"], f"{prefix}-3.json")

    def test_a_null_mutant_change_re_derives_the_execution_order(self):
        man_rel = "closure-evidence/v2/v2.1/REQUALIFICATION-MANIFEST-2.json"
        old, new = "    return ast.unparse(tree)\n", "    return ast.unparse(tree) + '\\n'\n"
        src = _toy_mutation(TARGETS)
        self.assertEqual(src.count(old), 1)
        self.edit({man_rel: json.dumps({"snapshot": self.base, "execution_order": {"path": "closure-evidence/EO.json"}}),
                   "validation/v2/mutation.py": src.replace(old, new)})
        doc, _ = D.build(self.repo, self.base, self.commit("null mutant"))
        eo = {r["record"]: r for r in doc["records"]}["closure-evidence/EO.json"]
        self.assertEqual(eo["reasons"], [{"why": "3 null mutant(s) changed", "targets": sorted(TARGETS),
                                          "files": ["validation/v2/mutation.py"]}])

    def test_q0_follows_a_checker_its_source_and_its_known_bad_fixtures(self):
        self.init({"validation/v2/checker_calibration.py": "OUT_REL = 'closure-evidence/Q0.json'\nSRC = 'tools/chk.py'\n",
                   "tools/chk.py": "X = 1\n", "tests/v2/fixtures/known_bad/bad.py": "X = 1\n", "validation/v2/chk.py": "X = 1\n"})
        for path in ("tools/chk.py", "tests/v2/fixtures/known_bad/bad.py", "validation/v2/chk.py"):
            with self.subTest(path):
                q0 = {r["record"]: r for r in self.delta({path: "X = 2\n"})["records"]}["closure-evidence/Q0.json"]
                self.assertEqual((q0["rederive"], q0["reasons"]), (True, [
                    {"why": f"{path}: a checker, its source or its known-bad fixture changed", "files": [path]}]))
                self.base = _git(self.repo, "rev-parse", "HEAD")
        q0 = {r["record"]: r for r in self.delta({"docs/x.md": "x\n"})["records"]}["closure-evidence/Q0.json"]
        self.assertEqual((q0["rederive"], q0["reasons"]), (False, []))

    # -- --check ----------------------------------------------------------------------------------------------------

    def write_table(self, head: str, read_set: pathlib.Path | None = None) -> pathlib.Path:
        out = self.repo / "docs" / "delta"              # inside COPY, as the real table is
        doc, md = D.build(self.repo, self.base, head, read_set)
        out.mkdir(parents=True, exist_ok=True)
        (out / "DELTA.json").write_text(D.S2._render(doc), encoding="utf-8")
        (out / "DELTA.md").write_text(md, encoding="utf-8")
        return out

    def test_check_refuses_a_stale_or_edited_table_and_passes_a_current_one(self):
        self.edit({"evidence/notes.md": "more notes\n"})
        head = self.commit("evidence")
        out = self.write_table(head)
        doc, md = json.loads((out / "DELTA.json").read_text(encoding="utf-8")), (out / "DELTA.md").read_text(encoding="utf-8")
        self.commit("the table")                         # inside OUT_DIR: never a change the table must cover
        self.assertEqual(D.check(self.repo, out), [])
        self.edit({"evidence/more.md": "x\n"})
        self.commit("more evidence")                     # evidence outside COPY after the table's head: still covered
        self.assertEqual(D.check(self.repo, out), [])
        self.edit({"tools/run.py": "X = 1\n"})
        self.commit("a tool")                            # code outside COPY reaching no target: still covered
        self.assertEqual(D.check(self.repo, out), [])
        self.edit({"docs/more.md": "x\n"})
        now = self.commit("data inside COPY")            # its reading is not measured: not covered
        self.assertEqual(D.check(self.repo, out), [f"stale: HEAD {now[:12]} has changes after the table's head "
                                                   f"{head[:12]} that it does not cover: docs/more.md"])
        self.edit({"aisef2/n.py": "def h(x):\n    return x\n"})
        now = self.commit("product")
        self.assertEqual(D.check(self.repo, out), [f"stale: HEAD {now[:12]} has changes after the table's head "
                                                   f"{head[:12]} that it does not cover: aisef2/n.py, docs/more.md"])
        (out / "DELTA.md").write_text(md.replace("re-measure", "stands"), encoding="utf-8")
        self.assertIn(f"{out}/DELTA.md is not what {self.base[:12]}..{head[:12]} derives now", D.check(self.repo, out))
        doc["head"] = now
        (out / "DELTA.json").write_text(json.dumps(doc), encoding="utf-8")
        self.assertIn(f"{out}/DELTA.json is not what {self.base[:12]}..{now[:12]} derives now", D.check(self.repo, out))

    def test_check_calls_a_later_change_every_kill_test_may_read_stale(self):
        self.init({N: "X = 1\nD = 'docs/data.json'\n"})       # M and N both name it: found statically for each
        self.edit({"evidence/notes.md": "x\n"})
        head = self.commit("evidence")
        out = self.write_table(head)
        self.commit("the table")
        self.edit({"docs/data.json": "{\"x\": 3}\n"})
        now = self.commit("data")
        doc, _ = D.build(self.repo, head, now)
        self.assertEqual((doc["files"][0]["kinds"], doc["files"][0]["read_set"]["not_measured"]), ([D.DATA, D.UNMEASURED], [M, N]))
        self.assertEqual(D.check(self.repo, out), [f"stale: HEAD {now[:12]} has changes after the table's head "
                                                   f"{head[:12]} that it does not cover: docs/data.json"])

    def test_check_calls_a_later_change_a_record_binds_stale(self):
        man_rel = "closure-evidence/v2/v2.1/REQUALIFICATION-MANIFEST-2.json"
        self.edit({man_rel: json.dumps({"snapshot": self.base, "bound": {"path": "evidence/notes.md",
                                                                           "sha256": _sha(FILES["evidence/notes.md"])}})})
        head = self.commit("manifest")
        out = self.write_table(head)
        self.commit("the table")
        self.assertEqual(D.check(self.repo, out), [])
        self.edit({"evidence/notes.md": "edited\n"})
        now = self.commit("bound evidence")
        self.assertEqual(D.check(self.repo, out), [f"stale: HEAD {now[:12]} has changes after the table's head "
                                                   f"{head[:12]} that it does not cover: evidence/notes.md"])

    def test_check_refuses_a_table_derived_beside_other_reuse_criteria(self):
        self.edit({"evidence/notes.md": "x\n"})
        out = self.write_table(self.commit("evidence"))
        self.commit("the table")
        src = D.PROOF.read_text(encoding="utf-8")
        old = 'out.append("its kill set is not the current one")'
        self.assertEqual(src.count(old), 1)
        self.addCleanup(setattr, D, "PROOF", D.PROOF)
        for name, text, problems in (("a change outside the criteria", src + "\n# a comment\n", 0),
                                     ("a change of proof()", src.replace(old, "pass"), 1)):
            with self.subTest(name):
                D.PROOF = pathlib.Path(self._tmp.name) / f"proof-{problems}.py"
                D.PROOF.write_text(text, encoding="utf-8")
                sha = D.MR.criteria_sha256(D.PROOF)
                self.assertEqual(D.check(self.repo, out), [] if not problems else [
                    f"{D.PROOF_REL}: its reuse criteria (criteria_sha256 {sha[:16]}) are not the ones the table was derived "
                    f"beside: verdict() re-implements proof() — compare the two before re-deriving the table"])
        doc = json.loads((out / "DELTA.json").read_text(encoding="utf-8"))
        self.assertEqual(doc["proof"], {"path": D.PROOF_REL, "criteria_sha256": D.MR.criteria_sha256(ROOT / D.PROOF_REL)})

    def test_check_refuses_a_table_whose_head_is_not_an_ancestor_of_head(self):
        _git(self.repo, "checkout", "-q", "-b", "side")
        self.edit({"evidence/notes.md": "side\n"})
        side = self.commit("side")
        out = pathlib.Path(self._tmp.name) / "table"   # outside the repository: no change of either branch
        doc, md = D.build(self.repo, self.base, side)
        out.mkdir()
        (out / "DELTA.json").write_text(D.S2._render(doc), encoding="utf-8")
        (out / "DELTA.md").write_text(md, encoding="utf-8")
        self.assertEqual(D.check(self.repo, out), [])
        _git(self.repo, "checkout", "-q", "-")
        self.edit({"evidence/other.md": "main\n"})
        self.commit("main")
        self.assertEqual(D.check(self.repo, out), [f"the table's head {side[:12]} is not HEAD or an ancestor of it"])

    def test_check_re_derives_with_the_recorded_read_set_and_refuses_another(self):
        self.edit({"docs/notes.md": "x\n"})
        head = self.commit("data")
        rs = self.repo / "readset.json"
        rs.write_text(json.dumps({"commit": head, "kill_files": {M: ran(M), N: ran(N)}}), encoding="utf-8")
        out = self.write_table(head, rs)
        self.assertEqual(json.loads((out / "DELTA.json").read_text(encoding="utf-8"))["files"][0]["kinds"], [D.UNREAD])
        self.assertEqual(D.check(self.repo, out), [])
        rs.write_text(json.dumps({"commit": head, "kill_files": {}}), encoding="utf-8")
        self.assertEqual(D.check(self.repo, out),
                         ["the read-set the table records (readset.json) is missing or not the file it was built from"])


if __name__ == "__main__":
    unittest.main()
