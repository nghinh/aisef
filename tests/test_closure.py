"""`aisef closure` — the project closure gate evaluator.

The gate exists because two of the four bullets of the old exit condition became
permanently unsatisfiable, so the tests here are less about "does it compute a
table" and more about the six things it must never do: launch an agent, run a
paid workload, modify a corpus, auto-approve, turn `UNCONFIGURED` into `PASS`,
or silently substitute a missing corpus. Each has a class below.

The rule every probe test asserts in one way or another is bug 154's: a
criterion is never satisfied by its own absence. Missing evidence is
`UNRUNNABLE`, which blocks.
"""

from __future__ import annotations

import ast
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.cli import main  # noqa: E402
from aisef.control import closure as CL  # noqa: E402
from aisef.control import conformance as CF  # noqa: E402
from aisef.control.approvals import GATE_ORDER, AUTO_APPROVER, ApprovalStore, Gate  # noqa: E402
from aisef.control.gate import Outcome  # noqa: E402
from aisef.control.state import StateStore, StoryStatus, StoryRecord, SprintState  # noqa: E402
from aisef.harness.observe import EvidenceStore  # noqa: E402


# ------------------------------------------------- stub probes for fixtures
# Referenced from fixture criteria files as `tests.test_closure:stub_*`, the
# same `module:callable` form the shipped criteria file uses.

def stub_passed(ctx):
    return CL.Probed(Outcome.PASSED, "stub says yes")


def stub_failed(ctx):
    return CL.Probed(Outcome.FAILED, "stub says no")


def stub_unconfigured(ctx):
    return CL.Probed(Outcome.UNCONFIGURED, "nobody configured it")


def stub_raises(ctx):
    raise RuntimeError("boom")


def stub_reads(ctx):
    """Reads a file, so the report records that path and its digest."""
    text = ctx.read("evidence.txt")
    return CL.Probed(Outcome.PASSED if text else Outcome.FAILED, "read the evidence")


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


def crit(cid: str, probe: str, **kw) -> dict:
    return {"id": cid, "statement": f"{cid} statement", "probe": probe, **kw}


def spec_of(*criteria: dict, **extra) -> dict:
    gate = {"id": "GT", "title": "test gate", "waiver_eligible": False,
            "criteria": list(criteria)}
    out = {"contract_version": "1", "contract_path": "docs/PROJECT-CLOSURE-GATE.md",
           "contract_sha256": "", "unconfigured_is_unrunnable": True,
           "severity_scale": {"blocking": ["P0", "P1"]}, "gates": [gate]}
    out.update(extra)
    return out


class Repo:
    """A throwaway framework checkout: contract, criteria file, one commit."""

    CONTRACT = "# closure contract\n"

    def __init__(self, spec: dict | None = None, *, pin: bool = True, commit: bool = True):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        (self.root / "docs").mkdir()
        self.write("docs/PROJECT-CLOSURE-GATE.md", self.CONTRACT)
        self.spec = spec if spec is not None else spec_of(crit("GT.1", "tests.test_closure:stub_passed"))
        if pin:
            self.spec["contract_sha256"] = hashlib.sha256(self.CONTRACT.encode()).hexdigest()
        self.write_json(CL.CRITERIA_PATH, self.spec)
        if commit:
            git(self.root, "init")
            git(self.root, "config", "user.name", "Test")
            git(self.root, "config", "user.email", "t@t.t")
            git(self.root, "add", ".")
            git(self.root, "commit", "-m", "init")

    def close(self):
        self._tmp.cleanup()

    @property
    def head(self) -> str:
        return git(self.root, "rev-parse", "HEAD").stdout.strip()

    def write(self, rel: str, text: str) -> Path:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        # newline="" — không để nền tảng dịch `\n` thành `\r\n`. Ghim hợp đồng
        # là digest trên **byte**, nên một lần dịch đầu dòng làm mọi phép thử
        # approval/pin đọc ra `contract is stale`. Đo ở CI Windows (run
        # 34913237817): 13 phép thử đỏ vì đúng một ký tự này.
        p.write_text(text, encoding="utf-8", newline="")
        return p

    def write_json(self, rel: str, obj) -> Path:
        return self.write(rel, json.dumps(obj, indent=2, ensure_ascii=False))

    def ctx(self, criterion: dict | None = None, *, corpus: str = "") -> CL.Ctx:
        return CL.Ctx(root=self.root, spec=self.spec, criterion=criterion or {}, corpus_arg=corpus)

    def evaluate(self, **kw) -> CL.Report:
        return CL.evaluate(self.root, spec=self.spec, **kw)


class Corpus:
    """A throwaway aisef project standing in for the G4 corpus."""

    def __init__(self, stories=("S-1",), *, planned=(), status=StoryStatus.DONE,
                 approve=True, review=True, candidate_merged=True):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.art = self.root / CL.ARTIFACT_ROOT
        self.art.mkdir()
        (self.root / "src.txt").write_text("code\n", encoding="utf-8")
        git(self.root, "init")
        git(self.root, "config", "user.name", "Test")
        git(self.root, "config", "user.email", "t@t.t")
        git(self.root, "add", ".")
        git(self.root, "commit", "-m", "init")
        self.head = git(self.root, "rev-parse", "HEAD").stdout.strip()

        all_ids = list(stories) + list(planned)
        (self.art / "stories.index.json").write_text(json.dumps({
            "stories": [{"id": sid, "epic_id": "EPIC-01"} for sid in all_ids],
            "epics": [{"id": "EPIC-01"}],
            "waves": {"1": all_ids},
        }), encoding="utf-8")
        StateStore(self.art).save(SprintState(stories={
            sid: StoryRecord(id=sid, epic_id="EPIC-01", status=status.value) for sid in stories}))

        cand = self.head if candidate_merged else "0" * 40
        store = EvidenceStore(self.art, candidate=cand)
        for sid in stories:
            store.tool_run(sid, "test", ok=True)
            if review:
                store.tool_run(sid, "review", ok=True)
                store.tool_run(sid, "security", ok=True)
        if approve:
            approvals = ApprovalStore(self.art)
            for gate in GATE_ORDER[:-1]:
                approvals.approve(gate, by="human")

    def close(self):
        self._tmp.cleanup()

    def pre_deploy(self, *, passed=True, scope="EPIC-01", waivers=None, checks=None):
        rep = {"passed": passed,
               "checks": checks or [{"name": "scope", "passed": True, "skipped": False}],
               "scope": ({"epic": scope} if scope else None), "waivers": waivers or {},
               "degraded_waiver": ""}
        (self.art / "pre-deploy-report.json").write_text(json.dumps(rep), encoding="utf-8")
        return rep

    def digests(self) -> dict[str, str]:
        """Every file under the corpus with its hash — how "did the evaluator
        touch the corpus" is answered."""
        out = {}
        for p in sorted(self.root.rglob("*")):
            if p.is_file() and ".git" not in p.parts:
                out[str(p.relative_to(self.root))] = hashlib.sha256(p.read_bytes()).hexdigest()
        return out


# ------------------------------------------------------------ the vocabulary


class TestVocabulary(unittest.TestCase):
    def test_reuses_the_story_gate_outcome(self):
        """One outcome type for all gates — not a second enum that drifts."""
        from aisef.control import outcome as O

        self.assertIs(CL.Outcome, Outcome)
        self.assertIs(CL.Outcome, O.Outcome)

    def test_hard_kinds_are_real_check_kinds(self):
        from aisef.control.outcome import CHECK_KINDS

        self.assertTrue(set(CL.HARD_KINDS) <= set(CHECK_KINDS))


class TestClosureTightening(unittest.TestCase):
    """`UNCONFIGURED.blocks` is False for story gates and that is right there.
    At closure it would let an unconfigured check read as absolution."""

    def test_unconfigured_is_promoted_to_unrunnable_and_blocks(self):
        repo = Repo(spec_of(crit("GT.1", "tests.test_closure:stub_unconfigured")))
        self.addCleanup(repo.close)
        r = repo.evaluate().results[0]
        self.assertIs(r.outcome, Outcome.UNRUNNABLE)
        self.assertTrue(r.outcome.blocks)
        self.assertIn("UNCONFIGURED", r.detail)
        self.assertIn("nobody configured it", r.detail)

    def test_story_gate_semantics_are_unchanged(self):
        self.assertFalse(Outcome.UNCONFIGURED.blocks)

    def test_shipped_criteria_file_asks_for_the_tightening(self):
        spec = CL.load_spec(ROOT)
        self.assertTrue(spec.get("unconfigured_is_unrunnable"))

    def test_a_probe_that_raises_blocks(self):
        repo = Repo(spec_of(crit("GT.1", "tests.test_closure:stub_raises")))
        self.addCleanup(repo.close)
        r = repo.evaluate().results[0]
        self.assertIs(r.outcome, Outcome.UNRUNNABLE)
        self.assertIn("RuntimeError", r.detail)

    def test_an_unresolvable_probe_blocks(self):
        repo = Repo(spec_of(crit("GT.1", "tests.test_closure:no_such_probe")))
        self.addCleanup(repo.close)
        r = repo.evaluate().results[0]
        self.assertIs(r.outcome, Outcome.UNRUNNABLE)
        self.assertIn("not resolvable", r.detail)


# --------------------------------------------------- no pass by its own absence


class TestNoCriterionPassesOnAbsence(unittest.TestCase):
    """Bug 154: the release gate's one acceptance assertion skipped when an env
    var was unset and the log read `OK (skipped=1)` — green, on the assertion
    that had never run. Every one of the 26 probes, given a repository with no
    evidence at all, must block."""

    def test_every_probe_blocks_in_an_empty_repository(self):
        shipped = CL.load_spec(ROOT)
        repo = Repo(shipped, pin=False)
        self.addCleanup(repo.close)
        report = repo.evaluate()
        self.assertEqual(len(report.results), 27)
        for r in report.results:
            with self.subTest(criterion=r.id):
                self.assertTrue(r.outcome.blocks,
                                f"{r.id} did not block with no evidence: {r.outcome} {r.detail}")
                self.assertTrue(r.detail, f"{r.id} blocked without saying why")


class TestShippedCriteriaFile(unittest.TestCase):
    def setUp(self):
        self.spec = CL.load_spec(ROOT)
        self.criteria = [c for g in self.spec["gates"] for c in g["criteria"]]

    def test_six_gates_twentyseven_criteria_unique_ids(self):
        self.assertEqual(len(self.spec["gates"]), 6)
        self.assertEqual(len(self.criteria), 27)
        ids = [c["id"] for c in self.criteria]
        self.assertEqual(len(set(ids)), len(ids))

    def test_every_named_probe_exists_and_is_callable(self):
        for c in self.criteria:
            with self.subTest(criterion=c["id"]):
                fn = CL._ref(c["probe"])
                self.assertTrue(callable(fn))
                self.assertTrue(c["probe"].startswith("aisef.control.closure:"))

    def test_exactly_five_criteria_are_waiver_eligible(self):
        self.assertEqual(CL.eligible_ids(self.spec), ["G2.3", "G2.4b", "G4.6", "G5.3", "G6.3"])


# ------------------------------------------------------------------- G1 probes


