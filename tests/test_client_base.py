from __future__ import annotations
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.clients.base import (
    Capability, ClientAdapter, Support, RunSpec, GIT_NO_CREDENTIALS, child_env,
)
from aisef.clients.stream import RunResult


class TestSupport(unittest.TestCase):

    def test_native_blocks(self):
        self.assertTrue(Support.NATIVE.blocks_at_source)

    def test_emulated_blocks(self):
        self.assertTrue(Support.EMULATED.blocks_at_source)

    def test_post_hoc_does_not_block(self):
        self.assertFalse(Support.POST_HOC.blocks_at_source)

    def test_unsupported_does_not_block(self):
        self.assertFalse(Support.UNSUPPORTED.blocks_at_source)


class TestChildEnv(unittest.TestCase):

    CLEAN_ENV = {
        "PATH": "/usr/bin",
        "HOME": "/home/test",
        "ANTHROPIC_API_KEY": "sk-test",
        "SECRET_STUFF": "nope",
        "LC_ALL": "en_US.UTF-8",
    }

    @patch.dict("os.environ", CLEAN_ENV, clear=True)
    def test_keeps_path(self):
        env = child_env({})
        self.assertEqual(env["PATH"], "/usr/bin")

    @patch.dict("os.environ", CLEAN_ENV, clear=True)
    def test_anthropic_key_only_for_the_client_that_pays_with_it(self):
        """Lỗi 101: khoá đi kèm nhà cung cấp nó trả tiền cho. Cho mọi client
        thì một phiên định chạy qua router của dự án lại xác thực bằng khoá
        Anthropic của máy — client đọc được nó **đè lên** đăng nhập của chính
        nó, và người dùng trả tiền cho tài khoản khác mà không ai nói gì."""
        self.assertNotIn("ANTHROPIC_API_KEY", child_env({}))
        self.assertEqual(
            child_env({}, allow_prefixes=("ANTHROPIC_",))["ANTHROPIC_API_KEY"],
            "sk-test")

    @patch.dict("os.environ", CLEAN_ENV, clear=True)
    def test_adapter_prefixes_are_what_the_clients_declare(self):
        from aisef.clients.claude_code import ClaudeCodeAdapter
        from aisef.clients.opencode import OpenCodeAdapter
        self.assertEqual(ClaudeCodeAdapter.env_prefixes, ("ANTHROPIC_",))
        self.assertEqual(OpenCodeAdapter.env_prefixes, ())

    @patch.dict("os.environ", CLEAN_ENV, clear=True)
    def test_drops_unknown(self):
        env = child_env({})
        self.assertNotIn("SECRET_STUFF", env)

    @patch.dict("os.environ", CLEAN_ENV, clear=True)
    def test_adds_git_no_credentials(self):
        env = child_env({})
        for k, v in GIT_NO_CREDENTIALS.items():
            self.assertEqual(env[k], v)

    @patch.dict("os.environ", CLEAN_ENV, clear=True)
    def test_spec_env_overlays(self):
        env = child_env({"PATH": "/custom", "NEW": "val"})
        self.assertEqual(env["PATH"], "/custom")
        self.assertEqual(env["NEW"], "val")

    @patch.dict("os.environ", CLEAN_ENV, clear=True)
    def test_empty_prefix_filtered(self):
        env = child_env({}, allow_prefixes=("", "MY_"))
        self.assertNotIn("SECRET_STUFF", env)

    @patch.dict("os.environ", {**CLEAN_ENV, "MY_VAR": "yes"}, clear=True)
    def test_allow_prefixes(self):
        env = child_env({}, allow_prefixes=("MY_",))
        self.assertEqual(env["MY_VAR"], "yes")

    @patch.dict("os.environ", CLEAN_ENV, clear=True)
    def test_keeps_lc_prefix(self):
        env = child_env({})
        self.assertEqual(env["LC_ALL"], "en_US.UTF-8")


