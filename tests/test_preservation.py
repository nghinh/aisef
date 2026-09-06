"""ADR-004 R4 — hành vi phải giữ (preservation) và thứ phải xanh ở ứng viên.

Ba tầng, mỗi tầng một câu hỏi: slot có nêu **đúng** hành vi của story
khác mà story này chạm tệp không (a); story sửa làm đỏ test của story
trước thì cổng "bảo toàn" có chặn và sổ có ghi REOPENED với đúng thủ phạm
không (b); hai slot mới có ăn quá 15 % ngân sách ngữ cảnh không (c).
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import tests  # noqa: E402,F401 — HostProvider vào chỗ docker, không mở container (tests/__init__.py)
sys.path.insert(0, str(ROOT / "tests"))

from aisdlc.config import DEFAULTS, Config  # noqa: E402
from aisdlc.control import ledger as L  # noqa: E402
from aisdlc.control.normalize import Story  # noqa: E402
from aisdlc.control.outcome import Outcome  # noqa: E402
from aisdlc.harness.observe import AGENT_RUN, HANDOFF, MOCKUP_MAP, Event, EvidenceStore  # noqa: E402
from aisdlc.phases.implement import (  # noqa: E402
    SLOT_SOURCE,
    build_context,
    handoff_slots,
    implement_story,
)
from test_gate import GateTestCase  # noqa: E402
from test_implement import ScriptedClient  # noqa: E402

#: Runner giả in đúng định dạng `pytest -v`: test của story trước xanh khi
#: `src/a.py` còn nguyên, đỏ khi story sau sửa nó — cách rẻ nhất để có một
#: hồi quy thật, không cần model.
#:
#: Test của story sau **chỉ xuất hiện khi `src/b.py` có** — nếu nó xanh sẵn ở
#: baseline thì đối chứng nop (ADR-005 V3) chấm ✗ đúng: một test xanh trước
#: khi story viết dòng nào không chứng minh gì cho story ấy. Trước 2026-09-06
#: kịch bản này in nó vô điều kiện và story B trượt cổng vì đúng lý do ấy.
RUN_TESTS = """import sys
from pathlib import Path
a = Path("src/a.py").read_text() if Path("src/a.py").is_file() else ""
ok = a.strip() == "x = 1"
print("tests/test_a.py::test_AC_STORY_01_01_1 " + ("PASSED" if ok else "FAILED"))
if Path("src/b.py").is_file():
    print("tests/test_b.py::test_AC_STORY_01_02_1 PASSED")
