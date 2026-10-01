"""QP-2.6 Q1 — independence of the two witnesses, for every active probe (CYCLE2-QUALIFICATION-PLAN §2).

The implementer's and the verifier's checkouts of one revision give the same verdict for every active probe kind, on a
revision that commits stale bytecode, when one checkout differs from the other only in what a checkout may differ in:
CRLF line endings (core.autocrlf on one side), the executable bit, and file dates — including dates that collide with
the committed bytecode's header (the P7-FINDING-001 condition, generalised to the Cycle-2 probes). Each probe is also given an observable that
does not hold, so agreement is on the verdict, never on an always-SATISFIED answer.
"""

import os
import pathlib
import py_compile
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import BehaviorVerdict, SubjectAbsence  # noqa: E402
from aisef2.probe import catalog  # noqa: E402
from aisef2.probe.protocol import ExecutionEnv, RevisionRef, run_probe  # noqa: E402
from aisef2.product.outcome import Executed  # noqa: E402
from aisef2.product.spec import ProductProofSpec  # noqa: E402

S, R = BehaviorVerdict.SATISFIED, BehaviorVerdict.REFUTED
SOURCE = "def add(a, b):\n    return a + b\n"
STALE = "def add(a, b):\n    return a - b\n"   # same size: a header whose (mtime, size) matches SOURCE's is a collision
MAIN = "import sys\n\nfrom app.calc import add\n\nsys.exit(add(1, 2))\n"
FILES = {"app/__init__.py": "", "app/calc.py": SOURCE, "app/__main__.py": MAIN, "README.md": "calc\n"}
STAMP = 1_700_000_000
_GIT_ENV = {"GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "maintenance.auto", "GIT_CONFIG_VALUE_0": "false",
            "GIT_CONFIG_KEY_1": "gc.auto", "GIT_CONFIG_VALUE_1": "0"}


def git(repo, *args: str) -> str:
    p = subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t.t", "-c", "core.autocrlf=false",
                        *args], capture_output=True, encoding="utf-8", env={**os.environ, **_GIT_ENV})
    if p.returncode != 0:
        raise AssertionError(f"git {args}: {p.stderr}")
    return p.stdout.strip()


def spec(probe, kind, locator, observable, stimulus, expectation):
    return ProductProofSpec.create(
        contract_id=f"BC-WITNESS-{kind}", probe_id=probe.id, probe_digest=probe.digest,
        probe_input={"subject": {"kind": kind, "locator": locator}, "stimulus": stimulus,
                     "observable": {**observable, "within_s": 30}, "subject_absence": SubjectAbsence.REQUIRES_SUBJECT.value},
        candidate_expectation=expectation, compiler_id="qp-2.6", compiler_digest="c" * 64)


#: kind -> (locator, stimulus, observable that holds on SOURCE, observable that does not); the stale bytecode would
#: answer neither (a - b)
CASES = {
    "file_artifact": ("path:app/calc.py", {"grep": r"return a \+ b"}, {"matches": 1}, {"matches": 2}),
    "cli_invocation": ("app:__main__", {"argv": []}, {"exit_code": 3}, {"exit_code": 4}),
    "process_effect": ("app.calc:add", {"scenario": [{"step": "call", "args": [1, 2], "kwargs": {}}]}, {"returns": 3}, {"returns": 4}),
    "python_callable": ("app.calc:add", {"args": [1, 2]}, {"returns": 3}, {"returns": 4}),
}


