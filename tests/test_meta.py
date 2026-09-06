"""Test đọc chính mã nguồn — chống hai lớp lỗi mà unit test thường không
thấy, vì chúng là lỗi **vắng mặt**:

* D5 — bằng chứng có mô hình nhưng không ai sinh. `FILE_CHANGE` và
  `GUARD_BLOCK` có hằng, có test, và suốt hai tuần không có một dòng nào
  trong `aisef/` ghi chúng; luật "file sửa sau lần test cuối" của guard
  `completion` chưa từng chạy ngoài test.
* D2 — năng lực khai `EMULATED` mà không có mã mô phỏng. OpenCode khai
  `TOOL_ALLOWLIST: EMULATED "qua permission config"`, không có mã nào sinh
  config ấy, và người rà soát trên OpenCode ghi được code.

Hai test này rẻ và chặn cả lớp tái sinh ở mọi hạng mục sau.
"""

from __future__ import annotations

import importlib
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PKG = ROOT / "aisef"


def _sources(exclude: set[str] = frozenset()) -> dict[Path, str]:
    return {
        p: p.read_text(encoding="utf-8")
        for p in PKG.rglob("*.py")
        if p.name not in exclude and "__pycache__" not in p.parts
    }


class TestMoiLoaiBangChungDeuCoNguoiSinh(unittest.TestCase):
    #: Loại cố ý chưa có người sinh — phải nêu lý do, và danh sách này
    #: **chỉ được ngắn đi**.
    CHUA_CO = {
        "NOTE": "ghi chú tự do — chưa có pha nào cần; xoá hằng nếu tới G12 vẫn không dùng",
    }

    def test_hang_kind_trong_observe_co_noi_ghi(self):
        observe = (PKG / "harness" / "observe.py").read_text(encoding="utf-8")
        kinds = {
            k: v for k, v in re.findall(r'^([A-Z_]+) = "([a-z_]+)"\s*#', observe, re.M)
            # `EVIDENCE_DIR = "evidence"` là đường dẫn, không phải loại sự kiện.
            if not k.endswith(("_DIR", "_FILE", "_PATH"))
        }
        self.assertTrue(kinds, "không đọc được hằng kind nào — regex lệch với observe.py")
        others = _sources(exclude={"observe.py"})
        for const, value in kinds.items():
            with self.subTest(kind=const):
                if const in self.CHUA_CO:
                    continue
                used = any(
                    re.search(rf"\b{const}\b", src) or f'"{value}"' in src
                    for src in others.values()
                )
                self.assertTrue(
                    used,
                    f"{const} có mô hình nhưng không tệp nào trong aisef/ ghi nó — "
                    f"guard hay cổng đọc loại này sẽ luôn thấy rỗng",
                )

    def test_danh_sach_chua_co_khong_lam_bia(self):
        observe = (PKG / "harness" / "observe.py").read_text(encoding="utf-8")
        for const in self.CHUA_CO:
            self.assertIn(f"{const} = ", observe, f"{const} không còn — xoá khỏi CHUA_CO")


class TestNangLucKhaiEmulatedPhaiCoMaMoPhong(unittest.TestCase):
    """Mỗi `Support.EMULATED` phải kèm `# emulated by: <mô-đun>.<hàm>` và
    hàm ấy phải tồn tại. Khai "mô phỏng" mà không chỉ được vào mã là
    khai xanh cho một thứ không có."""

    PATTERN = re.compile(
        r"Support\.EMULATED,?\s*#\s*emulated by:\s*([\w.]+)\.(\w+)"
    )

    def test_moi_dong_emulated_tro_vao_ham_co_that(self):
        for path in (PKG / "clients").glob("*.py"):
            src = path.read_text(encoding="utf-8")
            for line_no, line in enumerate(src.splitlines(), 1):
                # Chỉ dòng **khai** năng lực; `base.py` dùng tên hằng trong
                # logic so sánh, không phải khai báo.
                if "Support.EMULATED" not in line or "Capability." not in line:
                    continue
                with self.subTest(file=path.name, line=line_no):
                    m = self.PATTERN.search(line)
                    self.assertIsNotNone(
                        m, f"{path.name}:{line_no} khai EMULATED mà không có "
                           f"`# emulated by: <module>.<func>`: {line.strip()}"
                    )
                    module = importlib.import_module(f"aisef.harness.{m.group(1)}") \
                        if not m.group(1).startswith("aisef") \
                        else importlib.import_module(m.group(1))
                    self.assertTrue(
                        callable(getattr(module, m.group(2), None)),
                        f"{m.group(1)}.{m.group(2)} không tồn tại",
                    )


if __name__ == "__main__":
    unittest.main()


