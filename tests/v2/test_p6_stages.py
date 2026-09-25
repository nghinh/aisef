"""WP-6.2 — every stage of the orchestration path on its own, fast: the seam, the gate rows, the typed adapters and
the derived confinement, the git workspace and merger, the two-party proof, the engineering-quality assessment, the
reviewer, the scanner, the merge and post-merge proof, the runner's helpers, and `verified_payload`. The real-path
cases live in test_p6_orchestration; these are the kill tests of each stage module's mutants (validation/v2/mutation.py).
"""

import difflib
import os
import pathlib
import re
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tests.v2.test_p6_orchestration as e2e  # noqa: E402
from aisef2.arch.enums import (  # noqa: E402
    AdequacyOutcome, BehaviorVerdict as V, ContractSatisfaction as CS, ControlProjection as P, Enforcement,
    EventType as T, MeasurementPoint as M, ObligationRole as R, Owner, Polarity, Relevance, SubjectAbsence, Vacuity,
)
from aisef2.control.owner import FailureCode as F  # noqa: E402
from aisef2.errors import InvariantError  # noqa: E402
from aisef2.journal import format3 as f3  # noqa: E402
from aisef2.journal.format2 import OperationOutcome as O, ResourceKind as K  # noqa: E402
from aisef2.orchestrate import adapters, gate, merge as mg, proof as pf, quality as ql, review as rv  # noqa: E402
from aisef2.orchestrate import seam, security as sc, story_runner as sr, workspace as ws  # noqa: E402
from aisef2.orchestrate.adapters import (  # noqa: E402
    CapabilityUnrunnable, Finding, Implemented, Merge, MergeOutcome, ReadOnlyScope,
)
from aisef2.probe.protocol import ExecutionEnv  # noqa: E402
from aisef2.probe.python_callable import PythonCallableProbe  # noqa: E402
from aisef2.product.outcome import Executed, Unrunnable  # noqa: E402
from aisef2.quality import test_execution as te  # noqa: E402
from aisef2.quality.adequacy import assemble  # noqa: E402
from aisef2.runtime.run_scope import RunScope  # noqa: E402
from aisef2.runtime.story_scope import Residual  # noqa: E402
from tests.v2.p4.test_run_scope import spec as RUN_SPEC  # noqa: E402
from tests.v2.p4.world import closed_after  # noqa: E402
from tests.v2.test_v2_005 import FAILED, INTEGRATION_GAP, RAN, UNRUNNABLE  # noqa: E402

SHA_A, SHA_B, SHA_C = "a" * 40, "b" * 40, "c" * 40
ENV = ExecutionEnv(sys.executable, 30, Enforcement.PARTIAL)


class FakeRange:
    kind = K.PROCESS_RANGE

    def __init__(self, name):
        self.name, self.released = name, 0

    def release(self):
        self.released += 1


class FakeProbe:
    """Answers per spec id (a ProbeResult or a callable of the RevisionRef); the real python_callable identity, so
    the compiled specs bind to it. With `on_range` it reports one fake process range per evaluation."""
    id, digest = PythonCallableProbe.id, PythonCallableProbe.digest

    def __init__(self, answers, on_range=None, level=Enforcement.PARTIAL):
        self.answers, self.on_range, self.level, self.seen = answers, on_range, level, []

    def enforcement(self):
        return self.level

    def harness_preconditions(self):
        return ()

    def evaluate(self, spec, at, env):
        self.seen.append((spec.id, at.sha, at.root))
        if self.on_range is not None:
            self.on_range(FakeRange(f"probe {spec.id}"))
        a = self.answers[spec.id]
        return a(at) if callable(a) else a


class Other(FakeProbe):
    digest = "1" * 64


def factory(answers, **kw):
    return lambda on_range: FakeProbe(answers, on_range, **kw)


class Journal(unittest.TestCase):
    """A run with a frozen plan and an ACTIVE story S1 (admitted by hand), as every journaling stage needs."""

    def setUp(self):
        self._d = tempfile.TemporaryDirectory(prefix="aisef2-stages-")
        self.addCleanup(self._d.cleanup)
        self.tmp = pathlib.Path(self._d.name)
        self.clock = iter(float(n) for n in range(10 ** 6))
        self.run = closed_after(self, RunScope(self.tmp / "run", "run-stages", spec=RUN_SPEC, clock=lambda: next(self.clock)))
        self.run.begin()
        self.c1, self.s1 = e2e.contract("C1", "app.calc:add", [1, 2], 3)
        self.c0, self.s0 = e2e.contract("C0", "app.calc:sub", [3, 1], 2)
        self.specs = {self.s1.id: self.s1, self.s0.id: self.s0}
        self.plan = e2e.plan_of(SHA_A, e2e.obligation("C1", self.s1.id, "S1", R.INTRODUCE),
                                e2e.obligation("C0", self.s0.id, "S0", R.PRESERVE),
                                e2e.obligation("C0V", self.s0.id, "S2", R.VERIFY))
        sr._freeze_plan(self.run, self.plan)
        (self.tmp / "impl").mkdir()
        (self.tmp / "ver").mkdir()

    def activate(self, story="S1", dispositions=None, parent=SHA_A):
        d = dispositions or {"C1": "READY"}
        self.run.append(T.STORY_BEGIN, {"story_id": story, "parent": parent})
        self.run.append(T.STORY_ADMITTED, {"story_id": story, "parent": parent, "admitted": True,
                                           "developer_call_permitted": "READY" in d.values(), "dispositions": d})
        return self.run.story(story)

    def events(self, kind, story=None):
        return [e for e in self.run.events if e.type == kind and (story is None or e.data.get("story_id") == story)]

    def checks(self, prefix=""):
        return [(e.data["check"], e.data["passed"]) for e in self.events("gate/check") if e.data["check"].startswith(prefix)]


# --------------------------------------------------------------------------------------------- seam

class Seam(unittest.TestCase):
    TABLE = {"rows": [
        {"v1_mode": "CHANGE_REQUIRED", "obligation_role": "INTRODUCE", "polarity": "MUST_HOLD",
         "subject_absence": "HUMAN_DECLARATION_REQUIRED", "reason": "HUMAN_DECLARATION_REQUIRED"},
        {"v1_mode": "DECLARED", "obligation_role": "PRESERVE", "polarity": "MUST_NOT_HOLD",
         "subject_absence": "REQUIRES_SUBJECT", "reason": "MAPPED"},
        {"v1_mode": "REASON_ONLY", "obligation_role": "VERIFY", "polarity": "MUST_HOLD",
         "subject_absence": "REQUIRES_SUBJECT", "reason": "HUMAN_DECLARATION_REQUIRED"},
    ]}

    def test_a_row_needing_a_declaration_is_refused_without_a_typed_one_and_resolved_with_it(self):
        with self.assertRaisesRegex(seam.SeamRefusal, r"^C1 \(CHANGE_REQUIRED\): HUMAN_DECLARATION_REQUIRED$") as cm:
            seam.resolve("C1", "CHANGE_REQUIRED", self.TABLE, None)
        self.assertEqual((cm.exception.criterion_id, cm.exception.mode, cm.exception.reason),
                         ("C1", "CHANGE_REQUIRED", "HUMAN_DECLARATION_REQUIRED"))
        with self.assertRaises(seam.SeamRefusal):
            seam.resolve("C1", "CHANGE_REQUIRED", self.TABLE, "REQUIRES_SUBJECT")     # a string is not a declaration
        legacy = seam.resolve("C1", "CHANGE_REQUIRED", self.TABLE, SubjectAbsence.REQUIRES_SUBJECT)
        self.assertEqual(legacy, seam.Legacy("C1", "CHANGE_REQUIRED", R.INTRODUCE, Polarity.MUST_HOLD,
                                             SubjectAbsence.REQUIRES_SUBJECT))
        with self.assertRaises(seam.SeamRefusal):     # the reason alone demands a declaration
            seam.resolve("C3", "REASON_ONLY", self.TABLE, None)
        self.assertEqual(seam.resolve("C3", "REASON_ONLY", self.TABLE, SubjectAbsence.REQUIRES_SUBJECT).role, R.VERIFY)

    def test_a_mapped_row_takes_its_absence_from_the_table_and_never_from_the_declaration(self):
        legacy = seam.resolve("C2", "DECLARED", self.TABLE, None)
        self.assertEqual((legacy.role, legacy.polarity, legacy.subject_absence),
                         (R.PRESERVE, Polarity.MUST_NOT_HOLD, SubjectAbsence.REQUIRES_SUBJECT))
        with self.assertRaisesRegex(seam.SeamRefusal, "no row in the migration table"):
            seam.resolve("C9", "NOT_A_MODE", self.TABLE, SubjectAbsence.REQUIRES_SUBJECT)

    def test_admit_legacy_resolves_all_in_criterion_order_or_refuses_before_any(self):
        self.assertEqual(seam.admit_legacy({}, None, {}), ())
        with self.assertRaisesRegex(seam.SeamRefusal, r"^C1 \(CHANGE_REQUIRED\): no migration table$"):
            seam.admit_legacy({"C1": "CHANGE_REQUIRED"}, None, {"C1": SubjectAbsence.REQUIRES_SUBJECT})
        out = seam.admit_legacy({"C2": "DECLARED", "C1": "CHANGE_REQUIRED"}, self.TABLE,
                                {"C1": SubjectAbsence.REQUIRES_SUBJECT})
        self.assertEqual([x.criterion_id for x in out], ["C1", "C2"])
        self.assertIsInstance(out, tuple)
        with self.assertRaises(seam.SeamRefusal):
            seam.admit_legacy({"C2": "DECLARED", "C1": "CHANGE_REQUIRED"}, self.TABLE, {})
        table = e2e.json.loads((ROOT / "closure-evidence/v2/P6-MIGRATION-TABLE.json").read_text(encoding="utf-8"))
        for row in table["rows"]:                       # the generated table: every row needs a declaration
            with self.assertRaises(seam.SeamRefusal):
                seam.resolve("C", row["v1_mode"], table, None)


