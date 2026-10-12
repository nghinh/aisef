"""V2.1 (mutation survivors, batch R04, round 2): how a path becomes one word of the command line `aisef bundle
continue` tells the operator to paste (`bundle_cli._shell_word`, used for `--repo` and `--parent` of `next`).

* The operator's shell decides the quoting: single quotes on POSIX, double quotes around a path that holds whitespace on
  Windows. The `windows` default follows `sys.platform` of the host, so a host's quoting is only seen on that host:
  the second copy below is executed AND called as if on each platform (whether the default is bound when the module
  is imported or when the function is called is not the requirement), and the module the other tests use is untouched.
* A path made of letters or digits of any script needs no quoting and is printed as it is: the ASCII-only safe set of
  `shlex.quote` is not the criterion, and a path whose every character is such a letter is the case where nothing but
  letters is left to judge.

Pins aisef2/app/bundle_cli.py::_shell_word [5, 11]. Platform-independent: no host is assumed."""

from __future__ import annotations

import pathlib
import shlex
import sys
import types
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle_cli  # noqa: E402


def shell_word_on(platform: str, text: str) -> str:
    """`_shell_word(text)`, no `windows` given, as a host whose `sys.platform` is `platform` gets it: a second copy of
    `bundle_cli` is executed and called while `sys.platform` is patched, and never registered in `sys.modules`."""
    path = pathlib.Path(bundle_cli.__file__)
    module = types.ModuleType(f"bundle_cli_on_{platform}")
    module.__file__ = str(path)
    code = compile(path.read_text(encoding="utf-8"), str(path), "exec")
    with mock.patch.object(sys, "platform", platform):
        exec(code, module.__dict__)
        return module._shell_word(text)


class DefaultFollowsTheHostThePathIsPrintedFor(unittest.TestCase):
    """`_shell_word(path)` with no `windows` quotes for the shell of the platform the module runs on: a Windows
    operator gets a double-quoted path (cmd.exe does not take single quotes as quoting), a POSIX one a single-quoted
    path (inside double quotes their shell would still expand `$` and backticks).

    Pins aisef2/app/bundle_cli.py::_shell_word [5]."""

    SPACED_WINDOWS = "C:\\Users\\Some One\\run 1\\repo"
    SPACED_POSIX = "/home/some one/run $1/repo"

    def test_on_windows_a_path_with_whitespace_is_in_double_quotes_and_another_is_not_quoted(self):
        self.assertEqual(shell_word_on("win32", self.SPACED_WINDOWS), f'"{self.SPACED_WINDOWS}"')
        self.assertEqual(shell_word_on("win32", "C:\\Users\\x\\run1\\repo"), "C:\\Users\\x\\run1\\repo")

    def test_on_a_posix_host_a_path_with_whitespace_or_a_dollar_is_in_single_quotes(self):
        for platform in ("linux", "darwin"):
            with self.subTest(platform=platform):
                word = shell_word_on(platform, self.SPACED_POSIX)
                self.assertEqual(word, f"'{self.SPACED_POSIX}'")
                self.assertEqual(shlex.split(word), [self.SPACED_POSIX])
                self.assertEqual(shell_word_on(platform, "/home/x/run1/repo"), "/home/x/run1/repo")

    def test_the_hosts_own_default_is_the_one_its_platform_gets(self):
        """Control: the module this process imported follows its own platform, whichever that is."""
        for text in (self.SPACED_WINDOWS, self.SPACED_POSIX, "/plain/path"):
            self.assertEqual(bundle_cli._shell_word(text), shell_word_on(sys.platform, text))


class LettersOfAnyScriptAloneAreOneWordAsTheyAre(unittest.TestCase):
    """A path whose every character is a letter or digit needs no quoting for a POSIX shell, whatever its script: it
    is printed as it is (`日本語`, not `'日本語'`). The path `dir/日本語` was already so; a run directory given as one
    bare relative name is the case in which no `/`, `.` or `-` is left beside the letters.

    Pins aisef2/app/bundle_cli.py::_shell_word [11]."""

    #: every character `str.isalnum`, and at least one outside ASCII (shlex.quote's own safe set would quote them)
    BARE = ("\u65e5\u672c\u8a9e", "\u03a9mega", "ch\u1ea1y", "\u0434\u0430", "run\u0663", "\u00fcber")

    def test_a_bare_name_of_letters_is_printed_as_it_is(self):
        for text in self.BARE:
            with self.subTest(text=ascii(text)):
                self.assertTrue(text.isalnum() and not text.isascii())
                self.assertEqual(bundle_cli._shell_word(text, windows=False), text)

    def test_the_same_letters_are_quoted_once_a_character_needs_it(self):
        for text in self.BARE:
            with self.subTest(text=ascii(text)):
                for spoiled in (f"{text} 2", f"{text}$x", f"{text};x"):
                    word = bundle_cli._shell_word(spoiled, windows=False)
                    self.assertNotEqual(word, spoiled)
                    self.assertEqual(shlex.split(word), [spoiled])


if __name__ == "__main__":
    unittest.main()
