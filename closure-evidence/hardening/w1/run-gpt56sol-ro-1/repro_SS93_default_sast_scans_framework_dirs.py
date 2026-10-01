"""SS-93 — the default Python sast command (`bandit -q -r .`, aisef/harness/capabilities.py) scans the framework
directories the kernel itself says are not the project's code (aisef/phases/qa.py::_KHUNG: .claude/, .opencode/,
.aisef/, _bmad-output/ — bug 113's family). Measured in W1 PROFILE-W1-OC-GPT56SOL-T80-RO run 1 (2026-09-19): 1 093 of
1 096 bandit findings located under ./.claude (the workload's installed skills). A story or pre-deploy with a
`security` contract would be FAILED on findings in files the developer does not own. Fails on the frozen kernel.

    PYTHONPATH=<tree> python closure-evidence/hardening/w1/run-gpt56sol-ro-1/repro_SS93_default_sast_scans_framework_dirs.py
"""
import unittest

from aisef.harness.capabilities import Role, profile_by_stack
from aisef.phases.qa import _KHUNG


class SS93(unittest.TestCase):
    def test_the_default_sast_command_does_not_scan_the_framework_directories(self):
        cmd = profile_by_stack("python").capability(Role.SAST).command
        unexcluded = [d for d in _KHUNG if d.rstrip("/") not in cmd]
        self.assertEqual(unexcluded, [], f"`{cmd}` scans {unexcluded}")


if __name__ == "__main__":
    unittest.main()
