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



class TestKhongDocDauRaBangBangMaCuaMay(unittest.TestCase):
    """`subprocess.run(..., text=True)` không nói bảng mã thì Python dùng bảng
    mã **của máy**: cp1252 trên runner Windows. Tiến trình con của dự án này
    nói UTF-8 (chính `_speak_utf8` đặt thế, lỗi 79), nên luồng đọc của cha
    chết bằng `UnicodeDecodeError` **trong thread**, `communicate()` trả về
    `stdout=None` — không ngoại lệ, không thông báo, chỉ là không có gì. Đúng
    một dòng như thế làm CI Windows đỏ ba vòng (lỗi 99).

    Quét bằng `ast` chứ không bằng grep: `encoding=` nằm dòng khác vẫn tính.
    """

    GOI = ("run", "Popen", "check_output", "call", "check_call")

    def _thieu(self, path: Path) -> list[int]:
        import ast
        out = []
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            ten = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
            if ten not in self.GOI:
                continue
            kw = {k.arg for k in node.keywords if k.arg}
            if ("text" in kw or "universal_newlines" in kw) and "encoding" not in kw:
                out.append(node.lineno)
        return out

    def test_moi_lan_goi_tien_trinh_con_deu_khai_bang_ma(self):
        thieu = []
        for d in ("aisef", "tests"):
            for p in sorted((ROOT / d).rglob("*.py")):
                thieu += [f"{p.relative_to(ROOT)}:{ln}" for ln in self._thieu(p)]
        self.assertEqual(thieu, [], "thiếu encoding=\"utf-8\": " + ", ".join(thieu))

    def test_phep_quet_that_su_thay_duoc_loi(self):
        """Phép quét chỉ có nghĩa nếu nó bắt được ca hỏng."""
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.py"
            p.write_text("import subprocess\n"
                         "subprocess.run(['git'], capture_output=True, text=True)\n",
                         encoding="utf-8")
            self.assertEqual(self._thieu(p), [2])

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


