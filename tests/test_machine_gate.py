"""Kiểm chứng cổng máy — phải CHẶN THẬT khi tài liệu có vấn đề."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.config import DEFAULTS, Config  # noqa: E402
from aisef.control.machine_gate import check_all, check_prd, check_stories  # noqa: E402
from aisef.control.normalize import PRD, OpenQuestion, Requirement, parse_prd_file  # noqa: E402
from aisef.control.scheduler import Story  # noqa: E402

PRD_FIXTURE = ROOT / "tests" / "fixtures" / "bmad" / "prd.md"


def req(rid: str, *, criteria=("kiểm được",), kind="functional", title="Tiêu đề") -> Requirement:
    return Requirement(id=rid, kind=kind, title=title, acceptance_criteria=list(criteria))


def story(sid: str, *, deps=(), scope=("src/x.py",)) -> Story:
    return Story(id=sid, epic_id="E1", depends_on=tuple(deps), write_scope=tuple(scope))


class TestPrdGateOnRealDocument(unittest.TestCase):
    def test_real_prd_passes(self):
        r = check_prd(parse_prd_file(PRD_FIXTURE))
        self.assertTrue(r.passed, r.summary())

    def test_real_prd_surfaces_open_questions_as_warnings(self):
        r = check_prd(parse_prd_file(PRD_FIXTURE))
        self.assertTrue(any("open questions" in w for w in r.warnings))
        self.assertTrue(any("blocked by open questions" in w for w in r.warnings))


class TestPrdGate(unittest.TestCase):
    def test_empty_prd_fails(self):
        self.assertFalse(check_prd(PRD()).passed)

    def test_untestable_requirement_blocks(self):
        prd = PRD(requirements=[req("FR-1", criteria=())])
        r = check_prd(prd)
        self.assertFalse(r.passed)
        self.assertIn("FR-1", r.errors[0])

    def test_missing_title_blocks(self):
        prd = PRD(requirements=[req("FR-1", title="  ")])
        self.assertFalse(check_prd(prd).passed)

    def test_open_questions_warn_but_do_not_block(self):
        prd = PRD(
            requirements=[req("FR-1")],
            open_questions=[OpenQuestion(id="OQ-1", text="?", blocks=["FR-9"])],
        )
        r = check_prd(prd)
        self.assertTrue(r.passed)
        self.assertTrue(r.warnings)

    def test_missing_nfr_is_only_a_warning(self):
        r = check_prd(PRD(requirements=[req("FR-1")]))
        self.assertTrue(r.passed)
        self.assertTrue(any("non-functional" in w for w in r.warnings))


class TestStoryGate(unittest.TestCase):
    def test_empty_fails(self):
        self.assertFalse(check_stories([]).passed)

    def test_valid_stories_pass(self):
        stories = [story("S-1", scope=("src/a.py",)), story("S-2", scope=("src/b.py",))]
        self.assertTrue(check_stories(stories).passed)

    def test_missing_write_scope_blocks(self):
        r = check_stories([story("S-1", scope=())])
        self.assertFalse(r.passed)
        self.assertIn("write_scope", r.errors[0])

    def test_duplicate_id_blocks(self):
        r = check_stories([story("S-1"), story("S-1", scope=("src/b.py",))])
        self.assertFalse(r.passed)
        self.assertTrue(any("duplicate" in e for e in r.errors))

    def test_dependency_cycle_blocks(self):
        stories = [
            story("S-1", deps=("S-2",), scope=("src/a.py",)),
            story("S-2", deps=("S-1",), scope=("src/b.py",)),
        ]
        r = check_stories(stories)
        self.assertFalse(r.passed)
        self.assertTrue(any("cycle" in e for e in r.errors))

    def test_unknown_dependency_blocks(self):
        r = check_stories([story("S-1", deps=("KHONG-CO",))])
        self.assertFalse(r.passed)

    def test_too_many_acceptance_criteria_blocks(self):
        """Story quá lớn sẽ tràn ngữ cảnh trong một phiên."""
        r = check_stories([story("S-1")], story_ac_count={"S-1": 20})
        self.assertFalse(r.passed)
        self.assertTrue(any("split" in e for e in r.errors))

    def test_khong_co_tieu_chi_nao_thi_chan(self):
        """Lỗi 145. Story không tiêu chí **không phải** story nhỏ, mà là story
        không kiểm được: `criteria have tests` không có gì để tìm, còn nop trả
        PASSED ở nhánh "story declares no criteria". Đo trên marks-cli
        2026-09-14: nhãn `Acceptance criteria:` trần (lỗi 144) làm cả sáu story
        về 0 tiêu chí, cổng máy báo `errors: []`, trong khi thẻ story in đúng
        dòng "(none — machine gate will block)"."""
        r = check_stories([story("S-1"), story("S-2")],
                          story_ac_count={"S-1": 0, "S-2": 3})
        self.assertFalse(r.passed)
        loi = " ".join(r.errors)
        self.assertIn("S-1", loi)
        self.assertNotIn("S-2", loi)

    def test_khong_khai_so_tieu_chi_thi_khong_ket_luan(self):
        """Người gọi không truyền `story_ac_count` (kiểm bộ phận, luồng cũ) —
        im lặng không phải là 0."""
        self.assertTrue(check_stories([story("S-1")]).passed)

    def test_tieu_chi_ta_thu_giu_cho_thi_chan(self):
        """Lỗi 148. Story giao **vật giữ chỗ** tốn cả một epic. marks-cli
        2026-09-14: STORY-01-02 giao dispatcher mà các lệnh trả "not
        implemented", tiêu chí "lệnh stub thoát 1, một dòng `marks: `, không
        có stdout" được ghi VERIFIED vào ledger. Hai hậu quả đều chí tử:
        preservation chặn STORY-02-01 — story hiện thực `add` — vì nó **phải**
        phá hành vi ấy; và cái thất bại vô điều kiện của stub đã thoả sẵn tiêu
        chí nhánh lỗi của chính STORY-02-01 (cùng dấu hiệu quan sát: thoát 1,
        một dòng stderr, store không đổi), nên không test nào của nó đỏ được ở
        điểm rẽ nhánh. Epic dừng ở wave 1, bốn story sau không bao giờ tới."""
        r = check_stories(
            [story("S-1"), story("S-2")],
            story_ac_text={
                "S-1": ["Given lệnh còn là stub, Then nó thoát 1 và in `marks: `"],
                "S-2": ["Given url hợp lệ, Then store có thêm một bản ghi"],
            },
        )
        self.assertFalse(r.passed)
        loi = " ".join(r.errors)
        self.assertIn("S-1", loi)
        self.assertNotIn("S-2", loi)

    def test_khong_truyen_van_ban_tieu_chi_thi_khong_ket_luan(self):
        self.assertTrue(check_stories([story("S-1")]).passed)

    def test_ac_limit_respects_config(self):
        cfg = Config({**DEFAULTS, "story.max_acceptance_criteria": 30})
        r = check_stories([story("S-1")], config=cfg, story_ac_count={"S-1": 20})
        self.assertTrue(r.passed)

    def test_pham_vi_ghi_ngoai_du_an_bi_chan(self):
        """Lỗi 147. Mục phạm vi ngoài gốc dự án không bao giờ ghi được —
        guard chặn theo gốc dự án **trước** khi so phạm vi — nên nó không phải
        lỗ hổng mà là rác đánh lừa mọi người đọc sau: cảnh báo độ rộng đếm
        `tmp` và `foo` thành module gốc của dự án. marks-cli 2026-09-14: người
        lập kế hoạch khai đúng như lời khuyên của lỗi 146 bảo."""
        r = check_stories([story("S-1", scope=("bin/marks.js", "/tmp/x.json")),
                           story("S-2", scope=("src/a.py",))])
        self.assertFalse(r.passed)
        loi = " ".join(r.errors)
        self.assertIn("/tmp/x.json", loi)
        self.assertNotIn("S-2", loi)

    def test_pham_vi_ghi_tuong_doi_van_qua(self):
        self.assertTrue(check_stories([story("S-1", scope=("src/a.py", "tests/"))]).passed)

    def test_too_wide_write_scope_blocks(self):
        wide = tuple(f"src/{i}.py" for i in range(20))
        r = check_stories([story("S-1", scope=wide)])
        self.assertFalse(r.passed)
        self.assertTrue(any("too many" in e for e in r.errors))


class TestTraceability(unittest.TestCase):
    def prd(self) -> PRD:
        return PRD(
            requirements=[req("FR-1"), req("FR-2"), req("FR-3")],
            open_questions=[OpenQuestion(id="OQ-1", text="?", blocks=["FR-3"])],
        )

    def test_uncovered_requirement_blocks(self):
        """Mất truy vết từ PRD tới code là lỗi chặn, không phải cảnh báo."""
        r = check_stories(
            [story("S-1")], self.prd(), story_fr_map={"S-1": ["FR-1"]}
        )
        self.assertFalse(r.passed)
        self.assertTrue(any("FR-2" in e for e in r.errors))

    def test_blocked_requirement_excluded_from_coverage(self):
        """FR-3 bị OQ-1 chặn nên không đòi story phủ nó."""
        r = check_stories(
            [story("S-1")], self.prd(), story_fr_map={"S-1": ["FR-1", "FR-2"]}
        )
        self.assertTrue(r.passed, r.summary())

    def test_story_touching_blocked_requirement_fails(self):
        r = check_stories(
            [story("S-1")], self.prd(), story_fr_map={"S-1": ["FR-1", "FR-2", "FR-3"]}
        )
        self.assertFalse(r.passed)
        self.assertTrue(any("blocked by open questions" in e for e in r.errors))

    def test_unknown_requirement_reference_warns(self):
        r = check_stories(
            [story("S-1")], self.prd(), story_fr_map={"S-1": ["FR-1", "FR-2", "FR-99"]}
        )
        self.assertTrue(any("FR-99" in w for w in r.warnings))


class TestCombine(unittest.TestCase):
    def test_merges_and_prefixes(self):
        a = check_prd(PRD())
        b = check_stories([])
        combined = check_all([a, b])
        self.assertFalse(combined.passed)
        self.assertTrue(all(e.startswith("[machine gate") for e in combined.errors))

    def test_all_passing_combines_to_pass(self):
        prd = PRD(requirements=[req("FR-1")])
        combined = check_all([check_prd(prd), check_stories([story("S-1")])])
        self.assertTrue(combined.passed)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestChuoiHoanToan(unittest.TestCase):
    """Epic bị xâu thành chuỗi thì máy chạy song song không với tới được.

    Đo trên e9: BMAD khai mỗi story phụ thuộc story ngay trước, cả 7 story
    của EPIC-01 thành 7 đợt. Máy chia đợt có, được kiểm bằng test đơn vị,
    và **không bao giờ chạy** — một năng lực đã tuyên bố mà không quan sát
    được lần nào.
    """

    def st(self, sid, deps=(), epic="EPIC-01", scope=("src/a.py",)):
        return Story(id=sid, epic_id=epic, title=sid,
                     depends_on=tuple(deps), write_scope=tuple(scope))

    def test_canh_bao_khi_moi_story_mot_dot(self):
        stories = [
            self.st("S-1"),
            self.st("S-2", ["S-1"], scope=("src/b.py",)),
            self.st("S-3", ["S-2"], scope=("src/c.py",)),
            self.st("S-4", ["S-3"], scope=("src/d.py",)),
        ]
        r = check_stories(stories)
        self.assertTrue(r.passed, r.errors)
        self.assertTrue(any("fully serialized" in w for w in r.warnings))
        self.assertTrue(any("EPIC-01" in w for w in r.warnings))

    def test_khong_canh_bao_khi_co_story_song_song(self):
        stories = [
            self.st("S-1"),
            self.st("S-2", ["S-1"], scope=("src/b.py",)),
            self.st("S-3", ["S-1"], scope=("src/c.py",)),
            self.st("S-4", ["S-2", "S-3"], scope=("src/d.py",)),
        ]
        r = check_stories(stories)
        self.assertFalse(any("fully serialized" in w for w in r.warnings))

    def test_epic_qua_nho_thi_khong_ket_luan(self):
        """Hai story nối nhau không nói lên gì về thói quen lập kế hoạch."""
        stories = [self.st("S-1"), self.st("S-2", ["S-1"], scope=("src/b.py",))]
        r = check_stories(stories)
        self.assertFalse(any("fully serialized" in w for w in r.warnings))

    def test_theo_tung_epic_khong_phai_ca_tap(self):
        """Epic chạy tuần tự với nhau; song song chỉ có nghĩa **trong** một
        epic. Tính trên cả tập thì con số ra khác và không nói lên gì."""
        stories = [
            self.st("S-1", epic="EPIC-01"),
            self.st("S-2", ["S-1"], epic="EPIC-01", scope=("src/b.py",)),
            self.st("S-3", ["S-2"], epic="EPIC-01", scope=("src/c.py",)),
            self.st("T-1", epic="EPIC-02", scope=("api/a.py",)),
            self.st("T-2", ["T-1"], epic="EPIC-02", scope=("api/b.py",)),
            self.st("T-3", ["T-1"], epic="EPIC-02", scope=("api/c.py",)),
        ]
        r = check_stories(stories)
        canh = [w for w in r.warnings if "fully serialized" in w]
        self.assertEqual(len(canh), 1)
        self.assertIn("EPIC-01", canh[0])
        self.assertNotIn("EPIC-02", canh[0])



class TestHaiStoryCungPhamViGhi(unittest.TestCase):
    """Lỗi 128 (todo-cli 2026-09-13, 3/3): mỗi epic bị chia thành "làm lệnh X"
    và "các ca lỗi của lệnh X", cùng đúng một tệp. Bản cài đặt tử tế của story
    đầu phủ luôn tiêu chí của story sau, nên story sau **không có việc gì hợp
    lệ**: test của nó xanh ở điểm rẽ, `tests verify story` chặn, và không test
    nào developer viết ra có thể đỏ cho hành vi đã merge. Ba trên mười ba story
    chết như thế, ~45 phút agent — mà kế hoạch đã đọc được ngay ở cổng này."""

    def st(self, sid, epic="EPIC-01", scope=("lib/commands/list.js",), deps=()):
        return Story(id=sid, epic_id=epic, title=sid,
                     depends_on=tuple(deps), write_scope=tuple(scope))

    def _canh(self, r):
        return [w for w in r.warnings if "same epic write exactly the same files" in w]

    def test_canh_bao_khi_hai_story_cung_tep(self):
        r = check_stories([self.st("S-1"), self.st("S-2", deps=["S-1"]),
                           self.st("S-9", epic="EPIC-09", scope=("lib/commands/add.js",))])
        self.assertTrue(r.passed, r.errors)
        canh = self._canh(r)
        self.assertEqual(len(canh), 1)
        self.assertIn("S-1, S-2", canh[0])
        self.assertIn("lib/commands/list.js", canh[0])

    def test_pham_vi_khac_thi_khong_canh_bao(self):
        r = check_stories([self.st("S-1"),
                           self.st("S-2", deps=["S-1"], scope=("lib/commands/add.js",))])
        self.assertEqual(self._canh(r), [])

    def test_khac_epic_thi_khong_ket_luan(self):
        """Epic chạy tuần tự; hai epic chạm cùng tệp là chuyện khác hẳn."""
        r = check_stories([self.st("S-1", epic="EPIC-01"),
                           self.st("T-1", epic="EPIC-02")])
        self.assertEqual(self._canh(r), [])

    def test_lockfile_khong_tinh_vao_so_sanh(self):
        """Mọi story JS đều mang lockfile trong phạm vi ghi; để nó vào phép so
        sánh thì hai story chỉ trùng lockfile cũng bị tố oan — hoặc tệ hơn,
        hai story trùng **thật** lại thoát vì một bên khai thêm `yarn.lock`."""
        r = check_stories([
            self.st("S-1", scope=("lib/commands/list.js", "package-lock.json")),
            self.st("S-2", deps=["S-1"], scope=("lib/commands/list.js", "yarn.lock")),
            self.st("S-9", epic="EPIC-09", scope=("lib/commands/add.js",)),
        ])
        canh = self._canh(r)
        self.assertEqual(len(canh), 1, "lockfile không được che mất chỗ trùng thật")
        self.assertNotIn("lock", canh[0])

    def test_pham_vi_rong_thi_khong_ket_luan(self):
        r = check_stories([self.st("S-1", scope=()), self.st("S-2", scope=())])
        self.assertEqual(self._canh(r), [])

    def test_pham_vi_ca_du_an_deu_dung_thi_khong_noi_gi(self):
        """Đo trên `todo-oc` (ứng dụng một tệp): cả **7** story đều ghi
        `index.html`, và cảnh báo tố 2 cặp — nói đúng nhưng không nói được gì.
        Phạm vi mà **mọi** story đều khai là hình dạng của dự án, không phải mùi
        của cặp nào. Trên dự án nhiều tệp nó vẫn có nghĩa: `list.js` là 2/13."""
        r = check_stories([
            self.st("S-1", epic="EPIC-01", scope=("index.html",)),
            self.st("S-2", epic="EPIC-02", scope=("index.html",)),
            self.st("S-3", epic="EPIC-03", scope=("index.html",)),
            self.st("S-4", epic="EPIC-03", deps=["S-3"], scope=("index.html",)),
        ])
        self.assertEqual(self._canh(r), [])

    def test_chi_mot_phan_du_an_dung_chung_thi_van_noi(self):
        r = check_stories([
            self.st("S-1", epic="EPIC-01", scope=("lib/a.js",)),
            self.st("S-2", epic="EPIC-02", scope=("lib/b.js",)),
            self.st("S-3", epic="EPIC-03", scope=("lib/list.js",)),
            self.st("S-4", epic="EPIC-03", deps=["S-3"], scope=("lib/list.js",)),
        ])
        canh = self._canh(r)
        self.assertEqual(len(canh), 1)
        self.assertIn("S-3, S-4", canh[0])
