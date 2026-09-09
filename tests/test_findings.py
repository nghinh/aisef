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
from aisef.harness.observe import NOTE, Event, EvidenceStore  # noqa: E402
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
        self.assertEqual(v.blocking(), ["[block] src/a.py:1 — mất dữ liệu khi lưu"])

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
        self.assertTrue(v.blocking()[0].startswith("[stuck]"))


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
        self.assertIn("Missing JSON block", client.prompts[1])
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

    def _da_khuyen_nghi(self, sha: str, tag: str = "should fix"):
        """Lượt trước ở bản `sha`: đúng mục này chỉ được xếp *nên sửa*."""
        EvidenceStore(self.root, candidate=sha).record("STORY-01-01", Event(
            kind=NOTE, name="review:verdict", ok=True,
            detail={"verdict": "block", "findings": [
                {"tag": tag, "file": "src/a.py", "line": 27,
                 "why": "test chỉ kiểm một trường", "behavior_id": "AC-1"}]},
        ))

    def _luot_sau(self, text: str, sha: str = "bbb"):
        return _reconcile("STORY-01-01", EvidenceStore(self.root, candidate=sha),
                          text, review_verdict(text), role="review")

    #: Lượt sau nâng đúng mục đó lên chặn.
    NANG_CAP = """- [block] src/a.py:31 — test chỉ kiểm một trường

```json
{"verdict": "block", "findings": [
  {"tag": "block", "file": "src/a.py", "line": 31,
   "why": "test chỉ kiểm một trường", "behavior_id": "AC-1"}]}
```
"""

    def test_muc_da_xep_nen_sua_khong_duoc_nang_thanh_chan(self):
        """Nâng *nên sửa* của lượt trước thành *chặn* là dời cột mốc: tác giả
        sửa hết mục chặn rồi bị chặn bởi tầng dưới, story cháy hết lượt mà
        không hội tụ (todo/STORY-01-01)."""
        self._da_khuyen_nghi("aaa")
        self.assertEqual(self._luot_sau(self.NANG_CAP), [], "phải hạ về nên sửa")
        self.assertIn("review:no-escalation", self.notes())
        self.assertEqual(self.notes()["review:verdict"]["verdict"], "pass")

    def test_muc_da_chan_lan_truoc_van_duoc_chan_lai(self):
        """Chưa sửa thì chặn tiếp — quy tắc chỉ cấm *nâng cấp*, không xoá trí nhớ."""
        self._da_khuyen_nghi("aaa", tag="block")
        self.assertEqual(len(self._luot_sau(self.NANG_CAP)), 1)
        self.assertNotIn("review:no-escalation", self.notes())

    def test_muc_moi_o_tep_do_van_chan_duoc(self):
        """Hạ cấp theo (tệp, behavior_id): tiêu chí khác trong cùng tệp vẫn chặn."""
        self._da_khuyen_nghi("aaa")
        text = self.NANG_CAP.replace('"AC-1"', '"AC-9"')
        self.assertEqual(len(self._luot_sau(text)), 1)

    def test_ket_luan_cua_chinh_luot_nay_khong_tinh_la_lan_truoc(self):
        """Ghi nhận của cùng bản là kết luận hiện tại, không phải lập trường cũ."""
        self._da_khuyen_nghi("bbb")
        self.assertEqual(len(self._luot_sau(self.NANG_CAP, sha="bbb")), 1)

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


class TestPhatHienCuKhongThuocDiffNay(unittest.TestCase):
    """Lỗi 40. Mục người rà soát nêu ở lượt trước được đưa lại cho chính họ để
    chặn "dời cột gôn". Nhưng mục nhắm vào tệp **không còn trong diff** thì đưa
    lại chính là mời họ nêu lần nữa: người rà soát bảo mật lặp lại phiếu nhắm
    `.opencode/plugin/aisef-guard.ts` — tệp do harness ghi, story không hề chạm
    — và lần thứ hai nâng từ `high` lên `critical` (todo/STORY-01-02
    2026-09-09). Thứ không nằm trong diff của ứng viên này không phải việc của
    ứng viên này.
    """

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _ghi(self):
        from aisef.harness.observe import NOTE, EvidenceStore, Event
        st = EvidenceStore(self.root, candidate="cu")
        st.record("S-01", Event(kind=NOTE, name="security:verdict", ok=False, detail={
            "verdict": "block",
            "candidate": "cu",
            "findings": [
                {"tag": "block", "file": "js/main.js", "line": 3, "why": "mat du lieu"},
                {"tag": "block", "file": ".opencode/plugin/aisef-guard.ts", "line": 13,
                 "why": "PATH hijacking"},
            ],
        }))
        return EvidenceStore(self.root, candidate="moi")

    def test_bo_muc_ve_tep_ngoai_diff(self):
        from aisef.phases.implement import _prior_review
        got = _prior_review(self._ghi(), "S-01", role="security", changed=["js/main.js"])
        self.assertIn("js/main.js", got)
        self.assertNotIn("aisef-guard", got, "tệp ngoài diff không được đưa lại")

    def test_khong_biet_diff_thi_giu_nguyen(self):
        from aisef.phases.implement import _prior_review
        got = _prior_review(self._ghi(), "S-01", role="security", changed=[])
        self.assertIn("aisef-guard", got, "không có diff để lọc thì không đoán")