class TestTaiLieuTroVaoMaCoThat(unittest.TestCase):
    """R4: SOLUTION/README nhắc `kit/agents/`, `kit/mcp/`, `control/fsm.py`,
    `phases/ship`… không tồn tại. Tài liệu nêu đường dẫn nào thì đường dẫn ấy
    phải có thật — không thì bảng kiến trúc là lời kể."""

    def test_moi_duong_dan_module_trong_tai_lieu_ton_tai(self):
        rx = re.compile(r"`((?:aisef/)?(?:kit|harness|control|phases|clients)/[A-Za-z0-9_./-]+)`")
        for doc in ("docs/SOLUTION.md", "README.md"):
            text = (ROOT / doc).read_text(encoding="utf-8")
            for ref in sorted(set(rx.findall(text))):
                rel = (ref if ref.startswith("aisef/") else "aisef/" + ref).rstrip("/")
                with self.subTest(doc=doc, path=ref):
                    self.assertTrue((ROOT / rel).exists() or (ROOT / (rel + ".py")).exists(),
                                    f"{doc} nhắc `{ref}` nhưng không có trong cây mã")


class TestSolutionKhopMa(unittest.TestCase):
    """P1-6 mở rộng (2026-09-06): SOLUTION nêu lệnh CLI, knob cấu hình, mục cổng
    story, bước nhật ký, slot bàn giao, guard và cổng người — mỗi thứ phải khớp
    **tên** trong mã. Danh sách đọc từ mã, không chép tay vào test: thêm một
    lệnh/knob/mục mà quên tài liệu thì test đỏ, không phải người đọc phát hiện
    sau. Hai đợt ADR-004 lệch 6 chỗ (tool giả, `next/complete`, guard "before
    commit", 6 knob thiếu, cổng story 5 mục thay vì 15, `verify.*` 10 thay vì 12)
    mà test cũ chỉ bắt đường dẫn tệp."""

    @classmethod
    def setUpClass(cls):
        cls.text = (ROOT / "docs/SOLUTION.md").read_text(encoding="utf-8")

    def _co(self, name: str) -> bool:
        return f"`{name}`" in self.text or f"**{name}**" in self.text

    def test_moi_lenh_cli_co_trong_bo_lenh(self):
        import argparse
        from aisef.cli.parser import build_parser
        sub = next(a for a in build_parser()._actions if isinstance(a, argparse._SubParsersAction))
        self.assertGreaterEqual(len(sub.choices), 20)
        for cmd in sub.choices:
            with self.subTest(cmd=cmd):
                self.assertRegex(self.text, rf"(?m)^aisef {re.escape(cmd)}(\s|$)",
                                 f"`aisef {cmd}` có trong parser nhưng không có ở SOLUTION §10")

    def test_moi_knob_cau_hinh_co_trong_bang_nguong(self):
        from aisef.config import DEFAULTS
        gop = {"verify.waived", "verify.waiver_reason", "verify.baseline", "verify.clean_tree",
               "verify.nop"}
        for key in DEFAULTS:
            with self.subTest(key=key):
                if key.startswith("verify.") and key not in gop:
                    # 12 loại kiểm định gộp một dòng `verify.*`, nhưng tên loại phải có
                    kind = key.split(".", 1)[1]
                    self.assertTrue("`verify.*`" in self.text and f"`{kind}`" in self.text,
                                    f"loại kiểm định `{kind}` không có ở dòng `verify.*` SOLUTION §13")
                else:
                    self.assertTrue(self._co(key), f"knob `{key}` có trong DEFAULTS nhưng không có ở SOLUTION §13")

    def test_moi_muc_cong_story_co_trong_bang_cong(self):
        src = (PKG / "control" / "gate.py").read_text(encoding="utf-8")
        names = set(re.findall(r'Check\(\s*"([^"]+)"', src)) | set(re.findall(r'^\s*ten = "([^"]+)"', src, re.M))
        self.assertGreaterEqual(len(names), 10, "regex lệch với gate.py")
        for name in sorted(names):
            with self.subTest(muc=name):
                self.assertTrue(self._co(name), f"mục cổng `{name}` có trong gate.py nhưng không có ở SOLUTION §12")

    def test_thu_tu_nhat_ky_dung_nhu_ma(self):
        from aisef.control.journal import STEPS
        gon = re.sub(r"\s+", " ", self.text)
        self.assertIn(" → ".join(STEPS), gon, "thứ tự `STEPS` ở SOLUTION §6 lệch `control/journal.py`")

    def test_moi_slot_ban_giao_co_trong_tai_lieu(self):
        from aisef.phases.implement import SLOT_SOURCE
        for slot in SLOT_SOURCE:
            with self.subTest(slot=slot):
                self.assertTrue(self._co(slot), f"slot `{slot}` có trong SLOT_SOURCE nhưng không có ở SOLUTION §5.4")

    def test_moi_guard_va_cong_nguoi_co_ten_trong_tai_lieu(self):
        from aisef.control.approvals import Gate
        from aisef.harness.guardrails import GUARD_MATCHERS
        for g in GUARD_MATCHERS:
            with self.subTest(guard=g):
                self.assertTrue(self._co(g), f"guard `{g}` không có ở SOLUTION §5.5")
        for g in Gate:
            with self.subTest(gate=g.value):
                self.assertTrue(self._co(g.value), f"cổng người `{g.value}` không có ở SOLUTION §6")