class TestG1(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.close)
        git(self.repo.root, "tag", "v9.9.9")
        self.sha = self.repo.head

    def release(self, **parts):
        self.repo.write_json(f"{CL.EVIDENCE_DIR}/release.json", parts)

    def test_missing_record_is_unrunnable_for_all_four(self):
        for probe in (CL.probe_ci_green, CL.probe_package_checks,
                      CL.probe_pypi_install, CL.probe_packaged_data):
            with self.subTest(probe=probe.__name__):
                p = probe(self.repo.ctx())
                self.assertIs(p.outcome, Outcome.UNRUNNABLE)
                self.assertIn("closure-evidence/release.json", p.detail)

    def test_ci_green_binds_to_the_tag_commit(self):
        self.release(ci={"workflow": "tests.yml", "conclusion": "success",
                         "tag": "v9.9.9", "commit": self.sha})
        self.assertIs(CL.probe_ci_green(self.repo.ctx()).outcome, Outcome.PASSED)

    def test_ci_green_on_another_commit_fails(self):
        self.release(ci={"workflow": "tests.yml", "conclusion": "success",
                         "tag": "v9.9.9", "commit": "0" * 40})
        p = CL.probe_ci_green(self.repo.ctx())
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("points at", p.detail)

    def test_ci_red_fails(self):
        self.release(ci={"workflow": "tests.yml", "conclusion": "failure",
                         "tag": "v9.9.9", "commit": self.sha})
        self.assertIs(CL.probe_ci_green(self.repo.ctx()).outcome, Outcome.FAILED)

    def test_unknown_tag_is_unrunnable(self):
        self.release(ci={"workflow": "tests.yml", "conclusion": "success",
                         "tag": "v0.0.0-nope", "commit": self.sha})
        self.assertIs(CL.probe_ci_green(self.repo.ctx()).outcome, Outcome.UNRUNNABLE)

    def test_package_checks_read_both_exits(self):
        self.release(package={"build_exit": 0, "twine_exit": 0, "commit": self.sha})
        self.assertIs(CL.probe_package_checks(self.repo.ctx()).outcome, Outcome.PASSED)
        self.release(package={"build_exit": 0, "twine_exit": 1, "commit": self.sha})
        self.assertIs(CL.probe_package_checks(self.repo.ctx()).outcome, Outcome.FAILED)

    def test_package_checks_recorded_at_another_commit_are_unrunnable(self):
        self.release(package={"build_exit": 0, "twine_exit": 0, "commit": "0" * 40})
        p = CL.probe_package_checks(self.repo.ctx())
        self.assertIs(p.outcome, Outcome.UNRUNNABLE)
        self.assertIn("HEAD is", p.detail)

    def test_package_checks_missing_one_exit_is_unrunnable(self):
        self.release(package={"build_exit": 0, "commit": self.sha})
        self.assertIs(CL.probe_package_checks(self.repo.ctx()).outcome, Outcome.UNRUNNABLE)

    def test_pypi_install_must_report_this_version(self):
        self.repo.write("pyproject.toml", '[project]\nname = "aisef"\nversion = "1.6.0"\n')
        self.release(pypi_install={"version_reported": "1.6.0"})
        self.assertIs(CL.probe_pypi_install(self.repo.ctx()).outcome, Outcome.PASSED)
        self.release(pypi_install={"version_reported": "1.5.0"})
        self.assertIs(CL.probe_pypi_install(self.repo.ctx()).outcome, Outcome.FAILED)

    def test_packaged_data_needs_every_name_non_empty(self):
        self.release(packaged_data={n: 3 for n in CL.PACKAGED_DATA})
        self.assertIs(CL.probe_packaged_data(self.repo.ctx()).outcome, Outcome.PASSED)
        self.release(packaged_data={**{n: 3 for n in CL.PACKAGED_DATA}, CL.PACKAGED_DATA[0]: 0})
        self.assertIs(CL.probe_packaged_data(self.repo.ctx()).outcome, Outcome.FAILED)
        self.release(packaged_data={n: 3 for n in CL.PACKAGED_DATA[1:]})
        p = CL.probe_packaged_data(self.repo.ctx())
        self.assertIs(p.outcome, Outcome.UNRUNNABLE)
        self.assertIn(CL.PACKAGED_DATA[0], p.detail)


# ------------------------------------------------------------------- G2 probes


class TestDocDungHinhDangArtifactThat(unittest.TestCase):
    """Bộ chấm phải đọc **hình dạng artifact thật sự có trên đĩa**.

    Hai agent định nghĩa hình dạng độc lập nhau trong cùng một đợt: bên sinh
    (`reviewer_qual.judge_only_audit`) lồng bốn thuộc tính dưới `properties` và
    các con số dưới `measured`; bên đọc (probe) chờ khoá phẳng. Kết quả là một
    tiêu chí **đang đạt** bị chấm `UNRUNNABLE` — false FAIL, đúng thứ Phase B
    gọi là lỗi cổng đóng dự án phải sửa trước khi đi tiếp.
    """

    def test_artifact_that_tren_dia_doc_duoc(self):
        from aisef.control.closure import Ctx, probe_judge_only_semantics
        got = probe_judge_only_semantics(Ctx(root=ROOT, spec={}))
        self.assertEqual(got.outcome, Outcome.PASSED,
                         f"artifact có thật, bốn thuộc tính đều holds, mà chấm ra {got.outcome}: {got.detail}")
        self.assertIn("%", got.detail, "tỉ lệ judge-alone phải in ra, không được ẩn sau một PASS")


class TestG2Suite(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.close)

    def suite(self, **rec):
        self.repo.write_json(f"{CL.EVIDENCE_DIR}/suite.json",
                             {"tree": "main", "commit": self.repo.head, **rec})

    def test_a_worktree_is_unrunnable_not_a_number(self):
        """A worktree skips ~61 more tests, so its count is not comparable."""
        self.suite(passed=2682, skipped=19, failed=0)
        wt = self.repo.root / "wt"
        git(self.repo.root, "worktree", "add", str(wt))
        ctx = CL.Ctx(root=wt, spec=self.repo.spec, criterion={})
        p = CL.probe_suite_green(ctx)
        self.assertIs(p.outcome, Outcome.UNRUNNABLE)
        self.assertIn("not the main checkout", p.detail)

    def test_main_checkout_green_passes_and_records_skips(self):
        self.suite(passed=2682, skipped=19, failed=0)
        p = CL.probe_suite_green(self.repo.ctx())
        self.assertIs(p.outcome, Outcome.PASSED)
        self.assertIn("19 skipped", p.detail)
        self.assertIn("tree=main", p.detail)

    def test_red_suite_fails(self):
        self.suite(passed=2600, skipped=19, failed=3)
        self.assertIs(CL.probe_suite_green(self.repo.ctx()).outcome, Outcome.FAILED)

    def test_run_recorded_in_a_worktree_is_unrunnable(self):
        self.suite(passed=2608, skipped=80, failed=0, tree="worktree")
        p = CL.probe_suite_green(self.repo.ctx())
        self.assertIs(p.outcome, Outcome.UNRUNNABLE)
        self.assertIn("worktree", p.detail)

    def test_run_from_another_commit_is_unrunnable(self):
        self.suite(passed=2682, skipped=19, failed=0, commit="0" * 40)
        self.assertIs(CL.probe_suite_green(self.repo.ctx()).outcome, Outcome.UNRUNNABLE)


class TestG2Lint(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.close)

    def test_clean_passes_dirty_fails(self):
        self.repo.write_json(f"{CL.EVIDENCE_DIR}/lint.json",
                             {"tool": "ruff", "exit": 0, "commit": self.repo.head})
        self.assertIs(CL.probe_lint_clean(self.repo.ctx()).outcome, Outcome.PASSED)
        self.repo.write_json(f"{CL.EVIDENCE_DIR}/lint.json",
                             {"tool": "ruff", "exit": 1, "commit": self.repo.head})
        self.assertIs(CL.probe_lint_clean(self.repo.ctx()).outcome, Outcome.FAILED)


class TestG2Register(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.close)

    def register(self, *defects):
        self.repo.write_json("docs/DEFECT-REGISTER.json", {"defects": list(defects)})

    def test_missing_register_is_unrunnable(self):
        p = CL.probe_defect_register(self.repo.ctx())
        self.assertIs(p.outcome, Outcome.UNRUNNABLE)
        self.assertIn("DEFECT-REGISTER.json", p.detail)

    def test_empty_register_is_a_real_pass(self):
        self.register()
        self.assertIs(CL.probe_defect_register(self.repo.ctx()).outcome, Outcome.PASSED)

    def test_open_p1_fails_and_is_named(self):
        self.register({"id": "D-1", "severity": "P1", "status": "OPEN"},
                      {"id": "D-2", "severity": "P2", "status": "OPEN"})
        p = CL.probe_defect_register(self.repo.ctx())
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("D-1", p.detail)
        self.assertNotIn("D-2", p.detail)

    def test_closed_p0_passes(self):
        self.register({"id": "D-1", "severity": "P0", "status": "CLOSED"})
        self.assertIs(CL.probe_defect_register(self.repo.ctx()).outcome, Outcome.PASSED)

    def test_entry_without_status_is_unrunnable_not_closed(self):
        self.register({"id": "D-1", "severity": "P0"})
        p = CL.probe_defect_register(self.repo.ctx())
        self.assertIs(p.outcome, Outcome.UNRUNNABLE)
        self.assertIn("D-1", p.detail)

    def test_blocking_severities_come_from_the_criteria_file(self):
        self.repo.spec["severity_scale"] = {"blocking": ["P0"]}
        self.register({"id": "D-1", "severity": "P1", "status": "OPEN"})
        self.assertIs(CL.probe_defect_register(self.repo.ctx()).outcome, Outcome.PASSED)

    def test_unclassified_register_cannot_answer_g2_4a(self):
        self.register({"id": "D-1", "severity": "P2", "status": "CLOSED"})
        p = CL.probe_deterministic_false_pass(self.repo.ctx())
        self.assertIs(p.outcome, Outcome.UNRUNNABLE)
        self.assertIn("false_pass", p.detail)

    def test_open_false_pass_in_a_deterministic_check_fails(self):
        self.register({"id": "D-1", "severity": "P0", "status": "OPEN",
                       "false_pass": True, "check_kind": "deterministic"})
        p = CL.probe_deterministic_false_pass(self.repo.ctx())
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("D-1", p.detail)

    def test_a_judge_false_pass_is_a_published_property_not_a_g2_4a_defect(self):
        self.register({"id": "D-1", "severity": "P1", "status": "OPEN",
                       "false_pass": True, "check_kind": "model-judge"})
        self.assertIs(CL.probe_deterministic_false_pass(self.repo.ctx()).outcome, Outcome.PASSED)

    def test_unknown_check_kind_is_unrunnable(self):
        self.register({"id": "D-1", "severity": "P1", "status": "OPEN",
                       "false_pass": True, "check_kind": "vibes"})
        p = CL.probe_deterministic_false_pass(self.repo.ctx())
        self.assertIs(p.outcome, Outcome.UNRUNNABLE)
        self.assertIn("vibes", p.detail)

    def test_kind_is_derived_from_the_named_gate_check(self):
        """Một mục nêu `check` là tên một mục cổng thật thì loại của nó đã được
        khung tự phân — `gate.CHECK_KIND` là nguồn duy nhất. Bắt người ghi tay
        thêm `check_kind` mở ra đúng một đường lách: ghi `model-judge` cho một
        mục **cấu trúc** là cách hợp lệ hoá một PASS giả mà G2.4a hỏi về."""
        self.register({"id": "D-1", "severity": "P1", "status": "OPEN",
                       "false_pass": True, "check": "criteria have tests"})
        p = CL.probe_deterministic_false_pass(self.repo.ctx())
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("D-1", p.detail)

    def test_a_hand_written_kind_cannot_contradict_the_framework(self):
        """`criteria have tests` là `structural` theo khung; khai `model-judge`
        không được phép biến nó thành không-chặn."""
        self.register({"id": "D-1", "severity": "P1", "status": "OPEN",
                       "false_pass": True, "check": "criteria have tests",
                       "check_kind": "model-judge"})
        p = CL.probe_deterministic_false_pass(self.repo.ctx())
        self.assertIs(p.outcome, Outcome.UNRUNNABLE)
        self.assertIn("criteria have tests", p.detail)

    def test_a_defect_outside_any_gate_check_still_needs_a_hand_written_kind(self):
        """Không phải khiếm khuyết nào cũng nằm ở một mục cổng — khi `check`
        không có trong bản đồ, lời khai là thứ duy nhất còn lại."""
        self.register({"id": "D-1", "severity": "P1", "status": "OPEN",
                       "false_pass": True, "check": "pre-deploy readiness",
                       "check_kind": "deterministic"})
        p = CL.probe_deterministic_false_pass(self.repo.ctx())
        self.assertIs(p.outcome, Outcome.FAILED)


class TestG2JudgeOnly(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.close)

    def audit(self, holds=True, **extra):
        rec = {p: {"holds": holds, "evidence": "x"} for p in CL.JUDGE_PROPERTIES}
        rec.update({"judge_alone_blocks": 21, "blocks_total": 57})
        rec.update(extra)
        self.repo.write_json(f"{CL.EVIDENCE_DIR}/judge-only-audit.json", rec)

    def test_missing_audit_names_the_four_properties(self):
        p = CL.probe_judge_only_semantics(self.repo.ctx())
        self.assertIs(p.outcome, Outcome.UNRUNNABLE)
        for name in CL.JUDGE_PROPERTIES:
            self.assertIn(name, p.detail)

    def test_all_four_holding_passes_and_publishes_the_rate(self):
        self.audit()
        p = CL.probe_judge_only_semantics(self.repo.ctx())
        self.assertIs(p.outcome, Outcome.PASSED)
        self.assertIn("36.8%", p.detail)

    def test_one_property_not_holding_fails(self):
        self.audit()
        self.repo.write_json(f"{CL.EVIDENCE_DIR}/judge-only-audit.json", {
            **json.loads((self.repo.root / CL.EVIDENCE_DIR / "judge-only-audit.json").read_text(encoding="utf-8")),
            "G2.4b-iii": {"holds": False, "evidence": "no override path"}})
        p = CL.probe_judge_only_semantics(self.repo.ctx())
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("G2.4b-iii", p.detail)

    def test_audit_without_the_counts_is_unrunnable(self):
        rec = {p: {"holds": True} for p in CL.JUDGE_PROPERTIES}
        self.repo.write_json(f"{CL.EVIDENCE_DIR}/judge-only-audit.json", rec)
        p = CL.probe_judge_only_semantics(self.repo.ctx())
        self.assertIs(p.outcome, Outcome.UNRUNNABLE)
        self.assertIn("judge_alone_blocks", p.detail)


