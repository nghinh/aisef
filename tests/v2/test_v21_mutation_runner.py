"""The mutation runner's own contract (docs/v2.1/MUTATION-RUNNER-V2.md), on toy targets and toy kill files built in a
temporary root and driven through the real `run_target` (and `mutants`, `_run_tests`, `main`), the real ProcessRange
and the real cleanup authority. Each case builds the situation a confirmed finding of the V2.1 runner audit described,
asserts the designed truth per mutant, and — where a protection can be switched off — shows the old failure with it
off, so a toy that no longer exercises the channel fails instead of passing vacuously. Not a kill file."""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.v2 import mutation as m  # noqa: E402

POSIX = os.name == "posix"


def toy(base: pathlib.Path, module: str, files: dict[str, str], name: str = "toy") -> pathlib.Path:
    """A root holding aisef2/<name>.py and the kill files tests/v2/<file> (dedented)."""
    root = base / "root"
    for rel, text in {"aisef2/__init__.py": "", f"aisef2/{name}.py": module, "tests/v2/__init__.py": "",
                      **{f"tests/v2/{k}": textwrap.dedent(v) for k, v in files.items()}}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    return root


def killed(result: dict) -> list[bool]:
    return [r["killed"] for r in result["results"]]


# --------------------------------------------------------------------------------------------- §1 bytecode

#: v(1) is all the kill file asks, through an isolated child that writes its bytecode into the tree (BC-2)
BC_MODULE = "def v(x):\n    if x == 1:\n        return 'aa'\n    return 'bb'\n"
BC_KILL = {"test_k.py": """
    import pathlib, subprocess, sys, unittest
    TREE = str(pathlib.Path(__file__).resolve().parents[2])
    class K(unittest.TestCase):
        def test_v1_through_an_isolated_child(self):
            code = f"import sys; sys.path.insert(0, {TREE!r}); from aisef2.toy import v; print(v(1))"
            out = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, check=True).stdout
            self.assertEqual(out.strip(), "aa")
    """}
#: generator order: condition negated, L4 returns None, Eq->NotEq, L3 returns None, 'bb' emptied, 'aa' emptied
BC_TRUTH = [True, False, True, True, False, True]


class Bytecode(unittest.TestCase):
    """BC-1, BC-2, BC-4, ORD-3: a version of the mutated file never runs another version's bytecode."""

    def setUp(self) -> None:
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = pathlib.Path(d.name)
        self.mod = self.dir / "bcmod.py"

    def child(self, *flags: str, env: dict | None = None) -> str:
        code = f"import sys; sys.path.insert(0, {str(self.dir)!r}); import bcmod; print(bcmod.V)"
        return subprocess.run([sys.executable, *flags, "-c", code], capture_output=True, text=True, check=True,
                              env=env).stdout.strip()

    def test_a_same_size_same_second_version_reuses_the_cache_without_the_stamp(self):
        """The trap is live on this host: an -I child writes the .pyc, a -B child with PYTHONDONTWRITEBYTECODE reads
        it for a different version of one size written in the same whole second."""
        self.mod.write_text("V = 'A'\n", encoding="utf-8")
        second = int(self.mod.stat().st_mtime)
        os.utime(self.mod, (second, second))
        self.assertEqual(self.child("-I"), "A")
        self.mod.write_text("V = 'B'\n", encoding="utf-8")
        os.utime(self.mod, (second, second))
        self.assertEqual(self.child("-B", env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}), "A")

    def test_write_version_makes_the_next_import_compile_the_new_bytes(self):
        prefix = self.dir / "prefix"
        last = m._write_version(self.mod, "V = 'A'\n", 0)
        self.assertEqual(self.child("-I"), "A")
        for i, value in enumerate("BCDEFGHIJKLMNOPQRSTU"):
            last = m._write_version(self.mod, f"V = '{value}'\n", last)
            with self.subTest(i=i):
                self.assertEqual(self.child("-B", env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}), value)
                self.assertEqual(self.child("-I"), value)
                # BC-4: a cache under a pycache prefix is refused the same way, wherever it lives
                self.assertEqual(self.child(env={**os.environ, "PYTHONPYCACHEPREFIX": str(prefix)}), value)

    def test_stamps_are_strictly_increasing_whole_seconds_above_the_original(self):
        self.mod.write_text("V = 0\n", encoding="utf-8")
        original = int(self.mod.stat().st_mtime)
        last, seen = original, []
        begun = time.monotonic()
        for i in range(30):
            last = m._write_version(self.mod, f"V = {i % 10}\n", last)
            st = self.mod.stat()
            self.assertEqual(st.st_mtime, int(st.st_mtime))      # whole seconds: an ns-only stamp is worse than none
            seen.append(int(st.st_mtime))
        self.assertLess(time.monotonic() - begun, 5)
        self.assertEqual(seen, sorted(set(seen)))
        self.assertGreater(seen[0], original)

    @unittest.skipUnless(POSIX, "the runner's process ranges and cleanup authority are measured on POSIX")
    def test_consecutive_same_size_mutants_are_classified_by_their_own_bytes(self):
        root = toy(self.dir, BC_MODULE, BC_KILL)
        src = (root / "aisef2/toy.py").read_text(encoding="utf-8")
        found = m.mutants(src, "v", {})
        sizes = [len(s) for _, s in found]
        # not vacuous: same-size neighbours whose designed classes differ, so a stale .pyc would show
        self.assertTrue(any(sizes[i] == sizes[i + 1] and BC_TRUTH[i] != BC_TRUTH[i + 1] for i in range(len(found) - 1)))
        self.assertEqual(killed(m.run_target(root, "aisef2/toy.py::v", ["tests/v2/test_k.py"])), BC_TRUTH)
        # the old failure, with the stamp switched off: every version in one whole second
        fixed = int((root / "aisef2/toy.py").stat().st_mtime) + 1

        def same_second(path, text, last):
            path.write_text(text, encoding="utf-8")
            os.utime(path, (fixed, fixed))
            return fixed
        with mock.patch.object(m, "_write_version", same_second):
            self.assertNotEqual(killed(m.run_target(root, "aisef2/toy.py::v", ["tests/v2/test_k.py"])), BC_TRUTH)


if __name__ == "__main__":
    unittest.main()
