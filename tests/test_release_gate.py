"""Cổng phát hành của **chính kho framework** — đọc bảng hợp quy bằng code.

Chạy với ``AISEF_RELEASE=1``. Không có biến đó thì bỏ qua, để bộ test
thường không đỏ chỉ vì bảng chưa được chạy tuần này.

V2: the release path (.github/workflows/release.yml) no longer runs the V1 gate below; the V2 stable release charter
replaces it with validation/v2_release_gate.py (G8, §10 — docs/v2/RELEASE-PROCESS.md), tested by V2ReleaseGate.
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.control import conformance as C  # noqa: E402

_s = importlib.util.spec_from_file_location("v2_release_gate", ROOT / "validation" / "v2_release_gate.py")
G = importlib.util.module_from_spec(_s)
_s.loader.exec_module(G)


class V2ReleaseGate(unittest.TestCase):
    """Production PyPI receives a version only when V2-STABLE-STATUS says FINAL_RELEASE_READY PASS with no open
    blocker and the owner's latest PRODUCTION_PUBLISH ruling authorizes exactly that version (charter §19, §22)."""

    READY = {"FINAL_RELEASE_READY": "PASS", "OPEN_V2_0_BLOCKERS": []}
    HELD = {"seq": 2, "approver": "human:owner", "decision": {"PRODUCTION_PUBLISH": "HELD for the owner"}}
    OK = {"seq": 3, "approver": "human:owner", "decision": {"PRODUCTION_PUBLISH": "AUTHORIZED", "VERSION": "2.0.0"}}

    def gate(self, *entries, version="2.0.0", pyproject="2.0.0", status=READY):
        return G.problems(version, pyproject, status, {"entries": [{"seq": 1, "decision": {}}, *entries]})

    def test_the_owner_authorizing_this_exact_version_passes(self):
        self.assertEqual(self.gate(self.HELD, self.OK), [])

    def test_held_unauthorized_or_revoked_publication_is_refused(self):
        self.assertTrue(self.gate(self.HELD))
        self.assertTrue(self.gate())
        self.assertTrue(self.gate(self.OK, dict(self.HELD, seq=4)))           # a later hold wins
        self.assertTrue(self.gate(dict(self.OK, approver="agent")))
        self.assertTrue(self.gate(self.OK, version="2.0.1", pyproject="2.0.1"))

    def test_rc_versions_a_tag_pyproject_mismatch_or_an_unready_status_are_refused(self):
        self.assertTrue(self.gate(dict(self.OK, decision={**self.OK["decision"], "VERSION": "2.0.0rc1"}),
                                  version="2.0.0rc1", pyproject="2.0.0rc1"))
        self.assertTrue(self.gate(self.OK, pyproject="1.7.6"))
        for status in ({"FINAL_RELEASE_READY": "NOT_STARTED", "OPEN_V2_0_BLOCKERS": []},
                       {"FINAL_RELEASE_READY": "PASS", "OPEN_V2_0_BLOCKERS": ["B13"]}, {"FINAL_RELEASE_READY": "PASS"}, {}):
            with self.subTest(status=status):
                self.assertTrue(self.gate(self.OK, status=status))


class ReleaseWorkflowsCannotPublishByAccident(unittest.TestCase):
    """B13 / charter G8: only a stable vX.Y.Z tag reaches production PyPI, and only behind every gate; RC / dev tags
    and manual runs reach staging.yml, which has no way to publish. Static: the YAML read as text."""

    W = ROOT / ".github" / "workflows"

    @staticmethod
    def code(f: Path) -> str:
        """The workflow without its comment lines: an explanation is not a configuration."""
        return "\n".join(line for line in f.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith("#"))

    def test_production_publish_is_stable_tags_only_and_behind_every_gate(self):
        code = self.code(self.W / "release.yml")
        on = code.split("\non:", 1)[1].split("\npermissions:", 1)[0]
        self.assertEqual(re.findall(r"(?m)^\s*(\w+):", on), ["push", "tags"])
        self.assertIn('tags: ["v[0-9]+.[0-9]+.[0-9]+"]', on)
        self.assertIn("needs: [stable-tag, tests, staging, v2-gate]", code)
        for gate in ("uses: ./.github/workflows/tests.yml", "uses: ./.github/workflows/staging.yml",
                     "python -P validation/v2_release_gate.py", r"^v[0-9]+\.[0-9]+\.[0-9]+$"):
            self.assertIn(gate, code)
        self.assertNotIn("AISEF_RELEASE=1", code)       # the V1 freshness gate is replaced on this path

    def test_no_other_workflow_can_publish(self):
        for f in sorted(self.W.glob("*.yml")):
            if f.name == "release.yml":
                continue
            code = self.code(f)
            with self.subTest(workflow=f.name):
                for publish in ("id-token", "pypi-publish", "twine upload"):
                    self.assertNotIn(publish, code)


