"""Sổ prompt + định tuyến vai.

Prompt là mã nguồn: có phiên bản, kiểm được bằng test, và **thiếu biến là
lỗi**. Chỗ trống không được điền sẽ lặng lẽ thành khoảng trắng, và agent
làm việc với hướng dẫn khuyết mà không ai biết.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.config import DEFAULTS, Config  # noqa: E402
from aisef.harness.prompts import (  # noqa: E402
    PROMPT_DIR,
    Prompt,
    PromptError,
    load_catalog,
)
from aisef.harness.routing import (  # noqa: E402
    DEVELOPER,
    REVIEWER,
    ROLES,
    Routing,
    RoutingError,
    build_spec,
    role_of,
)
from aisef.harness.sandbox import Level  # noqa: E402

STORY_CTX = {
    "story_id": "STORY-01-01",
    "story_title": "Tạo ghi chú",
    "story_contract": "tiêu chí…",
    "architecture_rules": "AR-1 …",
    "write_scope": "src/notes/",
    "mockup_section": "màn hình danh-sach",
    "tools": "- aisef tool test",
    "index": "- STORY-01-01 · done · abc1234 · V3 G0 R0 · evidence/STORY-01-01.jsonl",
    "preservation": "- `AC-STORY-01-00-1` · STORY-01-00 · test `src/x.test.ts > AC-STORY-01-00-1`",
    "validation": "- test bảo toàn: `src/x.test.ts > AC-STORY-01-00-1`",
    "skills": "- `x` — dùng khi: y",
    "diff_summary": "3 file đổi",
    "impact": "_Chưa có phân tích ảnh hưởng_",
    "repo_map": "## Code map around write scope — static hint, not ground truth\n\n`src/a.ts`",
    "blast_radius": "_(greenfield — không có blast radius)_",
    "prior_review": "_(first review of this story — nothing said before)_",
}


class TestCatalog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_catalog()

    def test_every_role_has_its_prompt(self):
        for role in ROLES.values():
            self.assertIn(role.prompt, self.catalog, role.id)

    def test_prompts_are_versioned(self):
        for prompt in self.catalog.prompts.values():
            self.assertGreaterEqual(prompt.version, 1)
            self.assertIn("@", prompt.stamp)

    def test_unknown_prompt_names_the_alternatives(self):
        with self.assertRaises(PromptError) as e:
            self.catalog.get("khong-co")
        self.assertIn("story-implement", str(e.exception))

    def test_frontmatter_not_left_in_the_body(self):
        for prompt in self.catalog.prompts.values():
            self.assertNotIn("version:", prompt.body.splitlines()[0])


class TestRender(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog()

    def test_slots_filled(self):
        text = self.catalog.get("story-implement").render(STORY_CTX)
        self.assertIn("STORY-01-01", text)
        self.assertIn("src/notes/", text)
        self.assertNotIn("{{", text)

    def test_missing_variable_raises(self):
        ctx = dict(STORY_CTX)
        del ctx["write_scope"]
        with self.assertRaises(PromptError) as e:
            self.catalog.get("story-implement").render(ctx)
        self.assertIn("write_scope", str(e.exception))

    def test_blank_variable_raises(self):
        """Biến rỗng nguy hiểm hơn biến thiếu: prompt vẫn dựng được, chỉ là
        mất hẳn một mục hướng dẫn."""
        ctx = {**STORY_CTX, "architecture_rules": "   "}
        with self.assertRaises(PromptError):
            self.catalog.get("story-implement").render(ctx)

    def test_blank_allowed_when_declared(self):
        ctx = {**STORY_CTX, "mockup_section": ""}
        text = self.catalog.get("story-implement").render(
            ctx, allow_empty=("mockup_section",)
        )
        self.assertIn("STORY-01-01", text)

    def test_braces_in_body_are_left_alone(self):
        """Thân prompt có ngoặc nhọn thật (JSON, mã nguồn) — `str.format`
        sẽ vấp, nên cú pháp chỗ trống phải là {{ }}."""
        p = Prompt(name="x", version=1, role="r", body='{"a": 1} và {{ ten }}')
        self.assertEqual(p.render({"ten": "N"}), '{"a": 1} và N')

    def test_load_from_a_directory_without_prompts(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(load_catalog(tmp).prompts, {})


class TestPromptContent(unittest.TestCase):
    """Vài điều prompt **phải** nói — thiếu là hỏng theo cách không thấy ngay."""

    def setUp(self):
        self.catalog = load_catalog()

    def test_developer_prompt_forbids_working_around_scope(self):
        body = self.catalog.get("story-implement").body
        self.assertIn("workaround", body)
        self.assertIn("stop", body)

    def test_developer_prompt_demands_red_before_green(self):
        body = self.catalog.get("story-implement").body
        self.assertIn("RED", body)
        self.assertIn("first", body)

    def test_developer_prompt_says_evidence_beats_claims(self):
        self.assertIn("evidence", self.catalog.get("story-implement").body)

    def test_reviewer_prompt_forbids_editing(self):
        self.assertIn("Do not fix code", self.catalog.get("story-review").body)

    def test_reviewer_prompt_refuses_padding(self):
        """Bắt phải có phát hiện sẽ đẻ ra phát hiện giả."""
        self.assertIn("not manufacture findings", self.catalog.get("story-review").body)

    def test_nguoi_ra_soat_thay_ca_ke_hoach_va_duoc_dan_khong_cham_luot_khac(self):
        """Lỗi 58. Story "vỏ ứng dụng" có **một** tiêu chí — cấu trúc tài liệu —
        bị chặn ba mục vì chưa có submit handler, chưa đọc localStorage, chưa
        lưu: đúng ba story sau nó. Người rà soát chấm cả PRD, nên story đầu
        tiên của mọi dự án bị chặn vì không phải story cuối cùng."""
        prompt = self.catalog.get("story-review")
        self.assertIn("index", prompt.slots)
        body = prompt.body
        self.assertIn("Behaviour another story owns", body)
        self.assertIn("acceptance criteria are the", body)


class TestSlotBanDoMa(unittest.TestCase):
    """ADR-005 V7: slot `repo_map` ở cả ba vai; knob 0 → slot rỗng và prompt
    **không** có mục (tiêu đề nằm trong slot, không nằm trong prompt)."""

    def setUp(self):
        self.catalog = load_catalog()

    def test_ca_ba_prompt_co_slot(self):
        for name in ("story-implement", "story-review", "story-security-review"):
            self.assertIn("repo_map", self.catalog.get(name).slots, name)

    def test_slot_rong_thi_khong_co_muc(self):
        from aisef.phases.implement import ALLOW_EMPTY
        text = self.catalog.get("story-implement").render({**STORY_CTX, "repo_map": ""}, allow_empty=ALLOW_EMPTY)
        self.assertNotIn("Code map", text)
        self.assertNotIn("{{", text)

    def test_slot_co_thi_muc_hien(self):
        text = self.catalog.get("story-review").render(STORY_CTX)
        self.assertIn("## Code map around write scope", text)


class TestRouting(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog()
        self.cfg = Config(dict(DEFAULTS))

    def spec(self, role: str, **kw):
        prompt = self.catalog.get(ROLES[role].prompt)
        return build_spec(role, prompt, STORY_CTX, workdir=Path("."), config=self.cfg, **kw)

    def test_reviewer_may_not_resume_the_developer_session(self):
        """Rà lại trong cùng phiên chỉ là hỏi lại chính niềm tin đã có."""
        with self.assertRaises(RoutingError):
            self.spec(REVIEWER, session_id="phien-cua-nguoi-viet")

    def test_developer_may_resume(self):
        self.assertEqual(self.spec(DEVELOPER, session_id="abc").session_id, "abc")

    def test_reviewer_cannot_write(self):
        for tool in ("Write", "Edit"):
            self.assertIn(tool, self.spec(REVIEWER).disallowed_tools)

    def test_reviewer_runs_read_only(self):
        self.assertIs(role_of(REVIEWER).level, Level.READ_ONLY)

    def test_wrong_prompt_for_the_role_is_refused(self):
        with self.assertRaises(RoutingError):
            build_spec(REVIEWER, self.catalog.get("story-implement"), STORY_CTX,
                       workdir=Path("."), config=self.cfg)

    def test_unknown_role(self):
        with self.assertRaises(RoutingError):
            build_spec("khong-co", self.catalog.get("story-review"), STORY_CTX,
                       workdir=Path("."), config=self.cfg)

    def test_model_comes_from_config(self):
        cfg = Config({**DEFAULTS, "route.reviewer_model": "opus"})
        prompt = self.catalog.get("story-review")
        spec = build_spec(REVIEWER, prompt, STORY_CTX, workdir=Path("."), config=cfg)
        self.assertEqual(spec.model, "opus")

    def test_no_model_configured_leaves_client_default(self):
        self.assertEqual(self.spec(DEVELOPER).model, "")

    def test_routing_without_config(self):
        self.assertEqual(Routing.from_config(None).model_for(DEVELOPER), "")


class TestPromptFilesOnDisk(unittest.TestCase):
    def test_prompt_dir_shipped_with_the_package(self):
        self.assertTrue(PROMPT_DIR.is_dir())
        self.assertTrue(list(PROMPT_DIR.glob("*.md")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
