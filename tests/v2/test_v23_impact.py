"""validation/v23/impact.py (F5 static impact engine) on toy git repositories: the W1-DESIGN §9 negatives N1-N33 and
the N14 calibration (an always-VERIFIED_REUSE engine is rejected by the same cases). Each toy holds the real
generator and runner-settings segments of validation/v2/mutation.py (copied into the toy at test time, so the toy
follows the real harness), toy tables, toy targets and one committed record. Nothing is measured; no kill test runs.
Not a kill file."""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from typing import NamedTuple

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.qualification import s2_mutation_record as S2  # noqa: E402
from validation.v2 import mutation as M  # noqa: E402
from validation.v23 import impact  # noqa: E402

REAL = (ROOT / impact.MUTATION_REL).read_text(encoding="utf-8")
KEEP = {"source_digest", "_SWAP", "_inert", "_script", "_root", "mutants", "_enum_members", "null_mutant",
        "superseded", *impact.I9_NAMES}
RECORD = "closure-evidence/v2/T-MUTATION.json"
TARGETS = {
    "aisef2/toy.py::target": ["tests/v2/test_k.py"],
    "aisef2/util.py::inc": ["tests/v2/test_k.py"],
    "aisef2/app/client.py::_is_gone": ["tests/v2/test_client.py"],
    "aisef2/dyn.py::pick": ["tests/v2/test_dyn.py"],
    "aisef2/doc.py::keys": ["tests/v2/test_doc.py"],
}
PY = f"{sys.version_info.major}.{sys.version_info.minor}"
POSIX_TAIL = 'Traceback (most recent call last):\n  File "<tree>/aisef2/toy.py", line 7, in target\nAssertionError\n'
WIN_TAIL = 'Traceback (most recent call last):\n  File "<tree>\\aisef2\\app\\client.py", line 2, in _is_gone\nAssertionError\n'
HOMEBREW = '  File "/opt/homebrew/Cellar/python@3.14/3.14.7/lib/python3.14/unittest/case.py", line 58, in run\n'
USRLIB = '  File "/usr/lib/python3.12/unittest/case.py", line 58, in run\n'

FILES = {
    "pyproject.toml": '[project]\nname = "toy"\n',
    "aisef2/__init__.py": "",
    "aisef2/kinds.py": "from enum import Enum\n\n\nclass Kind(Enum):\n    A = 1\n    B = 2\n",
    "aisef2/util.py": "def inc(x):\n    return x + 1\n",
    "aisef2/toy.py": '"""toy."""\nfrom aisef2 import util\nfrom aisef2.kinds import Kind\n\n\ndef target(x):\n'
                     "    if x > 1:\n        return util.inc(x)\n    return Kind.A.value - 1\n\n\n"
                     "def helper(x):\n    return x * 2\n\n\ndef called_by_test():\n    return 7\n",
    "aisef2/app/__init__.py": "",
    "aisef2/app/client.py": "def _is_gone(pid):\n    return pid < 0\n",
    "aisef2/dyn.py": 'import sys\n\n\ndef pick(x):\n    return "b" if x > 1 else "a"\n\n\ndef run(k):\n'
                     '    return getattr(sys.modules[__name__], "_do_" + k)()\n\n\ndef _do_a():\n    return 1\n\n\n'
                     "def _do_b():\n    return 2\n",
    "aisef2/doc.py": "def keys(d):\n    return sorted(d)\n",
    "docs/v2.1/schema.json": '{"a": 1}\n',
    "tests/__init__.py": "",
    "tests/v2/__init__.py": "",
    "tests/v2/test_k.py": "import unittest\n\nfrom aisef2 import toy, util\n\n\nclass T(unittest.TestCase):\n"
                          "    def test_target(self):\n        self.assertEqual(toy.target(2), 3)\n"
                          "        self.assertEqual(toy.called_by_test(), 7)\n\n"
                          "    def test_inc(self):\n        self.assertEqual(util.inc(1), 2)\n",
    "tests/v2/test_client.py": "import unittest\n\nfrom aisef2.app import client\n\n\nclass T(unittest.TestCase):\n"
                               "    def test_gone(self):\n        self.assertTrue(client._is_gone(-1))\n",
    "tests/v2/test_dyn.py": "import unittest\n\nfrom aisef2 import dyn\n\n\nclass T(unittest.TestCase):\n"
                            "    def test_run(self):\n        self.assertEqual(dyn.run(dyn.pick(1)), 1)\n",
    "tests/v2/test_doc.py": "import json\nimport pathlib\nimport unittest\n\nfrom aisef2 import doc\n\n"
                            "ROOT = pathlib.Path(__file__).resolve().parents[2]\n\n\nclass T(unittest.TestCase):\n"
                            "    def test_schema(self):\n"
                            '        data = json.loads((ROOT / "docs" / "v2.1" / "schema.json").read_text())\n'
                            '        self.assertEqual(doc.keys(data), ["a"])\n',
}


