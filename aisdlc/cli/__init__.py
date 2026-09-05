"""Giao diện dòng lệnh.

Mọi lệnh đều **gọi-một-lần**: đọc trạng thái trên đĩa, làm việc, ghi lại,
rồi thoát. Không lệnh nào giả định mình là tiến trình chính, không lệnh
nào chạy nền. Đó là điều kiện để cùng bộ lệnh này dùng được ở hai chế độ
(quyết định Đ2):

* **driver-led** — script hoặc CI gọi ``aisdlc run``;
* **agent-led** — chính agent gọi ``aisdlc next`` / ``verify`` / ``complete``
  qua Bash, ngay trong phiên chat của Claude Desktop hay OpenCode.

Quy ước mã thoát: ``0`` thành công · ``1`` lỗi dùng sai · ``2`` trạng thái
chưa đạt (cổng chưa duyệt, doctor không đạt) — để CI phân biệt được
"hỏng" với "chưa xong".

Bố cục gói (chia theo pha, không đổi hành vi):

* :mod:`._common` — mã thoát, gốc artifact, kho duyệt/trạng thái, adapter;
* :mod:`.doctor` — lệnh ``doctor``;
* :mod:`.plan` — cổng người + pha lập kế hoạch;
* :mod:`.implement` — pha hiện thực và nghiệm thu;
* :mod:`.harness` — dựng và vận hành harness;
* :mod:`.parser` — bộ phân tích tham số và ``main``.

Mọi tên module-level cũ được xuất lại ở đây, nên ``from aisdlc.cli import
main`` và bạn bè vẫn chạy y như khi còn là một file.
"""

from __future__ import annotations

from ._common import (
    ARTIFACT_ROOT,
    _GATE_MARK,
    EXIT_NOT_READY,
    EXIT_OK,
    EXIT_USAGE,
    _approvals,
    _artifact_root,
    _client,
    _gate_arg,
    _state,
)
from .doctor import _hook_paths_elsewhere, cmd_doctor
from .harness import cmd_compile, cmd_doc, cmd_guard, cmd_init, cmd_setup, cmd_skill
from .implement import (
    _project_has_ui,
    cmd_devsecops,
    cmd_evidence,
    cmd_predeploy,
    cmd_qa,
    cmd_report,
    cmd_run,
    cmd_status,
    cmd_tool,
    cmd_verify,
)
from .parser import build_parser, main
from .plan import (
    _preflight_lines,
    cmd_approve,
    cmd_auto_approve,
    cmd_change,
    cmd_gates,
    cmd_mockup,
    cmd_plan,
    cmd_reject,
    cmd_review,
)

__all__ = [
    "ARTIFACT_ROOT",
    "EXIT_NOT_READY",
    "EXIT_OK",
    "EXIT_USAGE",
    "build_parser",
    "cmd_approve",
    "cmd_auto_approve",
    "cmd_change",
    "cmd_compile",
    "cmd_devsecops",
    "cmd_doc",
    "cmd_doctor",
    "cmd_evidence",
    "cmd_gates",
    "cmd_guard",
    "cmd_init",
    "cmd_mockup",
    "cmd_plan",
    "cmd_predeploy",
    "cmd_qa",
    "cmd_reject",
    "cmd_report",
    "cmd_review",
    "cmd_run",
    "cmd_setup",
    "cmd_skill",
    "cmd_status",
    "cmd_tool",
    "cmd_verify",
    "main",
]