class TestConSoTrongTaiLieuKhopNguonDocDuoc(unittest.TestCase):
    """Số đếm trong tài liệu phải đọc được từ mã hoặc từ bảng — không đánh máy.

    Ba con số đã trôi cùng lúc (đo 2026-09-12): `STABILITY.md` nói 58 khoá cấu
    hình khi `DEFAULTS` đã có 68; `README` nói 31 lỗi khi bảng phân loại đã ghi
    tới lỗi 70; và tiêu đề mục của chính bảng ấy còn nói "22–63". Cả ba đều là
    lỗi **vắng phép kiểm**: không có gì nối con số trong tài liệu với nguồn sinh
    ra nó. Ba phép dưới đây làm chính việc nối ấy.
    """

    DOCS = ROOT / "docs"

    @staticmethod
    def _ma_loi_trong_bang(text: str) -> list[int]:
        """Mã lỗi = ô đầu của mỗi dòng bảng trong FAILURE-TAXONOMY."""
        return [int(m) for m in re.findall(r"(?m)^\|\s*(\d+)\s*\|", text)]

    def test_so_khoa_cau_hinh_trong_stability_khop_defaults(self):
        from aisef.config import DEFAULTS
        text = (self.DOCS / "STABILITY.md").read_text(encoding="utf-8")
        m = re.search(r"### Config keys \((\d+) keys\)", text)
        self.assertIsNotNone(m, "không đọc được số khoá ở STABILITY.md — tiêu đề đã đổi dạng")
        self.assertEqual(int(m.group(1)), len(DEFAULTS),
                         "STABILITY.md nói số khoá khác `len(DEFAULTS)`")

    def test_so_guard_trong_stability_khop_matchers(self):
        """Cùng lớp với phép trên, cùng tệp, và đã trôi thật: `STABILITY.md`
        nói "Guards (9 guards)" với bảng thiếu `tool-bypass` khi
        `GUARD_MATCHERS` đã có 10 (đo 2026-09-14). Phép trước chỉ nối số
        **khoá cấu hình**, nên con số ngay dưới nó trôi tự do."""
        from aisef.harness.guardrails import GUARD_MATCHERS
        text = (self.DOCS / "STABILITY.md").read_text(encoding="utf-8")
        m = re.search(r"### Guards \((\d+) guards\)", text)
        self.assertIsNotNone(m, "không đọc được số guard ở STABILITY.md — tiêu đề đã đổi dạng")
        self.assertEqual(int(m.group(1)), len(GUARD_MATCHERS),
                         "STABILITY.md nói số guard khác `len(GUARD_MATCHERS)`")
        for ten in sorted(GUARD_MATCHERS):
            with self.subTest(guard=ten):
                self.assertIn(f"| `{ten}` |", text,
                              f"guard `{ten}` có trong GUARD_MATCHERS nhưng không có dòng nào ở bảng STABILITY.md")

    def test_nhom_khoa_trong_stability_phu_het_defaults(self):
        from aisef.config import DEFAULTS
        text = (self.DOCS / "STABILITY.md").read_text(encoding="utf-8")
        for prefix in sorted({k.split(".")[0] for k in DEFAULTS}):
            with self.subTest(nhom=prefix):
                self.assertIn(f"`{prefix}.*`", text,
                              f"nhóm khoá `{prefix}.*` có trong DEFAULTS nhưng không có ở STABILITY.md")

    def test_so_loi_trong_readme_khop_bang_phan_loai(self):
        ids = self._ma_loi_trong_bang((self.DOCS / "FAILURE-TAXONOMY.md").read_text(encoding="utf-8"))
        self.assertTrue(ids, "regex lệch với bảng trong FAILURE-TAXONOMY.md")
        lon_nhat = max(ids)
        for ten in ("README.md", "README.vi.md"):
            with self.subTest(tai_lieu=ten):
                text = (ROOT / ten).read_text(encoding="utf-8")
                m = re.search(r"(?m)^(\d+) (?:bugs found by measurement|lỗi tìm bằng đo)", text)
                self.assertIsNotNone(m, f"không đọc được số lỗi ở {ten} — câu đã đổi dạng")
                self.assertEqual(int(m.group(1)), lon_nhat,
                                 f"{ten} nói số lỗi khác mã lỗi lớn nhất trong FAILURE-TAXONOMY")

    def test_tieu_de_muc_phu_het_ma_loi_trong_bang(self):
        text = (self.DOCS / "FAILURE-TAXONOMY.md").read_text(encoding="utf-8")
        ids = self._ma_loi_trong_bang(text)
        m = re.search(r"## Lỗi (\d+)[–-](\d+) —", text)
        self.assertIsNotNone(m, "không đọc được khoảng mã lỗi ở tiêu đề mục")
        dau, cuoi = int(m.group(1)), int(m.group(2))
        self.assertEqual((dau, cuoi), (min(ids), max(ids)),
                         "tiêu đề mục không phủ đúng khoảng mã lỗi có trong bảng")


class TestLienKetTaiLieuTroVaoChoCoThat(unittest.TestCase):
    """Mọi liên kết tương đối trong tài liệu phải trỏ vào tệp — và neo — có thật.

    Lỗi thật đã xảy ra (đo 2026-09-12): `BENCH-REPORT-v1.3.md` bảo người đọc tìm
    "hàng đợi phase B/C/D trong `docs/EXECUTION-PLAN.md`" trong khi tệp ấy không
    có hàng đợi nào. Người đọc mất thời gian tìm một thứ không tồn tại, và kế
    hoạch thật thì nằm trong ngữ cảnh một phiên — mất khi phiên đóng. Phép kiểm
    này bắt cả hai dạng: tệp không có, và neo không có trong tệp có.
    """

    TAI_LIEU = "docs/*.md"
    THEM = ("README.md", "README.vi.md", "CHANGELOG.md")
    LIEN_KET = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
    TIEU_DE = re.compile(r"(?m)^#{1,6}\s+(.+?)\s*$")

    @staticmethod
    def _neo(tieu_de: str) -> str:
        """Slug kiểu GitHub: thường hoá, bỏ dấu câu (giữ khoảng trắng nó để lại),
        khoảng trắng → gạch nối. Không gộp gạch nối liền nhau — GitHub cũng không."""
        import unicodedata
        h = unicodedata.normalize("NFC", tieu_de.strip().lower())
        return re.sub(r"[^\w\s-]", "", h).replace(" ", "-")

    def _tep(self) -> list[Path]:
        return sorted(ROOT.glob(self.TAI_LIEU)) + [ROOT / t for t in self.THEM]

    def test_moi_lien_ket_tuong_doi_tro_vao_tep_va_neo_co_that(self):
        tep = self._tep()
        neo = {
            f.name: {self._neo(m) for m in self.TIEU_DE.findall(f.read_text(encoding="utf-8"))}
            for f in tep
        }
        so_lien_ket = 0
        for f in tep:
            for href in self.LIEN_KET.findall(f.read_text(encoding="utf-8")):
                if href.startswith(("http://", "https://", "mailto:")):
                    continue
                so_lien_ket += 1
                duong_dan, _, phan_neo = href.partition("#")
                dich = (f.parent / duong_dan) if duong_dan else f
                with self.subTest(tu=f.name, toi=href):
                    if duong_dan:
                        self.assertTrue(dich.exists(),
                                        f"{f.name} trỏ tới `{href}` — tệp không có")
                    if phan_neo and dich.suffix == ".md" and dich.name in neo:
                        self.assertIn(phan_neo, neo[dich.name],
                                      f"{f.name} trỏ tới `{href}` — tệp có, neo không có")
        self.assertGreater(so_lien_ket, 40, "regex lệch — không đọc được liên kết nào đáng kể")