def harness(targets=None, extra: str = "") -> str:
    """The toy's validation/v2/mutation.py: the real generator and I9 segments, toy tables."""
    keep = [text for names, text, _ in impact.segments(REAL) if set(names) & KEEP]
    tables = (f"RECORDS = {{'T': {RECORD!r}}}\nPHASE_TARGETS = {{'T': {targets or TARGETS!r}}}\n"
              "TARGETS = {t: k for ts in PHASE_TARGETS.values() for t, k in ts.items()}\n"
              f"SUPERSEDED = {{}}\nV21_RETIRED = ()\nV21_TARGETS = {{}}\nCOPY = {M.COPY!r}\n{extra}")
    return ("from __future__ import annotations\n\nimport ast\nimport copy\nimport hashlib\nimport os\nimport pathlib\n"
            "import re\nimport sys\n\n" + "\n".join(keep) + "\n" + tables)


def entry(files: dict, target: str, tail: str | None = POSIX_TAIL, survivor: bool = False) -> dict:
    """A runner-2 result with every mutant KILLED by a bracketed kill (mutation._confirmed holds), measured on
    `files`; `survivor` adds a second, SURVIVED mutant."""
    kill = TARGETS[target]
    first = "FAIL: test_x (test_x.T.test_x)"
    row = {"file": kill[0], "outcome": "FAIL", "first": first, **({"tail": tail} if tail else {})}
    rows = [row, {"file": kill[0], "role": "control", "outcome": "PASS"},
            {"file": kill[0], "role": "control", "outcome": "PASS"},
            {"file": kill[0], "role": "rerun", "outcome": "FAIL", "first": first}]
    res = [{"mutant": "L1 a", "class": "KILLED", "killed": True, "killed_by": {"file": kill[0], "first": first},
            "files": rows}]
    if survivor:
        res.append({"mutant": "L2 b", "class": "SURVIVED", "killed": False,
                    "files": [{"file": f, "outcome": "PASS"} for f in kill]})
    return {"target": target, "runner": 2, "kill_tests": list(kill),
            "source_sha256": M.source_digest(files[target.split("::")[0]]), "tree_sha256": "0" * 64,
            "mutants": len(res), "results": res, "t0": [{"file": f, "role": "t0", "outcome": "PASS"} for f in kill],
            "killed": 1, "survivors": [r["mutant"] for r in res if not r["killed"]]}


