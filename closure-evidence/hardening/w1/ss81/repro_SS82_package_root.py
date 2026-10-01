"""SS-82 — a package root is not recognised as the story's. The parent lacks the package `ledgerlock` (the story adds
ledgerlock/__init__.py); a test file fails with `No module named 'ledgerlock'`. On the frozen kernel the run log's
matcher returns "" — the log says the control was NOT performed — while the gate scored the same record PASSED (W1
GPT56SOL-T80 run 1, STORY-01-01, nop seq 113 vs gate seq 129). On the fix, the log line and the gate read one binding.

    PYTHONPATH=<tree> python closure-evidence/hardening/w1/ss81/repro_SS82_package_root.py
"""
import unittest
from types import SimpleNamespace

from aisef.phases import implement as I

OUT = ("ImportError while importing test module '/workspace/tests/test_nfc_normalization.py'.\n"
       "tests/test_nfc_normalization.py:3: in <module>\n    from ledgerlock import normalize_key\n"
       "E   ModuleNotFoundError: No module named 'ledgerlock'\n")
STORY = ["ledgerlock/__init__.py", "ledgerlock/__main__.py", "ledgerlock/cli.py"]


class SS82PackageRootIsTheStorys(unittest.TestCase):
    def test_the_missing_package_binds_to_the_storys_init(self):
        if hasattr(I, "_vang_ma_cua_story"):                       # frozen kernel 02a34e0e
            res = SimpleNamespace(unrunnable="no runnable setup in this tree — dependencies are not installed",
                                  output=lambda: (OUT, ""))
            self.assertEqual(I._vang_ma_cua_story(res, STORY), "ledgerlock/__init__.py")
        else:                                                      # F7 fix: the log summary calls proof.bound
            from aisef.control.proof import bound
            err = {"error": "module_not_found", "missing_module": "ledgerlock", "file": "tests/test_nfc_normalization.py"}
            self.assertEqual(bound(err, STORY, STORY), (True, "ledgerlock/__init__.py"))


if __name__ == "__main__":
    unittest.main()
