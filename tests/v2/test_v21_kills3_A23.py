"""V2.1 (owner B-03, kills round 3, batch A23): the survivors of aisef2/app/cli.py::_parser that audit found to carry
an identifying element — something another part of the product defines and the help repeats for the operator.

The other help strings and metavars of `_parser`, and the two `run` survivors of this batch (the ': ' between an
exception's type and its text, the temporary directory's name prefix), are audited in the batch report, not tested: no
reader or contract depends on their words. What is tested here is only what the help must keep true when the code it
describes moves: the format ids it names, and the command it points at."""

from __future__ import annotations

import contextlib
import io
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle, bundle_cli, cli, settings  # noqa: E402


def help_of(dest: str) -> str:
    """The help text `aisef run --help` shows for the option stored as `dest` (argparse's own table: the rendered help
    wraps at the terminal's width, which is not part of what is under test)."""
    found = [a.help for a in cli._parser()._actions if a.dest == dest]
    assert len(found) == 1, (dest, found)
    return found[0] or ""


def exit_code_of(argv: list[str]) -> int | str | None:
    """The exit status of `aisef bundle ARGV` (argparse exits on --help and on an unknown subcommand)."""
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            bundle_cli.main(argv)
    except SystemExit as e:
        return e.code
    return None


class FormatIds(unittest.TestCase):
    """`aisef run --help` is where an operator who authors the two input files by hand is told which format each must
    declare — the value of the `format` key that `bundle.read` and `settings.read` demand and refuse without (their
    refusals say "not a project bundle of format ..." / "not run settings of format ..."). The id the help names
    must be the one the code accepts, so a format that moves cannot leave the help sending the operator to a file
    that is then refused.

    Pins aisef2/app/cli.py::_parser [19, 20]: the `--project` help names bundle.FORMAT and the `--settings` help
    names settings.FORMAT (the ids are read from the modules that enforce them, not copied)."""

    def test_each_input_file_help_names_the_format_the_code_accepts(self):
        for dest, module in (("project", bundle), ("settings", settings)):
            with self.subTest(dest):
                self.assertIn(module.FORMAT, help_of(dest))


class ParentPointer(unittest.TestCase):
    """`--parent` takes a run to continue, and the bundle given with it is the one `aisef bundle continue` derives from
    that run (docs/v2.1/USAGE-2.1.md section 5). Within `aisef run` the help is the only place that names that
    command (R.execute reads the predecessor for its record, claim and spend, not for its bundle). The help is the
    pointer: it must name that command, and the command must exist, or the operator is sent to a subcommand
    `aisef bundle` does not have.

    Pins aisef2/app/cli.py::_parser [25]: the `--parent` help names `aisef bundle continue`, and every `aisef bundle X`
    it names is a registered subcommand, while a name that is not one is refused (the control that makes the
    registration check discriminate). Which further commands the help also mentions is not pinned."""

    def test_the_help_names_the_continue_command_and_it_is_registered(self):
        named = sorted(set(re.findall(r"aisef bundle ([a-z][a-z-]*)", help_of("parent"))))
        self.assertIn("continue", named)
        for name in named:
            with self.subTest(name):
                self.assertEqual(exit_code_of([name, "--help"]), 0)
        self.assertEqual(exit_code_of(["no-such-command", "--help"]), 2)


if __name__ == "__main__":
    unittest.main()
