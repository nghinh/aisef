"""Sổ hành vi — VERIFIED / GAP / REOPENED chiếu từ bằng chứng (ADR-004 R2/R6/R7).

Điều sổ này phải chứng minh được, và cổng story hôm nay không: phân biệt
"chưa từng đạt" với "đã đạt rồi hỏng". Vì thế test trung tâm ở đây là một
chuỗi thời gian, không phải một ảnh chụp.
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.control import ledger as L  # noqa: E402
from aisef.harness.observe import Event, EvidenceStore, MOCKUP_MAP  # noqa: E402


def ac_test(story: str, i: int) -> str:
    return f"src/x.ts > nhóm > AC-{story}-{i}: mô tả"


class LedgerTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "_bmad-output"
        self.root.mkdir(parents=True)
        self.store = EvidenceStore(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def run_cli(self, *args: str) -> tuple[int, str, str]:
        from aisef.cli import main

        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["--project", str(self.root.parent), *args])
        return code, out.getvalue(), err.getvalue()

    def index(self, stories):
        (self.root / L.STORIES_INDEX).write_text(
            json.dumps({"stories": stories}, ensure_ascii=False), encoding="utf-8"
        )

    def run_tests(self, story: str, *, ids, failed=(), attempt=1, candidate="", ok=None):
        self.store.tool_run(
            story, "test",
            ok=(not failed) if ok is None else ok,
            detail={
                "test_format": "vitest", "test_ids": list(ids),
                "failed_ids": list(failed), "attempt": attempt,
                **({"candidate": candidate} if candidate else {}),
            },
        )


class TestChuoiThoiGian(LedgerTestCase):
    def setUp(self):
        super().setUp()
        self.index([
            {"id": "STORY-01-01", "epic_id": "EPIC-01",
             "acceptance_criteria": ["a"], "covers": ["FR-1"]},
            {"id": "STORY-01-02", "epic_id": "EPIC-01", "acceptance_criteria": ["b"]},
        ])

    def test_xanh_do_xanh_thanh_verified_reopened_verified(self):
        """Chuỗi HoH: đúng → hỏng → sửa. Cái ở giữa **không** phải GAP."""
        t1 = ac_test("STORY-01-01", 1)
        self.run_tests("STORY-01-01", ids=[t1])
        # Story sau chạy cùng bộ test và làm đỏ tiêu chí của story trước.
        self.run_tests("STORY-01-02", ids=[t1, ac_test("STORY-01-02", 1)],
                       failed=[t1], attempt=2, candidate="deadbeefcafe")
        self.run_tests("STORY-01-02", ids=[t1, ac_test("STORY-01-02", 1)], attempt=3)

        led = L.build(self.root)
        b = led.behaviors["AC-STORY-01-01-1"]
        self.assertEqual([h["status"] for h in b.history],
                         [L.VERIFIED, L.REOPENED, L.VERIFIED])
        self.assertEqual(b.status, L.VERIFIED)

    def test_regressed_by_chi_dung_story_va_luot_lam_hong(self):
        t1 = ac_test("STORY-01-01", 1)
        self.run_tests("STORY-01-01", ids=[t1])
        self.run_tests("STORY-01-02", ids=[t1], failed=[t1], attempt=2,
                       candidate="deadbeefcafe")

        led = L.build(self.root)
        b = led.behaviors["AC-STORY-01-01-1"]
        self.assertEqual(b.status, L.REOPENED)
        self.assertEqual(b.regressed_by, "STORY-01-02#2@deadbee")
        # Hồi quy liên story là con số HoH đo; đỏ lại trong lượt của chính
        # mình chỉ là TDD, không được lẫn vào đây.
        self.assertEqual(led.summary()["cross_reopens"], 2)   # tiêu chí + FR-1
        self.assertEqual(
            {c["id"] for c in led.cross_reopens}, {"AC-STORY-01-01-1", "FR-1"})
        self.assertEqual(led.cross_reopens[0]["verified_by"], "STORY-01-01")

    def test_do_lai_trong_luot_cua_chinh_minh_khong_tinh_lien_story(self):
        t1 = ac_test("STORY-01-01", 1)
        self.run_tests("STORY-01-01", ids=[t1])
        self.run_tests("STORY-01-01", ids=[t1], failed=[t1], attempt=2)
        led = L.build(self.root)
        # tiêu chí **và** FR story phủ đều hỏng lại — nhưng do chính nó
        self.assertEqual(led.summary()["reopened"], 2)
        self.assertEqual(led.summary()["cross_reopens"], 0)

    def test_gap_roi_xanh_la_resolved_khong_phai_reopened(self):
        # Lượt đầu chưa có test nào mang mã → GAP, không phải "chưa biết".
        self.run_tests("STORY-01-01", ids=["src/x.ts > không mang mã nào"], ok=True)
        led = L.build(self.root)
        self.assertEqual(led.behaviors["AC-STORY-01-01-1"].status, L.GAP)
        self.assertEqual(led.summary()["resolved"], 0)

        self.run_tests("STORY-01-01", ids=[ac_test("STORY-01-01", 1)], attempt=2)
        led = L.build(self.root)
        b = led.behaviors["AC-STORY-01-01-1"]
        self.assertEqual(b.status, L.VERIFIED)
        self.assertEqual([h["status"] for h in b.history], [L.GAP, L.VERIFIED])
        self.assertEqual(led.summary()["resolved"], 2)   # tiêu chí + FR-1
        self.assertEqual(led.summary()["reopen_events"], 0)

    def test_lich_su_chi_ghi_khi_trang_thai_doi(self):
        """e9 có ~100 lần chạy test × ~280 tên; ghi mọi quan sát thì sổ to
        hơn bằng chứng nó chiếu ra."""
        for i in range(10):
            self.run_tests("STORY-01-01", ids=[ac_test("STORY-01-01", 1)], attempt=i + 1)
        led = L.build(self.root)
        self.assertEqual(len(led.behaviors["AC-STORY-01-01-1"].history), 1)


class TestNguonHanhVi(LedgerTestCase):
    def test_bon_nguon_deu_thanh_hanh_vi(self):
        self.index([{"id": "STORY-01-01", "epic_id": "EPIC-01",
                     "acceptance_criteria": ["a"], "covers": ["FR-2", "NFR-1"]}])
        self.run_tests("STORY-01-01", ids=[ac_test("STORY-01-01", 1)])
        self.store.tool_run("STORY-01-01", "qa:e2e", ok=False, detail={"tail": "đỏ"})
        self.store.record("STORY-01-01", Event(
            kind=MOCKUP_MAP, name="notes-list", ok=False, detail={"missing": ["nút"]}))

        led = L.build(self.root)
        self.assertEqual(led.behaviors["AC-STORY-01-01-1"].status, L.VERIFIED)
        self.assertEqual(led.behaviors["FR-2"].kind, "fr")
        self.assertEqual(led.behaviors["NFR-1"].kind, "nfr")
        self.assertEqual(led.behaviors["qa:e2e"].status, L.GAP)
        self.assertEqual(led.behaviors["mockup:notes-list"].status, L.GAP)

    def test_khong_doc_duoc_ten_test_la_gap_khong_phai_dat(self):
        """Cùng luật với cổng: chưa cấu hình reporter ≠ tiêu chí đã đạt."""
        self.index([{"id": "STORY-01-01", "acceptance_criteria": ["a", "b"]}])
        self.store.tool_run("STORY-01-01", "test", ok=True, detail={"tail": "3 passed"})
        led = L.build(self.root)
        self.assertEqual(led.summary()["gap"], 2)
        self.assertIn("cannot read test names", led.behaviors["AC-STORY-01-01-1"].source["why"])

    def test_bo_test_chay_mot_phan_khong_bien_story_khac_thanh_gap(self):
        """Lần chạy không thấy story kia thì nó im lặng, không kết tội."""
        self.index([
            {"id": "STORY-01-01", "acceptance_criteria": ["a"]},
            {"id": "STORY-01-02", "acceptance_criteria": ["b"]},
        ])
        self.run_tests("STORY-01-01", ids=[ac_test("STORY-01-01", 1)])
        led = L.build(self.root)
        self.assertNotIn("AC-STORY-01-02-1", led.behaviors)

    def test_story_sau_thieu_test_khong_lam_do_yeu_cau_story_khac_dang_xanh(self):
        """Đo trên todo-cli STORY-06-01: năm yêu cầu bật REOPENED trong khi 65/65
        test xanh. Story ấy `covers` cùng yêu cầu với ba story trước và có một tiêu
        chí không test nào chạm tới, nên rollup của **chính nó** ghi đỏ; xanh của
        story chủ sở hữu — đủ tiêu chí, trong **cùng** lần chạy — đến sau nên bị bỏ
        (xanh ở ứng viên chưa landed trả về sớm). Vắng mặt ở tiêu chí của story sau
        không xoá được bằng chứng story trước vừa để lại.
        """
        from aisef.control.journal import Entry, JournalStore

        self.index([
            {"id": "STORY-02-01", "acceptance_criteria": ["a"], "covers": ["FR-1"]},
            {"id": "STORY-06-01", "acceptance_criteria": ["b", "c"], "covers": ["FR-1"]},
        ])
        t1, t6 = ac_test("STORY-02-01", 1), ac_test("STORY-06-01", 1)
        self.run_tests("STORY-02-01", ids=[t1])
        # Như kho thật: story sau đã đóng băng ứng viên, lần chạy không mang SHA.
        JournalStore(self.root).record("STORY-06-01", Entry(
            step="candidate.frozen", attempt=1, data={"sha": "a" * 40}))
        self.run_tests("STORY-06-01", ids=[t1, t6])   # xanh hết; tiêu chí 2 không có test
        led = L.build(self.root)
        self.assertEqual(led.behaviors["AC-STORY-06-01-2"].gap_kind, L.UNTESTED,
                         "vắng mặt phải ở tiêu chí của chính story sau")
        self.assertEqual(led.behaviors["FR-1"].status, L.VERIFIED)
        self.assertEqual(led.summary()["reopen_events"], 0)

    def test_su_kien_behavior_do_pha_khac_ghi_cung_vao_so(self):
        self.index([{"id": "STORY-01-01", "acceptance_criteria": ["a"]}])
        self.run_tests("STORY-01-01", ids=[ac_test("STORY-01-01", 1)])
        self.store.behavior("STORY-01-01", id="AC-STORY-01-01-1", status="gap",
                            candidate="abc1234", source={"reviewer": "chặn"})
        led = L.build(self.root)
        b = led.behaviors["AC-STORY-01-01-1"]
        self.assertEqual(b.status, L.REOPENED)
        self.assertEqual(b.source["reviewer"], "chặn")

    def test_evidence_cu_khong_co_candidate_van_chieu_duoc(self):
        """R1 do luồng khác làm; bằng chứng hôm nay không có SHA."""
        self.index([{"id": "STORY-01-01", "acceptance_criteria": ["a"]}])
        self.run_tests("STORY-01-01", ids=[ac_test("STORY-01-01", 1)])
        led = L.build(self.root)
        self.assertEqual(led.behaviors["AC-STORY-01-01-1"].candidate, "")
        self.assertEqual(led.summary()["verified"], 1)


class TestMetrics(LedgerTestCase):
    def fake(self) -> L.Ledger:
        led = L.Ledger(root=self.root)
        led.observe("AC-S-1", "ac", ok=True, at=1.0, story="S", attempt=1)
        led.observe("AC-S-2", "ac", ok=False, at=2.0, story="S", attempt=1)
        led.snapshot("loop-1", cost_usd=2.0)
        led.observe("AC-S-2", "ac", ok=True, at=3.0, story="S2", attempt=1)
        led.observe("AC-S-1", "ac", ok=False, at=4.0, story="S2", attempt=2)
        led.snapshot("loop-2", cost_usd=4.0)
        return led

    def test_growth_reopened_resolved(self):
        m = self.fake().metrics()
        self.assertEqual([g["verified"] for g in m["growth"]], [1, 2])
        self.assertEqual(m["ever_verified"], 2)
        self.assertEqual(m["resolved"], 1)
        self.assertEqual(m["reopen_events"], 1)
        self.assertEqual(m["reopen_rate"], 0.5)

    def test_cai_thien_bien_giua_hai_moc(self):
        loops = self.fake().metrics()["loops"]
        self.assertEqual(loops[0]["marginal"], (1 - 0) / 2.0)
        # vòng 2: VERIFIED 1→1 (một cái đóng, một cái hỏng), REOPENED 0→1
        self.assertEqual(loops[1]["d_verified"], 0)
        self.assertEqual(loops[1]["d_reopened"], 1)
        self.assertEqual(loops[1]["marginal"], (0 - 1) / 4.0)

    def test_khong_co_chi_phi_thi_khong_co_mau_so(self):
        led = L.Ledger(root=self.root)
        led.observe("AC-S-1", "ac", ok=True, at=1.0, story="S")
        led.snapshot("loop-1", cost_usd=0.0)
        self.assertIsNone(led.metrics()["loops"][0]["marginal"])

    def test_moc_vong_khong_bi_mat_khi_chieu_lai(self):
        """`aisef report` chiếu lại sổ mỗi lần; mốc mà vòng cải tiến vừa
        chốt là thứ duy nhất không suy lại được, nên phải sống sót."""
        self.index([{"id": "STORY-01-01", "acceptance_criteria": ["a"]}])
        led = L.build(self.root)
        led.snapshot("loop-1", cost_usd=3.0)
        led.write(self.root)
        self.assertEqual([lo["n"] for lo in L.build(self.root).loops], ["loop-1"])

    def test_snapshot_ghi_vao_ledger_json(self):
        led = self.fake()
        led.write(self.root)
        data = json.loads((self.root / L.LEDGER_FILE).read_text(encoding="utf-8"))
        self.assertEqual(data["version"], L.VERSION)
        self.assertEqual([lo["n"] for lo in data["loops"]], ["loop-1", "loop-2"])
        self.assertIn("history", data["behaviors"]["AC-S-1"])


class TestChiMuc(LedgerTestCase):
    def build_two_epics(self) -> L.Ledger:
        self.index([
            {"id": "STORY-01-01", "epic_id": "EPIC-01", "acceptance_criteria": ["a"]},
            {"id": "STORY-01-02", "epic_id": "EPIC-01", "acceptance_criteria": ["b"]},
            {"id": "STORY-02-01", "epic_id": "EPIC-02", "acceptance_criteria": ["c"]},
        ])
        self.run_tests("STORY-01-01", ids=[ac_test("STORY-01-01", 1)])
        return L.build(self.root)

    def test_toi_da_mot_dong_moi_story_va_mot_dong_moi_epic(self):
        led = self.build_two_epics()
        lines = led.index_lines()
        self.assertEqual(len(lines), 3 + 2)          # 3 story + 2 epic
        self.assertEqual(sum(1 for l in lines if l.startswith("## ")), 2)

    def test_dong_story_co_du_trang_thai_candidate_so_hanh_vi_va_duong_dan(self):
        led = self.build_two_epics()
        line = next(l for l in led.index_lines() if "STORY-01-01" in l)
        self.assertIn("V1 G0 R0", line)
        self.assertIn("evidence/STORY-01-01.jsonl", line)

    def test_index_ghi_ra_file(self):
        led = self.build_two_epics()
        path = led.index(self.root)
        self.assertTrue(path.name == L.INDEX_FILE)
        self.assertIn("EPIC-02", path.read_text(encoding="utf-8"))

    def test_lat_cat_epic_chi_lay_epic_do_va_co_tran(self):
        led = self.build_two_epics()
        slice_ = led.epic_slice("EPIC-01")
        self.assertIn("STORY-01-02", slice_)
        self.assertNotIn("STORY-02-01", slice_)
        cut = led.epic_slice("EPIC-01", max_chars=40)
        self.assertLessEqual(len(cut), 40 + 80)      # phần cắt có ghi chú
        self.assertIn("truncated", cut)


class TestSlotIndexTrongPrompt(LedgerTestCase):
    def test_slot_index_co_nguon_ledger_va_ton_tran(self):
        from aisef.config import Config
        from aisef.control.normalize import Story
        from aisef.phases.implement import SLOT_SOURCE, build_context, handoff_slots

        self.assertEqual(SLOT_SOURCE["index"], "ledger")
        self.index([{"id": "STORY-01-01", "epic_id": "EPIC-01",
                     "acceptance_criteria": ["a"]}])
        for i in range(30):
            self.store.tool_run(f"STORY-01-{i:02d}", "test", ok=True,
                                detail={"tail": "x" * 50})

        story = Story(id="STORY-01-01", epic_id="EPIC-01", title="t")
        cfg = Config.load(self.root.parent)
        cfg.values["context.max_index_chars"] = 120
        ctx = build_context(story, project=self.root.parent, artifact_root=self.root,
                            architecture=None, contract=None, config=cfg)
        self.assertLessEqual(len(ctx["index"]), 120 + 80)
        self.assertEqual(handoff_slots(ctx)["index"][0], "ledger")

    def test_chua_co_bang_chung_thi_slot_noi_that(self):
        from aisef.control.normalize import Story
        from aisef.phases.implement import build_context

        story = Story(id="STORY-09-01", epic_id="EPIC-09", title="t")
        ctx = build_context(story, project=self.root.parent, artifact_root=self.root,
                            architecture=None, contract=None, config=None)
        self.assertIn("no evidence yet", ctx["index"])


class TestCliEvidence(LedgerTestCase):
    def seed(self):
        self.index([{"id": "STORY-01-01", "epic_id": "EPIC-01",
                     "acceptance_criteria": ["a"]},
                    {"id": "STORY-01-02", "epic_id": "EPIC-01",
                     "acceptance_criteria": ["b"]}])
        t1 = ac_test("STORY-01-01", 1)
        self.run_tests("STORY-01-01", ids=[t1])
        self.run_tests("STORY-01-02", ids=[t1, ac_test("STORY-01-02", 1)],
                       failed=[t1], attempt=2)

    def test_tra_mot_hanh_vi_in_ra_lich_su(self):
        self.seed()
        code, out, _ = self.run_cli("evidence", "AC-STORY-01-01-1")
        self.assertEqual(code, 0)
        self.assertIn("REOPENED", out)
        self.assertIn("STORY-01-02#2", out)
        self.assertEqual(out.count("verified"), 1)   # dòng lịch sử đầu tiên

    def test_tra_mot_story_in_dong_chi_muc_va_hanh_vi_cua_no(self):
        self.seed()
        code, out, _ = self.run_cli("evidence", "STORY-01-01")
        self.assertEqual(code, 0)
        self.assertIn("evidence/STORY-01-01.jsonl", out)
        self.assertIn("AC-STORY-01-01-1", out)

    def test_id_khong_co_thi_bao_khong_biet_chu_khong_im(self):
        self.seed()
        code, _, err = self.run_cli("evidence", "AC-KHONG-CO-1")
        self.assertEqual(code, 2)
        self.assertIn("no story or behaviour", err)

    def test_co_story_thi_ghi_bang_chung_evidence_lookup(self):
        self.seed()
        self.run_cli("evidence", "AC-STORY-01-01-1", "--story", "STORY-01-02")
        notes = [e for e in self.store.read("STORY-01-02").events if e.name == "evidence_lookup"]
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0].detail["id"], "AC-STORY-01-01-1")


class TestXuatBangGap(LedgerTestCase):
    """`aisef issues` (ADR-004 R12): sổ ra bảng để theo dõi ngoài kho.

    Bảng là phép chiếu thứ hai của cùng một sổ — nó không được nói khác
    `aisef evidence`: cùng thủ phạm, cùng nguồn kiểm, cùng số lần đổi.
    """

    def seed(self):
        self.index([
            {"id": "STORY-01-01", "epic_id": "EPIC-01", "acceptance_criteria": ["a"]},
            {"id": "STORY-01-02", "epic_id": "EPIC-01", "acceptance_criteria": ["b", "c"]},
            {"id": "STORY-02-01", "epic_id": "EPIC-02", "acceptance_criteria": ["d"]},
        ])
        t1 = ac_test("STORY-01-01", 1)
        self.run_tests("STORY-01-01", ids=[t1])
        # 01-02 làm đỏ tiêu chí của 01-01, và chính nó thiếu test cho tiêu chí 2.
        self.run_tests("STORY-01-02", ids=[t1, ac_test("STORY-01-02", 1)],
                       failed=[t1], attempt=2, candidate="deadbeefcafe")
        self.store.tool_run("STORY-02-01", "qa:e2e", ok=False, detail={"tail": "đỏ"})

    def test_mac_dinh_xuat_md_gap_va_hoi_quy_hoi_quy_len_dau(self):
        self.seed()
        code, out, _ = self.run_cli("issues")
        self.assertEqual(code, 0)
        path = self.root / "ISSUES.md"
        self.assertIn(str(path.resolve()), out)   # Windows tmp is an 8.3 alias
        text = path.read_text(encoding="utf-8")
        rows = [l for l in text.splitlines() if l.startswith("| AC-") or l.startswith("| qa:")]
        self.assertEqual(len(rows), 3)                         # 01-01-1 · 01-02-2 · qa:e2e
        self.assertTrue(rows[0].startswith("| AC-STORY-01-01-1 | ac | reopened | STORY-01-01 "
                                           "| STORY-01-02#2@deadbee | src/x.ts"))
        self.assertIn("| 2 |", rows[0])                        # verified → reopened: 2 lần đổi
        self.assertIn("| AC-STORY-01-02-2 | ac | gap | STORY-01-02 |  |  | no test carries this code", text)
        self.assertIn("| qa:e2e | qa | gap | STORY-02-01 |  | qa:e2e |", text)
        self.assertNotIn("| verified |", text)

    def test_csv_chuan_doc_lai_duoc_cung_cot_voi_md(self):
        import csv

        self.seed()
        self.run_cli("issues", "--format", "csv")
        with (self.root / "ISSUES.csv").open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(tuple(rows[0].keys()), L.ISSUE_COLUMNS)
        self.assertEqual(rows[0]["regressed_by"], "STORY-01-02#2@deadbee")
        self.assertEqual({r["status"] for r in rows}, {"reopened", "gap"})

    def test_loc_epic_va_trang_thai(self):
        self.seed()
        out = self.root / "x.md"
        self.run_cli("issues", "--epic", "EPIC-02", "--out", str(out))
        text = out.read_text(encoding="utf-8")
        self.assertIn("qa:e2e", text)
        self.assertNotIn("STORY-01-", text)

        self.run_cli("issues", "--status", "reopened", "--out", str(out))
        self.assertIn("· 1 behaviours", out.read_text(encoding="utf-8"))

        self.run_cli("issues", "--status", "verified,gap", "--out", str(out))
        self.assertIn("| AC-STORY-01-02-1 | ac | verified |", out.read_text(encoding="utf-8"))

    def test_trang_thai_sai_thi_bao_loi_khong_xuat_tep_rong(self):
        self.seed()
        code, _, err = self.run_cli("issues", "--status", "gap,done")
        self.assertEqual(code, 1)
        self.assertIn("done", err)
        self.assertFalse((self.root / "ISSUES.md").exists())


if __name__ == "__main__":
    unittest.main()


class TestUngVienChuaLanded(LedgerTestCase):
    """Xanh ở ứng viên chưa vào nhánh chính không phải VERIFIED (ADR-004 R1×R2).

    Đo 2026-09-06 trên client giả của R3: lượt story sửa trượt cổng — test
    xanh trong worktree, reviewer chặn — vẫn làm hành vi gốc VERIFIED.
    """

    def setUp(self):
        super().setUp()
        from aisef.control.journal import Entry, JournalStore
        self.index([{"id": "STORY-01-01", "epic_id": "EPIC-01",
                     "acceptance_criteria": ["a"], "covers": ["FR-1"]}])
        self.journal = JournalStore(self.root)
        self.Entry = Entry

    def freeze(self, sha, *, attempt=1, committed=False):
        self.journal.record("STORY-01-01", self.Entry(step="candidate.frozen", attempt=attempt,
                                                       data={"sha": sha}))
        # `attempt.committed` chỉ đóng giao dịch (có cả khi trượt); landed là `merge.completed`.
        self.journal.record("STORY-01-01", self.Entry(step="attempt.committed", attempt=attempt))
        if committed:
            self.journal.record("STORY-01-01", self.Entry(step="merge.completed", attempt=attempt))

    def status(self, value):
        (self.root / "sprint-status.json").write_text(
            json.dumps({"stories": {"STORY-01-01": {"status": value}}}), encoding="utf-8")

    def test_xanh_o_ung_vien_bi_cong_tra_ve_khong_thanh_verified(self):
        self.freeze("aaa1111")
        self.run_tests("STORY-01-01", ids=[ac_test("STORY-01-01", 1)], candidate="aaa1111")
        led = L.build(self.root)
        self.assertEqual(led.behaviors["AC-STORY-01-01-1"].status, L.GAP)
        self.assertEqual(led.behaviors["FR-1"].status, L.GAP)
        self.assertIn("unlanded", led.behaviors["AC-STORY-01-01-1"].source.get("why", ""))
        self.assertEqual(led.summary()["unlanded_green"], 2)

    def test_landed_roi_thi_verified_va_do_o_ung_vien_chua_landed_van_tinh(self):
        self.freeze("aaa1111")
        self.run_tests("STORY-01-01", ids=[ac_test("STORY-01-01", 1)], candidate="aaa1111")
        self.freeze("bbb2222", committed=True)
        self.run_tests("STORY-01-01", ids=[ac_test("STORY-01-01", 1)], candidate="bbb2222")
        led = L.build(self.root)
        self.assertEqual(led.behaviors["AC-STORY-01-01-1"].status, L.VERIFIED)
        self.assertEqual(led.behaviors["AC-STORY-01-01-1"].candidate, "bbb2222")
        # Lượt sau làm đỏ ở ứng viên chưa landed: vẫn là hồi quy — không tin client.
        self.freeze("ccc3333", attempt=2)
        self.run_tests("STORY-01-01", ids=[ac_test("STORY-01-01", 1)],
                       failed=[ac_test("STORY-01-01", 1)], attempt=2, candidate="ccc3333")
        led = L.build(self.root)
        self.assertEqual(led.behaviors["AC-STORY-01-01-1"].status, L.REOPENED)

    def test_xanh_truoc_khi_dong_bang_khong_thanh_verified(self):
        """Lỗi 26 (par B3, 2026-09-06): agent tự chạy test giữa phiên — bằng chứng
        mang story id nhưng chưa có candidate — xanh ở đó làm 3 hành vi của story
        **trượt**, chưa merge, thành VERIFIED; story sau chạm tệp phải "bảo toàn"
        thứ chưa từng lên main."""
        self.run_tests("STORY-01-01", ids=[ac_test("STORY-01-01", 1)])   # giữa phiên
        self.freeze("aaa1111")
        self.run_tests("STORY-01-01", ids=[ac_test("STORY-01-01", 1)], candidate="aaa1111")
        self.status("failed")
        led = L.build(self.root)
        self.assertEqual(led.behaviors["AC-STORY-01-01-1"].status, L.GAP)
        self.assertEqual(led.behaviors["FR-1"].status, L.GAP)
        self.assertEqual(led.summary()["unlanded_green"], 4)
        # Đỏ giữa phiên vẫn tính — không tin client.
        self.status("done")
        self.assertEqual(L.build(self.root).behaviors["AC-STORY-01-01-1"].status, L.VERIFIED)
        self.journal.record("STORY-01-01", self.Entry(step="merge.completed", attempt=1))
        self.freeze("bbb2222", attempt=2)
        self.run_tests("STORY-01-01", ids=[ac_test("STORY-01-01", 1)],
                       failed=[ac_test("STORY-01-01", 1)], attempt=2)   # giữa phiên lượt 2
        self.assertEqual(L.build(self.root).behaviors["AC-STORY-01-01-1"].status, L.REOPENED)

    def test_bang_chung_khong_co_nhat_ky_hay_khong_co_candidate_van_tinh_nhu_cu(self):
        # Không nhật ký (QA cấp dự án) hoặc evidence cũ không khai bản: giữ luật cũ.
        self.run_tests("STORY-01-01", ids=[ac_test("STORY-01-01", 1)])
        self.assertEqual(L.build(self.root).behaviors["AC-STORY-01-01-1"].status, L.VERIFIED)

    def test_story_done_thi_ung_vien_cuoi_landed_du_khong_merge(self):
        # Chạy thẳng trong dự án (`--no-isolate`): không có merge, nhưng story đã done.
        self.freeze("aaa1111")
        self.freeze("bbb2222", attempt=2)
        self.run_tests("STORY-01-01", ids=[ac_test("STORY-01-01", 1)], candidate="aaa1111")
        self.run_tests("STORY-01-01", ids=[ac_test("STORY-01-01", 1)], attempt=2, candidate="bbb2222")
        self.status("failed")
        self.assertEqual(L.build(self.root).behaviors["AC-STORY-01-01-1"].status, L.GAP)
        self.status("done")
        led = L.build(self.root)
        self.assertEqual(led.behaviors["AC-STORY-01-01-1"].status, L.VERIFIED)
        self.assertEqual(led.behaviors["AC-STORY-01-01-1"].candidate, "bbb2222")

    def test_qua_cong_o_ung_vien_thi_landed_du_chua_merge(self):
        from aisef.harness.observe import Event, NOTE
        self.freeze("aaa1111")
        self.run_tests("STORY-01-01", ids=[ac_test("STORY-01-01", 1)], candidate="aaa1111")
        self.store.record("STORY-01-01", Event(kind=NOTE, name="gate:verdict", ok=True,
                                               detail={"candidate": "aaa1111"}))
        self.assertEqual(L.build(self.root).behaviors["AC-STORY-01-01-1"].status, L.VERIFIED)



class TestTruyVetNguoiKhai(LedgerTestCase):
    """`aisef evidence <AC> --link` (QĐ B6 2026-09-06): sửa siêu dữ liệu —
    tên test có sẵn chứng minh tiêu chí. Sổ vẫn đòi test ấy xanh ở ứng viên
    đã landed; không ai ghi thẳng VERIFIED."""

    CU = "src/x.test.js > khởi động đọc được a"

    def setUp(self):
        super().setUp()
        self.index([{"id": "STORY-01-01", "epic_id": "EPIC-01", "acceptance_criteria": ["a"]}])

    def link(self, **over):
        (self.root / L.TRACE_FILE).write_text(json.dumps({
            "AC-STORY-01-01-1": {"test_id": self.CU, "why": "test đọc a từ đầu", "by": "nghi",
                                 **over}}, ensure_ascii=False), encoding="utf-8")

    def test_chua_khai_thi_gap_khai_roi_thi_verified_kem_nguon_truy_vet(self):
        self.run_tests("STORY-01-01", ids=[self.CU])
        self.assertEqual(L.build(self.root).behaviors["AC-STORY-01-01-1"].status, L.GAP)
        self.link()
        b = L.build(self.root).behaviors["AC-STORY-01-01-1"]
        self.assertEqual(b.status, L.VERIFIED)
        self.assertEqual(b.source["test_id"], self.CU)
        self.assertEqual(b.source["via"], "traceability")
        self.assertEqual(b.source["by"], "nghi")

    def test_test_da_khai_ma_do_thi_van_gap(self):
        self.link()
        self.run_tests("STORY-01-01", ids=[self.CU], failed=[self.CU])
        self.assertEqual(L.build(self.root).behaviors["AC-STORY-01-01-1"].status, L.GAP)

    def test_khai_test_khong_co_trong_lan_chay_thi_khong_noi_gi(self):
        self.link(test_id="src/khac.test.js > không tồn tại")
        self.run_tests("STORY-01-01", ids=[self.CU])
        b = L.build(self.root).behaviors["AC-STORY-01-01-1"]
        self.assertEqual(b.status, L.GAP)
        self.assertNotIn("via", b.source)

    def test_cli_link_can_why_va_ghi_tep(self):
        self.run_tests("STORY-01-01", ids=[self.CU])
        code, _out, err = self.run_cli("evidence", "AC-STORY-01-01-1", "--link", self.CU)
        self.assertNotEqual(code, 0)
        self.assertIn("--why", err)
        code, out, _err = self.run_cli("evidence", "AC-STORY-01-01-1", "--link", self.CU,
                                       "--why", "test đọc a từ đầu", "--by", "nghi")
        self.assertEqual(code, 0, out)
        data = json.loads((self.root / L.TRACE_FILE).read_text(encoding="utf-8"))
        self.assertEqual(data["AC-STORY-01-01-1"]["by"], "nghi")
        self.assertIn("VERIFIED", out)


class TestLoaiGap(LedgerTestCase):
    """ADR-009 O2: sổ ghi "là GAP" mà không ghi **loại** vắng mặt nào.

    Ba sự vắng mặt khác nhau cùng bị ghi là GAP: hành vi chưa được xây
    (`unbuilt`), hành vi có mà không test nào chạm tới (`untested`), và harness
    không nối được hành vi → test (`untraced`). Chỉ loại đầu đáng một story sửa
    có trả phí. Loại được **chiếu** từ `source.why` — đúng bộ câu mà chính sổ
    viết ra — chứ không đoán.
    """

    def setUp(self):
        super().setUp()
        self.index([{"id": "STORY-01-01", "epic_id": "EPIC-01",
                     "acceptance_criteria": ["a", "b"]}])

    def kind_of(self, bid: str) -> str:
        return L.build(self.root).behaviors[bid].gap_kind

    def test_test_do_la_unbuilt(self):
        t = ac_test("STORY-01-01", 1)
        self.run_tests("STORY-01-01", ids=[t], failed=[t])
        self.assertEqual(self.kind_of("AC-STORY-01-01-1"), L.UNBUILT)

    def test_khong_co_test_mang_ma_la_untested(self):
        self.run_tests("STORY-01-01", ids=[ac_test("STORY-01-01", 1)])
        self.assertEqual(self.kind_of("AC-STORY-01-01-2"), L.UNTESTED)

    def test_khong_doc_duoc_ten_test_la_untraced(self):
        self.store.tool_run("STORY-01-01", "test", ok=True, detail={"tail": "1 passed"})
        self.assertEqual(self.kind_of("AC-STORY-01-01-1"), L.UNTRACED)

    def test_khai_truy_vet_ma_test_khong_chay_la_untraced(self):
        (self.root / L.TRACE_FILE).write_text(json.dumps({
            "AC-STORY-01-01-2": {"test_id": "src/khac.test.js > không chạy",
                                 "why": "đã chứng minh", "by": "nghi"}},
            ensure_ascii=False), encoding="utf-8")
        self.run_tests("STORY-01-01", ids=[ac_test("STORY-01-01", 1)])
        b = L.build(self.root).behaviors["AC-STORY-01-01-2"]
        self.assertEqual(b.gap_kind, L.UNTRACED)
        self.assertIn("src/khac.test.js", b.source["why"])

    def test_xanh_o_ung_vien_chua_landed_la_unbuilt(self):
        """Test có, xanh, nhưng trên ứng viên không bao giờ landed: trên nhánh
        chính không có gì chứng minh hành vi — `unbuilt`, không phải untested."""
        t = ac_test("STORY-01-01", 1)
        self.run_tests("STORY-01-01", ids=[t], candidate="a" * 40)
        (self.root / "journal").mkdir(exist_ok=True)
        (self.root / "journal" / "STORY-01-01.jsonl").write_text(
            json.dumps({"step": "candidate.frozen", "data": {"sha": "a" * 40}}) + "\n",
            encoding="utf-8")
        b = L.build(self.root).behaviors["AC-STORY-01-01-1"]
        self.assertEqual(b.status, L.GAP)
        self.assertEqual(b.gap_kind, L.UNBUILT)

    def test_yeu_cau_thua_huong_loai_gap_cua_tieu_chi(self):
        """FR/NFR đỏ **qua** tiêu chí của nó: mọi tiêu chí non-green cùng một lý do
        thì yêu cầu cũng cùng loại ấy. Lý do lẫn lộn thì về `unbuilt` — phía đắt,
        không bao giờ phía rẻ. Đo trên bốn kho dogfood: chuyển 1 trong 18 gap
        mức yêu cầu (todo-cli FR-9)."""
        self.index([{"id": "STORY-01-01", "epic_id": "EPIC-01",
                     "acceptance_criteria": ["a", "b"], "covers": ["FR-1"]},
                    {"id": "STORY-01-02", "epic_id": "EPIC-01",
                     "acceptance_criteria": ["c", "d"], "covers": ["FR-2"]}])
        # 01-01: cả hai tiêu chí chỉ thiếu test → FR-1 untested.
        self.run_tests("STORY-01-01", ids=["src/x.ts > không mang mã"])
        # 01-02: một tiêu chí có test đỏ, một chỉ thiếu test → lẫn lộn → FR-2 unbuilt.
        t = ac_test("STORY-01-02", 1)
        self.run_tests("STORY-01-02", ids=[t], failed=[t])
        led = L.build(self.root)
        self.assertEqual(led.behaviors["FR-1"].gap_kind, L.UNTESTED)
        self.assertEqual(led.behaviors["FR-2"].gap_kind, L.UNBUILT)

    def test_ly_do_gap_khong_duoc_cu_khi_bang_chung_moi_noi_khac(self):
        """Nguồn của gap phải là lý do **mới nhất**: gap thiếu test mà lượt sau
        có test đỏ là một sự vắng mặt khác, cách sửa khác — sổ giữ lý do cũ thì
        hàng đợi cứ mở story chỉ-viết-test mãi."""
        self.run_tests("STORY-01-01", ids=["src/x.ts > không mang mã"])
        self.assertEqual(self.kind_of("AC-STORY-01-01-1"), L.UNTESTED)
        t = ac_test("STORY-01-01", 1)
        self.run_tests("STORY-01-01", ids=[t], failed=[t], attempt=2)
        b = L.build(self.root).behaviors["AC-STORY-01-01-1"]
        self.assertEqual(b.status, L.GAP, "vẫn là GAP, không có chuyển trạng thái")
        self.assertEqual(len(b.history), 1, "không ghi lịch sử vì trạng thái không đổi")
        self.assertEqual(b.gap_kind, L.UNBUILT)
        self.assertEqual(b.source["test_id"], t)

    def test_verified_thi_khong_co_loai_gap(self):
        self.run_tests("STORY-01-01", ids=[ac_test("STORY-01-01", 1)])
        self.assertEqual(self.kind_of("AC-STORY-01-01-1"), "")

    def test_bang_issues_dem_ba_loai_rieng(self):
        t1 = ac_test("STORY-01-01", 1)
        self.run_tests("STORY-01-01", ids=[t1], failed=[t1])     # 1 unbuilt · 1 untested
        code, out, _ = self.run_cli("issues")
        self.assertEqual(code, 0, out)
        self.assertIn("unbuilt 1", out)
        self.assertIn("untested 1", out)
        self.assertIn("untraced 0", out)
        text = (self.root / "ISSUES.md").read_text(encoding="utf-8")
        self.assertIn("gap_kind", text)
        self.assertIn("| unbuilt |", text)
        self.assertIn("| untested |", text)

    def test_loai_gap_vao_ledger_json_va_cot_csv(self):
        import csv

        self.run_tests("STORY-01-01", ids=[ac_test("STORY-01-01", 1)])
        led = L.build(self.root)
        self.assertEqual(led.as_dict()["behaviors"]["AC-STORY-01-01-2"]["gap_kind"], L.UNTESTED)
        self.assertNotIn("gap_kind", led.as_dict()["behaviors"]["AC-STORY-01-01-1"])
        self.run_cli("issues", "--format", "csv")
        with (self.root / "ISSUES.csv").open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(tuple(rows[0].keys()), L.ISSUE_COLUMNS)
        self.assertEqual(rows[0]["gap_kind"], L.UNTESTED)

    def test_summary_mang_ba_so_va_dem_ca_reopened(self):
        """`summary()` là chỗ `aisef report` và dashboard đọc; thiếu ba số ở đây
        thì hai bản báo cáo ấy chỉ in một con số `gap`.

        Ba số đếm **mọi** hành vi non-green, kể cả REOPENED — nên chúng cộng lại
        bằng `gap + reopened`, *không* bằng `gap`: bốn kho dogfood có 32 gap + 17
        reopened = 49 = 40 + 4 + 5.
        """
        t1 = ac_test("STORY-01-01", 1)
        self.run_tests("STORY-01-01", ids=[t1])                            # 1 xanh, 2 thiếu test
        self.run_tests("STORY-01-01", ids=[t1], failed=[t1], attempt=2)    # 1 đỏ lại
        s = L.build(self.root).summary()
        self.assertEqual((s["gap"], s["reopened"]), (1, 1))
        self.assertEqual(s["gap_kinds"], {L.UNBUILT: 1, L.UNTESTED: 1, L.UNTRACED: 0})
        self.assertEqual(sum(s["gap_kinds"].values()), s["gap"] + s["reopened"])

    def test_report_che_ba_so_chi_khi_corpus_co_hon_mot_loai(self):
        """`aisef report` phải nói loại vắng mặt nào — nhưng chỉ khi có hơn một
        loại. Một dòng `unbuilt 2 · untested 0 · untraced 0` đọc thành "đã chẻ
        rồi mà không thấy gì" (cùng quy ước với `reviewer_qual.report` và mục
        token của báo cáo bench)."""
        self.run_tests("STORY-01-01", ids=["src/x.ts > không mang mã"])     # cả hai untested
        code, out, err = self.run_cli("report")
        self.assertIn("behaviour ledger", out + err)
        self.assertNotIn("untested", out, "một loại duy nhất: không được chẻ")
        t1 = ac_test("STORY-01-01", 1)
        self.run_tests("STORY-01-01", ids=[t1], failed=[t1], attempt=2)     # thêm 1 unbuilt
        code, out, err = self.run_cli("report")
        self.assertIn("unbuilt 1", out)
        self.assertIn("untested 1", out)
        self.assertNotIn("untraced", out, "loại đếm 0 không có gì để nói")


class TestKhongDocDuocKhongPhaiHoiQuy(LedgerTestCase):
    """D-001 — cùng lớp với dòng phân loại 155 (vắng mặt bị đọc thành hồi quy),
    ở đúng nhánh mà bản sửa ấy không phủ.

    `_observe_tests`, khi `readable` là sai (không có reporter, suite không chạy
    được, runner ghi chú), gọi `rollup(line, False, why)` cho story chủ nhà — nên
    **mọi** requirement story ấy `covers` bị ghi là không-xanh, mà những
    requirement ấy do các story **trước** sở hữu và đã VERIFIED. Không một phép
    thử đỏ nào được đọc ở đâu cả.

    Đo trên corpus `todo`: FR-1, FR-2, FR-4 (của STORY-02-01) và FR-9 (của
    STORY-01-02) cùng lật sang REOPENED do một lượt của STORY-02-02 mà `test`
    tool_run có `ok=True`.

    Vì sao nó tệ hơn một dòng báo sai: vòng lặp tự tính theo Δverified − Δreopened
    để quyết định có đi tiếp, nên số học của nó bị bẩn; và chỉ người đọc đối chiếu
    sổ với bằng chứng mới phân biệt được hiện vật này với một hồi quy thật.
    """

    def setUp(self):
        super().setUp()
        self.index([
            {"id": "STORY-01-01", "epic_id": "EPIC-01",
             "acceptance_criteria": ["a"], "covers": ["FR-1"]},
            {"id": "STORY-01-02", "epic_id": "EPIC-01",
             "acceptance_criteria": ["b"], "covers": ["FR-1"]},
        ])

    def khong_doc_duoc(self, story, **d):
        """Một lượt `test` **xanh** mà không đọc được tên phép thử nào."""
        self.store.tool_run(story, "test", ok=True,
                            detail={"test_ids": [], "failed_ids": [], **d})

    def test_lot_khong_doc_duoc_khong_lam_requirement_cua_story_khac_reopened(self):
        # STORY-01-01 chứng minh FR-1 trước.
        self.run_tests("STORY-01-01", ids=[ac_test("STORY-01-01", 1)])
        self.assertEqual(L.build(self.root).behaviors["FR-1"].status, L.VERIFIED)
        # STORY-01-02 chạy, xanh, nhưng không đọc được tên nào.
        self.khong_doc_duoc("STORY-01-02", test_note="reporter printed no names")
        led = L.build(self.root)
        self.assertEqual(led.behaviors["FR-1"].status, L.VERIFIED,
                         "FR-1 do STORY-01-01 sở hữu và không có gì đỏ được đọc")

    def test_tieu_chi_cua_chinh_story_ay_van_la_gap_co_ly_do(self):
        """Không đọc được tên thì tiêu chí của **chính** story ấy vẫn chưa được
        chứng minh — cái bị bỏ là việc lật requirement của người khác, không phải
        việc ghi nhận rằng story này chưa chứng minh được gì."""
        self.khong_doc_duoc("STORY-01-02", test_note="reporter printed no names")
        b = L.build(self.root).behaviors["AC-STORY-01-02-1"]
        self.assertEqual(b.status, L.GAP)
        self.assertIn("cannot read test names", b.source.get("why", ""))

    def test_mot_phep_thu_do_that_van_lam_reopened(self):
        """Phép kiểm âm: bỏ `rollup` ở nhánh không-đọc-được không được làm mất
        khả năng phát hiện hồi quy thật."""
        self.run_tests("STORY-01-01", ids=[ac_test("STORY-01-01", 1)])
        self.assertEqual(L.build(self.root).behaviors["FR-1"].status, L.VERIFIED)
        self.run_tests("STORY-01-02", ids=[ac_test("STORY-01-01", 1)],
                       failed=[ac_test("STORY-01-01", 1)])
        self.assertEqual(L.build(self.root).behaviors["FR-1"].status, L.REOPENED)