def _git(root: pathlib.Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@x"}
    return subprocess.run(["git", "-C", str(root), "-c", "commit.gpgsign=false", *args], check=True,
                          capture_output=True, text=True, env=env).stdout.strip()


class Toy:
    def __init__(self, root: pathlib.Path):
        self.root = root
        self.files = dict(FILES)
        self.harness = harness()
        self.entries = {t: entry(self.files, t, WIN_TAIL if t in impact.WINDOWS_CLAIM else POSIX_TAIL) for t in TARGETS}
        self.extra: dict[str, bytes] = {}
        root.mkdir(parents=True, exist_ok=True)
        _git(root, "init", "-q")

    def edit(self, rel: str, old: str, new: str) -> None:
        assert old in self.files[rel], (rel, old)
        self.files[rel] = self.files[rel].replace(old, new, 1)

    def commit(self) -> str:
        record = {"record": "toy", "tool": impact.MUTATION_REL,
                  "targets": [self.entries[t] for t in sorted(self.entries)]}
        out = {**{k: v.encode() for k, v in self.files.items()}, impact.MUTATION_REL: self.harness.encode(),
               RECORD: (json.dumps(record, indent=1) + "\n").encode(), **self.extra}
        for rel, data in out.items():   # files are only added or rewritten, never removed
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_bytes(data)
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "--allow-empty", "-m", "c")
        return _git(self.root, "rev-parse", "HEAD")

    def observe(self, head: str, data=None, **over) -> dict:
        """A complete, admissible O(F) for every toy kill file: every .py of its static closure loaded."""
        out = {}
        for kill in {f for k in TARGETS.values() for f in k}:
            py = sorted(p for p in S2.closure(self.root, head, (kill,)) if p.endswith(".py"))
            out[kill] = {"commit": head, "platform": "windows" if kill == "tests/v2/test_client.py" else "posix",
                         "python": PY, "witness": True, "outcome": "PASS", "opened": dict.fromkeys(py, "load"),
                         "loaded": py, "listed": [], "listed_by": {}, "lost": 0, "unparsed_lines": 0,
                         "children": {"hooked": 0, "unhooked_python": 0, "other": 0}, **over}
            for p in (data or {}).get(kill, ()):
                out[kill]["opened"][p] = "data"
        return out


class Case(NamedTuple):
    base: str
    head: str
    obs: dict | None
    target: str
    state: str
    component: str


def check(classify, toy: Toy, case: Case) -> list[str]:
    """[] when `classify` gives `case.target` the expected state and component."""
    got = [s for s in classify(toy.root, case.base, case.head, observations=case.obs) if s.target == case.target]
    if len(got) != 1:
        return [f"{case.target}: {len(got)} states"]
    s = got[0]
    if (s.state, s.component) != (case.state, case.component):
        return [f"{case.target}: {s.state} ({s.component}) {s.reason!r}, wanted {case.state} ({case.component})"]
    return []


# ---- the cases (each builds its own toy; N14 runs them against an always-reuse engine)

def n1(t: Toy) -> Case:
    b = t.commit()
    t.edit("aisef2/toy.py", "return Kind.A.value - 1", "return Kind.A.value - 2")
    h = t.commit()
    return Case(b, h, t.observe(h), "aisef2/toy.py::target", "INVALIDATED", "I1")


def n2(t: Toy) -> Case:
    b = t.commit()
    t.edit("aisef2/toy.py", "return x * 2", "return x * 3")
    h = t.commit()
    return Case(b, h, t.observe(h), "aisef2/toy.py::target", "VERIFIED_REUSE", "")


def n3(t: Toy) -> Case:
    b = t.commit()
    t.edit("aisef2/util.py", "return x + 1", "return x + 1 + 0")
    h = t.commit()
    return Case(b, h, t.observe(h), "aisef2/toy.py::target", "INVALIDATED", "I2")


def n3b(t: Toy) -> Case:   # a helper only the kill test calls
    b = t.commit()
    t.edit("aisef2/toy.py", "return 7", "return 7 + 0")
    h = t.commit()
    return Case(b, h, t.observe(h), "aisef2/toy.py::target", "INVALIDATED", "I2")


def n4(t: Toy) -> Case:
    b = t.commit()
    t.edit("tests/v2/test_k.py", "self.assertEqual(toy.target(2), 3)\n        self.assertEqual(toy.called_by_test(), 7)",
           "pass")
    h = t.commit()
    return Case(b, h, None, "aisef2/toy.py::target", "INVALIDATED", "I4")


def n5(t: Toy) -> Case:
    b = t.commit()
    t.harness = harness({**TARGETS, "aisef2/toy.py::target": ["tests/v2/test_doc.py"]})
    h = t.commit()
    return Case(b, h, None, "aisef2/toy.py::target", "INVALIDATED", "I3")


def n6(t: Toy) -> Case:
    b = t.commit()
    assert "ast.Gt: ast.LtE" in t.harness
    t.harness = t.harness.replace("ast.Gt: ast.LtE", "ast.Gt: ast.Lt", 1)
    h = t.commit()
    return Case(b, h, None, "aisef2/toy.py::target", "INVALIDATED", "I5")


