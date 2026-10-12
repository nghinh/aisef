"""DRAFT, not part of the suite: what would pin the probe's locale IF the owner decides that the measurement mirrors the
session's locale (option (A) of the R02 question: LANG, with LC_ALL, passed through; the refusal check made
locale-proof in the same change). Option (B) (the probe in a fixed locale) makes the two mutants the code."""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import confine  # noqa: E402
from aisef2.runtime import process_range  # noqa: E402


class TheProbeRunsInTheOperatorsLocale(unittest.TestCase):
    def test_lang_reaches_the_probe(self):
        seen = []

        def run(argv, *a, **k):
            if isinstance(argv, list) and argv[-1:] != ["--version"] and confine.PROBE in argv:
                seen.append(dict(k["env"]))
                return subprocess.CompletedProcess(argv, 97, "", "")
            if argv[-1:] == ["--version"]:
                return subprocess.CompletedProcess(argv, 0, "bubblewrap 1.2.3\n", "")
            return real(argv, *a, **k)
        real = subprocess.run
        with tempfile.TemporaryDirectory() as t:
            tmp = pathlib.Path(os.path.realpath(t))
            bwrap = tmp / "bwrap"
            bwrap.write_text("#!/bin/sh\nexit 97\n")
            bwrap.chmod(0o755)
            exe = tmp / "client" / "opencode"
            exe.parent.mkdir()
            exe.write_text("#!/bin/sh\n")
            spec = {"backend": "bwrap", "bwrap": str(bwrap), "network": "host", "read_only": []}
            with mock.patch.object(subprocess, "run", run), mock.patch.object(process_range, "process_table", lambda: {}):
                confine.measure(spec, tmp / "m", str(exe), system="linux",
                                environ={"PATH": "/usr/bin:/bin", "HOME": str(tmp / "h"), "LANG": "de_DE.UTF-8"})
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0].get("LANG"), "de_DE.UTF-8")


if __name__ == "__main__":
    unittest.main()
