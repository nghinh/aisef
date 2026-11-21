"""Platform-parity preflight (W1-DESIGN §7, L1-TESTENV): the W1 targeted tests (tests/v23) run on macOS, Linux and
Windows before integration. The runs are a measurement (closure-evidence/v2.3/l1-testenv/); these checks pin what makes
the CI legs of it real, so the W1 tests cannot drop out of a platform silently:

* the job of tests.yml that runs the whole suite covers ubuntu, macOS and Windows and discovers from `tests`, which
  holds tests/v23;
* tests/v23/__init__.py is there and empty (A2): discovery descends only into a package, so without it CI never
  imports a W1 test;
* tests/v23 loads alike under CI's discovery (`-s tests`, top level `tests`) and the lanes' (`-s tests/v23 -t .`):
  no import error under either, and the same tests.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
OSES = {"ubuntu-latest", "macos-latest", "windows-latest"}
#: the whole suite as every ref but the v2.1.0 tag runs it: the raw discovery from `tests` (not `tests/v2`)
SUITE = re.compile(r"unittest discover -s tests(?![\w/])")


def jobs(text: str) -> dict[str, str]:
    """Job name -> its block, comment lines dropped (a job is a key indented two spaces under `jobs:`)."""
    body = "\n".join(x for x in text.split("\njobs:", 1)[-1].splitlines() if not x.lstrip().startswith("#"))
    marks = [(m.group(1), m.start()) for m in re.finditer(r"(?m)^  ([A-Za-z_][\w-]*):[ \t]*$", body)]
    return {name: body[at:(marks[i + 1][1] if i + 1 < len(marks) else len(body))] for i, (name, at) in enumerate(marks)}


LOAD = r'''
import json, sys, unittest
root, v23 = sys.argv[1], sys.argv[1] + "/tests/v23"
out = {}
for form, top, prefix in (("ci", root + "/tests", "v23."), ("lanes", root, "tests.v23.")):
    loader = unittest.TestLoader()
    ids, todo = [], [loader.discover(v23, top_level_dir=top)]
    while todo:
        for t in todo.pop():
            (todo.append(t) if isinstance(t, unittest.TestSuite) else ids.append(t.id()))
    out[form] = {"errors": [e.splitlines()[-1] for e in loader.errors],
                 "ids": sorted(i[len(prefix):] if i.startswith(prefix) else "!" + i for i in ids)}
print(json.dumps(out))
'''


class PlatformParity(unittest.TestCase):
    def test_the_suite_job_discovers_tests_v23_on_linux_macos_and_windows(self):
        suite = {name: block for name, block in jobs((ROOT / ".github/workflows/tests.yml").read_text(encoding="utf-8")).items()
                 if SUITE.search(block)}
        self.assertIn("unit", suite)
        self.assertLessEqual(OSES, set(re.findall(r"\b(?:ubuntu|macos|windows)-latest\b", suite["unit"])), suite["unit"])

    def test_tests_v23_is_a_package_with_an_empty_init(self):
        init = ROOT / "tests" / "v23" / "__init__.py"
        self.assertTrue(init.is_file())
        self.assertEqual(init.stat().st_size, 0)

    def test_tests_v23_loads_alike_under_the_ci_and_the_lanes_discovery(self):
        r = subprocess.run([sys.executable, "-P", "-c", LOAD, str(ROOT)], cwd=ROOT, capture_output=True, text=True,
                           encoding="utf-8", timeout=600)
        self.assertEqual(r.returncode, 0, r.stderr[-3000:])
        got = json.loads(r.stdout.strip().splitlines()[-1])
        for form in ("ci", "lanes"):
            with self.subTest(form=form):
                self.assertEqual(got[form]["errors"], [])
        self.assertEqual(got["ci"]["ids"], got["lanes"]["ids"])
        self.assertIn("test_v23_platform_parity.PlatformParity.test_tests_v23_is_a_package_with_an_empty_init",
                      got["ci"]["ids"])   # not vacuous: this very file is found


if __name__ == "__main__":
    unittest.main()
