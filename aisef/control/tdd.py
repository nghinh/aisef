"""TDD kiểm được (G8): đỏ trước xanh, và test có sẵn không bị yếu đi.

Prompt đã đòi "viết test trước, thấy nó đỏ" từ lâu; đây là lần đầu máy
kiểm. Hai tín hiệu, một chặn một cảnh báo:

1. **Đỏ trước xanh** — story *thêm* test (tệp test mới, hoặc dòng mới mang
   mã ``AC-<story>-``) thì bằng chứng phải có một lần ``test`` đỏ **trước**
   lần xanh cuối. Xanh ngay từ đầu chưa chứng minh test kiểm được gì.
   Story không thêm test (refactor thuần) thì không áp dụng — không đoán.
2. **Test biến mất** — tệp test có ở điểm rẽ nhánh mà số ca giảm thì đưa
   cho người rà soát, kèm tên tệp và số. Không tự chặn: "cập nhật kỳ vọng"
   là hợp lệ và cần phán đoán.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from ..harness.observe import TOOL_RUN, Evidence
from .impact import is_test_path

TEST_FUNC = re.compile(r"^\s*(def test_|it\(|test\(|func Test)", re.MULTILINE)


def _git(cwd: Path | str, *args: str) -> str:
    try:
        p = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return ""
    return p.stdout if p.returncode == 0 else ""


def added_tests(workdir: Path | str, *, base_ref: str, changed: list[str], story_id: str) -> list[str]:
    """Tệp test story **thêm**: mới so với điểm rẽ (kể cả chưa theo dõi),
    hoặc có dòng mới mang mã tiêu chí của story."""
    workdir = Path(workdir)
    tests = [f for f in changed if is_test_path(f)]
    if not tests:
        return []
    o_goc = set()
    if base_ref:
        o_goc = {l.strip() for l in _git(workdir, "ls-tree", "-r", "--name-only", base_ref).splitlines()}
    out = []
    for f in tests:
        if f not in o_goc:
            out.append(f)                       # tệp mới
            continue
        diff = _git(workdir, "diff", base_ref, "--", f) if base_ref else _git(workdir, "diff", "HEAD", "--", f)
        if any(l.startswith("+") and not l.startswith("+++") and f"AC-{story_id}-" in l.replace("_", "-")
               for l in diff.splitlines()):
            out.append(f)                       # tiêu chí mới có test
    return out


def red_before_green(evidence: Evidence) -> bool:
    """Có lần `test` đỏ (chạy thật, không phải bỏ qua) trước lần xanh cuối."""
    runs = evidence.of(TOOL_RUN, "test")
    greens = [e for e in runs if e.ok]
    if not greens:
        return False
    last_green = greens[-1]
    return any((not e.ok) and not e.detail.get("skipped") and e.seq < last_green.seq for e in runs)


def test_delta(workdir: Path | str, *, base_ref: str, changed: list[str]) -> list[str]:
    """Tệp test có sẵn mà số ca giảm: `"path: 5 → 3"`."""
    if not base_ref:
        return []
    workdir = Path(workdir)
    out = []
    for f in changed:
        if not is_test_path(f):
            continue
        truoc = _git(workdir, "show", f"{base_ref}:{f}")
        if not truoc:
            continue
        p = workdir / f
        sau = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""
        n0, n1 = len(TEST_FUNC.findall(truoc)), len(TEST_FUNC.findall(sau))
        if n1 < n0:
            out.append(f"{f}: {n0} → {n1}")
    return out