def n6b(t: Toy) -> Case:
    b = t.commit()
    t.edit("aisef2/kinds.py", "    B = 2\n", "    B = 2\n    C = 3\n")
    h = t.commit()
    return Case(b, h, None, "aisef2/toy.py::target", "INVALIDATED", "I5")


def _platform(t: Toy, target: str, tail: str | None) -> Case:
    t.entries[target] = entry(t.files, target, tail)
    b = t.commit()
    return Case(b, b, None, target, *(("INVALIDATED", "I6") if tail is not None else ("UNRESOLVED", "I6")))


def n7a_windows_for_posix(t: Toy) -> Case:
    return _platform(t, "aisef2/toy.py::target", WIN_TAIL)


def n7a_posix_for_windows(t: Toy) -> Case:
    return _platform(t, "aisef2/app/client.py::_is_gone", POSIX_TAIL)


def n7c(t: Toy) -> Case:
    e = t.entries["aisef2/toy.py::target"]
    t.entries["aisef2/toy.py::target"] = {k: e[k] for k in ("target", "kill_tests", "source_sha256", "mutants")} | {
        "killed": 1, "survivors": [], "results": [{"mutant": "L1 a", "killed": True}]}
    b = t.commit()
    return Case(b, b, None, "aisef2/toy.py::target", "UNRESOLVED", "I6")


def n7d_separators(t: Toy) -> Case:
    return _platform(t, "aisef2/toy.py::target", POSIX_TAIL + WIN_TAIL)


def n7d_flavors(t: Toy) -> Case:
    return _platform(t, "aisef2/toy.py::target", POSIX_TAIL + HOMEBREW + USRLIB)


def n7e(t: Toy) -> Case:   # fixture paths only, no frame: no evidence
    c = _platform(t, "aisef2/toy.py::target", "AssertionError: 'C:\\Users\\x\\run1' != '<run>/tmp/<mkdtemp>/home/.config'\n")
    return c._replace(state="UNRESOLVED")


def n7f(t: Toy) -> Case:   # a worker history whose log is not the bytes it recorded: W refused
    e = entry(t.files, "aisef2/toy.py::target", None)
    t.entries["aisef2/toy.py::target"] = e
    w = "closure-evidence/v2/x/mutation-workers/w1"
    rec = (json.dumps({"targets": [e]}) + "\n").encode()
    log = ("MUTANT " + HOMEBREW).encode()
    t.extra = {f"{w}.log": log, f"{w}.record.json": rec,
               f"{w}.history.json": json.dumps({"log": {"path": f"{w}.log", "sha256": "0" * 64},
                                                "record": {"path": f"{w}.record.json", "sha256": impact._sha(rec)}}).encode()}
    b = t.commit()
    return Case(b, b, None, "aisef2/toy.py::target", "UNRESOLVED", "I6")


def n7g(t: Toy) -> Case:   # shares a tree_sha256 with a linux entry, no evidence of its own
    t.entries["aisef2/util.py::inc"] = entry(t.files, "aisef2/util.py::inc", POSIX_TAIL + USRLIB)
    t.entries["aisef2/toy.py::target"] = entry(t.files, "aisef2/toy.py::target", None)
    b = t.commit()
    return Case(b, b, None, "aisef2/toy.py::target", "UNRESOLVED", "I6")


def n8(t: Toy) -> Case:
    t.entries["aisef2/toy.py::target"] = e = entry(t.files, "aisef2/toy.py::target", survivor=True)
    b = t.commit()
    k = e["results"][0]
    e = json.loads(json.dumps(e))
    e["results"][1] = {**k, "mutant": "L2 b"}
    e.update(killed=2, survivors=[])
    t.entries["aisef2/toy.py::target"] = e
    h = t.commit()
    return Case(b, h, None, "aisef2/toy.py::target", "INVALIDATED", "I7")


