"""validation/v23/observe.py (the F5 recorder) and its use as an input of validation/v23/impact.py.

* The owner's nine adversarial cases (2026-11-21), each REJECTED (UNRESOLVED) or conservatively INVALIDATED, with
  red-before against a recorder variant (a hook without one kind of event, recorded with the audit backend) or an
  engine variant (one rule switched off through impact._OFF) that lacks the guard.
* The strace parser over a recorded, normalized trace (tests/v23/fixtures/strace-toy.json) and hand-made lines:
  runs on every host.
* The strace backend itself on Linux (skipped, with the reason, where strace is absent).

Real recordings run a toy's kill file through the toy's own runner (the real validation/v2/mutation.py with toy tables,
tests/v23/test_v23_impact.py), never a repository kill file. Not a kill file (tests/v23 is outside every mutation.COPY
root: Amendment A2)."""

from __future__ import annotations

import json
import pathlib
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.v23 import test_v23_impact as TI  # noqa: E402
from validation.v23 import impact  # noqa: E402
from validation.v23 import observe as OBS  # noqa: E402

STRACE = sys.platform.startswith("linux") and shutil.which("strace") is not None
NO_STRACE = "strace backend: needs strace on a Linux host (this host has none; the parser runs on recorded fixtures)"
FIXTURE = pathlib.Path(__file__).with_name("fixtures") / "strace-toy.json"
K, TGT, INC = TI.K, TI.TGT, TI.INC
CHILD = "tests/v2/test_child.py"
BRANCH, BRANCH_K = "aisef2/branch.py::pick", "tests/v2/test_branch.py"


def without(*branches: str) -> str:
    """The hook with dispatch branches disabled: a recorder lacking those events (red-before only)."""
    src = OBS.HOOK
    for old, new in (("open", ('if event == "open":', 'if event == "<off>":')),
                     ("listing", ('elif event in ("os.listdir", "os.scandir"):', "elif event in ():")),
                     ("exec", ('elif event == "exec":', 'elif event == "<off>":')),
                     ("import", ('elif event in ("compile", "import"):', "elif event in ():")),
                     ("launch", ("elif event in _LAUNCH:", "elif event in ():"))):
        if old in branches:
            assert new[0] in src, new[0]
            src = src.replace(new[0], new[1], 1)
    return src


def record(t: TI.Toy, kills, backend: str = "auto", hook: str | None = None) -> dict:
    """observe.record() of each kill file at the toy's HEAD; load()ed as impact.py's --observations would."""
    out = pathlib.Path(tempfile.mkdtemp(prefix="rec-", dir=t.root.parent))
    with mock.patch.object(OBS, "HOOK", hook or OBS.HOOK):
        for k in kills:
            OBS.record(t.root, k, out, backend)
    return OBS.load(out)


def state(t: TI.Toy, base: str, head: str, obs, target: str = TGT, off=()) -> impact.State:
    with mock.patch.object(impact, "_OFF", frozenset(off)):
        return next(s for s in impact.classify(t.root, base, head, observations=obs) if s.target == target)


