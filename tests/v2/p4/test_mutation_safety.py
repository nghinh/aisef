"""MUT-SAFE-1..8 (P4-FINDING-011, owner decision of 2026-09-23 §6): the mutation runner's cleanup authority.

Mutated code may report anything as a member, an escapee or a stray; the runner signals only what
`validation/v2/cleanup_authority.py` proves is its own, from its own reading of the host, and refuses the rest as
RESIDUAL_OWNERSHIP_UNKNOWN. Every test spies on os.kill / os.killpg inside the authority (MUT-SAFE-7): a signal to
anything outside the independently captured owned set fails the test at the call, before it is sent.

A canary here is a process that is NOT the runner's: born before the boundary was established (the test's own child
started earlier stands in for an unrelated same-user process — the runner's parent, a shell, an IDE, a launchd agent
— which are also asserted never to be selected, but are never signalled, not even with signal 0)."""

import ast
import importlib.util
import os
import pathlib
import subprocess
import sys
import time
import types
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

POSIX = os.name == "posix"
AUTHORITY = ROOT / "validation/v2/cleanup_authority.py"
RUNNER = ROOT / "validation/v2/mutation.py"


def _load(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses resolve a module's annotations through sys.modules
    spec.loader.exec_module(module)
    return module


def _sleeper() -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True,
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


@unittest.skipUnless(POSIX, "the authority reads a POSIX process table")
class CleanupAuthority(unittest.TestCase):
    """MUT-SAFE-1..7: selection is proved from the runner's own boundary, never from what was reported."""

    def setUp(self):
        self.ca = _load(AUTHORITY, "aisef_v2_cleanup_authority")
        self.canary = _sleeper()  # born BEFORE the boundary: stands in for every process that is not the runner's
        self.addCleanup(lambda: self.canary.poll() is None and self.canary.kill())
        time.sleep(1.1)  # the table reports births to the second: the canary is strictly older than the boundary
        self.boundary = self.ca.establish(ROOT)
        self.mine = _sleeper()  # born AFTER: the runner's own worker
        self.addCleanup(lambda: self.mine.poll() is None and self.mine.kill())
        time.sleep(0.2)
        self.table = self.ca.host_table()
        self.owned = set(self.ca.owned(self.boundary, self.table))
        self.assertIn(self.mine.pid, self.owned)
        self.assertNotIn(self.canary.pid, self.owned)
        self.unrelated = [self.canary.pid, os.getppid(), 1, os.getpid()] + [
            p for p in self.table if self.table[p].ppid == 1 and p not in self.owned][:5]
        # MUT-SAFE-7: the spy refuses, at the call, any target outside the independently captured owned set
        self.sent = []
        real = {"pid": os.kill, "group": os.killpg}  # captured before the patch: the authority's os IS this os

        def spy(kind):
            def send(target, sig):
                self.assertIn(target, self.owned, f"{kind} to a process the runner does not own: {target}")
                self.sent.append((kind, target))
                return real[kind](target, sig)
            return send
        self.spy = [mock.patch.object(self.ca.os, "kill", spy("pid")), mock.patch.object(self.ca.os, "killpg", spy("group"))]
        for p in self.spy:
            p.start()
            self.addCleanup(p.stop)

    def test_MUT_SAFE_1_a_report_of_every_process_on_the_host_selects_only_the_runners_own(self):
        everything = list(self.table)
        report = self.ca.signal_owned(self.boundary, pids=everything, groups=everything, dry_run=True, table=self.table)
        chosen = {s["id"] for s in report.signalled}
        self.assertTrue(chosen <= self.owned, chosen - self.owned)
        self.assertIn(self.mine.pid, chosen)
        self.assertNotIn(self.canary.pid, chosen)
        self.assertEqual(len(report.unproven), 2 * len(everything) - len(report.signalled))
        self.assertIsNone(self.canary.poll())

    def test_MUT_SAFE_2_the_runners_parent_shell_and_launchd_owned_processes_are_never_signalled(self):
        report = self.ca.signal_owned(self.boundary, pids=self.unrelated, groups=self.unrelated, table=self.table)
        self.assertEqual(report.signalled, [])
        self.assertEqual(self.sent, [])
        self.assertTrue(report.residual_ownership_unknown)
        self.assertEqual({u["id"] for u in report.unproven}, set(self.unrelated))
        self.assertIsNone(self.canary.poll())

    def test_MUT_SAFE_3_a_reused_pid_or_pgid_of_an_unrelated_process_is_refused(self):
        # the canary leads its own session: its pid is a valid pgid too — a mutant that reports it is reporting the
        # id of something that is not the runner's, exactly as a reused pid would
        report = self.ca.signal_owned(self.boundary, pids=[self.canary.pid], groups=[self.canary.pid], table=self.table)
        self.assertEqual(report.signalled, [])
        self.assertEqual([u["why"] for u in report.unproven],
                         ["born before the boundary or not a descendant of the runner"] * 2)
        self.assertIsNone(self.canary.poll())

    def test_MUT_SAFE_4_ownership_that_cannot_be_proved_fails_closed(self):
        absent = max(self.table) + 100000
        report = self.ca.signal_owned(self.boundary, pids=[absent, self.mine.pid], groups=[absent], table={})
        self.assertEqual((report.signalled, self.sent), ([], []))
        self.assertTrue(report.residual_ownership_unknown)
        self.assertEqual(self.ca.RESIDUAL_OWNERSHIP_UNKNOWN, "RESIDUAL_OWNERSHIP_UNKNOWN")
        self.assertTrue(all(u["why"] == "not in the host table" for u in report.unproven))

    def test_MUT_SAFE_5_an_owned_child_is_cleaned_and_the_canary_beside_it_survives(self):
        report = self.ca.signal_owned(self.boundary, pids=[self.mine.pid, self.canary.pid],
                                      groups=[self.mine.pid, self.canary.pid], table=self.table)
        self.assertEqual([(s["kind"], s["id"]) for s in report.signalled], [("group", self.mine.pid), ("pid", self.mine.pid)])
        self.assertEqual(report.signalled[0]["proof"]["runner"], os.getpid())
        self.mine.wait(timeout=5)
        self.assertIsNotNone(self.mine.poll())
        self.assertIsNone(self.canary.poll())
        self.assertEqual({u["id"] for u in report.unproven}, {self.canary.pid})

    def test_MUT_SAFE_6_the_finding_011_mutant_cannot_expand_the_cleanup_set(self):
        """The mutant that took the login session down on 2026-09-23 15:38:28 (Python 93138): `_Posix.escaped` with
        `p.group == self.group` turned into `!=`, so it reports (nearly) every process on the host as escaped. Run for
        real, against the real host, its report goes through the authority: nothing outside the owned set."""
        mutation = _load(RUNNER, "aisef_v2_mutation_safety")
        src = (ROOT / "aisef2/runtime/process_range.py").read_text(encoding="utf-8")
        desc, mutated = next((d, s) for d, s in mutation.mutants(src, "_Posix.escaped", {}) if d.endswith("Eq->NotEq"))
        module = types.ModuleType("process_range_mutant")  # the mutated module, as a kill test would load it
        module.__file__ = str(ROOT / "aisef2/runtime/process_range.py")
        sys.modules[module.__name__] = module
        self.addCleanup(sys.modules.pop, module.__name__, None)
        exec(compile(mutated, "process_range(mutant)", "exec"), module.__dict__)
        ns = module.__dict__
        posix = ns["_Posix"]()
        posix.adopt(self.mine.pid)
        reported = [p.pid for p in posix.escaped(self.mine.pid)]  # the mutant's own reading of the host
        self.assertGreater(len(reported), 50, "the mutant is the catastrophic one: it reports the host")
        self.assertIn(self.canary.pid, reported)
        report = self.ca.signal_owned(self.boundary, pids=reported, groups=[p for p in reported], dry_run=True,
                                      table=self.table)
        chosen = {s["id"] for s in report.signalled}
        self.assertTrue(chosen <= self.owned, chosen - self.owned)
        self.assertNotIn(self.canary.pid, chosen)
        self.assertGreater(len(report.unproven), 50)
        self.assertEqual(self.sent, [])  # dry: the selection is proved without a signal

    def test_MUT_SAFE_7_every_signal_the_authority_sends_targets_the_owned_set(self):
        everything = list(self.table)
        report = self.ca.signal_owned(self.boundary, pids=everything, groups=everything, table=self.table)  # live
        self.assertTrue({t for _, t in self.sent} <= self.owned)
        self.assertEqual(sorted(t for _, t in self.sent), sorted(s["id"] for s in report.signalled))
        self.assertIsNone(self.canary.poll())
        self.assertIn(("group", self.mine.pid), self.sent)


class DependencyBoundary(unittest.TestCase):
    """MUT-SAFE-8: the authority is stdlib only, and the runner signals nothing itself."""

    def test_MUT_SAFE_8_the_authority_imports_no_code_under_mutation_and_the_runner_signals_only_through_it(self):
        tree = ast.parse(AUTHORITY.read_text(encoding="utf-8"))
        imported = {(n.names[0].name if isinstance(n, ast.Import) else n.module).split(".")[0]
                    for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))}
        self.assertTrue(imported <= set(sys.stdlib_module_names), imported - set(sys.stdlib_module_names))
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        self.assertFalse({"aisef2", "mutation", "process_table", "descendants", "ProcessRange"} & names)
        runner = ast.parse(RUNNER.read_text(encoding="utf-8"))
        calls = [n for n in ast.walk(runner) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                 and n.func.attr in ("kill", "killpg", "terminate", "send_signal")]
        self.assertEqual(calls, [], [ast.unparse(c) for c in calls])
        self.assertIn("import cleanup_authority as ca", RUNNER.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
