"""Lời người rà soát: nguyên văn (lỗi 16) và bản máy đọc theo schema (R8)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.clients.base import Capability, ClientAdapter, RunSpec, Support  # noqa: E402
from aisef.clients.stream import RunResult  # noqa: E402
from aisef.harness.observe import NOTE, EvidenceStore  # noqa: E402
from aisef.phases.implement import (  # noqa: E402
    REVIEWS_DIR,
    _reconcile,
    _reconcile_security,
    _with_schema,
    blocking_findings,
    merge_findings,
    persist_verdict,
    plan_defects,
    review_verdict,
)

REPORT = """# Rà soát

- [chặn] src/ui/app-shell.tsx:190-256 — toàn bộ phần nối dây của TCCN 1, 4, 6, 7
  chưa có test nào chạm tới; xoá đoạn này thì bộ test vẫn xanh.
- [bế tắc] Hai loại kiểm định `e2e` và `accessibility` mà story khai — không
  thể thêm test cho chúng từ trong write_scope: story chỉ cho ghi `src/**`,
  còn `tests/e2e` và `tests/a11y` nằm ngoài. Sửa write_scope rồi chạy lại.

- ghi chú thường, không phải mục chặn.
"""


class TestMultilineFindings(unittest.TestCase):
    def test_continuation_lines_belong_to_the_finding(self):
        f = blocking_findings(REPORT)
        self.assertEqual(len(f), 2)
        self.assertIn("xoá đoạn này thì bộ test vẫn xanh", f[0])
        self.assertTrue(f[1].startswith("[bế tắc]"))
        self.assertIn("tests/a11y", f[1])
        self.assertNotIn("ghi chú thường", " ".join(f))
        self.assertEqual(len(plan_defects(f)), 1)

    def test_single_line_findings_unchanged(self):
        self.assertEqual(blocking_findings("- [chặn] a\n- [chặn] b\n"), ["[chặn] a", "[chặn] b"])


class TestPersistVerdict(unittest.TestCase):
    def test_full_text_is_kept_on_disk(self):
        with tempfile.TemporaryDirectory() as d:
            r = RunResult(ok=True, text=REPORT, session_id="s1", num_turns=35, cost_usd=4.12)
            p = persist_verdict(d, "STORY-01-05", "review", 1, r)
            self.assertEqual(p, Path(d) / REVIEWS_DIR / "STORY-01-05-review-1.md")
            body = p.read_text(encoding="utf-8")
            self.assertIn("tests/a11y", body)
            self.assertIn("$4.12", body)


JSON_KHOP = """- [chặn] src/a.py:1 — mất dữ liệu khi lưu

```json
{"verdict": "block", "findings": [
  {"tag": "chặn", "file": "src/a.py", "line": 1, "why": "mất dữ liệu khi lưu",
   "behavior_id": "AC-STORY-01-01-1"}]}
```
"""


class KichBan(ClientAdapter):
    """Client giả cho lượt rà soát: trả lần lượt các câu đã viết sẵn."""

    id = "kich-ban"

    def __init__(self, *texts: str, ok: bool = True):
        self.texts = list(texts)
        self.ok = ok
        self.prompts: list[str] = []

    def available(self) -> bool:
        return True

    def capabilities(self):
        return {c: Support.NATIVE for c in Capability}

    def run(self, spec: RunSpec) -> RunResult:
        self.prompts.append(spec.prompt)
        text = self.texts[min(len(self.prompts), len(self.texts)) - 1]
        return RunResult(ok=self.ok, text=text, cost_usd=0.3,
                         error="" if self.ok else "api_error")


class SchemaTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.spec = RunSpec(prompt="# Rà soát", workdir=self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def chay(self, *texts: str):
        """Một lượt rà soát đã chạy xong → phần schema + đối chiếu."""
        client = KichBan(*texts)
        dau = client.run(self.spec)
        text, verdict = _with_schema(
            client, self.spec, dau, store=EvidenceStore(self.root),
            story_id="STORY-01-01", artifact_root=self.root, workdir=self.root,
            role="review", number=1,
        )
        return client, text, verdict

    def notes(self) -> dict[str, dict]:
        return {e.name: e.detail
                for e in EvidenceStore(self.root).read("STORY-01-01").of(NOTE)}


class TestReviewVerdict(unittest.TestCase):
    def test_lay_khoi_json_du_co_chu_thua_hai_dau(self):
        v = review_verdict(JSON_KHOP)
        self.assertEqual(v.verdict, "block")
        self.assertEqual(v.findings[0]["behavior_id"], "AC-STORY-01-01-1")
        self.assertEqual(v.blocking(), ["[chặn] src/a.py:1 — mất dữ liệu khi lưu"])

    def test_khong_co_json_thi_none(self):
        self.assertIsNone(review_verdict("- [chặn] src/a.py:1 — mất dữ liệu"))
        self.assertIsNone(review_verdict(""))

    def test_sai_schema_thi_none(self):
        self.assertIsNone(review_verdict('{"verdict": "có lẽ ổn", "findings": []}'))

    def test_muc_sai_schema_bi_bo_khong_sap(self):
        v = review_verdict('nói gì đó {"a": 1} rồi {"verdict":"pass","findings":["x",{}]}')
        self.assertEqual(v.findings, [])

    def test_ket_luan_chan_ma_khong_neu_muc_van_la_chan(self):
        v = review_verdict('{"verdict": "stuck", "findings": []}')
        self.assertEqual(len(v.blocking()), 1)
        self.assertTrue(v.blocking()[0].startswith("[bế tắc]"))


class TestSchemaVaHoiLai(SchemaTestCase):
    def test_json_hop_le_thi_khong_hoi_lai(self):
        client, text, verdict = self.chay(JSON_KHOP)
        self.assertEqual(len(client.prompts), 1)
        self.assertEqual(_reconcile("STORY-01-01", EvidenceStore(self.root), text, verdict, role="review"),
                         ["[chặn] src/a.py:1 — mất dữ liệu khi lưu"])
        self.assertNotIn("review:mismatch", self.notes())
        self.assertEqual(self.notes()["review:verdict"]["verdict"], "block")

    def test_thieu_json_thi_hoi_lai_dung_mot_lan(self):
        client, text, verdict = self.chay("- [chặn] src/a.py:1 — mất dữ liệu khi lưu",
                                          JSON_KHOP)
        self.assertEqual(len(client.prompts), 2, "phải hỏi lại đúng một lần")
        self.assertIn("Thiếu khối JSON", client.prompts[1])
        self.assertEqual(verdict.verdict, "block")
        _reconcile("STORY-01-01", EvidenceStore(self.root), text, verdict, role="review")
        self.assertNotIn("review:no-schema", self.notes())

    def test_ca_hai_luot_thieu_json_thi_dung_van_ban(self):
        client, text, verdict = self.chay("- [chặn] src/a.py:1 — mất dữ liệu",
                                          "vẫn không có JSON")
        self.assertEqual(len(client.prompts), 2, "không hỏi lại lần thứ hai")
        self.assertIsNone(verdict)
        got = _reconcile("STORY-01-01", EvidenceStore(self.root), text, verdict, role="review")
        self.assertEqual(got, ["[chặn] src/a.py:1 — mất dữ liệu"])
        self.assertIn("review:no-schema", self.notes())

    def test_lech_thi_lay_hop_hai_nguon(self):
        text = """- [chặn] src/a.py:1 — mất dữ liệu khi lưu