def n9_table(t: Toy) -> Case:   # the target added to mutation.py's Option C table; the pinned ruling intact
    t.extra = {impact.RULING_REL: (ROOT / impact.RULING_REL).read_bytes()}
    t.harness = harness(extra="VERIFIED_REUSE = {'aisef2/toy.py::target': '" + "0" * 64 + "'}\n")
    t.entries["aisef2/toy.py::target"]["source_sha256"] = "f" * 64
    b = t.commit()
    return Case(b, b, None, "aisef2/toy.py::target", "INVALIDATED", "I8")


def n9_ruling(t: Toy) -> Case:   # the ruling file altered to cover the target
    doc = json.loads((ROOT / impact.RULING_REL).read_bytes())
    doc["disposition"]["VERIFIED_REUSE"]["aisef2/toy.py::target"] = dict(next(iter(doc["disposition"]["VERIFIED_REUSE"].values())))
    t.extra = {impact.RULING_REL: json.dumps(doc).encode()}
    t.harness = harness(extra="VERIFIED_REUSE = {'aisef2/toy.py::target': '" + "0" * 64 + "'}\n")
    t.entries["aisef2/toy.py::target"]["source_sha256"] = doc["source_transition"]["measured_source_sha256"]
    b = t.commit()
    return Case(b, b, None, "aisef2/toy.py::target", "INVALIDATED", "I8")


def n10(t: Toy) -> Case:
    h = t.commit()
    return Case("0" * 40, h, None, "aisef2/toy.py::target", "UNRESOLVED", "basis")


def n13_data_reader(t: Toy) -> Case:   # a comment appended; the kill file reads the module as data
    b = t.commit()
    t.files["aisef2/toy.py"] += "# note\n"
    h = t.commit()
    return Case(b, h, t.observe(h, {"tests/v2/test_k.py": ["aisef2/toy.py"]}), "aisef2/util.py::inc", "INVALIDATED", "R2")


def n13b(t: Toy) -> Case:
    b = t.commit()
    t.edit("aisef2/toy.py", "from aisef2.kinds import Kind\n", "from aisef2.kinds import Kind\nfrom enum import Enum\n")
    t.files["aisef2/toy.py"] += "\n\nclass New(Enum):\n    X = 1\n"
    h = t.commit()
    return Case(b, h, t.observe(h), "aisef2/util.py::inc", "INVALIDATED", "R6")


def n18(t: Toy) -> Case:
    b = t.commit()
    t.files["aisef2/util.py"] = "import sys\n\nsys.setrecursionlimit(60)\n\n\n" + t.files["aisef2/util.py"]
    h = t.commit()
    return Case(b, h, t.observe(h), "aisef2/toy.py::target", "INVALIDATED", "R6")


def n21(t: Toy) -> Case:
    b = t.commit()
    t.files["tests/v2/zz/__init__.py"] = "raise SystemExit(1)\n"
    h = t.commit()
    return Case(b, h, t.observe(h), "aisef2/toy.py::target", "INVALIDATED", "R4")


def n21b(t: Toy) -> Case:
    b = t.commit()
    t.files["tests/v2/p9/__init__.py"] = ""
    t.files["tests/v2/p9/test_k.py"] = "import unittest\n\n\nclass T(unittest.TestCase):\n    def test_x(self):\n        self.fail()\n"
    h = t.commit()
    return Case(b, h, t.observe(h), "aisef2/toy.py::target", "INVALIDATED", "R4")


def n22(t: Toy) -> Case:
    b = t.commit()
    t.files["aisef2/toy/__init__.py"] = ""
    h = t.commit()
    return Case(b, h, t.observe(h), "aisef2/toy.py::target", "INVALIDATED", "R5")


def n23(t: Toy) -> Case:
    b = t.commit()
    t.edit("aisef2/dyn.py", "return 2", "return 3")
    h = t.commit()
    return Case(b, h, t.observe(h), "aisef2/dyn.py::pick", "INVALIDATED", "R8")


def n31(t: Toy) -> Case:
    b = t.commit()
    t.files["docs/v2.1/schema.json"] = '{"a": 2}\n'
    h = t.commit()
    return Case(b, h, t.observe(h, {"tests/v2/test_doc.py": ["docs/v2.1/schema.json"]}), "aisef2/doc.py::keys",
                "INVALIDATED", "R2")


