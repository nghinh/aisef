"""The canonical defect register — closure criterion G2.3.

Two facts the whole contract turns on, and one file that must keep them apart:

* **absent** means nobody wrote the register, so G2.3 cannot be evaluated
  (`UNRUNNABLE`, which blocks);
* **present and empty** means somebody looked and found nothing outstanding,
  which is a real PASS.

Everything else here is the same rule from the other side: a row the reader
cannot understand — unknown severity, missing id, duplicate id, a typo'd field
name — is an error, never a silently skipped row. A register that drops the one
row nobody could parse is worse than no register, because it reads green.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.control import defects as D  # noqa: E402

MINIMAL = {
    "id": "D-999",
    "severity": "P0",
    "status": "OPEN",
    "title": "a defect",
    "evidence": "python3 -m pytest tests/test_defects.py",
}


def register(*entries: dict, **header) -> dict:
    out = {
        "register_version": "1",
        "severity_scale": {"source": D.SEVERITY_SOURCE, "blocking": list(D.BLOCKING)},
        "defects": list(entries),
    }
    out.update(header)
    return out


class RegisterTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "DEFECT-REGISTER.json"

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, payload) -> Path:
        self.path.write_text(json.dumps(payload), encoding="utf-8")
        return self.path


class TestAbsentIsNotEmpty(RegisterTestCase):
    """The distinction closure is built on: nobody wrote one vs nothing is open."""

    def test_absent_register_is_its_own_error(self):
        with self.assertRaises(D.RegisterAbsent):
            D.read(self.path)

    def test_absent_is_not_reported_as_an_empty_register(self):
        with self.assertRaises(Exception) as ctx:
            D.read(self.path)
        self.assertNotIsInstance(ctx.exception, D.RegisterError,
                                 "a missing file must not read as a malformed one either")

    def test_present_and_empty_is_a_real_pass(self):
        self.assertEqual(D.read(self.write(register())), ())
        self.assertEqual(D.blocking(D.read(self.path)), ())


class TestInvalidRowsAreErrors(RegisterTestCase):
    def test_unknown_severity(self):
        with self.assertRaises(D.RegisterError) as ctx:
            D.read(self.write(register({**MINIMAL, "severity": "P4"})))
        self.assertIn("P4", str(ctx.exception))

    def test_missing_id(self):
        entry = {k: v for k, v in MINIMAL.items() if k != "id"}
        with self.assertRaises(D.RegisterError) as ctx:
            D.read(self.write(register(entry)))
        self.assertIn("id", str(ctx.exception))

    def test_duplicate_id(self):
        with self.assertRaises(D.RegisterError) as ctx:
            D.read(self.write(register(MINIMAL, {**MINIMAL, "severity": "P2"})))
        self.assertIn("D-999", str(ctx.exception))

    def test_unknown_status(self):
        with self.assertRaises(D.RegisterError):
            D.read(self.write(register({**MINIMAL, "status": "open"})))

    def test_typo_in_a_field_name_is_not_dropped(self):
        with self.assertRaises(D.RegisterError) as ctx:
            D.read(self.write(register({**MINIMAL, "severty": "P0"})))
        self.assertIn("severty", str(ctx.exception))

    def test_missing_evidence(self):
        entry = {k: v for k, v in MINIMAL.items() if k != "evidence"}
        with self.assertRaises(D.RegisterError):
            D.read(self.write(register(entry)))

    def test_open_entry_may_not_carry_a_fix(self):
        with self.assertRaises(D.RegisterError):
            D.read(self.write(register({**MINIMAL, "fixed": "abc1234"})))

    def test_check_must_name_a_real_gate_check(self):
        with self.assertRaises(D.RegisterError):
            D.read(self.write(register({**MINIMAL, "check": "code review"})))
        self.assertEqual(D.read(self.write(register({**MINIMAL, "check": "review"})))[0].check,
                         "review")

    def test_unreadable_json_names_the_file(self):
        self.path.write_text("{not json", encoding="utf-8")
        with self.assertRaises(D.RegisterError) as ctx:
            D.read(self.path)
        self.assertIn(self.path.name, str(ctx.exception))


class TestOneSeverityScale(RegisterTestCase):
    """P0–P3 is defined once, in `docs/EXTERNAL-VALIDATION-v1.1.0.md`. A register
    that names another source, or redefines which severities block, is rejected
    rather than obeyed — that is how two scales stop drifting apart."""

    def test_a_second_scale_source_is_refused(self):
        with self.assertRaises(D.RegisterError):
            D.read(self.write(register(**{"severity_scale": {
                "source": "docs/SOMETHING-ELSE.md", "blocking": list(D.BLOCKING)}})))

    def test_the_blocking_set_cannot_be_edited_in_the_data(self):
        with self.assertRaises(D.RegisterError):
            D.read(self.write(register(**{"severity_scale": {
                "source": D.SEVERITY_SOURCE, "blocking": ["P0"]}})))


class TestDeterministicRead(RegisterTestCase):
    def test_order_does_not_depend_on_file_order(self):
        a = {**MINIMAL, "id": "D-001", "severity": "P2"}
        b = {**MINIMAL, "id": "D-002", "severity": "P0"}
        first = [d.id for d in D.read(self.write(register(a, b)))]
        second = [d.id for d in D.read(self.write(register(b, a)))]
        self.assertEqual(first, second)
        self.assertEqual(first, ["D-002", "D-001"], "severity then id")

    def test_blocking_is_open_p0_p1_only(self):
        rows = register(
            {**MINIMAL, "id": "D-001", "severity": "P0", "status": "OPEN"},
            {**MINIMAL, "id": "D-002", "severity": "P1", "status": "OPEN"},
            {**MINIMAL, "id": "D-003", "severity": "P2", "status": "OPEN"},
            {**MINIMAL, "id": "D-004", "severity": "P0", "status": "CLOSED",
             "fixed": "abc1234"},
        )
        self.assertEqual([d.id for d in D.blocking(D.read(self.write(rows)))],
                         ["D-001", "D-002"])


class TestTheRepositoryRegister(unittest.TestCase):
    """The register this repository ships is the one G2.3 reads, so the suite
    reads it too: a row that only the author's editor accepted is not a row."""

    @classmethod
    def setUpClass(cls):
        cls.defects = D.read(ROOT / D.PATH)

    def test_it_reads(self):
        self.assertTrue(self.defects, "seeded from measured open items, not empty today")

    def test_every_taxonomy_reference_is_a_row_that_exists(self):
        rows = set(re.findall(r"^\| *(\d+) *\|",
                              (ROOT / "docs" / "FAILURE-TAXONOMY.md").read_text(encoding="utf-8"),
                              re.M))
        for d in self.defects:
            if d.taxonomy is not None:
                with self.subTest(defect=d.id):
                    self.assertIn(str(d.taxonomy), rows,
                                  f"{d.id} points at taxonomy row {d.taxonomy}, which has no row")

    def test_no_entry_restates_the_taxonomy_instead_of_pointing_at_it(self):
        for d in self.defects:
            with self.subTest(defect=d.id):
                self.assertLess(len(d.title), 120, "the title names the defect; detail belongs in notes")