```json
{"verdict": "block", "findings": [
  {"tag": "chặn", "file": "src/b.py", "line": 9, "why": "nuốt lỗi"}]}
```
"""
        got = _reconcile("STORY-01-01", EvidenceStore(self.root), text, review_verdict(text), role="review")
        self.assertEqual(len(got), 2, "mất mục nào là nới lỏng cổng")
        self.assertIn("src/a.py", got[0])
        self.assertIn("src/b.py", got[1])
        lech = self.notes()["review:mismatch"]
        self.assertEqual(len(lech["text"]), 1)
        self.assertEqual(len(lech["json"]), 1)

    def test_json_bo_mot_muc_cua_van_ban_van_bi_chan(self):
        text = "- [bế tắc] src/a.py:1 — ngoài write_scope\n\n" \
               '{"verdict": "pass", "findings": []}'
        got = _reconcile("STORY-01-01", EvidenceStore(self.root), text, review_verdict(text), role="review")
        self.assertEqual(len(plan_defects(got)), 1)
        self.assertIn("review:mismatch", self.notes())

    def test_merge_giu_thu_tu_van_ban_truoc(self):
        hop, lech = merge_findings(["[chặn] a.py:1 — x"], ["[chặn] a.py:2 — x"])
        self.assertEqual(hop, ["[chặn] a.py:1 — x"], "cùng tệp cùng thẻ là một mục")
        self.assertFalse(lech)


class TestSchemaBaoMat(SchemaTestCase):
    def test_severity_tu_json_duoc_hop_vao(self):
        text = """[high] src/api/note.ts:42 — id lấy thẳng từ query

```json
{"verdict": "block", "findings": [
  {"tag": "chặn", "severity": "critical", "file": "src/db.ts", "line": 7,
   "why": "chuỗi SQL nối tay", "behavior_id": "FR-3"}]}
```
"""
        rep = _reconcile_security("STORY-01-01", EvidenceStore(self.root), text, review_verdict(text))
        self.assertEqual([f.severity for f in rep.blocking()], ["critical", "high"])
        self.assertIn("security:mismatch", self.notes())
        self.assertEqual(self.notes()["security:verdict"]["findings"][0]["behavior_id"], "FR-3")

    def test_khong_co_json_thi_dung_van_ban_nhu_cu(self):
        rep = _reconcile_security(
            "STORY-01-01", EvidenceStore(self.root), "[high] src/a.ts:1 — lộ token", None)
        self.assertEqual(len(rep.blocking()), 1)
        self.assertIn("security:no-schema", self.notes())

    def test_muc_nhieu_van_bi_loc_du_den_tu_json(self):
        text = 'không có phát hiện bảo mật\n{"verdict": "pass", "findings": [' \
               '{"tag": "nên sửa", "severity": "low", "file": "src/a.ts", ' \
               '"why": "thiếu giới hạn tần suất"}]}'
        rep = _reconcile_security("STORY-01-01", EvidenceStore(self.root), text, review_verdict(text))
        self.assertEqual(rep.findings, [])
        self.assertEqual(len(rep.filtered), 1)
        self.assertEqual(rep.error, "")


if __name__ == "__main__":
    unittest.main()