# --------------------------------------------------------------------------------------------- gate

class Gate(Journal):
    def test_a_check_row_and_a_decision_citing_rows(self):
        a = gate.check(self.run, "S1", "admission", 1, "admitted")
        b = gate.check(self.run, "S1", "merge", 0, "conflict")
        ea, eb = self.run.events[a], self.run.events[b]
        self.assertEqual(dict(ea.data), {"gate": "story", "check": "S1:admission", "passed": True, "detail": "admitted"})
        self.assertEqual(dict(eb.data), {"gate": "story", "check": "S1:merge", "passed": False, "detail": "conflict"})
        self.assertIs(ea.data["passed"], True)
        seq = gate.decision(self.run, (a, b), 0)
        d = self.run.events[seq]
        self.assertEqual((d.type, tuple(d.source_seqs), d.data["passed"], d.data["gate"]), ("gate/decision", (a, b), False, "story"))
        self.assertIs(d.data["passed"], False)
        self.assertEqual(list(d.data["projections"]), ["story_state", "budgets", "failure_owner", "retry_target"])
        self.assertEqual(gate.GATE, "story")


# --------------------------------------------------------------------------------------------- adapters

class Adapters(unittest.TestCase):
    def test_a_developer_answer_is_COMPLETED_with_a_candidate_or_FAILED_without(self):
        self.assertEqual(Implemented(O.COMPLETED, SHA_A, "x").candidate, SHA_A)
        self.assertIsNone(Implemented(O.FAILED, None, "x").candidate)
        for outcome, cand, why in (
                (O.COMPLETED, None, "^a completed developer answer names its candidate; a failed one names none$"),
                (O.FAILED, SHA_A, "^a completed developer answer names its candidate; a failed one names none$"),
                (O.SIGNALLED, None, "^a developer answer is COMPLETED or FAILED$"),
                (O.NOT_STARTED, SHA_A, "^a developer answer is COMPLETED or FAILED$"),
                (O.COMPLETED, "main", "^a candidate is an immutable reference: a full SHA, never a branch or a tag$"),
                (O.COMPLETED, SHA_A[:12], "^a candidate is an immutable reference: a full SHA, never a branch or a tag$")):
            with self.subTest(outcome=outcome, candidate=cand), self.assertRaisesRegex(InvariantError, why):
                Implemented(outcome, cand, "x")

    def test_a_finding_blocks_only_when_blocking_and_corroborated(self):
        self.assertEqual([Finding("f", b, c).blocks for b in (True, False) for c in (("x",), ())],
                         [True, False, False, False])

    def test_a_merge_names_its_revision_exactly_when_merged(self):
        self.assertEqual(Merge(MergeOutcome.MERGED, SHA_A, ()).revision, SHA_A)
        self.assertEqual(Merge(MergeOutcome.CONFLICT, None, ("a.py",)).conflicts, ("a.py",))
        for outcome, rev in ((MergeOutcome.MERGED, None), (MergeOutcome.CONFLICT, SHA_A)):
            with self.subTest(outcome=outcome), \
                    self.assertRaisesRegex(InvariantError, "^a merge names its merged revision; a conflict names none$"):
                Merge(outcome, rev, ())

    def test_confinement_is_derived_from_an_existing_checkout_and_reverses(self):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            (root / "pkg").mkdir()
            (root / "pkg" / "m.py").write_text("x = 1\n", encoding="utf-8")
            (root / ".git").mkdir()
            (root / ".git" / "HEAD").write_text("ref\n", encoding="utf-8")
            (root / "b.txt").write_bytes(b"\x00\x01")
            scope = adapters.confine("S1", d)
            self.assertEqual((scope.story_id, scope.root), ("S1", str(root)))
            self.assertEqual(scope.files(), ("b.txt", "pkg/m.py"))          # sorted, posix, no .git
            listed = list(root.rglob("*"))
            with mock.patch.object(pathlib.Path, "rglob", return_value=iter(sorted(listed, reverse=True))):
                self.assertEqual(scope.files(), ("b.txt", "pkg/m.py"))      # whatever order the tree lists in
            self.assertEqual(scope.read("b.txt"), b"\x00\x01")
            writable = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
            for rel in ("pkg", "pkg/m.py", "b.txt"):
                self.assertEqual(stat.S_IMODE((root / rel).stat().st_mode) & writable, 0, rel)
            self.assertTrue(stat.S_IMODE((root / ".git" / "HEAD").stat().st_mode) & stat.S_IWUSR)   # .git untouched
            with self.assertRaises(PermissionError):
                (root / "pkg" / "m.py").write_text("tampered", encoding="utf-8")
            head = root / ".git" / "HEAD"
            os.chmod(head, stat.S_IMODE(head.stat().st_mode) & ~stat.S_IWUSR)      # .git is never touched either way
            adapters.unconfine(scope)
            for rel in ("pkg", "pkg/m.py", "b.txt"):
                self.assertTrue(stat.S_IMODE((root / rel).stat().st_mode) & stat.S_IWUSR, rel)
            self.assertEqual(stat.S_IMODE(head.stat().st_mode) & stat.S_IWUSR, 0)
            os.chmod(head, stat.S_IMODE(head.stat().st_mode) | stat.S_IWUSR)
            (root / "pkg" / "m.py").write_text("x = 2\n", encoding="utf-8")
            with self.assertRaisesRegex(InvariantError, r"^a read-only scope is derived from an existing checkout, not '.*nowhere'$"):
                adapters.confine("S1", str(root / "nowhere"))
        self.assertEqual(list(e2e.inspect.signature(adapters.confine).parameters), ["story_id", "checkout"])


# --------------------------------------------------------------------------------------------- workspace