def refinish(rec: dict, edit) -> dict:
    """The witness's manifest edited, the record derived again from it: what a recorder that wrote this provenance
    would have recorded (consistent, so only the binding can refuse it)."""
    w = pathlib.Path(rec["witness"]["dir"])
    man = json.loads((w / "manifest.json").read_text(encoding="utf-8"))
    edit(man)
    (w / "manifest.json").write_text(json.dumps(man, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    (w / OBS.RECORD).unlink()
    return OBS.finish(w)


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="aisef-obs-test-")
        self.t = TI.Toy(pathlib.Path(self._tmp.name) / "repo")

    def tearDown(self):
        self._tmp.cleanup()

    def assertNonReuse(self, s: impact.State, state: str, component: str | tuple, why: str = ""):
        comps = component if isinstance(component, tuple) else (component,)
        self.assertEqual(s.state, state, s)
        self.assertIn(s.component, comps, s)
        self.assertIn(why, s.reason)


class OwnerNegatives(Base):
    """The nine cases. `red` is the state of the same change under the variant that lacks the guard."""

    def helper_change(self) -> tuple[str, str]:   # N2: an unreferenced helper's body; reusable when nothing else fires
        b = self.t.commit()
        self.t.edit("aisef2/toy.py", "return x * 2", "return x * 3")
        return b, self.t.commit()

    def test_0_a_complete_observation_reuses_n2(self):
        b, h = self.helper_change()
        obs = record(self.t, [K])
        rec = obs[K]
        self.assertEqual(OBS.verify(rec), (None, []))
        self.assertEqual({k: v for k, v in rec["completeness"].items() if v}, {})
        self.assertEqual(rec["backend"], "strace" if STRACE else "audit")
        self.assertEqual(rec["outcome"], "PASS")
        self.assertEqual(state(self.t, b, h, obs).state, "VERIFIED_REUSE")
        self.assertIn("aisef2/toy.py", rec["loaded"])
        self.assertEqual(rec["tests"]["ids"], [["v2.test_k.T.test_inc", "ok"], ["v2.test_k.T.test_target", "ok"]])

    # 1 ------------------------------------------------------------------------------------------------------------
    def test_1_missing_child_process_tracing(self):
        """A non-Python child reads toy.py through a path no literal names (the static boundary cannot see it); a
        comment appended to toy.py changes no segment and no layout. Audit: the child is untraced (R1). strace: the
        child is traced and its read of toy.py is data (R2). Red-before: a hook that records no launch — reuse."""
        t = self.t
        TI.add_test(t, K, "test_inc", "    def test_child(self):\n"
                    "        p = os.path.join(os.path.dirname(toy.__file__), 'to' + 'y' + '.py')\n"
                    "        out = subprocess.run(['wc', '-l', p], capture_output=True, text=True, check=True).stdout\n"
                    "        self.assertGreater(int(out.split()[0]), 0)\n", "import os\nimport subprocess\n")
        b = t.commit()
        t.files["aisef2/toy.py"] += "# one more line\n"
        h = t.commit()
        guarded = state(t, b, h, record(t, [K]))
        self.assertNonReuse(guarded, "INVALIDATED", "R2" if STRACE else "R1",
                            "reads aisef2/toy.py as data" if STRACE else "untraced_children 1")
        red = state(t, b, h, record(t, [K], "audit", without("launch")))
        self.assertEqual(red.state, "VERIFIED_REUSE", red)

    # 2 ------------------------------------------------------------------------------------------------------------
    def test_2a_dynamic_import(self):
        """importlib.import_module of a computed name loads a module S(F) does not hold: the D2 check refuses the
        observation. Red-before: a hook without open/exec/import events — the load is unseen, reuse."""
        t = self.t
        t.files["aisef2/plug_a.py"] = "def value():\n    return 1\n"
        TI.add_test(t, K, "test_inc", "    def test_plugin(self):\n"
                    "        m = importlib.import_module('aisef2.' + ''.join(['plug', '_a']))\n"
                    "        self.assertEqual(m.value(), 1)\n", "import importlib\n")
        b = t.commit()
        t.edit("aisef2/plug_a.py", "return 1", "return 1 + 0")
        h = t.commit()
        self.assertNotIn("aisef2/plug_a.py", impact.kill_closure(t.root, b, h, K))
        self.assertNonReuse(state(t, b, h, record(t, [K])), "UNRESOLVED", "D2", "misses aisef2/plug_a.py")
        red = state(t, b, h, record(t, [K], "audit", without("open", "exec", "import")))
        self.assertEqual(red.state, "VERIFIED_REUSE", red)

    def test_2b_runtime_path_construction(self):
        """A data file read through a path built at run time from parts no literal joins: only the observation sees
        the read (R2). Red-before: a hook without open events — reuse."""
        t = self.t
        t.files["aisef2/data.txt"] = "alpha\n"
        TI.add_test(t, K, "test_inc", "    def test_data(self):\n"
                    "        p = pathlib.Path(toy.__file__).with_name(''.join(['da', 'ta.txt']))\n"
                    "        self.assertTrue(p.read_text().strip())\n", "import pathlib\n")
        b = t.commit()
        t.files["aisef2/data.txt"] = "beta\n"
        h = t.commit()
        self.assertNonReuse(state(t, b, h, record(t, [K])), "INVALIDATED", "R2", "reads aisef2/data.txt as data")
        red = state(t, b, h, record(t, [K], "audit", without("open")))
        self.assertEqual(red.state, "VERIFIED_REUSE", red)

    # 3 ------------------------------------------------------------------------------------------------------------
    def test_3_directory_enumeration_detects_a_new_test(self):
        """The kill test lists its own directory by a computed path; a new test module appears there. S(F) does not
        hold it (no registry, no literal), so only the listing decides: R3. Red-before: no listing events — reuse."""
        t = self.t
        TI.add_test(t, K, "test_inc", "    def test_listing(self):\n"
                    "        self.assertIn('test_k.py', os.listdir(os.path.dirname(os.path.abspath(__file__))))\n",
                    "import os\n")
        b = t.commit()
        t.files["tests/v2/test_new.py"] = TI.NEW_TEST_SRC
        h = t.commit()
        self.assertNotIn("tests/v2/test_new.py", impact.kill_closure(t.root, b, h, K))
        self.assertNonReuse(state(t, b, h, record(t, [K])), "INVALIDATED", "R3", "lists tests/v2")
        red = state(t, b, h, record(t, [K], "audit", without("listing")))
        self.assertEqual(red.state, "VERIFIED_REUSE", red)

    # 4 ------------------------------------------------------------------------------------------------------------
    def test_4_changed_environment_platform_or_toolchain(self):
        """A record whose witness says it ran with another environment, on another flavor or family, on another
        python minor or implementation, or for an entry whose own flavor or interpreter is unproven: R0 refuses
        each. Red-before: the same records with R0 switched off are reused."""
        b, h = self.helper_change()
        good = record(self.t, [K])[K]
        flavor = good["platform"]["flavor"]
        other = "linux" if flavor == "darwin" else "darwin"
        edits = {
            "environment": (lambda m: m["env"].update(PYTHONHASHSEED="0" * 64), "its environment is not the runner's"),
            "flavor": (lambda m: m["platform"].update(flavor=other), f"it ran on {other}"),
            "family": (lambda m: m["platform"].update(family="windows"), "the claim is posix"),
            "python": (lambda m: m.update(python="3.0"), "python 3.0"),
            "implementation": (lambda m: m["toolchain"].update(implementation="pypy"), "(pypy)"),
        }
        for name, (edit, why) in edits.items():
            with self.subTest(name):
                obs = {K: refinish(record(self.t, [K])[K], edit)}
                self.assertEqual(OBS.verify(obs[K]), (None, []))   # a consistent record: only the binding refuses it
                self.assertNonReuse(state(self.t, b, h, obs), "UNRESOLVED", "R0", why)
                self.assertEqual(state(self.t, b, h, obs, off={"R0"}).state, "VERIFIED_REUSE")
        home = "/Users/u/lib/x.py" if flavor == "darwin" else "/home/u/lib/x.py"   # this flavor, no interpreter
        for name, tail, why in (("entry flavor unproven", TI.POSIX_TAIL, "the entry's own flavor is unproven"),
                                ("entry interpreter unproven", TI.POSIX_TAIL + f'  File "{home}", line 1, in f\n',
                                 "the entry's own interpreter is unproven")):
            with self.subTest(name):
                t = TI.Toy(pathlib.Path(tempfile.mkdtemp(dir=self._tmp.name)) / "repo")
                t.entries[TGT] = TI.entry(t.files, TGT, tail)
                b2 = t.commit()
                t.edit("aisef2/toy.py", "return x * 2", "return x * 3")
                h2 = t.commit()
                obs = record(t, [K])
                self.assertNonReuse(state(t, b2, h2, obs), "UNRESOLVED", "R0", why)
                self.assertEqual(state(t, b2, h2, obs, off={"R0"}).state, "VERIFIED_REUSE")

    # 5 ------------------------------------------------------------------------------------------------------------
    def branch_toy(self, body: str, data: str) -> tuple[str, str, dict]:
        t = self.t
        t.files["aisef2/branch.py"] = ("import pathlib\n\nROOT = pathlib.Path(__file__).resolve().parents[1]\n\n\n"
                                       f"def pick(x):\n    if x > 5:\n        return {body}.read_text()\n    return 'small'\n")
        t.files[data] = "one\n"
        t.files[BRANCH_K] = ("import unittest\n\nfrom aisef2 import branch\n\n\nclass T(unittest.TestCase):\n"
                             "    def test_pick(self):\n        self.assertEqual(branch.pick(1), 'small')\n")
        t.set_targets({**TI.TARGETS, BRANCH: [BRANCH_K]})
        t.entries[BRANCH] = TI.entry(t.files, BRANCH, kill=[BRANCH_K])
        b = t.commit()
        t.files[data] = "two\n"
        h = t.commit()
        return b, h, record(t, [BRANCH_K])

    def test_5_a_mutant_branch_reads_a_changed_file(self):
        """Only the mutant `x <= 5` of pick reads the data file; the unmutated run (and so the observation) never
        does. The static boundary still INVALIDATES (R2S), for a literal path and for a computed one under a literal
        directory. Red-before: the frozen rules with the observation, the static boundary off — reuse."""
        for name, body, data in (("literal", '(ROOT / "aisef2" / "branch.txt")', "aisef2/branch.txt"),
                                 ("computed", '(ROOT / "aisef2" / ("branch" + str(x % 2) + ".txt"))', "aisef2/branch1.txt")):
            with self.subTest(name):
                b, h, obs = self.branch_toy(body, data)
                self.assertNotIn(data, obs[BRANCH_K]["opened"])   # the baseline never read it
                self.assertEqual({k: v for k, v in obs[BRANCH_K]["completeness"].items() if v}, {})
                self.assertNonReuse(state(self.t, b, h, obs, BRANCH), "INVALIDATED", "R2", data)
                self.assertEqual(state(self.t, b, h, obs, BRANCH, off={"R2S"}).state, "VERIFIED_REUSE")
                self.t = TI.Toy(pathlib.Path(tempfile.mkdtemp(dir=self._tmp.name)) / "repo")

    # 6 ------------------------------------------------------------------------------------------------------------
    def test_6_changed_transitive_dependency(self):
        """K -> toy -> util -> deep: the body of deep.base changes. It was loaded, never read as data, so the observed
        read set alone says nothing; the reference through util decides (I2). An import-time change of the same
        module: R6. Red-before: the name tier off — reuse."""
        t = self.t
        t.files["aisef2/deep.py"] = "def base(x):\n    return x\n"
        t.files["aisef2/util.py"] = "from aisef2 import deep\n\n\ndef inc(x):\n    return deep.base(x) + 1\n"
        t.reentry()
        b = t.commit()
        t.edit("aisef2/deep.py", "return x\n", "return x + 0\n")
        h = t.commit()
        obs = record(t, [K])
        self.assertIn("aisef2/deep.py", obs[K]["loaded"])
        self.assertNotEqual(obs[K]["opened"].get("aisef2/deep.py"), "data")
        self.assertNonReuse(state(t, b, h, obs, INC), "INVALIDATED", "I2", "aisef2/deep.py::base")
        self.assertEqual(state(t, b, h, obs, INC, off={"I2"}).state, "VERIFIED_REUSE")
        t.files["aisef2/deep.py"] = "import sys\n\nLIMIT = sys.getrecursionlimit()\n\n\n" + t.files["aisef2/deep.py"]
        h2 = t.commit()
        self.assertNonReuse(state(t, b, h2, record(t, [K]), INC), "INVALIDATED", "R6", "aisef2/deep.py")

    # 7 ------------------------------------------------------------------------------------------------------------
    def test_7_missing_or_truncated_trace_files(self):
        """A witness file deleted, cut short, or added after recording: R1 (what it held is unknown). A hook record
        whose process never reached normal exit (audit) and a strace file with no `+++` line: R1 through the
        derived completeness. Red-before: R1 off — reuse."""
        b, h = self.helper_change()
        for name, damage, why in (
                ("deleted", lambda w: next((w / "hook").glob("*.ev")).unlink(), "is missing"),
                ("truncated", lambda w: (w / "manifest.json").write_bytes((w / "manifest.json").read_bytes()[:-40]),
                 "not the bytes recorded"),
                ("added", lambda w: (w / "hook" / "999-x.ev").write_text("S\t999\t1\n"), "was not recorded")):
            with self.subTest(name):
                rec = record(self.t, [K])[K]
                damage(pathlib.Path(rec["witness"]["dir"]))
                self.assertNonReuse(state(self.t, b, h, {K: rec}), "INVALIDATED", "R1", why)
                self.assertEqual(state(self.t, b, h, {K: rec}, off={"R1"}).state, "VERIFIED_REUSE")
        rec = record(self.t, [K])[K]   # the root process's E line removed, the record derived again: unterminated
        w = pathlib.Path(rec["witness"]["dir"])
        for f in (w / "hook").glob("*.ev"):
            f.write_text("".join(x for x in f.read_text().splitlines(keepends=True) if not x.startswith("E\t")))
        (w / OBS.RECORD).unlink()
        rec = OBS.finish(w)
        want = "truncated_trace_files" if STRACE else "unterminated_processes 1"
        if STRACE:   # under strace the hook's exit marker is not needed: cut the root trace's +++ line instead
            for f in (w / "strace").glob("tr.*"):
                f.write_text("".join(x for x in f.read_text().splitlines(keepends=True) if not x.startswith("+++")))
            (w / OBS.RECORD).unlink()
            rec = OBS.finish(w)
        self.assertNonReuse(state(self.t, b, h, {K: rec}), "INVALIDATED", "R1", want)

    # 8 ------------------------------------------------------------------------------------------------------------
    def test_8_tampered_provenance_or_missing_measurement(self):
        """(a) A record edited after recording (a data read deleted): it is not what its witness derives to — R0.
        Red-before: an engine that does not re-derive (verify always passes) reuses it. (b) A consistent record whose
        provenance names another tree, kill file, runner or recorder: R0. (c) No witness at all, no record of the kill
        file, or a duplicate record: R0. (d) The mutation entry has no committed counterpart at the basis: I7."""
        t = self.t
        TI.add_test(t, K, "test_inc", "    def test_scan(self):\n"
                    "        self.assertNotIn('TODO', pathlib.Path(toy.__file__).read_text())\n", "import pathlib\n")
        b = t.commit()
        t.files["aisef2/toy.py"] += "# note\n"
        h = t.commit()
        rec = record(t, [K])[K]
        self.assertEqual(rec["opened"]["aisef2/toy.py"], "data")
        self.assertNonReuse(state(t, b, h, {K: rec}), "INVALIDATED", "R2", "reads aisef2/toy.py as data")
        forged = {**rec, "opened": {k: v for k, v in rec["opened"].items() if k != "aisef2/toy.py"}}
        self.assertNonReuse(state(t, b, h, {K: forged}), "UNRESOLVED", "R0", "not what its witness says (opened)")
        with mock.patch.object(OBS, "verify", lambda r: (None, [])):
            self.assertEqual(state(t, b, h, {K: forged}).state, "VERIFIED_REUSE")
        for name, edit, why in (
                ("tree", lambda m: m.update(tree_sha256="0" * 64), "tree_sha256 is not head's runner tree"),
                ("kill file", lambda m: m["kill_file"].update(sha256="0" * 64), "kill file it ran is not head's"),
                ("runner", lambda m: m.update(runner_sha256="0" * 64), "not run by head's runner"),
                ("recorder", lambda m: m.update(observe_sha256="0" * 64), "not recorded by head's recorder"),
                ("commit", lambda m: m.update(commit=b), "another tree")):
            with self.subTest(name):
                self.assertNonReuse(state(t, b, h, {K: refinish(record(t, [K])[K], edit)}), "UNRESOLVED", "R0", why)
        bare = {k: v for k, v in record(t, [K])[K].items() if k != "witness"}
        self.assertNonReuse(state(t, b, h, {K: bare}), "UNRESOLVED", "R0", "it has no witness")
        self.assertNonReuse(state(t, b, h, {}), "UNRESOLVED", "R0", f"no admissible observation of {K}")
        twice, both = (pathlib.Path(tempfile.mkdtemp(dir=self._tmp.name)) for _ in range(2))
        for i in range(2):   # two recordings of one kill file in one --observations directory: both refused
            shutil.copytree(OBS.record(t.root, K, twice / str(i)), both / str(i))
        self.assertEqual(OBS.load(both)[K], {"format": "duplicate"})
        self.assertNonReuse(state(t, b, h, OBS.load(both)), "UNRESOLVED", "R0", "not an observation record")
        t2 = TI.Toy(pathlib.Path(tempfile.mkdtemp(dir=self._tmp.name)) / "repo")   # (d) missing original measurement
        del t2.entries[TGT]
        b2 = t2.commit()
        t2.reentry()
        h2 = t2.commit()
        s = state(t2, b2, h2, record(t2, [K]))
        self.assertNonReuse(s, "INVALIDATED", "I7", "no committed counterpart")

    # 9 ------------------------------------------------------------------------------------------------------------
    def test_9_modified_kill_test_or_mutant_generator(self):
        """(a) The kill test weakened after its observation: I4 fires; with I4 off the stale observation is refused
        (R0); with both off it would be reused (red-before). (b) The generator changed: I5, even with a fresh, complete
        observation of head; with I5 off it would be reused (red-before)."""
        t = self.t
        b = t.commit()
        old = record(t, [K])
        t.edit(K, "self.assertEqual(util.inc(1), 2)", "pass")
        h = t.commit()
        self.assertNonReuse(state(t, b, h, old), "INVALIDATED", "I4", K)
        self.assertNonReuse(state(t, b, h, old, off={"I4"}), "UNRESOLVED", "R0", "another tree")
        self.assertEqual(state(t, b, h, old, off={"I4", "R0"}).state, "VERIFIED_REUSE")
        t2 = TI.Toy(pathlib.Path(tempfile.mkdtemp(dir=self._tmp.name)) / "repo")
        b2 = t2.commit()
        t2.harness = t2.harness.replace("ast.Gt: ast.LtE", "ast.Gt: ast.Lt", 1)
        h2 = t2.commit()
        fresh = record(t2, [K])
        self.assertNonReuse(state(t2, b2, h2, fresh), "INVALIDATED", "I5", "generator output differs")
        self.assertEqual(state(t2, b2, h2, fresh, off={"I5"}).state, "VERIFIED_REUSE")


class StraceParser(unittest.TestCase):
    """The strace parser and its reconciliation with the hook, on recorded (normalized) and hand-made traces."""

    def test_lines(self):
        t = OBS.parse_strace([
            'execve("/usr/bin/python3", ["python3", "-m", "x"], 0x7ffd /* 17 vars */) = 0',
            'openat(AT_FDCWD</w/tree>, "aisef2/toy.py", O_RDONLY|O_CLOEXEC) = 3</w/tree/aisef2/toy.py>',
            'newfstatat(AT_FDCWD</w/tree>, "aisef2", {st_mode=S_IFDIR|0755, st_size=4096, ...}, 0) = 0',
            'openat(AT_FDCWD</w/tree>, "tests/v2", O_RDONLY|O_NONBLOCK|O_CLOEXEC|O_DIRECTORY) = 4</w/tree/tests/v2>',
            'getdents64(4</w/tree/tests/v2>, 0x1 /* 6 entries */, 32768) = 152',
            'getdents64(4</w/tree/tests/v2>, 0x1 /* 0 entries */, 32768) = 0',
            'readlink("link", "aisef2/toy.py", 4096) = 13',
            'clone3({flags=CLONE_VM|CLONE_THREAD|CLONE_SETTLS, child_tid=0x1} => {parent_tid=[12]}, 88) = 12',
            'vfork()                                 = 13',
            '--- SIGCHLD {si_signo=SIGCHLD, si_code=CLD_EXITED, si_pid=13} ---',
            'openat(AT_FDCWD</w/tree>, "long', ' <unfinished ...>',
            'newfstatat(AT_FDCWD</w/tree>, "a" <unfinished ...>',
            '<... newfstatat resumed>{st_mode=S_IFREG|0644, ...}, 0) = 0',
            'openat(AT_FDCWD</w/tree>, "aaaa"..., O_RDONLY) = -1 ENOENT (No such file or directory)',
            'chdir("sub") = 0',
            'access("rel", F_OK) = -1 ENOENT (No such file or directory)',
            'getdents64(5, 0x1 /* 1 entries */, 32768) = 24',
            '+++ exited with 0 +++'])
        kinds = [e[:4] for e in t["ev"]]
        self.assertIn(("x", None, None, "/usr/bin/python3"), kinds)   # the argv array is not a path
        self.assertIn(("o", "AT_FDCWD", "/w/tree", "aisef2/toy.py"), kinds)
        self.assertEqual(sum(1 for e in kinds if e[0] == "l"), 1)   # one listing for one open, two getdents
        self.assertIn(("s", None, None, "link"), kinds)   # readlink: the link text is not a lookup
        self.assertNotIn(("s", None, None, "aisef2/toy.py"), kinds)
        self.assertEqual(t["created"], [(12, True), (13, False)])
        self.assertIn(("s", "AT_FDCWD", "/w/tree", "a"), kinds)   # unfinished ... resumed joined
        self.assertEqual((t["cut"], t["bad"], t["nofd"], t["end"]), (1, 1, 1, True))   # "aaaa"..., the lone line, fd 5
        self.assertIn(("cd", None, None, "sub"), kinds)
        self.assertEqual(OBS._c(r"a\303\251\x41\"\\\n"), 'aéA"\\\n')

    def witness(self, files: dict, procs: dict) -> pathlib.Path:
        """A witness with the given strace files {tid: text} and hook records {pid: lines} under tree /w/tree."""
        w = pathlib.Path(tempfile.mkdtemp(prefix="aisef-strace-"))
        self.addCleanup(shutil.rmtree, w, True)
        (w / "strace").mkdir()
        (w / "hook").mkdir()
        for tid, text in files.items():
            (w / "strace" / f"tr.{tid}").write_text(text, encoding="utf-8")
        for pid, lines in procs.items():
            (w / "hook" / f"{pid}-x.ev").write_text("".join(x + "\n" for x in lines), encoding="utf-8")
        (w / "manifest.json").write_text(json.dumps({"tree": "/w/tree", "checkout": "/w/checkout", "backend": "strace",
                                                     "row": {"outcome": "PASS", "exit": 0, "ran": 1}}), encoding="utf-8")
        return w

    def test_reconciliation(self):
        root = ('openat(AT_FDCWD</w/tree>, "aisef2/toy.py", O_RDONLY|O_CLOEXEC) = 3</w/tree/aisef2/toy.py>\n'
                'newfstatat(AT_FDCWD</w/tree>, "aisef2/toy.py", {st_mode=S_IFREG|0644, ...}, 0) = 0\n'
                'newfstatat(AT_FDCWD</w/tree>, "aisef2/data.txt", {st_mode=S_IFREG|0644, ...}, 0) = 0\n'
                'openat(AT_FDCWD</w/tree>, "aisef2/link", O_RDONLY) = 4</w/tree/aisef2/target.txt>\n'
                'openat(AT_FDCWD</w/tree>, "aisef2", O_RDONLY|O_DIRECTORY) = 5</w/tree/aisef2>\n'
                'getdents64(5</w/tree/aisef2>, 0x1 /* 3 entries */, 32768) = 80\n'
                'vfork() = 101\nvfork() = 102\n+++ exited with 0 +++\n')
        kid = ('execve("/usr/bin/wc", ["wc", "-l", "aisef2/toy.py"], 0x1 /* 9 vars */) = 0\n'
               'openat(AT_FDCWD</w/tree>, "aisef2/toy.py", O_RDONLY) = 3</w/tree/aisef2/toy.py>\n')   # no +++: cut
        hook = ["S\t100\t1", "o\tload\t/w/tree/aisef2/toy.py", "m\t/w/tree/aisef2/toy.py", "l\town\t/w/tree/aisef2\t<native>",
                "C\tsubprocess.Popen\t0\t0\t['wc']", "E\t0"]
        rec = OBS.derive(self.witness({100: root, 101: kid}, {100: hook}))
        self.assertEqual(rec["opened"], {"aisef2/data.txt": "data", "aisef2/link": "data", "aisef2/target.txt": "data",
                                         "aisef2/toy.py": "data"})   # the child's read makes toy.py data
        self.assertEqual(rec["listed"], [])   # the import system's own listing, accounted for by the hook
        self.assertEqual(rec["loaded"], ["aisef2/toy.py"])
        c = rec["completeness"]
        self.assertEqual((c["untraced_children"], c["missing_trace_files"], c["truncated_trace_files"]), (1, 1, 1))
        self.assertEqual((rec["children"]["traced"], rec["os_trace"]), (1, True))
        alone = OBS.derive(self.witness({100: root.replace("vfork() = 101\nvfork() = 102\n", "")}, {100: hook}))
        self.assertEqual(alone["opened"]["aisef2/toy.py"], "load")   # matched by the hook's own load: not data
        self.assertEqual({k: v for k, v in alone["completeness"].items() if v}, {})
        untraced = OBS.derive(self.witness({100: root.replace("vfork() = 102\n", "") + ""}, {100: hook, 200: ["S\t200\t100"]}))
        self.assertGreaterEqual(untraced["completeness"]["unaccounted_processes"], 1)   # a hooked pid no trace shows
        listed = OBS.derive(self.witness({100: root}, {100: hook[:3] + hook[4:]}))   # the hook did not make the listing
        self.assertEqual((listed["listed"], listed["listed_by"]), (["aisef2"], {"aisef2": ["<native>"]}))

    def test_recorded_fixture(self):
        """A real strace -f -ff -y recording of a toy kill file that runs `wc` (Linux, strace 6.8, CPython 3.12),
        normalized: the tree is /w/tree, every other host path /w/x. The child is traced, its read is data."""
        fx = json.loads(FIXTURE.read_text(encoding="utf-8"))
        w = self.witness({int(k): v for k, v in fx["strace"].items()}, {int(k): v.splitlines() for k, v in fx["hook"].items()})
        rec = OBS.derive(w)
        self.assertEqual({k: v for k, v in rec["completeness"].items() if v}, {})
        self.assertEqual(rec["children"]["traced"], fx["expect"]["traced"])
        self.assertEqual(rec["opened"].get("aisef2/toy.py"), "data")
        self.assertIn("tests/v2/test_k.py", rec["loaded"])
        self.assertEqual(rec["listed"], [])


@unittest.skipUnless(STRACE, NO_STRACE)
class StraceBackend(Base):
    """The strace backend on this Linux host: complete, every process traced, a child's read is data."""

    def test_backend_records_children_and_threads(self):
        t = self.t
        TI.add_test(t, K, "test_inc", "    def test_kids(self):\n"
                    "        threading.Thread(target=lambda: os.stat(os.path.dirname(toy.__file__))).start()\n"
                    "        p = os.path.join(os.path.dirname(toy.__file__), 'to' + 'y' + '.py')\n"
                    "        subprocess.run(['wc', '-l', p], check=True, capture_output=True)\n"
                    "        subprocess.run([sys.executable, '-c', 'pass'], check=True, env={'PATH': os.environ['PATH']})\n",
                    "import os\nimport subprocess\nimport sys\nimport threading\n")
        b = t.commit()
        t.files["aisef2/toy.py"] += "# one more line\n"
        h = t.commit()
        rec = record(t, [K], "strace")[K]
        self.assertEqual((rec["backend"], rec["os_trace"]), ("strace", True))
        self.assertEqual({k: v for k, v in rec["completeness"].items() if v}, {})
        self.assertGreaterEqual(rec["children"]["traced"], 2)
        self.assertEqual(rec["children"]["unhooked_python"], 1)   # traced anyway: not an incompleteness
        self.assertEqual(rec["opened"]["aisef2/toy.py"], "data")
        self.assertTrue(rec["tools"]["strace"].startswith("strace"))
        self.assertNonReuse(state(t, b, h, {K: rec}), "INVALIDATED", "R2", "reads aisef2/toy.py as data")


if __name__ == "__main__":
    unittest.main()
