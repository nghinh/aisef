"""Suite đơn vị: provider mặc định **không mở container** (kế hoạch phát hành A2).

Mỗi `run_tool`/`run_suite` qua Docker mất 6–18 s một container trên máy đo,
suite đầy đủ 25–60 phút và nhạy tải máy. Test đơn vị kiểm **luật của
harness** — bằng chứng ghi gì, cổng đọc gì, "không chạy được ≠ đỏ" — không
kiểm Docker, nên `HostProvider` (chạy thật trên máy, khai NATIVE, xem
`harness/sandbox.py`) được đặt vào chỗ `docker`; mọi test cũ giữ nguyên cấu
hình và ý nghĩa. Docker thật chỉ ở test đánh dấu `needs_docker` và hợp quy
S1–S5, bật tường minh như hợp quy/dogfood:

    python3 -m unittest discover -s tests -q                      # nhanh, không Docker
    AISEF_TEST_DOCKER=1 python3 -m unittest tests.test_sandbox tests.test_tools -q

`unittest discover -s tests` **không** nạp gói này (start dir là top level),
nên module nào chạm sandbox thì `import tests` — một dòng, import là đủ.
Chạy theo tên module (`python3 -m unittest tests.test_qa`) nạp gói tự nhiên.
"""

from __future__ import annotations

import os
import unittest

from aisef.harness import sandbox

DOCKER = os.environ.get("AISEF_TEST_DOCKER") == "1"

#: Test cần Docker thật. Chỉ hỏi daemon khi đã bật — `docker info` mất
#: gần một giây, không trả cho mỗi lần import.
needs_docker = unittest.skipUnless(
    DOCKER and sandbox.docker_available(), "bật bằng AISEF_TEST_DOCKER=1 (cần daemon)"
)

if not DOCKER:
    sandbox.PROVIDERS["docker"] = sandbox.HostProvider()


def obligations(story_id: str, n: int, mode: str = "CHANGE_REQUIRED", requirement: str = "FR-1") -> dict:
    """Declared proof obligations for a fixture's criteria.

    Every plan declares what each criterion must SHOW (TDD proof policy V2, owner decision 2026-09-20); a fixture
    whose subject is another check declares the ordinary case so the plan is valid, exactly as a real plan must."""
    return {f"AC-{story_id}-{i}": {"ac_id": f"AC-{story_id}-{i}", "proof_mode": mode, "requirement": requirement}
            for i in range(1, n + 1)}
