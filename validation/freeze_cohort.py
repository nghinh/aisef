#!/usr/bin/env python3
"""Đóng băng một cohort benchmark thành bằng chứng bất biến cho G5.2.

Vì sao tách khỏi bộ chấm: `aisef closure` chỉ **đọc**, và phải đọc được trên
một máy không có kho phiên của OpenCode. Nhưng danh tính từng phiên chỉ có
trong `opencode.db` (3,5 GB, cục bộ, không đi theo kho). Cách duy nhất giữ cả
hai là: trích ở đây một lần, ghi vào `closure-evidence/cohorts/`, để bộ chấm
đọc bản đã ghi.

    python3 validation/freeze_cohort.py C-2 --bench-dir .bench-c2 \\
        --report docs/BENCH-REPORT-C2.md --execution-sha <sha>
    python3 validation/freeze_cohort.py C-1 --historical \\
        --bench-dir .bench --limitation "..."

Đóng băng là **một chiều**: chạy lại trên cohort đã có bản khai sẽ từ chối,
trừ khi `--force`. Một cohort có thể khai lại sau khi đã thấy kết quả thì nó
không còn là ràng buộc nào cả.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.control import cohort as C  # noqa: E402
from aisef.control.closure import AmbiguousRegion, frozen_region_digest  # noqa: E402

OUT = ROOT / C.COHORT_DIR


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _find(o, key):
    """Tìm một khoá ở bất kỳ độ sâu nào trong tệp tiêu chí."""
    if isinstance(o, dict):
        for k, v in o.items():
            if k == key:
                return v
            got = _find(v, key)
            if got is not None:
                return got
    elif isinstance(o, list):
        for x in o:
            got = _find(x, key)
            if got is not None:
                return got
    return None


def freeze_current(cid: str, bench_dir: str, report: str, execution_sha: str,
                   protocol: str, scoring: str, force: bool) -> int:
    from tests.bench import _analyze as A
    from tests.bench import _mine as M

    decl_path = OUT / f"{cid}.json"
    if decl_path.exists() and not force:
        print(f"{decl_path.relative_to(ROOT)} đã tồn tại — đóng băng là một "
              f"chiều; dùng --force nếu thật sự muốn khai lại", file=sys.stderr)
        return 2

    raw = ROOT / bench_dir / "results.jsonl"
    if not raw.is_file():
        print(f"không có {raw}", file=sys.stderr)
        return 2
    OUT.mkdir(parents=True, exist_ok=True)

    attempts_path = OUT / f"{cid}-attempts.jsonl"
    shutil.copyfile(raw, attempts_path)
    rows = [json.loads(x) for x in attempts_path.read_text(encoding="utf-8").splitlines() if x.strip()]

    sessions = A.session_rows(bench_dir=bench_dir)
    sessions_path = OUT / f"{cid}-sessions.json"
    sessions_path.write_text(json.dumps(
        {"cohort_id": cid, "source": "opencode session store (read-only)",
         "bench_dir": bench_dir, "sessions": sessions},
        indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")

    # Vùng và công thức đến **từ tệp tiêu chí**, không viết cứng ở đây — §1.1
    # nói công thức không được có bản thứ hai.
    spec = json.loads((ROOT / "docs" / "closure-gate.json").read_text(encoding="utf-8"))
    region = _find(spec, "prereg_frozen_region")
    if region is None:
        print("tệp tiêu chí không khai prereg_frozen_region", file=sys.stderr)
        return 2
    try:
        pdigest = frozen_region_digest(ROOT / protocol, region)
    except (AmbiguousRegion, OSError, ValueError) as e:
        print(f"không đọc được vùng đóng băng của {protocol}: {e}", file=sys.stderr)
        return 2

    totals = C.compute_totals(rows, sessions)
    decl = {
        "cohort_id": cid,
        "status": C.CURRENT,
        "protocol_path": protocol,
        "protocol_digest": pdigest,
        "benchmark_execution_sha": execution_sha,
        "manifest_sha256": _sha(M.TASKS_DIR / "MANIFEST.sha256"),
        "scoring_version": scoring,
        "infra_statuses": list(C.DEFAULT_INFRA_STATUSES),
        "attempts": {"path": str(attempts_path.relative_to(ROOT)),
                     "sha256": _sha(attempts_path), "count": len(rows)},
        "sessions": {"path": str(sessions_path.relative_to(ROOT)),
                     "sha256": _sha(sessions_path), "count": len(sessions)},
        "report": report,
        "excluded": [],
        "totals": totals,
    }
    decl["totals_sha256"] = C.totals_digest(totals)
    decl_path.write_text(json.dumps(decl, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
                         encoding="utf-8")
    print(f"  wrote {decl_path.relative_to(ROOT)}")
    print(f"  wrote {attempts_path.relative_to(ROOT)} ({len(rows)} lượt)")
    print(f"  wrote {sessions_path.relative_to(ROOT)} ({len(sessions)} phiên)")
    print(f"\ntotals_sha256 = {decl['totals_sha256']}")
    print("  báo cáo phải mang đúng chuỗi này, nếu không G5.2 đỏ.")
    return 0


def freeze_historical(cid: str, bench_dir: str, limitation: str, force: bool) -> int:
    decl_path = OUT / f"{cid}.json"
    if decl_path.exists() and not force:
        print(f"{decl_path.relative_to(ROOT)} đã tồn tại", file=sys.stderr)
        return 2
    raw = ROOT / bench_dir / "results.jsonl"
    if not raw.is_file():
        print(f"không có {raw}", file=sys.stderr)
        return 2
    OUT.mkdir(parents=True, exist_ok=True)
    rows = [x for x in raw.read_text(encoding="utf-8").splitlines() if x.strip()]
    blank = sum(1 for x in rows if not json.loads(x).get("exit_status"))
    decl = {
        "cohort_id": cid,
        "status": C.HISTORICAL,
        # Bằng chứng gốc **không** được sao, không được sửa, không được dời.
        # Chỉ ghim vân tay để "không đổi" là thứ kiểm được chứ không phải thứ
        # được tuyên bố.
        "raw_path": str(raw.relative_to(ROOT)),
        "raw_sha256": _sha(raw),
        "rows": len(rows),
        "rows_without_exit_status": blank,
        "limitation": limitation,
        "report": None,
    }
    decl_path.write_text(json.dumps(decl, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
                         encoding="utf-8")
    print(f"  wrote {decl_path.relative_to(ROOT)} ({len(rows)} dòng, {blank} không có exit_status)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cohort_id")
    ap.add_argument("--bench-dir", required=True)
    ap.add_argument("--historical", action="store_true")
    ap.add_argument("--limitation", default="")
    ap.add_argument("--report", default="")
    ap.add_argument("--execution-sha", default="")
    ap.add_argument("--protocol", default="docs/handoff/bench-real-model-wiring.md")
    ap.add_argument("--scoring-version", default="")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if a.historical:
        if not a.limitation:
            print("cohort lịch sử phải khai --limitation", file=sys.stderr)
            return 2
        return freeze_historical(a.cohort_id, a.bench_dir, a.limitation, a.force)
    for need, flag in ((a.report, "--report"), (a.execution_sha, "--execution-sha"),
                       (a.scoring_version, "--scoring-version")):
        if not need:
            print(f"cohort hiện hành phải khai {flag}", file=sys.stderr)
            return 2
    return freeze_current(a.cohort_id, a.bench_dir, a.report, a.execution_sha,
                          a.protocol, a.scoring_version, a.force)


if __name__ == "__main__":
    raise SystemExit(main())