class TestThongDiepCongMayDuNgan(unittest.TestCase):
    """Thông điệp cổng máy phải đọc được trong một màn hình terminal.

    Mẫu lấy từ guard: **nói chỗ sửa trước**, giải thích sau. Một đoạn văn 7
    dòng có đủ thông tin vẫn là một đoạn văn người ta lướt qua — và lướt qua
    thì thông tin ấy bằng không. Ngưỡng ≤ 5 dòng ở 80 cột (đợt 2 mục 2.3).
    """

    NGUONG_DONG = 5

    def _thong_diep(self):
        import ast
        import textwrap

        src = (ROOT / "aisef" / "control" / "machine_gate.py").read_text(encoding="utf-8")

        def van_ban(node):
            """Chuỗi người dùng thấy; chỗ thay `{...}` tính là 12 ký tự."""
            ra = []

            def di(n):
                if isinstance(n, ast.Constant) and isinstance(n.value, str):
                    ra.append(n.value)
                elif isinstance(n, ast.JoinedStr):
                    for v in n.values:
                        ra.append(str(v.value) if isinstance(v, ast.Constant) else "x" * 12)
                elif isinstance(n, ast.BinOp):
                    di(n.left)
                    di(n.right)

            for a in node.args:
                di(a)
            return "".join(ra)

        ra = []
        for node in ast.walk(ast.parse(src)):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "append" and "errors" in ast.unparse(node.func)):
                t = van_ban(node)
                if t:
                    ra.append((len(textwrap.wrap(t, 80)), node.lineno, t))
        return ra

    def test_khong_thong_diep_nao_qua_nam_dong(self):
        qua = [(d, ln, t[:70]) for d, ln, t in self._thong_diep() if d > self.NGUONG_DONG]
        self.assertEqual(qua, [], f"thông điệp dài quá {self.NGUONG_DONG} dòng: {qua}")

    def test_van_con_thong_diep_de_do(self):
        """Phép thử trên chỉ có nghĩa khi thật sự có thông điệp để đo."""
        self.assertGreaterEqual(len(self._thong_diep()), 10)