if __name__ == "__main__":
    unittest.main()


class TestPhanLoaiFalsePassChoG2_4a(unittest.TestCase):
    """G2.4a hỏi "có false PASS nào ở mục **tất định/cấu trúc** đang chặn không".

    Sổ phải **trả lời** được câu ấy. Im lặng thì probe đúng khi chấm
    `UNRUNNABLE` — nhưng một sổ không phân loại gì biến một tiêu chí *đang
    đạt* thành chưa chạy được, và "chưa ai phân loại" không phải bằng chứng
    khoẻ (cùng luật `UNCONFIGURED` → `UNRUNNABLE` của hợp đồng).
    """

    def test_moi_dong_khai_ro_co_phai_false_pass_khong(self):
        for d in D.read(ROOT / D.PATH):
            with self.subTest(defect=d.id):
                self.assertIn(d.false_pass, (True, False),
                              f"{d.id} không nói nó có phải false PASS hay không")

    def test_false_pass_o_muc_tat_dinh_thi_phai_ten_muc(self):
        for d in D.read(ROOT / D.PATH):
            if d.false_pass:
                with self.subTest(defect=d.id):
                    self.assertTrue(d.check, f"{d.id} khai false_pass mà không nêu mục nào")

    def test_khong_co_false_pass_tat_dinh_nao_dang_mo(self):
        """Đây là điều G2.4a khẳng định. Đỏ khi có, chứ không im lặng."""
        from aisef.control.gate import CHECK_KIND
        bad = [d.id for d in D.read(ROOT / D.PATH)
               if d.false_pass and d.status == "OPEN"
               and CHECK_KIND.get(d.check) in ("deterministic", "structural")]
        self.assertEqual(bad, [], f"false PASS tất định đang mở: {bad}")