# ------------------------------------------------------------------- G3 probe


class TestG3Conformance(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.close)

    def table(self, *, days_old: int = 1, passing: bool = True):
        runs = []
        for client in CF.RELEASE_CLIENTS:
            run = CF.ClientRun(client=client, version="1.0", at="2026-09-08T00:00:00+00:00")
            for i, (pid, *_rest) in enumerate(CF.PROBES):
                run.results.append(CF.ProbeResult(pid, passing or i != 0))
            runs.append(run)
        generated = (date.today() - timedelta(days=days_old)).isoformat()
        self.repo.write(CF.REPORT_PATH, CF.Report(runs=runs, generated=generated).to_markdown())

    def criterion(self) -> dict:
        return {"freshness": {"kind": "age_days",
                              "max_from": "aisef.control.conformance:MAX_AGE_DAYS"}}

    def test_missing_table_is_unrunnable(self):
        p = CL.probe_conformance(self.repo.ctx(self.criterion()))
        self.assertIs(p.outcome, Outcome.UNRUNNABLE)

    def test_fresh_and_passing_passes_and_prints_days_left(self):
        self.table(days_old=6)
        p = CL.probe_conformance(self.repo.ctx(self.criterion()))
        self.assertIs(p.outcome, Outcome.PASSED)
        self.assertIn("8d left of 14d", p.detail)
        self.assertIn("release policy reads", p.detail)

    def test_a_lapsed_window_fails_with_the_age(self):
        self.table(days_old=CF.MAX_AGE_DAYS + 1)
        p = CL.probe_conformance(self.repo.ctx(self.criterion()))
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("days old", p.detail)

    def test_a_failing_cell_fails(self):
        self.table(passing=False)
        self.assertIs(CL.probe_conformance(self.repo.ctx(self.criterion())).outcome, Outcome.FAILED)

    def test_max_age_is_read_from_the_module_not_a_literal(self):
        self.assertIn("aisef.control.conformance:MAX_AGE_DAYS",
                      json.dumps(CL.load_spec(ROOT)))


# ------------------------------------------------------------------- G4 probes


class TestG4Corpus(unittest.TestCase):
    def setUp(self):
        self.repo = Repo(spec_of(crit("G4.1", "aisef.control.closure:probe_corpus_present")))
        self.addCleanup(self.repo.close)
        # `corpus` belongs on the gate, as in the shipped criteria file.
        self.repo.spec["gates"][0]["corpus"] = {"primary": "marks-cli", "fallback": "todo-oc",
                                               "fallback_requires_owner_approval": True}
        self.corpus = Corpus()
        self.addCleanup(self.corpus.close)

    def ctx(self, criterion=None, *, corpus=None):
        return self.repo.ctx(criterion or {}, corpus=str(corpus if corpus is not None else self.corpus.root))

    def test_resolvable_corpus_passes_and_records_its_head(self):
        p = CL.probe_corpus_present(self.ctx())
        self.assertIs(p.outcome, Outcome.PASSED)
        self.assertEqual(p.digest, self.corpus.head)

    def test_a_missing_corpus_is_unrunnable_and_the_fallback_is_not_substituted(self):
        """Owner ruling 2: the fallback is a named R1 substitution the owner
        approves, never something the evaluator reaches for."""
        gone = self.corpus.root / "nope"
        p = CL.probe_corpus_present(self.ctx(corpus=gone))
        self.assertIs(p.outcome, Outcome.UNRUNNABLE)
        self.assertIn("marks-cli", p.detail)
        self.assertIn("NOT substituted", p.detail)

    def test_every_g4_probe_is_unrunnable_without_the_corpus(self):
        gone = self.corpus.root / "nope"
        for probe in (CL.probe_corpus_present, CL.probe_upstream_gates, CL.probe_stories_done,
                      CL.probe_review_and_security, CL.probe_evidence_at_candidate,
                      CL.probe_pre_deploy, CL.probe_pre_deploy_approved):
            with self.subTest(probe=probe.__name__):
                p = probe(self.ctx(corpus=gone))
                self.assertIs(p.outcome, Outcome.UNRUNNABLE)

    def test_upstream_gates_all_approved_passes(self):
        self.assertIs(CL.probe_upstream_gates(self.ctx()).outcome, Outcome.PASSED)

    def test_one_unapproved_upstream_gate_fails_and_is_named(self):
        (self.corpus.art / "approvals" / "readiness.json").unlink()
        p = CL.probe_upstream_gates(self.ctx())
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("readiness", p.detail)

    def test_all_stories_done_passes(self):
        self.assertIs(CL.probe_stories_done(self.ctx()).outcome, Outcome.PASSED)

    def test_a_planned_story_that_never_ran_is_not_done(self):
        corpus = Corpus(stories=("S-1",), planned=("S-2",))
        self.addCleanup(corpus.close)
        p = CL.probe_stories_done(self.ctx(corpus=corpus.root))
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("never run: S-2", p.detail)

    def test_verified_but_unmerged_is_not_done(self):
        corpus = Corpus(status=StoryStatus.VERIFIED)
        self.addCleanup(corpus.close)
        p = CL.probe_stories_done(self.ctx(corpus=corpus.root))
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("not merged", p.detail)

    def test_review_and_security_recorded_for_every_story_passes(self):
        self.assertIs(CL.probe_review_and_security(self.ctx()).outcome, Outcome.PASSED)

    def test_a_story_without_security_fails(self):
        corpus = Corpus(review=False)
        self.addCleanup(corpus.close)
        p = CL.probe_review_and_security(self.ctx(corpus=corpus.root))
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("S-1:review", p.detail)

    def test_evidence_at_the_merged_candidate_passes(self):
        self.assertIs(CL.probe_evidence_at_candidate(self.ctx()).outcome, Outcome.PASSED)

    def test_evidence_at_a_candidate_outside_the_history_fails(self):
        corpus = Corpus(candidate_merged=False)
        self.addCleanup(corpus.close)
        p = CL.probe_evidence_at_candidate(self.ctx(corpus=corpus.root))
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("not in the corpus history", p.detail)

    def test_a_check_left_at_an_older_build_fails(self):
        EvidenceStore(self.corpus.art, candidate="a" * 40).tool_run("S-1", "lint", ok=True)
        EvidenceStore(self.corpus.art, candidate=self.corpus.head).tool_run("S-1", "test", ok=True)
        p = CL.probe_evidence_at_candidate(self.ctx())
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("aaaaaaa", p.detail)


class TestG4PreDeploy(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.close)
        self.corpus = Corpus()
        self.addCleanup(self.corpus.close)

    def ctx(self):
        return self.repo.ctx(corpus=str(self.corpus.root))

    def test_no_report_is_unrunnable(self):
        p = CL.probe_pre_deploy(self.ctx())
        self.assertIs(p.outcome, Outcome.UNRUNNABLE)
        self.assertIn("pre-deploy-report.json", p.detail)

    def test_passing_report_with_scope_passes(self):
        self.corpus.pre_deploy()
        self.assertIs(CL.probe_pre_deploy(self.ctx()).outcome, Outcome.PASSED)

    def test_report_without_scope_fails(self):
        self.corpus.pre_deploy(scope="")
        p = CL.probe_pre_deploy(self.ctx())
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("scope", p.detail)

    def test_a_waiver_without_a_reason_is_not_evidence(self):
        self.corpus.pre_deploy(waivers={"isolation": ""})
        p = CL.probe_pre_deploy(self.ctx())
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("without a reason", p.detail)

    def test_a_waiver_with_a_reason_is_accepted(self):
        self.corpus.pre_deploy(waivers={"isolation": "no docker on this machine"})
        self.assertIs(CL.probe_pre_deploy(self.ctx()).outcome, Outcome.PASSED)

    def test_red_checks_are_named(self):
        self.corpus.pre_deploy(passed=False, checks=[{"name": "runbook", "passed": False}])
        p = CL.probe_pre_deploy(self.ctx())
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("runbook", p.detail)

    def test_unapproved_gate_fails_and_closure_never_signs_it(self):
        self.corpus.pre_deploy()
        p = CL.probe_pre_deploy_approved(self.ctx())
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("never signs", p.detail)

    def test_auto_approval_is_not_a_human_signature(self):
        self.corpus.pre_deploy()
        ApprovalStore(self.corpus.art).auto_approve(Gate.PRE_DEPLOY)
        p = CL.probe_pre_deploy_approved(self.ctx())
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn(AUTO_APPROVER, p.detail)

    def test_human_approval_on_that_report_passes(self):
        self.corpus.pre_deploy()
        ApprovalStore(self.corpus.art).approve(Gate.PRE_DEPLOY, by="owner")
        self.assertIs(CL.probe_pre_deploy_approved(self.ctx()).outcome, Outcome.PASSED)

    def test_approval_of_another_report_is_stale_and_fails(self):
        self.corpus.pre_deploy()
        ApprovalStore(self.corpus.art).approve(Gate.PRE_DEPLOY, by="owner")
        self.corpus.pre_deploy(scope="EPIC-02")
        p = CL.probe_pre_deploy_approved(self.ctx())
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("stale", p.detail)


# ------------------------------------------------------------------- G5 probes


