"""Bench V8 — mine/lint/validate/run/report/export trên **dự án giả** (kịch bản
TAP như `tests/test_improve.py`) + fixture lỗi kho thật.

Không cần `AISDLC_BENCH=1`: dự án giả chạy trong giây. Phần chạy unit thật của
kho (validate ×3 task lỗi 13) mới cần cờ; client thật không có ở đây.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from aisdlc.clients.base import ClientAdapter  # noqa: E402
from aisdlc.clients.stream import RunResult  # noqa: E402
from aisdlc.control.impact import is_test_path  # noqa: E402
from aisdlc.control.journal import Entry as JEntry  # noqa: E402
from aisdlc.control.journal import JournalStore  # noqa: E402
from aisdlc.harness.observe import AGENT_RUN, NOTE, TOOL_RUN, Event, EvidenceStore  # noqa: E402

from . import _mine as M  # noqa: E402
from . import _runner as R  # noqa: E402

T0 = 1_700_000_000
RUN_TESTS = ("#!/bin/sh\necho 'TAP version 13'\necho 'ok 1 - nền'\ncode=0\n"
             "for t in src/*.test.sh; do [ -f \"$t\" ] && { sh \"$t\" || code=1; }; done\nexit $code\n")
FEATURE_TEST = ("#!/bin/sh\nif [ -f src/feature.txt ]; then echo 'ok 2 - src/feature.test.sh > tính năng'; "
                "else echo 'not ok 2 - src/feature.test.sh > tính năng'; exit 1; fi\n")
# đổi kết cục mỗi lần chạy — đúng thứ `validate` ×3 phải bắt được
FLAKY_TEST = ("#!/bin/sh\nn=$(cat .n 2>/dev/null || echo 0); n=$((n+1)); echo $n > .n\n"
              "if [ $((n % 2)) -eq 0 ]; then echo 'ok 3 - src/flaky.test.sh > chập chờn'; "
              "else echo 'not ok 3 - src/flaky.test.sh > chập chờn'; exit 1; fi\n")
ALWAYS_RED = "#!/bin/sh\necho 'not ok 4 - src/do.test.sh > luôn đỏ'\nexit 1\n"
STORIES = ("STORY-01-01", "STORY-01-02", "STORY-01-03")


def sh(cwd, *cmd, ts=None):
    env = {**os.environ, "GIT_COMMITTER_DATE": f"{ts} +0000", "GIT_AUTHOR_DATE": f"{ts} +0000"} if ts else None
    return subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True, env=env).stdout.strip()


def commit(cwd, msg, ts):
    sh(cwd, "git", "add", "-A")
    sh(cwd, "git", "commit", "-qm", msg, ts=ts)
    return sh(cwd, "git", "rev-parse", "HEAD")


def story_md(sid: str) -> str:
    return (f"# {sid}: Tính năng\n\n## Tiêu chí chấp nhận\n\n1. [AC-{sid}-1] Given kho, When gọi, Then có.\n\n"
            "## Phạm vi được ghi\n\n- `src/feature.txt`\n- `src/feature.test.sh`\n\n"
            "## Phản hồi lượt trước\n\nLOI_NGUOI_RA_SOAT\n\n---\n\n_Sinh tự động từ `epics.md`._\n")


def make_e9(root: Path) -> dict:
    """Dự án giả kiểu e9: ba story done — 01-01 có baseline + nhật ký, 01-02 chỉ có
    `agent_run` (trước R9, mốc thời gian) với test không bao giờ xanh, 01-03 không tệp test."""
    sh(root, "git", "init", "-q", "-b", "main")
    sh(root, "git", "config", "user.email", "t@t")
    sh(root, "git", "config", "user.name", "t")
    (root / ".ai").mkdir()
    (root / ".ai" / "config.json").write_text(json.dumps({"tools.test": "sh run-tests.sh", "sandbox.use_docker": False}))
    (root / "run-tests.sh").write_text(RUN_TESTS)
    out = root / "_bmad-output"
    (out / "stories" / "EPIC-01").mkdir(parents=True)
    (out / "stories.index.json").write_text(json.dumps(
        {"stories": [{"id": s, "file": f"stories/EPIC-01/{s}.md"} for s in STORIES]}))
    for s in STORIES:
        (out / "stories" / "EPIC-01" / f"{s}.md").write_text(story_md(s), encoding="utf-8")
    (out / "sprint-status.json").write_text(json.dumps({"stories": {s: {"status": "done"} for s in STORIES}}))
    (root / "src").mkdir()
    shas = {"base": commit(root, "nền", T0)}
    for i, (sid, files) in enumerate((
        ("STORY-01-01", {"feature.txt": "có\n", "feature.test.sh": FEATURE_TEST, "flaky.test.sh": FLAKY_TEST}),
        ("STORY-01-02", {"do.test.sh": ALWAYS_RED}),
        ("STORY-01-03", {"khac.txt": "không test\n"}),
    ), 1):
        sh(root, "git", "checkout", "-qb", f"story/{sid}")
        for name, body in files.items():
            (root / "src" / name).write_text(body, encoding="utf-8")
        shas[sid] = commit(root, sid, T0 + 1000 * i)
        sh(root, "git", "checkout", "-q", "main")
        sh(root, "git", "merge", "-q", "--ff-only", f"story/{sid}")
    ev, jn = EvidenceStore(out), JournalStore(out)
    ev.tool_run("STORY-01-01", "test:baseline", ok=True, detail={"baseline": True, "parent": shas["base"]})
    ev.record("STORY-01-01", Event(kind=AGENT_RUN, name="STORY-01-01#1", cost_usd=2.5, duration_ms=1000,
                                   detail={"turns": 10}))
    jn.record("STORY-01-01", JEntry(step="candidate.frozen", attempt=1, data={"sha": shas["STORY-01-01"]}))
    # lượt đầu 01-02 bắt đầu sau commit 01-01, trước commit 01-02 → base theo thời gian = commit 01-01
    ev.record("STORY-01-02", Event(kind=AGENT_RUN, name="STORY-01-02#1", at=T0 + 1900, duration_ms=100_000,
                                   cost_usd=1.0, detail={"turns": 4}))
    ev.record("STORY-01-03", Event(kind=AGENT_RUN, name="STORY-01-03#1", at=T0 + 2900, duration_ms=100_000,
                                   cost_usd=1.0, detail={"turns": 4}))
    return shas


def patch_paths(text: str) -> list[str]:
    return [l.split(" b/", 1)[1] for l in text.splitlines() if l.startswith("diff --git ")]


class BenchCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        self.e9 = tmp / "e9"
        self.e9.mkdir()
        self.shas = make_e9(self.e9)
        self._env, self._keep = os.environ.get("AISDLC_BENCH_E9"), R.KEEP_DIR
        os.environ["AISDLC_BENCH_E9"] = str(self.e9)
        R.KEEP_DIR = tmp / "bench"
        self.tasks = {t.id: t for t in M.mine_stories(self.e9, tmp / "tasks")}

    def tearDown(self):
        R.KEEP_DIR = self._keep
        if self._env is None:
            os.environ.pop("AISDLC_BENCH_E9", None)
        else:
            os.environ["AISDLC_BENCH_E9"] = self._env
        self._tmp.cleanup()


class TestMineStories(BenchCase):
    def test_base_tu_baseline_ung_vien_tu_nhat_ky_tach_test_va_gold(self):
        t = self.tasks["STORY-01-01"]
        self.assertEqual((t.base, t.candidate, t.invalid_reason), (self.shas["base"], self.shas["STORY-01-01"], ""))
        self.assertEqual(patch_paths(t.read("tests.patch")), ["src/feature.test.sh", "src/flaky.test.sh"])
        self.assertEqual(patch_paths(t.read("gold.patch")), ["src/feature.txt"])
        self.assertEqual(t.write_scope, ["src/feature.txt", "src/feature.test.sh"])
        self.assertEqual(t.history, {"cost_usd": 2.5, "turns": 10})
        self.assertEqual((t.verify, t.tests_visible, t.too_big), ("sh run-tests.sh", False, False))

    def test_prompt_bo_phan_hoi_va_dong_sinh_tu_dong(self):
        p = self.tasks["STORY-01-01"].read("prompt.md")
        self.assertIn("[AC-STORY-01-01-1]", p)
        self.assertNotIn("LOI_NGUOI_RA_SOAT", p)
        self.assertNotIn("Sinh tự động", p)
        self.assertFalse(p.rstrip().endswith("---"))

    def test_khong_baseline_thi_base_theo_moc_thoi_gian_lu_dau(self):
        t = self.tasks["STORY-01-02"]
        self.assertEqual((t.base, t.candidate), (self.shas["STORY-01-01"], self.shas["STORY-01-02"]))

    def test_story_khong_tep_test_la_invalid_ngay_luc_dao(self):
        t = self.tasks["STORY-01-03"]
        self.assertIn("không có tệp test", t.invalid_reason)
        self.assertEqual((t.read("tests.patch"), t.read("gold.patch")), ("", ""))

    def test_task_json_doc_lai_bang_task(self):
        t = self.tasks["STORY-01-01"]
        self.assertEqual(M.Task.load(t.dir), t)

    def test_prompt_ro_thi_task_mang_ly_do_va_khong_co_prompt(self):
        md = self.e9 / "_bmad-output" / "stories" / "EPIC-01" / "STORY-01-01.md"
        md.write_text(md.read_text(encoding="utf-8").replace("Then có.", f"Then có (xem {self.shas['base']})."),
                      encoding="utf-8")
        t = {x.id: x for x in M.mine_stories(self.e9, Path(self._tmp.name) / "t2")}["STORY-01-01"]
        self.assertTrue(t.invalid_reason.startswith("prompt rò: SHA"), t.invalid_reason)
        self.assertEqual(t.read("prompt.md"), "")


class TestLint(unittest.TestCase):
    def test_sha_url_ma_story_sua_ten_commit(self):
        self.assertEqual(M.lint_prompt("Sửa cho xanh."), [])
        self.assertIn("SHA", M.lint_prompt("ở 765d846 sửa rồi")[0])
        self.assertIn("SHA", M.lint_prompt("a" * 40)[0])
        self.assertIn("URL", M.lint_prompt("xem https://x/y")[0])
        self.assertIn("STORY-RP-02", M.lint_prompt("của STORY-RP-02", allow=("STORY-RP-01",))[0])
        self.assertEqual(M.lint_prompt("AC-STORY-RP-01-1 xanh", allow=("STORY-RP-01",)), [])
        self.assertIn("tên commit", M.lint_prompt("fix(x): dọn rồi tạo thật", forbid=("fix(x): dọn rồi tạo thật",))[0])


class TestValidate(BenchCase):
    def test_f2p_p2p_va_test_chap_chon_bi_loai_neu_ten(self):
        t = R.validate(self.tasks["STORY-01-01"], runs=3)
        self.assertEqual(t.f2p_ids, ["src/feature.test.sh > tính năng"])
        self.assertEqual(t.p2p_ids, ["nền"])
        self.assertEqual(t.flaky_ids, ["src/flaky.test.sh > chập chờn"])
        self.assertEqual(t.validated, {"base_fail": True, "gold_pass": True, "runs": 3})
        self.assertEqual(t.invalid_reason, "")
        self.assertEqual(M.Task.load(t.dir).f2p_ids, t.f2p_ids, "kết quả validate phải nằm trên đĩa")

    def test_gold_con_do_la_invalid(self):
        t = R.validate(self.tasks["STORY-01-02"], runs=2)
        self.assertTrue(t.invalid_reason.startswith("base+test+gold còn đỏ: src/do.test.sh"), t.invalid_reason)
        self.assertFalse(t.validated["gold_pass"])

    def test_ban_chep_khong_lich_su_mot_ref_khong_tao_tac_luot_goc(self):
        ws = R.materialize(self.tasks["STORY-01-01"], R.KEEP_DIR / "ws")
        self.assertEqual(sh(ws, "git", "rev-list", "--all", "--count"), "1")
        self.assertEqual(sh(ws, "git", "for-each-ref", "--format=%(refname)"), "refs/heads/main")
        self.assertFalse((ws / "_bmad-output" / "evidence").exists())
        self.assertFalse((ws / "_bmad-output" / "sprint-status.json").exists())
        self.assertEqual(json.loads((ws / ".ai" / "config.json").read_text())["tools.test"], "sh run-tests.sh")
        self.assertFalse((ws / "src" / "feature.test.sh").exists(), "test ẩn không có trong bản chép cho agent")


class FakeClient(ClientAdapter):
    id = "claude"   # để `compile_for` biên dịch hook như hợp quy

    def __init__(self, act=None):
        self.act, self.calls = act, 0

    def available(self):
        return True

    def capabilities(self):
        return {}

    def run(self, spec):
        self.calls += 1
        if self.act:
            self.act(Path(spec.workdir))
        return RunResult(ok=True, text="xong", cost_usd=1.5, duration_ms=20, num_turns=7)


class TestRun(BenchCase):
    def setUp(self):
        super().setUp()
        # 2 lần là đủ để test chập chờn lộ ra và bị loại; 1 lần thì nó đỏ ở gold → task INVALID (đúng luật)
        self.task = R.validate(self.tasks["STORY-01-01"], runs=2)

    def _oracle(self, ws: Path):
        sh(ws, "git", "apply", str(self.task.dir / "gold.patch"))

    def _cheat(self, ws: Path):   # viết test luôn xanh, không làm tính năng
        (ws / "src").mkdir(exist_ok=True)
        (ws / "src" / "feature.test.sh").write_text("#!/bin/sh\necho 'ok 2 - src/feature.test.sh > tính năng'\n")

    def test_oracle_pass_va_bang_chung_mang_mode_bench(self):
        [r] = R.run(self.task, FakeClient(self._oracle), attempts=1)
        self.assertEqual((r.outcome, r.f2p_pass, r.f2p_total, r.p2p_red, r.cost_usd, r.turns),
                         (R.PASS, 1, 1, [], 1.5, 7))
        self.assertEqual((r.files, r.lines), (1, 1))
        ws = R.KEEP_DIR / "run" / "claude" / self.task.id / "a1"
        ev = EvidenceStore(ws / "_bmad-output").read(self.task.id)
        self.assertEqual(ev.of(NOTE, "mode")[0].detail["mode"], "bench")
        self.assertEqual([e.name for e in ev.of(AGENT_RUN)], ["STORY-01-01#1"])
        self.assertEqual(ev.last(TOOL_RUN, "test").detail["candidate"], r.candidate)
        self.assertFalse((ws / "_bmad-output" / "sprint-status.json").exists())
        self.assertEqual(sh(ws, "git", "rev-list", "--all", "--count"), "2", "nền + ứng viên, không ref gold")
        self.assertTrue((ws / ".claude" / "settings.json").is_file(), "hook biên dịch như hợp quy")

    def test_sua_test_bi_hoan_nguyen_roi_ap_test_an(self):
        [r] = R.run(self.task, FakeClient(self._cheat), attempts=1)
        self.assertEqual((r.outcome, r.f2p_pass), (R.FAIL, 0))
        ws = R.KEEP_DIR / "run" / "claude" / self.task.id / "a1"
        self.assertIn("if [ -f src/feature.txt ]", (ws / "src" / "feature.test.sh").read_text())

    def test_nop_fail_va_ba_luot_bao_cao_pass_at_k(self):
        rs = R.run(self.task, FakeClient(), attempts=3)
        self.assertEqual([r.outcome for r in rs], [R.FAIL] * 3)
        md = R.report(rs + R.run(self.task, FakeClient(self._oracle), attempts=1), list(self.tasks.values()))
        self.assertIn("| STORY-01-01 | claude | 0.25 | 1 | ✗ |", md)
        self.assertIn("**pass@1** 0.25", md)
        self.assertIn("flaky: src/flaky.test.sh > chập chờn", md)
        self.assertEqual(len(R.load_results()), 4)

    def test_task_invalid_khong_goi_client(self):
        c = FakeClient(self._oracle)
        rs = R.run(self.tasks["STORY-01-03"], c, attempts=2)
        self.assertEqual(([r.outcome for r in rs], c.calls), ([R.INVALID] * 2, 0))


class TestExport(BenchCase):
    def test_cau_truc_thu_muc_harbor(self):
        out = R.export(self.tasks["STORY-01-01"], R.KEEP_DIR / "harbor")
        for rel in ("instruction.md", "task.toml", "environment/Dockerfile", "environment/snapshot.tar",
                    "tests/test.sh", "tests/tests.patch", "solution/solve.sh", "solution/gold.patch"):
            self.assertTrue((out / rel).is_file(), rel)
        self.assertIn("FROM ", (out / "environment" / "Dockerfile").read_text())
        self.assertIn("sh run-tests.sh", (out / "tests" / "test.sh").read_text())
        self.assertIn("reward.txt", (out / "tests" / "test.sh").read_text())
        self.assertNotIn(self.shas["base"], (out / "instruction.md").read_text())


def _has_commit(sha: str) -> bool:
    return subprocess.run(["git", "cat-file", "-e", sha + "^{commit}"], cwd=ROOT, capture_output=True).returncode == 0


@unittest.skipUnless(_has_commit("765d846"), "cần lịch sử kho thật (không phải bản clone nông)")
class TestMineBugsThat(unittest.TestCase):
    """Fixture ba lỗi thật (13, 20, 25) — đào từ lịch sử kho, không cần agent."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        picked = tuple(b for b in M.BUGS if b.id in ("13", "20", "25"))
        self.tasks = {t.id: t for t in M.mine_bugs(ROOT, Path(self._tmp.name), picked)}

    def tearDown(self):
        self._tmp.cleanup()

    def test_tach_nguon_test_va_prompt_sach(self):
        self.assertEqual(sorted(self.tasks), ["bug-13", "bug-20", "bug-25"])
        for t in self.tasks.values():
            with self.subTest(task=t.id):
                self.assertEqual(t.invalid_reason, "")
                self.assertTrue(all(is_test_path(p) for p in patch_paths(t.read("tests.patch"))))
                gold = patch_paths(t.read("gold.patch"))
                self.assertTrue(gold and all(p.startswith("aisdlc/") for p in gold), gold)
                self.assertEqual(sh(ROOT, "git", "rev-parse", t.fix_commit + "^"), t.base)
                subject = sh(ROOT, "git", "log", "-1", "--format=%s", t.fix_commit)
                self.assertEqual(M.lint_prompt(t.read("prompt.md"), forbid=(subject,)), [])
                self.assertTrue(t.tests_visible)
        self.assertEqual(self.tasks["bug-13"].verify, "python3 -m unittest -v tests.test_worktree")

    @unittest.skipUnless(R.ENABLED, "AISDLC_BENCH=1: chạy unit thật của kho ×3 ở hai trạng thái")
    def test_validate_loi_13_do_o_base_xanh_o_gold(self):
        keep, R.KEEP_DIR = R.KEEP_DIR, Path(self._tmp.name) / "bench"
        try:
            t = R.validate(self.tasks["bug-13"], runs=3)
        finally:
            R.KEEP_DIR = keep
        self.assertEqual(t.invalid_reason, "")
        self.assertTrue(any(i.endswith("test_stray_dir_is_not_a_worktree") for i in t.f2p_ids), t.f2p_ids)
        self.assertEqual(t.validated, {"base_fail": True, "gold_pass": True, "runs": 3})


class TestTaskDaCommit(unittest.TestCase):
    """`tests/bench/tasks/` là mã của kho: task hợp lệ phải đủ patch, prompt sạch."""

    def test_task_loi_kho_du_va_sach(self):
        tasks = M.load_tasks(M.TASKS_DIR)
        self.assertGreaterEqual(len(tasks), 15)
        for t in tasks:
            with self.subTest(task=t.id):
                self.assertEqual(t.source, "bug")
                if t.invalid_reason:
                    continue
                self.assertTrue(t.read("tests.patch") and t.read("gold.patch"))
                self.assertEqual(M.lint_prompt(t.read("prompt.md")), [])
                self.assertTrue(t.verify.startswith("python3 -m unittest -v tests."))
