"""V2.1 (owner B-03b): kill tests for the survivors of aisef2/app/cli.py's V2.1 mutation target `_parser`, the class
named by the target and the mutants it kills. In the kill set of exactly the target it kills (validation/v2/mutation.py).

The earlier kill set drives `aisef run` only with complete, valid arguments and reads what each mode prints: no test
read the usage or the help an operator is shown, and none left out the one required argument, so an emptied program
name, description, help text or metavar, and `--project` no longer required, all survived."""

from __future__ import annotations

import contextlib
import io
import os
import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import cli  # noqa: E402

USAGE = ("usage: aisef run [-h] [--check | --verify] --project PROJECT [--settings SETTINGS] [--repo REPO] [--out OUT] "
         "[--expect-anchor SHA256] [--parent PARENT] [--anchor-out ANCHOR_OUT] [--accept-unaccounted] "
         "[--supersede-claim SHA256]")


class Parser(unittest.TestCase):
    """_parser — "L29 string 'aisef run' emptied", "L29 string \"Run a project's admitted plan under the AISEF V2 kernel.\"
    emptied", "L31 string \"check the inputs and the plan's admission; no provider request\" emptied", "L32 string 'verify
    a finished run directory against its journal' emptied", "L33 True->False" (`--project` required), the help strings
    of --project, --settings, --repo, --out (L33-L36), --expect-anchor (L38), --parent (L40), --anchor-out (L42),
    --accept-unaccounted (L45) and --supersede-claim (L47) emptied, "L37 string 'SHA256' emptied" and "L46 string
    'SHA256' emptied" (the metavars that say a sha256 is expected): `aisef run --help` is the command's documentation —
    its usage, what it does, and what each option means and in which mode — and a run named without its project bundle
    is refused (exit 2) with the usage, before anything is read."""

    def aisef_run(self, argv: list[str]) -> tuple[int, str, str]:
        """(exit status, stdout, stderr) of `aisef run ARGV`, each with its whitespace collapsed: the words and their
        order are the documentation, the line breaks are the terminal's width. Colour off (argparse 3.14 colours a tty)."""
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, {"NO_COLOR": "1", "PYTHON_COLORS": "0"}), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as c:
            cli.run(argv)
        return c.exception.code, " ".join(out.getvalue().split()), " ".join(err.getvalue().split())

    def test_the_help_is_the_command_s_usage_purpose_and_every_option_s_meaning(self):
        self.assertEqual(self.aisef_run(["--help"]), (0, USAGE + (
            " Run a project's admitted plan under the AISEF V2 kernel."
            " options:"
            " -h, --help show this help message and exit"
            " --check check the inputs and the plan's admission; no provider request"
            " --verify verify a finished run directory against its journal"
            " --project PROJECT the project bundle (aisef-v2-project/1)"
            " --settings SETTINGS the run settings (aisef-v2-run/1)"
            " --repo REPO the project's git repository (cloned; never written)"
            " --out OUT the run directory (a new one to run; an existing one to verify)"
            " --expect-anchor SHA256 verify only: the evidence anchor the run printed, kept outside the run directory"
            " --parent PARENT run only: the run this one continues (`aisef bundle continue`), recorded with its anchor"
            " --anchor-out ANCHOR_OUT run only: a new file (never overwritten) the evidence anchor is written to — keep"
            " it where the developer cannot write (docs/v2.1/ANCHOR-THREAT-MODEL.md)"
            " --accept-unaccounted run --parent only: start although the lineage has spend no evidence accounts for"
            " (recorded)"
            " --supersede-claim SHA256 run --parent only: supersede the predecessor's claim with this sha256 whose"
            " child never began and whose claimant cannot be shown gone, or whose child's evidence cannot be read"
            " (the operator's assertion, recorded)"), ""))

    def test_a_run_named_without_its_project_bundle_is_refused_with_the_usage(self):
        self.assertEqual(self.aisef_run(["--check", "--settings", "settings.json", "--repo", "repo"]), (2, "", (
            f"{USAGE} aisef run: error: the following arguments are required: --project")))


if __name__ == "__main__":
    unittest.main()