class WitnessIndependence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="aisef2-witness-", ignore_cleanup_errors=True)
        base = pathlib.Path(cls._tmp.name)
        cls.repo = base / "repo"
        cls.repo.mkdir()
        git(cls.repo, "init", "-q", "-b", "main")
        for rel, text in FILES.items():
            p = cls.repo / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(text.encode("utf-8"))
        # committed stale bytecode: compiled from STALE, its header dated STAMP with SOURCE's size
        stale = base / "stale.py"
        stale.write_bytes(STALE.encode("utf-8"))
        os.utime(stale, (STAMP, STAMP))
        tag = sys.implementation.cache_tag
        pyc = cls.repo / "app" / "__pycache__" / f"calc.{tag}.pyc"
        pyc.parent.mkdir()
        py_compile.compile(str(stale), cfile=str(pyc), doraise=True, invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP)
        git(cls.repo, "add", "-A", "-f")
        git(cls.repo, "commit", "-q", "-m", "revision with committed stale bytecode")
        cls.sha = git(cls.repo, "rev-parse", "HEAD")
        cls.checkouts = {"implementer": cls._worktree("implementer")}
        # the verifier's checkouts: CRLF (as core.autocrlf=true writes them), the executable bit, colliding dates
        crlf = cls._worktree("verifier-crlf")
        for rel in FILES:
            p = crlf / rel
            p.write_bytes(p.read_bytes().replace(b"\n", b"\r\n"))
        cls.checkouts["verifier-crlf"] = crlf
        mode = cls._worktree("verifier-exec-bit")
        for rel in FILES:
            os.chmod(mode / rel, 0o755)
        cls.checkouts["verifier-exec-bit"] = mode
        dated = cls._worktree("verifier-colliding-dates")
        for p in dated.rglob("*"):
            if p.is_file() and ".git" not in p.parts:
                os.utime(p, (STAMP, STAMP))
        cls.checkouts["verifier-colliding-dates"] = dated
        cls.probes = catalog.probes_by_id()

    @classmethod
    def _worktree(cls, name: str) -> pathlib.Path:
        wt = cls.repo.parent / name
        git(cls.repo, "worktree", "add", "-q", "--detach", str(wt), cls.sha)
        return wt

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def verdict(self, probe, s, where: str):
        env = ExecutionEnv(sys.executable, 60.0, probe.enforcement())
        result = run_probe(probe, s, RevisionRef(self.sha, str(self.checkouts[where])), env).result
        self.assertIsInstance(result, Executed, f"{s.probe_id} at {where}: {result!r}")
        return result.behavior_verdict

    def test_every_active_probe_gives_one_verdict_at_every_checkout_of_the_revision(self):
        active = catalog.active()
        self.assertEqual(sorted(k.value for k in active), sorted(CASES))
        for kind_, entry in sorted(active.items(), key=lambda kv: kv[0].value):
            probe = self.probes[entry.probe_id]
            locator, stimulus, holds, fails = CASES[kind_.value]
            for observable, expected in ((holds, S), (fails, R)):
                s = spec(probe, kind_.value, locator, observable, stimulus, S)
                seen = {where: self.verdict(probe, s, where) for where in self.checkouts}
                with self.subTest(probe=entry.probe_id, observable=observable):
                    self.assertEqual(set(seen.values()), {expected}, seen)

    def test_the_checkouts_differ_only_where_a_checkout_may(self):
        head = self.checkouts["implementer"]
        for where, wt in self.checkouts.items():
            self.assertEqual(git(wt, "rev-parse", "HEAD"), self.sha, where)
            self.assertTrue((wt / "app" / "__pycache__").is_dir(), where)   # the stale bytecode is committed
        self.assertIn(b"\r\n", (self.checkouts["verifier-crlf"] / "app" / "calc.py").read_bytes())
        self.assertNotIn(b"\r\n", (head / "app" / "calc.py").read_bytes())
        self.assertEqual(int((self.checkouts["verifier-colliding-dates"] / "app" / "calc.py").stat().st_mtime), STAMP)

    def test_the_colliding_checkout_really_carries_the_stale_bytecode_condition(self):
        """Non-vacuity: a plain in-tree import (no isolation, -B only so nothing is written) runs the committed stale
        bytecode at the colliding checkout and the source elsewhere — the condition the probes must not observe."""
        def plain(where):
            return subprocess.run([sys.executable, "-B", "-c", "from app.calc import add; print(add(1, 2))"],
                                  cwd=self.checkouts[where], capture_output=True, encoding="utf-8",
                                  env={k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}).stdout.strip()
        self.assertEqual(plain("verifier-colliding-dates"), "-1")
        self.assertEqual(plain("implementer"), "3")


if __name__ == "__main__":
    unittest.main()
