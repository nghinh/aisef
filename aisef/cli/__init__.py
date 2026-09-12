"""Command-line interface.

Every command is **fire-and-forget**: read on-disk state, do work, write back,
then exit.  No command assumes it is the main process, none runs in the
background.  This is what allows the same command set to work in two modes
(decision D2):

* **driver-led** — a script or CI calls ``aisef run``;
* **agent-led** — the agent itself calls ``aisef next`` / ``verify`` /
  ``complete`` via Bash, inside a Claude Desktop or OpenCode chat session.

Exit code convention: ``0`` success · ``1`` usage error · ``2`` not-ready
state (gate unapproved, doctor check failed) — so CI can distinguish
"broken" from "not yet done".

Package layout (split by phase, no behaviour change):

* :mod:`._common` — exit codes, artifact root, approval/state stores, adapter;
* :mod:`.doctor` — ``doctor`` command;
* :mod:`.plan` — human gates + planning phase;
* :mod:`.implement` — implementation and acceptance phase;
* :mod:`.harness` — harness setup and operation;
* :mod:`.parser` — argument parser and ``main``.

All legacy module-level names are re-exported here, so ``from aisef.cli import
main`` and friends still work as they did when this was a single file.
"""

from __future__ import annotations

from ._common import (
    ARTIFACT_ROOT,
    _GATE_MARK,  # noqa: F401 — tái xuất cho tương thích ngược
    EXIT_NOT_READY,
    EXIT_OK,
    EXIT_USAGE,
    _approvals,  # noqa: F401 — tái xuất cho tương thích ngược
    _artifact_root,  # noqa: F401 — tái xuất cho tương thích ngược
    _client,  # noqa: F401 — tái xuất cho tương thích ngược
    _gate_arg,  # noqa: F401 — tái xuất cho tương thích ngược
    _state,  # noqa: F401 — tái xuất cho tương thích ngược
)
from .doctor import _hook_paths_elsewhere, cmd_doctor  # noqa: F401 — tái xuất cho tương thích ngược
from .harness import cmd_baseline, cmd_compile, cmd_doc, cmd_guard, cmd_init, cmd_setup, cmd_skill
from .implement import (
    _project_has_ui,  # noqa: F401 — tái xuất cho tương thích ngược
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
    _preflight_lines,  # noqa: F401 — tái xuất cho tương thích ngược
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
    "cmd_baseline",
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