class TestRunSpec(unittest.TestCase):

    def test_defaults(self):
        spec = RunSpec(prompt="hi", workdir=Path("/tmp"))
        self.assertEqual(spec.system_prompt, "")
        self.assertEqual(spec.model, "")
        self.assertEqual(spec.max_turns, 0)
        self.assertEqual(spec.timeout_seconds, 1800)
        self.assertEqual(spec.allowed_tools, [])
        self.assertEqual(spec.disallowed_tools, [])
        self.assertEqual(spec.extra_dirs, [])
        self.assertIsNone(spec.settings_file)
        self.assertEqual(spec.session_id, "")
        self.assertEqual(spec.env, {})
        self.assertEqual(spec.env_allow, [])


class _Stub(ClientAdapter):
    id = "stub"

    def __init__(self, caps: dict[Capability, Support] | None = None):
        self._caps = caps or {}

    def available(self) -> bool:
        return True

    def capabilities(self) -> dict[Capability, Support]:
        return self._caps

    def run(self, spec: RunSpec) -> RunResult:
        raise NotImplementedError


class TestClientAdapter(unittest.TestCase):

    def test_supports_known(self):
        s = _Stub({Capability.HEADLESS: Support.NATIVE})
        self.assertIs(s.supports(Capability.HEADLESS), Support.NATIVE)

    def test_supports_unknown_returns_unsupported(self):
        s = _Stub({})
        self.assertIs(s.supports(Capability.HEADLESS), Support.UNSUPPORTED)

    def test_guards_block_native(self):
        s = _Stub({Capability.PRE_TOOL_GUARD: Support.NATIVE})
        self.assertTrue(s.guards_block_at_source())

    def test_guards_block_post_hoc(self):
        s = _Stub({Capability.PRE_TOOL_GUARD: Support.POST_HOC})
        self.assertFalse(s.guards_block_at_source())

    def test_degradations_empty_when_all_native(self):
        caps = {Capability.HEADLESS: Support.NATIVE, Capability.SUBAGENT: Support.NATIVE}
        self.assertEqual(_Stub(caps).degradations(), [])

    def test_degradations_lists_non_native(self):
        caps = {
            Capability.HEADLESS: Support.NATIVE,
            Capability.TOOL_ALLOWLIST: Support.POST_HOC,
            Capability.SUBAGENT: Support.EMULATED,
        }
        d = _Stub(caps).degradations()
        self.assertEqual(len(d), 2)
        self.assertIn("subagent: emulated", d)
        self.assertIn("tool_allowlist: post_hoc", d)


if __name__ == "__main__":
    unittest.main()


class TestLoi401NeuDuongDiThat(unittest.TestCase):
    """Dòng phân loại 160 — một 401 phải nêu **client và model** đã hỏng.

    Đo trên chính phiên này (2026-09-14, corpus marks-cli): sáu phiên trước chạy
    `client=opencode model=9router/mycombo`; một lượt gọi `aisef run` thiếu
    `--client opencode` nên rơi về mặc định `claude`, và thông báo trả về là
    *"authenticated with ANTHROPIC_API_KEY … outranks a `claude.ai` login"*.
    Câu ấy **đúng** cho phiên ấy, nhưng nó chỉ nói về nguồn thông tin xác thực,
    không nói **đường nào** đã đi — nên người đọc (tôi) kết luận rằng khoá của
    dự án đã hết hạn, trong khi dự án không hề dùng đường Anthropic: cấu hình
    OpenCode còn đặt `disabled_providers: ["anthropic"]`.

    Một dự án cấu hình nhiều client thì "nguồn xác thực" không quy được lỗi về
    đường đi. Tên client và model thì quy được, trong đúng một dòng.
    """

    def test_hint_neu_ten_client_va_model(self):
        from aisef.clients.base import auth_hint
        h = auth_hint({"ANTHROPIC_API_KEY": "sk-secret-value-123"},
                      client="claude", model="claude-opus-5")
        self.assertIn("claude", h)
        self.assertIn("claude-opus-5", h)
        self.assertIn("ANTHROPIC_API_KEY", h)
        # Tên biến thì nêu, **giá trị** thì không bao giờ.
        self.assertNotIn("sk-secret-value-123", h)

    def test_duong_khong_phai_anthropic_khong_bi_do_cho_bien_anthropic(self):
        """Một 401 thật từ 9router không được đọc thành "khoá Anthropic sai"."""
        from aisef.clients.base import auth_hint
        h = auth_hint({}, client="opencode", model="9router/mycombo")
        self.assertIn("opencode", h)
        self.assertIn("9router/mycombo", h)
        self.assertNotIn("ANTHROPIC", h.upper())

    def test_bien_anthropic_co_mat_nhung_client_khong_doc_no(self):
        """Biến có trong shell **không** phải bằng chứng nó được dùng: opencode
        không đọc `ANTHROPIC_API_KEY`, nên nêu tên nó ở đây là chỉ sai chỗ."""
        from aisef.clients.base import auth_hint
        h = auth_hint({"ANTHROPIC_API_KEY": "sk-secret-value-123"},
                      client="opencode", model="9router/mycombo")
        self.assertNotIn("ANTHROPIC_API_KEY", h)
        self.assertIn("opencode", h)

    def test_khong_biet_client_thi_van_chay_duoc(self):
        from aisef.clients.base import auth_hint
        self.assertTrue(auth_hint({}))


