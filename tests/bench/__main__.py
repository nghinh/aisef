"""`python3 -m tests.bench {mine,validate,run,report,export}` — bench ADR-005 V8.

Không nối vào `aisef` CLI: bench là việc của người phát triển harness, không
phải của dự án dùng harness, và một lệnh `-m` ít mã hơn một sub-parser.
"""

from __future__ import annotations

import argparse
import os
import json
import sys

from . import _mine as M
from . import _runner as R


def _giu_khoa(a):
    """Khoá độc quyền cho lệnh gọi client thật; None với lệnh chỉ đọc.

    Hai tiến trình bench cùng một `AISEF_BENCH_DIR` **xoá cây làm việc của
    nhau**: `materialize()` gọi `remove_tree(dest)` trước khi dựng, nên lượt
    thứ hai của cùng (task, điều kiện, lượt) dọn sạch bằng chứng mà báo cáo
    trước đang trích dẫn. Và nhà cung cấp sau `mycombo` không chịu được hai
    phiên song song. Khoá ở ranh giới lệnh chặn cả hai bằng một chỗ.

    Khoá **không** liên tiến trình với dogfood: một `aisef run` đang chạy vẫn
    chiếm endpoint mà bench không thấy. Đó là việc của người vận hành.

    `qualify` lấy **cùng** khoá dù sổ của nó nằm ở `.aisef-qual/`: thứ khoá bảo
    vệ là *endpoint*, không phải thư mục, và một đợt tuyển chạy song song với
    một đợt đo làm hỏng **cả hai** phép đo. Ba chế độ không gọi client thật
    (`--du-toan`, `--bao-cao`, `--tu-kiem`) thì không khoá — chúng chỉ đọc.
    """
    if a.cmd not in ("run", "run-both", "qualify"):
        return None
    if a.cmd == "qualify" and (a.du_toan or a.bao_cao or a.tu_kiem):
        return None
    from aisef._compat import flock_ex_nb, open_lock_fd

    R.KEEP_DIR.mkdir(parents=True, exist_ok=True)
    fd = open_lock_fd(R.KEEP_DIR / "bench.lock")
    try:
        flock_ex_nb(fd)
    except OSError:
        os.close(fd)
        print(f"một đợt đo khác đang chạy trong {R.KEEP_DIR} (khoá: bench.lock). Chạy song song "
              "thì hai đợt xoá cây làm việc của nhau — đợi nó xong, hoặc đặt AISEF_BENCH_DIR khác.",
              file=sys.stderr)
        return False
    return fd