@unittest.skipUnless(os.environ.get("AISEF_RELEASE") == "1", "chỉ khi phát hành (AISEF_RELEASE=1)")
class TestCongPhatHanh(unittest.TestCase):
    def test_bang_hop_quy_du_va_moi(self):
        p = ROOT / C.REPORT_PATH
        self.assertTrue(p.is_file(), "chưa có docs/CONFORMANCE.md — chạy hợp quy trước")
        ok, why = C.release_ready(C.parse(p.read_text(encoding="utf-8")))
        self.assertTrue(ok, why)

    def test_nghiem_thu_dogfood_theo_pham_vi(self):
        """Corpus nghiệm thu (e9 EPIC-01, QĐ C-a 2026-09-06) phải có cổng
        `pre-deploy` **đạt theo phạm vi khai** và **được duyệt** trên đúng bản
        báo cáo ấy — đọc từ đĩa, không từ STATUS. Đường dẫn dự án qua
        ``AISEF_ACCEPTANCE``; thiếu thì bỏ qua có nêu tên, không tính đạt.

        **Trạng thái 14/09: phép này chưa từng chạy kể từ 06/09.** Corpus nó
        được viết cho (e9) không còn trên máy nào (ADR-009 phase 3,
        `docs/handoff/o4-cost-per-outcome.md` §2), và `release.yml` gọi cổng
        phát hành **không** kèm ``AISEF_ACCEPTANCE`` — nên nó bỏ qua im lặng
        trong khi bản ghi phát hành đọc thành "PASSED". Đo lại 14/09 trên
        `todo-oc` (7/7 story done, 7 cổng người đã duyệt) bằng
        ``bin/aisef --project <todo-oc> pre-deploy --epic EPIC-01``: `scope`,
        `all stories done`, `human gates` đạt; còn đỏ `Dockerfile`,
        `CI workflow`, `runbook` (chưa chạy `aisef devsecops`), `isolation`
        (không có Docker, không khai `sandbox.pre_deploy_degraded_waiver`) và
        `verification` (7 loại chưa cấu hình, `mutation` unrunnable, không khai
        `verify.waived`). Một corpus thay thế phải có **cả** ba artefact
        devsecops, Docker chạy được hoặc waiver có lý do, và cổng `pre-deploy`
        do **người** duyệt trên đúng bản báo cáo ấy."""
        import json

        from aisef.control.approvals import PRE_DEPLOY_REPORT, ApprovalStore, Gate, Status

        root = os.environ.get("AISEF_ACCEPTANCE", "")
        if not root:
            self.skipTest(
                "AISEF_ACCEPTANCE=<dự án nghiệm thu> chưa đặt ⇒ phép nghiệm thu dogfood "
                "KHÔNG chạy. e9 (corpus gốc) không còn; `todo-oc` đo 14/09 chưa đủ "
                "(thiếu Dockerfile/CI/RUNBOOK, không có Docker, cổng pre-deploy chưa ai duyệt). "
                "Xem docstring của phép này."
            )
        art = Path(root) / "_bmad-output"
        rep_path = art / PRE_DEPLOY_REPORT
        self.assertTrue(rep_path.is_file(), f"chưa có {rep_path} — chạy `aisef pre-deploy --epic E`")
        rep = json.loads(rep_path.read_text(encoding="utf-8"))
        self.assertTrue(rep.get("passed"), "pre-deploy của corpus nghiệm thu KHÔNG ĐẠT")
        scope = rep.get("scope") or {}
        self.assertTrue(scope.get("epic"), "báo cáo không khai phạm vi (`--epic`) — nghiệm thu gì?")
        self.assertIs(ApprovalStore(art).status(Gate.PRE_DEPLOY), Status.APPROVED,
                      "cổng pre-deploy chưa duyệt, hoặc duyệt trên bản báo cáo khác (stale)")
        # Loại miễn phải có lý do ghi trong báo cáo — miễn không lý do không phải bằng chứng.
        for kind, why in (rep.get("waivers") or {}).items():
            self.assertTrue(str(why).strip(), f"{kind} miễn không lý do")
