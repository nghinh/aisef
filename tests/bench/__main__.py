"""`python3 -m tests.bench {mine,validate,run,report,export}` — bench ADR-005 V8.

Không nối vào `aisef` CLI: bench là việc của người phát triển harness, không
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
    m = sub.add_parser("mine", help="đào task: lỗi kho → tests/bench/tasks; story e9 (--e9 / AISEF_BENCH_E9) → .bench/tasks")
    m.add_argument("--e9", default=os.environ.get("AISEF_BENCH_E9", ""))
    m.add_argument("--no-bugs", action="store_true")
    v = sub.add_parser("validate", help="base+test đỏ, base+test+gold xanh, ×--runs; test chập chờn loại và nêu tên")
    v.add_argument("ids", nargs="*")
    v.add_argument("--runs", type=int, default=3)
    r = sub.add_parser("run", help="một phiên client mỗi lượt, --attempts lượt (cần AISEF_BENCH=1, tốn tiền)")
    r.add_argument("ids", nargs="*")
    r.add_argument("--client", default="claude")
    r.add_argument("--attempts", type=int, default=3)
    r.add_argument("--bare", action="store_true", help="control group: cùng prompt, không guard/env AISEF")
    r.add_argument("--model", default="", help="model cụ thể (rỗng = mặc định của client); đi vào cả hai điều kiện")
    b = sub.add_parser("run-both", help="interleaved: AISEF rồi bare cho mỗi task, --attempts lượt (cần AISEF_BENCH=1)")
    b.add_argument("ids", nargs="*")
    b.add_argument("--client", default="claude")
    b.add_argument("--attempts", type=int, default=3)
    b.add_argument("--shuffle", type=int, default=0, metavar="SEED",
                   help="xáo thứ tự task với hạt giống cho trước (0 = giữ nguyên thứ tự). Có hạt giống thì lần chạy sau dựng lại được đúng thứ tự ấy; xáo không hạt giống là một biến không ai ghi lại")
    b.add_argument("--model", default="", help="model cụ thể (rỗng = mặc định của client); đi vào cả hai điều kiện")
    b.add_argument("--max-usd", type=float, default=0.0,
                   help="trần chi phí: dừng TRƯỚC task kế nếu đã tiêu quá; 0 = không trần. Cắt ở ranh giới task để mỗi task đo được vẫn đủ thiết kế; task bị bỏ được in ra, không im lặng")
    sub.add_parser("report", help="báo cáo Markdown từ .bench/results.jsonl")
    e = sub.add_parser("export", help="xuất một task ra thư mục định dạng Harbor")
    e.add_argument("id")
    e.add_argument("--out", default=str(R.KEEP_DIR / "harbor"))
    a = p.parse_args(argv)

    tasks = M.load_tasks(M.TASKS_DIR, M.KEEP_DIR / "tasks")
    ids = getattr(a, "ids", [])
    # Khi người dùng nêu tên task, chạy **theo thứ tự họ nêu**: lọc theo thứ tự
    # dataset làm lời khai "chạy theo thứ tự này" trong báo cáo thành sai mà
    # không ai thấy (đo 2026-09-12: lô `multi-3 multi-1` chạy multi-1 trước).
    by_id = {t.id: t for t in tasks}
    pick = [by_id[i] for i in ids if i in by_id] if ids else list(tasks)
    if a.cmd == "mine":
        got = [] if a.no_bugs else M.mine_bugs(R.ROOT)
        if a.e9:
            os.environ["AISEF_BENCH_E9"] = a.e9
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
        if a.client not in R.SIMULATED_CLIENTS and not R.ENABLED:
            print("đặt AISEF_BENCH=1 — chạy client thật tốn tiền", file=sys.stderr)
            return 1
        client = R.make_client(a.client)
        res = [x for t in pick for x in R.run(t, client, attempts=a.attempts, bare=a.bare, model=a.model)]
        print(R.report(res, tasks))
    elif a.cmd == "run-both":
        if a.client not in R.SIMULATED_CLIENTS and not R.ENABLED:
            print("đặt AISEF_BENCH=1 — chạy client thật tốn tiền", file=sys.stderr)
            return 1
        import random
        client = R.make_client(a.client)
        order = list(pick)
        if a.shuffle:
            random.Random(a.shuffle).shuffle(order)
            print(f"thứ tự (hạt giống {a.shuffle}): {', '.join(t.id for t in order)}", file=sys.stderr)
        res, bo_qua = [], []
        for i, t in enumerate(order):
            tieu = sum(x.cost_usd for x in res)
            if a.max_usd and tieu >= a.max_usd:
                bo_qua = [x.id for x in order[i:]]
                break
            res += R.run(t, client, attempts=a.attempts, bare=False, model=a.model)
            res += R.run(t, client, attempts=a.attempts, bare=True, model=a.model)
        if bo_qua:
            print(f"TRẦN CHI PHÍ {a.max_usd:.2f} USD đạt sau {len(order) - len(bo_qua)}/{len(order)} task "
                  f"(đã tiêu {sum(x.cost_usd for x in res):.2f}). KHÔNG chạy: {', '.join(bo_qua)}",
                  file=sys.stderr)
        print(R.report(res, tasks))
    elif a.cmd == "report":
        print(R.report(R.load_results(), tasks))
    elif a.cmd == "export":
        print(R.export(next(t for t in tasks if t.id == a.id), a.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
