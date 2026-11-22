"""Review 2 of the F5 recorder (2026-11-22): regression tests for the two confirmed findings (R2-1, R2-2). Each test is
red on the 57387ed5 engine (validation/v23/impact.py at that commit: the reuse the finding describes) and green here;
every fix only turns a reuse into a non-reuse. Where an `_OFF` key covers the guard, the test also shows the same
change reused with that rule off (the guard is load-bearing). Real recordings use the backend this host has (strace on
Linux when present, else audit). Not a kill file (tests/v23 is outside every mutation.COPY root: Amendment A2)."""

from __future__ import annotations

import pathlib
import sys
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.v23 import test_v23_observe as TO  # noqa: E402
from tests.v23 import test_v23_review1 as R1  # noqa: E402
from validation.v23 import impact  # noqa: E402

PLAIN, WIDE, UPPER = "aisef2/plugins/a.txt", "aisef2/ｐlugins/a.txt", "aisef2/PLUGINS/a.txt"   # U+FF50: fullwidth p
#: the kill test of aisef2/cfg.py::f looks the directory up by a name no literal holds, and asserts strictly only when
#: it is absent (or present): the answer of the lookup decides what the run checks
LOOKUP = ("        name = bytes([112, 108, 117, 103, 105, 110, 115]).decode()\n"
          "        if {neg}os.path.isdir(os.path.join(HERE, name)):\n            self.assertEqual(cfg.f(1), 0)\n"
          "        self.assertIn(cfg.f(1), (0, 1))\n")
#: (name, imports, the branch only a mutant takes) of sel.pick: test_snd2's B2 with other ways to load a module by a
#: computed name, or to run code S(F) need not hold
LOADS = (
    ("find_spec + exec_module", "import importlib.util\n",
     "        spec = importlib.util.find_spec('aisef2.' + 'handlers')\n        m = importlib.util.module_from_spec(spec)\n"
     "        spec.loader.exec_module(m)\n        return m.read()\n"),
    ("importlib.__import__", "import importlib\n",
     "        return importlib.__import__('aisef2.' + 'handlers', fromlist=['read']).read()\n"),
    ("builtins.__import__", "import builtins\n",
     "        return builtins.__import__('aisef2.' + 'handlers', fromlist=['read']).read()\n"),
    ("pkgutil.resolve_name", "import pkgutil\n", "        return pkgutil.resolve_name('aisef2.' + 'handlers').read()\n"),
    ("PathFinder.find_spec", "import importlib.util\nimport os\nfrom importlib.machinery import PathFinder\n",
     "        spec = PathFinder.find_spec('aisef2.' + 'handlers', [os.path.dirname(os.path.dirname(__file__))])\n"
     "        m = importlib.util.module_from_spec(spec)\n        spec.loader.exec_module(m)\n        return m.read()\n"),
    ("a bare name through sys.path", "import os\nimport sys\n",
     "        sys.path.insert(0, os.path.dirname(__file__))\n        import handlers\n        return handlers.read()\n"),
    ("a child's -c text", "import subprocess\nimport sys\n",
     "        return subprocess.run([sys.executable, '-c', 'import aisef2.handlers as h; print(h.read())'],\n"
     "                              capture_output=True, text=True, check=True).stdout\n"),
)
NS, MOD = "aisef2/plugins/README.txt", "aisef2/plugins.py"
#: (name, imports, opt.pick's probe of aisef2.plugins, what Δ adds): test_snd1 by other spellings. The relative import
#: of the module itself is loaded by the unmutated run (D2 refuses it, as at 57387ed5): only the namespace case here
PROBES = (
    ("find_spec of a computed name", "import importlib.util\n",
     "    if importlib.util.find_spec('aisef2.' + ''.join(['plug', 'ins'])) is None:\n        return x > 1\n", (NS, MOD)),
    ("a literal relative import_module", "import importlib\n",
     "    try:\n        importlib.import_module('.plugins', 'aisef2')\n    except ImportError:\n        return x > 1\n", (NS,)),
)
#: dynamic_sites: spellings that must be sites, and controls that must not
SITES = {
    "find_spec(c)": "import importlib.util\nimportlib.util.find_spec('a.' + n)\n",
    "module_from_spec": "import importlib.util\nimportlib.util.module_from_spec(s)\n",
    "exec_module": "s.loader.exec_module(m)\n",
    "load_module(c)": "loader.load_module('a.' + n)\n",
    "importlib.__import__": "import importlib\nimportlib.__import__('a.b')\n",
    "relative find_spec": "import importlib.util\nimportlib.util.find_spec('.p', 'a')\n",
    "import_module as im": "from importlib import import_module as im\nim('a.b')\n",
    "a reference": "import importlib\nload = importlib.import_module\n",
    "getattr of a loader": "import importlib\ngetattr(importlib, 'import_module')('a.b')\n",
    "attrgetter": "import operator\noperator.attrgetter('import_module')\n",
    "resources.files(c)": "import importlib.resources\nimportlib.resources.files(n)\n",
    "from importlib.resources": "from importlib.resources import files\n",
    "sys.path": "import sys\nsys.path.append(d)\n",
    "from sys import path": "from sys import path\n",
    "meta_path": "import sys\nsys.meta_path.insert(0, Finder())\n",
    "a literal launch": "import subprocess\nsubprocess.run(['wc', '-l', 'x'])\n",
    "os.execl": "import os\nos.execl('/bin/sh', 'sh')\n",
    "from subprocess import run": "from subprocess import run\n",
    "import subprocess as sp": "import subprocess as sp\nsp.run(['x'])\n",
    "discover": "import unittest\nunittest.TestLoader().discover('tests/v2/sub')\n",
    "loadTestsFromName(c)": "loader.loadTestsFromName('a.' + n)\n",
}
CONTROLS = {
    "literal import_module": "import importlib\nimportlib.import_module('a.b')\n",
    "literal find_spec": "import importlib.util\nimportlib.util.find_spec('a.b')\n",
    "from importlib import import_module": "from importlib import import_module\nimport_module('a.b')\n",
    "asyncio.run": "import asyncio\nasyncio.run(main())\n",
    "from os import path": "from os import path\npath.join('a', 'b')\n",
    "sys.argv": "import sys\nprint(sys.argv)\n",
}