class TestKhongDungApiChiCoTrenPosix(unittest.TestCase):
    """Lần thứ ba lặp lại cùng một lớp lỗi: mã chạy xanh trên macOS, đỏ ở CI
    Windows vì một giả định POSIX. Lỗi 99 là bảng mã, 115 là khoá tệp, lần này
    là `signal.SIGKILL` — thứ **không tồn tại** trên Windows (`os.kill` ở đó
    gọi TerminateProcess cho mọi tín hiệu, nên chỉ có một bước dứt khoát).

    Ba lần thì không còn là xui. Phép thử này đọc cây cú pháp: dùng một tên chỉ
    có trên POSIX thì **hàm chứa nó** phải nhắc `win32` — tức có nhánh riêng cho
    Windows. Không bắt được mọi cách viết sai, nhưng bắt đúng cách đã sai ba lần:
    quên mất rằng Windows tồn tại.
    """

    #: Tên chỉ có trên POSIX, thường gặp trong mã quản lý tiến trình.
    POSIX_ONLY = {"SIGKILL", "SIGQUIT", "SIGSTOP", "SIGCONT", "SIGHUP",
                  "fork", "setsid", "getuid", "geteuid", "killpg"}

    #: Cách viết một nhánh nền tảng: `sys.platform`, `os.name`, hoặc một hằng
    #: kiểu `_WIN` đã tính sẵn ở đầu mô-đun.
    DAU_HIEU_NEN = ("win32", "os.name", "_WIN", "IS_WINDOWS", "WINDOWS")

    def _duoc_canh(self, src: str, cay) -> set:
        """Hàm nằm trong một nhánh `if` theo nền tảng — kể cả nhánh `else`.

        `aisef/_compat.py` tách ở **tầng mô-đun** (`if _WIN: … else: …`), nên
        nhìn trong thân hàm là tố oan: nhánh POSIX không bao giờ chạy trên
        Windows.
        """
        import ast

        an_toan = set()
        for node in ast.walk(cay):
            if not isinstance(node, ast.If):
                continue
            dieu_kien = ast.get_source_segment(src, node.test) or ""
            if not any(d in dieu_kien for d in self.DAU_HIEU_NEN):
                continue
            for nhanh in (node.body, node.orelse):
                for con in nhanh:
                    for x in ast.walk(con):
                        if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            an_toan.add(x)
        return an_toan

    def test_moi_cho_dung_deu_co_nhanh_windows(self):
        import ast

        for path in sorted((ROOT / "aisef").rglob("*.py")):
            src = path.read_text(encoding="utf-8")
            cay = ast.parse(src, filename=str(path))
            canh = self._duoc_canh(src, cay)
            for ham in ast.walk(cay):
                if not isinstance(ham, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                dung = {n.attr for n in ast.walk(ham)
                        if isinstance(n, ast.Attribute) and n.attr in self.POSIX_ONLY}
                if not dung:
                    continue
                than = ast.get_source_segment(src, ham) or ""
                if ham in canh or any(d in than for d in self.DAU_HIEU_NEN):
                    continue
                with self.subTest(tep=path.name, ham=ham.name):
                    self.fail(
                        f"{path.name}::{ham.name} dùng {', '.join(sorted(dung))} — "
                        f"chỉ có trên POSIX; cần nhánh riêng cho Windows "
                        f"(`sys.platform == \"win32\"`)")

    def test_phep_quet_that_su_thay_duoc_loi(self):
        """Phép quét chỉ có nghĩa nếu nó bắt được ca hỏng — và tha ca đã canh."""
        import ast
        import tempfile

        hong = ("import os, signal\n"
                "def dung(p):\n"
                "    os.kill(p, signal.SIGKILL)\n")
        canh_trong_ham = ("import os, signal, sys\n"
                          "def dung(p):\n"
                          "    s = signal.SIGTERM if sys.platform == 'win32' else signal.SIGKILL\n"
                          "    os.kill(p, s)\n")
        canh_tang_module = ("import os, signal, sys\n"
                            "if sys.platform == 'win32':\n"
                            "    def dung(p): os.kill(p, signal.SIGTERM)\n"
                            "else:\n"
                            "    def dung(p): os.kill(p, signal.SIGKILL)\n")
        with tempfile.TemporaryDirectory() as d:
            for ten, ma, cho_phep in (("hong", hong, False),
                                      ("trong_ham", canh_trong_ham, True),
                                      ("tang_module", canh_tang_module, True)):
                p = Path(d) / f"{ten}.py"
                p.write_text(ma, encoding="utf-8")
                cay = ast.parse(ma)
                canh = self._duoc_canh(ma, cay)
                ok = True
                for ham in ast.walk(cay):
                    if not isinstance(ham, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        continue
                    dung_ten = {n.attr for n in ast.walk(ham)
                                if isinstance(n, ast.Attribute) and n.attr in self.POSIX_ONLY}
                    than = ast.get_source_segment(ma, ham) or ""
                    if dung_ten and ham not in canh and not any(
                            x in than for x in self.DAU_HIEU_NEN):
                        ok = False
                with self.subTest(ca=ten):
                    self.assertEqual(ok, cho_phep)


class TestTienDangKyCot2BiGhim(unittest.TestCase):
    """Tiền đăng ký cột 2 phải ghim được, và ghim thật (phán quyết 7, tiêu chí G5.1).

    Một dự đoán không ghim thì không phân biệt được với một dự đoán viết sau khi
    thấy dữ liệu — và dự án này đã in ra một con số (dải nhiễu ±0,08) không sống
    nổi một lượt đọc lại. Bốn phép dưới đây là **bản tham chiếu** của công thức
    digest mà `aisef.control.closure:probe_prereg_digest` phải dùng lại khi máy
    đóng gate được viết; công thức ấy không được có bản thứ hai.
    """

    VUNG = r"(?s)<!--\s*PREREG-FROZEN:BEGIN\s*-->\n(.*?)\n<!--\s*PREREG-FROZEN:END\s*-->"
    GHIM = ROOT / "docs/BENCH-PREREGISTRATION-C2.md"
    BAN_GIAO = ROOT / "docs/handoff/bench-real-model-wiring.md"
    CONG = ROOT / "docs/closure-gate.json"

    @classmethod
    def _vung_ghim(cls, tep: Path) -> str:
        """Chuẩn hoá xuống dòng, cắt dòng trống đầu/cuối vùng — ngoài ra từng byte."""
        t = tep.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
        khop = re.findall(cls.VUNG, t)
        if len(khop) != 1:
            raise AssertionError(f"{tep.name}: {len(khop)} vùng ghim, phải đúng 1")
        return khop[0].strip("\n")

    @classmethod
    def _digest(cls, tep: Path) -> str:
        import hashlib
        return hashlib.sha256(cls._vung_ghim(tep).encode("utf-8")).hexdigest()

    def _tieu_chi(self) -> dict:
        import json
        cong = json.loads(self.CONG.read_text(encoding="utf-8"))
        for g in cong["gates"]:
            for c in g["criteria"]:
                if c["id"] == "G5.1":
                    return c
        raise AssertionError("closure-gate.json không còn tiêu chí G5.1")

    def test_digest_khop_gia_tri_ghi_ngoai_tep(self):
        """Giá trị ghim nằm ở `closure-gate.json`, không nằm trong tệp nó ghim: một
        digest ghi trong chính chủ thể của nó được cập nhật cùng một động tác với
        văn bản, nên nó không ghim gì."""
        c = self._tieu_chi()
        self.assertEqual(c["evidence"], "docs/BENCH-PREREGISTRATION-C2.md")
        self.assertEqual(c["freshness"], {"kind": "pinned_digest", "source": "prereg_sha256"})
        self.assertRegex(c.get("prereg_sha256", ""), r"^[0-9a-f]{64}$",
                         "G5.1 chưa ghi `prereg_sha256` — UNCONFIGURED, hợp đồng §4.1 đọc thành UNRUNNABLE")
        self.assertEqual(self._digest(self.GHIM), c["prereg_sha256"],
                         "vùng ghim §2 đã đổi — hoàn nguyên văn bản, đừng ghi lại digest")
        self.assertNotIn(c["prereg_sha256"], self.GHIM.read_text(encoding="utf-8"),
                         "digest bị nhắc lại trong chính tệp nó ghim — một con số có hai nhà là con số sẽ lệch")

    def test_ban_lich_su_ra_dung_cung_digest(self):
        """Thứ định ngày cho bản ghim là bản lịch sử: cùng văn bản, commit trước khi
        có một byte dữ liệu cột 2. Hai bản lệch nhau là mất bằng chứng ngày."""
        self.assertEqual(self._digest(self.BAN_GIAO), self._digest(self.GHIM),
                         "§7 bản bàn giao không còn trùng vùng ghim của tài liệu đóng")

    def test_ban_giao_giu_muc_7_tai_cho_va_co_con_tro_co_ngay(self):
        """Văn bản lịch sử ở nguyên chỗ cũ, và nói ra bản ghim nằm đâu."""
        t = self.BAN_GIAO.read_text(encoding="utf-8")
        self.assertIn("## 7. Tiền đăng ký — viết trước khi có dữ liệu", t)
        muc7 = t.split("## 7. ", 1)[1].split("\n## 8. ", 1)[0]
        self.assertIn("2026-09-14", muc7)
        self.assertIn("BENCH-PREREGISTRATION-C2.md", muc7)

    def test_phu_luc_hau_nghiem_nam_ngoai_vung_ghim(self):
        """Ranh giới giữa cam kết và hậu nghiệm: cái học được sau tiền đăng ký có
        trong tài liệu, và **không** có trong vùng ghim."""
        vung = self._vung_ghim(self.GHIM)
        ca_tep = self.GHIM.read_text(encoding="utf-8")
        for cau in ("BENCH-TASK-DISCRIMINATION", "G5.3", "lỗi 86"):
            with self.subTest(cau=cau):
                self.assertIn(cau, ca_tep)
                self.assertNotIn(cau, vung, f"`{cau}` là hậu nghiệm, không được nằm trong vùng ghim")
