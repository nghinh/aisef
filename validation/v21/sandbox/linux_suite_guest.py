"""The suite runner INSIDE the Linux guest of linux_suite.sh (V2.1 fix window, lane E; owner 2026-10-15).

`python3 -B linux_suite_guest.py --summary FILE [MODULE ...]` is `python3 -m unittest discover -s tests -v` (no MODULE)
or `python3 -m unittest -v MODULE ...` (MODULE named as discover names it: `v2.test_x`, `test_meta`, `v2.p4.test_y`),
with the same sys.path and argv a `-m unittest` start gives, plus one thing `-m unittest` does not give: what the run
measured — the wall time of every module, the skips with their reasons, the slowest tests, the failing ids — written to
FILE as one JSON object. It starts no process of its own, reads nothing but the tree it runs in, never runs opencode.

The summary is rewritten at every module boundary ("complete": false) and once more when the run ends ("complete":
true), so a run that is killed or dies hard still leaves the numbers of everything before it.

The time of a module is every interval between two test events attributed to the test that follows: module import is
not in it (discovery loads everything first, `load_s`), `setUpClass` of a class is. Within a run the sum of the module
seconds is `run_s`.
"""
import json
import os
import platform
import resource
import sys
import time
import unittest

T0 = time.perf_counter()


def module_of(test) -> str:
    """The module a test (or the holder of a class/module-level error or skip) belongs to."""
    if type(test).__name__ == "_FailedTest":      # a module that did not import: its name is the method name
        return test._testMethodName
    if type(test).__name__ == "_ErrorHolder":
        d = test.id()                       # "setUpClass (v2.test_x.Foo)" / "setUpModule (v2.test_x)"
        inner = d[d.find("(") + 1:d.rfind(")")] if "(" in d else d
        return inner.rsplit(".", 1)[0] if d.startswith("setUpClass") or d.startswith("tearDownClass") else inner
    return type(test).__module__


class Result(unittest.TextTestResult):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.mods: dict[str, dict] = {}
        self.slow: list[tuple[float, str]] = []
        self.skip_rows: list[tuple[str, str]] = []
        self._last = time.perf_counter()
        self._start = self._last
        self._cur = None
        self.runner = None

    def _mod(self, test) -> dict:
        return self.mods.setdefault(module_of(test), {"tests": 0, "seconds": 0.0, "skipped": 0})

    def startTest(self, test):
        now = time.perf_counter()
        if self.runner is not None and module_of(test) != self._cur:
            self._cur = module_of(test)
            self.runner.write_summary(self, complete=False)
        self._mod(test)["seconds"] += now - self._last      # setUpClass / setUpModule of what runs next
        self._start = now
        super().startTest(test)

    def stopTest(self, test):
        super().stopTest(test)
        now = time.perf_counter()
        m = self._mod(test)
        m["tests"] += 1
        m["seconds"] += now - self._start
        self.slow.append((now - self._start, test.id()))
        self._last = now

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self._mod(test)["skipped"] += 1
        self.skip_rows.append((test.id(), reason))


class Runner(unittest.TextTestRunner):
    resultclass = Result
    summary_path = None
    discovered = 0
    load_s = 0.0

    def _makeResult(self):
        r = super()._makeResult()
        r.runner = self
        return r

    def write_summary(self, r, complete: bool) -> None:
        if not self.summary_path:
            return
        wall = time.perf_counter() - T0
        by_reason: dict[str, int] = {}
        for _id, reason in r.skip_rows:
            by_reason[reason] = by_reason.get(reason, 0) + 1
        ru, rc = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
        summary = {
            "complete": complete, "discovered": self.discovered, "ran": r.testsRun,
            "failures": [t.id() for t, _ in r.failures], "errors": [t.id() for t, _ in r.errors],
            "skipped": len(r.skipped), "expected_failures": len(r.expectedFailures),
            "unexpected_successes": [t.id() for t in r.unexpectedSuccesses],
            "successful": complete and r.wasSuccessful(),
            "load_s": round(self.load_s, 2), "run_s": round(wall - self.load_s, 2), "wall_s": round(wall, 2),
            "modules": {k: {"tests": v["tests"], "seconds": round(v["seconds"], 2), "skipped": v["skipped"]}
                        for k, v in sorted(r.mods.items())},
            "skips_by_reason": dict(sorted(by_reason.items(), key=lambda kv: -kv[1])),
            "skips": [{"test": i, "reason": s} for i, s in r.skip_rows],
            "slowest": [{"test": i, "seconds": round(s, 2)} for s, i in sorted(r.slow, reverse=True)[:30]],
            "driver_maxrss_kb": ru.ru_maxrss, "children_maxrss_kb": rc.ru_maxrss,
            "python": platform.python_version(), "platform": platform.platform(),
        }
        tmp = self.summary_path + ".part"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=1, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, self.summary_path)

    def run(self, test):
        self.discovered = test.countTestCases()
        self.load_s = time.perf_counter() - T0
        r = super().run(test)
        self.write_summary(r, complete=True)
        return r


def main(argv: list[str]) -> None:
    if argv[:1] != ["--summary"] or len(argv) < 2:
        sys.exit("usage: linux_suite_guest.py --summary FILE [MODULE ...]")
    Runner.summary_path, modules = argv[1], [m for m in argv[2:] if m != "--"]
    sys.path.insert(0, os.getcwd())               # `-m unittest` puts the cwd first
    if modules:
        sys.path.insert(1, os.path.join(os.getcwd(), "tests"))     # run-tests.sh: PYTHONPATH=tests
        args = ["python -m unittest", "-v", *modules]
    else:
        args = ["python -m unittest", "discover", "-s", "tests", "-v"]
    sys.argv = args
    unittest.main(module=None, argv=args, testRunner=Runner)


if __name__ == "__main__":
    main(sys.argv[1:])