class TestTuChoiXacThucLaHaTang(unittest.TestCase):
    """Dòng phân loại 161 — nhà cung cấp **từ chối** phiên thì không tính một
    lượt chất lượng.

    `implement._chay_mot_luot` nói thẳng nguyên tắc ngay dưới chỗ này: *"Infra
    statuses still return here — the provider cut the session, the retry costs
    no quality attempt, and the next one grades this tree."* Một 401 đúng là
    thế: cây không bị đụng (`moved_tree: false`), không có gì để chấm. Nhưng
    `auth` không nằm trong `INFRA_STATUSES`, nên nó tiêu một lượt chất lượng —
    và story mất ngân sách vì một việc người viết mã không dự phần, đúng cái
    hình lỗi 130 đã đo với `max_turns`.
    """

    def test_auth_van_khong_phai_infra_status(self):
        """`auth` **không** được thêm vào `INFRA_STATUSES`, và đó là có chủ ý đã
        đo: một thông tin xác thực bị từ chối không phải sự cố thoáng qua, nên
        thử lại tiêu ngân sách hạ tầng vào một thất bại lặp lại y hệt (đo
        2026-09-12: 176 s mỗi lượt, $0, ba lượt, không học được gì)."""
        from aisef.clients.stream import INFRA_STATUSES
        self.assertNotIn("auth", INFRA_STATUSES)
        for s in ("timeout", "infra", "rate_limit"):
            self.assertIn(s, INFRA_STATUSES)
        self.assertNotIn("max_turns", INFRA_STATUSES)

    def test_luot_auth_khong_tinh_vao_ngan_sach_chat_luong(self):
        """Nhưng ý đồ ấy **không** đạt được bằng việc loại khỏi `INFRA_STATUSES`:
        làm thế chỉ chuyển chi phí sang ngân sách **chất lượng**, và lượt sau vẫn
        chạy. Đo trên marks-cli 2026-09-14: `attempt=1 FAIL … attempt=2 START`.

        Cách đúng là đúng thành ngữ đã có trong tệp này cho "không phải lỗi người
        viết mã **và** thử lại là vô ích": `infra=True` + `fatal=True`."""
        from aisef.phases.implement import Attempt, StoryOutcome
        a = Attempt(number=1)
        a.infra, a.fatal, a.error = True, True, "401"
        out = StoryOutcome(story_id="S-01")
        out.attempts.append(a)
        self.assertEqual(out.quality_attempts, 0,
                         "một phiên bị nhà cung cấp từ chối không chấm gì, nên "
                         "không được tiêu một lượt chất lượng")

    def test_luot_hong_binh_thuong_van_tinh(self):
        """Phép kiểm âm: một lượt bị chấm trượt vẫn tiêu ngân sách chất lượng."""
        from aisef.phases.implement import Attempt, StoryOutcome
        a = Attempt(number=1)
        a.error = "gate failed"
        out = StoryOutcome(story_id="S-01")
        out.attempts.append(a)
        self.assertEqual(out.quality_attempts, 1)
