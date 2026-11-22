"""E5 (W1-DESIGN §4.6) — golden success-path byte-identity, NOT a kill file: every non-raising typed path produces a
journal byte-identical to the v2.2.0 reference `story_runner` (git show da3ea33f:…), loaded under a private module
name registered in sys.modules before exec (a slotted dataclass requires it). Each arm runs in a fresh temporary
directory with a fixed clock and fixed git dates, so the journal bytes are deterministic; the reference is run twice
first — a mismatch there names the scenario as "harness not deterministic", never as a product difference. If the
v2.2.0 blob is unavailable the test FAILS; it never skips (CI fetch-depth is 0)."""

import hashlib
import importlib.util
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import ObligationRole  # noqa: E402
from aisef2.orchestrate import story_runner as current  # noqa: E402
from aisef2.orchestrate.quality import TestsPolicy  # noqa: E402
from aisef2.quality import test_execution as te  # noqa: E402
from aisef2.runtime.run_scope import RunScope  # noqa: E402
from tests.v2 import test_p6_orchestration as O  # noqa: E402
from tests.v2.p4.test_run_scope import spec as RUN_SPEC  # noqa: E402

V2_2_0 = "da3ea33f3b695aaca73e87a704145a0193aced23"
_REF_NAME = "aisef2_story_runner_v220_golden"
GIT_ENV = {"GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z", "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z",
           "GIT_CONFIG_NOSYSTEM": "1"}
BROKEN_ADD = "\n\ndef add(a, b):\n    return a - b\n"


def reference():
    if _REF_NAME in sys.modules:
        return sys.modules[_REF_NAME]
    r = subprocess.run(["git", "-C", str(ROOT), "show", f"{V2_2_0}:aisef2/orchestrate/story_runner.py"],
                       capture_output=True, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(f"the v2.2.0 story_runner blob is unavailable (shallow clone?): {r.stderr[:200]}")
    spec = importlib.util.spec_from_loader(_REF_NAME, loader=None)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[_REF_NAME] = mod                       # before exec: @dataclass(slots=True) resolves the module
    exec(compile(r.stdout, _REF_NAME, "exec"), mod.__dict__)
    return mod


#: name -> (dev kwargs | None for default good dev, adapter overrides, plan role, spec key, expected to raise?)
def scenarios():
    good = {"app/calc.py": O.CALC + O.ADD, "tests/test_s1.py": O.TEST_ADD}
    return {
        "commit": dict(files=good),
        "proof-fails-retry-then-rollback": dict(files={"app/calc.py": O.CALC + BROKEN_ADD,
                                                       "tests/test_s1.py": O.TEST_ADD}),
        "developer-outage": dict(outage=True),
        "developer-fails": dict(fail=True),
        "merge-conflict": dict(files=good, on_trunk={"app/calc.py": O.MUL}),
        "no-work": "NO_WORK",
        "review-finding": ("REVIEW", good),
        "scan-finding": ("SCAN", good),
        "reviewer-unrunnable": ("UNRUNNABLE", good),
    }


class Golden(unittest.TestCase):
    maxDiff = None

    def journal(self, mod, scenario) -> bytes:
        """One arm: a fresh world, the scenario through `mod.run_story`, the journal's bytes."""
        import os
        from unittest import mock
        with tempfile.TemporaryDirectory(prefix="aisef-e5-golden-") as t, \
                mock.patch.dict(os.environ, GIT_ENV):
            tmp = pathlib.Path(t)
            repo, base = O.make_repo(tmp)
            for sub in ("ws", "merge", "run"):
                (tmp / sub).mkdir()
            script = str(tmp / "scan.py")
            pathlib.Path(script).write_text(O.SCAN_SCRIPT, encoding="utf-8")
            ws = O.GitWorkspace(repo, tmp / "ws")
            merger = O.GitMerger(repo, "main", tmp / "merge")
            clock = iter(float(n) for n in range(10 ** 6))
            run = RunScope(tmp / "run", "run-golden", spec=RUN_SPEC, clock=lambda: next(clock))
            run.begin()
            try:
                c1, s1 = O.contract("C1", "app.calc:add", [1, 2], 3)
                c0, s0 = O.contract("C0", "app.calc:sub", [3, 1], 2)
                specs = {s1.id: s1, s0.id: s0}
                reviewer, scanner, dev_kw = O.Rev(), O.Scan(script), scenario
                if scenario == "NO_WORK":
                    plan = O.plan_of(base, O.obligation("C-0", s0.id, "S1", ObligationRole.INTRODUCE), pid="PLAN-G")
                    dev = O.Dev()
                else:
                    plan = O.plan_of(base, O.obligation("C-1", s1.id, "S1", ObligationRole.INTRODUCE), pid="PLAN-G")
                    if isinstance(scenario, tuple):
                        kind, files = scenario
                        dev = O.Dev(files)
                        if kind == "REVIEW":
                            reviewer = O.Rev(findings=(O.Finding("F-1", True, ("R-C1",)),))
                        elif kind == "SCAN":
                            scanner = O.Scan(script, findings=(O.Finding("F-2", True, ("R-C1",)),))
                        elif kind == "UNRUNNABLE":
                            reviewer = O.Rev(unrunnable=True)
                    else:
                        dev = O.Dev(**{k: v for k, v in dev_kw.items() if k != "on_trunk"},
                                    on_trunk=dev_kw.get("on_trunk"), repo=repo)
                inputs = mod.StoryInputs(specs, O.PROBE, O.ENV, te.DeveloperTests("S1", ("tests/test_s1.py",)),
                                         te.DeveloperTests("S1", ("tests/test_other.py",)),
                                         te.Dependencies(frozenset(), frozenset({"app", "tests"})), te.UNITTEST)
                adapters = mod.Adapters(dev, reviewer, scanner, merger, ws)
                mod.run_story(run, plan, "S1", inputs, adapters, mod.Policy(O.LIMITS, TestsPolicy(True), tool_timeout_s=60))
                run.shutdown()
            finally:
                if run._writer is not None:
                    run._writer.close()
                run.lease.release()
            return run.journal_path.read_bytes()

    def test_every_typed_path_is_byte_identical_to_v2_2_0(self):
        ref = reference()
        for name, scenario in scenarios().items():
            with self.subTest(name):
                a = self.journal(ref, scenario)
                b = self.journal(ref, scenario)
                self.assertEqual(hashlib.sha256(a).hexdigest(), hashlib.sha256(b).hexdigest(),
                                 f"harness not deterministic for {name}")
                c = self.journal(current, scenario)
                if a != c:
                    for la, lc in zip(a.split(b"\n"), c.split(b"\n"), strict=False):
                        if la != lc:
                            self.fail(f"{name}: first differing journal line:\nv2.2.0 : {la[:300]!r}\ncurrent: {lc[:300]!r}")
                    self.fail(f"{name}: journals differ in length ({len(a)} vs {len(c)} bytes)")


if __name__ == "__main__":
    unittest.main()