class TestG5(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.close)

    #: Đúng mốc và luật mà `docs/BENCH-PREREGISTRATION-C2.md` §1.1 khai, ở dạng
    #: máy đọc được — probe lấy mốc **từ dữ liệu**, nên chỉ có một công thức.
    REGION = {"begin": r"<!--\s*PREREG-FROZEN:BEGIN\s*-->",
              "end": r"<!--\s*PREREG-FROZEN:END\s*-->",
              "exactly_one_pair": True,
              "also_in": "docs/handoff/bench.md"}

    def prereg(self, than="ngưỡng ≥ 3, dải ±0,08", *, ngoai="", tep=None):
        """Một tiền đăng ký có mốc thật. `ngoai` là phụ lục **ngoài** vùng ghim."""
        text = ("# prereg\n\n"
                "<!-- PREREG-FROZEN:BEGIN -->\n" + than + "\n<!-- PREREG-FROZEN:END -->\n"
                + ngoai)
        return self.repo.write(tep or "docs/BENCH-PREREGISTRATION-C2.md", text)

    def crit_prereg(self, **kw):
        c = {"evidence": "docs/BENCH-PREREGISTRATION-C2.md",
             "prereg_frozen_region": dict(self.REGION)}
        c.update(kw)
        return c

    def test_unpinned_prereg_is_unrunnable_even_when_it_exists(self):
        self.prereg()
        p = CL.probe_prereg_digest(self.repo.ctx(self.crit_prereg()))
        self.assertIs(p.outcome, Outcome.UNRUNNABLE)
        self.assertIn("not digest-pinned", p.detail)

    def test_pinned_prereg_passes_and_an_edit_inside_the_region_fails(self):
        path = self.prereg()
        self.prereg(tep=self.REGION["also_in"])
        c = self.crit_prereg(prereg_sha256=CL.frozen_region_digest(path, self.REGION))
        self.assertIs(CL.probe_prereg_digest(self.repo.ctx(c)).outcome, Outcome.PASSED)
        self.prereg("ngưỡng ≥ 2, dải ±0,08")          # một byte trong vùng ghim
        p = CL.probe_prereg_digest(self.repo.ctx(c))
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("changed after pinning", p.detail)

    def test_a_dated_addendum_outside_the_region_keeps_the_pin(self):
        """Tệp này **phải** mọc thêm (§1.2): phụ lục có ngày, trạng thái G5.3, con
        trỏ tới báo cáo. Digest cả tệp làm mỗi lần thêm như thế vỡ pin, và một pin
        vỡ thường xuyên thì lần sửa thật vào vùng ghim đi qua giữa tiếng ồn ấy."""
        path = self.prereg()
        self.prereg(tep=self.REGION["also_in"])
        c = self.crit_prereg(prereg_sha256=CL.frozen_region_digest(path, self.REGION))
        self.prereg(ngoai="\n## 3. Học được sau — 2026-09-14\n\nG5.3 chưa chạy.\n")
        self.assertIs(CL.probe_prereg_digest(self.repo.ctx(c)).outcome, Outcome.PASSED)

    def test_crlf_checkout_does_not_break_the_pin(self):
        """Kho không có `.gitattributes` và CI chạy cả trên Windows, nên một
        checkout bật `core.autocrlf` là FAILED giả nếu không chuẩn hoá LF."""
        path = self.prereg()
        self.prereg(tep=self.REGION["also_in"])
        c = self.crit_prereg(prereg_sha256=CL.frozen_region_digest(path, self.REGION))
        path.write_bytes(path.read_text(encoding="utf-8").replace("\n", "\r\n").encode())
        self.assertIs(CL.probe_prereg_digest(self.repo.ctx(c)).outcome, Outcome.PASSED)

    def test_no_markers_is_unrunnable_and_never_falls_back_to_the_whole_file(self):
        """Không mốc thì **không đo được**, và băm cả tệp thay vào là băm một thứ
        khác rồi gọi là đã đo thứ này — đúng lớp lỗi đạt-sai hợp đồng cấm."""
        path = self.repo.write("docs/BENCH-PREREGISTRATION-C2.md", "# prereg\nkhông mốc\n")
        c = self.crit_prereg(prereg_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        p = CL.probe_prereg_digest(self.repo.ctx(c))
        self.assertIs(p.outcome, Outcome.UNRUNNABLE)
        self.assertIn("0", p.detail)

    def test_two_frozen_regions_is_unrunnable_not_a_pass(self):
        """Hai vùng ghim thì không biết vùng nào là cam kết."""
        path = self.prereg()
        path.write_text(path.read_text(encoding="utf-8") * 2, encoding="utf-8")
        p = CL.probe_prereg_digest(self.repo.ctx(self.crit_prereg(prereg_sha256="0" * 64)))
        self.assertIs(p.outcome, Outcome.UNRUNNABLE)
        self.assertIn("2", p.detail)

    def test_the_historical_copy_must_carry_the_same_bytes(self):
        """Bản lịch sử là thứ **định ngày** cho tiền đăng ký; nó lệch thì cái
        chứng minh "viết trước khi có dữ liệu" đã mất, dù bản ghim vẫn khớp."""
        path = self.prereg()
        self.prereg("ngưỡng ≥ 9, khác hẳn", tep=self.REGION["also_in"])
        c = self.crit_prereg(prereg_sha256=CL.frozen_region_digest(path, self.REGION))
        p = CL.probe_prereg_digest(self.repo.ctx(c))
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("bench.md", p.detail)

    def test_a_missing_historical_copy_is_unrunnable(self):
        path = self.prereg()
        c = self.crit_prereg(prereg_sha256=CL.frozen_region_digest(path, self.REGION))
        p = CL.probe_prereg_digest(self.repo.ctx(c))
        self.assertIs(p.outcome, Outcome.UNRUNNABLE)
        self.assertIn("bench.md", p.detail)

    #: Giao thức tuyển, ở dạng máy đọc được như `closure-gate.json` khai.
    QREGION = {"begin": r"<!--\s*QUAL-FROZEN:BEGIN\s*-->",
               "end": r"<!--\s*QUAL-FROZEN:END\s*-->"}

    def qual(self, nguong="ngưỡng 15 %, cỡ mẫu 12", *, digest=None, qualifies="có"):
        """Giao thức + báo cáo đúng hình dạng probe G5.3 đọc."""
        gt = self.repo.write(
            "docs/QUAL-PROTOCOL.md",
            "# gt\n\n<!-- QUAL-FROZEN:BEGIN -->\n" + nguong + "\n<!-- QUAL-FROZEN:END -->\n")
        pin = CL.frozen_region_digest(gt, self.QREGION)
        self.repo.write("docs/BENCH-PAIR-QUALIFICATION.md",
                        f"# tuyển\n\ndigest vùng ghim `{(digest or pin)[:16]}…`\n\n"
                        "| model | client | phiên | cut | rate | infra | qualifies | evidence |\n"
                        "|---|---|---|---|---|---|---|---|\n"
                        f"| m | opencode | 12 | 1 | 8,3 % | 0 | {qualifies} | e.jsonl |\n")
        return {"evidence": "docs/BENCH-PAIR-QUALIFICATION.md",
                "protocol": "docs/QUAL-PROTOCOL.md",
                "protocol_sha256": pin,
                "protocol_frozen_region": dict(self.QREGION)}, gt

    def test_a_qualifying_pair_passes_when_the_protocol_pin_still_holds(self):
        c, _ = self.qual()
        p = CL.probe_pair_qualification(self.repo.ctx(c))
        self.assertIs(p.outcome, Outcome.PASSED, p.detail)

    def test_a_protocol_edited_after_pinning_fails_however_good_the_report(self):
        """Chủ dự án: *"do not inspect qualification results and then choose the
        threshold."* Báo cáo đẹp trên một giao thức đã sửa là đúng thứ ấy, nên
        probe phải đọc pin trước khi đọc bảng."""
        c, gt = self.qual()
        gt.write_text(gt.read_text(encoding="utf-8").replace("15 %", "40 %"), encoding="utf-8")
        p = CL.probe_pair_qualification(self.repo.ctx(c))
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("after", p.detail.lower())

    def test_a_report_naming_another_protocol_digest_cannot_be_read(self):
        """Một bảng sinh dưới giao thức khác đọc bằng giao thức này là so hai
        thứ khác nhau rồi gọi là một."""
        c, _ = self.qual(digest="f" * 64)
        p = CL.probe_pair_qualification(self.repo.ctx(c))
        self.assertIs(p.outcome, Outcome.UNRUNNABLE)
        self.assertIn("ffffffff", p.detail)

    def test_a_report_stating_no_protocol_digest_is_unrunnable(self):
        c, _ = self.qual()
        self.repo.write("docs/BENCH-PAIR-QUALIFICATION.md",
                        "# tuyển\n\n| model | client | cut | rate | qualifies | evidence |\n"
                        "|---|---|---|---|---|---|\n| m | opencode | 1 | 8,3 % | có | e |\n")
        p = CL.probe_pair_qualification(self.repo.ctx(c))
        self.assertIs(p.outcome, Outcome.UNRUNNABLE)
        self.assertIn("digest", p.detail)

    def test_no_pair_qualifying_still_blocks_with_the_pin_intact(self):
        c, _ = self.qual(qualifies="chưa kết luận")
        p = CL.probe_pair_qualification(self.repo.ctx(c))
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("WAIVER_PENDING", p.detail)

    # ------------------------------------------------------------ G5.2 cohorts
    #
    # The gate asks whether the evidence behind a CURRENT claim can show that no
    # cut or infra session was graded as a result. Rows written before the
    # classification schema existed cannot answer that and must not be made to
    # pretend: they are declared historical. The matrix below is the owner's
    # anti-cherry-pick list (A-F) — the point of cohort scoping is that it must
    # be impossible to pick convenient rows *after* seeing the result.

    def cohort(self, **over):
        """A minimal, fully reconciling CURRENT cohort. Tests break one thing."""
        rows = [{"client": "x", "task_id": "t1", "attempt": 1, "outcome": "PASS",
                 "exit_status": "ok", "infra_retries": 0},
                {"client": "x", "task_id": "t1", "attempt": 2, "outcome": "FAIL",
                 "exit_status": "ok", "infra_retries": 0}]
        rows = over.pop("rows", rows)
        sessions = over.pop("sessions", [
            {"session_id": f"s{i}", "client": r["client"], "task_id": r["task_id"],
             "attempt": r["attempt"], "status": "ok"} for i, r in enumerate(rows)])
        d = CL.cohort.COHORT_DIR
        ap = self.repo.write(f"{d}/K-attempts.jsonl",
                             "".join(json.dumps(r) + "\n" for r in rows))
        sp = self.repo.write_json(f"{d}/K-sessions.json", {"sessions": sessions})
        totals = over.pop("totals", None)
        if totals is None:
            totals = CL.cohort.compute_totals(rows, sessions)
        decl = {
            "cohort_id": "K", "status": CL.cohort.CURRENT,
            "protocol_path": "docs/p.md", "protocol_digest": "d" * 64,
            "benchmark_execution_sha": "a" * 40, "manifest_sha256": "m" * 64,
            "scoring_version": "v1", "report": "docs/R.md",
            "attempts": {"path": f"{d}/K-attempts.jsonl",
                         "sha256": CL.cohort.sha256_text(ap.read_text(encoding="utf-8")),
                         "count": len(rows)},
            "sessions": {"path": f"{d}/K-sessions.json",
                         "sha256": CL.cohort.sha256_text(sp.read_text(encoding="utf-8")),
                         "count": len(sessions)},
            "totals": totals,
        }
        decl.update(over)
        self.repo.write_json(f"{d}/K.json", decl)
        self.repo.write("docs/R.md",
                        f"# K\n\ntotals_sha256 = {CL.cohort.totals_digest(totals)}\n")
        return decl

    def g52(self):
        return CL.probe_cut_session_separation(self.repo.ctx())

    def test_no_cohort_declared_is_unrunnable(self):
        p = self.g52()
        self.assertIs(p.outcome, Outcome.UNRUNNABLE)
        self.assertIn("cohort", p.detail)

    def test_a_fully_reconciling_cohort_passes(self):
        self.cohort()
        p = self.g52()
        self.assertIs(p.outcome, Outcome.PASSED, p.detail)
        self.assertIn("2 attempts", p.detail)

    # A -- a current report cannot omit failing rows from its declared cohort
    def test_A_report_omitting_a_failing_row_fails(self):
        rows = [{"client": "x", "task_id": "t1", "attempt": 1, "outcome": "PASS",
                 "exit_status": "ok", "infra_retries": 0},
                {"client": "x", "task_id": "t1", "attempt": 2, "outcome": "FAIL",
                 "exit_status": "ok", "infra_retries": 0}]
        # the report is written for a cohort of one PASS: totals claim 1/1
        self.cohort(rows=rows, totals={"x.attempts": 1, "x.pass": 1})
        p = self.g52()
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("x.attempts declared 1 but the rows give 2", p.detail)

    # B -- a cohort cannot be re-selected after scoring
    def test_B_editing_rows_after_the_cohort_was_frozen_fails(self):
        self.cohort()
        d = CL.cohort.COHORT_DIR
        self.repo.write(f"{d}/K-attempts.jsonl",
                        json.dumps({"client": "x", "task_id": "t1", "attempt": 1,
                                    "outcome": "PASS", "exit_status": "ok",
                                    "infra_retries": 0}) + "\n")
        p = self.g52()
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("changed after it was frozen", p.detail)

    def test_B_rows_with_no_declared_digest_fail(self):
        decl = self.cohort()
        decl["attempts"].pop("sha256")
        self.repo.write_json(f"{CL.cohort.COHORT_DIR}/K.json", decl)
        p = self.g52()
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("re-selected after scoring", p.detail)

    # C -- cohort identity binds to the pre-registered run/protocol
    def test_C_cohort_without_protocol_digest_fails(self):
        decl = self.cohort()
        decl["protocol_digest"] = ""
        self.repo.write_json(f"{CL.cohort.COHORT_DIR}/K.json", decl)
        p = self.g52()
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("protocol_digest", p.detail)

    def test_C_cohort_without_execution_sha_fails(self):
        decl = self.cohort()
        decl["benchmark_execution_sha"] = ""
        self.repo.write_json(f"{CL.cohort.COHORT_DIR}/K.json", decl)
        p = self.g52()
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("benchmark_execution_sha", p.detail)

    # D -- attempt/session counts reconcile
    def test_D_an_attempt_with_no_session_fails(self):
        rows = [{"client": "x", "task_id": "t1", "attempt": 1, "outcome": "PASS",
                 "exit_status": "ok", "infra_retries": 0}]
        self.cohort(rows=rows, sessions=[])
        p = self.g52()
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("no session recorded", p.detail)

    def test_D_a_session_outside_the_cohort_fails(self):
        self.cohort(sessions=[{"session_id": "s", "client": "x", "task_id": "OTHER",
                               "attempt": 9, "status": "ok"}])
        p = self.g52()
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("belong to no declared attempt", p.detail)

    def test_D_a_run_no_retry_counter_explains_fails(self):
        rows = [{"client": "x", "task_id": "t1", "attempt": 1, "outcome": "PASS",
                 "exit_status": "ok", "infra_retries": 0}]
        two = [{"session_id": "s1", "client": "x", "task_id": "t1", "attempt": 1,
                "status": "ok"},
               {"session_id": "s2", "client": "x", "task_id": "t1", "attempt": 1,
                "status": "ok"}]
        self.cohort(rows=rows, sessions=two)
        p = self.g52()
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("sessions != infra_retries + 1", p.detail)

    def test_D_report_not_carrying_the_totals_digest_fails(self):
        self.cohort()
        self.repo.write("docs/R.md", "# K\n\nno digest here\n")
        p = self.g52()
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("totals digest", p.detail)

    # the C-1b artifact itself: a cut session graded as a result
    def test_a_cut_final_session_graded_as_a_result_fails(self):
        rows = [{"client": "x", "task_id": "t1", "attempt": 1, "outcome": "FAIL",
                 "exit_status": "ok", "infra_retries": 0}]
        self.cohort(rows=rows, sessions=[
            {"session_id": "s1", "client": "x", "task_id": "t1", "attempt": 1,
             "status": "cut"}])
        p = self.g52()
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("C-1b artifact", p.detail)

    # E -- a current cohort with an unclassified row fails
    def test_E_a_current_row_without_exit_status_fails(self):
        rows = [{"client": "x", "task_id": "t1", "attempt": 1, "outcome": "PASS",
                 "infra_retries": 0}]
        self.cohort(rows=rows)
        p = self.g52()
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("no exit_status", p.detail)

    # F -- historical rows do NOT fail the probe merely for the old schema
    def test_F_historical_rows_without_exit_status_do_not_fail(self):
        self.cohort()
        self.repo.write(".bench/results.jsonl",
                        json.dumps({"task_id": "old", "outcome": "PASS"}) + "\n")
        self.repo.write_json(f"{CL.cohort.COHORT_DIR}/H.json", {
            "cohort_id": "H", "status": CL.cohort.HISTORICAL,
            "raw_path": ".bench/results.jsonl", "raw_sha256": "f" * 64,
            "limitation": "predates exit_status; backs no current claim",
            "report": None})
        p = self.g52()
        self.assertIs(p.outcome, Outcome.PASSED, p.detail)
        self.assertIn("1 historical", p.detail)

    def test_F_a_historical_cohort_backing_a_report_fails(self):
        self.cohort()
        self.repo.write_json(f"{CL.cohort.COHORT_DIR}/H.json", {
            "cohort_id": "H", "status": CL.cohort.HISTORICAL,
            "raw_path": ".bench/results.jsonl", "raw_sha256": "f" * 64,
            "limitation": "predates exit_status",
            "report": "docs/SOMETHING.md"})
        p = self.g52()
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("may not back a current claim", p.detail)

    def test_F_a_historical_cohort_with_no_limitation_fails(self):
        self.cohort()
        self.repo.write_json(f"{CL.cohort.COHORT_DIR}/H.json", {
            "cohort_id": "H", "status": CL.cohort.HISTORICAL,
            "raw_path": ".bench/results.jsonl", "raw_sha256": "f" * 64,
            "report": None})
        p = self.g52()
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("limitation", p.detail)

    def test_post_stop_data_must_be_labelled_in_the_report(self):
        self.cohort(confirmatory={"confirmatory_attempts": 1, "post_stop_attempts": 1,
                                  "post_stop_label": "POST-STOP EXPLORATORY"})
        p = self.g52()
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("post-stop label", p.detail)

    def test_missing_pair_qualification_is_unrunnable(self):
        p = CL.probe_pair_qualification(self.repo.ctx({"evidence": "docs/BENCH-PAIR-QUALIFICATION.md"}))
        self.assertIs(p.outcome, Outcome.UNRUNNABLE)

    def test_no_pair_qualifying_is_waiver_pending_and_blocks(self):
        self.repo.write("docs/BENCH-PAIR-QUALIFICATION.md", (
            "| model | client | sessions | cut sessions | cut rate | timeouts | qualifies | evidence |\n"
            "|---|---|---|---|---|---|---|---|\n"
            "| mycombo | opencode | 8 | 3 | 0.38 | 0 | no | .bench-q/a |\n"))
        p = CL.probe_pair_qualification(self.repo.ctx({"evidence": "docs/BENCH-PAIR-QUALIFICATION.md"}))
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("WAIVER_PENDING", p.detail)
        self.assertTrue(p.outcome.blocks)

    def test_one_qualifying_pair_passes(self):
        self.repo.write("docs/BENCH-PAIR-QUALIFICATION.md", (
            "| model | client | sessions | cut sessions | cut rate | timeouts | qualifies | evidence |\n"
            "|---|---|---|---|---|---|---|---|\n"
            "| sonnet | claude | 8 | 0 | 0.00 | 0 | yes | .bench-q/b |\n"))
        p = CL.probe_pair_qualification(self.repo.ctx({"evidence": "docs/BENCH-PAIR-QUALIFICATION.md"}))
        self.assertIs(p.outcome, Outcome.PASSED)
        self.assertIn("sonnet/claude", p.detail)

    def test_a_table_missing_the_declared_columns_is_unrunnable(self):
        self.repo.write("docs/BENCH-PAIR-QUALIFICATION.md",
                        "| pair | qualifies |\n|---|---|\n| x | yes |\n")
        p = CL.probe_pair_qualification(self.repo.ctx({"evidence": "docs/BENCH-PAIR-QUALIFICATION.md"}))
        self.assertIs(p.outcome, Outcome.UNRUNNABLE)
        self.assertIn("does not state", p.detail)

    def test_bench_reproducible_needs_both_halves(self):
        """The manifest matching is not enough: a criterion with two conjuncts
        must not pass on one of them.

        Hermetic on purpose. Written against the real `ROOT` it asserted a fact
        about *this checkout's* evidence — so it passed only while
        `closure-evidence/bench-selfcheck.json` happened to be absent or stale,
        and went red the moment that record was written correctly. A test whose
        verdict depends on today's working tree is measuring the tree, not the
        logic. The manifest half is read from the real dataset (the probe resolves
        it through `tests.bench._mine`, which is not redirectable), so only the
        recorded half is faked here — and faking its *absence* is precisely the
        conjunct under test.
        """
        p = CL.probe_bench_reproducible(
            CL.Ctx(root=self.repo.root, spec=self.repo.spec, criterion={}))
        self.assertIs(p.outcome, Outcome.UNRUNNABLE)
        self.assertIn("bench-selfcheck.json", p.detail)

    def test_bench_reproducible_passes_only_with_a_full_selfcheck_record(self):
        """And the recorded half must carry real counts.

        A record of `1/1` satisfied `passed == total` and so passed a criterion
        whose contract text says nineteen checks — that really happened, in
        `validation/record_closure_evidence.py`, because its regex matched the
        first `N/N` anywhere in the output.
        """
        self.repo.write("closure-evidence/bench-selfcheck.json",
                        '{"commit": "deadbee", "exit": 0, "passed": 19, "total": 19}')
        p = CL.probe_bench_reproducible(
            CL.Ctx(root=self.repo.root, spec=self.repo.spec, criterion={}))
        # The manifest half still reads the real dataset, so this asserts the
        # recorded half stopped being the blocker — not that the whole criterion
        # passes inside a temporary directory.
        self.assertNotIn("bench-selfcheck.json", p.detail)

    def test_a_report_stating_neither_band_nor_inconclusive_fails(self):
        self.repo.write("docs/BENCH-REPORT-X.md", "# X\n\npass@1 48/48 vs 48/48, delta 0.\n")
        p = CL.probe_inconclusive_reported(self.repo.ctx())
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("BENCH-REPORT-X.md", p.detail)

    def test_a_report_stating_it_is_inconclusive_passes(self):
        self.repo.write("docs/BENCH-REPORT-X.md", "# X\n\nKhông kết luận được từ 30 task.\n")
        self.assertIs(CL.probe_inconclusive_reported(self.repo.ctx()).outcome, Outcome.PASSED)

    def test_no_bench_report_at_all_is_unrunnable(self):
        self.assertIs(CL.probe_inconclusive_reported(self.repo.ctx()).outcome, Outcome.UNRUNNABLE)

    def test_a_retired_claim_on_a_public_surface_fails(self):
        self.repo.write("README.md", "AISEF has near-zero measured cost overhead.\n")
        p = CL.probe_no_stale_claims(self.repo.ctx({"evidence": "README.md"}))
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("near-zero", p.detail)

    def test_clean_public_surfaces_pass(self):
        self.repo.write("README.md", "AISEF measured +44% turns on C-1.\n")
        self.assertIs(CL.probe_no_stale_claims(self.repo.ctx({"evidence": "README.md"})).outcome,
                      Outcome.PASSED)

    def test_a_missing_public_surface_is_unrunnable(self):
        p = CL.probe_no_stale_claims(self.repo.ctx({"evidence": "README.md,landingpage/index.html"}))
        self.assertIs(p.outcome, Outcome.UNRUNNABLE)

    # ------------------------------------------------ G5.6 claim status
    #
    # A substring cannot tell asserting from mentioning. Both failure
    # directions were real on this repository: `±0,08` slipped an ASCII-only
    # matcher, and the C-2 report's explanation of *why* `±0.08` was withdrawn
    # was read as the claim itself. Status is therefore declared in the source,
    # never inferred — and anything undeclared counts as a current assertion,
    # so silence cannot shelter one.

    REGISTRY = {"claim_registry": {
        "retired": [{"id": "noise-band", "forms": ["±0.08", "±0,08"]}],
        "annotation": {
            "begin": r"<!--\s*claim:(CURRENT_ASSERTION|HISTORICAL|RETIRED|WITHDRAWAL_EXPLANATION)\s*-->",
            "end": r"<!--\s*/claim\s*-->",
            "mention_ok": ["HISTORICAL", "RETIRED", "WITHDRAWAL_EXPLANATION"]}}}

    def claims(self, body: str):
        self.repo.write("docs/BENCH-REPORT-X.md", body)
        self.repo.spec.update(self.REGISTRY)
        return CL.probe_no_stale_claims(
            self.repo.ctx({"evidence": "docs/BENCH-REPORT-X.md"}))

    def test_current_assertion_with_ascii_band_fails(self):
        p = self.claims("# X\n\nThe measured noise band is ±0.08.\n")
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("noise-band", p.detail)

    def test_current_assertion_with_locale_band_fails(self):
        """`±0,08` is the same claim with a decimal comma. Retiring a number
        and restating it in another locale is not a correction."""
        p = self.claims("# X\n\nDải nhiễu đã đo là ±0,08.\n")
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("noise-band", p.detail)

    def test_explaining_that_the_band_is_retired_passes(self):
        p = self.claims("# X\n\n<!-- claim:WITHDRAWAL_EXPLANATION -->\n"
                        "±0.08 is retired: it came from C-1b's artifact delta "
                        "and must not be used.\n<!-- /claim -->\n")
        self.assertIs(p.outcome, Outcome.PASSED, p.detail)

    def test_a_dated_historical_mention_passes(self):
        p = self.claims("# X\n\n<!-- claim:HISTORICAL -->\n"
                        "C-1b (13/09/2026) reported ±0,08.\n<!-- /claim -->\n")
        self.assertIs(p.outcome, Outcome.PASSED, p.detail)

    def test_an_unlabelled_bench_report_repeating_the_claim_fails(self):
        """The default is assertion. A report that simply restates a retired
        number, with no status declared, is making the claim."""
        p = self.claims("# X\n\nResults sit inside ±0.08 of the control.\n")
        self.assertIs(p.outcome, Outcome.FAILED)

    def test_annotating_a_live_claim_as_current_does_not_excuse_it(self):
        p = self.claims("# X\n\n<!-- claim:CURRENT_ASSERTION -->\n"
                        "The band is ±0.08.\n<!-- /claim -->\n")
        self.assertIs(p.outcome, Outcome.FAILED)

    def test_an_unterminated_region_is_not_a_shelter(self):
        """An opening marker with no close would otherwise hide the rest of
        the file — the easiest possible bypass."""
        p = self.claims("# X\n\n<!-- claim:RETIRED -->\nThe band is ±0.08.\n")
        self.assertIs(p.outcome, Outcome.FAILED)

    def test_text_outside_an_annotated_region_is_still_audited(self):
        p = self.claims("# X\n\n<!-- claim:HISTORICAL -->\nold\n<!-- /claim -->\n"
                        "And today the band is ±0,08.\n")
        self.assertIs(p.outcome, Outcome.FAILED)


# ------------------------------------------------------------------- G6 probes


PROTOCOL = """# External validation

## Metrics

| Metric | Type |
|---|---|
| Install success | bool |
| Time to first success (any gate passes) | minutes |

## Protocol

Run `aisef doctor`, then `aisef plan`.
"""

RECORD = """# External validation report

Participant: an external engineer, no AISEF contribution

Install success: yes. Time to first success: 35 minutes.

| Finding | Severity | Status |
|---|---|---|
| docs gap | P2 | open |
"""


class TestG6(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.close)
        self.repo.write("docs/EXTERNAL-VALIDATION-v1.1.0.md", PROTOCOL)
        self.repo.write("README.md", "## Install\n\npip install aisef\n\n## Quick Start\n\naisef setup\n")
        self.repo.write("docs/USAGE-GUIDE.md", "aisef doctor\naisef plan\n")
        self.repo.write("pyproject.toml", '[project]\nname = "aisef"\nversion = "1.6.0"\n')
        self.repo.spec["onboarding_digest"] = {
            "sources": [{"path": "README.md", "extract": "section:Install"},
                        {"path": "README.md", "extract": "section:Quick Start"},
                        {"path": "docs/USAGE-GUIDE.md", "extract": "canonical_cli_workflow"},
                        {"path": "docs/EXTERNAL-VALIDATION-v1.1.0.md", "extract": "section:Protocol"},
                        {"path": "aisef/config.py", "extract": "onboarding_defaults"}],
            "onboarding_defaults": ["tools.test", "run.max_turns"]}
        (self.repo.root / "aisef").mkdir(exist_ok=True)
        self.repo.write("aisef/config.py", "# defaults are read from the module, not this text\n")

    def criterion(self) -> dict:
        return {"evidence": "docs/EXTERNAL-VALIDATION-REPORT-v1.1.0.md"}

    def record(self, text: str = RECORD):
        self.repo.write("docs/EXTERNAL-VALIDATION-REPORT-v1.1.0.md", text)

    def digest_file(self, *, version="1.6.0", sha=None):
        now, gone = CL.onboarding_digest(self.repo.root, self.repo.spec["onboarding_digest"])
        self.assertEqual(gone, [])
        self.repo.write_json(f"{CL.EVIDENCE_DIR}/onboarding-digest.json",
                             {"sha256": sha or now, "version": version})
        return now

    def test_the_protocol_existing_does_not_satisfy_g6(self):
        for probe in (CL.probe_external_report, CL.probe_participant_external,
                      CL.probe_onboarding_blockers):
            with self.subTest(probe=probe.__name__):
                p = probe(self.repo.ctx(self.criterion()))
                self.assertIs(p.outcome, Outcome.UNRUNNABLE)
                self.assertIn("protocol, not the record", p.detail)

    def test_record_with_the_protocol_metrics_and_a_matching_digest_passes(self):
        self.record()
        self.digest_file()
        p = CL.probe_external_report(self.repo.ctx(self.criterion()))
        self.assertIs(p.outcome, Outcome.PASSED)

    def test_a_record_missing_a_protocol_metric_fails(self):
        self.record("# report\n\nParticipant: external person\n")
        self.digest_file()
        p = CL.probe_external_report(self.repo.ctx(self.criterion()))
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("Install success", p.detail)

    def test_no_recorded_onboarding_digest_is_unrunnable(self):
        self.record()
        p = CL.probe_external_report(self.repo.ctx(self.criterion()))
        self.assertIs(p.outcome, Outcome.UNRUNNABLE)
        self.assertIn("onboarding-digest.json", p.detail)

    def test_a_changed_onboarding_surface_fails(self):
        self.record()
        self.digest_file()
        self.repo.write("README.md", "## Install\n\npip install aisef --pre --extra-index-url x\n"
                                     "\n## Quick Start\n\naisef setup\n")
        p = CL.probe_external_report(self.repo.ctx(self.criterion()))
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("onboarding surface changed", p.detail)

    def test_prose_reflow_does_not_change_the_digest(self):
        before, _ = CL.onboarding_digest(self.repo.root, self.repo.spec["onboarding_digest"])
        self.repo.write("README.md", "## Install\n\npip   install\n    aisef\n\n## Quick Start\n\naisef setup\n")
        after, _ = CL.onboarding_digest(self.repo.root, self.repo.spec["onboarding_digest"])
        self.assertEqual(before, after)

    def test_a_different_minor_version_fails(self):
        self.record()
        self.digest_file(version="1.5.0")
        p = CL.probe_external_report(self.repo.ctx(self.criterion()))
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("MAJOR.MINOR", p.detail)

    def test_a_vanished_onboarding_default_cannot_be_hashed_silently(self):
        self.repo.spec["onboarding_digest"]["onboarding_defaults"] = ["tools.test", "gone.key"]
        digest, gone = CL.onboarding_digest(self.repo.root, self.repo.spec["onboarding_digest"])
        self.assertEqual(digest, "")
        self.assertIn("gone.key", " ".join(gone))

    def test_an_ai_participant_cannot_satisfy_g6(self):
        self.record("# report\n\nParticipant: Claude agent, external to the project\n")
        p = CL.probe_participant_external(self.repo.ctx(self.criterion()))
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("agent cannot satisfy", p.detail)

    def test_a_record_without_a_participant_line_is_unrunnable(self):
        self.record("# report\n\nInstall success: yes\n")
        p = CL.probe_participant_external(self.repo.ctx(self.criterion()))
        self.assertIs(p.outcome, Outcome.UNRUNNABLE)

    def test_an_external_person_passes(self):
        self.record()
        self.assertIs(CL.probe_participant_external(self.repo.ctx(self.criterion())).outcome,
                      Outcome.PASSED)

    def test_an_unresolved_p0_blocker_fails(self):
        self.record(RECORD.replace("| docs gap | P2 | open |", "| cannot install | P0 | open |"))
        p = CL.probe_onboarding_blockers(self.repo.ctx(self.criterion()))
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("P0", p.detail)

    def test_a_resolved_p0_blocker_passes(self):
        self.record(RECORD.replace("| docs gap | P2 | open |", "| cannot install | P0 | resolved |"))
        self.assertIs(CL.probe_onboarding_blockers(self.repo.ctx(self.criterion())).outcome,
                      Outcome.PASSED)

    def test_a_record_without_a_findings_table_is_unrunnable(self):
        self.record("# report\n\nParticipant: external person\n")
        p = CL.probe_onboarding_blockers(self.repo.ctx(self.criterion()))
        self.assertIs(p.outcome, Outcome.UNRUNNABLE)


# ---------------------------------------------------------------- the waivers


class TestWaivers(unittest.TestCase):
    def setUp(self):
        self.repo = Repo(spec_of(
            crit("GT.1", "tests.test_closure:stub_failed", waiver_eligible=True),
            crit("GT.2", "tests.test_closure:stub_failed")))
        self.addCleanup(self.repo.close)

    def test_a_waiver_without_a_reason_is_refused(self):
        with self.assertRaises(ValueError) as e:
            CL.sign_waiver(self.repo.root, "GT.1", "   ")
        self.assertIn("not evidence", str(e.exception))
        self.assertEqual(CL.load_state(self.repo.root), {})

    def test_only_waiver_eligible_criteria_may_be_waived(self):
        with self.assertRaises(ValueError) as e:
            CL.sign_waiver(self.repo.root, "GT.2", "because I said so")
        self.assertIn("not waiver-eligible", str(e.exception))

    def test_an_unknown_criterion_is_refused(self):
        with self.assertRaises(ValueError):
            CL.sign_waiver(self.repo.root, "G9.9", "reason")

    def test_a_signed_waiver_renders_as_waived_and_does_not_block(self):
        CL.sign_waiver(self.repo.root, "GT.1", "docker is an environment fact", by="owner")
        by_id = {r.id: r for r in self.repo.evaluate().results}
        self.assertIs(by_id["GT.1"].outcome, Outcome.WAIVED)
        self.assertFalse(by_id["GT.1"].outcome.blocks)
        self.assertEqual(by_id["GT.1"].outcome.mark, "◇")
        self.assertIn("docker is an environment fact", by_id["GT.1"].detail)
        self.assertIn("owner", by_id["GT.1"].detail)
        self.assertIs(by_id["GT.2"].outcome, Outcome.FAILED)

    def test_the_waiver_records_what_it_hid(self):
        CL.sign_waiver(self.repo.root, "GT.1", "reason enough")
        r = {x.id: x for x in self.repo.evaluate().results}["GT.1"]
        self.assertEqual(r.waiver["was"], "failed")
        self.assertIn("stub says no", r.waiver["was_detail"])

    def test_a_waiver_never_upgrades_a_passing_criterion(self):
        repo = Repo(spec_of(crit("GT.1", "tests.test_closure:stub_passed", waiver_eligible=True)))
        self.addCleanup(repo.close)
        CL.sign_waiver(repo.root, "GT.1", "not needed")
        self.assertIs(repo.evaluate().results[0].outcome, Outcome.PASSED)


# --------------------------------------------------------------- the approval


class TestApproval(unittest.TestCase):
    def repo(self, *criteria, pin=True) -> Repo:
        repo = Repo(spec_of(*criteria), pin=pin)
        self.addCleanup(repo.close)
        return repo

    def test_approval_is_refused_while_anything_blocks(self):
        repo = self.repo(crit("GT.1", "tests.test_closure:stub_failed"))
        with self.assertRaises(ValueError) as e:
            CL.sign_approval(repo.root)
        self.assertIn("GT.1", str(e.exception))
        self.assertEqual(CL.load_state(repo.root), {})

    def test_approval_is_refused_while_the_contract_is_unpinned(self):
        repo = self.repo(crit("GT.1", "tests.test_closure:stub_passed"), pin=False)
        with self.assertRaises(ValueError) as e:
            CL.sign_approval(repo.root)
        self.assertIn("unpinned", str(e.exception))

    def test_approval_records_who_when_and_the_digest_set(self):
        repo = self.repo(crit("GT.1", "tests.test_closure:stub_reads"))
        repo.write("evidence.txt", "evidence\n")
        rec = CL.sign_approval(repo.root, by="owner", note="ship it")
        self.assertEqual(rec["by"], "owner")
        self.assertTrue(rec["at"])
        self.assertEqual(rec["contract_sha256"], repo.evaluate().contract["sha256"])
        self.assertTrue(rec["digests"]["GT.1"])
        self.assertEqual(CL.load_state(repo.root)["approval"]["note"], "ship it")

    def test_an_approved_gate_reads_approved(self):
        repo = self.repo(crit("GT.1", "tests.test_closure:stub_reads"))
        repo.write("evidence.txt", "evidence\n")
        CL.sign_approval(repo.root, by="owner")
        report = CL.evaluate(repo.root)
        self.assertEqual(report.approval["status"], "approved")
        self.assertTrue(report.closable)

    def test_an_evidence_digest_that_moved_makes_the_approval_stale(self):
        repo = self.repo(crit("GT.1", "tests.test_closure:stub_reads"))
        repo.write("evidence.txt", "evidence\n")
        CL.sign_approval(repo.root, by="owner")
        repo.write("evidence.txt", "different evidence\n")
        report = CL.evaluate(repo.root)
        self.assertEqual(report.approval["status"], "stale")
        self.assertIn("evidence digest changed: GT.1", " ".join(report.approval["stale_because"]))

    def test_editing_the_contract_makes_the_approval_stale(self):
        repo = self.repo(crit("GT.1", "tests.test_closure:stub_reads"))
        repo.write("evidence.txt", "evidence\n")
        CL.sign_approval(repo.root, by="owner")
        repo.write("docs/PROJECT-CLOSURE-GATE.md", Repo.CONTRACT + "\nedited to be satisfied\n")
        report = CL.evaluate(repo.root)
        self.assertEqual(report.contract["state"], "stale")
        self.assertFalse(report.closable)
        self.assertIn("contract digest changed", " ".join(report.approval["stale_because"]))


class TestStaleness(unittest.TestCase):
    """Three independent causes, per §4.4. The first two are above; the third is
    a declared freshness window lapsing, which is the criterion itself turning
    red rather than a separate mechanism."""

    def test_a_lapsed_freshness_window_blocks_without_anything_else_changing(self):
        repo = Repo()
        self.addCleanup(repo.close)
        runs = [CF.ClientRun(client=c, version="1.0") for c in CF.RELEASE_CLIENTS]
        for run in runs:
            run.results = [CF.ProbeResult(p[0], True) for p in CF.PROBES]
        criterion = {"freshness": {"max_from": "aisef.control.conformance:MAX_AGE_DAYS"}}
        fresh = (date.today() - timedelta(days=1)).isoformat()
        repo.write(CF.REPORT_PATH, CF.Report(runs=runs, generated=fresh).to_markdown())
        self.assertIs(CL.probe_conformance(repo.ctx(criterion)).outcome, Outcome.PASSED)
        lapsed = (date.today() - timedelta(days=CF.MAX_AGE_DAYS + 1)).isoformat()
        repo.write(CF.REPORT_PATH, CF.Report(runs=runs, generated=lapsed).to_markdown())
        p = CL.probe_conformance(repo.ctx(criterion))
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertTrue(p.outcome.blocks)

    def test_staleness_reuses_the_approval_status_vocabulary(self):
        from aisef.control.approvals import Status

        report = CL.Report(contract={"sha256": "x", "state": "pinned"}, results=[])
        state = {"approval": {"contract_sha256": "y", "digests": {}}}
        self.assertEqual(CL.approval_state(state, report)["status"], Status.STALE.value)
        self.assertEqual(CL.approval_state({}, report)["status"], Status.PENDING.value)


class TestPin(unittest.TestCase):
    def test_pin_writes_the_contract_digest_into_the_criteria_file(self):
        repo = Repo(pin=False)
        self.addCleanup(repo.close)
        self.assertEqual(repo.evaluate().contract["state"], "unpinned")
        pinned = CL.pin(repo.root)
        self.assertEqual(list(pinned), ["docs/PROJECT-CLOSURE-GATE.md"])
        spec = CL.load_spec(repo.root)
        self.assertEqual(spec["contract_sha256"],
                         hashlib.sha256(Repo.CONTRACT.encode()).hexdigest())
        self.assertEqual(CL.evaluate(repo.root).contract["state"], "pinned")

    def test_pin_also_pins_the_bench_preregistration_when_it_exists(self):
        repo = Repo(spec_of(crit("G5.1", "aisef.control.closure:probe_prereg_digest",
                                 evidence="docs/BENCH-PREREGISTRATION-C2.md")), pin=False)
        self.addCleanup(repo.close)
        than = ("# prereg\n\n<!-- PREREG-FROZEN:BEGIN -->\nngưỡng ≥ 3\n"
                "<!-- PREREG-FROZEN:END -->\n")
        repo.write("docs/BENCH-PREREGISTRATION-C2.md", than)
        pinned = CL.pin(repo.root)
        self.assertIn("docs/BENCH-PREREGISTRATION-C2.md", pinned)
        self.assertIs(CL.evaluate(repo.root).results[0].outcome, Outcome.PASSED)

    def test_pinned_keys_are_posix_on_every_platform(self):
        """Khoá ghim đi vào **tệp tiêu chí đã commit**, nên nó phải là cùng một
        chuỗi ở mọi nền.

        `str(path.relative_to(root))` cho `docs\\BENCH-PREREGISTRATION-C2.md`
        trên Windows và `docs/BENCH-PREREGISTRATION-C2.md` ở nơi khác: cùng một
        tệp, hai danh tính, và một bản ghim viết ở Windows không tra được ở
        Linux. Đo ở CI Windows, run 34915208534.

        Nói thẳng giới hạn: trên POSIX phép này gần như hiển nhiên đúng, vì
        `as_posix()` và `str()` trùng nhau. Nó có giá trị chứng minh **ở job
        Windows của CI** — và job ấy có thật, nên đây là phép kiểm thật chứ
        không phải phép kiểm trang trí.
        """
        repo = Repo(spec_of(crit("G5.1", "aisef.control.closure:probe_prereg_digest",
                                 evidence="docs/BENCH-PREREGISTRATION-C2.md")), pin=False)
        self.addCleanup(repo.close)
        repo.write("docs/BENCH-PREREGISTRATION-C2.md",
                   "# prereg\n\n<!-- PREREG-FROZEN:BEGIN -->\nx\n<!-- PREREG-FROZEN:END -->\n")
        pinned = CL.pin(repo.root)
        for k in pinned:
            with self.subTest(key=k):
                self.assertNotIn("\\", k, "khoá ghim mang dấu phân cách của nền")
                self.assertEqual(k, Path(k).as_posix())

    def test_pin_writes_the_frozen_region_digest_not_the_whole_file(self):
        """Bản trước ghim cả tệp ở mức trên cùng và để digest vùng ghim ở mức tiêu
        chí không ai đọc — hai nhà cho một con số, và probe đọc nhà sai."""
        crit_g5 = crit("G5.1", "aisef.control.closure:probe_prereg_digest",
                       evidence="docs/BENCH-PREREGISTRATION-C2.md")
        crit_g5["prereg_frozen_region"] = {
            "begin": r"<!--\s*PREREG-FROZEN:BEGIN\s*-->",
            "end": r"<!--\s*PREREG-FROZEN:END\s*-->"}
        repo = Repo(spec_of(crit_g5), pin=False)
        self.addCleanup(repo.close)
        than = ("# prereg\n\n<!-- PREREG-FROZEN:BEGIN -->\nngưỡng ≥ 3\n"
                "<!-- PREREG-FROZEN:END -->\n\n## 3. phụ lục có ngày\n")
        path = repo.write("docs/BENCH-PREREGISTRATION-C2.md", than)
        CL.pin(repo.root)
        spec = CL.load_spec(repo.root)
        self.assertNotIn("prereg_sha256", spec)
        c = CL._find(spec, "G5.1")[1]
        self.assertEqual(c["prereg_sha256"],
                         CL.frozen_region_digest(path, c["prereg_frozen_region"]))
        self.assertNotEqual(c["prereg_sha256"],
                            hashlib.sha256(path.read_bytes()).hexdigest())

    def test_repinning_is_refused_because_it_would_hide_an_edit(self):
        repo = Repo()
        self.addCleanup(repo.close)
        with self.assertRaises(ValueError) as e:
            CL.pin(repo.root)
        self.assertIn("already pinned", str(e.exception))

    def test_evaluation_never_computes_the_pin(self):
        """A pin computed at evaluation time is not a pin."""
        repo = Repo(spec_of(crit("GT.1", "tests.test_closure:stub_passed")), pin=False)
        self.addCleanup(repo.close)
        report = repo.evaluate()
        self.assertFalse(report.blocking)
        self.assertFalse(report.closable, "unpinned contract must not be closable")
        self.assertEqual(CL.load_spec(repo.root)["contract_sha256"], "")


# ------------------------------------------------------- the six things it never does


class TestNeverDoes(unittest.TestCase):
    SOURCE = ROOT / "aisef" / "control" / "closure.py"
    CLI = ROOT / "aisef" / "cli" / "closure.py"

    def calls(self, path: Path) -> list[str]:
        names = []
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call):
                f = node.func
                names.append(f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", ""))
        return names

    def imports(self, path: Path) -> list[str]:
        out = []
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom):
                out.append(node.module or "")
            elif isinstance(node, ast.Import):
                out += [a.name for a in node.names]
        return out

    def test_never_launches_an_agent(self):
        """No client adapter, no session runner: the evaluator reads records of
        runs, it does not start them."""
        mods = " ".join(self.imports(self.SOURCE))
        for forbidden in ("aisef.clients.compile", "clients.compile", "phases.run", "phases.qa"):
            self.assertNotIn(forbidden, mods)
        for call in ("ADAPTERS", "run_story", "run_session", "run_agent", "compile_all"):
            self.assertNotIn(call, self.calls(self.SOURCE))

    def test_never_runs_a_paid_workload(self):
        """Not even a free subprocess of its own: the one process it starts is
        read-only git, through the existing helper."""
        for call in ("run", "Popen", "check_output", "check_call", "call",
                     "run_suite", "run_selfcheck", "score", "evaluate_pre_deploy"):
            self.assertNotIn(call, self.calls(self.SOURCE), f"closure.py calls {call}")

    def test_never_modifies_a_corpus(self):
        corpus = Corpus()
        self.addCleanup(corpus.close)
        corpus.pre_deploy()
        ApprovalStore(corpus.art).approve(Gate.PRE_DEPLOY, by="owner")
        shipped = CL.load_spec(ROOT)
        repo = Repo(shipped, pin=False)
        self.addCleanup(repo.close)
        before = corpus.digests()
        CL.evaluate(repo.root, corpus=str(corpus.root), spec=shipped)
        self.assertEqual(corpus.digests(), before)

    def test_never_approves_itself(self):
        """`sign_approval` exists in the control module and is called nowhere in
        it — only the CLI calls it, and only behind `--approve`."""
        self.assertNotIn("sign_approval", self.calls(self.SOURCE))
        cli = self.CLI.read_text(encoding="utf-8")
        tree = ast.parse(cli)
        guarded = [n for n in ast.walk(tree)
                   if isinstance(n, ast.If) and "approve" in ast.dump(n.test)
                   and "sign_approval" in ast.dump(n)]
        self.assertTrue(guarded, "sign_approval is not behind an `--approve` check")
        self.assertEqual(cli.count("sign_approval"), 1)

    def test_never_turns_unconfigured_into_pass(self):
        repo = Repo(spec_of(crit("GT.1", "tests.test_closure:stub_unconfigured")))
        self.addCleanup(repo.close)
        r = repo.evaluate().results[0]
        self.assertIsNot(r.outcome, Outcome.PASSED)
        self.assertIs(r.outcome, Outcome.UNRUNNABLE)

    def test_never_silently_substitutes_a_missing_corpus(self):
        """The fallback corpus exists on disk and is still not used."""
        fallback = Corpus()
        self.addCleanup(fallback.close)
        shipped = CL.load_spec(ROOT)
        for gate in shipped["gates"]:
            if gate.get("corpus"):
                gate["corpus"]["fallback"] = fallback.root.name
        repo = Repo(shipped, pin=False)
        self.addCleanup(repo.close)
        before = fallback.digests()
        report = CL.evaluate(repo.root, spec=shipped, corpus=str(repo.root / "no-such-corpus"))
        g4 = [r for r in report.results if r.gate == "G4"]
        self.assertEqual(len(g4), 7)
        for r in g4:
            with self.subTest(criterion=r.id):
                self.assertIs(r.outcome, Outcome.UNRUNNABLE)
                self.assertIn("no-such-corpus", r.detail)
        self.assertIn("NOT substituted", g4[0].detail)
        self.assertEqual(fallback.digests(), before)