def rename(old: str, new: str):
    def change(t):
        R1.drop(t, old)
        t.files[new] = "x\n"
    return change


class Review2(TO.Base):
    def lookup_toy(self, old: str, new: str, method: str):
        kill = "tests/v2/test_cfg.py"
        files = {"aisef2/cfg.py": R1.CFG, old: "x\n", kill: R1.HEAD.format(m="cfg") + "    def test_f(self):\n" + method}
        t, b, h = R1.toy(self, "aisef2/cfg.py::f", kill, files, rename(old, new))
        return t, b, h, kill

    # R2-1 ----------------------------------------------------------------------------------------------------------
    def test_r2_1_a_directory_renamed_to_a_spelling_that_folds_alike(self):
        """The kill test looks up aisef2/plugins; between basis and head the directory is renamed to a spelling that
        folds alike (fullwidth p <-> p): the lookup's answer changes (no supported volume folds U+FF50). A real
        record, either direction. 57387ed5: kind() compared folded answers (dir, dir) — VERIFIED_REUSE."""
        for name, old, new, neg in (("fullwidth to plain", WIDE, PLAIN, "not "), ("plain to fullwidth", PLAIN, WIDE, "")):
            with self.subTest(name):
                t, b, h, kill = self.lookup_toy(old, new, LOOKUP.format(neg=neg))
                rec = TO.record(t, [kill])
                self.assertEqual(rec[kill]["opened"].get("aisef2/plugins"), "data")
                self.assertNonReuse(TO.state(t, b, h, rec, "aisef2/cfg.py::f"), "INVALIDATED", "R2",
                                    "looked up aisef2/plugins, which was dir")
                self.assertEqual(TO.state(t, b, h, rec, "aisef2/cfg.py::f", {"R2"}).state, "VERIFIED_REUSE")

    def test_r2_1_a_volume_between_exact_and_folded(self):
        """A case-insensitive volume that does not fold compatibility characters (APFS): basis aisef2/PLUGINS, head
        aisef2/\\uff50lugins; a lookup of aisef2/plugins answers dir, then absent. Neither the exact answers (absent,
        absent) nor the folded ones (dir, dir) differ; the sets of spellings do. Synthetic record (any host).
        57387ed5: VERIFIED_REUSE."""
        t, b, h, kill = self.lookup_toy(UPPER, WIDE, R1.CFG_KILL.format(read="1"))
        obs = t.observe(h, {kill: ["aisef2/plugins"]})
        self.assertNonReuse(TO.state(t, b, h, obs, "aisef2/cfg.py::f"), "INVALIDATED", "R2",
                            "looked up aisef2/plugins, which was dir aisef2/PLUGINS and is dir aisef2/ｐlugins")
        self.assertEqual(TO.state(t, b, h, obs, "aisef2/cfg.py::f", {"R2"}).state, "VERIFIED_REUSE")

    def test_r2_1_spellings_unit(self):
        """A case-only rename (seen on a case-sensitive volume: ext4) and an HFS+ ignorable code point (U+200C): the
        spellings differ, and the ignorable folds away. 57387ed5: no spellings(); its kind() answered dir at both,
        and _fold kept U+200C."""
        ctx = impact._Ctx.__new__(impact._Ctx)
        ctx._c, ctx.copy_files = {}, lambda R: R.files
        B, H = (types.SimpleNamespace(sha=s, files=[f]) for s, f in (("b", "aisef2/Plugins/a.txt"), ("h", PLAIN)))
        self.assertEqual(ctx.spellings(B, "aisef2/plugins"), {("aisef2/Plugins", "dir")})
        self.assertNotEqual(ctx.spellings(B, "aisef2/plugins"), ctx.spellings(H, "aisef2/plugins"))
        self.assertEqual(ctx.spellings(H, "."), {("", "dir")})
        self.assertEqual(impact._fold("aisef2/plu‌gins"), impact._fold("aisef2/plugins"))

    # R2-2 ----------------------------------------------------------------------------------------------------------
    def test_r2_2_mutant_only_loads_through_other_entry_points(self):
        """Δ changes aisef2/handlers.py, which S(F) does not hold; only a mutant's branch loads it (LOADS). Each way
        is an R8 site. 57387ed5: none was — VERIFIED_REUSE (the reviewer measured basis FAIL / head PASS)."""
        kill = "tests/v2/test_sel.py"
        for name, imports, branch in LOADS:
            with self.subTest(name):
                sel = imports + "\n\ndef pick(x):\n    if x > 5:\n" + branch + "    return 'small'\n"
                files = {"aisef2/sel.py": sel, "aisef2/handlers.py": "def read():\n    return 1\n",
                         kill: R1.HEAD.format(m="sel") + "    def test_pick(self):\n        self.assertNotEqual(sel.pick(1), 1)\n"}
                t, b, h = R1.toy(self, "aisef2/sel.py::pick", kill, files,
                                 lambda t: t.files.update({"aisef2/handlers.py": "def read():\n    return 2\n"}))
                self.assertNotIn("aisef2/handlers.py", impact.kill_closure(t.root, b, h, kill))
                rec = TO.record(t, [kill])
                self.assertNonReuse(TO.state(t, b, h, rec, "aisef2/sel.py::pick"), "INVALIDATED", "R8",
                                    "computed-name site at aisef2/sel.py")
                self.assertEqual(TO.state(t, b, h, rec, "aisef2/sel.py::pick", {"R8"}).state, "VERIFIED_REUSE")

    def test_r2_2_a_namespace_directory_by_find_spec_or_a_relative_name(self):
        """test_snd1 with the directory probed by find_spec of a computed name, or imported by a literal relative
        name: R5 sees no name, so the probe is an R8 site. Δ adds aisef2/plugins/README.txt (a namespace directory)
        or the module aisef2/plugins.py. 57387ed5 (audit): VERIFIED_REUSE. strace: the trace holds the import system's
        stat of the .py the probe looks for (aisef2/plugins/__init__.py, absent; aisef2/plugins.py, found, not loaded)
        as an opened .py S(F) does not hold, so D2 refuses first (C10, UNRESOLVED); behind it R8, or R2 for the module
        (that stat is data)."""
        kill = "tests/v2/test_opt.py"
        for name, imports, probe, adds in PROBES:
            for added in adds:
                with self.subTest(name, added=added):
                    files = {"aisef2/opt.py": imports + "\n\ndef pick(x):\n" + probe + "    return None\n",
                             kill: R1.HEAD.format(m="opt") + "    def test_pick(self):\n"
                             "        self.assertIn(opt.pick(2), (True, None))\n"}
                    t, b, h = R1.toy(self, "aisef2/opt.py::pick", kill, files,
                                     lambda t, added=added: t.files.update({added: "x = 1\n"}))
                    rec = TO.record(t, [kill])
                    off = {"D2"} if TO.STRACE else set()
                    if TO.STRACE:
                        looked = "aisef2/plugins/__init__.py" if added == NS else MOD
                        self.assertNonReuse(TO.state(t, b, h, rec, "aisef2/opt.py::pick"), "UNRESOLVED", "D2",
                                            f"S({kill}) misses {looked}")
                    either = TO.STRACE and added == MOD
                    self.assertNonReuse(TO.state(t, b, h, rec, "aisef2/opt.py::pick", off), "INVALIDATED",
                                        ("R8", "R2") if either else "R8", "" if either else "computed-name site at aisef2/opt.py")
                    if not either:
                        self.assertEqual(TO.state(t, b, h, rec, "aisef2/opt.py::pick", off | {"R8"}).state, "VERIFIED_REUSE")

    def test_r2_2_site_table(self):
        """Every spelling of SITES is a site; CONTROLS (a literal absolute name, a launch-free module) are not.
        57387ed5: none of the 21 spellings was a site."""
        for name, src in SITES.items():
            with self.subTest(name):
                self.assertTrue(impact.dynamic_sites(src, "x.py"))
        for name, src in CONTROLS.items():
            with self.subTest(name):
                self.assertFalse(impact.dynamic_sites(src, "x.py"))


if __name__ == "__main__":
    unittest.main()
