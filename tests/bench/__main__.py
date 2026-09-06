"""`python3 -m tests.bench {mine,validate,run,report,export}` — bench ADR-005 V8.

Không nối vào `aisdlc` CLI: bench là việc của người phát triển harness, không
phải của dự án dùng harness, và một lệnh `-m` ít mã hơn một sub-parser.
"""

from __future__ import annotations

import argparse
import os
import sys

from . import _mine as M
from . import _runner as R


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python3 -m tests.bench", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("mine", help="đào task: lỗi kho → tests/bench/tasks; story e9 (--e9 / AISDLC_BENCH_E9) → .bench/tasks")
    m.add_argument("--e9", default=os.environ.get("AISDLC_BENCH_E9", ""))
    m.add_argument("--no-bugs", action="store_true")
    v = sub.add_parser("validate", help="base+test đỏ, base+test+gold xanh, ×--runs; test chập chờn loại và nêu tên")
    v.add_argument("ids", nargs="*")
    v.add_argument("--runs", type=int, default=3)
    r = sub.add_parser("run", help="một phiên client mỗi lượt, --attempts lượt (cần AISDLC_BENCH=1, tốn tiền)")
    r.add_argument("ids", nargs="*")
    r.add_argument("--client", default="claude")
    r.add_argument("--attempts", type=int, default=3)
    sub.add_parser("report", help="báo cáo Markdown từ .bench/results.jsonl")
    e = sub.add_parser("export", help="xuất một task ra thư mục định dạng Harbor")
    e.add_argument("id")
    e.add_argument("--out", default=str(R.KEEP_DIR / "harbor"))
    a = p.parse_args(argv)

    tasks = M.load_tasks(M.TASKS_DIR, M.KEEP_DIR / "tasks")
    ids = getattr(a, "ids", [])
    pick = [t for t in tasks if not ids or t.id in ids]
    if a.cmd == "mine":
        got = [] if a.no_bugs else M.mine_bugs(R.ROOT)
        if a.e9:
            os.environ["AISDLC_BENCH_E9"] = a.e9
            got += M.mine_stories(a.e9)
        for t in got:
            print(f"{t.id:14s} base={t.base[:7] or '—':8s} {'too_big · ' if t.too_big else ''}{t.invalid_reason or 'ok'}")
        for k, why in M.SKIPPED_BUGS.items():
            print(f"bỏ lỗi {k}: {why}")
    elif a.cmd == "validate":
        for t in pick:
            t = R.validate(t, runs=a.runs)
            print(f"{t.id:14s} F2P={len(t.f2p_ids)} P2P={len(t.p2p_ids)} flaky={t.flaky_ids} "
                  f"{t.invalid_reason or 'ok'}")
    elif a.cmd == "run":
        if not R.ENABLED:
            print("đặt AISDLC_BENCH=1 — chạy client thật tốn tiền", file=sys.stderr)
            return 1
        from aisdlc.clients.compile import ADAPTERS
        res = [x for t in pick for x in R.run(t, ADAPTERS[a.client](), attempts=a.attempts)]
        print(R.report(res, tasks))
    elif a.cmd == "report":
        print(R.report(R.load_results(), tasks))
    elif a.cmd == "export":
        print(R.export(next(t for t in tasks if t.id == a.id), a.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