# ---------------------------------------------------------------- the command


class TestCli(unittest.TestCase):
    def run_cli(self, root: Path, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["--project", str(root), "closure", *args])
        return code, out.getvalue(), err.getvalue()

    def test_a_blocked_gate_exits_one_and_a_clean_one_exits_zero(self):
        blocked = Repo(spec_of(crit("GT.1", "tests.test_closure:stub_failed")))
        self.addCleanup(blocked.close)
        code, out, _ = self.run_cli(blocked.root)
        self.assertEqual(code, 1)
        self.assertIn("BLOCKED", out)
        self.assertIn("✗ GT.1", out)

        clean = Repo(spec_of(crit("GT.1", "tests.test_closure:stub_passed")))
        self.addCleanup(clean.close)
        code, out, _ = self.run_cli(clean.root)
        self.assertEqual(code, 0)
        self.assertIn("CLOSABLE", out)

    def test_a_usage_error_exits_two_not_one(self):
        """1 means blocked here (contract §4.3), so a usage error must not read
        as a verdict about the project. Only the subparser's own errors can be
        redirected: an unrecognised flag is reported by the top-level parser
        and still exits 1, as it does for every other verb."""
        repo = Repo()
        self.addCleanup(repo.close)
        with self.assertRaises(SystemExit) as e:
            self.run_cli(repo.root, "--waive")
        self.assertEqual(e.exception.code, 2)

    def test_no_criteria_file_is_a_usage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _, err = self.run_cli(Path(tmp))
            self.assertEqual(code, 2)
            self.assertIn(CL.CRITERIA_PATH, err)

    def test_the_report_records_probe_evidence_digest_and_time(self):
        repo = Repo(spec_of(crit("GT.1", "tests.test_closure:stub_reads")))
        self.addCleanup(repo.close)
        repo.write("evidence.txt", "evidence\n")
        code, _, _ = self.run_cli(repo.root)
        self.assertEqual(code, 0)
        data = CL.read_report(repo.root)
        row = data["criteria"][0]
        self.assertEqual(row["probe"], "tests.test_closure:stub_reads")
        self.assertEqual(row["evidence"], "evidence.txt")
        self.assertEqual(row["digest"],
                         hashlib.sha256(b"evidence\n").hexdigest())
        self.assertTrue(row["at"])

    def test_report_flag_needs_an_evaluation_first(self):
        repo = Repo()
        self.addCleanup(repo.close)
        code, _, err = self.run_cli(repo.root, "--report")
        self.assertEqual(code, 2)
        self.assertIn("run `aisef closure` first", err)

    def test_report_flag_renders_the_human_form(self):
        repo = Repo(spec_of(crit("GT.1", "tests.test_closure:stub_failed")))
        self.addCleanup(repo.close)
        self.run_cli(repo.root)
        code, out, _ = self.run_cli(repo.root, "--report")
        self.assertEqual(code, 1)
        text = (repo.root / CL.REPORT_MD).read_text(encoding="utf-8")
        self.assertIn("GT.1", text)
        self.assertIn("What blocks closure", text)
        self.assertNotIn("](", text)          # docs/*.md links are checked by test_meta
        self.assertIn(CL.REPORT_MD, out)

    def test_waive_without_a_reason_exits_two(self):
        repo = Repo(spec_of(crit("GT.1", "tests.test_closure:stub_failed", waiver_eligible=True)))
        self.addCleanup(repo.close)
        code, _, err = self.run_cli(repo.root, "--waive", "GT.1")
        self.assertEqual(code, 2)
        self.assertIn("not evidence", err)

    def test_waiving_a_criterion_the_contract_protects_exits_two(self):
        repo = Repo(spec_of(crit("GT.1", "tests.test_closure:stub_failed")))
        self.addCleanup(repo.close)
        code, _, err = self.run_cli(repo.root, "--waive", "GT.1", "--reason", "convenient")
        self.assertEqual(code, 2)
        self.assertIn("not waiver-eligible", err)

    def test_waiving_an_eligible_criterion_unblocks_it(self):
        repo = Repo(spec_of(crit("GT.1", "tests.test_closure:stub_failed", waiver_eligible=True)))
        self.addCleanup(repo.close)
        code, out, _ = self.run_cli(repo.root, "--waive", "GT.1", "--reason", "environment fact")
        self.assertEqual(code, 0)
        self.assertIn("◇ GT.1", out)

    def test_a_reason_without_a_waiver_is_a_usage_error(self):
        repo = Repo()
        self.addCleanup(repo.close)
        code, _, err = self.run_cli(repo.root, "--reason", "dangling")
        self.assertEqual(code, 2)
        self.assertIn("--waive", err)

    def test_approve_refuses_while_blocked_and_signs_when_clean(self):
        repo = Repo(spec_of(crit("GT.1", "tests.test_closure:stub_failed")))
        self.addCleanup(repo.close)
        code, _, err = self.run_cli(repo.root, "--approve")
        self.assertEqual(code, 1)
        self.assertIn("cannot approve", err)
        self.assertEqual(CL.load_state(repo.root), {})

        clean = Repo(spec_of(crit("GT.1", "tests.test_closure:stub_passed")))
        self.addCleanup(clean.close)
        code, out, _ = self.run_cli(clean.root, "--approve")
        self.assertEqual(code, 0)
        self.assertIn("closure approved by", out)
        self.assertTrue(CL.load_state(clean.root)["approval"]["at"])

    def test_pin_then_evaluate(self):
        repo = Repo(spec_of(crit("GT.1", "tests.test_closure:stub_passed")), pin=False)
        self.addCleanup(repo.close)
        code, out, _ = self.run_cli(repo.root)
        self.assertEqual(code, 1, "unpinned contract is not closable")
        code, out, _ = self.run_cli(repo.root, "--pin")
        self.assertEqual(code, 0)
        self.assertIn("pinned docs/PROJECT-CLOSURE-GATE.md", out)
        self.assertIn("CLOSABLE", out)

    def test_the_verb_is_in_the_parser_and_documented(self):
        import argparse

        from aisef.cli.parser import build_parser

        sub = next(a for a in build_parser()._actions
                   if isinstance(a, argparse._SubParsersAction))
        self.assertIn("closure", sub.choices)
        solution = (ROOT / "docs/SOLUTION.md").read_text(encoding="utf-8")
        self.assertRegex(solution, r"(?m)^aisef closure(\s|$)")


