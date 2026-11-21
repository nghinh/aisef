"""Review 1 of the F5 recorder (2026-11-22): one regression test per confirmed finding (A3-SND-1..8, STR-1, BOTH-1,
AUD-1, PROV-1..3) and per LOW finding fixed in this pass (A3-SND-9, AUD-2, STR-2..5, PROV-4 in part). Each test is red
on the 8a31f7c8 recorder and engine (validation/v23/observe.py, impact.py at that commit: the reuse, or the record,
the finding describes) and green here: every fix only turns a reuse into a non-reuse. Where an `_OFF` key covers the
new guard, the test also shows the same change reused with that rule off (the guard is load-bearing).

Real recordings run a toy's kill file through the toy's own runner (tests/v23/test_v23_impact.py), with the backend
this host has (strace on Linux when present, else audit); hand-made traces go through observe.derive(). Not a kill
file (tests/v23 is outside every mutation.COPY root: Amendment A2)."""

from __future__ import annotations

import contextlib
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.v23 import test_v23_impact as TI  # noqa: E402
from tests.v23 import test_v23_observe as TO  # noqa: E402
from validation.v23 import impact  # noqa: E402
from validation.v23 import observe as OBS  # noqa: E402

STRACE = TO.STRACE
K, TGT = TI.K, TI.TGT
HEAD = ("import os\nimport pathlib\nimport subprocess\nimport sys\nimport tempfile\nimport unittest\n\n"
        "from aisef2 import {m}\n\nHERE = os.path.dirname({m}.__file__)\n\n\nclass T(unittest.TestCase):\n")
CFG = "def f(x):\n    if x > 5:\n        return 1\n    return 0\n"
#: the kill test of aisef2/cfg.py::f reads aisef2/limit.txt by a name no literal joins; Δ changes that file
CFG_KILL = "        n = int({read})\n        self.assertTrue(cfg.f(n) == 0 or n > 5)\n"
LIMIT = "''.join(['lim', 'it.txt'])"
EXECVE = TI.EXECVE


def toy(self, target: str, kill: str, files: dict, change) -> tuple[TI.Toy, str, str]:
    """A toy whose `target` is killed by `kill`: the basis commit, `change(toy)`, the head commit."""
    t = TI.Toy(pathlib.Path(tempfile.mkdtemp(dir=self._tmp.name)) / "repo")
    t.files.update(files)
    t.set_targets({**TI.TARGETS, target: [kill]})
    t.entries[target] = TI.entry(t.files, target, kill=[kill])
    b = t.commit()
    change(t)
    return t, b, t.commit()


def remove(t: TI.Toy, rel: str) -> None:
    """`rel` deleted from the toy, and its directory when that leaves it empty (as a checkout of head would)."""
    del t.files[rel]
    (t.root / rel).unlink()
    with contextlib.suppress(OSError):
        (t.root / rel).parent.rmdir()


def cfg_toy(self, method: str, change=None):
    """aisef2/cfg.py::f, killed by tests/v2/test_cfg.py's test_f (`method`); Δ = aisef2/limit.txt 3 -> 9."""
    kill = "tests/v2/test_cfg.py"
    files = {"aisef2/cfg.py": CFG, "aisef2/limit.txt": "3\n", kill: HEAD.format(m="cfg") + "    def test_f(self):\n" + method}
    t, b, h = toy(self, "aisef2/cfg.py::f", kill, files, change or (lambda t: t.files.update({"aisef2/limit.txt": "9\n"})))
    return t, b, h, kill


def witness(case: unittest.TestCase, files: dict, procs: dict, kill: str = K, backend: str = "strace") -> pathlib.Path:
    """A hand-made witness (TO.StraceParser.witness) whose manifest names the kill file."""
    w = TO.StraceParser.witness(case, files, procs, backend)
    man = json.loads((w / "manifest.json").read_text(encoding="utf-8"))
    man["kill_file"] = {"path": kill}
    (w / "manifest.json").write_text(json.dumps(man), encoding="utf-8")
    return w


