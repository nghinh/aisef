"""B-03 round 3 — `confine._judge`: a user-namespace check that has no exit status did not run, whatever it printed.

`_judge`'s docstring: what the measurement shows that confinement must not allow "— or did not measure (a check that
could not run is a problem, never a pass)". The probe's `unshare --user true` is a measured refusal only when it RAN
and exited with a status, and the kernel's wording came with that status: the exit status is what says the command ran
(a loader failure that never reached the kernel prints the same errno text — test_v21_kills3_A06 pins that for 127).
A try with no exit status at all — the value `tries.get("user_namespace", (None, ""))` stands for — is a check that
did not run, so no text beside it can turn it into a refusal.

Campaign 5 left `rc in (None, 127)` -> `rc in (127,)` (`_judge` [100]) SURVIVED: the module's own producer
(`_sections`) stores an int status or leaves a list that is refused earlier, so the only way to reach the None member
is `_judge`'s own default, whose text is "" and matches no refusal. The audit of that mutant rested on what the
producer builds; this test states the contract of the function's input instead, which does not.
"""

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import confine  # noqa: E402
from tests.v2 import v21_r3_conf_rows as rows  # noqa: E402

WS = pathlib.PurePosixPath("/w/ws")
TOKEN = "TOKEN-0123456789abcdef"
UNMEASURED = "no refusal of a further user namespace was measured"
REFUSALS = ("unshare: unshare failed: No space left on device", "unshare: unshare failed: Operation not permitted",
            "No space left on device", "Operation not permitted")


def clean_report() -> dict:
    """A measurement `_judge` finds nothing to say about (the workspace the only host-backed mount)."""
    return {"network": "host", "created_outside_workspace": {"kernel": False}, "setsid_survivors": [],
            "host_mounts": rows.HOST,
            "inside": {"capabilities": dict.fromkeys(("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"), "0000000000000000"),
                       "no_new_privs": "1", "namespaces": dict.fromkeys(("user", "pid", "ipc", "uts", "mnt"), "own"),
                       "routed_interfaces": [], "home_listing": [], "unix_sockets": [],
                       "mounts": [rows.mount("/"), {"at": str(WS), "access": "rw", "fs": "ext4"}],
                       "mount_targets": [str(WS)]}}


def judged(**user_namespace) -> list[str]:
    tries = {"read_canary": (1, "cat: canary: No such file or directory"), "workspace": (0, "ok"),
             "read_git_directory": (0, "ref: refs/heads/main")}
    tries.update(user_namespace)
    return confine._judge(clean_report(), TOKEN, "", tries, "/nonexistent", WS)


class ATryWithoutAnExitStatusDidNotRun(unittest.TestCase):
    def test_a_refusal_the_kernel_gave_is_not_a_problem(self):          # the control: the clean report is clean
        for text in REFUSALS:
            with self.subTest(text=text):
                self.assertEqual(judged(user_namespace=(1, text)), [])

    def test_no_exit_status_is_unmeasured_whatever_the_text_beside_it_says(self):
        for text in ("",) + REFUSALS:
            with self.subTest(text=text):
                problems = judged(user_namespace=(None, text))
                self.assertEqual([p for p in problems if p.startswith(UNMEASURED)], [f"{UNMEASURED} (exit None: {text})"],
                                 problems)
                self.assertEqual(len(problems), 1, problems)

    def test_a_try_that_was_never_recorded_is_the_same_problem(self):
        self.assertEqual(judged(), [f"{UNMEASURED} (exit None: )"])


if __name__ == "__main__":
    unittest.main()