def _ghi_quyet_dinh_dung(khai: dict, vi_sao: str, da_chay, bo_qua: list[str],
                         bo_qua_luat: bool) -> None:
    """Ghi quyết định dừng vào bằng chứng máy-đọc-được, cạnh chính dữ liệu.

    Dừng mà không để lại dấu thì bảng kết quả đọc ra như một thiết kế 2 task,
    còn chạy tiếp mà không để lại dấu thì 10 task sau đọc ra như thứ giao thức
    đã đòi. Cả hai đều là bảng nói dối; tệp này là cái phân biệt chúng.
    """
    R.KEEP_DIR.mkdir(parents=True, exist_ok=True)
    (R.KEEP_DIR / "stop-decision.json").write_text(json.dumps({
        "fired": True,
        "honoured": not bo_qua_luat,
        "reason": vi_sao,
        "rule": khai.get("rule") or {},
        "rule_source": khai.get("source") or "",
        "rule_source_digest": khai.get("source_digest") or "",
        "tasks_completed": [x.id for x in da_chay],
        "tasks_not_run": bo_qua if not bo_qua_luat else [],
        "post_stop_tasks": bo_qua if bo_qua_luat else [],
        "post_stop_label": ("POST-STOP EXPLORATORY — COLLECTED AFTER THE "
                            "PRE-REGISTERED STOP CONDITION") if bo_qua_luat else "",
    }, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


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
    r.add_argument("--note", default=os.environ.get("AISEF_BENCH_NOTE", ""),
                   help="nhãn cohort do người vận hành khai, ghi vào từng dòng — bắt buộc khi model là alias "
                        "(đổi mô hình nền không đổi một ký tự nào trong dữ liệu)")
    b = sub.add_parser("run-both", help="interleaved: AISEF rồi bare cho mỗi task, --attempts lượt (cần AISEF_BENCH=1)")
    b.add_argument("ids", nargs="*")
    b.add_argument("--client", default="claude")
    b.add_argument("--attempts", type=int, default=3)
    b.add_argument("--shuffle", type=int, default=0, metavar="SEED",
                   help="xáo thứ tự task với hạt giống cho trước (0 = giữ nguyên thứ tự). Có hạt giống thì lần chạy sau dựng lại được đúng thứ tự ấy; xáo không hạt giống là một biến không ai ghi lại")
    b.add_argument("--model", default="", help="model cụ thể (rỗng = mặc định của client); đi vào cả hai điều kiện")
    b.add_argument("--note", default=os.environ.get("AISEF_BENCH_NOTE", ""),
                   help="nhãn cohort do người vận hành khai, ghi vào từng dòng — bắt buộc khi model là alias "
                        "(đổi mô hình nền không đổi một ký tự nào trong dữ liệu)")
    b.add_argument("--ignore-stop-rule", action="store_true",
                   help="chạy tiếp sau khi điều kiện dừng đã đóng băng kích hoạt. "
                        "Phải nêu tường minh và được GHI LẠI vào stop-decision.json: "
                        "dữ liệu thu sau điểm ấy là hậu-dừng, không phải thứ giao thức đòi")
    b.add_argument("--max-usd", type=float, default=0.0,
                   help="trần chi phí: dừng TRƯỚC task kế nếu đã tiêu quá; 0 = không trần. Cắt ở ranh giới task để mỗi task đo được vẫn đủ thiết kế; task bị bỏ được in ra, không im lặng")
    b.add_argument("--max-minutes", type=float, default=0.0,
                   help="trần thời gian phiên (phút), cắt ở ranh giới task như --max-usd; 0 = không trần. "
                        "Cần vì --max-usd TRƠ với nhà cung cấp báo cost=0: không có trần nào thì một model "
                        "hay chạm trần lượt chạy tới hết đồng hồ 1800 s mỗi lượt")
    rp = sub.add_parser("report", help="báo cáo Markdown từ .bench/results.jsonl")
    rp.add_argument("--cohort", default="",
                    help="chỉ lấy dòng có `model` hoặc `note` chứa chuỗi này — "
                         "sổ là tệp nối thêm, mọi đợt đo nằm chung một chỗ")
    an = sub.add_parser("analyze", help="đo lại sau đợt chạy: xong giả, ghi ngoài phạm vi, lượt trượt sửa ở đâu (đọc cây đã giữ, không đụng scorer)")
    an.add_argument("--client", default="opencode", help="tiền tố mã client cần đọc")
    q = sub.add_parser("qualify", help="tuyển cặp model↔CLI trước cột 2 (G5.3): đo tỉ lệ phiên bị CLI "
                                       "cắt, không chấm điểm. Ngưỡng đã ghim ở "
                                       "docs/BENCH-PAIR-QUALIFICATION-PROTOCOL.md")
    q.add_argument("--client", default="opencode")
    q.add_argument("--model", default="", help="model cụ thể (rỗng = mặc định của client)")
    q.add_argument("--note", default=os.environ.get("AISEF_BENCH_NOTE", ""),
                   help="nhãn cặp do người vận hành khai — bắt buộc khi model là alias (`mycombo`)")
    q.add_argument("--phien", type=int, default=0, help="số phiên (0 = cỡ mẫu đã ghim)")
    q.add_argument("--max-minutes", type=float, default=0.0, help="trần thời gian đợt (0 = đã ghim)")
    q.add_argument("--du-toan", action="store_true",
                   help="in hoá đơn sẽ tiêu rồi thoát — KHÔNG gọi client")
    q.add_argument("--bao-cao", action="store_true", help="chỉ dựng lại báo cáo từ sổ đã ghi")
    q.add_argument("--tu-kiem", action="store_true",
                   help="chứng minh đường ống bằng `opencode` GIẢ — 0 phiên thật")
    q.add_argument("--out", default="docs/BENCH-PAIR-QUALIFICATION.md")
    sc = sub.add_parser("selfcheck", help="chạy đường ống thật với `opencode` GIẢ — chứng minh plumbing "
                                          "trước khi phóng đợt đo thật, không tốn một lượt gọi model nào")
    sc.add_argument("--task", default=None, help="task để tự kiểm (mặc định: task rẻ nhất)")
    sc.add_argument("--model", default="", help="giá trị `--model` cần kiểm là tới **cả hai** nhánh")
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
    # Tên không có trong bộ dữ liệu là **lỗi**, không phải chuyện bỏ qua được:
    # một đợt đo tuyển task theo danh sách tên (xem
    # `docs/BENCH-TASK-DISCRIMINATION.md`) mà đánh sai một tên thì cohort ngắn đi
    # trong im lặng, và câu "đợt này chạy tuyển chọn X" trong báo cáo thành sai
    # mà không ai kiểm được. Danh sách hợp lệ thì hành vi **không đổi một chút**.
    thieu = [i for i in ids if i not in by_id]
    if thieu:
        print(f"không có task nào tên: {', '.join(thieu)} — bộ dữ liệu có "
              f"{len(tasks)} task, xem `tests/bench/tasks/`.", file=sys.stderr)
        return 2
    pick = [by_id[i] for i in ids] if ids else list(tasks)
    khoa = _giu_khoa(a)
    if khoa is False:
        return 3
    try:
        return _dispatch(a, tasks, pick)
    finally:
        if khoa is not None:
            os.close(khoa)


def _dispatch(a, tasks: list, pick: list) -> int:
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
        ranh_gioi_truoc = R.chup_ranh_gioi()
        res = []
        for t in pick:
            res += R.run(t, client, attempts=a.attempts, bare=a.bare, model=a.model, note=a.note)
            try:
                R.bat_buoc_ranh_gioi(ranh_gioi_truoc)
            except R.RanhGioiViPham as e:
                print(f"\nHUỶ ĐỢT ĐO: {e}", file=sys.stderr)
                print(R.report(res, tasks))
                return 4
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
        # Ranh giới workspace (lỗi 166): chụp trước, kiểm sau **từng task**, và
        # vi phạm thì **huỷ** — không phải cảnh báo. Cột 2 là 72 lượt nhiều giờ;
        # một rò rỉ phát hiện ở cuối nghĩa là cả đợt chạy trên một kho đã bẩn.
        ranh_gioi_truoc = R.chup_ranh_gioi()
        khai_dung = R.luat_dung()
        da_ghi_bo_qua = False
        res, bo_qua, vi_sao = [], [], ""
        for i, t in enumerate(order):
            phut = sum(x.duration_ms for x in res) / 60_000
            if a.max_usd and sum(x.cost_usd for x in res) >= a.max_usd:
                bo_qua, vi_sao = [x.id for x in order[i:]], f"TRẦN CHI PHÍ {a.max_usd:.2f} USD"
                break
            # Trần thời gian: `--max-usd` trơ với nhà cung cấp báo cost=0 (C-1,
            # C-1b: 0,00 ở mọi dòng), nên không có nó thì đợt đo không có điều
            # kiện dừng nào ngoài người vận hành ngồi canh.
            if a.max_minutes and phut >= a.max_minutes:
                bo_qua, vi_sao = [x.id for x in order[i:]], f"TRẦN THỜI GIAN {a.max_minutes:.0f} phút"
                break
            res += R.run(t, client, attempts=a.attempts, bare=False, model=a.model, note=a.note)
            res += R.run(t, client, attempts=a.attempts, bare=True, model=a.model, note=a.note)
            try:
                R.bat_buoc_ranh_gioi(ranh_gioi_truoc)
            except R.RanhGioiViPham as e:
                print(f"\nHUỶ ĐỢT ĐO sau {i + 1}/{len(order)} task: {e}", file=sys.stderr)
                print(R.report(res, tasks))
                return 4
            # Điều kiện dừng đã đóng băng, áp bằng mã chứ không bằng trí nhớ:
            # trên C-2 nó kích hoạt sau task 2 và mười task nữa vẫn chạy.
            vi_sao_dung = R.kiem_dung_som(res, [x.id for x in order], khai_dung)
            if vi_sao_dung and not a.ignore_stop_rule:
                bo_qua = [x.id for x in order[i + 1:]]
                _ghi_quyet_dinh_dung(khai_dung, vi_sao_dung, order[:i + 1], bo_qua, False)
                print(f"\nDỪNG THEO GIAO THỨC sau {i + 1}/{len(order)} task: "
                      f"{vi_sao_dung}.\nKHÔNG chạy: {', '.join(bo_qua) or '(không còn)'}",
                      file=sys.stderr)
                break
            if vi_sao_dung and a.ignore_stop_rule and not da_ghi_bo_qua:
                da_ghi_bo_qua = True
                _ghi_quyet_dinh_dung(khai_dung, vi_sao_dung, order[:i + 1],
                                     [x.id for x in order[i + 1:]], True)
                print(f"\nĐIỀU KIỆN DỪNG ĐÃ KÍCH HOẠT sau {i + 1} task nhưng bị "
                      f"BỎ QUA có chủ ý (--ignore-stop-rule): {vi_sao_dung}. "
                      f"Mọi task sau đây là dữ liệu HẬU-DỪNG.", file=sys.stderr)
        if bo_qua:
            print(f"{vi_sao} đạt sau {len(order) - len(bo_qua)}/{len(order)} task "
                  f"(đã tiêu {sum(x.cost_usd for x in res):.2f} USD, "
                  f"{sum(x.duration_ms for x in res) / 60_000:.0f} phút phiên). "
                  f"KHÔNG chạy: {', '.join(bo_qua)}", file=sys.stderr)
        print(R.report(res, tasks))
    elif a.cmd == "analyze":
        from . import _analyze as A
        print(A.report(A.collect(a.client), A.cut_sessions()))
    elif a.cmd == "report":
        rows = R.load_results()
        if a.cohort:
            rows = [r for r in rows if a.cohort in (r.model or "") or a.cohort in (r.note or "")]
            if not rows:
                print(f"không có dòng nào khớp cohort {a.cohort!r}", file=sys.stderr)
                return 2
        print(R.report(rows, tasks))
    elif a.cmd == "qualify":
        from . import _qualify as Q
        if a.tu_kiem:
            return Q.tu_kiem()
        if a.bao_cao:
            return Q.viet_bao_cao(Q.doc_so(), a.out)
        phien = a.phien or Q.SO_PHIEN_TUYEN
        if a.du_toan:
            print(Q.du_toan(a.client, a.model, Q.TASK_TUYEN, phien,
                            tran_phut=a.max_minutes or Q.TRAN_PHUT))
            return 0
        if a.client not in R.SIMULATED_CLIENTS and not R.ENABLED:
            print("đặt AISEF_BENCH=1 — chạy client thật tốn tiền", file=sys.stderr)
            return 1
        if not a.note:
            print("thiếu --note: `mycombo` là một alias, nên hai đợt trên hai mô hình nền "
                  "trông y hệt nhau trong sổ. Khai nhãn cặp.", file=sys.stderr)
            return 2
        # Ràng buộc 2 của chủ dự án: bốn điều kiện phải đúng **trước** một phiên
        # tuyển thật nào. Cửa nằm ở đây chứ không ở một bản ghi, vì một bản ghi thì
        # kiểm xong vẫn phóng được.
        ok, hong, rec = Q.tien_kiem()
        (R.ROOT / "closure-evidence").mkdir(exist_ok=True)
        (R.ROOT / "closure-evidence/g5-preflight.json").write_text(
            json.dumps({**rec, "ok": ok, "blockers": hong}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
        if not ok:
            print("tiền kiểm G5 không đạt — không phóng đợt tuyển:", file=sys.stderr)
            for h in hong:
                print(f"  ✗ {h}", file=sys.stderr)
            return 3
        Q.chay(R.make_client(a.client), phien=phien, model=a.model, note=a.note,
               tran_phut=a.max_minutes or Q.TRAN_PHUT)
        return Q.viet_bao_cao(Q.doc_so(), a.out)
    elif a.cmd == "selfcheck":
        from . import _selfcheck as S
        return S.run_selfcheck(a.task or S.TASK_MAC_DINH, model=a.model)
    elif a.cmd == "export":
        print(R.export(next(t for t in tasks if t.id == a.id), a.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