class TestRealRepository(unittest.TestCase):
    """The shipped criteria file, evaluated against this checkout. No
    assertions about which cells are green — the point is that all 26 probes
    run, none crashes, and every non-passing one says why."""

    def test_evaluating_this_repository_produces_twentyseven_readable_rows(self):
        report = CL.evaluate(ROOT)
        self.assertEqual(len(report.results), 27)
        for r in report.results:
            with self.subTest(criterion=r.id):
                self.assertIn(r.outcome, tuple(Outcome))
                if r.outcome is not Outcome.PASSED:
                    self.assertTrue(r.detail)
                self.assertTrue(r.probe.startswith("aisef.control.closure:"))
        self.assertIn("Project closure gate", CL.table(report))
        self.assertIn("| criterion |", CL.render(report.as_dict()))


if __name__ == "__main__":
    unittest.main()


class TestMotSHaDuyNhatChoViecDong(unittest.TestCase):
    """Điều chỉnh 2 của chủ dự án: `release_tag_commit == closure_target_sha`.

    Lỗ nó bịt: G1 chứng nhận gói trên PyPI ở commit của **tag**, còn G2–G5 đọc
    **HEAD**. Đó là hai phần mềm khác nhau, và một bản ghi đóng dự án trộn chúng
    lại thì không chứng nhận gì cả. Chủ dự án nói thẳng ba điều không được làm:
    dựng HEAD mà cài bản PyPI cũ; đọc dữ liệu đóng gói từ HEAD rồi bảo nó chứng
    minh tag cũ; gộp bằng chứng từ các revision khác nhau thành một G1 PASS.

    Một tiêu chí **giữ** bất biến này, không rải thành bốn: thông báo hỏng phải
    nói "G1 chứng nhận X, việc đóng nhắm Y" ở đúng một chỗ.
    """

    def repo_at(self, *, target=None, tag_at_head=True):
        c = crit("G1.0", "aisef.control.closure:probe_closure_target",
                 evidence="closure-evidence/release.json")
        repo = Repo(spec_of(c))
        self.addCleanup(repo.close)
        head = repo.head
        git(repo.root, "tag", "v9.9.9", head if tag_at_head else "HEAD")
        if not tag_at_head:
            repo.write("x.txt", "sau khi gắn tag\n")
            git(repo.root, "add", "."); git(repo.root, "commit", "-m", "sau")
        repo.write_json("closure-evidence/release.json",
                        {"version": "9.9.9", "tag": "v9.9.9"})
        if target is not None:
            repo.spec["closure_target_sha"] = target or repo.head
        repo.write_json(CL.CRITERIA_PATH, repo.spec)
        return repo, head

    def probe(self, repo):
        return CL.probe_closure_target(repo.ctx({"evidence": "closure-evidence/release.json"}))

    def test_khong_ghim_dich_thi_khong_do_duoc(self):
        """Chưa chốt ứng viên đóng dự án thì bất biến không có gì để so — chặn,
        và nói việc phải làm, chứ không đạt."""
        repo, _ = self.repo_at()
        p = self.probe(repo)
        self.assertIs(p.outcome, Outcome.UNRUNNABLE)
        self.assertIn("closure_target_sha", p.detail)

    def test_tag_va_head_cung_la_dich_thi_dat(self):
        repo, head = self.repo_at(target="")
        p = self.probe(repo)
        self.assertIs(p.outcome, Outcome.PASSED, p.detail)
        self.assertIn(head[:12], p.detail)

    def test_tag_tro_vao_commit_khac_dich_thi_do(self):
        repo, head = self.repo_at(target="0" * 40)
        p = self.probe(repo)
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn(head[:12], p.detail)
        self.assertIn("000000", p.detail)

    def test_head_di_tiep_sau_khi_ghim_dich_thi_do(self):
        """G2–G5 đọc HEAD. HEAD rời khỏi dịch thì bằng chứng của chúng nói về
        phần mềm khác với cái G1 chứng nhận."""
        repo, head = self.repo_at(tag_at_head=False)
        repo.spec["closure_target_sha"] = head
        repo.write_json(CL.CRITERIA_PATH, repo.spec)
        p = self.probe(repo)
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("HEAD", p.detail)

    def test_khong_co_ban_ghi_phat_hanh_thi_khong_do_duoc(self):
        repo, head = self.repo_at(target="")
        (repo.root / "closure-evidence/release.json").unlink()
        p = self.probe(repo)
        self.assertIs(p.outcome, Outcome.UNRUNNABLE)
        self.assertIn("release.json", p.detail)

    def test_pin_target_ghi_head_va_tu_choi_cay_ban(self):
        """Chốt một ứng viên trên cây bẩn là chốt một SHA không tả được cái đã đo."""
        repo, head = self.repo_at()
        repo.write("dirty.txt", "chưa commit\n")
        with self.assertRaises(ValueError) as e:
            CL.pin_target(repo.root)
        self.assertIn("dirty", str(e.exception).lower())
        git(repo.root, "add", "."); git(repo.root, "commit", "-m", "clean")
        sha = CL.pin_target(repo.root)
        self.assertEqual(sha, repo.head)
        self.assertEqual(CL.load_spec(repo.root)["closure_target_sha"], repo.head)


