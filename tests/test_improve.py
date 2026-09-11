"""Vòng cải tiến epic theo bằng chứng (ADR-004 R3) — `aisef improve`.

Chạy trên kho git thật với client giả: điều phải chứng minh là vòng **ghép**
đúng thứ có sẵn (QA → sổ → story sửa → `run_epic` → sổ) và **dừng bằng
code** ở đúng năm điều kiện — không phải agent viết code hay. Client giả
"sửa" bằng cách ghi một kịch bản test TAP vào phạm vi ghi; bằng chứng test
do chính harness chạy kịch bản ấy ghi ra, như với story thật.

Gap xuất phát là loại có thật ở HEAD đã merge: bộ test xanh nhưng **chưa có
test mang mã** tiêu chí (e9: 18 gap của 01-01/02/03). Test đỏ trên main
không tới được đây — cổng story đã chặn nó trước khi merge.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import tests  # noqa: E402,F401 — HostProvider vào chỗ docker, không mở container (tests/__init__.py)

from aisef.clients.base import Capability, ClientAdapter, RunSpec, Support  # noqa: E402
from aisef.clients.stream import RunResult  # noqa: E402
from aisef.config import DEFAULTS, Config  # noqa: E402
from aisef.control import ledger as L  # noqa: E402
from aisef.control.approvals import GATE_ORDER, ApprovalStore, Gate, Status  # noqa: E402
from aisef.control.journal import JournalStore  # noqa: E402
from aisef.harness.observe import HANDOFF, EvidenceStore  # noqa: E402
from aisef.phases.improve import improve  # noqa: E402

BEHAVIORS = ("AC-STORY-01-01-1", "AC-STORY-01-01-2")
TEST_SCRIPT = "src/core/suite.sh"

INDEX = {
    "epics": [{"id": "EPIC-01", "title": "nền"}],
    "stories": [{
        "id": "STORY-01-01", "epic_id": "EPIC-01", "title": "nền",
        "acceptance_criteria": ["đọc được a", "đọc được b"], "covers": [],
        "write_scope": ["src/core"], "depends_on": [], "screens": [],
        "verification_contract": ["unit"], "file": "stories/EPIC-01/STORY-01-01.md",
    }],
    "waves": {"EPIC-01": [["STORY-01-01"]]},
}


def tap_name(bid: str) -> str:
    return f"src/core/x.test.js > {bid} hành vi"


class Fixer(ClientAdapter):
    """Agent giả: sửa hành vi story sửa được giao bằng cách ghi kịch bản
    test TAP; `fix=False` thì viết kịch bản mà không sửa gì (mọi test đỏ)."""

    id = "fixer"

    def __init__(self, artifacts: Path, *, fix: bool = True, review: str = "không có mục chặn",
                 fail_first: int = 0):
        self.artifacts = artifacts
        self.fix = fix
        self.review = review
        self.fail_first = fail_first      # lượt developer đầu không ghi gì → trượt cổng
        self.fixed: set[str] = set()
        self.develop_calls: list[str] = []

    def available(self) -> bool:
        return True

    def capabilities(self):
        return {c: Support.NATIVE for c in Capability}

    def run(self, spec: RunSpec) -> RunResult:
        dau = spec.prompt.lstrip().splitlines()[0] if spec.prompt.strip() else ""
        if dau.startswith("# Security review"):
            return RunResult(ok=True, text="không có phát hiện bảo mật", cost_usd=0.1)
        if dau.startswith("# Review"):
            return RunResult(ok=True, text=self.review, cost_usd=0.1)

        sid = spec.env["AISEF_STORY_ID"]
        self.develop_calls.append(sid)
        if self.fail_first > 0:
            self.fail_first -= 1
            return RunResult(ok=True, text="xong", cost_usd=1.0)
        idx = json.loads((self.artifacts / "stories.index.json").read_text(encoding="utf-8"))
        rec = next(s for s in idx["stories"] if s["id"] == sid)
        if self.fix:
            self.fixed.add(rec["repair_of"])
        # Test mới mang mã của story sửa **và** mã gốc; `fix=False` chỉ có
        # test mang mã mới — story qua cổng của nó mà không đóng gap nào.
        # Runner thật không quên test cũ: giữ test có sẵn ở baseline (R9 chấm
        # "mất test" là hồi quy) và test của mọi story sửa trước (R4 đòi hành
        # vi VERIFIED của story khác còn xanh ở ứng viên).
        lines = ["TAP version 13", f"ok 1 - {BASE_TEST}"]
        truoc = [x for x in dict.fromkeys(self.develop_calls) if x != sid]
        for i, bid in enumerate([f"AC-{x}-1" for x in truoc] + [f"AC-{sid}-1"] + sorted(self.fixed), 2):
            lines.append(f"ok {i} - {tap_name(bid)}")
        script = Path(spec.workdir) / TEST_SCRIPT
        script.parent.mkdir(parents=True, exist_ok=True)
        # Runner thật thoát khác 0 khi có test đỏ — harness đọc mã thoát,
        # còn sổ đọc tên test; kịch bản phải giống runner ở cả hai chỗ.
        exit_code = 1 if any(l.startswith("not ok") for l in lines) else 0
        script.write_text("#!/bin/sh\n" + "\n".join(f"echo '{l}'" for l in lines)
                          + f"\nexit {exit_code}\n", encoding="utf-8")
        return RunResult(ok=True, text="xong", cost_usd=1.0)


#: Test có sẵn trước khi vòng sửa chạm vào — baseline R9 phải chạy được.
BASE_TEST = "src/core/x.test.js > khởi động"


class ImproveTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)
        for cmd in (["git", "init", "-q", "-b", "main"],
                    ["git", "config", "user.email", "t@t"],
                    ["git", "config", "user.name", "t"]):
            subprocess.run(cmd, cwd=self.project, check=True)
        (self.project / "README.md").write_text("dự án\n", encoding="utf-8")
        script = self.project / TEST_SCRIPT
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text(f"#!/bin/sh\necho 'TAP version 13'\necho 'ok 1 - {BASE_TEST}'\nexit 0\n",
                          encoding="utf-8")
        self.artifacts = self.project / "_bmad-output"
        self.artifacts.mkdir()
        (self.artifacts / "stories.index.json").write_text(
            json.dumps(INDEX, ensure_ascii=False), encoding="utf-8")
        # Trạng thái xuất phát: bộ test xanh, không test nào mang mã tiêu chí
        # của STORY-01-01 → hai tiêu chí là GAP "chưa có test mang mã".
        EvidenceStore(self.artifacts).tool_run(
            "STORY-01-01", "test", ok=True,
            detail={"test_format": "node-tap", "test_ids": [BASE_TEST],
                    "failed_ids": []},
        )
        subprocess.run(["git", "add", "-A"], cwd=self.project, check=True)
        subprocess.run(["git", "commit", "-qm", "kế hoạch"], cwd=self.project, check=True)

    def tearDown(self):
        self._tmp.cleanup()

    def config(self, **over):
        # Không Docker: mỗi lần chạy tool trong container mất ~3 s trên máy
        # có Docker, và điều phép thử này đo không nằm ở lớp cách ly.
        return Config({**DEFAULTS, "tools.test": f"sh {TEST_SCRIPT}", "tools.lint": "true",
                       "run.max_retries": 0, "sandbox.use_docker": False, **over})

    def improve(self, client, **kw):
        kw.setdefault("config", self.config())
        kw.setdefault("auto", True)
        kw.setdefault("has_ui", False)
        return improve(self.project, client, "EPIC-01", **kw)

    def ledger(self) -> L.Ledger:
        return L.build(self.artifacts)

    def index(self) -> dict:
        return json.loads((self.artifacts / "stories.index.json").read_text(encoding="utf-8"))


class TestRepairRecovery(ImproveTestCase):
    def test_intent_precedes_story_registration(self):
        from unittest.mock import patch

        with patch("aisef.phases.improve.repair_story", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.improve(Fixer(self.artifacts), max_loops=1)
        journal = JournalStore(self.artifacts).read("improve-EPIC-01")
        self.assertTrue(journal.reached("repair.intent"))
        with patch("aisef.phases.improve.run_epic") as dispatch:
            resumed = self.improve(Fixer(self.artifacts), max_loops=1)
        dispatch.assert_not_called()
        self.assertEqual([lo.n for lo in resumed.loops], [1])
        self.assertIn("interrupted", resumed.stopped)

    def test_dispatch_interruption_preserves_cost_and_budget(self):
        from unittest.mock import patch
        from aisef.phases.run import run_epic

        def interrupted(*args, **kwargs):
            run_epic(*args, **kwargs)
            raise KeyboardInterrupt

        client = Fixer(self.artifacts)
        with patch("aisef.phases.improve.run_epic", side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):
                self.improve(client, max_loops=1)
        with patch("aisef.phases.improve.run_epic") as dispatch:
            resumed = self.improve(client, max_loops=1)
        dispatch.assert_not_called()
        self.assertEqual([lo.n for lo in resumed.loops], [1])
        self.assertGreater(resumed.cost_usd, 1.0)
        again = self.improve(client, max_loops=1)
        self.assertEqual(again.loops, [])
        self.assertEqual(len([r for r in self.ledger().loops if r["n"] == "loop-1"]), 1)

    def test_lost_ledger_does_not_reset_round_budget(self):
        from unittest.mock import patch

        self.improve(Fixer(self.artifacts), max_loops=1)
        (self.artifacts / L.LEDGER_FILE).write_text("{")
        with patch("aisef.phases.improve.run_epic") as dispatch:
            result = self.improve(Fixer(self.artifacts), max_loops=1)
        dispatch.assert_not_called()
        self.assertEqual(result.loops, [])
        self.assertIn("max_loops", result.stopped)

    def test_report_interruption_does_not_duplicate_snapshot(self):
        from unittest.mock import patch

        with patch("aisef.phases.improve._write_report", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.improve(Fixer(self.artifacts), max_loops=1)
        with patch("aisef.phases.improve.run_epic") as dispatch:
            resumed = self.improve(Fixer(self.artifacts), max_loops=1)
        dispatch.assert_not_called()
        self.assertEqual([lo.n for lo in resumed.loops], [1])
        self.assertEqual(len([r for r in self.ledger().loops if r["n"] == "loop-1"]), 1)


class TestVongSuaGap(ImproveTestCase):
    def test_hai_gap_moi_vong_sua_mot_vong_ba_dung_vi_het_gap(self):
        """AC (a) của R3: 2 GAP → vòng 1 sửa 1, vòng 2 sửa 1, vòng 3 dừng."""
        r = self.improve(Fixer(self.artifacts), max_loops=3)
        self.assertEqual(r.error, "")
        self.assertEqual([lo.n for lo in r.loops], [1, 2], r.summary())
        self.assertEqual(len(r.loops[0].before["gaps"]), 2)
        self.assertEqual(len(r.loops[0].after["gaps"]), 1)
        self.assertEqual(len(r.loops[1].after["gaps"]), 0)
        self.assertIn("no GAP/REOPENED remaining", r.stopped)
        self.assertTrue(r.ok, r.summary())
        self.assertEqual([lo.behavior for lo in r.loops], list(BEHAVIORS))
        for lo in r.loops:
            self.assertTrue(lo.done, lo.outcome_text)
            self.assertEqual(lo.improvement, 1, "mỗi vòng đóng đúng một gap")

    def test_moc_vong_ghi_vao_so_dung_dinh_dang_r2(self):
        self.improve(Fixer(self.artifacts), max_loops=3)
        data = json.loads((self.artifacts / L.LEDGER_FILE).read_text(encoding="utf-8"))
        self.assertEqual([lo["n"] for lo in data["loops"]], ["loop-0", "loop-1", "loop-2"])
        for lo in data["loops"]:
            for key in ("n", "at", "verified", "gap", "reopened", "cost_usd", "epic",
                        "epic_verified", "epic_reopened"):
                self.assertIn(key, lo)
            self.assertEqual(lo["epic"], "EPIC-01")
        self.assertEqual(data["loops"][1]["story"], "STORY-RP-01")
        self.assertGreater(data["loops"][1]["cost_usd"], 1.0, "chi phí từ bằng chứng story sửa")
        self.assertEqual(data["loops"][0]["cost_usd"], 0.0, "mốc xuất phát không tốn gì")

    def test_moi_vong_mot_bao_cao(self):
        r = self.improve(Fixer(self.artifacts), max_loops=3)
        for n in (1, 2):
            path = self.artifacts / f"LOOP-REPORT-{n}.md"
            self.assertTrue(path.is_file(), path)
            text = path.read_text(encoding="utf-8")
            self.assertIn(f"STORY-RP-0{n}", text)
            self.assertIn("Epic gaps before", text)
            self.assertIn("Decision", text)
        self.assertIn("no GAP", (self.artifacts / "LOOP-REPORT-2.md").read_text(encoding="utf-8"))
        self.assertEqual([lo.report_path.name for lo in r.loops],
                         ["LOOP-REPORT-1.md", "LOOP-REPORT-2.md"])

    def test_story_sua_la_mot_hanh_vi_dung_dinh_dang_story_split(self):
        self.improve(Fixer(self.artifacts), max_loops=1)
        idx = self.index()
        rp = next(s for s in idx["stories"] if s["id"] == "STORY-RP-01")
        self.assertEqual(rp["epic_id"], "EPIC-RP-01")
        self.assertEqual(rp["repair_of"], "AC-STORY-01-01-1")
        self.assertEqual(rp["loop"], "loop-1")
        # `src/core` của story gốc + đường harness cấp cho hợp đồng kiểm định (lỗi 21), nằm trong đó.
        self.assertEqual(rp["write_scope"][0], "src/core")
        self.assertTrue(all(p.startswith("src/core") for p in rp["write_scope"]), rp["write_scope"])
        self.assertEqual(rp["depends_on"], [])
        self.assertEqual(rp["verification_contract"], ["unit"])
        self.assertEqual(len(rp["acceptance_criteria"]), 1)
        self.assertIn("AC-STORY-01-01-1", rp["acceptance_criteria"][0],
                      "giữ id hành vi để sổ khớp lại")
        self.assertEqual(rp["source"].get("why"), "no test carries this code", "nguồn của gap đi theo story")
        self.assertEqual(idx["waves"]["EPIC-RP-01"], [["STORY-RP-01"]])
        self.assertTrue(any(e["id"] == "EPIC-RP-01" for e in idx["epics"]))
        text = (self.artifacts / rp["file"]).read_text(encoding="utf-8")
        self.assertIn("[AC-STORY-RP-01-1]", text)
        self.assertIn("## Fix behavior", text)
        self.assertIn("aisef evidence AC-STORY-01-01-1", text)
        # story gốc không bị đụng
        self.assertTrue(any(s["id"] == "STORY-01-01" for s in idx["stories"]))

    def test_story_sua_vong_sau_ghi_hanh_vi_bao_toan(self):
        """R4 nạp slot từ đây: hành vi đã VERIFIED trong phạm vi ghi."""
        self.improve(Fixer(self.artifacts), max_loops=2)
        rp2 = next(s for s in self.index()["stories"] if s["id"] == "STORY-RP-02")
        self.assertIn("AC-STORY-01-01-1", rp2["preservation"])
        text = (self.artifacts / rp2["file"]).read_text(encoding="utf-8")
        self.assertIn("## Preservation", text)
        self.assertIn("AC-STORY-01-01-1", text)

    def test_bat_bien_moi_story_sua_di_qua_run_epic(self):
        """AC (b): worktree riêng, cổng, reviewer ≠ developer — đọc từ nhật ký
        và bằng chứng `handoff`, không từ lời mô-đun."""
        self.improve(Fixer(self.artifacts), max_loops=3)
        for sid in ("STORY-RP-01", "STORY-RP-02"):
            with self.subTest(story=sid):
                steps = JournalStore(self.artifacts).read(sid).steps()
                self.assertIn("worktree.created", steps, steps)
                self.assertIn("merge.completed", steps, steps)
                hand = EvidenceStore(self.artifacts).read(sid).of(HANDOFF)
                self.assertTrue(any(e.detail.get("from") == "developer"
                                    and e.detail.get("to") == "reviewer" for e in hand),
                                [e.name for e in hand])

    def test_bang_chung_qa_cap_du_an_la_moc_khong_phai_story(self):
        self.improve(Fixer(self.artifacts), max_loops=1,
                     config=self.config(**{"verify.unit": "true"}))
        led = self.ledger()
        self.assertEqual(led.behaviors["qa:unit"].since, "loop-0")
        self.assertNotIn("loop-0", led.stories)
        self.assertNotIn("loop-", (self.artifacts / L.INDEX_FILE).read_text(encoding="utf-8"))


class TestRepairQualification(ImproveTestCase):
    def test_required_missing_check_stops_without_agent(self):
        from unittest.mock import patch
        from aisef.harness.guardrails import head_sha
        from aisef.phases.qa import QaReport

        client = Fixer(self.artifacts)
        with patch("aisef.phases.improve.run_suite", return_value=QaReport(
                candidate=head_sha(self.project))):
            report = self.improve(client)
        self.assertFalse(report.ok)
        self.assertIn("required evidence missing: unit", report.stopped)
        self.assertEqual(client.develop_calls, [])

    def test_infrastructure_failure_is_not_a_product_repair(self):
        client = Fixer(self.artifacts)
        report = self.improve(client, config=self.config(**{
            "verify.unit": "aisef_nonexistent_test_command"}))
        self.assertIn("infrastructure", report.stopped)
        self.assertEqual(client.develop_calls, [])

    def test_stale_candidate_stops_without_agent(self):
        from unittest.mock import patch
        from aisef.phases.qa import QaReport

        client = Fixer(self.artifacts)
        with patch("aisef.phases.improve.run_suite", return_value=QaReport(candidate="old")):
            report = self.improve(client)
        self.assertIn("candidate", report.stopped)
        self.assertFalse(report.ok)
        self.assertEqual(client.develop_calls, [])

    def test_scripted_client_retry_repair_and_fresh_qa_lifecycle(self):
        from unittest.mock import patch
        from tests.test_implement import ScriptedClient
        from aisef.harness.guardrails import head_sha
        from aisef.phases.qa import run_suite

        fixer = Fixer(self.artifacts)

        class RepairClient(ScriptedClient):
            def run(inner, spec):
                result = super().run(spec)
                if result.ok and inner.calls[-1] == "develop":
                    return fixer.run(spec)
                return result

        client = RepairClient(writes=(), fail_first=1)
        candidates = []

        def measured(*args, **kwargs):
            result = run_suite(*args, **kwargs)
            candidates.append(result.candidate)
            return result

        with patch("aisef.phases.improve.run_suite", side_effect=measured):
            report = self.improve(client, config=self.config(**{"run.max_retries": 1}))
        self.assertTrue(report.ok, report.summary())
        self.assertEqual(len(report.loops), 2)
        self.assertEqual(client.calls.count("develop"), 3)
        self.assertEqual(len(set(candidates)), 3)
        self.assertEqual(candidates[-1], head_sha(self.project))
        for loop in report.loops:
            steps = JournalStore(self.artifacts).read(loop.story_id).steps()
            self.assertIn("merge.completed", steps)

    def test_product_failure_cannot_be_clean_when_epic_gaps_close(self):
        report = self.improve(Fixer(self.artifacts), config=self.config(**{
            "verify.sit": "false"}))
        self.assertEqual(len(report.loops), 2)
        self.assertEqual(report.gaps_left, [])
        self.assertFalse(report.ok)
        self.assertIn("product checks failed", report.stopped)

    def test_explicit_required_waiver_remains_supported(self):
        report = self.improve(Fixer(self.artifacts), config=self.config(**{
            "verify.waived": "unit"}))
        self.assertTrue(report.ok, report.summary())

    def test_clean_tree_fallback_cannot_qualify_candidate(self):
        from unittest.mock import patch
        from aisef.harness.guardrails import head_sha
        from aisef.phases.qa import KINDS, KindResult, QaReport

        candidate = head_sha(self.project)
        qa = QaReport(candidate=candidate, tree="agent-tree (fallback)",
                      results=[KindResult(KINDS["unit"], ran=True, ok=True)])
        client = Fixer(self.artifacts)
        with patch("aisef.phases.improve.run_suite", return_value=qa):
            report = self.improve(client)
        self.assertFalse(report.ok)
        self.assertIn("clean-tree evidence", report.stopped)
        self.assertEqual(client.develop_calls, [])

    def test_exact_cost_cap_does_not_open_another_round(self):
        from aisef.phases.improve import stop_reason

        led = L.Ledger()
        led.loops = [
            {"n": "loop-0", "epic": "EPIC-01"},
            {"n": "loop-1", "epic": "EPIC-01", "cost_usd": 1.0},
        ]
        reason = stop_reason(led, "EPIC-01", [object()], None, max_loops=5,
                             flat_loops=2, cost_cap=1.0, auto=True,
                             approvals=ApprovalStore(self.artifacts))
        self.assertIn("cost_cap_usd", reason)


class TestDieuKienDung(ImproveTestCase):
    def test_du_max_loops(self):
        r = self.improve(Fixer(self.artifacts), max_loops=1)
        self.assertEqual(len(r.loops), 1)
        self.assertIn("improve.max_loops = 1", r.stopped)
        self.assertEqual(r.gaps_left, ["AC-STORY-01-01-2"])
        self.assertFalse(r.ok)

    def test_cai_thien_bien_bang_khong_hai_vong_lien_thi_dung(self):
        """Story sửa qua cổng của **nó** (test mang mã mới xanh) mà không đóng
        gap nào: Δ toàn sổ vẫn dương, Δ hành vi thuộc epic mới bằng 0."""
        r = self.improve(Fixer(self.artifacts, fix=False), max_loops=5,
                         config=self.config(**{"improve.flat_loops": 2}))
        self.assertEqual([lo.n for lo in r.loops], [1, 2], r.summary())
        self.assertTrue(all(lo.done for lo in r.loops), "qua cổng nhưng vô ích")
        self.assertTrue(all(lo.improvement <= 0 for lo in r.loops))
        self.assertIn("marginal improvement ≤ 0 for 2 consecutive", r.stopped)
        self.assertGreater(self.ledger().summary()["verified"],
                           r.loops[0].before["verified"], "Δ toàn sổ dương — không dùng nó")

    def test_story_sua_truot_thi_vong_sau_chay_lai_no_khong_de_ban_sao(self):
        r = self.improve(Fixer(self.artifacts, fail_first=1), max_loops=2)
        self.assertEqual([lo.story_id for lo in r.loops], ["STORY-RP-01", "STORY-RP-01"])
        self.assertEqual([lo.done for lo in r.loops], [False, True])
        self.assertEqual([lo.improvement for lo in r.loops], [0, 1])
        rp = [s["id"] for s in self.index()["stories"] if s["id"].startswith("STORY-RP-")]
        self.assertEqual(rp, ["STORY-RP-01"])

    def test_vuot_tran_chi_phi(self):
        r = self.improve(Fixer(self.artifacts), max_loops=5,
                         config=self.config(**{"improve.cost_cap_usd": 1.0}))
        self.assertEqual(len(r.loops), 1)
        self.assertGreater(r.loops[0].cost_usd, 1.0)
        self.assertIn("improve.cost_cap_usd", r.stopped)

    def test_be_tac_ke_hoach_dung_va_tra_nguoi_kem_loi_reviewer(self):
        # Test xanh để tới được lượt rà soát; người rà soát kết luận bế tắc.
        c = Fixer(self.artifacts, review=(
            "[bế tắc] TCCN 1 — cần chỉ mục trong src/store/db.ts, ngoài "
            "write_scope. Đã kiểm chứng: đúng."
        ))
        r = self.improve(c, max_loops=5)
        self.assertEqual(len(r.loops), 1)
        self.assertIn("plan stuck", r.stopped)
        self.assertIn("src/store/db.ts", r.stopped, "lời người rà soát phải tới tay người")
        self.assertEqual(len(c.develop_calls), 1, "không thử tiếp trên cùng gap")

    def test_cong_nguoi_improve_truoc_vong_2(self):
        c = Fixer(self.artifacts)
        r = self.improve(c, max_loops=3, auto=False)
        self.assertEqual(len(r.loops), 1)
        self.assertIn("awaiting human approval", r.stopped)
        store = ApprovalStore(self.artifacts)
        self.assertIs(store.status(Gate.IMPROVE), Status.PENDING)
        self.assertTrue(store.has_artifacts(Gate.IMPROVE), "LOOP-REPORT-1.md là artifact")

        store.approve(Gate.IMPROVE, by="nghi")
        r2 = self.improve(c, max_loops=3, auto=False)
        self.assertEqual([lo.n for lo in r2.loops], [2], "chạy lại tiếp từ mốc cuối")
        self.assertIn("no GAP", r2.stopped)
        # báo cáo vòng 2 là artifact mới → phê duyệt cũ hết hiệu lực
        self.assertIs(store.status(Gate.IMPROVE), Status.STALE)

    def test_auto_khong_hoi_nguoi_nhung_van_bi_chan_boi_dieu_kien_khac(self):
        r = self.improve(Fixer(self.artifacts), max_loops=1, auto=True)
        self.assertNotIn("awaiting human", r.stopped)
        self.assertIn("max_loops", r.stopped)


class TestChayLai(ImproveTestCase):
    def test_chay_lai_tiep_tu_loops_cuoi_khong_dem_lai_tu_khong(self):
        c = Fixer(self.artifacts)
        self.improve(c, max_loops=1)
        r = self.improve(c, max_loops=1)
        self.assertEqual(r.loops, [], "đủ max_loops rồi thì không tốn thêm vòng nào")
        self.assertIn("max_loops", r.stopped)
        r = self.improve(c, max_loops=2)
        self.assertEqual([lo.n for lo in r.loops], [2])
        self.assertTrue((self.artifacts / "LOOP-REPORT-2.md").is_file())
        labels = [lo["n"] for lo in self.ledger().loops]
        self.assertEqual(labels, ["loop-0", "loop-1", "loop-2"])

    def test_so_doi_giua_hai_lan_goi_thi_ghi_lai_moc_xuat_phat(self):
        """Story thường chạy giữa hai lần `improve` không được tính vào Δ của vòng."""
        c = Fixer(self.artifacts)
        self.improve(c, max_loops=1)
        EvidenceStore(self.artifacts).tool_run(   # ai đó chạy `aisef tool test` tay
            "STORY-01-01", "test", ok=True,
            detail={"test_format": "node-tap", "test_ids": [tap_name(b) for b in BEHAVIORS],
                    "failed_ids": []},
        )
        r = self.improve(c, max_loops=3)
        self.assertEqual(r.loops, [])
        self.assertIn("no GAP", r.stopped)
        self.assertEqual([lo["n"] for lo in self.ledger().loops], ["loop-0", "loop-1", "loop-0"])


class TestLoiVao(ImproveTestCase):
    def test_epic_khong_co_trong_ke_hoach(self):
        r = improve(self.project, Fixer(self.artifacts), "EPIC-99", config=self.config())
        self.assertIn("not found in plan", r.error)

    def test_cli_chan_khi_readiness_chua_duyet(self):
        import io
        from contextlib import redirect_stderr, redirect_stdout

        from aisef.cli import EXIT_NOT_READY, main

        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["--project", str(self.project), "improve", "--epic", "EPIC-01"])
        self.assertEqual(code, EXIT_NOT_READY)
        self.assertIn("gate not approved", err.getvalue())

    def test_ba_knob_co_kieu_va_ngu_nghia(self):
        cfg = Config.load(self.project, env={})
        self.assertEqual(cfg["improve.max_loops"], 3)
        self.assertEqual(cfg["improve.flat_loops"], 2)
        self.assertEqual(cfg["improve.cost_cap_usd"], 0.0)
        from aisef.config import ConfigError
        with self.assertRaises(ConfigError):
            Config.load(self.project, env={"AISEF_IMPROVE_MAX_LOOPS": "0"})


class TestCongImprove(unittest.TestCase):
    """Cổng `improve` dùng đúng cơ chế phê duyệt gắn băm, nhưng đứng ngoài
    thứ tự vòng đời: dự án chưa chạy `improve` không bị nó chặn."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.store = ApprovalStore(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_artifact_la_moi_bao_cao_vong_bao_cao_moi_lam_stale(self):
        self.assertFalse(self.store.has_artifacts(Gate.IMPROVE))
        (self.root / "LOOP-REPORT-1.md").write_text("# vòng 1\n", encoding="utf-8")
        self.assertTrue(self.store.has_artifacts(Gate.IMPROVE))
        self.store.approve(Gate.IMPROVE, by="nghi")
        self.assertIs(self.store.status(Gate.IMPROVE), Status.APPROVED)
        (self.root / "LOOP-REPORT-2.md").write_text("# vòng 2\n", encoding="utf-8")
        self.assertIs(self.store.status(Gate.IMPROVE), Status.STALE)

    def test_khong_nam_trong_vong_doi_tam_cong(self):
        self.assertNotIn(Gate.IMPROVE, GATE_ORDER)
        self.assertEqual(self.store.blocking(Gate.IMPROVE), [])
        self.assertNotIn(Gate.IMPROVE, self.store.blocking(Gate.PRE_DEPLOY))
        self.assertEqual(len(self.store.summary()), len(GATE_ORDER))

    def test_bam_cong_cu_khong_doi(self):
        """Đổi cách băm mà làm phê duyệt cũ của tám cổng thành stale thì
        mọi dự án đang chạy phải duyệt lại — không được."""
        (self.root / "prd.md").write_text("# PRD\n", encoding="utf-8")
        import hashlib
        from aisef.control.approvals import sha256_of
        cu = hashlib.sha256(f"prd.md:{sha256_of(self.root / 'prd.md')}".encode()).hexdigest()
        self.assertEqual(self.store.content_hash(Gate.PRD), cu)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestHangDoiSuaTuDong(ImproveTestCase):
    """QĐ B6 2026-09-06: `qa:*` cấp dự án đứng ngoài hàng đợi tự động; tiêu
    chí có verifier cụ thể đi trước; story sửa phải viết test mới mang mã."""

    def test_thu_tu_hang_doi_va_qa_dung_ngoai(self):
        from aisef.phases.improve import repair_queue

        led = L.Ledger()
        for bid, kind in (("qa:e2e", "qa"), ("mockup:m", "mockup"), ("FR-1", "fr"),
                          ("AC-STORY-01-01-2", "ac"), ("AC-STORY-01-01-1", "ac")):
            led.observe(bid, kind, ok=False, at=1.0, story="STORY-01-01")
        led.observe("AC-STORY-01-01-2", "ac", ok=True, at=2.0, story="STORY-01-01")
        led.observe("AC-STORY-01-01-2", "ac", ok=False, at=3.0, story="STORY-01-02")
        q = [b.id for b in repair_queue(list(led.behaviors.values()))]
        self.assertEqual(q, ["AC-STORY-01-01-2", "AC-STORY-01-01-1", "FR-1", "mockup:m"],
                         "REOPENED trước, rồi ac → fr → mockup; qa:* không có mặt")

    def test_gap_qa_khong_mo_story_sua_va_ly_do_dung_neu_ten_no(self):
        EvidenceStore(self.artifacts).tool_run(
            "STORY-01-01", "qa:e2e", ok=False, detail={"tail": "đỏ"})
        fixer = Fixer(self.artifacts)
        r = self.improve(fixer, max_loops=5)
        self.assertEqual([lo.behavior for lo in r.loops], list(BEHAVIORS))
        self.assertNotIn("qa:e2e", [lo.behavior for lo in r.loops])
        self.assertIn("outside auto-repair queue", r.stopped)
        self.assertIn("qa:e2e", r.stopped)
        self.assertEqual(r.gaps_left, ["qa:e2e"], "vẫn là gap của epic, chỉ không sửa tự động")
        self.assertFalse(r.ok)

    def test_story_sua_doi_test_moi_mang_ma_va_chi_duong_truy_vet(self):
        self.improve(Fixer(self.artifacts), max_loops=1)
        body = next(self.artifacts.rglob("STORY-RP-01.md")).read_text(encoding="utf-8")
        self.assertIn("nop control", body)
        self.assertIn("not** add tags to existing tests", body)
        self.assertIn(f"aisef evidence {BEHAVIORS[0]} --link", body)

    def test_be_tac_truy_vet_thi_bao_cao_chi_cach_sua_sieu_du_lieu(self):
        r = self.improve(Fixer(self.artifacts, review=f"[bế tắc] truy vết: {BASE_TEST}"),
                         max_loops=2)
        self.assertEqual(len(r.loops), 1)
        self.assertIn("truy vết", r.loops[0].stuck)
        report = r.loops[0].report_path.read_text(encoding="utf-8")
        self.assertIn(f"aisef evidence {BEHAVIORS[0]} --link", report)
        self.assertIn("not** a functional improvement", report)
