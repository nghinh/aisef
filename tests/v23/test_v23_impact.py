"""validation/v23/impact.py (F5 static impact engine) on toy git repositories: the W1-DESIGN §9 negatives N1-N33, the
adversarial-review regressions D1-D5 and the re-review's A1/D4/I4/F2 (each mirrors the reviewer's probe), and N14: every rule is load-bearing — with
that one rule switched off, at least one negative case becomes VERIFIED_REUSE, while the intact engine keeps every
negative case non-reuse. Each toy holds the whole of the real validation/v2/mutation.py with toy tables appended (so
the toy's runner is the real one and validation/v23/observe.py can run it), toy targets and one committed record.
Observations are observe.py records derived from a synthetic witness written here (`Toy.observe`): R0 verifies and
binds them exactly as it does a recorded one. Nothing is measured; no kill test runs. Not a kill file (tests/v23 is
outside every mutation.COPY root: Amendment A2)."""

from __future__ import annotations

import contextlib
import functools
import io
import json
import os
import pathlib
import posixpath
import subprocess
import sys
import tempfile
import unittest
import unittest.case
from typing import NamedTuple
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.qualification import s2_mutation_record as S2  # noqa: E402
from validation.qualification import v21_snapshot_delta as SD  # noqa: E402
from validation.v2 import mutation as M  # noqa: E402
from validation.v23 import impact  # noqa: E402
from validation.v23 import observe as OBS  # noqa: E402

REAL = (ROOT / impact.MUTATION_REL).read_text(encoding="utf-8")
#: what a toy commits besides its own files: the real runner's helper and the real recorder, byte for byte
RUNNER_FILES = {rel: (ROOT / rel).read_bytes() for rel in ("validation/v2/cleanup_authority.py", OBS.TOOL)}
RECORD = "closure-evidence/v2/T-MUTATION.json"
TGT, INC, DOC, DYN = "aisef2/toy.py::target", "aisef2/util.py::inc", "aisef2/doc.py::keys", "aisef2/dyn.py::pick"
K = "tests/v2/test_k.py"
TARGETS = {
    TGT: [K],
    INC: [K],
    "aisef2/app/client.py::_is_gone": ["tests/v2/test_client.py"],
    DYN: ["tests/v2/test_dyn.py"],
    DOC: ["tests/v2/test_doc.py"],
}
PY = f"{sys.version_info.major}.{sys.version_info.minor}"
POSIX_TAIL = 'Traceback (most recent call last):\n  File "<tree>/aisef2/toy.py", line 7, in target\nAssertionError\n'
WIN_TAIL = 'Traceback (most recent call last):\n  File "<tree>\\aisef2\\app\\client.py", line 2, in _is_gone\nAssertionError\n'
#: a frame of this interpreter's own unittest: the default entries carry this host's flavor and python, as an entry
#: measured here would (R0 binds an observation to the entry's own flavor and interpreter)
#: ILLUSTRATIVE stand-in for the linux agent's fixture fix: this host's flavor, linux where it has none (Windows)
FLAVOR = OBS.identity()["platform"]["flavor"] or "linux"
LOCAL = (f'  File "/opt/homebrew/lib/python{PY}/unittest/case.py", line 58, in run\n' if FLAVOR == "darwin"
         else f'  File "/usr/lib/python{PY}/unittest/case.py", line 58, in run\n')
FLAVORED = POSIX_TAIL + LOCAL
WIN_FLAVORED = WIN_TAIL + f'  File "C:\\Python{sys.version_info.major}{sys.version_info.minor}\\Lib\\unittest\\case.py", line 58\n'
HOMEBREW = '  File "/opt/homebrew/Cellar/python@3.14/3.14.7/lib/python3.14/unittest/case.py", line 58, in run\n'
USRLIB = '  File "/usr/lib/python3.12/unittest/case.py", line 58, in run\n'
RULES = ("I7", "I6", "I1", "I8", "I3", "I4", "I5", "I9", "R4", "R5", "R6", "R0", "D2", "R1", "R2", "R3", "R8", "I2")

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
    K: "import unittest\n\nfrom aisef2 import toy, util\n\n\nclass T(unittest.TestCase):\n"
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
    """The toy's validation/v2/mutation.py: the real one, its tables replaced by the toy's (appended: the last binding
    wins), so the generator, the I9 segments and the runner are the real ones."""
    tables = (f"\n\n# ---- the toy's tables\nRECORDS = {{'T': {RECORD!r}}}\nPHASE_TARGETS = {{'T': {targets or TARGETS!r}}}\n"
              "TARGETS = {t: k for ts in PHASE_TARGETS.values() for t, k in ts.items()}\n"
              f"SUPERSEDED = {{}}\nV21_RETIRED = ()\nV21_TARGETS = {{}}\nVERIFIED_REUSE = {{}}\nCOPY = {M.COPY!r}\n{extra}")
    return REAL + tables


def entry(files: dict, target: str, tail: str | None = FLAVORED, survivor: bool = False, kill=None) -> dict:
    """A runner-2 result with every mutant KILLED by a bracketed kill (mutation._confirmed holds), measured on
    `files`; `survivor` adds a second, SURVIVED mutant."""
    kill = kill or TARGETS[target]
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
                          capture_output=True, text=True, encoding="utf-8", env=env).stdout.strip()


class Toy:
    def __init__(self, root: pathlib.Path):
        self.root = root   # its parent holds what the toy writes beside it (observation witnesses)
        self.files = dict(FILES)
        self.targets = dict(TARGETS)
        self.harness = harness()
        self.reentry()
        self.extra: dict[str, bytes] = {}
        root.mkdir(parents=True, exist_ok=True)
        _git(root, "init", "-q")
        # a toy commits the bytes it writes: a host's core.autocrlf=true (the windows runner's system default) would
        # store RUNNER_FILES' CRLF checkout as LF, and the toy's recorder would no longer be the module that runs
        _git(root, "config", "core.autocrlf", "false")

    def reentry(self) -> None:
        self.entries = {t: entry(self.files, t, WIN_FLAVORED if t in impact.WINDOWS_CLAIM else FLAVORED) for t in TARGETS}

    def set_targets(self, targets: dict) -> None:
        self.targets = targets
        self.harness = harness(targets)

    def edit(self, rel: str, old: str, new: str) -> None:
        assert old in self.files[rel], (rel, old)
        self.files[rel] = self.files[rel].replace(old, new, 1)

    def commit(self) -> str:
        record = {"record": "toy", "tool": impact.MUTATION_REL,
                  "targets": [self.entries[t] for t in sorted(self.entries)]}
        out = {**{k: v.encode() for k, v in self.files.items()}, impact.MUTATION_REL: self.harness.encode(),
               RECORD: (json.dumps(record, indent=1) + "\n").encode(), **RUNNER_FILES, **self.extra}
        for rel, data in out.items():   # files are only added or rewritten, never removed
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_bytes(data)
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "--allow-empty", "-m", "c")
        return _git(self.root, "rev-parse", "HEAD")

    def observe(self, head: str, data=None, opened=None, loaded=None, **over) -> dict:
        """An observe.py record of every toy kill file, derived (observe.finish) from a synthetic witness: complete and
        admissible unless `over` says otherwise — every .py of its static closure load-opened and executed, `data`
        {kill: [paths read as data]}, `opened` {kill: {path: tag}}, `loaded` {kill: [more executed files]}; `over`:
        commit, platform, python, outcome, witness (False: none), outside_tree, lost, unparsed_lines, os_trace,
        children {hooked, unhooked_python, other}, listed, listed_by."""
        out = {}
        for kill in sorted({f for k in self.targets.values() for f in k}):
            py = sorted(p for p in S2.closure(self.root, over.get("commit", head), (kill,)) if p.endswith(".py"))
            ops = {**dict.fromkeys(py, "load"), **dict.fromkeys((data or {}).get(kill, ()), "data"),
                   **(opened or {}).get(kill, {})}
            out[kill] = synthetic(self, head, kill, ops, [*py, kill, *(loaded or {}).get(kill, ())], over)
        return out


EXECVE = 'execve("/usr/bin/python3", ["python3"], 0x1 /* 1 vars */) = 0\n'   # a traced task's interpreter image
RUNNER_ENV = sorted({*(k for k in M.ENV_KEEP if k in os.environ), *M._FRESH, M.TOKEN, "PYTHONPATH", OBS.MARK})


@functools.lru_cache(maxsize=256)
def _tree(root: pathlib.Path, commit: str) -> str | None:
    return impact.tree_digest(root, commit, M.COPY, [RECORD])


