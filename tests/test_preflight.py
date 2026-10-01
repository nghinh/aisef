"""Story chạy được không — chấm bằng code, trước khi gọi model.

Mọi ca ở đây là một thế bí **đã xảy ra thật** trên dự án e9, hoặc là
mặt trái của nó: cổng báo thiếu oan sẽ chặn một story chạy được, đắt
ngang bỏ sót.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.config import DEFAULTS, Config  # noqa: E402
from aisef.control.normalize import Story  # noqa: E402
from aisef.control.preflight import (  # noqa: E402
    STORY_NOT_EXECUTABLE,
    check_stories_executable,
    check_story,
    provisioned,
    required_capabilities,
)


from tests import obligations


class PreflightTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)
        (self.project / "package.json").write_text(
            json.dumps({"devDependencies": {"vitest": "^3"}}), encoding="utf-8"
        )

    def tearDown(self):
        self._tmp.cleanup()

    def config(self, **over):
        return Config({
            **DEFAULTS,
            "tools.test": "npm test",
            "tools.lint": "npx tsc --noEmit",
            **over,
        })

    def story(self, **kw):
        base = dict(
            id="STORY-01-01", epic_id="EPIC-01", title="Story",
            acceptance_criteria=["Then chuyện gì đó xảy ra"],
            write_scope=["src/a.ts"],
        )
        base.update(kw)
        st = Story(**base)
        st.ac_proof = obligations(st.id, len(st.acceptance_criteria))
        return st

    def check(self, story, **cfg):
        return check_story(story, project=self.project, config=self.config(**cfg))

    def caps(self, pf):
        return {m.capability for m in pf.missing}

    def contract(self, *screens):
        d = self.project / "_bmad-output"
        d.mkdir(exist_ok=True)
        (d / "design-contract.json").write_text(
            json.dumps({"screens": {s: {} for s in screens}}), encoding="utf-8"
        )


class TestWriteScope(PreflightTestCase):
    def test_thieu_write_scope_thi_truot_truoc_khi_goi_model(self):
        """Tiêu chí chấp nhận đòi một tệp chưa tồn tại và không nằm trong
        phạm vi ghi: story không thể thoả tiêu chí của chính nó."""
        pf = self.check(self.story(
            acceptance_criteria=["Then `src/export/csv.ts` sinh ra tệp CSV"],
            write_scope=["src/store/db.ts"],
        ))
        self.assertFalse(pf.executable)
        self.assertIn("write:src/export/csv.ts", self.caps(pf))
        self.assertIn(STORY_NOT_EXECUTABLE, pf.summary())

    def test_tep_da_ton_tai_thi_khong_doi_quyen_ghi(self):
        """Story có thể chỉ **đọc** một tệp đã có. Đòi quyền ghi cho nó là
        báo thiếu oan."""
        (self.project / "src").mkdir()
        (self.project / "src" / "doc-thoi.ts").write_text("x", encoding="utf-8")
        pf = self.check(self.story(
            acceptance_criteria=["Then đọc cấu hình từ `src/doc-thoi.ts`"],
            write_scope=["src/a.ts"],
        ))
        self.assertNotIn("write:src/doc-thoi.ts", self.caps(pf))

    def test_ten_tang_khong_bi_coi_la_duong_dan_thieu(self):
        """Tiêu chí hay gọi tên tầng (`store/`) trong khi phạm vi khai
        đường đầy đủ (`src/store/db.ts`) — hai cái đó là một."""
        pf = self.check(self.story(
            acceptance_criteria=["Then `store/` commit trong đúng một giao dịch"],
            write_scope=["src/store/db.ts"],
        ))
        self.assertNotIn("write:store/", self.caps(pf))

    def test_goi_chua_khai_doi_quyen_ghi_manifest(self):
        """Thế bí STORY-01-02 trên e9: TCCN 7 đòi test trên
        `fake-indexeddb`, phạm vi chỉ có `src/`. Bốn lượt, $10,39."""
        s = self.story(
            acceptance_criteria=["Then `store/` được test trên `fake-indexeddb`"],
            write_scope=["src/store/db.ts"],
        )
        # Không có manifest trên đĩa thì phạm vi có hiệu lực không tự thêm
        # được, và story bí đúng như đã xảy ra.
        (self.project / "package.json").unlink()
        needs = {n.capability for n in required_capabilities(s, project=self.project)}
        self.assertNotIn("manifest-write", needs, "không có manifest thì không kết luận")

        (self.project / "package.json").write_text("{}", encoding="utf-8")
        pf = self.check(s)
        self.assertTrue(pf.executable, "manifest có trên đĩa thì phạm vi tự phủ")

    def test_goi_da_khai_thi_khong_doi_gi(self):
        pf = self.check(self.story(
            acceptance_criteria=["Then test chạy bằng `vitest`"],
            write_scope=["src/a.ts"],
        ))
        self.assertNotIn("manifest-write", self.caps(pf))


class TestKhongBaoOan(PreflightTestCase):
    """Ba luật rút ra từ chính 18 story thật của e9.

    Lần chạy đầu, cổng báo 6/18 story không chạy được; ba trong số đó là
    báo oan. Chặn oan một story chạy được đắt ngang bỏ sót.
    """

    def test_duong_dan_neu_nhu_rang_buoc_khong_doi_quyen_ghi(self):
        """TCCN 2 của STORY-01-01: "tệp trong `src/search/` import React
        thì lệnh dựng thất bại" — nói về thư mục story **không** sở hữu.
        Động từ "dựng" nằm cách đó 90 ký tự."""
        pf = self.check(self.story(acceptance_criteria=[
            "When một tệp trong `src/domain/`, `src/store/` hoặc `src/search/` "
            "import React, hoặc một tầng dưới import ngược lên tầng trên, "
            "Then lệnh dựng thất bại với lỗi rõ ràng chỉ đúng tệp vi phạm"
        ]))
        self.assertEqual(
            {c for c in self.caps(pf) if c.startswith("write:")}, set(), pf.summary()
        )

    def test_dong_tu_tao_ngay_canh_duong_dan_thi_van_bat(self):
        pf = self.check(self.story(
            acceptance_criteria=["Then `src/export/csv.ts` sinh ra tệp CSV"],
            write_scope=["src/a.ts"],
        ))
        self.assertIn("write:src/export/csv.ts", self.caps(pf))

    def test_token_thi_giac_khong_phai_van_de_bao_mat(self):
        """"token" trơn xuất hiện ở gần như mọi story dựng giao diện —
        `token thị giác` của hệ thiết kế là biến CSS."""
        pf = self.check(self.story(acceptance_criteria=[
            "Then toàn bộ token thị giác trong DESIGN.md tồn tại dưới dạng biến CSS"
        ]))
        self.assertNotIn("verify.security", self.caps(pf))

        pf = self.check(
            self.story(acceptance_criteria=["Then token phiên hết hạn sau 30 phút"]),
            **{"security.semantic_review": False},
        )
        self.assertIn("verify.security", self.caps(pf))

    def test_tep_o_thu_muc_khac_van_tinh_la_da_co(self):
        """`DESIGN.md` nằm trong `_bmad-output/`, không ở gốc dự án."""
        d = self.project / "_bmad-output"
        d.mkdir(exist_ok=True)
        (d / "DESIGN.md").write_text("# thiết kế", encoding="utf-8")
        pf = self.check(self.story(
            acceptance_criteria=["Then lớp kiểu được dựng từ `DESIGN.md`"],
        ))
        self.assertNotIn("write:DESIGN.md", self.caps(pf))

    def test_tep_cau_hinh_o_goc_khong_phai_mot_module(self):
        """`vite.config.ts` ở gốc là tệp cấu hình. Đếm nó vào thì mọi story
        dựng nền dự án đều bị coi là thay đổi chéo module."""
        pf = self.check(self.story(
            write_scope=["src/a.ts", "vite.config.ts", "index.html", "bench/x.ts"],
        ))
        self.assertNotIn("code-intelligence", self.caps(pf))

    def test_toan_kho_khong_phai_dau_hieu_thay_doi_cheo(self):
        """Trong tiếng Việt "kho" vừa là kho mã vừa là kho dữ liệu; trên
        e9 nó nằm ở câu **cấm** quét toàn kho IndexedDB."""
        pf = self.check(self.story(acceptance_criteria=[
            "Then không có lần quét toàn kho nào lúc khởi động"
        ]))
        self.assertNotIn("code-intelligence", self.caps(pf))


class TestDuongDanNgoaiDuAn(PreflightTestCase):
    """Lỗi 146. Tiêu chí nêu đường dẫn **dữ liệu lúc chạy** —
    `MARKS_FILE=/tmp/x.json`, "thư mục làm việc là `/foo`" — chứ không phải
    thứ story phải tạo. Đo trên marks-cli 2026-09-14."""

    def setUp(self):
        super().setUp()
        import subprocess
        for args in (["init", "-q"], ["config", "user.email", "t@t"],
                     ["config", "user.name", "T"]):
            subprocess.run(["git", "-C", str(self.project), *args], capture_output=True)
        (self.project / ".gitignore").write_text(".marks.json\n", encoding="utf-8")

    def test_duong_dan_tuyet_doi_khong_doi_quyen_ghi(self):
        pf = self.check(self.story(acceptance_criteria=[
            "Given `MARKS_FILE=/tmp/x.json`, Then Store ghi vào `/tmp/x.json`"
        ]))
        self.assertEqual(
            {c for c in self.caps(pf) if c.startswith("write:")}, set(), pf.summary())

    def test_mot_duong_dan_ngoai_kho_khong_lam_hong_mien_tru_gitignore(self):
        """`git check-ignore --stdin` chết nguyên mẻ (exit 128) khi gặp đường
        dẫn ngoài kho, và người gọi đọc tập rỗng thành "không có gì bị bỏ qua".
        Một tiêu chí nhắc `/tmp/x.json` làm mất luôn miễn trừ của
        `./.marks.json` — thứ `.gitignore` có phủ."""
        pf = self.check(self.story(acceptance_criteria=[
            "Given biến môi trường trỏ tới `/tmp/x.json`, Then Store ghi vào "
            "`/tmp/x.json`, không phải `./.marks.json`"
        ]))
        self.assertEqual(
            {c for c in self.caps(pf) if c.startswith("write:")}, set(), pf.summary())

    def test_duong_dan_trong_kho_van_bat_nhu_cu(self):
        pf = self.check(self.story(
            acceptance_criteria=["Then `src/export/csv.ts` sinh ra tệp CSV"],
            write_scope=["src/a.ts"],
        ))
        self.assertIn("write:src/export/csv.ts", self.caps(pf))


class TestUIStory(PreflightTestCase):
    def test_story_ui_thieu_trinh_duyet_thi_truot(self):
        pf = self.check(self.story(screens=["notes-list"]))
        self.assertFalse(pf.executable)
        self.assertIn("browser", self.caps(pf))

    def test_story_ui_thieu_hop_dong_thi_giac_thi_truot(self):
        pf = self.check(
            self.story(screens=["notes-list"]),
            **{"app.dev_command": "npm run dev", "app.base_url": "http://localhost:5199"},
        )
        self.assertIn("mockup-map", self.caps(pf))

    def test_story_ui_du_dieu_kien_thi_chay_duoc(self):
        self.contract("notes-list")
        pf = self.check(
            self.story(screens=["notes-list"]),
            **{"app.dev_command": "npm run dev", "app.base_url": "http://localhost:5199"},
        )
        self.assertTrue(pf.executable, pf.summary())

    def test_man_hinh_khac_trong_hop_dong_khong_tinh_la_du(self):
        """Có hợp đồng cho màn *khác* không giúp gì cho màn story cần."""
        self.contract("trash")
        pf = self.check(
            self.story(screens=["notes-list"]),
            **{"app.dev_command": "npm run dev", "app.base_url": "http://localhost:5199"},
        )
        self.assertIn("mockup-map", self.caps(pf))

    def test_story_khong_giao_dien_khong_doi_trinh_duyet(self):
        pf = self.check(self.story())
        self.assertNotIn("browser", self.caps(pf))


class TestVerificationTypes(PreflightTestCase):
    def test_loai_kiem_dinh_duoc_goi_ten_thi_phai_co_cau_hinh(self):
        for cum, cap in (
            ("kịch bản E2E đi hết luồng", "verify.e2e"),
            ("kiểm thử tích hợp giữa hai dịch vụ", "verify.sit"),
            ("hợp đồng API không đổi", "verify.api-contract"),
            ("đạt chuẩn trợ năng WCAG AA", "verify.accessibility"),
            ("hàm migration tiến chạy", "verify.migration"),
            ("p95 dưới 200ms", "verify.perf"),
        ):
            with self.subTest(cum=cum):
                pf = self.check(self.story(acceptance_criteria=[f"Then {cum}"]))
                self.assertIn(cap, self.caps(pf))

    def test_cau_hinh_roi_thi_thoi(self):
        pf = self.check(
            self.story(acceptance_criteria=["Then kịch bản E2E đi hết luồng"]),
            **{"verify.e2e": "npx playwright test"},
        )
        self.assertNotIn("verify.e2e", self.caps(pf))

    def test_mien_co_ghi_lai_duoc_tinh_la_da_cap(self):
        """`verify.waived` là quyết định của người, không phải chỗ trống."""
        pf = self.check(
            self.story(acceptance_criteria=["Then kịch bản E2E đi hết luồng"]),
            **{"verify.waived": "e2e"},
        )
        self.assertNotIn("verify.e2e", self.caps(pf))

    def test_khong_nhac_thi_khong_doi(self):
        pf = self.check(self.story(acceptance_criteria=["Then ghi chú được lưu"]))
        self.assertEqual(self.caps(pf), set(), pf.summary())

    def test_thieu_cong_cu_nen_thi_truot(self):
        """Không có `tools.test` thì guard `completion` chặn agent kết thúc
        bằng một chỉ dẫn nó không chạy được — bắt từ đây."""
        pf = self.check(self.story(), **{"tools.test": ""})
        self.assertIn("tools.test", self.caps(pf))


class TestSecurityAndNetwork(PreflightTestCase):
    def test_story_cham_bao_mat_doi_kiem_dinh_bao_mat(self):
        """Tắt rà soát ngữ nghĩa thì phải có `verify.security` cấu hình."""
        for cum in ("băm mật khẩu người dùng", "chống XSS trên ô nhập",
                    "token phiên hết hạn sau 30 phút"):
            with self.subTest(cum=cum):
                pf = self.check(
                    self.story(acceptance_criteria=[f"Then {cum}"]),
                    **{"security.semantic_review": False},
                )
                self.assertIn("verify.security", self.caps(pf))

    def test_ra_soat_ngu_nghia_bat_thi_da_du(self):
        """Nó **là** một cách cấp năng lực này — đòi thêm `verify.security`
        là bắt cấu hình hai lần cho cùng một việc."""
        pf = self.check(self.story(acceptance_criteria=["Then chống XSS trên ô nhập"]))
        self.assertNotIn("verify.security", self.caps(pf))

    def test_story_can_mang_doi_mo_mang_cho_sandbox(self):
        pf = self.check(self.story(
            acceptance_criteria=["Then gọi API ngoài của nhà cung cấp bản đồ"]
        ))
        self.assertIn("network", self.caps(pf))

    def test_mo_mang_roi_thi_thoi(self):
        pf = self.check(
            self.story(acceptance_criteria=["Then gọi API ngoài lấy tỷ giá"]),
            **{"sandbox.tools_network": True},
        )
        self.assertNotIn("network", self.caps(pf))


class TestCodeIntelligence(PreflightTestCase):
    def test_thay_doi_cheo_nhieu_module_doi_phan_tich_anh_huong(self):
        pf = self.check(self.story(
            write_scope=["src/a.ts", "api/b.ts", "worker/c.ts", "shared/d.ts"],
        ))
        self.assertIn("code-intelligence", self.caps(pf))

    def test_tieu_chi_noi_toi_moi_noi_dung_thi_doi_phan_tich(self):
        pf = self.check(self.story(
            acceptance_criteria=["Then mọi nơi dùng hàm này đều được cập nhật"],
        ))
        self.assertIn("code-intelligence", self.caps(pf))

    def test_mot_module_thi_khong_doi(self):
        pf = self.check(self.story(write_scope=["src/a.ts", "src/b.ts"]))
        self.assertNotIn("code-intelligence", self.caps(pf))

    def test_manifest_khong_tinh_la_mot_module(self):
        """`package.json` và lockfile được harness tự thêm — đếm chúng vào
        thì mọi story đều thành 'chạm nhiều module'."""
        pf = self.check(self.story(write_scope=["src/a.ts", "src/b.ts"]))
        self.assertNotIn("code-intelligence", self.caps(pf))


class TestProvisioned(PreflightTestCase):
    def test_doc_tu_cau_hinh_va_dia_khong_doan(self):
        self.contract("notes-list", "trash")
        got = provisioned(self.project, self.config(**{
            "verify.e2e": "npx playwright test",
            "app.dev_command": "npm run dev",
            "app.base_url": "http://localhost:5199",
            "sandbox.tools_network": True,
        }))
        self.assertIn("verify.e2e", got)
        self.assertIn("verify.security", got)   # rà soát ngữ nghĩa bật sẵn
        self.assertIn("browser", got)
        self.assertIn("network", got)
        self.assertIn("mockup-map:notes-list", got)
        self.assertNotIn("verify.perf", got)
        self.assertNotIn("code-intelligence", got)

    def test_khong_co_lenh_dev_thi_chua_co_trinh_duyet(self):
        """`app.base_url` có mặc định hợp lý; thứ thật sự thiếu là lệnh
        dựng ứng dụng lên để xem."""
        got = provisioned(self.project, self.config())
        self.assertNotIn("browser", got)
        got = provisioned(self.project, self.config(**{"app.base_url": ""}))
        self.assertNotIn("browser", got)


class TestHaiMucCham(PreflightTestCase):
    """Story hỏng khác dự án chưa cấu hình — hai loại, hai thời điểm chặn."""

    def test_story_hong_la_loi_cua_story(self):
        pf = self.check(self.story(
            acceptance_criteria=["Then `src/khac/moi.ts` sinh ra báo cáo"],
            write_scope=["src/a.ts"],
        ))
        self.assertTrue(pf.story_defects)
        self.assertEqual(pf.provisioning_gaps, [])

    def test_thieu_cau_hinh_la_viec_cua_du_an(self):
        """Pha dựng mockup và việc cấu hình công cụ đều diễn ra **sau**
        cổng `stories` — chặn ở đó là bắt người sửa thứ chưa tới lượt."""
        pf = self.check(self.story(screens=["notes-list"]))
        self.assertEqual(pf.story_defects, [])
        self.assertTrue(pf.provisioning_gaps)
        self.assertIn("browser", {m.capability for m in pf.provisioning_gaps})

    def test_ca_hai_loai_deu_lam_story_khong_chay_duoc(self):
        """Ở bước ngay trước khi gọi model thì cả hai đều chặn."""
        pf = self.check(self.story(
            screens=["notes-list"],
            acceptance_criteria=["Then `src/khac/moi.ts` sinh ra báo cáo"],
        ))
        self.assertFalse(pf.executable)


class TestRanhGioiChanChay(PreflightTestCase):
    """"Không chạy nổi" khác "chạy được nhưng thiếu bằng chứng".

    Không có trình duyệt thì story giao diện không dựng được màn nào —
    chặn. Không có `verify.accessibility` thì nó vẫn viết được code; cái
    thiếu là bằng chứng nghiệm thu, và cổng story đã ghi "chưa cấu hình
    — không tính là đạt" còn cổng trước triển khai thì chặn thật. Chặn ở
    cả hai chỗ là chặn hai lần cho một chuyện, và làm khung không dùng
    được ngay từ story giao diện đầu tiên.
    """

    def ui(self, **cfg):
        return self.check(self.story(screens=["notes-list"]), **cfg)

    def du_trinh_duyet(self):
        self.contract("notes-list")
        return {
            "app.dev_command": "npm run dev",
            "app.base_url": "http://localhost:5199",
        }

    def test_thieu_trinh_duyet_thi_khong_chay_noi(self):
        pf = self.ui()
        self.assertFalse(pf.executable)
        self.assertFalse(pf.complete)

    def test_thieu_kiem_dinh_thi_van_chay_noi_nhung_chua_du(self):
        pf = self.ui(**self.du_trinh_duyet())
        self.assertTrue(pf.executable, pf.summary())
        self.assertFalse(pf.complete)
        self.assertTrue({m.capability for m in pf.missing} & {
            "verify.e2e", "verify.accessibility"
        })

    def test_thieu_nha_cung_cap_anh_huong_van_chay_noi(self):
        """Bản dựng sẵn vẫn chạy khi không cấu hình nhà cung cấp riêng."""
        pf = self.check(self.story(
            write_scope=["src/a.ts", "api/b.ts", "worker/c.ts", "shared/d.ts"],
        ))
        self.assertIn("code-intelligence", self.caps(pf))
        self.assertTrue(pf.executable)

    def test_thieu_cong_cu_test_thi_khong_chay_noi(self):
        pf = self.check(self.story(), **{"tools.test": ""})
        self.assertFalse(pf.executable)


class TestBatch(PreflightTestCase):
    def test_cham_ca_tap_story(self):
        ok = self.story(id="STORY-01-01")
        xau = self.story(id="STORY-01-02", screens=["notes-list"])
        res = check_stories_executable(
            [ok, xau], project=self.project, config=self.config()
        )
        self.assertTrue(res[0].executable, res[0].summary())
        self.assertFalse(res[1].executable)


if __name__ == "__main__":
    unittest.main()


class TestDottedNamesAreNotFiles(PreflightTestCase):
    """Lỗi 20: `tools.lint`, `Note.text` trong tiêu chí không phải tệp chưa tồn tại."""

    def test_config_and_property_keys_are_not_write_needs(self):
        s = self.story(acceptance_criteria=[
            "Then `tools.lint` được chạy và `Note.text` được cập nhật, `save.done` phát ra",
        ])
        pf = self.check(s)
        self.assertFalse([m for m in pf.missing if m.capability.startswith("write:")], [m.line() for m in pf.missing])

    def test_real_source_path_is_still_a_write_need(self):
        s = self.story(acceptance_criteria=["Then tệp `src/ui/new-screen.tsx` được tạo"])
        pf = self.check(s)
        self.assertTrue(any(m.capability == "write:src/ui/new-screen.tsx" for m in pf.missing), [m.line() for m in pf.missing])


class TestTieuChiTiengAnhCungDuocDoc(PreflightTestCase):
    """Lỗi 114: mọi động từ trong `_MUTATION` đều là tiếng Việt (trừ
    `commit`), nên với dự án viết tiếng Anh, phép kiểm "tiêu chí đòi một tệp
    story không được ghi" **im lặng hoàn toàn**. Đo trên `todo-cli`: tiêu chí
    của STORY-01-01 đòi bốn tệp `lib/commands/*.js` nằm ngoài write_scope,
    cổng `stories` không nói gì, và guard chặn các lượt ghi ấy ba lượt sau."""

    def test_dong_tu_tieng_anh_lam_phep_kiem_no(self):
        s = self.story(acceptance_criteria=[
            "Then the project is structured as `lib/commands/add.js` and "
            "`bin/taskbook.js` exists with a shebang",
        ])
        pf = self.check(s)
        self.assertTrue(any(m.capability == "write:lib/commands/add.js" for m in pf.missing),
                        [m.line() for m in pf.missing])

    def test_tep_git_bo_qua_khong_can_pham_vi_ghi(self):
        """`./.taskbook.json` là kho dữ liệu chương trình tự ghi lúc chạy —
        git bỏ qua nó, nên nó không bao giờ hiện ra như thay đổi ngoài phạm
        vi, nên nó không cần phạm vi ghi."""
        import subprocess
        subprocess.run(["git", "init", "-q"], cwd=self.project, check=True)
        (self.project / ".gitignore").write_text(".taskbook.json\n", encoding="utf-8")
        s = self.story(acceptance_criteria=[
            "Then a task is saved to `./.taskbook.json` and the store is updated",
        ])
        pf = self.check(s)
        self.assertFalse([m for m in pf.missing if m.capability.startswith("write:")],
                         [m.line() for m in pf.missing])


class TestBangTuKhoaPhaiCoDuNgonNgu(PreflightTestCase):
    """Bài học lỗi 114 áp cho các bảng từ khoá còn lại: thiếu một ngôn ngữ thì
    phép kiểm **tắt** ở ngôn ngữ ấy, không phải yếu đi."""

    def test_goi_api_ngoai_bang_tieng_anh_van_can_mang(self):
        s = self.story(acceptance_criteria=[
            "Then the app calls an external API and stores the response",
        ])
        pf = self.check(s)
        self.assertTrue(any(m.capability == "network" for m in pf.needs),
                        [n.capability for n in pf.needs])

    def test_cam_mang_bang_tieng_anh_van_khong_doi_mang(self):
        s = self.story(acceptance_criteria=[
            "Then no outbound network requests are made and no external API is called",
        ])
        pf = self.check(s)
        self.assertFalse([m for m in pf.needs if m.capability == "network"])


class TestCamMangKhongPhaiCanMang(unittest.TestCase):
    """Lỗi 52. Preflight khớp chữ "third-party" rồi đòi **bật**
    `sandbox.tools_network` — cho một story mà tiêu chí chấp nhận nói *cấm*
    mọi truy cập mạng.

    Đo 2026-09-09 trên todo-e2e STORY-01-01: AC là "no third-party resources
    are requested and no outbound network requests are made on load". Heuristic
    đọc chữ mà bỏ câu, biến một yêu cầu bảo mật thành yêu sách nới lỏng
    sandbox, và chặn story là NOT_EXECUTABLE. Mặc định vốn đã là tắt mạng —
    đúng thứ story ấy cần, không phải cấu hình gì cả.
    """

    def test_cau_cam_thi_khong_sinh_nhu_cau(self):
        from aisef.control.preflight import _is_forbidden
        self.assertTrue(_is_forbidden(
            "the document loads and no third-party resources are requested", "third-party"))
        self.assertTrue(_is_forbidden(
            "Then no outbound network requests are made and no CDN is used", "cdn"))

    def test_cau_khang_dinh_van_sinh_nhu_cau(self):
        from aisef.control.preflight import _is_forbidden
        self.assertFalse(_is_forbidden(
            "the app calls a third-party geocoding API on submit", "third-party"))

    def test_phu_dinh_o_cau_khac_khong_tinh(self):
        """Một câu phủ định ba câu trước không nói gì về câu này."""
        from aisef.control.preflight import _is_forbidden
        self.assertFalse(_is_forbidden(
            "There is no login. The importer downloads from a third-party feed.",
            "third-party"))