sys.exit(0 if ok else 1)
"""


class TestCongBaoToan(GateTestCase):
    """Cổng đọc bằng chứng **ở đúng ứng viên**; không kiểm được ≠ đạt."""

    SHA = "c" * 40
    AC = {"id": "AC-STORY-01-01-1", "kind": "ac", "story": "STORY-01-01",
          "source": {"test_id": "tests/test_a.py::test_AC_STORY_01_01_1"}}

    def muc(self, **kw):
        g = self.gate(candidate=self.SHA, **kw)
        return next(c for c in g.checks if c.name == "bảo toàn")

    def chay_test(self, *, ids, failed=(), candidate=None):
        self.store.tool_run("S-01", "test", ok=not failed, detail={
            "test_format": "pytest", "test_ids": list(ids), "failed_ids": list(failed),
            "candidate": self.SHA if candidate is None else candidate,
        })
        self.store.tool_run("S-01", "lint", ok=True, detail={"candidate": self.SHA})

    def test_fr_hoi_story_da_xac_minh_no_khong_hoi_story_so_huu(self):
        """e9 FR-11: sở hữu bởi 01-01 (test không mang mã) nhưng sổ xác minh qua 01-05.

        Hỏi story sở hữu thì không bao giờ có test → UNRUNNABLE oan (01-07 lượt 1,
        2026-09-06); hỏi đúng story đã xác minh thì test có và xanh → đạt.
        """
        self.chay_test(ids=["tests/test_b.py::test_AC_STORY_01_05_1"])
        via = [{"id": "FR-11", "kind": "fr", "story": "STORY-01-01", "via": "STORY-01-05",
                "source": {"story": "STORY-01-05"}}]
        self.assertIs(self.muc(preservation=via).outcome, Outcome.PASSED)
        chu = [{"id": "FR-11", "kind": "fr", "story": "STORY-01-01", "source": {"story": "STORY-01-05"}}]
        self.assertIs(self.muc(preservation=chu).outcome, Outcome.UNRUNNABLE)

    def test_khong_truyen_thi_khong_ap_dung(self):
        self.green_story()
        m = self.muc()
        self.assertIs(m.outcome, Outcome.NOT_APPLICABLE)
        self.assertTrue(m.passed)

    def test_test_cua_story_khac_xanh_o_ung_vien_thi_dat(self):
        self.chay_test(ids=["tests/test_a.py::test_AC_STORY_01_01_1", "t::test_AC_S_01_1"])
        self.assertIs(self.muc(preservation=[self.AC]).outcome, Outcome.PASSED)

    def test_test_cua_story_khac_do_la_hoi_quy_va_neu_dung_ten(self):
        self.chay_test(ids=["tests/test_a.py::test_AC_STORY_01_01_1"],
                       failed=["tests/test_a.py::test_AC_STORY_01_01_1"])
        m = self.muc(preservation=[self.AC])
        self.assertIs(m.outcome, Outcome.FAILED)
        self.assertIn("AC-STORY-01-01-1", m.detail)
        self.assertIn("test_AC_STORY_01_01_1", m.detail)

    def test_khong_co_test_mang_ma_o_ung_vien_la_khong_kiem_duoc(self):
        """Test của story trước bị xoá/đổi tên thì lần chạy vẫn xanh — cổng
        không được đọc "xanh" thành "còn giữ"."""
        self.chay_test(ids=["t::test_AC_S_01_1"])
        m = self.muc(preservation=[self.AC])
        self.assertIs(m.outcome, Outcome.UNRUNNABLE)
        self.assertFalse(m.passed)
        self.assertIn("AC-STORY-01-01-1", m.detail)

    def test_bang_chung_o_ban_khac_khong_duoc_dung(self):
        self.chay_test(ids=["tests/test_a.py::test_AC_STORY_01_01_1"], candidate="d" * 40)
        self.assertIs(self.muc(preservation=[self.AC]).outcome, Outcome.UNRUNNABLE)

    def test_qa_va_mockup_theo_cung_ba_ket_cuc(self):
        self.chay_test(ids=["x"])
        qa = {"id": "qa:e2e", "kind": "qa", "story": "STORY-01-01", "source": {"qa_kind": "e2e"}}
        man = {"id": "mockup:danh-sach", "kind": "mockup", "story": "STORY-01-01",
               "source": {"screen": "danh-sach"}}
        self.assertIs(self.muc(preservation=[qa, man]).outcome, Outcome.UNRUNNABLE)

        self.store.tool_run("S-01", "qa:e2e", ok=True, detail={"candidate": self.SHA})
        self.store.record("S-01", Event(kind=MOCKUP_MAP, name="danh-sach", ok=True,
                                        detail={"candidate": self.SHA}))
        self.assertIs(self.muc(preservation=[qa, man]).outcome, Outcome.PASSED)

        self.store.record("S-01", Event(kind=MOCKUP_MAP, name="danh-sach", ok=False,
                                        detail={"missing": ["nút"], "candidate": self.SHA}))
        m = self.muc(preservation=[qa, man])
        self.assertIs(m.outcome, Outcome.FAILED)
        self.assertIn("mockup:danh-sach", m.detail)

    def test_fr_do_khi_mot_tieu_chi_cua_story_so_huu_do(self):
        fr = {"id": "FR-1", "kind": "fr", "story": "STORY-01-01", "source": {"story": "STORY-01-01"}}
        self.chay_test(ids=["t::test_AC_STORY_01_01_1", "t::test_AC_STORY_01_01_2"],
                       failed=["t::test_AC_STORY_01_01_2"])
        self.assertIs(self.muc(preservation=[fr]).outcome, Outcome.FAILED)


class VongDoiHaiStory(unittest.TestCase):
    """Story A xanh trước, story B chạm cùng tệp — dự án giả có runner in tên test."""

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)
        for cmd in (["git", "init", "-q"], ["git", "config", "user.email", "t@t"],
                    ["git", "config", "user.name", "t"]):
            subprocess.run(cmd, cwd=self.project, check=True)
        (self.project / "run_tests.py").write_text(RUN_TESTS, encoding="utf-8")
        self.artifacts = self.project / "_bmad-output"
        self.artifacts.mkdir()
        self.a = Story(id="STORY-01-01", epic_id="EPIC-01", title="A",
                       acceptance_criteria=["a"], covers=["FR-1"], write_scope=["src"])
        self.b = Story(id="STORY-01-02", epic_id="EPIC-01", title="B",
                       acceptance_criteria=["b"], covers=["FR-2"], write_scope=["src"])
        (self.artifacts / L.STORIES_INDEX).write_text(json.dumps({"stories": [
            {"id": s.id, "epic_id": s.epic_id, "acceptance_criteria": s.acceptance_criteria,
             "covers": s.covers, "write_scope": s.write_scope} for s in (self.a, self.b)
        ]}), encoding="utf-8")
        # Chỉ mục nằm trong cây: commit để cổng "phạm vi ghi" không tính nó là việc của story.
        subprocess.run(["git", "add", "-A"], cwd=self.project, check=True)
        subprocess.run(["git", "commit", "-qm", "nen"], cwd=self.project, check=True)
        # Docker bật thì `python3` không có trong ảnh alpine mặc định — runner giả
        # phải chạy ngoài sandbox; đây là phép kiểm điều phối, không phải sandbox.
        self.cfg = Config({**DEFAULTS, "tools.test": "python3 run_tests.py", "tools.lint": "true",
                           "run.max_retries": 0, "sandbox.use_docker": False})

    def tearDown(self):
        self._tmp.cleanup()

    def implement(self, story, client):
        return implement_story(story, project=self.project, artifact_root=self.artifacts,
                               client=client, config=self.cfg)


class TestSlotBaoToan(VongDoiHaiStory):
    def test_story_cham_tep_cua_hanh_vi_verified_thi_slot_neu_dung_hanh_vi_va_test_id(self):
        """AC (a). Trước khi A chạy: không có gì để giữ. Sau: đúng hành vi của A, kèm test id."""
        ctx0 = build_context(self.b, project=self.project, artifact_root=self.artifacts,
                             architecture=None, contract=None, config=self.cfg)
        self.assertIn("không chạm hành vi VERIFIED nào", ctx0["preservation"])
        self.assertEqual(ctx0["_preservation"], [])

        self.assertTrue(self.implement(self.a, ScriptedClient()).done)
        ctx = build_context(self.b, project=self.project, artifact_root=self.artifacts,
                            architecture=None, contract=None, config=self.cfg)
        ids = [it["id"] for it in ctx["_preservation"]]
        self.assertIn("AC-STORY-01-01-1", ids)
        self.assertIn("FR-1", ids)
        self.assertNotIn("AC-STORY-01-02-1", ids, "hành vi của chính mình không phải thứ phải giữ")
        self.assertIn("`AC-STORY-01-01-1` · STORY-01-01 · test `tests/test_a.py::test_AC_STORY_01_01_1`",
                      ctx["preservation"])
        self.assertIn("1 test bảo toàn", ctx["validation"])
        self.assertEqual(handoff_slots(ctx)["preservation"][0], "ledger")
        self.assertEqual(handoff_slots(ctx)["validation"][0], "ledger")
        self.assertEqual(SLOT_SOURCE["preservation"], "ledger")

    def test_tran_ky_tu_chi_cat_phan_in_ra_khong_cat_danh_sach_cong_cham(self):
        self.assertTrue(self.implement(self.a, ScriptedClient()).done)
        cfg = Config({**self.cfg.values, "context.max_preservation_chars": 40})
        ctx = build_context(self.b, project=self.project, artifact_root=self.artifacts,
                            architecture=None, contract=None, config=cfg)
        self.assertIn("đã cắt theo trần", ctx["preservation"])
        self.assertLessEqual(len(ctx["preservation"]), 40 + 80)
        # AC-STORY-01-01-1 · FR-1 · qa:fake-tests — cổng vẫn nhận đủ ba.
        self.assertEqual(len(ctx["_preservation"]), 3)


class TestHoiQuyCoChuDich(VongDoiHaiStory):
    """AC (b) — mutation test: B sửa `src/a.py` làm đỏ test của A."""

    class PhaA(ScriptedClient):
        """B làm việc của mình (`src/b.py`, test riêng xuất hiện) **và** sửa
        `src/a.py` — để lý do trượt là cổng bảo toàn, không phải thiếu test."""

        def __init__(self, **kw):
            super().__init__(writes=("src/b.py",), **kw)

        def run(self, spec):
            r = super().run(spec)
            if spec.env.get("AISDLC_STORY_ID"):
                (Path(spec.workdir) / "src" / "a.py").write_text("x = 2\n", encoding="utf-8")
            return r

    def test_cong_bao_toan_chan_va_so_ghi_reopened_dung_thu_pham(self):
        self.assertTrue(self.implement(self.a, ScriptedClient()).done)
        out = self.implement(self.b, self.PhaA())
        self.assertFalse(out.done)
        muc = next(c for c in out.attempts[-1].gate.checks if c.name == "bảo toàn")
        self.assertIs(muc.outcome, Outcome.FAILED, muc.line())
        self.assertIn("AC-STORY-01-01-1", muc.detail)

        # Sổ tự suy REOPENED từ chính bằng chứng cổng vừa đọc — không ai ghi tay.
        led = L.build(self.artifacts)
        b = led.behaviors["AC-STORY-01-01-1"]
        self.assertEqual(b.status, L.REOPENED)
        self.assertTrue(b.regressed_by.startswith("STORY-01-02#1"), b.regressed_by)
        self.assertEqual(led.behaviors["FR-1"].status, L.REOPENED)
        self.assertEqual([r["id"] for r in led.cross_reopens], ["AC-STORY-01-01-1", "FR-1"])

    def test_chay_sach_thi_khong_co_chan_oan(self):
        """B3: story sau không làm hỏng gì thì cổng bảo toàn ✅, sổ không REOPENED."""
        self.assertTrue(self.implement(self.a, ScriptedClient()).done)
        out = self.implement(self.b, ScriptedClient(writes=("src/b.py",)))
        self.assertTrue(out.done, out.summary())
        muc = next(c for c in out.attempts[-1].gate.checks if c.name == "bảo toàn")
        self.assertIs(muc.outcome, Outcome.PASSED, muc.line())
        # Đối chứng nop (V3) không chặn: test mang mã của B **không** xanh sẵn ở
        # baseline. Ở đây nó là – "story không thêm/sửa tệp test" vì runner giả
        # là một script, không phải tệp test; điều phép kiểm này chốt là **không
        # ✗**. Gắn mã vào test có sẵn thì mục này ✗ và story không "chạy sạch".
        nop = next(c for c in out.attempts[-1].gate.checks if c.name == "test có kiểm được story")
        self.assertIsNot(nop.outcome, Outcome.FAILED, nop.line())
        self.assertEqual(L.build(self.artifacts).reopen_events, 0)

    def test_ba_vai_nhan_cung_mot_danh_sach_tu_harness(self):
        """ADR-003 #9: reviewer và security nhận đúng slot developer nhận — tính
        một lần trước phiên, không tính lại sau khi sổ đã đổi vì chính lượt này."""
        self.assertTrue(self.implement(self.a, ScriptedClient()).done)
        self.implement(self.b, self.PhaA())
        goi = {e.detail["to"]: e.detail["slots"]
               for e in EvidenceStore(self.artifacts).read(self.b.id).of(HANDOFF)}
        self.assertEqual({"developer", "reviewer", "security"}, set(goi))
        for vai in ("reviewer", "security"):
            self.assertEqual(goi[vai]["preservation"], goi["developer"]["preservation"], vai)
            self.assertEqual(goi[vai]["preservation"]["source"], "ledger")


class TestNganSachNguCanh(VongDoiHaiStory):
    def test_hai_slot_moi_khong_qua_15_phan_tram_prompt(self):
        """AC (c). Số đo trước/sau thật nằm ở ADR-004 §6 R4; đây là chốt chặn để
        lần sửa prompt sau không lặng lẽ phá ngân sách."""
        self.assertTrue(self.implement(self.a, ScriptedClient()).done)
        self.implement(self.b, ScriptedClient(writes=("src/b.py",)))
        ev = EvidenceStore(self.artifacts).read(self.b.id)
        dev = next(e for e in ev.of(AGENT_RUN) if e.name == "STORY-01-02#1")
        goi = next(e for e in ev.of(HANDOFF) if e.detail["to"] == "developer")
        moi = sum(goi.detail["slots"][k]["chars"] for k in ("preservation", "validation"))
        self.assertGreater(moi, 0)
        self.assertLessEqual(moi, 0.15 * dev.detail["prompt_chars"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