class Workspace(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory(prefix="aisef2-ws-")
        self.addCleanup(self._d.cleanup)
        self.tmp = pathlib.Path(self._d.name)
        self.repo, self.base = e2e.make_repo(self.tmp)
        (self.tmp / "ws").mkdir()
        (self.tmp / "merge").mkdir()
        self.ws = ws.GitWorkspace(self.repo, self.tmp / "ws")
        self.merger = ws.GitMerger(self.repo, "main", self.tmp / "merge")

    def commit_on(self, files, message="c"):
        wt = self.ws.checkout("c-" + message.replace(" ", "-"), self.base)
        for rel, text in files.items():
            pathlib.Path(wt.path, rel).parent.mkdir(parents=True, exist_ok=True)
            pathlib.Path(wt.path, rel).write_text(text, encoding="utf-8")
        sha = ws.commit_all(wt.path, message)
        wt.release()
        return sha

    def test_git_runs_without_background_maintenance_and_sha_resolves_commits_only(self):
        self.assertEqual(ws._NO_BACKGROUND_GIT, {"GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "maintenance.auto",
                                                 "GIT_CONFIG_VALUE_0": "false", "GIT_CONFIG_KEY_1": "gc.auto",
                                                 "GIT_CONFIG_VALUE_1": "0"})
        p = ws.git(self.repo, "config", "--get", "maintenance.auto")
        self.assertEqual((p.returncode, p.stdout.strip()), (0, "false"))
        with mock.patch.dict(os.environ, {"GIT_AUTHOR_NAME": "Envtest", "GIT_AUTHOR_EMAIL": "e@x"}):
            self.assertTrue(ws.git(self.repo, "var", "GIT_AUTHOR_IDENT").stdout.startswith("Envtest <e@x>"))   # the parent's environment, plus the two
        c = self.ws.checkout("wt-bytes", self.base)
        pathlib.Path(c.path, "bytes.bin").write_bytes(b"not utf-8: \xff\xfe\n")
        ws.commit_all(c.path, "bytes")
        self.assertEqual(ws.git(c.path, "show", "HEAD:bytes.bin").stdout, "not utf-8: \ufffd\ufffd\n")   # replaced, never raised
        c.release()
        self.assertEqual(ws._sha(self.repo, "main"), self.base)
        self.assertEqual(ws._sha(self.repo, self.base[:8]), self.base)
        for bad in ("nope", "main^{tree}", "HEAD:app/calc.py"):
            with self.subTest(rev=bad), self.assertRaisesRegex(InvariantError, "^" + re.escape(repr(bad)) + " is not a commit of "):
                ws._sha(self.repo, bad)

    def test_scratch_is_a_handle_owned_directory_released_by_its_own_cleanup(self):
        s = self.ws.scratch("scratch-S1")
        self.assertEqual((s.name, s.kind), ("scratch-S1", K.SCRATCH))
        self.assertTrue(s.path.is_dir() and s.path.parent == self.tmp / "ws" and s.path.name.startswith("scratch-S1-"))
        s.release()
        self.assertFalse(s.path.exists())
        with self.assertRaisesRegex(adapters.ResourceUnavailable, r"^scratch x: \[Errno \d+\] "):
            ws.GitWorkspace(self.repo, self.tmp / "absent").scratch("x")

        class Stuck(tempfile.TemporaryDirectory):
            def cleanup(self):
                pass
        stuck = ws.Scratch("st", Stuck(dir=self.tmp))
        with self.assertRaisesRegex(Residual, "^scratch st survived its cleanup at "):
            stuck.release()

    def test_checkouts_are_detached_worktrees_at_a_full_sha_moved_and_released_through_git(self):
        c = self.ws.checkout("wt-S1", self.base)
        self.assertEqual((c.name, c.kind, c.revision, c.path), ("wt-S1", K.WORKTREE, self.base, self.tmp / "ws" / "wt-S1"))
        self.assertEqual(ws._sha(c.path, "HEAD"), self.base)
        self.assertEqual(ws.git(c.path, "symbolic-ref", "-q", "HEAD").returncode, 1)     # detached
        with self.assertRaisesRegex(adapters.ResourceUnavailable, r"^checkout wt-S1: .*wt-S1 already exists$"):
            self.ws.checkout("wt-S1", self.base)                                          # exists
        with self.assertRaisesRegex(InvariantError, "^a checkout is named by a full SHA, not 'main'$"):
            self.ws.checkout("wt-x", "main")
        with self.assertRaisesRegex(adapters.ResourceUnavailable, r"^checkout wt-y at 000000000000: git worktree add exited [1-9]\d*$"):
            self.ws.checkout("wt-y", "0" * 40)                                            # not a commit
        self.assertFalse((self.tmp / "ws" / "wt-y").exists())
        new = self.commit_on({"app/calc.py": e2e.CALC + e2e.ADD})
        pathlib.Path(c.path, "junk.txt").write_text("x", encoding="utf-8")
        self.ws.move(c, new)
        self.assertEqual((c.revision, ws._sha(c.path, "HEAD")), (new, new))
        self.assertFalse(pathlib.Path(c.path, "junk.txt").exists())                        # cleaned
        self.assertIn("def add", pathlib.Path(c.path, "app/calc.py").read_text(encoding="utf-8"))
        with self.assertRaisesRegex(InvariantError, "^a checkout moves to a full SHA, not 'main'$"):
            self.ws.move(c, "main")
        with self.assertRaisesRegex(adapters.ResourceUnavailable, r"^checkout wt-S1 to 000000000000: git checkout exited [1-9]\d*$"):
            self.ws.move(c, "0" * 40)
        self.assertEqual(c.revision, new)
        diff = self.ws.diff(self.base, new)
        self.assertIn("+def add(a, b):", diff)
        self.assertEqual(self.ws.diff(new, new), "")
        with self.assertRaisesRegex(InvariantError, r"^git diff [0-9a-f]{12}\.\.000000000000 exited [1-9]\d*$"):
            self.ws.diff(self.base, "0" * 40)
        c.release()
        self.assertFalse(c.path.exists())
        self.assertNotIn("wt-S1", ws.git(self.repo, "worktree", "list").stdout)
        plain = self.tmp / "ws" / "plain"
        plain.mkdir()
        with self.assertRaisesRegex(Residual, r"^worktree plain survived its removal at .* \(git exited [1-9]\d*\)$"):
            ws.Checkout("plain", self.repo, plain, self.base).release()                  # not a worktree: git cannot remove it

    def test_the_merger_types_merged_conflict_and_up_to_date_from_git(self):
        self.assertEqual(self.merger.base(), self.base)
        cand = self.commit_on({"app/calc.py": e2e.CALC + e2e.ADD}, "add")
        m = self.merger.merge(cand)
        self.assertEqual((m.outcome, m.conflicts), (MergeOutcome.MERGED, ()))
        self.assertEqual(self.merger.base(), m.revision)
        self.assertEqual(ws.git(self.repo, "log", "-1", "--format=%s", m.revision).stdout.strip(), f"merge {cand[:12]}")
        self.assertEqual(ws.git(self.repo, "rev-parse", f"{m.revision}^1").stdout.strip(), self.base)
        self.assertEqual(ws.git(self.repo, "rev-parse", f"{m.revision}^2").stdout.strip(), cand)
        again = self.merger.merge(cand)                                                   # already merged: up to date
        self.assertEqual((again.outcome, again.revision), (MergeOutcome.MERGED, m.revision))
        other = self.commit_on({"app/calc.py": e2e.CALC + "\n\ndef add(a, b):\n    return b + a\n"}, "other add")
        c = self.merger.merge(other)
        self.assertEqual((c.outcome, c.revision, c.conflicts), (MergeOutcome.CONFLICT, None, ("app/calc.py",)))
        self.assertEqual(self.merger.base(), m.revision)                                  # untouched by a conflict
        self.assertEqual([p for p in (self.tmp / "merge").iterdir()], [])                  # the merge worktree is gone
        for ref in ("main", other[:12], "HEAD"):
            with self.subTest(ref=ref), self.assertRaisesRegex(InvariantError, f"^a merge takes a full SHA, not {ref!r}$"):
                self.merger.merge(ref)                                                    # only an immutable reference
        self.assertEqual(self.merger.base(), m.revision)
        (self.tmp / "merge" / f"merge-{m.revision[:12]}-{other[:12]}").mkdir()
        with self.assertRaisesRegex(RuntimeError, r"^merge worktree .*merge-[0-9a-f]{12}-[0-9a-f]{12} already exists$"):
            self.merger.merge(other)

        class Stale(ws.GitMerger):
            def base(self):
                return ws._sha(self.repo, "main^1")                                       # a view the branch has left
        with self.assertRaisesRegex(RuntimeError, "^branch main moved during the merge: not updated$"):
            Stale(self.repo, "main", self.tmp / "merge").merge(other)
        self.assertEqual(self.merger.base(), m.revision)
        (self.tmp / "not-a-dir").write_text("", encoding="utf-8")                      # a root git cannot create under
        with self.assertRaisesRegex(RuntimeError, r"^merge worktree: git worktree add exited [1-9]\d*$"):
            ws.GitMerger(self.repo, "main", self.tmp / "not-a-dir").merge(other)
        wt = self.ws.checkout("wt-orphan", self.base)                                     # an unrelated history: git refuses,
        self.assertEqual(ws.git(wt.path, "checkout", "-q", "--orphan", "island").returncode, 0)   # with no unmerged path
        pathlib.Path(wt.path, "island.txt").write_text("i", encoding="utf-8")
        orphan = ws.commit_all(wt.path, "island")
        wt.release()
        with self.assertRaisesRegex(RuntimeError, r"^git merge exited [1-9]\d* without unmerged paths$"):
            self.merger.merge(orphan)
        self.assertEqual(self.merger.base(), m.revision)
        two = self.commit_on({"app/new.py": "n = 1\n", "tests/test_other.py": "x = 1\n"}, "two files")
        three = self.commit_on({"app/new.py": "n = 2\n", "tests/test_other.py": "x = 2\n"}, "three files")
        self.assertEqual(self.merger.merge(two).outcome, MergeOutcome.MERGED)
        c2 = self.merger.merge(three)
        self.assertEqual((c2.outcome, c2.conflicts), (MergeOutcome.CONFLICT, ("app/new.py", "tests/test_other.py")))

    def test_revert_undoes_exactly_the_merge_at_the_tip(self):
        cand = self.commit_on({"app/calc.py": e2e.CALC + e2e.ADD}, "add")
        with self.assertRaisesRegex(Residual, f"^branch main is not at the merge {cand[:12]}: nothing reverted$"):
            self.merger.revert(cand)
        m = self.merger.merge(cand)
        self.merger.revert(m.revision)
        self.assertEqual(self.merger.base(), self.base)
        with self.assertRaisesRegex(Residual, f"^branch main is not at the merge {m.revision[:12]}: nothing reverted$"):
            self.merger.revert(m.revision)
        for ref in ("main", m.revision[:12]):
            with self.subTest(ref=ref), self.assertRaisesRegex(InvariantError, f"^a revert takes the merge's full SHA, not {ref!r}$"):
                self.merger.revert(ref)
        m2 = self.merger.merge(cand)
        real = ws.git

        def refusing(repo, *args):                     # the branch update itself refused: reported, nothing else touched
            if args[:1] == ("update-ref",):
                return subprocess.CompletedProcess(args, 1, "", "refused")
            return real(repo, *args)
        with mock.patch.object(ws, "git", refusing), \
                self.assertRaisesRegex(Residual, f"^branch main could not be reset to {self.base[:12]}$"):
            self.merger.revert(m2.revision)
        self.assertEqual(self.merger.base(), m2.revision)
        self.merger.revert(m2.revision)
        self.assertEqual(self.merger.base(), self.base)

    def test_commit_all_stages_everything_and_names_the_commit(self):
        c = self.ws.checkout("wt", self.base)
        pathlib.Path(c.path, "new.txt").write_text("n", encoding="utf-8")
        sha = ws.commit_all(c.path, "new file")
        self.assertEqual(ws._sha(c.path, "HEAD"), sha)
        self.assertEqual(ws.git(c.path, "show", "--stat", "--format=%s", "HEAD").stdout.splitlines()[0], "new file")
        self.assertIn("new.txt", ws.git(c.path, "show", "--stat", "--format=", "HEAD").stdout)
        with self.assertRaisesRegex(RuntimeError, r"^git commit exited [1-9]\d*$"):
            ws.commit_all(self.tmp, "not a repo")


# --------------------------------------------------------------------------------------------- proof

class ProofStage(Journal):
    def party(self, answers, label, **kw):
        return pf.Party(self.scope, factory(answers, **kw), label)

    def prove(self, implementer, verifier, role=R.INTRODUCE, point=M.CANDIDATE, criterion="C1", spec=None, candidate=SHA_B):
        return pf.prove(self.run, "S1", criterion, spec or self.s1, role, implementer=implementer, verifier=verifier,
                        candidate=candidate, implementer_root=str(self.tmp / "impl"), verifier_root=str(self.tmp / "ver"),
                        env=ENV, point=point)

    def setUp(self):
        super().setUp()
        self.scope = self.activate()

    def test_agreement_is_a_cited_proof_read_through_the_binding_and_routed_by_point(self):
        sat = {self.s1.id: Executed(V.SATISFIED)}
        p = self.prove(self.party(sat, "implementer"), self.party(sat, "verifier"))
        self.assertEqual((p.criterion_id, p.spec_id, p.agreement, p.satisfaction, p.failure), ("C1", self.s1.id, True, CS.SATISFIED, None))
        a, b, v = (self.run.events[s] for s in (p.implementer_seq, p.verifier_seq, p.verified_seq))
        self.assertEqual([a.type, b.type, v.type], ["probe/evaluated", "probe/evaluated", "proof/verified"])
        self.assertEqual(tuple(v.source_seqs), (a.seq, b.seq))
        self.assertEqual((a.data["record"]["revision"], b.data["record"]["revision"]), (SHA_B, SHA_B))
        self.assertEqual(dict(v.data), {"story_id": "S1", "criterion_id": "C1", "spec_id": self.s1.id,
                                        "semantic_hash": self.s1.semantic_hash, "candidate": SHA_B, "agreement": True,
                                        "verdict": "SATISFIED"})
        for role, cid in ((R.PRESERVE, "C1p"), (R.VERIFY, "C1v")):     # Scenario L: the role changes nothing at the candidate
            q = self.prove(self.party(sat, "implementer"), self.party(sat, "verifier"), role=role, criterion=cid)
            self.assertEqual((q.satisfaction, q.failure), (CS.SATISFIED, None))
            self.assertEqual({k: v for k, v in self.run.events[q.verified_seq].data.items() if k != "criterion_id"},
                             {k: v for k, v in v.data.items() if k != "criterion_id"})
        unsat = {self.s1.id: Executed(V.REFUTED)}
        q = self.prove(self.party(unsat, "implementer"), self.party(unsat, "verifier"), criterion="C1x")
        self.assertEqual((q.agreement, q.satisfaction, q.failure.code), (True, CS.UNSATISFIED, F.CONTRACT_UNSATISFIED))
        q = self.prove(self.party(unsat, "implementer"), self.party(unsat, "verifier"), point=M.POST_MERGE)
        self.assertEqual((q.satisfaction, q.failure.code, q.failure.owner), (CS.UNSATISFIED, F.POST_MERGE_REGRESSION, Owner.INTEGRATION))
        with self.assertRaisesRegex(InvariantError, "^the parent is measured by StoryAdmission, never by a proof"):
            self.prove(self.party(sat, "implementer"), self.party(sat, "verifier"), point=M.PARENT, criterion="C1z")
        unr = {self.s1.id: Unrunnable("no interpreter")}
        q = self.prove(self.party(unr, "implementer"), self.party(unr, "verifier"), criterion="C1u")
        self.assertEqual((q.agreement, q.satisfaction), (True, None))
        self.assertEqual(q.failure.code, F.PROBE_UNRUNNABLE)
        self.assertNotIn("verdict", self.run.events[q.verified_seq].data)

    def test_a_disagreement_is_VERIFIER_DISAGREEMENT_and_a_mismatch_is_PROBE_MISMATCH(self):
        p = self.prove(self.party({self.s1.id: Executed(V.SATISFIED)}, "implementer"),
                       self.party({self.s1.id: Executed(V.REFUTED)}, "verifier"))
        self.assertEqual((p.agreement, p.satisfaction, p.failure.code, p.failure.owner), (False, None, F.VERIFIER_DISAGREEMENT, Owner.INTEGRATION))
        v = self.run.events[p.verified_seq]
        self.assertEqual((v.data["agreement"], "verdict" in v.data, tuple(v.source_seqs)), (False, False, (p.implementer_seq, p.verifier_seq)))
        n = len(self.run.events)
        other = pf.Party(self.scope, lambda on_range: Other({self.s1.id: Executed(V.SATISFIED)}, on_range), "verifier")
        q = self.prove(self.party({self.s1.id: Executed(V.SATISFIED)}, "implementer"), other, criterion="C1m")
        self.assertEqual((q.verified_seq, q.agreement, q.satisfaction, q.failure.code), (None, False, None, F.PROBE_MISMATCH))
        added = [e.type for e in self.run.events[n:] if e.type in ("probe/evaluated", "proof/verified")]
        self.assertEqual(added, ["probe/evaluated"] * 2)                     # two records, no proof
        low = self.party({self.s1.id: Executed(V.SATISFIED)}, "verifier", level=Enforcement.FULL)
        q = self.prove(self.party({self.s1.id: Executed(V.SATISFIED)}, "implementer"), low, criterion="C1e")
        self.assertEqual(q.failure.code, F.PROBE_MISMATCH)                    # a different enforcement is another instrument

    def test_each_party_runs_in_its_own_root_and_holds_its_range_under_its_own_name(self):
        sat = {self.s1.id: Executed(V.SATISFIED)}
        impl, ver = self.party(sat, "implementer"), self.party(sat, "verifier")
        self.assertEqual((impl.label, ver.label, impl.scope), ("implementer", "verifier", self.scope))
        self.prove(impl, ver)
        roots = [(e.data["criterion_id"], e.data["record"]["revision"]) for e in self.events("probe/evaluated", "S1")]
        self.assertEqual(roots, [("C1", SHA_B), ("C1", SHA_B)])
        names = [e.data["resource"] for e in self.events("story/resource-acquired", "S1")]
        self.assertEqual(names, [f"probe {self.s1.id} [C1/CANDIDATE implementer]", f"probe {self.s1.id} [C1/CANDIDATE verifier]"])
        released = [(e.data["resource"], e.data["status"]) for e in self.events("story/resource-released", "S1")]
        self.assertEqual(released, [(n, "RELEASED") for n in names])
        self.assertEqual(self.scope.held, ())
        seen = []

        class Looking(FakeProbe):
            def evaluate(s, spec, at, env):
                seen.append(at.root)
                return super().evaluate(spec, at, env)
        p = pf.prove(self.run, "S1", "C1", self.s1, R.INTRODUCE,
                     implementer=pf.Party(self.scope, lambda r: Looking(sat, r), "implementer"),
                     verifier=pf.Party(self.scope, lambda r: Looking(sat, r), "verifier"), candidate=SHA_C,
                     implementer_root=str(self.tmp / "IMPL"), verifier_root=str(self.tmp / "VER"), env=ENV, point=M.POST_MERGE)
        self.assertEqual(seen, [str(self.tmp / "IMPL"), str(self.tmp / "VER")])
        self.assertEqual(self.events("story/resource-acquired", "S1")[-1].data["resource"], f"probe {self.s1.id} [C1/POST_MERGE verifier]")
        self.assertEqual(p.satisfaction, CS.SATISFIED)

    def test_Ranged_names_a_range_within_the_attempt_and_releases_through_it(self):
        r = FakeRange("probe X")
        w = pf.Ranged(r, "probe X [C1/CANDIDATE implementer]")
        self.assertEqual((w.name, w.kind, r.released), ("probe X [C1/CANDIDATE implementer]", K.PROCESS_RANGE, 0))
        w.release()
        self.assertEqual(r.released, 1)

    def test_obligations_of_keeps_plan_order_for_the_story(self):
        self.assertEqual(pf.obligations_of(self.plan, "S1"), {"C1": (self.s1.id, R.INTRODUCE)})
        self.assertEqual(pf.obligations_of(self.plan, "S0"), {"C0": (self.s0.id, R.PRESERVE)})
        self.assertEqual(pf.obligations_of(self.plan, "S9"), {})


# --------------------------------------------------------------------------------------------- verified_payload

class VerifiedPayload(unittest.TestCase):
    A = {"result": {"status": "EXECUTED", "behavior_verdict": "SATISFIED"}}
    B = {"result": {"status": "EXECUTED", "behavior_verdict": "REFUTED"}}
    U = {"result": {"status": "UNRUNNABLE", "detail": "x"}}

    def payload(self, a, b):
        return f3.verified_payload(story_id="S1", criterion_id="C1", spec_id="PPS", semantic_hash="c" * 64,
                                   candidate=SHA_A, implementer=a, verifier=b)

    def test_agreement_is_result_equality_and_the_verdict_only_then(self):
        self.assertEqual(self.payload(self.A, self.A), {"story_id": "S1", "criterion_id": "C1", "spec_id": "PPS",
                                                         "semantic_hash": "c" * 64, "candidate": SHA_A,
                                                         "agreement": True, "verdict": "SATISFIED"})
        self.assertEqual(self.payload(self.A, self.B), {"story_id": "S1", "criterion_id": "C1", "spec_id": "PPS",
                                                         "semantic_hash": "c" * 64, "candidate": SHA_A, "agreement": False})
        u = self.payload(self.U, self.U)
        self.assertEqual((u["agreement"], "verdict" in u), (True, False))
        self.assertIs(self.payload(self.B, self.B)["agreement"], True)
        self.assertEqual(self.payload(self.B, self.B)["verdict"], "REFUTED")
        odd = self.payload({"result": "SATISFIED"}, {"result": "SATISFIED"})   # not a mapping: agreement, no verdict
        self.assertEqual((odd["agreement"], "verdict" in odd), (True, False))


# --------------------------------------------------------------------------------------------- quality

def unified(rel: str, old: str, new: str) -> str:
    a = f"a/{rel}" if old else "/dev/null"
    return "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), a, f"b/{rel}"))


class Quality(Journal):
    def tree(self, files):
        d = tempfile.mkdtemp(prefix="cand-", dir=self.tmp)
        for rel, text in files.items():
            pathlib.Path(d, rel).parent.mkdir(parents=True, exist_ok=True)
            pathlib.Path(d, rel).write_text(text, encoding="utf-8")
        return d

    def assess(self, files, patch, *, blocking=True, runner=te.UNITTEST, regressions=("tests/test_other.py",), story="S1"):
        self.activate(story, {"C1" if story == "S1" else "C0": "READY"})
        return ql.assess(self.run, story, self.tree(files), patch, te.DeveloperTests(story, ("tests/test_s1.py",)),
                         te.DeveloperTests(story, tuple(regressions)), te.Dependencies(frozenset(), frozenset({"app", "tests"})),
                         runner, ql.TestsPolicy(blocking), interpreter=sys.executable, timeout_s=60)

    BASE = {"app/__init__.py": "", "tests/__init__.py": "", "tests/test_other.py": e2e.TEST_OTHER}
    PATCH = unified("app/calc.py", e2e.CALC, e2e.CALC + e2e.ADD) + unified("tests/test_s1.py", "", e2e.TEST_ADD)

    def test_ADEQUATE_is_no_failure_whatever_the_policy(self):
        q = self.assess({**self.BASE, "app/calc.py": e2e.CALC + e2e.ADD, "tests/test_s1.py": e2e.TEST_ADD}, self.PATCH)
        self.assertEqual((q.assembly.outcome, q.failure), (AdequacyOutcome.ADEQUATE, None))
        e = self.run.events[q.seq]
        self.assertEqual(e.type, "tests/adequacy")
        self.assertEqual((e.data["outcome"], e.data["owner"], e.data["may_block"], e.data["developer_chargeable"],
                          e.data["vacuity"], e.data["relevance"], e.data["execution"]["outcome"], e.data["regressions"]["outcome"]),
                         ("ADEQUATE", None, False, False, "NON_VACUOUS", "RELEVANT", "PASSED", "PASSED"))

    def test_INADEQUATE_blocks_only_under_the_policy_and_is_the_developers(self):
        files = {**self.BASE, "app/calc.py": e2e.CALC + e2e.ADD, "tests/test_s1.py": e2e.TEST_ADD_WRONG}
        q = self.assess(files, self.PATCH, blocking=True)
        self.assertEqual((q.assembly.outcome, q.failure.code, q.failure.owner), (AdequacyOutcome.INADEQUATE, F.TESTS_INADEQUATE, Owner.DEVELOPER))
        e = self.run.events[q.seq]
        self.assertEqual((e.data["outcome"], e.data["owner"], e.data["may_block"], e.data["developer_chargeable"]),
                         ("INADEQUATE", "DEVELOPER", True, True))
        q2 = self.assess(files, self.PATCH, blocking=False, story="S0")
        self.assertEqual((q2.assembly.outcome, q2.failure), (AdequacyOutcome.INADEQUATE, None))
        self.assertEqual(self.run.events[q2.seq].data["story_id"], "S0")

    def test_UNRUNNABLE_is_TESTS_UNRUNNABLE_with_environment_provenance_and_no_outcome(self):
        absent = te.Runner("unittest", ("-m", "aisef2_no_such_runner", "{out}"), te._read_unittest)
        q = self.assess({**self.BASE, "app/calc.py": e2e.CALC + e2e.ADD, "tests/test_s1.py": e2e.TEST_ADD}, self.PATCH, runner=absent)
        self.assertEqual((q.assembly.outcome, q.failure.code, q.failure.owner), (None, F.TESTS_UNRUNNABLE, Owner.ENVIRONMENT))
        e = self.run.events[q.seq]
        self.assertEqual((e.data["outcome"], e.data["owner"], e.data["vacuity"], e.data["relevance"], e.data["execution"]["status"]),
                         (None, "ENVIRONMENT", None, None, "UNRUNNABLE"))

    def test_INCOMPLETE_is_recorded_and_never_a_failure(self):
        files = {**self.BASE, "app/calc.py": e2e.CALC + e2e.ADD, "tests/test_s1.py": e2e.TEST_ADD,
                 "tests/test_other.py": "import zzz_no_such_dependency\n" + e2e.TEST_OTHER}
        q = self.assess(files, self.PATCH, blocking=True)
        self.assertEqual((q.assembly.outcome, q.failure), (AdequacyOutcome.INCOMPLETE, None))
        e = self.run.events[q.seq]
        self.assertEqual((e.data["outcome"], e.data["owner"], e.data["regressions"]["selection"], e.data["regressions"]["owner_on_failure"]),
                         ("INCOMPLETE", None, "STORY_TESTS_NOT_COLLECTABLE", "INTEGRATION"))

    def test_payload_is_the_typed_assembly_field_for_field(self):
        a = assemble(RAN, Vacuity.NON_VACUOUS, Relevance.RELEVANT, RAN)
        self.assertEqual(ql.payload("S1", a), {"story_id": "S1", "execution": te.to_json(RAN), "vacuity": "NON_VACUOUS",
                                               "relevance": "RELEVANT", "regressions": te.to_json(RAN), "outcome": "ADEQUATE",
                                               "owner": None, "may_block": False, "developer_chargeable": False})
        b = assemble(UNRUNNABLE, None, None, RAN, chronology={"order": ["x"]})
        pb = ql.payload("S2", b)
        self.assertEqual((pb["story_id"], pb["outcome"], pb["owner"], pb["vacuity"], pb["relevance"], pb["chronology"]),
                         ("S2", None, "ENVIRONMENT", None, None, {"order": ["x"]}))
        c = assemble(FAILED, Vacuity.NON_VACUOUS, Relevance.RELEVANT, RAN)
        self.assertEqual((ql.payload("S1", c)["outcome"], ql.payload("S1", c)["owner"], ql.payload("S1", c)["may_block"],
                          ql.payload("S1", c)["developer_chargeable"]), ("INADEQUATE", "DEVELOPER", True, True))
        d = assemble(RAN, Vacuity.INDETERMINATE, Relevance.RELEVANT, INTEGRATION_GAP)
        self.assertEqual((ql.payload("S1", d)["outcome"], "chronology" in ql.payload("S1", d)), ("INCOMPLETE", False))


# --------------------------------------------------------------------------------------------- review

class Review(Journal):
    def setUp(self):
        super().setUp()
        self.activate()
        self.scope = ReadOnlyScope("S1", str(self.tmp / "ver"))

    def review(self, reviewer):
        return rv.review(self.run, "S1", self.scope, reviewer, ("C1",))

    def test_a_completed_review_is_a_REVIEW_request_its_result_and_a_row_per_finding(self):
        r = self.review(e2e.Rev([Finding("a", True, ("scanner:x", "human:y")), Finding("b", True, ()), Finding("c", False, ("h",))]))
        self.assertIsInstance(r.checks, tuple)
        req, res = self.run.events[r.request_seq], self.run.events[r.result_seq]
        self.assertEqual((req.type, req.data["budget_owner"], list(req.data["criteria"])), ("provider/request", "REVIEW", ["C1"]))
        self.assertEqual((res.type, res.data["outcome"], res.data["synthetic"], tuple(res.source_seqs)), ("provider/result", "COMPLETED", False, (req.seq,)))
        rows = [(self.run.events[s].data["check"], self.run.events[s].data["passed"], self.run.events[s].data["detail"]) for s in r.checks]
        self.assertEqual(rows, [("S1:review:a", False, "blocking, corroborated by scanner:x, human:y"),
                                ("S1:review:b", True, "advisory: a model review alone is never the sole blocking authority (D-002)"),
                                ("S1:review:c", True, "informational")])
        self.assertEqual((r.failure.code, r.failure.owner), (F.REVIEW_FINDING, Owner.REVIEW))
        self.assertEqual(self.run.state(P.BUDGETS)["review"], {"S1": {"requests": 1, "criteria": {"C1": 1}}})

    def test_no_finding_is_one_passing_row_and_an_advisory_finding_alone_never_blocks(self):
        r = self.review(e2e.Rev())
        self.assertEqual([(self.run.events[s].data["check"], self.run.events[s].data["passed"], self.run.events[s].data["detail"])
                          for s in r.checks], [("S1:review", True, "reviewed: no finding")])
        self.assertEqual((r.failure, r.checks), (None, r.checks[:1]))
        self.assertIsInstance(r.checks, tuple)
        r = self.review(e2e.Rev([Finding("b", True, ())]))
        self.assertEqual((r.failure, [self.run.events[s].data["passed"] for s in r.checks]), (None, [True]))

    def test_an_outage_a_capability_failure_and_a_failed_answer_are_typed(self):
        r = self.review(e2e.Rev(outage=True))
        self.assertEqual((r.failure.code, r.failure.owner, r.checks), (F.PROVIDER_UNAVAILABLE, Owner.PROVIDER, ()))
        self.assertEqual((self.run.events[r.result_seq].data["outcome"], self.run.events[r.result_seq].data["detail"]),
                         ("FAILED", "reviewer outage: reviewer 502"))
        r = self.review(e2e.Rev(unrunnable=True))
        self.assertEqual((r.failure.code, r.failure.owner), (F.CAPABILITY_UNRUNNABLE, Owner.ENVIRONMENT))
        self.assertEqual(self.run.events[r.result_seq].data["detail"], "reviewer cannot run: no reviewer binary on this host")
        r = self.review(e2e.Rev(fails=True))
        self.assertEqual((r.failure.code, self.run.events[r.result_seq].data["outcome"], r.checks), (F.PROVIDER_UNAVAILABLE, "FAILED", ()))
        self.assertEqual(self.run.state(P.BUDGETS)["review"]["S1"]["requests"], 3)


# --------------------------------------------------------------------------------------------- security

class Security(Journal):
    def setUp(self):
        super().setUp()
        self.activate()
        self.scope = ReadOnlyScope("S1", str(self.tmp / "ver"))
        self.script = str(self.tmp / "scan.py")
        pathlib.Path(self.script).write_text(e2e.SCAN_SCRIPT, encoding="utf-8")
        self.scratch = str(self.tmp / "scratch")
        pathlib.Path(self.scratch).mkdir()

    def scan(self, scanner, attempt=1, timeout_s=30):
        return sc.scan(self.run, "S1", self.scope, scanner, self.scratch, timeout_s=timeout_s, attempt=attempt)

    def test_a_scanner_that_ran_and_found_is_EXECUTED_with_a_row_per_finding(self):
        s = self.scan(e2e.Scan(self.script, [Finding("k", True, ("scanner:scan",)), Finding("i", False, ())]))
        inv, res = self.run.events[s.invoked_seq], self.run.events[s.result_seq]
        self.assertEqual((inv.type, inv.data["call_id"], inv.data["tool"]), ("tool/invoked", "scan-S1#1", "scan"))
        self.assertEqual((res.type, res.data["outcome"], res.data["synthetic"], tuple(res.source_seqs)), ("tool/result", "COMPLETED", False, (inv.seq,)))
        rows = [(self.run.events[c].data["check"], self.run.events[c].data["passed"], self.run.events[c].data["detail"]) for c in s.checks]
        self.assertEqual(rows, [("S1:security:k", False, "blocking"), ("S1:security:i", True, "informational")])
        self.assertEqual((s.failure.code, s.failure.owner), (F.SECURITY_FINDING, Owner.SECURITY))
        self.assertTrue(pathlib.Path(self.scratch, "scan-S1.report").exists())
        s2 = self.scan(e2e.Scan(self.script), attempt=2)
        self.assertEqual([(self.run.events[c].data["check"], self.run.events[c].data["passed"], self.run.events[c].data["detail"])
                          for c in s2.checks], [("S1:security", True, "scan ran: no finding")])
        self.assertEqual((s2.failure, self.run.events[s2.invoked_seq].data["call_id"]), (None, "scan-S1#2"))
        self.assertIsInstance(s.checks, tuple)
        self.assertIsInstance(s2.checks, tuple)

    def test_a_scanner_that_cannot_start_or_report_is_CAPABILITY_UNRUNNABLE(self):
        s = self.scan(e2e.Scan(self.script, interpreter="/nonexistent/aisef2-python"))
        self.assertEqual((s.invoked_seq, s.checks, s.failure.code, s.failure.owner), (None, (), F.CAPABILITY_UNRUNNABLE, Owner.ENVIRONMENT))
        closed = self.run.events[s.result_seq]
        self.assertEqual((closed.type, closed.data["outcome"], closed.data["synthetic"]), ("tool/result", "NOT_STARTED", True))
        n = len(self.run.events)

        class NoBinary:
            name = "scan"

            def argv(s_, scope, report):
                raise CapabilityUnrunnable("no scanner binary on this host")

            def read(s_, report, exit_code):
                raise AssertionError("never read")
        s = self.scan(NoBinary(), attempt=4)
        self.assertEqual((s.invoked_seq, s.result_seq, s.checks, s.failure.code), (None, None, (), F.CAPABILITY_UNRUNNABLE))
        self.assertEqual(len(self.run.events), n)                          # nothing was invoked, nothing journaled
        s = self.scan(e2e.Scan(self.script, silent=True), attempt=2)      # ran, reported nothing typed
        self.assertEqual((s.failure.code, s.checks, self.run.events[s.result_seq].data["outcome"]), (F.CAPABILITY_UNRUNNABLE, (), "COMPLETED"))

        class Hanging:
            name = "scan"

            def argv(s_, scope, report):
                return (sys.executable, "-c", "import time; time.sleep(30)")

            def read(s_, report, exit_code):
                raise AssertionError("never read: the tool did not complete")
        s = self.scan(Hanging(), attempt=3, timeout_s=0.5)
        self.assertEqual((s.failure.code, s.checks), (F.CAPABILITY_UNRUNNABLE, ()))
        self.assertNotIn(self.run.events[s.result_seq].data["outcome"], ("COMPLETED", "FAILED"))
        self.assertEqual(self.run.story("S1").held, ())


# --------------------------------------------------------------------------------------------- merge

class Fixed:
    def __init__(self, outcome):
        self.outcome, self.calls = outcome, []

    def base(self):
        return SHA_A

    def merge(self, candidate):
        self.calls.append(candidate)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome

    def revert(self, merged):
        self.calls.append(("revert", merged))


class MergeStage(Journal):
    def test_the_merge_outcome_is_typed_from_the_merger_or_flattened(self):
        m = mg.merge(self.run, "S1", Fixed(Merge(MergeOutcome.MERGED, SHA_C, ())), SHA_B)
        self.assertEqual((m.merge.revision, m.failure, self.run.events[m.check].data["passed"]), (SHA_C, None, True))
        self.assertEqual(self.run.events[m.check].data["detail"], f"merged at {SHA_C}")
        m = mg.merge(self.run, "S1", Fixed(Merge(MergeOutcome.CONFLICT, None, ("a.py", "b.py"))), SHA_B)
        self.assertEqual((m.merge.outcome, m.failure.code, m.failure.owner, m.failure.budget), (MergeOutcome.CONFLICT, F.MERGE_CONFLICT, Owner.INTEGRATION, None))
        self.assertEqual((self.run.events[m.check].data["passed"], self.run.events[m.check].data["detail"]), (False, "conflicts in ['a.py', 'b.py']"))
        m = mg.merge(self.run, "S1", Fixed(ValueError("boom")), SHA_B)
        self.assertEqual((m.merge, m.failure.code, self.run.events[m.check].data["detail"]), (None, F.UNKNOWN, "the merger raised ValueError"))
        self.assertEqual(self.checks(), [("S1:merge", True), ("S1:merge", False), ("S1:merge", False)])

    def test_affected_preserve_is_every_committed_other_storys_PRESERVE_obligation(self):
        self.assertEqual(mg.affected_preserve(self.plan, "S2", frozenset({"S0", "S1"})), {"C0": ("S0", self.s0.id)})
        self.assertEqual(mg.affected_preserve(self.plan, "S0", frozenset({"S0", "S1"})), {})      # not its own
        self.assertEqual(mg.affected_preserve(self.plan, "S2", frozenset({"S1"})), {})            # S0 not committed
        self.assertEqual(mg.affected_preserve(self.plan, "S1", frozenset({"S0", "S2"})), {"C0": ("S0", self.s0.id)})   # VERIFY is not PRESERVE

    def test_reprove_covers_the_story_then_the_affected_PRESERVE_and_stops_at_the_first_failure(self):
        scope = self.activate("S2", {"C0V": "READY"})
        good = {self.s0.id: Executed(V.SATISFIED), self.s1.id: Executed(V.SATISFIED)}
        proofs, checks = mg.reprove(self.run, "S2", self.plan, self.specs, merged=SHA_C,
                                    implementer=pf.Party(scope, factory(good), "implementer"),
                                    verifier=pf.Party(scope, factory(good), "verifier"), implementer_root=str(self.tmp / "impl"),
                                    verifier_root=str(self.tmp / "ver"), env=ENV, committed=frozenset({"S0", "S1"}))
        self.assertEqual([(p.criterion_id, p.satisfaction, p.failure) for p in proofs], [("C0V", CS.SATISFIED, None), ("C0", CS.SATISFIED, None)])
        self.assertEqual(self.checks("S2:"), [("S2:post-merge:C0V", True), ("S2:post-merge:C0", True)])
        self.assertEqual({self.run.events[c].data["detail"] for c in checks}, {"re-proved at the merged revision"})
        self.assertEqual({e.data["candidate"] for e in self.events("proof/verified", "S2")}, {SHA_C})
        scope1 = self.activate("S1")
        broken = {self.s0.id: Executed(V.SATISFIED), self.s1.id: Executed(V.REFUTED)}   # S1's own C1 regressed: stop there
        proofs, checks = mg.reprove(self.run, "S1", self.plan, self.specs, merged=SHA_C,
                                    implementer=pf.Party(scope1, factory(broken), "implementer"),
                                    verifier=pf.Party(scope1, factory(broken), "verifier"), implementer_root=str(self.tmp / "impl"),
                                    verifier_root=str(self.tmp / "ver"), env=ENV, committed=frozenset({"S0"}))
        self.assertEqual([(p.criterion_id, p.failure.code if p.failure else None) for p in proofs], [("C1", F.POST_MERGE_REGRESSION)])
        self.assertEqual(len(checks), 1)
        self.assertEqual(self.checks("S1:"), [("S1:post-merge:C1", False)])            # C0 is never reached
        self.assertEqual(self.run.events[checks[0]].data["detail"], "POST_MERGE_REGRESSION")
        self.assertEqual([e.data["criterion_id"] for e in self.events("proof/verified", "S1")], ["C1"])


# --------------------------------------------------------------------------------------------- runner helpers

class RunnerHelpers(Journal):
    def test_fail_carries_the_flattened_original_only_for_UNKNOWN(self):
        self.activate()
        from aisef2.control.owner import classify
        e = sr._fail(self.run, "S1", classify(F.MERGE_CONFLICT), "merge: MERGE_CONFLICT")
        self.assertEqual((e.type, e.data["code"], e.data["owner"], e.data["retryable"], "original" in e.data),
                         ("failure/observed", "MERGE_CONFLICT", "INTEGRATION", False, False))
        e = sr._fail(self.run, "S1", classify(F.UNKNOWN), "the merger raised ValueError")
        self.assertEqual((e.data["code"], e.data["original"], e.data["detail"]), ("UNKNOWN", "ValueError", "the merger raised ValueError"))
        e = sr._fail(self.run, "S1", classify(F.UNKNOWN), "")
        self.assertEqual((e.data["original"], e.data["detail"]), ("unknown", ""))      # an empty detail still names something

    def test_committed_reads_story_state_and_the_plan_is_frozen_once(self):
        self.assertEqual(sr._committed(self.run), frozenset())
        self.assertEqual(len(self.events("plan/frozen")), 1)
        sr._freeze_plan(self.run, self.plan)
        self.assertEqual(len(self.events("plan/frozen")), 1)
        frozen = self.events("plan/frozen")[0].data
        self.assertEqual((frozen["plan_id"], frozen["plan_hash"], dict(frozen["roles"])),
                         (self.plan.id, self.plan.plan_hash, {"C1": "INTRODUCE", "C0": "PRESERVE", "C0V": "VERIFY"}))
        self.activate()
        self.run.append(T.STORY_COMMIT, {"story_id": "S1", "revision": SHA_B})
        self.run.append(T.STORY_DISPOSE, {"story_id": "S1"})
        self.run.story("S1").dispose()
        self.run.append(T.STORY_END, {"story_id": "S1"})
        self.assertEqual(sr._committed(self.run), frozenset({"S1"}))
        self.activate("S0", {"C0": "READY"})
        from aisef2.control.owner import classify
        failed = sr._fail(self.run, "S0", classify(F.MERGE_CONFLICT), "merge")
        self.run.append(T.STORY_ROLLBACK, {"story_id": "S0"}, source_seqs=(failed.seq,))
        self.assertEqual(sr._committed(self.run), frozenset({"S1"}))

    def test_a_probe_factory_is_exactly_one(self):
        inputs = sr.StoryInputs(self.specs, {"p": factory({})}, ENV, te.DeveloperTests("S1", ("tests/test_s1.py",)),
                                te.DeveloperTests("S1", ("tests/test_other.py",)), te.Dependencies(frozenset(), frozenset()), te.UNITTEST)
        self.assertIsInstance(sr._probe(inputs, None), FakeProbe)
        for probes in ({}, {"p": factory({}), "q": factory({})}):
            with self.subTest(n=len(probes)), \
                    self.assertRaisesRegex(InvariantError, "^cycle 1 proves a story with exactly one probe factory$"):
                sr._probe(sr.StoryInputs(self.specs, probes, ENV, inputs.story_tests, inputs.regression_tests, inputs.deps, te.UNITTEST), None)

    def test_a_story_result_reads_its_last_attempt(self):
        a = sr.Attempt("S1", 1, "RETRY", F.CAPABILITY_UNRUNNABLE, None, (), (), 0)
        b = sr.Attempt("S1", 2, "COMMIT", None, SHA_C, (), (), 0)
        self.assertEqual((sr.StoryResult("S1", (a, b), {}).committed, sr.StoryResult("S1", (a, b), {}).revision), (True, SHA_C))
        self.assertEqual((sr.StoryResult("S1", (a,), {}).committed, sr.StoryResult("S1", (a,), {}).revision), (False, None))
        c = sr.Attempt("S1", 2, "ROLLBACK", F.MERGE_CONFLICT, None, (), (), 0)
        self.assertFalse(sr.StoryResult("S1", (b, c), {}).committed)

    def test_held_acquires_under_stage_names_and_releases_in_reverse(self):
        scope = self.activate()
        held = sr._Held(scope, "tests")
        r1, r2 = FakeRange("tests S1"), FakeRange("tests S1")
        held(r1)
        held(r2)
        self.assertEqual(scope.held, ("tests S1 [tests 1]", "tests S1 [tests 2]"))
        held.release()
        self.assertEqual((scope.held, r1.released, r2.released), ((), 1, 1))
        self.assertEqual([e.data["resource"] for e in self.events("story/resource-released", "S1")], ["tests S1 [tests 2]", "tests S1 [tests 1]"])
        held(FakeRange("x"))
        self.assertEqual(scope.held, ("x [tests 1]",))
        scope.release(scope._stack[-1][0])              # somebody released it first: release() skips it
        held.release()
        self.assertEqual(scope.held, ())

    def test_run_story_refuses_before_any_event_when_the_story_is_not_planned_or_the_seam_refuses(self):
        n = len(self.run.events)
        inputs = sr.StoryInputs(self.specs, {"p": factory({})}, ENV, te.DeveloperTests("S9", ("tests/test_s9.py",)),
                                te.DeveloperTests("S9", ("tests/test_other.py",)), te.Dependencies(frozenset(), frozenset()), te.UNITTEST)
        ad = sr.Adapters(e2e.Dev(), e2e.Rev(), e2e.Scan("x"), Fixed(None), None)
        with self.assertRaisesRegex(InvariantError, r"^story S9 has no obligation in plan PLAN-ORCH$"):
            sr.run_story(self.run, self.plan, "S9", inputs, ad, sr.Policy(e2e.LIMITS, ql.TestsPolicy(True)))
        legacy = sr.StoryInputs(self.specs, {"p": factory({})}, ENV, inputs.story_tests, inputs.regression_tests, inputs.deps,
                                te.UNITTEST, legacy={"C1": "CHANGE_REQUIRED"})
        with self.assertRaises(seam.SeamRefusal):
            sr.run_story(self.run, self.plan, "S1", legacy, ad, sr.Policy(e2e.LIMITS, ql.TestsPolicy(True)))
        self.assertEqual(len(self.run.events), n)
        self.assertEqual(sr.Policy(e2e.LIMITS, ql.TestsPolicy(True)).tool_timeout_s, 120.0)


if __name__ == "__main__":
    unittest.main()
