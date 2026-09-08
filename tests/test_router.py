"""Định tuyến skill cho story (ADR-002 đợt 1).

Tín hiệu quan trọng nhất để test: router **biết từ chối**. Paper ghi 2/20
task hỏng vì skill nhồi nhầm; đo trên e9, khớp một-từ-khoá làm story schema
IndexedDB khớp skill mật-mã-hậu-lượng-tử. Nên luật "hai tín hiệu độc lập"
và abstain là thứ phải giữ.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.control.normalize import Story  # noqa: E402
from aisef.kit import router  # noqa: E402
from aisef.kit.registry import Registry, SkillEntry, Verification  # noqa: E402


def entry(id, caps=(), *, tags=(), subdomain="", status="verified", use_when="", desc="skill"):
    return SkillEntry(
        id=id, source="demo", path=f".claude/skills/{id}", description=desc,
        use_when=use_when, subdomain=subdomain, tags=list(tags),
        capabilities=list(caps), status=status,
        verified=Verification(at="now", by="structural"),
    )


def reg(*entries) -> Registry:
    return Registry(entries={e.id: e for e in entries})


def story(**kw):
    base = dict(id="S-01", epic_id="E-01", title="Story",
                acceptance_criteria=["Then chuyện xảy ra"], write_scope=["src/a.ts"])
    base.update(kw)
    return Story(**base)


class TestBietTuChoi(unittest.TestCase):
    def test_khong_skill_nao_khop_thi_abstain(self):
        r = router.route(story(), reg(entry("bao-mat", ["security"])))
        self.assertTrue(r.abstained)
        self.assertEqual(r.ids(), [])

    def test_mot_tin_hieu_khong_du(self):
        """Khớp đúng một năng lực (keyword-only) không được chọn — luật §4.2."""
        s = story(acceptance_criteria=["Then p95 dưới 200ms"])  # cần perf
        r = router.route(s, reg(entry("chi-perf", ["perf"])))
        self.assertTrue(r.abstained)
        self.assertIsNotNone(r.best_rejected)   # có điểm, nhưng một tín hiệu

    def test_hai_tin_hieu_thi_chon(self):
        s = story(acceptance_criteria=["Then p95 dưới 200ms ở quy mô 10.000"],
                  title="đo hiệu năng perf")
        r = router.route(s, reg(entry("do-perf", ["perf"], tags=["perf", "benchmark"],
                                      subdomain="performance")))
        self.assertFalse(r.abstained)
        self.assertEqual(r.ids(), ["do-perf"])

    def test_registry_rong_thi_abstain(self):
        self.assertTrue(router.route(story(), reg()).abstained)

    def test_chi_xet_skill_routable(self):
        s = story(acceptance_criteria=["Then p95 dưới 200ms"], title="perf benchmark")
        good = entry("do-perf", ["perf"], tags=["perf"], subdomain="performance")
        cand = entry("moi", ["perf"], tags=["perf"], subdomain="performance", status="candidate")
        r = router.route(s, reg(good, cand))
        self.assertEqual(r.ids(), ["do-perf"])  # candidate không được xét


class TestChonDung(unittest.TestCase):
    def test_skill_framework_theo_pha_luon_du_dieu_kien(self):
        s = story(screens=["notes-list"])
        r = router.route(s, reg(entry("aisef-mockup-html", ["ui"])), phase="mockup")
        self.assertIn("aisef-mockup-html", r.ids())

    def test_ton_trong_tran_so_luong(self):
        s = story(acceptance_criteria=["Then bảo mật xác thực injection auth"],
                  title="security auth")
        skills = [entry(f"s{i}", ["security"], tags=["security", "auth", "injection"],
                        subdomain="authentication") for i in range(6)]
        r = router.route(s, reg(*skills), limit=2)
        self.assertEqual(len(r.picked), 2)

    def test_xep_diem_cao_truoc(self):
        s = story(screens=["x"], acceptance_criteria=["Then kịch bản e2e và trợ năng wcag"],
                  title="giao diện accessibility")
        it = router.route(s, reg(
            entry("nhieu", ["ui", "accessibility"], tags=["accessibility", "wcag", "aria"],
                  subdomain="accessibility"),
            entry("it", ["ui"], tags=["ui"]),
        ))
        self.assertEqual(it.picked[0].entry.id, "nhieu")


class TestRaChoAgent(unittest.TestCase):
    def test_prompt_abstain_bao_lam_theo_hien_phap(self):
        sec = router.route(story(), reg(entry("x", ["security"]))).prompt_section()
        self.assertIn("No skill", sec)
        self.assertIn("constitution", sec)

    def test_prompt_khong_dan_noi_dung_skill(self):
        """Progressive disclosure: chỉ tên, dùng-khi, đường dẫn — agent mở khi cần."""
        s = story(acceptance_criteria=["Then bảo mật auth injection"], title="security auth")
        e = entry("bao-mat", ["security"], tags=["security", "auth", "injection"],
                  subdomain="authentication", use_when="khi chạm dữ liệu người dùng")
        sec = router.route(s, reg(e)).prompt_section()
        self.assertIn("bao-mat", sec)
        self.assertIn("khi chạm dữ liệu người dùng", sec)
        self.assertIn(".claude/skills/bao-mat", sec)
        self.assertIn("when you reach the step", sec)  # nhắc mở muộn

    def test_evidence_ghi_da_xet_bao_nhieu_va_nguong(self):
        s = story(acceptance_criteria=["Then p95 dưới 200ms"])
        ev = router.route(s, reg(entry("chi-perf", ["perf"]))).as_evidence()
        self.assertTrue(ev["abstained"])
        self.assertEqual(ev["considered"], 1)
        self.assertEqual(ev["threshold"], router.DEFAULT_THRESHOLD)
        self.assertIsNotNone(ev["best_rejected"])   # để đo precision sau


if __name__ == "__main__":
    unittest.main()


class TestManHinhKhongPhaiTuKhoa(unittest.TestCase):
    """Đo 2026-09-05 trên e9: story điều hướng bàn phím (có màn hình) được đề
    nghị skill mã hoá đầu-cuối — vì skill ấy bị suy ra năng lực "ui" từ chữ,
    và "màn hình + một chữ" được đếm là hai tín hiệu. Cả hai đường đều đóng."""

    def story(self):
        return Story(id="S-9", epic_id="E", title="Keyboard navigation of the notes list with messaging",
                     acceptance_criteria=["Given the list, When arrow keys, Then focus moves"],
                     screens=["danh-sach"], verification_contract=["unit"])

    def test_cyber_skill_with_inferred_ui_is_not_offered_for_a_screen(self):
        e = entry("implementing-end-to-end-encryption-for-messaging", ["security", "ui"],
                  tags=["cryptography", "encryption", "messaging"])
        e.domain = "cybersecurity"
        r = router.route(self.story(), reg(e))
        self.assertTrue(r.abstained, [p.line() for p in r.picked])

    def test_ui_domain_skill_needs_two_words_besides_the_screen(self):
        it = entry("ui-mot-chu", ["ui"], tags=["messaging"]); it.domain = "ui-ux"
        nhieu = entry("ui-hai-chu", ["ui"], tags=["keyboard", "navigation", "messaging"]); nhieu.domain = "ui-ux"
        r = router.route(self.story(), reg(it, nhieu))
        self.assertEqual([p.entry.id for p in r.picked], ["ui-hai-chu"])

    def test_contract_alone_is_still_one_signal(self):
        e = entry("security-review", ["security"], tags=[]); e.domain = "cybersecurity"
        s = self.story(); s.verification_contract = ["unit", "security"]
        self.assertTrue(router.route(s, reg(e)).abstained)


class TestSkillCuaNgoGiaoDien(unittest.TestCase):
    """Story có màn hình → mời `ui-ux-pro-max` theo chính sách (không theo chữ);
    story không có màn hình → không."""

    def test_ui_story_gets_the_entry_skill(self):
        e = entry("ui-ux-pro-max", [], tags=[]); e.domain = "ui-ux"
        s = Story(id="S", epic_id="E", title="Tạo ghi chú mới bằng một thao tác", screens=["note-editor"])
        r = router.route(s, reg(e))
        self.assertEqual([p.entry.id for p in r.picked], ["ui-ux-pro-max"])
        self.assertIn("cửa ngõ", r.picked[0].rationale[0])

    def test_story_without_screen_does_not(self):
        e = entry("ui-ux-pro-max", [], tags=[]); e.domain = "ui-ux"
        s = Story(id="S", epic_id="E", title="kebabCase", screens=[])
        self.assertTrue(router.route(s, reg(e)).abstained)

    def test_only_in_implement_phase(self):
        e = entry("ui-ux-pro-max", [], tags=[]); e.domain = "ui-ux"
        s = Story(id="S", epic_id="E", title="t", screens=["x"])
        self.assertTrue(router.route(s, reg(e), phase="review").abstained)