class TestBangChungTuNoLamMinhCu(unittest.TestCase):
    """Dòng phân loại 162 — bằng chứng buộc vào `commit` mà **chính nó** phải được
    commit thì không bao giờ hiện hành được.

    Mâu thuẫn đo được trên chính kho này 2026-09-14:

    * G2.1 đòi `suite.json.commit == HEAD`;
    * `closure-evidence/` được **theo dõi** bởi git;
    * commit tệp bằng chứng làm HEAD đi qua đúng commit nó ghi → G2.1 cũ;
    * **không** commit thì cây bẩn → `pin_target` từ chối.

    Nên "G2.1 xanh" và "chốt được `closure_target_sha`" loại trừ nhau — một vòng
    không lối ra mà máy đóng gate tự tạo cho mình.

    Câu probe **thật sự** hỏi là "bằng chứng này có tả đúng **mã nguồn** hiện tại
    không". Một commit chỉ đụng `closure-evidence/` không đổi một dòng mã nào,
    nên câu trả lời vẫn là có. Nới đúng chừng ấy, không hơn: một commit đụng bất
    kỳ tệp nào **ngoài** thư mục ấy vẫn làm bằng chứng cũ.
    """

    def repo_with(self, *, extra: str = ""):
        """Một kho **duy nhất**: commit mã, ghi bằng chứng mang SHA ấy, rồi commit
        chính tệp bằng chứng — đúng trình tự sinh ra mâu thuẫn."""
        c = crit("GT.1", "aisef.control.closure:probe_suite_green",
                 evidence="closure-evidence/suite.json")
        repo = Repo(spec_of(c))
        self.addCleanup(repo.close)
        at = repo.head                     # mã nguồn ở đây
        repo.write_json("closure-evidence/suite.json",
                        {"commit": at, "exit": 0, "passed": 10, "failed": 0,
                         "errors": 0, "skipped": 0, "tree": "main"})
        if extra:
            repo.write(extra, "x\n")
        git(repo.root, "add", ".")
        git(repo.root, "commit", "-m", "record evidence")
        return repo, at

    def probe(self, repo):
        return CL.probe_suite_green(repo.ctx({"evidence": "closure-evidence/suite.json"}))

    def test_commit_chi_dung_bang_chung_thi_van_hien_hanh(self):
        repo, at = self.repo_with()
        self.assertNotEqual(repo.head, at, "HEAD phải đã đi qua commit ấy")
        p = self.probe(repo)
        self.assertIs(p.outcome, Outcome.PASSED, p.detail)

    def test_commit_dung_ma_nguon_thi_bang_chung_cu(self):
        """Phép kiểm âm — nới này không được che một thay đổi mã thật."""
        repo, _ = self.repo_with(extra="aisef/thay_doi.py")
        p = self.probe(repo)
        self.assertIs(p.outcome, Outcome.UNRUNNABLE)
        self.assertIn("re-record", p.detail)