def synthetic(t: Toy, head: str, kill: str, ops: dict, mods: list, over: dict) -> dict:
    """observe.finish() of a witness written here as the recorder would have written it for `kill` at `head`."""

    def _esc(s: str) -> str:   # the hook's own line escaping (read_set HOOK / observe HOOK)
        return s.replace("\\", "\\\\").replace("\n", "\\n").replace("\t", "\\t")

    commit = over.get("commit", head)
    w = pathlib.Path(tempfile.mkdtemp(prefix="obs-", dir=t.root.parent))
    tree = w / "tree"   # the path the run's events name; nothing runs there
    ident = OBS.identity()
    fam = over.get("platform") or ("windows" if kill == "tests/v2/test_client.py" else "posix")
    plat = {**ident["platform"], "family": fam, "flavor": None if fam == "windows" else FLAVOR}
    trace = bool(over.get("os_trace"))
    blob = impact._blob(t.root, commit, kill) or b""
    man = {"format": OBS.FORMAT, "tool": OBS.TOOL, "commit": commit, "tree": str(tree), "checkout": str(t.root),
           "tree_sha256": _tree(t.root, commit),
           "kill_file": {"path": kill, "sha256": impact._sha(blob)}, "module": kill[len("tests/"):-3].replace("/", "."),
           "runner_sha256": impact._sha(impact._blob(t.root, commit, impact.MUTATION_REL) or b""),
           "observe_sha256": OBS.own_sha256(), "backend": "strace" if trace else "audit",
           "hook": {"events": str(w / "hook"), "roots": list(OBS.RS._roots(tree)), "nonce": "0" * 24},
           "tools": {"strace": "strace -- version 6.8" if trace else None, "git": "git version 2",
                     "strace_events": OBS.STRACE_EVENTS if trace else None},
           "platform": plat, "python": over.get("python", ident["python"]), "toolchain": ident["toolchain"],
           "env": dict.fromkeys(RUNNER_ENV, "0" * 64),
           "row": {"outcome": over.get("outcome", "PASS"), "exit": 0, "ran": 1, "pid": 100}}
    (w / "hook").mkdir()
    (w / OBS.SITE).write_text(OBS.hook_source(w / "hook", man["hook"]["roots"], man["hook"]["nonce"]), encoding="utf-8")
    (w / "manifest.json").write_text(json.dumps(man, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    (w / "log.txt").write_text(f"test_x ({man['module']}.T.test_x) ... ok\n\nRan 1 test in 0.001s\n\nOK\n", encoding="utf-8")
    # OBS._esc, exactly as the hook writes: a native tree path may hold "\t"-like byte pairs (every Windows runner
    # path does — D:\a\…\tree), and an unescaped one is unescaped/split by the parser, so the kill file goes unseen
    at = {p: _esc(posixpath.normpath(posixpath.join(str(tree), p))) for p in {*ops, *mods}}
    lines = ["S\t100\t1\t['-m', 'unittest']"] + [f"o\t{tag}\t{at[p]}" for p, tag in sorted(ops.items())] + [
        f"m\t{at[p]}" for p in sorted(set(mods))]
    listed_by = over.get("listed_by") or {}
    for d in over.get("listed") or []:
        callers = [_esc(posixpath.normpath(posixpath.join(str(tree), c))) for c in listed_by.get(d, [kill])]
        lines.append("\t".join(["l", "run", _esc(posixpath.normpath(posixpath.join(str(tree), d))), *callers]))
    kids = {"hooked": 0, "unhooked_python": 0, "other": 0, **(over.get("children") or {})}
    lines += ["C\tsubprocess.Popen\t1\t0\t['python3']"] * kids["unhooked_python"]
    lines += ["C\tsubprocess.Popen\t0\t0\t['wc']"] * kids["other"]
    lines += ["C\tsubprocess.Popen\t1\t1\t['python3']"] * kids["hooked"]
    if over.get("outside_tree"):
        lines.append(f"o\tdata\t{_esc(str(t.root / 'aisef2' / 'toy.py'))}")
    lines += [f"L\t{over['lost']}"] if over.get("lost") else []
    lines += ["?garbage"] * (over.get("unparsed_lines") or 0)
    # newline="\n": the hook and strace write LF on every host (a text-mode write on Windows would add a CR)
    (w / "hook" / "100-root.ev").write_text("\n".join([*lines, "E\t0"]) + "\n", encoding="utf-8", newline="\n")
    for i in range(kids["hooked"]):
        (w / "hook" / f"{101 + i}-kid.ev").write_text(f"S\t{101 + i}\t100\t[]\nE\t0\n", encoding="utf-8", newline="\n")
    if trace:
        (w / "strace").mkdir()
        forks = "".join(f"vfork() = {101 + i}\n" for i in range(kids["hooked"]))
        (w / "strace" / "tr.100").write_text(EXECVE + forks + "+++ exited with 0 +++\n", encoding="utf-8", newline="\n")
        for i in range(kids["hooked"]):
            (w / "strace" / f"tr.{101 + i}").write_text(EXECVE + "+++ exited with 0 +++\n", encoding="utf-8", newline="\n")
    rec = OBS.finish(w)
    if over.get("witness") is False:
        rec.pop("witness")
    return rec


class Case(NamedTuple):
    base: str
    head: str
    obs: dict | None
    target: str
    state: str
    component: str


def state_of(toy: Toy, case: Case) -> impact.State:
    got = [s for s in impact.classify(toy.root, case.base, case.head, observations=case.obs) if s.target == case.target]
    assert len(got) == 1, (case.target, got)
    return got[0]


def check(toy: Toy, case: Case) -> list[str]:
    """[] when the engine gives `case.target` the expected state and component."""
    s = state_of(toy, case)
    if (s.state, s.component) != (case.state, case.component):
        return [f"{case.target}: {s.state} ({s.component}) {s.reason!r}, wanted {case.state} ({case.component})"]
    return []


def rowless(t: Toy, target: str = TGT) -> None:
    e = t.entries[target]
    t.entries[target] = {k: e[k] for k in ("target", "kill_tests", "source_sha256", "mutants")} | {
        "killed": 1, "survivors": [], "results": [{"mutant": "L1 a", "killed": True}]}


def add_test(t: Toy, rel: str, before: str, method: str, imports: str = "") -> None:
    """A test method in `rel`'s class T, placed before the method `before`, plus module imports."""
    if imports:
        t.edit(rel, "import unittest\n", imports + "import unittest\n")
    t.edit(rel, f"    def {before}(self):\n", method + f"\n    def {before}(self):\n")


# ---- the cases (each builds its own toy; N14 runs every negative case once more with its own rule switched off)

def n1(t: Toy) -> Case:
    b = t.commit()
    t.edit("aisef2/toy.py", "return Kind.A.value - 1", "return Kind.A.value - 2")
    h = t.commit()
    return Case(b, h, t.observe(h), TGT, "INVALIDATED", "I1")


def n1_comment(t: Toy) -> Case:   # I1 is exact text: a comment inside the target is a slice change
    b = t.commit()
    t.edit("aisef2/toy.py", "    if x > 1:\n", "    if x > 1:  # the boundary\n")
    h = t.commit()
    return Case(b, h, t.observe(h), TGT, "INVALIDATED", "I1")


def n2(t: Toy) -> Case:
    b = t.commit()
    t.edit("aisef2/toy.py", "return x * 2", "return x * 3")
    h = t.commit()
    return Case(b, h, t.observe(h), TGT, "VERIFIED_REUSE", "")


def n3(t: Toy) -> Case:
    b = t.commit()
    t.edit("aisef2/util.py", "return x + 1", "return x + 1 + 0")
    h = t.commit()
    return Case(b, h, t.observe(h), TGT, "INVALIDATED", "I2")


def n3b(t: Toy) -> Case:   # a helper only the kill test calls
    b = t.commit()
    t.edit("aisef2/toy.py", "return 7", "return 7 + 0")
    h = t.commit()
    return Case(b, h, t.observe(h), TGT, "INVALIDATED", "I2")


def n4(t: Toy) -> Case:
    b = t.commit()
    t.edit(K, "self.assertEqual(toy.target(2), 3)\n        self.assertEqual(toy.called_by_test(), 7)", "pass")
    h = t.commit()
    return Case(b, h, t.observe(h), TGT, "INVALIDATED", "I4")


def i4_comment(t: Toy) -> Case:   # §2.2: exact segment text, not ast.dump
    b = t.commit()
    t.edit(K, "self.assertEqual(toy.target(2), 3)\n", "self.assertEqual(toy.target(2), 3)  # the same check\n")
    h = t.commit()
    return Case(b, h, t.observe(h), TGT, "INVALIDATED", "I4")


def n5(t: Toy) -> Case:
    b = t.commit()
    t.set_targets({**TARGETS, TGT: ["tests/v2/test_doc.py"]})
    h = t.commit()
    return Case(b, h, t.observe(h), TGT, "INVALIDATED", "I3")


def n6(t: Toy) -> Case:
    b = t.commit()
    assert "ast.Gt: ast.LtE" in t.harness
    t.harness = t.harness.replace("ast.Gt: ast.LtE", "ast.Gt: ast.Lt", 1)
    h = t.commit()
    return Case(b, h, t.observe(h), TGT, "INVALIDATED", "I5")


def n6b(t: Toy) -> Case:
    b = t.commit()
    t.edit("aisef2/kinds.py", "    B = 2\n", "    B = 2\n    C = 3\n")
    h = t.commit()
    return Case(b, h, None, TGT, "INVALIDATED", "I5")


def _platform(t: Toy, target: str, tail: str | None) -> Case:
    t.entries[target] = entry(t.files, target, tail)
    b = t.commit()
    return Case(b, b, None, target, *(("INVALIDATED", "I6") if tail is not None else ("UNRESOLVED", "I6")))


def n7a_windows_for_posix(t: Toy) -> Case:
    return _platform(t, TGT, WIN_TAIL)


def n7a_posix_for_windows(t: Toy) -> Case:
    return _platform(t, "aisef2/app/client.py::_is_gone", POSIX_TAIL)


def n7c(t: Toy) -> Case:
    rowless(t)
    b = t.commit()
    return Case(b, b, None, TGT, "UNRESOLVED", "I6")


def n7d_separators(t: Toy) -> Case:
    return _platform(t, TGT, POSIX_TAIL + WIN_TAIL)


def n7d_flavors(t: Toy) -> Case:
    return _platform(t, TGT, POSIX_TAIL + HOMEBREW + USRLIB)


def n7e(t: Toy) -> Case:   # fixture paths only, no frame: no evidence
    c = _platform(t, TGT, "AssertionError: 'C:\\Users\\x\\run1' != '<run>/tmp/<mkdtemp>/home/.config'\n")
    return c._replace(state="UNRESOLVED")


def _history(t: Toy, w: str, log: bytes, rec_path: str, rec: bytes, log_sha: str | None = None) -> None:
    t.extra.update({f"{w}.log": log, f"{w}.history.json": json.dumps(
        {"log": {"path": f"{w}.log", "sha256": log_sha or impact._sha(log)},
         "record": {"path": rec_path, "sha256": impact._sha(rec)}}).encode()})


def n7f(t: Toy) -> Case:   # a worker history whose log is not the bytes it recorded: W refused
    e = entry(t.files, TGT, None)
    t.entries[TGT] = e
    w = "closure-evidence/v2/x/mutation-workers/w1"
    rec = (json.dumps({"targets": [e]}) + "\n").encode()
    t.extra[f"{w}.record.json"] = rec
    _history(t, w, ("MUTANT " + HOMEBREW).encode(), f"{w}.record.json", rec, log_sha="0" * 64)
    b = t.commit()
    return Case(b, b, None, TGT, "UNRESOLVED", "I6")


def n7g(t: Toy) -> Case:   # shares a tree_sha256 with a linux entry, no evidence of its own
    t.entries[INC] = entry(t.files, INC, POSIX_TAIL + USRLIB)
    t.entries[TGT] = entry(t.files, TGT, None)
    b = t.commit()
    return Case(b, b, None, TGT, "UNRESOLVED", "I6")


FORGED = "closure-evidence/x/mutation-workers/forged"   # outside COPY: Δ stays empty
DARWIN_LOG = b'note: "/opt/homebrew/bin/python3"\n'


def d1_history_after_basis(t: Toy) -> Case:   # probe_w variant B: a sibling record committed after the basis
    rowless(t)
    b = t.commit()
    rec = (json.dumps({"targets": [t.entries[TGT]]}) + "\n").encode()
    t.extra[f"{FORGED}.record.json"] = rec
    _history(t, FORGED, DARWIN_LOG, f"{FORGED}.record.json", rec)
    h = t.commit()
    return Case(b, h, t.observe(h), TGT, "UNRESOLVED", "I6")


def d1_history_not_sibling(t: Toy) -> Case:   # probe_w variant A: the history points at the live phase record
    for k in list(t.entries):
        rowless(t, k)
    t.commit()
    _history(t, FORGED, DARWIN_LOG, RECORD, (t.root / RECORD).read_bytes())
    b = t.commit()
    return Case(b, b, t.observe(b), TGT, "UNRESOLVED", "I6")


def n8(t: Toy) -> Case:
    t.entries[TGT] = e = entry(t.files, TGT, survivor=True)
    b = t.commit()
    k = e["results"][0]
    e = json.loads(json.dumps(e))
    e["results"][1] = {**k, "mutant": "L2 b"}
    e.update(killed=2, survivors=[])
    t.entries[TGT] = e
    h = t.commit()
    return Case(b, h, t.observe(h), TGT, "INVALIDATED", "I7")


def d2_shadowed_base(t: Toy) -> Case:   # probe_ref: N8, then a tag named like the basis abbreviation, at head
    c = n8(t)
    _git(t.root, "tag", c.base[:8], c.head)
    return c._replace(base=c.base[:8], state="UNRESOLVED", component="basis")


def d2_replaced_blob(t: Toy) -> Case:   # N8, then `git replace` makes the basis record's blob read as head's
    c = n8(t)
    _git(t.root, "replace", _git(t.root, "rev-parse", f"{c.base}:{RECORD}"), _git(t.root, "rev-parse", f"{c.head}:{RECORD}"))
    return c


def d3_not_live(t: Toy) -> Case:   # probe_live: superseded by the basis's tables, made live at head
    t.harness = harness({k: v for k, v in TARGETS.items() if k != DOC}, extra=f"SUPERSEDED = {{{DOC!r}: 'U'}}\n")
    b = t.commit()
    t.harness = harness()
    h = t.commit()
    return Case(b, h, t.observe(h), DOC, "INVALIDATED", "I7")


ORDER = ('"""toy."""\nfrom aisef2 import util\nfrom aisef2.kinds import Kind\n\n\n{first}\n\ndef target(x):\n'
         "    if x > 1:\n        return util.inc(x) + k()\n    return Kind.A.value - 1\n\n\n{second}\n\n"
         "def helper(x):\n    return x * 2\n\n\ndef called_by_test():\n    return 7\n")
K1, K2 = "def k():\n    return 1\n", "def k():\n    return 2\n"


def d4_order(t: Toy, target: str = TGT, component: str = "I1") -> Case:   # probe_order: two defs of k swapped
    t.files["aisef2/toy.py"] = ORDER.format(first=K1, second=K2)   # k() is 2 at the basis
    t.edit(K, "toy.target(2), 3", "toy.target(2), 5")
    t.reentry()
    b = t.commit()
    t.files["aisef2/toy.py"] = ORDER.format(first=K2, second=K1)   # k() is 1 now: target(2) == 4
    h = t.commit()
    return Case(b, h, t.observe(h), target, "INVALIDATED", component)


def d4_order_r6(t: Toy) -> Case:   # the same swap seen from another target whose kill file imports toy.py
    return d4_order(t, INC, "R6")


LOADER = ('ROOT = pathlib.Path(__file__).resolve().parents[2]\n'
          'SPEC = importlib.util.spec_from_file_location("doc_script", ROOT / "aisef2" / "doc.py")\n\n\n')


def d5_loader(t: Toy) -> Case:   # probe_untested: a kill file runs aisef2/doc.py in-process by path
    t.edit(K, "import unittest\n", "import importlib.util\nimport pathlib\nimport unittest\n")
    t.edit(K, "class T(", LOADER + "class T(")
    add_test(t, K, "test_inc", "    def test_doc(self):\n        m = importlib.util.module_from_spec(SPEC)\n"
             "        SPEC.loader.exec_module(m)\n        self.assertEqual(m.keys({'b': 1, 'a': 2}), ['a', 'b'])\n")
    b = t.commit()
    t.edit("aisef2/doc.py", "return sorted(d)", "return list(d)")
    h = t.commit()
    obs = t.observe(h, opened={K: {"aisef2/doc.py": "load"}})   # module_from_spec raises no import event: not loaded
    return Case(b, h, obs, INC, "INVALIDATED", "R2")   # the literal path names doc.py: the static boundary (R8 behind)


def d5_load_tag_data(t: Toy) -> Case:   # a "load" of a non-.py file is a data read
    b = t.commit()
    t.files["docs/v2.1/schema.json"] = '{"a": 2}\n'
    h = t.commit()
    obs = t.observe(h, opened={"tests/v2/test_doc.py": {"docs/v2.1/schema.json": "load"}})
    return Case(b, h, obs, DOC, "INVALIDATED", "R2")


def n9_table(t: Toy) -> Case:   # the target added to mutation.py's Option C table; the pinned ruling intact
    t.extra = {impact.RULING_REL: impact._blob(ROOT, "HEAD", impact.RULING_REL)}   # the pinned blob, not a CRLF checkout
    t.harness = harness(extra="VERIFIED_REUSE = {'aisef2/toy.py::target': '" + "0" * 64 + "'}\n")
    t.entries[TGT]["source_sha256"] = "f" * 64
    b = t.commit()
    return Case(b, b, None, TGT, "INVALIDATED", "I8")


def n9_ruling(t: Toy) -> Case:   # the ruling file altered to cover the target
    doc = json.loads((ROOT / impact.RULING_REL).read_bytes())
    doc["disposition"]["VERIFIED_REUSE"][TGT] = dict(next(iter(doc["disposition"]["VERIFIED_REUSE"].values())))
    t.extra = {impact.RULING_REL: json.dumps(doc).encode()}
    t.harness = harness(extra="VERIFIED_REUSE = {'aisef2/toy.py::target': '" + "0" * 64 + "'}\n")
    t.entries[TGT]["source_sha256"] = doc["source_transition"]["measured_source_sha256"]
    b = t.commit()
    return Case(b, b, None, TGT, "INVALIDATED", "I8")


def n10(t: Toy) -> Case:
    h = t.commit()
    return Case("0" * 40, h, None, TGT, "UNRESOLVED", "basis")


def n13_data_reader(t: Toy) -> Case:   # a comment appended; the kill file reads the module as data
    b = t.commit()
    t.files["aisef2/toy.py"] += "# note\n"
    h = t.commit()
    return Case(b, h, t.observe(h, {K: ["aisef2/toy.py"]}), INC, "INVALIDATED", "R2")


def n13b(t: Toy) -> Case:
    b = t.commit()
    t.edit("aisef2/toy.py", "from aisef2.kinds import Kind\n", "from aisef2.kinds import Kind\nfrom enum import Enum\n")
    t.files["aisef2/toy.py"] += "\n\nclass New(Enum):\n    X = 1\n"
    h = t.commit()
    return Case(b, h, t.observe(h), INC, "INVALIDATED", "R6")


def n15(t: Toy) -> Case:   # the kill test calls helper only on a branch its unmutated run never takes
    add_test(t, K, "test_inc", "    def test_branch(self):\n        if toy.target(0) > 5:\n            toy.helper(1)\n")
    c = n2(t)
    return c._replace(state="INVALIDATED", component="I2")


def _child(t: Toy, argv: str, change, trace: bool, children: dict) -> Case:
    add_test(t, K, "test_inc", f"    def test_child(self):\n        subprocess.run({argv}, check=True)\n",
             "import subprocess\nimport sys\n")
    b = t.commit()
    change(t)
    h = t.commit()
    over = {"os_trace": True} if trace else {"children": {"hooked": 0, **children}}
    obs = t.observe(h, {K: ["aisef2/toy.py"]} if trace else None, **over)   # traced: the child's opens are data
    named = "aisef2/toy.py" in argv   # a literal path in the kill test: the static boundary (R2S) fires first
    return Case(b, h, obs, INC, "INVALIDATED", "R2" if trace or named else "R1")


def _helper_body(t: Toy) -> None:
    t.edit("aisef2/toy.py", "return x * 2", "return x * 3")


def _comment(t: Toy) -> None:
    t.files["aisef2/toy.py"] += "# one more line\n"


def n16(t: Toy, trace: bool = False) -> Case:   # an unhooked Python child changes nothing the parent sees
    return _child(t, '[sys.executable, "-c", "from aisef2 import toy; toy.helper(1)"], env={"PATH": ""}',
                  _helper_body, trace, {"unhooked_python": 1, "other": 0})


def n16_trace(t: Toy) -> Case:
    return n16(t, True)


def n17(t: Toy, trace: bool = False) -> Case:   # a non-Python child reads toy.py
    return _child(t, '["wc", "-l", "aisef2/toy.py"]', _comment, trace, {"unhooked_python": 0, "other": 1})


def n17_trace(t: Toy) -> Case:
    return n17(t, True)


def n26(t: Toy, trace: bool = False) -> Case:   # the test_v21_confine pattern: copy toy.py, run it with python -I -B
    argv = ('[sys.executable, "-I", "-B", "-c", "import shutil, sys, tempfile; d = tempfile.mkdtemp(); '
            'shutil.copy(\'aisef2/toy.py\', d); sys.path.insert(0, d); import toy; toy.helper(1)"]')
    return _child(t, argv, _helper_body, trace, {"unhooked_python": 1, "other": 0})


def n26_trace(t: Toy) -> Case:
    return n26(t, True)


def n18(t: Toy) -> Case:
    b = t.commit()
    t.files["aisef2/util.py"] = "import sys\n\nsys.setrecursionlimit(60)\n\n\n" + t.files["aisef2/util.py"]
    h = t.commit()
    return Case(b, h, t.observe(h), TGT, "INVALIDATED", "R6")


REGISTRY = ('import pathlib\n\nTESTS_V2 = "tests/v2"\n\n\ndef test_directories(root):\n'
            '    return sorted({p.parent for p in (pathlib.Path(root) / TESTS_V2).rglob("test_*.py")})\n')
REG_LISTING = {"listed": ["tests/v2"], "listed_by": {"tests/v2": [SD.REGISTRY]}}
NEW_TEST = "tests/v2/test_new.py"
NEW_TEST_SRC = "import unittest\n\n\nclass N(unittest.TestCase):\n    def test_n(self):\n        pass\n"


def with_registry(t: Toy) -> None:
    """As in the repository: tests/v2/__init__.py imports the registry, whose TESTS_V2 names every tests/v2 file."""
    t.files["aisef2/invariants/__init__.py"] = ""
    t.files[SD.REGISTRY] = REGISTRY
    t.files["tests/v2/__init__.py"] = "from aisef2.invariants import registry  # noqa: F401\n"


def n20(t: Toy) -> Case:   # test_k lists aisef2 -> a new aisef2/new.py
    b = t.commit()
    t.files["aisef2/new.py"] = "X = 1\n"
    h = t.commit()
    return Case(b, h, t.observe(h, listed=["aisef2"], listed_by={"aisef2": [K]}), TGT, "INVALIDATED", "R3")


def n20_new_test(t: Toy, rel: str = NEW_TEST, state: str = "INVALIDATED", component: str = "R6") -> Case:
    """Amendment A1 withdrawn: the new file is in S(F) (registry's TESTS_V2), so R6 (module new) fires before the
    R3 registry discount is reached."""
    with_registry(t)
    b = t.commit()
    t.files[rel] = NEW_TEST_SRC
    h = t.commit()
    return Case(b, h, t.observe(h, **REG_LISTING), TGT, state, component)


def n20_new_dir(t: Toy) -> Case:   # a new test directory changes test_directories(): the discount does not hold
    return n20_new_test(t, "tests/v2/newdir/test_x.py", "INVALIDATED", "R6")


def n21(t: Toy) -> Case:
    b = t.commit()
    t.files["tests/v2/zz/__init__.py"] = "raise SystemExit(1)\n"
    h = t.commit()
    return Case(b, h, t.observe(h), TGT, "INVALIDATED", "R4")


def n21b(t: Toy) -> Case:
    b = t.commit()
    t.files["tests/v2/p9/__init__.py"] = ""
    t.files["tests/v2/p9/test_k.py"] = "import unittest\n\n\nclass T(unittest.TestCase):\n    def test_x(self):\n        self.fail()\n"
    h = t.commit()
    return Case(b, h, t.observe(h), TGT, "INVALIDATED", "R4")


def n21c(t: Toy) -> Case:   # R4 counts bytes: a comment in a package init the discovery imports
    t.files["tests/v2/sub/__init__.py"] = ""
    b = t.commit()
    t.files["tests/v2/sub/__init__.py"] = "# note\n"
    h = t.commit()
    return Case(b, h, t.observe(h), TGT, "INVALIDATED", "R4")


def n22(t: Toy) -> Case:
    b = t.commit()
    t.files["aisef2/toy/__init__.py"] = ""
    h = t.commit()
    return Case(b, h, t.observe(h), TGT, "INVALIDATED", "R5")


def r5_extension(t: Toy) -> Case:   # an extension module takes precedence over toy.py
    b = t.commit()
    t.extra["aisef2/toy.cpython-314-darwin.so"] = b"\xcf\xfa\xed\xfe"
    h = t.commit()
    return Case(b, h, t.observe(h), TGT, "INVALIDATED", "R5")


def n23(t: Toy) -> Case:
    b = t.commit()
    t.edit("aisef2/dyn.py", "return 2", "return 3")
    h = t.commit()
    return Case(b, h, t.observe(h), DYN, "INVALIDATED", "R8")


def n24(t: Toy) -> Case:   # the N23 site sits in a def the unmutated run never calls: tier S scopes all of S(F)
    t.edit("tests/v2/test_dyn.py", "self.assertEqual(dyn.run(dyn.pick(1)), 1)", "self.assertEqual(dyn.pick(1), 'a')")
    c = n23(t)
    return c


def n25_python(t: Toy) -> Case:
    c = n2(t)
    return c._replace(obs=t.observe(c.head, python="3.0"), state="UNRESOLVED", component="R0")


def n25_platform(t: Toy) -> Case:   # a darwin/linux record presented for a windows claim (and the reverse)
    c = n2(t)
    return c._replace(obs=t.observe(c.head, platform="windows"), state="UNRESOLVED", component="R0")


def n27(t: Toy) -> Case:
    c = n2(t)
    return c._replace(obs=t.observe(c.head, lost=1), state="INVALIDATED", component="R1")


COUNTER = ('import pathlib\nimport unittest\n\nROOT = pathlib.Path(__file__).resolve().parents[2]\n\n\n'
           'class C(unittest.TestCase):\n    def test_count(self):\n'
           '        n = sum(p.read_text().count("def test_") for p in (ROOT / "tests" / "v2").glob("test_*.py"))\n'
           '        self.assertGreater(n, 0)\n')


def n28(t: Toy) -> Case:   # kill file F2 counts `def test_` in every tests/v2 test module
    kill = [K, "tests/v2/test_count.py"]
    t.files["tests/v2/test_count.py"] = COUNTER
    t.set_targets({**TARGETS, INC: kill})
    t.entries[INC] = entry(t.files, INC, kill=kill)
    b = t.commit()
    t.files[K] += "# def test_extra(self): counted, not run\n"   # no segment changes: I4 additive, R6 silent
    h = t.commit()
    return Case(b, h, t.observe(h, {"tests/v2/test_count.py": [K]}), INC, "INVALIDATED", "R2")


def n29(t: Toy) -> Case:   # a new def changes the module layout: R6 fires first (R8, dir(), is the backstop)
    add_test(t, K, "test_inc", "    def test_dir(self):\n"
             "        self.assertEqual([n for n in dir(toy) if n.startswith('check_')], [])\n")
    b = t.commit()
    t.files["aisef2/toy.py"] += "\n\ndef check_b():\n    pass\n"
    h = t.commit()
    return Case(b, h, t.observe(h), TGT, "INVALIDATED", "R6")


def n30(t: Toy, loaded: str = "aisef2/plug.py", state: str = "VERIFIED_REUSE", component: str = "") -> Case:
    t.files["aisef2/reg.py"] = 'import importlib\n\n\ndef load():\n    return importlib.import_module("aisef2.plug")\n'
    t.files["aisef2/plug.py"] = "VALUE = 1\n"
    t.edit(K, "from aisef2 import toy, util\n", "from aisef2 import reg, toy, util\n")
    c = n2(t)
    return c._replace(obs=t.observe(c.head, loaded={K: [loaded]}), state=state, component=component)


def n30_miss(t: Toy) -> Case:   # loaded, but not in S(F): the D2 check
    return n30(t, "aisef2/doc.py", "UNRESOLVED", "D2")


def n31(t: Toy) -> Case:
    b = t.commit()
    t.files["docs/v2.1/schema.json"] = '{"a": 2}\n'
    h = t.commit()
    return Case(b, h, t.observe(h, {"tests/v2/test_doc.py": ["docs/v2.1/schema.json"]}), DOC, "INVALIDATED", "R2")


def n33(t: Toy) -> Case:
    b = t.commit()
    t.harness = t.harness.replace("TIMEOUT = 900", "TIMEOUT = 901", 1)
    h = t.commit()
    return Case(b, h, t.observe(h), TGT, "INVALIDATED", "I9")


def n33b(t: Toy) -> Case:
    b = t.commit()
    t.harness = t.harness.replace("def _confirmed(r: dict) -> bool:\n", "def _confirmed(r: dict) -> bool:\n    # edited\n", 1)
    h = t.commit()
    return Case(b, h, None, INC, "INVALIDATED", "I9")


def new_test_file(t: Toy) -> Case:   # §2.8: a NEW test file in a directory a code file names: in S(F), R6 (A1 withdrawn)
    t.files["aisef2/reg.py"] = 'TESTS_V2 = "tests/v2"\n'
    t.edit(K, "from aisef2 import toy, util\n", "from aisef2 import reg, toy, util\n")
    b = t.commit()
    t.files[NEW_TEST] = NEW_TEST_SRC
    h = t.commit()
    return Case(b, h, t.observe(h), TGT, "INVALIDATED", "R6")


def new_test_file_loaded(t: Toy) -> Case:   # the same file, observed loaded by the kill file's process: R6
    c = new_test_file(t)
    return c._replace(obs=t.observe(c.head, loaded={K: [NEW_TEST]}))


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


# ---- re-review regressions (each mirrors the confirmed probe; each gave VERIFIED_REUSE on the dcaebab7 engine)

DISPATCH = ('import importlib.util\nimport pathlib\n\nHERE = pathlib.Path(__file__).resolve().parent\n'
            'DESCRIBERS = {"exact": HERE / "describers" / "exact.py", "other": HERE / "describers" / "other.py"}\n\n\n'
            'def describe(value):\n    kind = "exact" if value == 3 else "other"\n'
            '    spec = importlib.util.spec_from_file_location("aisef2_describer_" + kind, DESCRIBERS[kind])\n'
            '    mod = importlib.util.module_from_spec(spec)\n    spec.loader.exec_module(mod)\n'
            '    return mod.describe(value)\n')
OTHER = 'PREFIX = "value "\n\n\ndef describe(value):\n    return PREFIX + str(value)\n'
DISPATCH_KILL = ("import unittest\n\nfrom aisef2 import dispatch, toy, util\n\n\nclass T(unittest.TestCase):\n"
                 "    def test_target(self):\n        self.assertTrue(dispatch.describe(toy.target(2)).startswith(\"three\"))\n"
                 "        self.assertEqual(toy.called_by_test(), 7)\n\n"
                 "    def test_inc(self):\n        self.assertEqual(util.inc(1), 2)\n")


def a1_loader(t: Toy, old: str = 'PREFIX = "value "', new: str = 'PREFIX = "three "', component: str = "R6") -> Case:
    """A1-MUTANTONLY: a Δ file named only by literal path parts (D2 b) and loaded through a computed-name loader on a
    path only a mutant takes; the unmutated run executes exact.py. A1 (code(F) ∪ ran(F)) judged neither R6 nor R8."""
    t.files.update({"aisef2/dispatch.py": DISPATCH, "aisef2/describers/exact.py": 'def describe(value):\n    return "three"\n',
                    "aisef2/describers/other.py": OTHER, K: DISPATCH_KILL})
    b = t.commit()
    t.edit("aisef2/describers/other.py", old, new)
    h = t.commit()
    obs = t.observe(h, opened={K: {"aisef2/describers/exact.py": "load"}})
    return Case(b, h, obs, TGT, "INVALIDATED", component)


def a1_loader_body(t: Toy) -> Case:   # a def-body change of other.py: its literal path parts (R2S), R8 behind
    return a1_loader(t, "return PREFIX + str(value)", 'return "three " + str(value)', "R2")


D4_KILL = ("import unittest\n\nfrom aisef2 import toy, util\n\n\nclass T(unittest.TestCase):\n"
           "    def test_target(self):\n"
           "        self.assertEqual(toy.target(1), 0)\n        self.assertEqual(toy.called_by_test(), 7)\n\n"
           "    def test_inc(self):\n        self.assertEqual(util.inc(5), 6)\n")
GOOD, BAD = "    return x + 1\n", "    return x + 1 if x > 1 else x - 1\n"
TRY = "try:\n    HOOK = _small\nexcept NameError:\n    HOOK = None\n\n\n"
SMALL = "def _small(x):\n    return x - 1\n\n\n"
HOOK_INC = "def inc(x):\n    if x > 1 or HOOK is None:\n        return x + 1\n    return HOOK(x)\n"
CLS = ("class Impl:\n    def run(self, x):\n        return {a}\n\n    def run(self, x):  # noqa: F811\n        return {b}\n\n\n"
       "def inc(x):\n    return x + 1 if x > 1 else Impl().run(x)\n")


def _impl_swap(first: str, second: str) -> str:
    return f"def _impl(x):\n{first}\n\ndef _impl(x):  # noqa: F811\n{second}\n\ndef inc(x):\n    return _impl(x)\n"


D4_LAYOUT = {   # D4-PARTIAL (a), (b), (c): util.py at the basis, at head; inc(1) goes from 2 to 0 in each
    "noqa_swap": (_impl_swap(BAD, GOOD), _impl_swap(GOOD, BAD)),
    "def_moved": (TRY + SMALL + HOOK_INC, SMALL + TRY + HOOK_INC),
    "method_swap": (CLS.format(a="x - 1", b="x + 1"), CLS.format(a="x + 1", b="x - 1")),
}


def d4_layout(t: Toy, kind: str = "noqa_swap") -> Case:
    base_src, head_src = D4_LAYOUT[kind]
    t.files.update({"aisef2/util.py": base_src, K: D4_KILL})
    b = t.commit()
    t.files["aisef2/util.py"] = head_src
    h = t.commit()
    return Case(b, h, t.observe(h), TGT, "INVALIDATED", "R6")


def d4_def_moved(t: Toy) -> Case:
    return d4_layout(t, "def_moved")


def d4_method_swap(t: Toy) -> Case:
    return d4_layout(t, "method_swap")


I4_HOOKS = {
    "load_tests": ("\n\ndef load_tests(loader, tests, pattern):\n    return unittest.TestSuite(t for s in tests for t in s "
                   "if t._testMethodName != \"test_target\")\n"),
    "setUpModule": "\n\ndef setUpModule():\n    toy.target = lambda x: 3 if x == 2 else 0\n",
}


def i4_hook(t: Toy, hook: str = "load_tests") -> Case:   # I4-HOOKS: a new unittest protocol def in the kill file
    b = t.commit()
    t.files[K] += I4_HOOKS[hook]
    h = t.commit()
    return Case(b, h, t.observe(h), TGT, "INVALIDATED", "I4")


def i4_setupmodule(t: Toy) -> Case:
    return i4_hook(t, "setUpModule")


NEGATIVE = [n1, n1_comment, n3, n3b, n4, i4_comment, n5, n6, n6b, n7a_windows_for_posix, n7a_posix_for_windows, n7c,
            n7d_separators, n7d_flavors, n7e, n7f, n7g, d1_history_after_basis, d1_history_not_sibling, n8,
            d2_shadowed_base, d2_replaced_blob, d3_not_live, d4_order, d4_order_r6, d5_loader, d5_load_tag_data,
            n9_table, n9_ruling, n10, n13_data_reader, n13b, n15, n16, n16_trace, n17, n17_trace, n18, n20, n20_new_test,
            n20_new_dir, n21, n21b, n21c, n22, r5_extension, n23, n24, n25_python, n25_platform, n26, n26_trace, n27,
            n28, n29, n30_miss, n31, n33, n33b, no_observation, wrong_tree_observation, unobserved_child,
            new_test_file, new_test_file_loaded, a1_loader, a1_loader_body, d4_layout, d4_def_moved, d4_method_swap,
            i4_hook, i4_setupmodule]


class ImpactTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.toy = Toy(pathlib.Path(self._tmp.name) / "repo")

    def tearDown(self):
        self._tmp.cleanup()

    def again(self) -> Toy:
        self.toy = Toy(pathlib.Path(tempfile.mkdtemp(dir=self._tmp.name)) / "repo")
        return self.toy

    def run_case(self, fn, *args) -> impact.State:
        case = fn(self.toy, *args)
        self.case = case
        self.assertEqual(check(self.toy, case), [])
        return state_of(self.toy, case)

    def test_n1_target_slice(self):
        self.run_case(n1)
        self.again()
        self.run_case(n1_comment)

    def test_n2_unreferenced_helper(self):
        s = self.run_case(n2)
        self.assertEqual(s.evidence["unreferenced_changes"], ["aisef2/toy.py::helper"])
        self.assertTrue(s.basis.startswith("observation:") and s.basis.endswith(f"@{self.case.base}"), s.basis)
        self.assertEqual(s.compared, ["I7", "I6", "I1", "I3", "I4", "I5", "I9"])
        # red-before: today's whole-file rule calls it stale
        self.assertNotEqual(M.source_digest(self.toy.files["aisef2/toy.py"]), self.toy.entries[TGT]["source_sha256"])

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
        self.assertEqual(M.target_problems(self.toy.entries[TGT], self.toy.root), [])

    def test_i4_exact_segment_text(self):
        self.run_case(i4_comment)
        # red-before: the ast.dump segments of v21_snapshot_delta see no change
        b, h = _last(self.toy)
        self.assertEqual(SD._segments(SD._text(self.toy.root, b, K)), SD._segments(SD._text(self.toy.root, h, K)))

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
        t.entries[TGT] = entry(t.files, TGT, POSIX_TAIL + HOMEBREW)
        b = t.commit()
        s = next(x for x in impact.classify(t.root, b, b) if x.target == TGT)
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
        t.entries[TGT] = entry(t.files, TGT, POSIX_TAIL + "'C:\\Users\\x\\run1' != '<run>/tmp/<mkdtemp>/home/.config'\n")
        b = t.commit()
        s = next(x for x in impact.classify(t.root, b, b) if x.target == TGT)
        self.assertEqual((s.state, s.evidence["platform"]["flavor"]), ("VERIFIED_REUSE", None))

    def test_n7f_worker(self):
        self.run_case(n7f)
        t = self.toy   # the same history with the right digest: the worker's darwin marker decides
        hist = next(k for k in t.extra if k.endswith(".history.json"))
        h = json.loads(t.extra[hist])
        h["log"]["sha256"] = impact._sha(t.extra[h["log"]["path"]])
        t.extra[hist] = json.dumps(h).encode()
        b = t.commit()
        s = next(x for x in impact.classify(t.root, b, b) if x.target == TGT)
        self.assertEqual((s.state, s.evidence["platform"]["family"], s.evidence["platform"]["flavor"]),
                         ("VERIFIED_REUSE", "posix", "darwin"))
        self.assertTrue(s.evidence["platform"]["by"].startswith("W:"))

    def test_n7g_co_occurrence(self):
        self.run_case(n7g)

    def test_d1_worker_history_after_the_basis(self):
        self.run_case(d1_history_after_basis)
        # red-before: read at head, the forged history is admissible W evidence for the entry
        b, h = _last(self.toy)
        digest = impact._sha(impact.canonical(self.toy.entries[TGT]))
        self.assertIn(digest, impact.workers_at(self.toy.root, h)[0])
        self.assertNotIn(digest, impact.workers_at(self.toy.root, b)[0])

    def test_d1_worker_history_must_name_its_own_siblings(self):
        self.run_case(d1_history_not_sibling)
        refused = impact.workers_at(self.toy.root, self.case.base)[1]
        self.assertTrue(any("sibling" in r for r in refused), refused)

    def test_n8_tamper(self):
        self.run_case(n8)

    def test_d2_abbreviated_basis_shadowed_by_a_ref(self):
        s = self.run_case(d2_shadowed_base)
        self.assertIn("shadowed by a ref", s.reason)
        # red-before: git itself prefers the ref, so the abbreviated basis names the tampered head
        self.assertEqual(_git(self.toy.root, "rev-parse", self.case.base), _last(self.toy)[1])

    def test_d2_replace_refs_are_ignored(self):
        self.run_case(d2_replaced_blob)
        # red-before: a git child that honours replace refs reads head's record at the basis
        b, h = _last(self.toy)
        self.assertEqual(_git(self.toy.root, "cat-file", "blob", f"{b}:{RECORD}"),
                         _git(self.toy.root, "cat-file", "blob", f"{h}:{RECORD}"))

    def test_d2_v220_label_only_for_the_pinned_full_sha(self):
        b = self.toy.commit()   # Δ = ∅: a reuse that rests on no observation (an observation-based one never carries
        c = Case(b, self.toy.commit(), None, TGT, "VERIFIED_REUSE", "")   # this label: Review 1, PROV-1)
        self.assertEqual(state_of(self.toy, c).basis, f"calibration@{c.base}")
        with mock.patch.object(impact, "BASE", c.base):
            self.assertEqual(state_of(self.toy, c).basis, f"v2.2.0-accepted@{c.base}")
            run = impact.classify(self.toy.root, c.base, c.head, observations=c.obs)
            self.assertEqual(impact.report(run)["run"], "v2.2.0-accepted")
            self.assertTrue(impact.report(impact.classify(self.toy.root, c.head, c.head))["run"].startswith("calibration"))
        self.assertEqual(impact.BASE, "da3ea33f3b695aaca73e87a704145a0193aced23")

    def test_f3_acceptance_basis_only_on_reuse(self):
        """F3: a non-reuse state claims no acceptance; it names the run's basis commit as evidence.run_base."""
        c = n1(self.toy)
        with mock.patch.object(impact, "BASE", c.base):
            s = state_of(self.toy, c)
        self.assertEqual((s.state, s.basis, s.evidence["run_base"]), ("INVALIDATED", "", c.base))
        c = n2(self.again())
        with mock.patch.object(impact, "BASE", c.base):
            r = state_of(self.toy, c)
        self.assertEqual(r.state, "VERIFIED_REUSE")   # it rests on an observation: no acceptance basis (PROV-1)
        self.assertTrue(r.basis.startswith("observation:") and "accepted" not in r.basis, r.basis)
        self.assertNotIn("run_base", r.evidence)

    def test_a_tree_path_holding_an_escape_pair_is_still_seen(self):
        """The witness writer escapes native paths exactly as the hook does (OBS._esc). A tree whose absolute path
        holds a backslash-letter pair — every Windows runner path does (D:\\a\\...\\tree); on POSIX a directory named
        so — must not be unescaped or split by the parser, or the kill file goes unseen and R1 swallows every other
        rule (the 26-failure windows-latest cluster at a0703c44, run 45006442353)."""
        self.toy = Toy(pathlib.Path(self._tmp.name) / "D:\\a\\tree-alike" / "repo")   # "\t" and "\a" pairs in one name
        c = n2(self.toy)
        rec = c.obs[K]
        self.assertEqual({k: v for k, v in rec["completeness"].items() if v}, {}, rec["completeness"])
        self.assertIn(K, rec["loaded"])
        with mock.patch.object(impact, "BASE", c.base):
            s = state_of(self.toy, c)
        self.assertEqual((s.state, s.component), ("VERIFIED_REUSE", ""), s.reason)

    def test_f2_report_uses_the_shas_the_run_resolved(self):
        """F2 (probe_report_toctou / verify_f2_main): a ref that moves after classify() resolved it does not move
        the report. A: a tampering commit lands on HEAD; B: --base is a tag moved from a calibration commit to BASE."""
        t = self.toy
        t.entries[TGT] = e = entry(t.files, TGT, survivor=True)
        b = t.commit()
        real = impact.classify
        moved = {}

        def tamper_after(root, base, head, **kw):
            run = real(root, base, head, **kw)
            e2 = json.loads(json.dumps(e))
            e2["results"][1] = {**e["results"][0], "mutant": "L2 b"}
            e2.update(killed=2, survivors=[])
            t.entries[TGT] = e2
            moved["head"] = t.commit()
            return run

        def retag_after(root, base, head, **kw):
            run = real(root, base, head, **kw)
            _git(t.root, "tag", "-f", "rel", b)
            return run

        def main(wrap, *argv):
            out = pathlib.Path(self._tmp.name) / f"{len(moved)}-{wrap.__name__}.json"
            with mock.patch.object(impact, "classify", wrap), contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                impact.main(["--classify", *argv, "--json", str(out)])
            return json.loads(out.read_text())

        with mock.patch.object(impact, "ROOT", t.root), mock.patch.object(impact, "BASE", b):
            doc = main(tamper_after)
            self.assertEqual((doc["head"]["sha"], doc["base"]["sha"], doc["run"]), (b, b, "v2.2.0-accepted"))
            self.assertEqual(state_of(t, Case(b, moved["head"], None, TGT, "", "")).component, "I7")   # the moved head
            h = moved["head"]
            _git(t.root, "tag", "rel", h)
            doc = main(retag_after, "--base", "rel", "--head", h)
            self.assertEqual((doc["base"]["sha"], doc["head"]["sha"]), (h, h))
            self.assertTrue(doc["run"].startswith("calibration"), doc["run"])
            self.assertEqual({x["basis"] for x in doc["states"] if x["state"] == "VERIFIED_REUSE"}, {f"calibration@{h}"})

    def test_d3_entry_must_be_live_at_the_basis(self):
        s = self.run_case(d3_not_live)
        self.assertIn("not live at the basis", s.reason)

    def test_d4_statement_order(self):
        self.run_case(d4_order)
        b, h = _last(self.toy)
        a, z = SD._text(self.toy.root, b, "aisef2/toy.py"), SD._text(self.toy.root, h, "aisef2/toy.py")
        # red-before: as a sorted multiset the slice is the same, and reach.changed() sees nothing
        self.assertEqual(sorted(impact.target_slice(M, a, "target")), sorted(impact.target_slice(M, z, "target")))
        self.assertEqual((impact.reach.changed(a, z)["names"], impact.reach.changed(a, z)["module"]), ({}, "unchanged"))
        self.again()
        self.assertIn("changed order", self.run_case(d4_order_r6).reason)

    def test_d5_code_run_by_path_in_process(self):
        self.assertIn("aisef2/doc.py", self.run_case(d5_loader).reason)   # the static boundary: its literal path
        with mock.patch.object(impact, "_OFF", frozenset({"R2S"})):   # R8 (the computed-name loader) still holds
            self.assertEqual(state_of(self.toy, self.case).component, "R8")
        # red-before: the observation never lists doc.py as loaded; only its "load" open says it ran
        self.assertNotIn("aisef2/doc.py", self.case.obs[K]["loaded"])
        site = 'spec_from_file_location("doc_script", ROOT / "aisef2" / "doc.py")'
        self.assertTrue(impact.dynamic_sites(site, "x.py"))
        self.assertFalse(impact.dynamic_sites('spec_from_file_location("doc_script", "aisef2/doc.py")', "x.py"))

    def test_d5_load_of_a_data_file(self):
        self.run_case(d5_load_tag_data)

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

    def test_git_failure_is_never_clean(self):
        """A failing git diff reads neither as a clean tree nor as Δ = ∅."""
        c = n2(self.toy)
        real = S2._git
        for marker, component in (("--name-only", "dirty"), ("--raw", "basis")):
            def failing(root, *args, marker=marker):
                if args[:1] == ("diff",) and marker in args:
                    return subprocess.CompletedProcess(args, 128, b"", b"fatal: injected")
                return real(root, *args)
            with self.subTest(marker), mock.patch.object(impact.S2, "_git", failing):
                states = impact.classify(self.toy.root, c.base, c.head, observations=c.obs)
                self.assertEqual({(s.state, s.component) for s in states}, {("UNRESOLVED", component)})

    def test_basis_rows_use_the_basis_digest_rule(self):
        t = self.toy
        b = t.commit()
        t.harness = harness(extra="\n\ndef source_digest(text: str) -> str:\n    return 'another rule'\n")
        h = t.commit()
        s = state_of(t, Case(b, h, t.observe(h), TGT, "", ""))
        self.assertEqual((s.state, s.component), ("VERIFIED_REUSE", ""), s.reason)

    def test_n13_comment(self):
        t = self.toy
        b = t.commit()
        t.files["aisef2/toy.py"] += "# note\n"
        h = t.commit()
        for s in impact.classify(t.root, b, h, observations=t.observe(h)):   # R6/R7 fire on nothing
            if s.target == DYN:   # its S(F) holds an open R8 site: with observations, any Δ ≠ ∅ (Review 1, A3-SND-2)
                self.assertEqual((s.state, s.component), ("INVALIDATED", "R8"), s)
            else:
                self.assertEqual(s.state, "VERIFIED_REUSE", s)
        self.again()
        self.run_case(n13_data_reader)

    def test_n13b_import_and_class(self):
        self.run_case(n13b)
        s = next(x for x in impact.classify(self.toy.root, *_last(self.toy)) if x.target == TGT)
        self.assertEqual((s.state, s.component), ("INVALIDATED", "I1"))

    def test_n15_untaken_branch(self):
        self.run_case(n15)

    def test_n16_unhooked_child(self):
        self.run_case(n16)
        self.again()
        self.run_case(n16_trace)

    def test_n17_non_python_child(self):
        self.run_case(n17)
        self.again()
        self.run_case(n17_trace)

    def test_n18_import_time(self):
        self.run_case(n18)

    def test_n20_listing(self):
        self.run_case(n20)

    def test_n20_registry_discount(self):
        """Amendment A1 withdrawn: a new tests/v2 module is in S(F) (TESTS_V2) and new, so R6 fires before R3; the N20
        positive does not hold under the frozen letter. The R3 registry discount itself, with R6 switched off: the
        new module is discounted (a later rule decides), a new test directory is not (R3)."""
        s = self.run_case(n20_new_test)
        self.assertEqual(s.evidence["additive_test_changes"], [NEW_TEST])
        b, h = _last(self.toy)
        self.assertIn(NEW_TEST, impact.kill_closure(self.toy.root, b, h, K))
        with mock.patch.object(impact, "_OFF", frozenset({"R6", "R2S"})):   # R2S: TESTS_V2 names every tests/v2 file
            self.assertNotEqual(state_of(self.toy, self.case).component, "R3")
            self.again()
            c = n20_new_dir(self.toy)
            self.assertEqual(state_of(self.toy, c).component, "R3")
        self.assertEqual(check(self.toy, c), [])

    def test_n21_discovery(self):
        self.run_case(n21)

    def test_n21_discovery_basename(self):
        self.run_case(n21b)

    def test_n21_discovery_bytes(self):
        self.run_case(n21c)

    def test_n22_resolution(self):
        self.run_case(n22)

    def test_r5_extension_module(self):
        self.run_case(r5_extension)

    def test_n23_computed_name(self):
        self.run_case(n23)
        # red-before: by name alone, tier S would clear _do_b (its def is its only occurrence)
        self.assertEqual(impact.name_refs(self.toy.files["aisef2/dyn.py"])["_do_b"], 1)
        self.assertTrue(impact.dynamic_sites(self.toy.files["aisef2/dyn.py"], "aisef2/dyn.py"))

    def test_n24_site_off_the_executed_path(self):
        self.run_case(n24)

    def test_n25_platform_and_python(self):
        self.run_case(n25_python)
        self.again()
        self.run_case(n25_platform)

    def test_r0_every_inadmissible_observation(self):
        c = n2(self.toy)
        for over, why in (({"outcome": "FAIL"}, "outcome"), ({"witness": False}, "witness"),
                          ({"outside_tree": True}, "outside the run's tree"), ({"python": "3.0"}, "python"),
                          ({"platform": "windows"}, "the claim is posix"), ({"commit": c.base}, "another tree")):
            with self.subTest(why):
                s = state_of(self.toy, c._replace(obs=self.toy.observe(c.head, **over)))
                self.assertEqual((s.state, s.component), ("UNRESOLVED", "R0"))
                self.assertIn(why, s.reason)
        obs = self.toy.observe(c.head)
        del obs[K]
        self.assertEqual(state_of(self.toy, c._replace(obs=obs)).component, "R0")

    def test_r1_incomplete_observations(self):
        """Each R1 clause decides alone (T1): lost and unparsed_lines with os_trace and no R1_UNSEEN word in S(F), so
        the static scan is off; then the static scan alone, without os_trace."""
        c = n2(self.toy)
        for over, why in (({"lost": 1}, "(lost 1)"), ({"unparsed_lines": 2}, "(unparsed_lines 2)")):
            with self.subTest(why):
                s = state_of(self.toy, c._replace(obs=self.toy.observe(c.head, os_trace=True, **over)))
                self.assertEqual((s.state, s.component), ("INVALIDATED", "R1"), s.reason)
                self.assertIn(why, s.reason)
        s = state_of(self.toy, c._replace(obs=self.toy.observe(c.head, os_trace=True)))
        self.assertEqual((s.state, s.component), ("VERIFIED_REUSE", ""), s.reason)
        t = self.again()
        t.edit("aisef2/util.py", "def inc(x):\n", "# no multiprocessing here\ndef inc(x):\n")   # an R1_UNSEEN word
        t.reentry()
        c = n2(t)
        s = state_of(t, c._replace(obs=t.observe(c.head)))
        self.assertEqual((s.state, s.component), ("INVALIDATED", "R1"), s.reason)
        self.assertIn("(static scan: multiprocessing)", s.reason)
        s = state_of(t, c._replace(obs=t.observe(c.head, os_trace=True)))   # os_trace covers what the hook misses
        self.assertEqual((s.state, s.component), ("VERIFIED_REUSE", ""), s.reason)

    def test_n26_copy_run(self):
        self.run_case(n26)
        self.again()
        self.run_case(n26_trace)

    def test_n27_lost(self):
        self.run_case(n27)

    def test_n28_test_read_as_data(self):
        s = self.run_case(n28)
        # red-before: I4 alone calls it an additive test change
        self.assertIn("I4", s.compared)
        self.assertEqual(s.evidence["additive_test_changes"], [K])

    def test_n29_enumeration(self):
        self.run_case(n29)
        with mock.patch.object(impact, "_OFF", frozenset({"R6"})):   # R8 (dir()) still holds behind R6
            self.assertEqual(state_of(self.toy, self.case).component, "R8")

    def test_a1_withdrawn_mutant_only_loader(self):
        """A1-MUTANTONLY (probe_a1_mutant_loader): R5-R8 judge Δ ∩ S(F) again, so a Δ file the unmutated run never
        executes is judged: R6 for an import-time change, R8 (the computed loader site) for a def-body change."""
        s = self.run_case(a1_loader)
        self.assertIn("aisef2/describers/other.py", s.reason)
        self.again()
        self.assertIn("aisef2/describers/other.py", self.run_case(a1_loader_body).reason)   # R2S: its literal parts
        with mock.patch.object(impact, "_OFF", frozenset({"R2S"})):   # R8 at the computed-name loader site behind it
            self.assertIn("aisef2/dispatch.py:10", state_of(self.toy, self.case).reason)
        b, h = _last(self.toy)
        self.assertNotIn("aisef2/describers/other.py", S2.closure(self.toy.root, h, (K,)))   # not import-reached

    def test_d4_module_layout(self):
        """D4-PARTIAL (verify_d4_partial a-c): a redefinition swap the noqa comment hid, a plain def moved relative
        to the statement that reads it, and swapped same-name methods; reach.changed() sees none of them."""
        for kind, fn in (("noqa_swap", d4_layout), ("def_moved", d4_def_moved), ("method_swap", d4_method_swap)):
            with self.subTest(kind):
                self.run_case(fn)
                got = impact.reach.changed(*D4_LAYOUT[kind])   # red-before: reach sees nothing
                self.assertEqual((got["names"], got["module"]), ({}, "unchanged"))
                self.again()
        shifted = "def f():\n    y = 1\n    return y\n\n\nX = 1\n"
        self.assertTrue(impact.layout_changed("def f():\n    return 1\n\n\nX = 1\n", shifted))   # X moved down
        self.assertIsNone(impact.layout_changed("def f():\n    return 1\n\n\nX = 1\n", "def f():\n    return 2\n\n\nX = 1\n"))
        self.assertIsNone(impact.layout_changed("X = 1\n", "X = 1\n# a comment after the last statement\n"))

    def test_i4_protocol_hooks_are_not_additive(self):
        """I4-HOOKS (probe_i4_hooks): a new load_tests or setUpModule decides which tests run and what they see."""
        self.assertIn("load_tests", self.run_case(i4_hook).reason)
        self.again()
        self.assertIn("setUpModule", self.run_case(i4_setupmodule).reason)
        old = set(impact.segment_texts(FILES[K]))
        plain = "\n\nclass N(unittest.TestCase):\n    def test_n(self):\n        pass\n"
        self.assertEqual(impact.not_additive(old, FILES[K] + plain), [])
        for extra in ("    @classmethod\n    def setUpClass(cls):\n        pass\n", "    X = 1\n",
                      "    def setUp(self):\n        pass\n", "    def __init_subclass__(cls):\n        pass\n"):
            self.assertEqual(impact.not_additive(old, FILES[K] + plain + extra), ["N"], extra)
        self.assertEqual(impact.not_additive(old, FILES[K] + "\n\ndef tearDownModule():\n    pass\n"), ["tearDownModule"])

    def test_n30_d2_check(self):
        self.run_case(n30)
        # red-before: the s2 closure alone misses the string-imported module (D2 c is what holds it)
        b, h = _last(self.toy)
        self.assertNotIn("aisef2/plug.py", S2.closure(self.toy.root, h, (K,)))
        self.again()
        self.run_case(n30_miss)

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
        self.again()
        self.run_case(unobserved_child)

    def test_i3_superset_and_reorder_are_reused(self):
        t = self.toy
        for current, note in (([K, "tests/v2/test_doc.py"], "kill-set-superset"),
                              (["tests/v2/test_doc.py", K], "kill-set-superset")):
            with self.subTest(note):
                t.set_targets({**TARGETS, TGT: current})
                b = t.commit()
                s = state_of(t, Case(b, b, None, TGT, "", ""))
                self.assertEqual((s.state, s.evidence.get("kill_set")), ("VERIFIED_REUSE", note), s.reason)
        t.entries[TGT] = entry(t.files, TGT, kill=[K, "tests/v2/test_doc.py"])
        t.set_targets({**TARGETS, TGT: ["tests/v2/test_doc.py", K]})
        b = t.commit()
        s = state_of(t, Case(b, b, None, TGT, "", ""))
        self.assertEqual((s.state, s.evidence.get("kill_set")), ("VERIFIED_REUSE", "kill-set-reordered"), s.reason)

    def test_new_test_file_named_by_a_directory_constant(self):
        s = self.run_case(new_test_file)
        self.assertEqual(s.evidence["additive_test_changes"], [NEW_TEST])
        self.assertIn(NEW_TEST, s.reason)

    def test_new_test_file_observed_loaded(self):
        self.run_case(new_test_file_loaded)

    def test_unchanged_base_is_reused(self):
        b = self.toy.commit()
        states = impact.classify(self.toy.root, b, b)
        self.assertEqual({s.state for s in states}, {"VERIFIED_REUSE"})
        self.assertEqual(len(states), len(TARGETS))
        self.assertNotIn("MEASURED", {s.state for s in states})   # a legacy entry is never MEASURED

    def test_n14_every_rule_is_load_bearing(self):
        """The intact engine gives every negative case its non-reuse state; with one rule switched off, at least one
        case of that rule becomes VERIFIED_REUSE — so no rule is decoration."""
        wrong, flipped = [], set()
        for fn in NEGATIVE:
            with tempfile.TemporaryDirectory() as d:
                toy = Toy(pathlib.Path(d) / "repo")
                case = fn(toy)
                self.assertNotEqual(case.state, "VERIFIED_REUSE", fn.__name__)
                wrong += [f"{fn.__name__}: {x}" for x in check(toy, case)]
                if case.component in RULES:
                    with mock.patch.object(impact, "_OFF", frozenset({case.component})):
                        if state_of(toy, case).state == "VERIFIED_REUSE":
                            flipped.add(case.component)
        self.assertEqual(wrong, [])
        self.assertEqual(sorted(set(RULES) - flipped), [])

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
            self.assertEqual(ctx.label, "v2.2.0-accepted")
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