def n33(t: Toy) -> Case:
    b = t.commit()
    t.harness = t.harness.replace("TIMEOUT = 900", "TIMEOUT = 901", 1)
    h = t.commit()
    return Case(b, h, None, "aisef2/toy.py::target", "INVALIDATED", "I9")


def n33b(t: Toy) -> Case:
    b = t.commit()
    t.harness = t.harness.replace("def _confirmed(r: dict) -> bool:\n", "def _confirmed(r: dict) -> bool:\n    # edited\n", 1)
    h = t.commit()
    return Case(b, h, None, "aisef2/util.py::inc", "INVALIDATED", "I9")


def no_observation(t: Toy) -> Case:   # N2's edit with no observation: R1 cannot be excluded
    c = n2(t)
    return c._replace(obs=None, state="INVALIDATED", component="R1")


def wrong_tree_observation(t: Toy) -> Case:   # R0: an observation of another tree is not admissible
    c = n2(t)
    return c._replace(obs=t.observe(c.base), state="UNRESOLVED", component="R0")


def unobserved_child(t: Toy) -> Case:   # R1 with an observation that has an unhooked child
    c = n2(t)
    return c._replace(obs=t.observe(c.head, children={"hooked": 0, "unhooked_python": 1, "other": 0}),
                      state="INVALIDATED", component="R1")


NEGATIVE = [n1, n3, n3b, n4, n5, n6, n6b, n7a_windows_for_posix, n7a_posix_for_windows, n7c, n7d_separators, n7d_flavors,
            n7e, n7f, n7g, n8, n9_table, n9_ruling, n10, n13_data_reader, n13b, n18, n21, n21b, n22, n23, n31, n33, n33b,
            no_observation, wrong_tree_observation, unobserved_child]


class ImpactTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.toy = Toy(pathlib.Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def run_case(self, fn) -> impact.State:
        case = fn(self.toy)
        self.assertEqual(check(impact.classify, self.toy, case), [])
        return next(s for s in impact.classify(self.toy.root, case.base, case.head, observations=case.obs)
                    if s.target == case.target)

    def test_n1_target_slice(self):
        self.run_case(n1)

    def test_n2_unreferenced_helper(self):
        s = self.run_case(n2)
        self.assertEqual(s.evidence["unreferenced_changes"], ["aisef2/toy.py::helper"])
        self.assertEqual(s.basis.split("@")[0], "v2.2.0-accepted")
        self.assertEqual(s.compared, ["I7", "I6", "I1", "I3", "I4", "I5", "I9"])
        # red-before: today's whole-file rule calls it stale
        self.assertNotEqual(M.source_digest(self.toy.files["aisef2/toy.py"]),
                            self.toy.entries["aisef2/toy.py::target"]["source_sha256"])

    def test_n2_without_observation_is_invalidated(self):
        s = self.run_case(no_observation)
        self.assertIn("R1 cannot be excluded", s.reason)

    def test_n3_referenced_helper(self):
        self.run_case(n3)

    def test_n3_helper_the_kill_test_calls(self):
        self.run_case(n3b)

    def test_n4_weakened_kill_test(self):
        self.run_case(n4)
        # red-before: today's verdict on the same record at the same tree finds nothing
        self.assertEqual(M.target_problems(self.toy.entries["aisef2/toy.py::target"], self.toy.root), [])

    def test_n5_dropped_killer(self):
        self.run_case(n5)

    def test_n6_generator_operator(self):
        self.run_case(n6)

    def test_n6_enum_members(self):
        self.run_case(n6b)

    def test_n7a(self):
        self.run_case(n7a_windows_for_posix)

    def test_n7a_windows_claim(self):
        self.run_case(n7a_posix_for_windows)

    def test_n7b_darwin_passes(self):
        t = self.toy
        t.entries["aisef2/toy.py::target"] = entry(t.files, "aisef2/toy.py::target", POSIX_TAIL + HOMEBREW)
        b = t.commit()
        s = next(x for x in impact.classify(t.root, b, b) if x.target == "aisef2/toy.py::target")
        self.assertEqual((s.state, s.evidence["platform"]["family"], s.evidence["platform"]["flavor"]),
                         ("VERIFIED_REUSE", "posix", "darwin"))

    def test_n7c_rowless(self):
        self.run_case(n7c)

    def test_n7d(self):
        self.run_case(n7d_separators)

    def test_n7d_flavors(self):
        self.run_case(n7d_flavors)

    def test_n7e_fixture_paths(self):
        self.run_case(n7e)
        t = self.toy   # with a frame of its own: posix, and the fixture paths prove no flavor
        t.entries["aisef2/toy.py::target"] = entry(t.files, "aisef2/toy.py::target",
                                                   POSIX_TAIL + "'C:\\Users\\x\\run1' != '<run>/tmp/<mkdtemp>/home/.config'\n")
        b = t.commit()
        s = next(x for x in impact.classify(t.root, b, b) if x.target == "aisef2/toy.py::target")
        self.assertEqual((s.state, s.evidence["platform"]["flavor"]), ("VERIFIED_REUSE", None))

    def test_n7f_worker(self):
        self.run_case(n7f)
        t = self.toy   # the same history with the right digest: the worker's darwin marker decides
        h = json.loads(t.extra[next(k for k in t.extra if k.endswith(".history.json"))])
        h["log"]["sha256"] = impact._sha(t.extra[h["log"]["path"]])
        t.extra[next(k for k in t.extra if k.endswith(".history.json"))] = json.dumps(h).encode()
        b = t.commit()
        s = next(x for x in impact.classify(t.root, b, b) if x.target == "aisef2/toy.py::target")
        self.assertEqual((s.state, s.evidence["platform"]["family"], s.evidence["platform"]["flavor"]),
                         ("VERIFIED_REUSE", "posix", "darwin"))
        self.assertTrue(s.evidence["platform"]["by"].startswith("W:"))

    def test_n7g_co_occurrence(self):
        self.run_case(n7g)

    def test_n8_tamper(self):
        self.run_case(n8)

    def test_n9_table(self):
        self.assertIn("not in the pinned ruling's scope", self.run_case(n9_table).reason)

    def test_n9_ruling(self):
        self.assertIn("not the pinned", self.run_case(n9_ruling).reason)

    def test_n10_missing_basis(self):
        self.run_case(n10)

    def test_n10_shallow(self):
        t = self.toy
        t.commit()
        b = t.commit()
        t.edit("aisef2/toy.py", "return x * 2", "return x * 3")
        t.commit()
        clone = pathlib.Path(self._tmp.name) / "shallow"
        subprocess.run(["git", "clone", "-q", "--depth", "2", f"file://{t.root}", str(clone)], check=True)
        states = impact.classify(clone, b, "HEAD")
        self.assertTrue(states)
        self.assertEqual({(s.state, s.component) for s in states}, {("UNRESOLVED", "basis")})
        self.assertIn("shallow", states[0].reason)

    def test_n13_comment(self):
        t = self.toy
        b = t.commit()
        t.files["aisef2/toy.py"] += "# note\n"
        h = t.commit()
        for s in impact.classify(t.root, b, h, observations=t.observe(h)):   # R6/R7 fire on nothing
            self.assertEqual(s.state, "VERIFIED_REUSE", s)
        self.toy = Toy(pathlib.Path(self._tmp.name) / "again")
        self.run_case(n13_data_reader)

    def test_n13b_import_and_class(self):
        self.run_case(n13b)
        s = next(x for x in impact.classify(self.toy.root, *_last(self.toy)) if x.target == "aisef2/toy.py::target")
        self.assertEqual((s.state, s.component), ("INVALIDATED", "I1"))

    def test_n18_import_time(self):
        self.run_case(n18)

    def test_n21_discovery(self):
        self.run_case(n21)

    def test_n21_discovery_basename(self):
        self.run_case(n21b)

    def test_n22_resolution(self):
        self.run_case(n22)

    def test_n23_computed_name(self):
        self.run_case(n23)
        # red-before: by name alone, tier S would clear _do_b (its def is its only occurrence)
        self.assertEqual(impact.name_refs(self.toy.files["aisef2/dyn.py"])["_do_b"], 1)
        self.assertTrue(impact.dynamic_sites(self.toy.files["aisef2/dyn.py"], "aisef2/dyn.py"))

    def test_n31_non_code_root(self):
        self.run_case(n31)
        b, h = _last(self.toy)
        self.assertIn("docs/v2.1/schema.json", impact.kill_closure(self.toy.root, b, h, "tests/v2/test_doc.py"))
        # red-before: the s2 closure resolves literals only to tests/ paths
        self.assertNotIn("docs/v2.1/schema.json", S2.closure(self.toy.root, h, ("tests/v2/test_doc.py",)))

    def test_n32_dirty_tree(self):
        t = self.toy
        b = t.commit()
        h = t.commit()
        (t.root / "aisef2/toy.py").write_text(t.files["aisef2/toy.py"] + "# uncommitted\n", encoding="utf-8")
        states = impact.classify(t.root, b, h)
        self.assertEqual({(s.state, s.component) for s in states}, {("UNRESOLVED", "dirty")})
        self.assertEqual(len(states), len(TARGETS))
        (t.root / "aisef2/toy.py").write_text(t.files["aisef2/toy.py"], encoding="utf-8")
        (t.root / "aisef2/untracked.py").write_text("", encoding="utf-8")
        self.assertEqual({s.component for s in impact.classify(t.root, b, h)}, {"dirty"})

    def test_n33_runner_setting(self):
        self.run_case(n33)
        b, h = _last(self.toy)
        self.assertEqual({(s.state, s.component) for s in impact.classify(self.toy.root, b, h)}, {("INVALIDATED", "I9")})

    def test_n33_confirmed_code(self):
        self.run_case(n33b)

    def test_r0_and_r1_need_admissible_complete_observations(self):
        self.run_case(wrong_tree_observation)
        self.toy = Toy(pathlib.Path(self._tmp.name) / "again")
        self.run_case(unobserved_child)

    def test_unchanged_base_is_reused(self):
        b = self.toy.commit()
        states = impact.classify(self.toy.root, b, b)
        self.assertEqual({s.state for s in states}, {"VERIFIED_REUSE"})
        self.assertEqual(len(states), len(TARGETS))
        self.assertNotIn("MEASURED", {s.state for s in states})   # a legacy entry is never MEASURED

    def test_n14_always_reuse_engine_is_rejected(self):
        def stub(root, base="", head="", *, observations=None):
            return [impact.State(t, "VERIFIED_REUSE") for t in TARGETS]
        failed = []
        for fn in NEGATIVE:
            with tempfile.TemporaryDirectory() as d:
                toy = Toy(pathlib.Path(d))
                case = fn(toy)
                self.assertNotEqual(case.state, "VERIFIED_REUSE")
                failed += [fn.__name__] if check(stub, toy, case) else []
        self.assertEqual(failed, [fn.__name__ for fn in NEGATIVE])

    def test_option_c_honoured_on_the_real_repository(self):
        """I8 positive: the pinned ruling covers a real Option C entry at v2.2.0 (skipped without that history)."""
        base = impact._rev(ROOT, impact.BASE)
        if base is None or impact.S2.blob(ROOT, base, impact.RULING_REL) is None:
            self.skipTest("v2.2.0 history not available")
        name = "aisef2/app/bundle_cli.py::APPROVAL_KEY"
        rec = json.loads(impact._blob(ROOT, base, M.RECORDS["V2.1"]))
        e = next(t for t in rec["targets"] if t["target"] == name)
        with tempfile.TemporaryDirectory() as d:
            R = impact.SD.Rev(ROOT, base, pathlib.Path(d))
            ctx = impact._Ctx(ROOT, R, R, None)
            src = R.text(name.split("::")[0])
            plat = {"family": "posix", "flavor": None}
            self.assertIsNone(ctx.option_c(name, e, src, plat))
            self.assertIsNotNone(ctx.option_c(name, {**e, "tree_sha256": "0" * 64}, src, plat))
            self.assertIsNotNone(ctx.option_c(name, e, src, {"family": "posix", "flavor": "darwin"}))


def _last(toy: Toy) -> tuple[str, str]:
    log = _git(toy.root, "log", "--format=%H", "-2").split()
    return log[1], log[0]


if __name__ == "__main__":
    unittest.main()
