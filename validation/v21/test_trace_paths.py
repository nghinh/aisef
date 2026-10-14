"""validation/v21/trace_paths.py: the marks are where the tool says, each text once; the helper writes what the tool reads.

Run by hand, from the repository root, through the wrapper:  python3 -B validation/v21/test_trace_paths.py
It is not part of the suite and is not a kill file; trace_paths.py is outside mutation.COPY."""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.v21 import trace_paths as T  # noqa: E402


class Patches(unittest.TestCase):
    def test_every_text_to_mark_is_in_the_tree_exactly_once(self):
        for rel, old, _ in T.PATCHES:
            with self.subTest(file=rel, text=old[:50]):
                self.assertEqual((ROOT / rel).read_text(encoding="utf-8").count(old), 1)

    def test_every_mark_names_a_declared_path_and_every_declared_path_is_marked(self):
        used = {part.split('"')[1] for _, _, new in T.PATCHES for part in new.splitlines() if "_aisef_trace(" in part}
        self.assertEqual(used, set(T.PATHS))

    def test_a_patched_copy_still_compiles_and_a_mark_writes_what_hits_of_reads(self):
        with tempfile.TemporaryDirectory() as t:
            tree, trace = pathlib.Path(t) / "tree", pathlib.Path(t) / "trace"
            for rel in {f for f, _, _ in T.PATCHES}:
                (tree / rel).parent.mkdir(parents=True, exist_ok=True)
                (tree / rel).write_text((ROOT / rel).read_text(encoding="utf-8"), encoding="utf-8")
            trace.mkdir()
            self.assertEqual(sorted(T.patch_tree(tree, trace)), sorted({f for f, _, _ in T.PATCHES}))
            for rel in {f for f, _, _ in T.PATCHES}:
                compile((tree / rel).read_text(encoding="utf-8"), rel, "exec")
            (trace / "CURRENT").write_text("some/kill_file.py\n", encoding="utf-8")
            src = (tree / T.RANGE).read_text(encoding="utf-8")
            ns: dict = {"__name__": "marked"}
            helper = "def _aisef_trace" + src.rsplit("def _aisef_trace", 1)[1]
            exec(helper, ns)
            ns["_aisef_trace"]("range._Posix.abort:gone")
            self.assertEqual({k: {t_: len(p) for t_, p in v.items()} for k, v in T.hits_of(trace).items()},
                             {"some/kill_file.py": {"range._Posix.abort:gone": 1}})


class Refusal(unittest.TestCase):
    def test_a_text_that_is_not_there_once_is_refused(self):
        with tempfile.TemporaryDirectory() as t:
            tree = pathlib.Path(t)
            (tree / "aisef2/app").mkdir(parents=True)
            (tree / "aisef2/runtime").mkdir(parents=True)
            (tree / T.CONFINE).write_text("nothing to mark\n", encoding="utf-8")
            (tree / T.RANGE).write_text("nothing to mark\n", encoding="utf-8")
            r = subprocess.run([sys.executable, "-B", "-c",
                                "import sys, pathlib; sys.path.insert(0, %r); from validation.v21 import trace_paths as T; "
                                "T.patch_tree(pathlib.Path(%r), pathlib.Path(%r))" % (str(ROOT), t, t)],
                               capture_output=True, text=True, check=False)
            self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