ROOT_HOOK = ["S\t100\t1", f"m\t/w/tree/{K}"]   # the 8a31f7c8 head format (both recorders parse it)
ROOT_TRACE = EXECVE + "vfork() = 101\n+++ exited with 0 +++\n"


class Review1(TO.Base):
    def obs_state(self, t, b, h, kill, target, off=()):
        return TO.state(t, b, h, TO.record(t, [kill]), target, off)

    # A3-SND-1 ------------------------------------------------------------------------------------------------------
    def test_snd1_a_namespace_package_that_appears_or_vanishes(self):
        """A directory (no __init__.py) that S(F) imports by name appears or vanishes: the import resolves otherwise.
        R5 judges directories as it judges module files. 8a31f7c8: reuse (audit; and strace for the vanish case)."""
        opt = ("def pick(x):\n    try:\n        import aisef2.plugins  # noqa: F401\n    except ImportError:\n"
               "        return x > 1\n    return None\n")
        kill = "tests/v2/test_opt.py"
        files = {"aisef2/opt.py": opt, kill: HEAD.format(m="opt") + "    def test_pick(self):\n"
                 "        self.assertIn(opt.pick(2), (True, None))\n"}
        readme = "aisef2/plugins/README.txt"
        for how, before, change in (("added", {}, lambda t: t.files.update({readme: "x\n"})),
                                    ("removed", {readme: "x\n"}, lambda t: remove(t, readme))):
            with self.subTest(how):
                t, b, h = toy(self, "aisef2/opt.py::pick", kill, {**files, **before}, change)
                s = self.obs_state(t, b, h, kill, "aisef2/opt.py::pick")
                self.assertNonReuse(s, "INVALIDATED", "R5", f"directory aisef2/plugins was {how}")
                if how == "removed" or not STRACE:
                    self.assertEqual(self.obs_state(t, b, h, kill, "aisef2/opt.py::pick", {"R5"}).state, "VERIFIED_REUSE")

    # A3-SND-2 ------------------------------------------------------------------------------------------------------
    def test_snd2_a_computed_import_only_a_mutant_takes(self):
        """sel.pick loads, on the branch only a mutant takes, a module outside S(F) by a computed name; Δ changes that
        module's data (B) or the module itself (B2). With Δ ≠ ∅ any open R8 site in what F ran refuses tier S, not
        only when a Δ .py of S(F) changed defs. 8a31f7c8: reuse."""
        sel = ("import importlib\n\n\ndef pick(x):\n    if x > 5:\n"
               "        return importlib.import_module('aisef2.' + 'handlers').read()\n    return 'small'\n")
        kill = "tests/v2/test_sel.py"
        for name, handlers, extra, assertion, change in (
                ("B", "import pathlib\n\n\ndef read():\n    return (pathlib.Path(__file__).parent / 'handlers.txt').read_text()\n",
                 {"aisef2/handlers.txt": "one\n"}, "self.assertNotEqual(sel.pick(1), 'one\\n')",
                 lambda t: t.files.update({"aisef2/handlers.txt": "two\n"})),
                ("B2", "def read():\n    return 1\n", {}, "self.assertNotEqual(sel.pick(1), 1)",
                 lambda t: t.files.update({"aisef2/handlers.py": "def read():\n    return 2\n"}))):
            with self.subTest(name):
                files = {"aisef2/sel.py": sel, "aisef2/handlers.py": handlers, **extra,
                         kill: HEAD.format(m="sel") + f"    def test_pick(self):\n        {assertion}\n"}
                t, b, h = toy(self, "aisef2/sel.py::pick", kill, files, change)
                self.assertNotIn("aisef2/handlers.py", impact.kill_closure(t.root, b, h, kill))
                s = self.obs_state(t, b, h, kill, "aisef2/sel.py::pick")
                self.assertNonReuse(s, "INVALIDATED", "R8", "computed-name site at aisef2/sel.py")
                self.assertEqual(self.obs_state(t, b, h, kill, "aisef2/sel.py::pick", {"R8"}).state, "VERIFIED_REUSE")

    # A3-SND-3 ------------------------------------------------------------------------------------------------------
    def test_snd3_a_literal_path_anchored_at_another_modules_file(self):
        """The kill test reads aisef2/data/one.txt through branch.__file__ only on a branch a mutant takes: the
        construction's literal part is matched at any depth (R2S). 8a31f7c8: reuse."""
        kill = "tests/v2/test_branch.py"
        for name, read in (("pathlib", "(pathlib.Path(branch.__file__).parent / 'data' / 'one.txt')"),
                           ("os.path", "pathlib.Path(os.path.join(os.path.dirname(branch.__file__), 'data', 'one.txt'))"),
                           ("computed", "(pathlib.Path(branch.__file__).parent / 'data' / ('o' + str(1 - 1)[:0] + 'ne.txt'))")):
            with self.subTest(name):
                files = {"aisef2/branch.py": "def pick(x):\n    return x > 5\n", "aisef2/data/one.txt": "one\n",
                         kill: HEAD.format(m="branch") + "    def test_pick(self):\n        if branch.pick(1):\n"
                         f"            self.assertEqual({read}.read_text(), 'two\\n')\n"
                         "        self.assertIn(branch.pick(1), (False, True))\n"}
                t, b, h = toy(self, "aisef2/branch.py::pick", kill, files,
                              lambda t: t.files.update({"aisef2/data/one.txt": "two\n"}))
                s = self.obs_state(t, b, h, kill, "aisef2/branch.py::pick")
                self.assertNonReuse(s, "INVALIDATED", "R2", "a path construction holding 'data")
                self.assertEqual(self.obs_state(t, b, h, kill, "aisef2/branch.py::pick", {"R2S"}).state, "VERIFIED_REUSE")

    # A3-SND-4 ------------------------------------------------------------------------------------------------------
    def test_snd4_the_kill_files_own_load_tests_is_not_unittests_walk(self):
        """load_tests lists aisef2 (L) or stats a file there (S) and drops test_pick when aisef2/flag.txt exists:
        tree code between unittest's walk and the call makes it a run, not the walk. 8a31f7c8: both recorded as the
        walk's (`l own`, `w`) and dropped — reuse."""
        kill = "tests/v2/test_branch.py"
        for name, probe, comp, why in (
                ("L", "flag = any(n.startswith('fl' + 'ag') for n in os.listdir(HERE))", "R3", "lists aisef2"),
                ("S", "try:\n        flag = os.stat(os.path.join(HERE, ''.join(['fl', 'ag.txt']))) is not None\n"
                      "    except OSError:\n        flag = False", "R2", "aisef2/flag.txt")):
            with self.subTest(name):
                files = {"aisef2/branch.py": "def pick(x):\n    return x > 5\n",
                         kill: HEAD.format(m="branch") + "    def test_pick(self):\n        self.assertTrue(branch.pick(6))\n\n\n"
                         "class U(unittest.TestCase):\n    def test_ok(self):\n        self.assertTrue(True)\n\n\n"
                         f"def load_tests(loader, tests, pattern):\n    {probe}\n    if flag:\n"
                         "        return loader.loadTestsFromTestCase(U)\n    return tests\n"}
                t, b, h = toy(self, "aisef2/branch.py::pick", kill, files, lambda t: t.files.update({"aisef2/flag.txt": "x\n"}))
                self.assertNonReuse(self.obs_state(t, b, h, kill, "aisef2/branch.py::pick"), "INVALIDATED", comp, why)

    # A3-SND-5 (and PROV-6) -----------------------------------------------------------------------------------------
    def test_snd5_a_directory_head_does_not_have_is_refused_by_the_recorder(self):
        """An untracked aisef2/plugins/__pycache__/ (a branch switch leaves it) makes the runner's copy hold an empty
        aisef2/plugins that head lacks; the tree digest covers files only. The recorder refuses. 8a31f7c8: recorded
        and admitted (tree_sha256 equal to head's)."""
        t = self.t
        t.commit()
        t.edit("aisef2/toy.py", "return x * 2", "return x * 3")
        h = t.commit()
        stale = t.root / "aisef2" / "plugins" / "__pycache__" / "__init__.cpython-314.pyc"
        stale.parent.mkdir(parents=True)
        stale.write_bytes(b"\0")
        self.assertEqual(impact._dirty(t.root, h, TI.M.COPY), [])   # what _dirty alone cannot see
        with self.assertRaisesRegex(SystemExit, "no file of HEAD implies: aisef2/plugins"):
            TO.record(t, [K])

    # A3-SND-6 ------------------------------------------------------------------------------------------------------
    def test_snd6_annotated_walrus_and_unpacked_bindings(self):
        """test_5's computed variant with the directory bound by an annotated assignment, a walrus, or a tuple
        unpacked: R2S substitutes every single-name binding. 8a31f7c8: reuse."""
        kill = "tests/v2/test_branch.py"
        for name, bind, use in (("annotated", "DATA: str = 'aisef2'\n", "DATA"),
                                ("walrus", "", "(DATA := 'aisef2')"),
                                ("tuple", "DATA, _N = 'aisef2', 0\n", "DATA")):
            with self.subTest(name):
                branch = ("import pathlib\n\nROOT = pathlib.Path(__file__).resolve().parents[1]\n" + bind + "\n\n"
                          f"def pick(x):\n    if x > 5:\n        return (pathlib.Path(ROOT, {use}) / ('branch' + str(x % 2)"
                          " + '.txt')).read_text()\n    return 'small'\n")
                files = {"aisef2/branch.py": branch, "aisef2/branch1.txt": "one\n",
                         kill: HEAD.format(m="branch") + "    def test_pick(self):\n"
                         "        self.assertNotEqual(branch.pick(1), 'one\\n')\n"}
                t, b, h = toy(self, "aisef2/branch.py::pick", kill, files,
                              lambda t: t.files.update({"aisef2/branch1.txt": "two\n"}))
                s = self.obs_state(t, b, h, kill, "aisef2/branch.py::pick")
                self.assertNonReuse(s, "INVALIDATED", "R2", "aisef2")
                self.assertEqual(self.obs_state(t, b, h, kill, "aisef2/branch.py::pick", {"R2S"}).state, "VERIFIED_REUSE")

    # A3-SND-7, STR-1 -----------------------------------------------------------------------------------------------
    def test_snd7_str1_an_image_exec_d_in_a_hooked_pid_is_observed_for_data_only(self):
        """strace: a forked child that ran the hook (F) execs `test -d aisef2/newpkg`; or the hooked root execs it.
        The import-system discount (a directory lookup in a hooked process) no longer survives the exec.
        8a31f7c8: the lookup is discounted — no data, no R2."""
        stat = 'newfstatat(AT_FDCWD</w/tree>, "aisef2/newpkg", {st_mode=S_IFDIR|0755, ...}, 0) = 0\n'
        test = 'execve("/usr/bin/test", ["test", "-d", "aisef2/newpkg"], 0x1 /* 1 vars */) = 0\n'
        with self.subTest("a forked child execs"):
            child = OBS.derive(witness(self, {100: ROOT_TRACE, 101: test + stat + "+++ exited with 0 +++\n"},
                                       {100: ROOT_HOOK + ["C\tos.fork\t1\t1\t-", "E\t0"], 101: ["F\t101\t100"]}))
            self.assertEqual(child["opened"].get("aisef2/newpkg"), "data")
        with self.subTest("the hooked root execs"):
            root = OBS.derive(witness(self, {100: EXECVE + test + stat + "+++ exited with 0 +++\n"},
                                      {100: ROOT_HOOK + ["E\t0"]}))
            self.assertEqual(root["opened"].get("aisef2/newpkg"), "data")
        before = OBS.derive(witness(self, {100: EXECVE + stat + "+++ exited with 0 +++\n"}, {100: ROOT_HOOK + ["E\t0"]}))
        self.assertNotIn("aisef2/newpkg", before["opened"])   # the same lookup by the hooked image itself: the discount

    # BOTH-1 --------------------------------------------------------------------------------------------------------
    def test_both1_chdir_directory_opens_statvfs_and_pathconf_are_lookups(self):
        """strace: a failed or successful chdir and a failed O_DIRECTORY open are lookups (data). audit: os.chdir,
        os.statvfs and os.pathconf are recorded as lookups, and a lookup of a directory that is absent at the basis
        and present at head is R2. 8a31f7c8: none of them recorded."""
        lines = ('chdir("/w/tree/aisef2/newpkg") = -1 ENOENT (No such file or directory)\n'
                 'chdir("/w/tree/aisef2/other") = 0\n'
                 'openat(AT_FDCWD</w/tree>, "aisef2/gone", O_RDONLY|O_DIRECTORY) = -1 ENOENT (No such file or directory)\n')
        with self.subTest("strace"):
            rec = OBS.derive(witness(self, {100: EXECVE + lines + "+++ exited with 0 +++\n"}, {100: ROOT_HOOK + ["E\t0"]}))
            self.assertEqual({p: rec["opened"].get(p) for p in ("aisef2/newpkg", "aisef2/other", "aisef2/gone")},
                             dict.fromkeys(("aisef2/newpkg", "aisef2/other", "aisef2/gone"), "data"))
        for name, call in (("chdir", "os.chdir(p)"), ("statvfs", "os.statvfs(p)"), ("pathconf", "os.pathconf(p, 'PC_NAME_MAX')")):
            with self.subTest(name):
                t, b, h, kill = cfg_toy(self, "        p = os.path.join(HERE, ''.join(['new', 'pkg']))\n"
                                        f"        try:\n            {call}\n        except OSError:\n            pass\n"
                                        "        os.chdir(os.path.dirname(HERE))\n" + CFG_KILL.format(read="1"),
                                        lambda t: t.files.update({"aisef2/newpkg/notes.txt": "x\n"}))
                s = self.obs_state(t, b, h, kill, "aisef2/cfg.py::f")
                self.assertNonReuse(s, "INVALIDATED", "R2", "looked up aisef2/newpkg, which was absent and is dir")

    # AUD-1 ---------------------------------------------------------------------------------------------------------
    def test_aud1_launch_accounting_by_identity(self):
        """audit: a child started by _posixsubprocess.fork_exec alone (multiprocessing's spawnv_passfds) is a
        launch; `python -W ignore -E` is predicted unhooked (-W takes a value); records and launches are matched by
        parent pid and argv, never netted. strace: every child is traced, its read is data. 8a31f7c8: complete
        records (no untraced child) — reuse."""
        for name, method, untraced in (
                ("fork_exec", "        from concurrent.futures import process as cfp\n"
                              "        pid = cfp.mp.util.spawnv_passfds(b'/bin/sh', [b'sh', b'-c', b'cat \"$1\" > /dev/null', b'sh',"
                              f" os.path.join(HERE, {LIMIT}).encode()], ())\n"
                              "        os.waitpid(pid, 0)\n", 1),
                ("-W value", "        for _ in range(2):\n"
                             "            subprocess.run([sys.executable, '-W', 'ignore', '-E', '-c', 'import sys; open(sys.argv[1]).read()',"
                             f" os.path.join(HERE, {LIMIT})], check=True)\n"
                             "        from concurrent.futures import ProcessPoolExecutor\n"
                             "        with ProcessPoolExecutor(1) as ex:\n            ex.submit(abs, 1).result()\n", 2)):
            with self.subTest(name):
                t, b, h, kill = cfg_toy(self, method + CFG_KILL.format(read="1"))
                rec = TO.record(t, [kill])[kill]
                if STRACE:
                    self.assertEqual(rec["opened"].get("aisef2/limit.txt"), "data")
                else:
                    self.assertEqual(rec["completeness"]["untraced_children"], untraced, rec["completeness"])
                s = TO.state(t, b, h, {kill: rec}, "aisef2/cfg.py::f")
                self.assertNonReuse(s, "INVALIDATED", "R2" if STRACE else "R1")

    def test_aud1_accounting_unit(self):
        """A surplus record and a missing one no longer cancel; a record is matched to its parent's launch."""
        root = {"kind": "S", "pid": 10, "ppid": 1, "argv": "['-m', 'x']",
                "C": [("subprocess.Popen", 1, 1, "['python-sh', '-c', 'x']")]}
        shell_kid = {"kind": "S", "pid": 12, "ppid": 11, "argv": "['-c', 'pass']", "C": []}   # ppid: the shell
        self.assertEqual(OBS._accounting([root, shell_kid], 10), (1, 1, root))
        kid = {"kind": "S", "pid": 11, "ppid": 10, "argv": "['-c', 'x']", "C": []}
        self.assertEqual(OBS._accounting([root, kid], 10), (0, 0, root))
        self.assertEqual(OBS._accounting([root, kid], 99)[2], None)   # not the pid the runner launched: no root

    # A3-SND-8 ------------------------------------------------------------------------------------------------------
    def test_snd8_reads_through_another_name_or_a_fake_python(self):
        """audit (C5/C8): the changed file read through another case of its name (folded in R2, every host: a
        synthetic record; a real one where the volume is case-insensitive), through a run-time symlink into the tree
        (an alias: R1), or by a shell named python-sh whose hooked grandchild balanced the count (identity matching:
        R1; strace: the shell's read is data, R2). 8a31f7c8: reuse in each."""
        with self.subTest("case alias, synthetic"):
            t, b, h, kill = cfg_toy(self, CFG_KILL.format(read="1"))
            obs = t.observe(h, {kill: ["aisef2/LIMIT.TXT"]})
            self.assertNonReuse(TO.state(t, b, h, obs, "aisef2/cfg.py::f"), "INVALIDATED", "R2", "reads aisef2/limit.txt")
        if os.path.exists(str(t.root / "aisef2" / "CFG.PY")):   # a case-insensitive volume
            with self.subTest("case alias, recorded"):
                t, b, h, kill = cfg_toy(self, CFG_KILL.format(
                    read="pathlib.Path(cfg.__file__).with_name(''.join(['LIM', 'IT.TXT'])).read_text()"))
                self.assertNonReuse(self.obs_state(t, b, h, kill, "aisef2/cfg.py::f"), "INVALIDATED", "R2",
                                    "aisef2/limit.txt")
        with self.subTest("symlink alias"):
            t, b, h, kill = cfg_toy(self, "        d = tempfile.mkdtemp()\n        os.symlink(HERE, os.path.join(d, 'alias'))\n"
                                    + CFG_KILL.format(read=f"pathlib.Path(d, 'alias', {LIMIT}).read_text()"))
            self.assertNonReuse(self.obs_state(t, b, h, kill, "aisef2/cfg.py::f"), "INVALIDATED", "R1", "aliases")
        with self.subTest("fake python"):
            t, b, h, kill = cfg_toy(self, "        d = tempfile.mkdtemp()\n        sh = os.path.join(d, 'python-sh')\n"
                                    "        os.symlink('/bin/sh', sh)\n"
                                    "        out = subprocess.run(['python-sh', '-c', 'cat \"$1\"; \"$2\" -c pass', 'x', "
                                    f"os.path.join(HERE, {LIMIT}), sys.executable],\n"
                                    "                             executable=sh, capture_output=True, text=True, check=True).stdout\n"
                                    + CFG_KILL.format(read="out"))
            s = self.obs_state(t, b, h, kill, "aisef2/cfg.py::f")
            self.assertNonReuse(s, "INVALIDATED", "R2" if STRACE else "R1", "" if STRACE else "unaccounted_processes 2")

    # PROV-1 --------------------------------------------------------------------------------------------------------
    def test_prov1_an_observation_based_reuse_carries_no_acceptance_basis(self):
        """N2 reused on an observation, with the basis the pinned v2.2.0 sha: the basis names the observation, the
        evidence says the recorder is no authority, and so does the report. 8a31f7c8: v2.2.0-accepted@<basis>."""
        c = TI.n2(self.t)
        with mock.patch.object(impact, "BASE", c.base):
            run = impact.classify(self.t.root, c.base, c.head, observations=c.obs)
            s = next(x for x in run if x.target == TGT)
            doc = impact.report(run, c.obs)
        self.assertEqual(s.state, "VERIFIED_REUSE")
        self.assertTrue(s.basis.startswith("observation:") and s.basis.endswith(f"@{c.base}"), s.basis)
        self.assertNotIn("accepted", s.basis)
        self.assertEqual(s.evidence["authority"], impact.OBSERVATION_AUTHORITY)
        self.assertEqual(doc["observation_authority"], impact.OBSERVATION_AUTHORITY)
        t = TI.Toy(pathlib.Path(tempfile.mkdtemp(dir=self._tmp.name)) / "repo")   # Δ = ∅: the label stands
        b = t.commit()
        with mock.patch.object(impact, "BASE", b):
            self.assertEqual(next(x for x in impact.classify(t.root, b, b, observations=t.observe(b))
                                  if x.target == TGT).basis, f"v2.2.0-accepted@{b}")

    # PROV-2 --------------------------------------------------------------------------------------------------------
    def test_prov2_the_hook_that_ran_is_bound(self):
        """A recorder whose in-memory hook differs from observe.py's (open events off) writes a truthful
        observe_sha256; the witness's copy of the hook is recomputed and compared: R0. 8a31f7c8: reuse."""
        t = self.t
        t.files["aisef2/data.txt"] = "alpha\n"
        TI.add_test(t, K, "test_inc", "    def test_data(self):\n"
                    "        p = pathlib.Path(toy.__file__).with_name(''.join(['da', 'ta.txt']))\n"
                    "        self.assertTrue(p.read_text().strip())\n", "import pathlib\n")
        b = t.commit()
        t.files["aisef2/data.txt"] = "beta\n"
        h = t.commit()
        rec = TO.record(t, [K], "audit", hook := TO.without("open"))
        self.assertEqual(rec[K]["observe_sha256"], OBS.own_sha256())
        self.assertNonReuse(TO.state(t, b, h, rec), "UNRESOLVED", "R0", "the hook it ran is not this recorder's")
        self.assertEqual(TO.state(t, b, h, rec, hook=hook).state, "VERIFIED_REUSE")

    def test_prov4_the_trace_set_is_bound(self):
        """A strace record whose trace was not taken with this recorder's syscall set: R0."""
        c = TI.n2(self.t)
        obs = self.t.observe(c.head, os_trace=True)
        self.assertEqual(TO.state(self.t, c.base, c.head, obs).state, "VERIFIED_REUSE")
        for kill, rec in obs.items():
            obs[kill] = TO.refinish(rec, lambda m: m["tools"].update(strace_events="%file"))
        self.assertNonReuse(TO.state(self.t, c.base, c.head, obs), "UNRESOLVED", "R0", "syscall set")

    # PROV-3 --------------------------------------------------------------------------------------------------------
    def test_prov3_the_root_record_is_identified(self):
        """The kill test removes its own hook record and starts a hooked child: no record is the runner's pid (audit)
        or the top task's (strace), and the kill file's code is not in `loaded`: R1. 8a31f7c8: the child's record
        passed for the root — reuse."""
        t = self.t
        TI.add_test(t, K, "test_inc", "    def test_gone(self):\n        import sitecustomize\n"
                    "        for n in os.listdir(sitecustomize._EV):\n"
                    "            if n.startswith(f'{os.getpid()}-'):\n                os.unlink(os.path.join(sitecustomize._EV, n))\n"
                    "        subprocess.run([sys.executable, '-c', 'pass'], check=True)\n",
                    "import os\nimport subprocess\nimport sys\n")
        b = t.commit()
        t.edit("aisef2/toy.py", "return x * 2", "return x * 3")
        h = t.commit()
        rec = TO.record(t, [K])[K]
        self.assertEqual((rec["completeness"]["missing_trace_files"], rec["completeness"]["kill_file_unseen"]), (1, 1))
        s = TO.state(t, b, h, {K: rec})   # strace: the unhooked root's discovery stats are data, and D2 may come first
        self.assertIn((s.state, s.component), {("INVALIDATED", "R1"), ("UNRESOLVED", "D2")}, s)

    # LOW, fixed: A3-SND-9 ------------------------------------------------------------------------------------------
    def test_snd9_a_mode_change_is_in_delta(self):
        """A mode-only change (the runner's copy keeps modes) is in Δ: without an observation R1, no longer Δ = ∅
        and VERIFIED_REUSE. 8a31f7c8: reuse."""
        t = self.t
        t.files["aisef2/limit.txt"] = "3\n"
        b = t.commit()
        os.chmod(t.root / "aisef2" / "limit.txt", 0o755)
        h = t.commit()
        self.assertNotEqual(b, h)
        self.assertNonReuse(TO.state(t, b, h, None), "INVALIDATED", "R1", "no observation")

    # LOW, fixed: AUD-2 ---------------------------------------------------------------------------------------------
    @unittest.skipUnless(hasattr(os, "posix_spawn"), "os.posix_spawn: POSIX only")
    def test_aud2_posix_spawn_file_actions(self):
        """A posix_spawn file action opens the changed file as the child's stdin: data. 8a31f7c8: unseen (audit)."""
        t, b, h, kill = cfg_toy(self, "        pid = os.posix_spawn(sys.executable, [sys.executable, '-c', 'import sys; sys.stdin.read()'],"
                                f" os.environ, file_actions=[(os.POSIX_SPAWN_OPEN, 0, os.path.join(HERE, {LIMIT}), os.O_RDONLY, 0)])\n"
                                "        os.waitpid(pid, 0)\n" + CFG_KILL.format(read="1"))
        rec = TO.record(t, [kill])[kill]
        self.assertEqual(rec["opened"].get("aisef2/limit.txt"), "data")
        self.assertNonReuse(TO.state(t, b, h, {kill: rec}, "aisef2/cfg.py::f"), "INVALIDATED", ("R1", "R2"))


