"""Vòng đời một story — thử lại, chặn, và phân biệt hai loại thất bại.

Client giả đóng vai agent: nó "viết code" bằng cách ghi file trong phạm vi
(hoặc cố tình ra ngoài), và trả lời rà soát theo kịch bản. Nhờ vậy kiểm
được đúng phần logic điều phối — cái quyết định story xong, thử lại hay bị
chặn — mà không phụ thuộc model.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisdlc.clients.base import Capability, ClientAdapter, RunSpec, Support  # noqa: E402
from aisdlc.clients.stream import RunResult  # noqa: E402
from aisdlc.config import DEFAULTS, Config  # noqa: E402
from aisdlc.control.normalize import Story, parse_architecture_file  # noqa: E402
from aisdlc.harness.guardrails import ENV_STORY_ID, ENV_WRITE_SCOPE  # noqa: E402
from aisdlc.harness.observe import AGENT_RUN, EvidenceStore  # noqa: E402
from aisdlc.phases.implement import (  # noqa: E402
    blocking_findings,
    build_context,
    implement_story,
    is_infrastructure_error,
)

FIX = ROOT / "tests" / "fixtures" / "bmad"


class ScriptedClient(ClientAdapter):
    """Agent giả: mỗi lượt viết code theo kịch bản, rồi rà soát theo kịch bản."""

    id = "scripted"

    def __init__(self, *, writes=("src/a.py",), review="không có mục chặn",
                 fail_first=0, fail_error="api_error"):
        self.writes = list(writes)
        self.review = review
        self.review_envs: list[dict] = []
        self.fail_first = fail_first
        self.fail_error = fail_error
        self.calls: list[str] = []
        self.envs: list[dict] = []

    def available(self) -> bool:
        return True

    def capabilities(self):
        return {c: Support.NATIVE for c in Capability}

    def run(self, spec: RunSpec) -> RunResult:
        is_review = "Rà soát" in spec.prompt
        self.calls.append("review" if is_review else "develop")
        (self.review_envs if is_review else self.envs).append(dict(spec.env))

        if self.fail_first > 0 and not is_review:
            self.fail_first -= 1
            return RunResult(ok=False, error=self.fail_error, cost_usd=0.2)

        if is_review:
            return RunResult(ok=True, text=self.review, cost_usd=0.3)

        for rel in self.writes:
            path = Path(spec.workdir) / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            # File test thì viết như một file test — nội dung quyết định
            # phép kiểm "test giả" có bắt được hay không.
            body = "def test_x():\n    pass\n" if "test_" in path.name else "x = 1\n"
            path.write_text(body, encoding="utf-8")
        return RunResult(ok=True, text="xong", cost_usd=1.0)


class ImplementTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.project, check=True)
        self.artifacts = self.project / "_bmad-output"
        self.artifacts.mkdir()
        self.story = Story(
            id="STORY-01-01",
            epic_id="EPIC-01",
            title="Tạo ghi chú",
            acceptance_criteria=["ghi chú mới xuất hiện trong danh sách"],
            covers=["FR-1"],
            write_scope=["src"],
        )

    def tearDown(self):
        self._tmp.cleanup()

    def config(self, **over):
        return Config({
            **DEFAULTS,
            "tools.test": "true",
            "tools.lint": "true",
            "run.max_retries": 1,
            **over,
        })

    def implement(self, client, **kw):
        return implement_story(
            self.story, project=self.project, artifact_root=self.artifacts,
            client=client, config=kw.pop("config", self.config()), **kw,
        )


class TestHappyPath(ImplementTestCase):
    def test_story_passes_in_one_attempt(self):
        out = self.implement(ScriptedClient())
        self.assertTrue(out.done, out.summary())
        self.assertEqual(len(out.attempts), 1)

    def test_developer_then_reviewer(self):
        c = ScriptedClient()
        self.implement(c)
        self.assertEqual(c.calls, ["develop", "review"])

    def test_reviewer_gets_scope_but_not_story_id(self):
        """Người rà soát cần **phạm vi**, không cần **mã story**.

        Thiếu phạm vi: `diff-scope` rơi vào nhánh "chưa khai phạm vi mà
        đã đổi file" và chặn mọi lệnh Bash — người rà soát đốt hết lượt
        để vật lộn với guard thay vì đọc code. Có mã story: guard
        `completion` chặn nó *dừng* khi test đang đỏ, đúng lúc nó có
        nhiều thứ đáng báo cáo nhất.
        """
        c = ScriptedClient()
        self.implement(c)
        self.assertEqual(c.review_envs[0].get(ENV_WRITE_SCOPE), "src")
        self.assertNotIn(ENV_STORY_ID, c.review_envs[0])

    def test_guard_context_reaches_the_client_environment(self):
        """Guard chạy trong hook — tiến trình con của client. Không truyền
        qua môi trường thì nó không biết phạm vi và sẽ chặn mọi thứ."""
        c = ScriptedClient()
        self.implement(c)
        self.assertEqual(c.envs[0][ENV_WRITE_SCOPE], "src")
        self.assertEqual(c.envs[0][ENV_STORY_ID], "STORY-01-01")

    def test_cost_recorded_per_run(self):
        out = self.implement(ScriptedClient())
        runs = EvidenceStore(self.artifacts).read("STORY-01-01").of(AGENT_RUN)
        self.assertEqual(len(runs), 2)          # viết + rà soát
        self.assertAlmostEqual(out.cost_usd, 1.0)  # chỉ lượt viết tính vào attempt


class TestRetry(ImplementTestCase):
    def test_blocking_review_triggers_a_retry_with_feedback(self):
        c = ScriptedClient(review="[chặn] src/a.py:1 — mất dữ liệu khi lưu")
        out = self.implement(c)
        self.assertFalse(out.done)
        self.assertEqual(out.quality_attempts, 2)   # lần đầu + 1 lần thử lại
        self.assertIn("đã thử", out.blocked_reason)

    def test_out_of_scope_write_fails_the_gate(self):
        c = ScriptedClient(writes=("src/a.py", "ngoai/pham-vi.py"))
        out = self.implement(c)
        self.assertFalse(out.done)
        self.assertIn("phạm vi", out.summary())

    def test_feedback_reaches_the_next_attempt(self):
        class Recorder(ScriptedClient):
            prompts: list = []

            def run(self, spec):
                if "Rà soát" not in spec.prompt:
                    Recorder.prompts.append(spec.prompt)
                return super().run(spec)

        Recorder.prompts = []
        self.implement(Recorder(review="[chặn] src/a.py:1 — sai"))
        self.assertGreaterEqual(len(Recorder.prompts), 2)
        self.assertIn("Lượt trước chưa đạt", Recorder.prompts[1])
        self.assertIn("sai", Recorder.prompts[1])


class TestFailureKinds(ImplementTestCase):
    def test_infrastructure_error_does_not_burn_a_retry(self):
        """Mất kết nối không phải agent làm sai. Gộp hai loại lại thì mạng
        chập chờn sẽ chặn oan story."""
        c = ScriptedClient(fail_first=1, fail_error="api_error")
        out = self.implement(c)
        self.assertTrue(out.done, out.summary())
        self.assertEqual(out.quality_attempts, 1)
        self.assertTrue(out.attempts[0].infra)

    def test_repeated_infrastructure_errors_eventually_block(self):
        out = self.implement(ScriptedClient(fail_first=99, fail_error="api_error"))
        self.assertFalse(out.done)
        self.assertIn("hạ tầng", out.blocked_reason)

    def test_classification(self):
        for err in ("api_error", "overloaded", "quá 1800s", "Connection lost"):
            self.assertTrue(is_infrastructure_error(err), err)
        self.assertFalse(is_infrastructure_error("test đỏ"))

    def test_review_that_cannot_run_is_not_clean(self):
        class NoReview(ScriptedClient):
            def run(self, spec):
                if "Rà soát" in spec.prompt:
                    return RunResult(ok=False, error="hết giờ")
                return super().run(spec)

        out = self.implement(NoReview())
        self.assertFalse(out.done)


class TestFakeTestDetection(ImplementTestCase):
    def test_story_that_writes_an_assertionless_test_is_blocked(self):
        """Mốc demo 7: đẩy một story có test giả → cổng chặn, nêu đúng lý do."""
        out = self.implement(ScriptedClient(writes=("src/tests/test_a.py",)))
        self.assertFalse(out.done)
        self.assertIn("test thật", out.summary())


class TestContext(ImplementTestCase):
    def test_architecture_rules_selected_by_requirement(self):
        arch = parse_architecture_file(FIX / "architecture.md")
        ctx = build_context(
            self.story, project=self.project, artifact_root=self.artifacts,
            architecture=arch, contract=None, config=self.config(),
        )
        self.assertIn("AR-1", ctx["architecture_rules"])     # ràng buộc FR-1
        self.assertNotIn("AR-9", ctx["architecture_rules"])  # xếp hạng tìm kiếm

    def test_story_file_is_used_when_present(self):
        path = self.artifacts / "stories" / "EPIC-01" / "STORY-01-01.md"
        path.parent.mkdir(parents=True)
        path.write_text("# hợp đồng đầy đủ của story\n", encoding="utf-8")
        ctx = build_context(
            self.story, project=self.project, artifact_root=self.artifacts,
            architecture=None, contract=None, config=self.config(),
        )
        self.assertIn("hợp đồng đầy đủ", ctx["story_contract"])

    def test_story_without_screens_gets_no_mockup(self):
        ctx = build_context(
            self.story, project=self.project, artifact_root=self.artifacts,
            architecture=None, contract=None, config=self.config(),
        )
        self.assertIn("không dựng màn hình nào", ctx["mockup_section"])


class TestFindings(unittest.TestCase):
    def test_only_blocking_items_count(self):
        text = (
            "- [chặn] src/a.py:10 — mất dữ liệu\n"
            "- [nên sửa] src/b.py:2 — tên biến khó hiểu\n"
            "[góp ý] có thể gộp hai hàm\n"
        )
        found = blocking_findings(text)
        self.assertEqual(len(found), 1)
        self.assertIn("mất dữ liệu", found[0])

    def test_clean_review(self):
        self.assertEqual(blocking_findings("không có mục chặn"), [])

    def test_empty_text(self):
        self.assertEqual(blocking_findings(""), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