class TestChotDichCungTuLamMinhCu(unittest.TestCase):
    """Anh em của lỗi 162, ở `closure_target_sha`.

    `pin_target` ghi HEAD vào `docs/closure-gate.json` — một tệp **không** nằm
    dưới `closure-evidence/`. Commit bản ghim ấy làm HEAD đi qua đúng commit vừa
    ghim, nên vế thứ hai của G1.0 (*HEAD vẫn là đích*) hỏng ngay sau khi chốt.
    Không commit thì cây bẩn, và `pin_target` từ chối cây bẩn — cùng vòng không
    lối ra mà 162 đã đo, chỉ đổi tệp.

    Nới cùng một chừng và không hơn: sổ sách đóng dự án (`closure-evidence/` và
    chính tệp tiêu chí) không phải mã nguồn, nên một commit chỉ đụng chúng không
    làm bằng chứng hay đích cũ. Một tệp mã đổi thì vẫn cũ.
    """

    def _repo(self, *, extra: str = ""):
        c = crit("G1.0", "aisef.control.closure:probe_closure_target",
                 evidence="closure-evidence/release.json")
        repo = Repo(spec_of(c))
        self.addCleanup(repo.close)
        git(repo.root, "tag", "v9.9.9")
        repo.write_json("closure-evidence/release.json", {"version": "9.9.9", "tag": "v9.9.9"})
        git(repo.root, "add", "."); git(repo.root, "commit", "-m", "release record")
        git(repo.root, "tag", "-f", "v9.9.9")          # tag the revision being certified
        CL.pin_target(repo.root)                        # ghi đích = HEAD
        if extra:
            repo.write(extra, "x\n")
        git(repo.root, "add", "."); git(repo.root, "commit", "-m", "pin the target")
        repo.spec = CL.load_spec(repo.root)      # pin_target wrote to disk
        return repo

    def probe(self, repo):
        return CL.probe_closure_target(
            repo.ctx({"evidence": "closure-evidence/release.json"}))

    def test_commit_cua_chinh_ban_ghim_khong_lam_dich_cu(self):
        repo = self._repo()
        p = self.probe(repo)
        self.assertIs(p.outcome, Outcome.PASSED, p.detail)

    def test_commit_dung_ma_nguon_thi_dich_cu(self):
        """Phép kiểm âm: mã đổi sau khi chốt thì G2–G5 nói về bản khác."""
        repo = self._repo(extra="aisef/thay_doi.py")
        p = self.probe(repo)
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("HEAD", p.detail)