class Review1Parser(unittest.TestCase):
    """LOW findings fixed in the strace parser (hand-made lines in the strace 6.8 format)."""

    def derive(self, root: str, hook=None) -> dict:
        return OBS.derive(witness(self, {100: EXECVE + root + "+++ exited with 0 +++\n"}, {100: (hook or ROOT_HOOK) + ["E\t0"]}))

    def test_str2_chained_relative_chdirs(self):
        rec = OBS.derive(witness(self, {100: ROOT_TRACE, 101: 'chdir("aisef2") = 0\nchdir("sub") = 0\n'
                                  'access("data.txt", R_OK) = 0\n+++ exited with 0 +++\n'}, {100: ROOT_HOOK + ["E\t0"]}))
        self.assertEqual(rec["opened"].get("aisef2/sub/data.txt"), "data")

    def test_str3_a_tree_path_through_another_name(self):
        rec = self.derive('symlink("/w/tree/aisef2", "/w/run/lnk") = 0\n'
                          'access("/proc/self/cwd/aisef2/other", F_OK) = 0\n')
        self.assertEqual(rec["completeness"]["aliases"], 2)

    def test_str4_calls_outside_the_traced_channel(self):
        rec = self.derive("io_uring_setup(8, 0x7ffd) = 3\n")
        self.assertEqual(rec["completeness"]["unobservable_calls"], 1)
        self.assertIn("io_uring_setup", OBS.STRACE_EVENTS)

    def test_str5_a_reused_fd_number_is_a_new_listing(self):
        rec = self.derive('openat(AT_FDCWD</w/tree>, "tests/v2", O_RDONLY|O_DIRECTORY) = 4</w/tree/tests/v2>\n'
                          'getdents64(4</w/tree/tests/v2>, 0x1 /* 3 entries */, 32768) = 80\n'
                          'openat(AT_FDCWD</w/tree>, "tests/v2", O_RDONLY) = 4</w/tree/tests/v2>\n'
                          'getdents64(4</w/tree/tests/v2>, 0x1 /* 3 entries */, 32768) = 80\n',
                          ROOT_HOOK + ["l\town\t/w/tree/tests/v2\t<native>"])
        self.assertEqual((rec["listed"], rec["listed_by"]), (["tests/v2"], {"tests/v2": ["<native>"]}))


if __name__ == "__main__":
    unittest.main()
