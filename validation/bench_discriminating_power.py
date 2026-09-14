#!/usr/bin/env python3
"""Sức phân biệt của từng task bench — tính lại từ lượt đã ghi, **không gọi model**.

Việc còn mở ở [BENCH-REPORT-C1B](../docs/BENCH-REPORT-C1B.md) §6 dòng 4: *tuyển
task theo tiêu chí "đã từng có nhánh thắng nhánh kia"*. Một task mà hai nhánh
luôn đồng ý tốn đủ giá và mua 0 tín hiệu — C-1 tiêu 5,8 giờ phiên cho 12 task
mà chỉ 3 task có nhánh thắng nhánh kia. Script này dựng lại con số ấy cho **cả
30 task** của bộ dữ liệu, từ `results.jsonl` và kho bằng chứng đã lưu.

Không đụng vào `tests/bench/tasks/`, `MANIFEST.sha256`, scorer, `pass@1`,
`TRAN_LUOT`, `--attempts`, `run.timeout_seconds` hay thứ tự task: đây là phép
đọc, và hai cohort đã đóng phải dựng lại được nguyên byte.

Ba định nghĩa, lấy đúng từ giao thức và hai báo cáo — không phát minh thêm:

1. **Một lượt** = một dòng `results.jsonl`, chấm bằng F2P/P2P trên test ẩn
   (`_runner._grade`). Cả C-1 và C-1b chạy theo đúng định nghĩa này: cơ chế
   chạy lại hạ tầng của C-1b *không nổ lần nào* (lỗi 86,
   [B-4](../docs/BENCH-OBSERVATIONS-C1B.md)). Sổ là tệp nối thêm nên một
   `(cohort, điều kiện, task, lượt)` có thể có nhiều dòng; lấy dòng **cuối**,
   đúng như giao thức khai và đúng với cây làm việc còn trên đĩa.
2. **Có thông tin** = hai nhánh ra kết cục **khác nhau**. Đơn vị là **cặp chéo
   nhánh**: mỗi lượt dùng được của nhánh AISEF ghép với mỗi lượt dùng được của
   nhánh trần, nên không cần ghép theo số thứ tự lượt (ghép theo thứ tự là một
   phép ghép tuỳ ý — các lượt là mẫu độc lập, không phải cặp thiết kế). Sức
   phân biệt `D` = tỉ lệ cặp không đồng ý. Với n bằng nhau và một nhánh thuần
   nhất, `D` trùng `|Δ pass@1|` đã in trong hai báo cáo — kiểm ở `tu_kiem()`.
3. **Không dùng được** = kết cục không đọc được thành phán quyết của agent:
   INVALID/UNRUNNABLE (scorer không chấm nổi), hoặc một FAIL mà phiên chết vì
   hạ tầng (`exit_status` trong `INFRA_STATUSES`, hoặc phiên bị CLI cắt). Một
   PASS thì **vẫn dùng được** dù phiên chết thế nào — bản sửa đã nằm trên đĩa
   và test ẩn xanh, đúng cách C-1b §4 đọc 6/9 lượt PASS sau phiên bị cắt.
   **Trần lượt (`max_turns`) không tính là hạ tầng** — `exit_status_of` xếp nó
   trước hạ tầng có chủ ý ("classifying it as infra would let turn-hungry
   stories retry for free"), nên nó vào cột riêng chứ không vào cột này.

Cohort mô phỏng bị loại khỏi phán quyết, **bằng mã chứ không bằng lời**:
`tests/bench/simulated.py` chọn chiến lược bằng `(attempt - 1) % 4`, một hàm
thuần của số thứ tự lượt, giống hệt ở hai điều kiện — sức phân biệt của nó
bằng 0 do cách dựng. Số lượt của nó vẫn được đếm để bảng tài nguyên khép kín.

Giá tiền: nhà cung cấp sau alias `9router/mycombo` báo `cost_usd = 0` ở **mọi**
bước của C-1 và C-1b — **vắng mặt giá**, không phải vắng mặt tài nguyên. Cột
tài nguyên vì thế là lượt, turn, giây phiên và **token** (đọc từ
`agent_run.tokens` trong kho bằng chứng, nơi duy nhất còn giữ chúng: dòng
`results.jsonl` của hai cohort ấy chưa có trường token).

Cách chạy (đọc, không ghi gì vào cohort):

    python3 validation/bench_discriminating_power.py                # .bench + .bench-c1b
    python3 validation/bench_discriminating_power.py ~/du-an/.bench-c2
    python3 validation/bench_discriminating_power.py --tu-kiem      # tự kiểm, không cần dữ liệu

Thư mục cohort vắng mặt được nêu tên rồi bỏ qua: `.bench*/` là gitignore, nên
trong cây làm việc sạch hoặc trên CI script in ra một bảng rỗng có ghi lý do
chứ không in số bịa.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.clients.stream import INFRA_STATUSES  # noqa: E402

#: Cohort mặc định trên máy phát triển. Tên thư mục là *sổ* của cohort
#: (`AISEF_BENCH_DIR`), không phải tên cohort — nhãn nằm ở `NHAN_COHORT`.
COHORT_MAC_DINH = (ROOT / ".bench", ROOT / ".bench-c1b")

#: (tên sổ, mã client nhánh AISEF) → nhãn cohort trong báo cáo. Thiếu khoá thì
#: dùng chính cặp ấy làm nhãn — thêm cohort mới không cần sửa script.
NHAN_COHORT = {
    (".bench", "claude"): "frontier v0.3.0/v1.3",
    (".bench", "opencode"): "C-1",
    (".bench", "simulated-weak"): "mô phỏng v1.3",
    (".bench-c1b", "opencode"): "C-1b",
}

#: Client mô phỏng: kết cục là hàm thuần của số thứ tự lượt
#: (`simulated.py`: `["gold","noop","partial","revert"][(attempt_n - 1) % 4]`),
#: nên hai điều kiện **luôn** ra cùng kết cục. Đếm lượt, không tính sức phân biệt.
TIEN_TO_MO_PHONG = "simulated"

#: Chữ ký phiên bị CLI cắt: adapter ghi câu này vào `error` từ bản vá 13/09.
#: C-1 chạy **trước** bản vá nên `error` của nó rỗng — trạng thái bị cắt của
#: từng lượt C-1 vì thế **không nằm trong corpus** và được báo là `unknown`,
#: không suy diễn. (Kho phiên của OpenCode có, nhưng nó nằm ngoài corpus, thay
#: đổi theo thời gian, và `_analyze.cut_sessions` khoá theo
#: `(điều kiện, task, lượt)` **không mang tên sổ** nên trộn C-1 với C-1b ở đúng
#: ba task dùng chung.)
CHU_KY_PHIEN_CAT = "could not parse the model's tool call"

#: Câu báo hết đồng hồ của adapter. `exit_status_of` chỉ nhận bản tiếng Anh
#: hiện tại (`clients/opencode.py`, `clients/claude_code.py`), nhưng dòng của
#: cohort frontier mang bản **tiếng Việt cũ** và cây làm việc của nó đã bị xoá,
#: nên không có bản dự phòng theo `error` thì một lượt bị đồng hồ cắt đọc thành
#: phán quyết của agent.
CHU_KY_HET_DONG_HO = ("exceeded ", "quá ")

PASS, FAIL = "PASS", "FAIL"
KHONG_CHAM_DUOC = ("INVALID", "UNRUNNABLE")

#: Nhóm task, theo tiêu chí của việc còn mở ("đã từng có nhánh thắng nhánh kia").
PHAN_BIET, TRAN, SAN, HOA_CO_BIEN_DONG, CHUA_DO = (
    "phân biệt được", "chạm trần", "sàn", "hoà (còn biến động)", "chưa đo")


# ---------------------------------------------------------------- đọc


def doc_task(tasks_dir: Path) -> dict[str, str]:
    """id task → `invalid_reason` (rỗng = hợp lệ). Chỉ đọc, không sửa một byte."""
    ra = {}
    for d in sorted(p for p in tasks_dir.iterdir() if p.is_dir()):
        j = json.loads((d / "task.json").read_text(encoding="utf-8"))
        ra[d.name] = (j.get("invalid_reason") or "").strip()
    return ra


def doc_ket_qua(so: Path) -> list[dict]:
    p = so / "results.jsonl"
    if not p.is_file():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def doc_bang_chung(so: Path) -> dict[tuple[str, str, int], dict]:
    """(điều kiện, task, lượt) → `agent_run` của lượt ấy trong kho bằng chứng.

    Nơi duy nhất còn giữ token và `exit_status` của C-1/C-1b: dòng
    `results.jsonl` của hai cohort ấy được ghi trước khi hai trường đó tồn tại.
    Cây làm việc bị `materialize()` xoá trước mỗi lần dựng, nên với một lượt
    chạy nhiều lần chỉ lần **cuối** còn trên đĩa — cùng quy ước "dòng cuối" của
    `gom()`, nên hai nguồn khớp nhau.
    """
    ra: dict[tuple[str, str, int], dict] = {}
    goc = so / "run"
    if not goc.is_dir():
        return ra
    for ev in sorted(goc.glob("*/*/a*/_bmad-output/evidence/*.jsonl")):
        dieu_kien, task, luot = ev.parts[-6], ev.parts[-5], ev.parts[-4]
        if ev.stem != task:                      # tệp jsonl khác trong cây dự án
            continue
        for line in ev.read_text(encoding="utf-8", errors="replace").splitlines():
            if '"agent_run"' not in line:
                continue
            r = json.loads(line)
            if r.get("kind") != "agent_run":
                continue
            d = r.get("detail") or {}
            tok = r.get("tokens") or {}
            ra[(dieu_kien, task, int(luot[1:]))] = {
                "turns": d.get("turns") or 0,
                "exit_status": d.get("exit_status") or "",
                "error": d.get("error") or "",
                "tokens": sum(v for v in tok.values() if isinstance(v, int)),
                "duration_ms": r.get("duration_ms") or 0,
            }
    return ra


def gom(rows: list[dict]) -> dict[tuple[str, str, int], dict]:
    """(điều kiện, task, lượt) → dòng **cuối cùng**, đúng quy ước của giao thức."""
    ra: dict[tuple[str, str, int], dict] = {}
    for r in rows:
        ra[(r["client"], r["task_id"], int(r["attempt"]))] = r
    return ra


# ---------------------------------------------------------------- phân loại


def phan_loai_luot(row: dict, ev: dict | None) -> str:
    """`ok` | `khong_cham_duoc` | `ha_tang` | `phien_cat` | `tran_luot`.

    Đọc `exit_status` từ bằng chứng khi có (dòng kết quả của C-1/C-1b chưa mang
    trường ấy), rồi tới `error` của chính dòng kết quả.
    """
    if row["outcome"] in KHONG_CHAM_DUOC:
        return "khong_cham_duoc"
    trang_thai = (ev or {}).get("exit_status") or row.get("exit_status") or ""
    loi = ((ev or {}).get("error") or row.get("error") or "")
    if trang_thai == "max_turns" or loi.strip() == "max_turns":
        return "tran_luot"
    if trang_thai in INFRA_STATUSES or loi.startswith(CHU_KY_HET_DONG_HO):
        return "ha_tang"
    if CHU_KY_PHIEN_CAT in loi:
        return "phien_cat"
    return "ok"


def dung_duoc(row: dict, loai: str) -> bool:
    """Một PASS luôn dùng được; một FAIL vì hạ tầng thì không.

    Lý lẽ nằm ở C-1b §4: 6/9 lượt kết thúc bằng phiên bị cắt **vẫn PASS**, vì
    agent đã ghi xong bản sửa trước khi phiên chết — bỏ chúng là bỏ dữ liệu
    tốt. Ngược lại, tính một FAIL vì hạ tầng thành "agent sửa sai" là điều
    giao thức C-1b gọi là *sai về bản chất*.
    """
    if loai == "khong_cham_duoc":
        return False
    return row["outcome"] == PASS or loai not in ("ha_tang", "phien_cat")


def suc_phan_biet(a: list[str], b: list[str]) -> dict:
    """Cặp chéo nhánh: bao nhiêu cặp không đồng ý, bao nhiêu cùng PASS/cùng FAIL."""
    ap, af = a.count(PASS), len(a) - a.count(PASS)
    bp, bf = b.count(PASS), len(b) - b.count(PASS)
    cap = len(a) * len(b)
    return {
        "cap": cap,
        "co_thong_tin": ap * bf + af * bp,
        "cung_pass": ap * bp,
        "cung_fail": af * bf,
        "D": (ap * bf + af * bp) / cap if cap else None,
    }


def nhom_task(theo_cohort: list[dict]) -> str:
    """Nhóm của một task, gộp mọi cohort **không mô phỏng** có lượt dùng được."""
    co = [c for c in theo_cohort if not c["mo_phong"] and c["n_a"] and c["n_b"]]
    if not co:
        return CHUA_DO
    if any(c["delta"] for c in co):
        return PHAN_BIET                    # "đã từng có nhánh thắng nhánh kia"
    if all(c["p1_a"] == 1.0 and c["p1_b"] == 1.0 for c in co):
        return TRAN
    if all(c["p1_a"] == 0.0 and c["p1_b"] == 0.0 for c in co):
        return SAN
    return HOA_CO_BIEN_DONG


# ---------------------------------------------------------------- tính


def thu_thap(so_list: list[Path], tasks_dir: Path,
             loai_bo_ha_tang: bool = True) -> tuple[dict, list[str]]:
    """task → [số liệu theo cohort]. Trả kèm ghi chú về thứ vắng mặt.

    `loai_bo_ha_tang=False` cho **cách đọc như đã chấm**: giữ mọi lượt chấm
    được, kể cả FAIL vì hạ tầng. Đó là cách hai báo cáo đã đóng tính `pass@1`,
    nên bảng ấy phải dựng lại đúng cột Δ đã in — nếu không thì bộ đọc này sai.
    `True` cho định nghĩa lượt mà giao thức C-1b **khai trước khi chạy** (phiên
    hỏng hạ tầng được chạy lại, không tính là lượt trượt của agent); cơ chế ấy
    không nổ lần nào vì lỗi 86, nên hiệu số giữa hai cách đọc chính là cái giá
    của lỗi ấy.
    """
    ghi_chu: list[str] = []
    tasks = doc_task(tasks_dir)
    ra: dict[str, list[dict]] = {t: [] for t in tasks}
    for so in so_list:
        rows = doc_ket_qua(so)
        if not rows:
            ghi_chu.append(f"`{so}` không có `results.jsonl` — bỏ qua, không thay bằng số nào.")
            continue
        bang_chung = doc_bang_chung(so)
        if not bang_chung:
            ghi_chu.append(f"`{so}/run/` không còn cây làm việc — cột token của sổ này rỗng.")
        luot = gom(rows)
        clients = sorted({c for c, _, _ in luot})
        cap_dieu_kien = [(c[: -len("-bare")], c) for c in clients if c.endswith("-bare")]
        for a_cl, b_cl in cap_dieu_kien:
            if a_cl not in clients:
                ghi_chu.append(f"`{so}`: có `{b_cl}` nhưng không có `{a_cl}` — bỏ cặp này.")
                continue
            nhan = NHAN_COHORT.get((so.name, a_cl), f"{so.name}/{a_cl}")
            mo_phong = a_cl.startswith(TIEN_TO_MO_PHONG)
            for t in sorted({t for _, t, _ in luot}):
                so_lieu = _mot_task(luot, bang_chung, rows, t, a_cl, b_cl, loai_bo_ha_tang)
                if so_lieu is None:
                    continue
                so_lieu |= {"cohort": nhan, "mo_phong": mo_phong, "so": so.name}
                ra.setdefault(t, []).append(so_lieu)
    return ra, ghi_chu


def _mot_task(luot: dict, bang_chung: dict, rows: list[dict],
              t: str, a_cl: str, b_cl: str, loai_bo_ha_tang: bool) -> dict | None:
    nhanh = {}
    for cl in (a_cl, b_cl):
        ds = [(k[2], v) for k, v in luot.items() if k[0] == cl and k[1] == t]
        if not ds:
            return None
        ket, loai, res = [], [], []
        for n, row in sorted(ds):
            lo = phan_loai_luot(row, bang_chung.get((cl, t, n)))
            loai.append(lo)
            res.append((row, bang_chung.get((cl, t, n))))
            if lo != "khong_cham_duoc" and (dung_duoc(row, lo) or not loai_bo_ha_tang):
                ket.append(row["outcome"])
        nhanh[cl] = {"ket": ket, "loai": loai, "res": res,
                     "ghi": sum(1 for r in rows if r["client"] == cl and r["task_id"] == t)}
    a, b = nhanh[a_cl], nhanh[b_cl]
    sp = suc_phan_biet(a["ket"], b["ket"])
    p1_a = a["ket"].count(PASS) / len(a["ket"]) if a["ket"] else None
    p1_b = b["ket"].count(PASS) / len(b["ket"]) if b["ket"] else None
    return {
        "task": t, "n_a": len(a["ket"]), "n_b": len(b["ket"]),
        "ghi_a": a["ghi"], "ghi_b": b["ghi"],
        "luot_a": len(a["loai"]), "luot_b": len(b["loai"]),
        "p1_a": p1_a, "p1_b": p1_b,
        "delta": None if p1_a is None or p1_b is None else round(p1_a - p1_b, 4),
        "khong_dung_duoc": sum(1 for k in (a, b) for r, lo in zip(k["res"], k["loai"], strict=True)
                               if not dung_duoc(r[0], lo)),
        "loai": [lo for k in (a, b) for lo in k["loai"]],
        "turns": sum(r["turns"] for k in (a, b) for r, _ in k["res"]),
        "giay": sum(r["duration_ms"] for k in (a, b) for r, _ in k["res"]) / 1000,
        "tokens": sum((e or {}).get("tokens", 0) for k in (a, b) for _, e in k["res"]),
        "co_token": all(e for k in (a, b) for _, e in k["res"]),
        "usd": sum(r["cost_usd"] for k in (a, b) for r, _ in k["res"]),
        **sp,
    }


# ---------------------------------------------------------------- báo cáo


def _pc(x) -> str:
    return "–" if x is None else f"{x:.2f}".replace(".", ",")


def _so(n) -> str:
    return f"{int(n):,}".replace(",", " ")


def _delta(c: dict) -> str:
    return "–" if c["delta"] is None else format(c["delta"], "+.2f").replace(".", ",")


def _d_theo_cohort(cs: list[dict]) -> str:
    """`D` từng cohort, **không gộp**: `sec-2` đổi byte đề bài ở v1.4, nên một
    con số gộp C-1 với C-1b trên task ấy là trộn hai bộ dữ liệu."""
    return " · ".join(f"{_pc(c['D'])} ({c['cohort']})" for c in cs)


def bang_30_task(du_lieu: dict, tasks: dict[str, str]) -> list[str]:
    """Một dòng cho mỗi task của bộ dữ liệu, kể cả task chưa từng chạy.

    Cohort mô phỏng **không** vào cột nào ở đây (lý do ở đầu tệp); số lượt của
    nó nằm ở bảng kiểu kết thúc để phần kế toán vẫn khép.
    """
    lines = ["| task | cohort thật đã chạy | lượt ghi | lượt dùng được | cặp | có thông tin | "
             "cùng PASS | cùng FAIL | D theo cohort | không dùng được | nhóm |",
             "|---|---|---:|---:|---:|---:|---:|---:|---|---:|---|"]
    for t in sorted(tasks):
        cs = [c for c in (du_lieu.get(t) or []) if not c["mo_phong"]]
        if not cs:
            lines.append(f"| `{t}` | – | 0 | 0 | 0 | 0 | 0 | 0 | – | 0 | **{CHUA_DO}** |")
            continue
        cap = sum(c["cap"] for c in cs)
        lines.append(
            f"| `{t}` | {', '.join(c['cohort'] for c in cs)} | "
            f"{sum(c['ghi_a'] + c['ghi_b'] for c in cs)} | {sum(c['n_a'] + c['n_b'] for c in cs)} | "
            f"{cap} | {sum(c['co_thong_tin'] for c in cs)} | {sum(c['cung_pass'] for c in cs)} | "
            f"{sum(c['cung_fail'] for c in cs)} | "
            f"{_d_theo_cohort(cs)} | "
            f"{sum(c['khong_dung_duoc'] for c in cs)} | {nhom_task(cs)} |")
    return lines


def bang_theo_cohort(sach: dict, tho: dict) -> list[str]:
    """Hai cách đọc cạnh nhau: như đã chấm, và theo định nghĩa lượt đã khai.

    Cột "như đã chấm" phải trùng đúng cột Δ của [C-1](../docs/BENCH-REPORT-C1.md)
    §3 và [C-1b](../docs/BENCH-REPORT-C1B.md) §1 — đó là phép kiểm bộ đọc này.
    """
    khoa = {(c["cohort"], c["task"]): c for cs in tho.values() for c in cs}
    lines = ["**(a)** như đã chấm — cột Δ ở đây phải trùng đúng bảng đã in của hai báo cáo. "
             "**(b)** bỏ lượt hỏng hạ tầng — định nghĩa lượt mà giao thức C-1b khai *trước* khi chạy.",
             "",
             "| cohort | task | (a) A/B | (a) p@1 A | (a) p@1 B | (a) Δ | (a) D | (b) A/B | "
             "(b) p@1 A | (b) p@1 B | (b) Δ | (b) D | turn | giây phiên | token |",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for nhan in _thu_tu_cohort(sach):
        for t, c in sorted((c["task"], c) for cs in sach.values() for c in cs
                           if c["cohort"] == nhan):
            r = khoa.get((nhan, t), c)
            lines.append(
                f"| {nhan} | `{t}` | {r['n_a']}/{r['n_b']} | {_pc(r['p1_a'])} | {_pc(r['p1_b'])} | "
                f"{_delta(r)} | {_pc(r['D'])} | {c['n_a']}/{c['n_b']} | {_pc(c['p1_a'])} | "
                f"{_pc(c['p1_b'])} | {_delta(c)} | {_pc(c['D'])} | {c['turns']} | "
                f"{c['giay']:.0f} | {_so(c['tokens']) if c['co_token'] else '–'} |")
    return lines


def bang_tong_cohort(sach: dict, tho: dict, tasks: dict[str, str]) -> list[str]:
    """Một dòng mỗi cohort — chỗ duy nhất trả lời "bao nhiêu giờ mua bao nhiêu tín hiệu".

    Cột `lượt trên task phân biệt` có **hai** con số vì việc còn mở ở C-1B §6
    trộn hai đơn vị: "C-1 cho 9 lượt có thông tin" là 3 task × 3 lượt của *một*
    nhánh, còn "C-1b cho 36 lượt" là 3 × 6 × *hai* nhánh. In cả hai để hai
    cohort so được với nhau.
    """
    lines = ["| cohort | task | lượt ghi | lượt dùng được | cặp (b) | cặp có thông tin (a) | "
             "cặp có thông tin (b) | lượt trên task phân biệt (1 nhánh / 2 nhánh) | giờ phiên | "
             "turn | token | USD nhà cung cấp báo |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    giu = chon(sach, tasks)
    for nhan in _thu_tu_cohort(sach):
        cs = [c for cs_ in sach.values() for c in cs_ if c["cohort"] == nhan]
        ts = [c for cs_ in tho.values() for c in cs_ if c["cohort"] == nhan]
        tren_giu = [c for c in cs if c["task"] in giu]
        hai = sum(c["luot_a"] + c["luot_b"] for c in tren_giu)
        tok = sum(c["tokens"] for c in cs)
        lines.append(
            f"| {nhan} | {len(cs)} | {sum(c['ghi_a'] + c['ghi_b'] for c in cs)} | "
            f"{sum(c['n_a'] + c['n_b'] for c in cs)} | {sum(c['cap'] for c in cs)} | "
            f"{sum(c['co_thong_tin'] for c in ts)} | {sum(c['co_thong_tin'] for c in cs)} | "
            f"{sum(c['luot_a'] for c in tren_giu)} / {hai} | "
            f"{sum(c['giay'] for c in cs) / 3600:.2f} | {sum(c['turns'] for c in cs)} | "
            f"{_so(tok) if all(c['co_token'] for c in cs) else '– (cây đã xoá)'} | "
            f"{sum(c['usd'] for c in cs):.2f} |")
    return lines


def _thu_tu_cohort(du_lieu: dict) -> list[str]:
    thay = [c["cohort"] for cs in du_lieu.values() for c in cs]
    uu_tien = list(NHAN_COHORT.values())
    return sorted(set(thay), key=lambda n: (uu_tien.index(n) if n in uu_tien else 99, n))


def bang_ket_thuc(du_lieu: dict) -> list[str]:
    """Kiểu kết thúc của từng lượt, theo cohort — cột `max_turns` tách riêng."""
    kieu = ("ok", "tran_luot", "ha_tang", "phien_cat", "khong_cham_duoc")
    lines = ["| cohort | lượt | " + " | ".join(f"`{k}`" for k in kieu) + " |",
             "|---|---:|" + "---:|" * len(kieu)]
    for nhan in _thu_tu_cohort(du_lieu):
        loai = [lo for cs in du_lieu.values() for c in cs if c["cohort"] == nhan for lo in c["loai"]]
        lines.append(f"| {nhan} | {len(loai)} | "
                     + " | ".join(str(loai.count(k)) for k in kieu) + " |")
    return lines


def tiet_kiem(du_lieu: dict, giu: set[str]) -> list[str]:
    """Giá của phần bị cắt, tính bằng đơn vị corpus **thật sự có**.

    Không có cột tiền cho C-1/C-1b (nhà cung cấp báo 0,00 ở mọi bước), nên đơn
    vị là lượt, turn, giây phiên và token. Con số này là *phép chiếu*: nó nói
    một cohort **hình dạng như C-1** sẽ tốn bao nhiêu nếu chỉ chạy phần giữ
    lại, chứ không nói C-1 "đáng ra" tốn ít hơn — tuyển chọn được rút ra từ
    chính kết quả của C-1, nên C-1 là cái giá phải trả để biết nó.
    """
    lines = ["| cohort | phần | task | lượt | turn | giây phiên | token | USD nhà cung cấp báo |",
             "|---|---|---:|---:|---:|---:|---:|---:|"]
    for nhan in _thu_tu_cohort(du_lieu):
        cs = [c for cs in du_lieu.values() for c in cs if c["cohort"] == nhan]
        for ten, phan in (("giữ", [c for c in cs if c["task"] in giu]),
                          ("cắt", [c for c in cs if c["task"] not in giu])):
            if not phan:
                continue
            tok = sum(c["tokens"] for c in phan)
            lines.append(
                f"| {nhan} | {ten} | {len(phan)} | {sum(c['luot_a'] + c['luot_b'] for c in phan)} | "
                f"{sum(c['turns'] for c in phan)} | {sum(c['giay'] for c in phan):.0f} | "
                f"{_so(tok) if all(c['co_token'] for c in phan) else _so(tok) + ' (thiếu)'} | "
                f"{sum(c['usd'] for c in phan):.2f} |")
    return lines


def _dong_trung(du_lieu: dict) -> list[str]:
    """Nơi sổ có nhiều dòng cho cùng một lượt — nói ra để "lượt ghi" đọc được."""
    ra = []
    for cs in du_lieu.values():
        for c in cs:
            thua = (c["ghi_a"] - c["luot_a"]) + (c["ghi_b"] - c["luot_b"])
            if thua:
                ra.append(f"{c['cohort']}/`{c['task']}` +{thua}")
    return sorted(ra)


def chon(du_lieu: dict, tasks: dict[str, str]) -> set[str]:
    """Tuyển chọn theo đúng tiêu chí của việc còn mở, cộng "hoà còn biến động".

    Hai nhóm được giữ: task **đã từng có nhánh thắng nhánh kia** (Δ ≠ 0 ở một
    cohort nào đó), và task hoà nhưng `D > 0` — nó chưa chạm trần/sàn nên mua
    thêm lượt còn có thể mua được tín hiệu. Task `D = 0` ở mọi cohort thì mua
    bao nhiêu lượt nữa cũng ra đúng một câu trả lời: đó là tiêu chí cắt.
    """
    return {t for t in tasks
            if nhom_task(du_lieu.get(t) or []) in (PHAN_BIET, HOA_CO_BIEN_DONG)}


def report(sach: dict, tho: dict, tasks: dict[str, str], ghi_chu: list[str]) -> str:
    giu_tho, giu_sach = chon(tho, tasks), chon(sach, tasks)
    lines = ["# Sức phân biệt theo task — đo trên lượt đã ghi", "",
             "Sinh bằng `python3 validation/bench_discriminating_power.py`. Không một lượt gọi "
             "model nào: mọi số dưới đây đọc từ `results.jsonl` và kho bằng chứng của các cohort "
             "đã đóng. Định nghĩa `lượt` / `có thông tin` / `không dùng được` nằm ở đầu script và "
             "lấy từ giao thức, không phát minh thêm.", ""]
    if ghi_chu:
        lines += ["> " + g for g in ghi_chu] + [""]
    trung = _dong_trung(sach)
    if trung:
        lines += ["> Dòng trùng (một `(task, điều kiện, lượt)` chạy nhiều lần; giữ dòng **cuối** "
                  "theo giao thức): " + ", ".join(trung) + ".", ""]
    lines += ["## Bảng 1 — ba mươi task", ""] + bang_30_task(sach, tasks)
    lines += ["", "## Bảng 2 — tổng theo cohort", ""] + bang_tong_cohort(sach, tho, tasks)
    lines += ["", "## Bảng 3 — theo từng cohort × task, hai cách đọc", ""] + bang_theo_cohort(sach, tho)
    lines += ["", "## Bảng 4 — kiểu kết thúc của lượt", ""] + bang_ket_thuc(sach)
    lines += ["", "## Bảng 5 — giá của phần bị cắt", "",
              f"Giữ theo **định nghĩa lượt đã khai** (bỏ lượt hỏng hạ tầng) — đây là tuyển "
              f"chọn được đề nghị: "
              f"{', '.join('`' + t + '`' for t in sorted(giu_sach)) or '**không task nào**'}.",
              f"Đối chiếu, giữ theo cách đọc **như đã chấm**: "
              f"{', '.join('`' + t + '`' for t in sorted(giu_tho)) or '**không task nào**'}.",
              ""] + tiet_kiem(sach, giu_sach)
    chua = [t for t in sorted(tasks) if not [c for c in (sach.get(t) or []) if not c["mo_phong"]]]
    if chua:
        lines += ["", "## Bảng 6 — task không quyết được", ""]
        for t in chua:
            ly_do = tasks[t] or "không có dòng kết quả nào trong các sổ đã đọc"
            lines.append(f"- `{t}`: **unknown** — {ly_do[:220]}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- tự kiểm


def tu_kiem() -> None:
    """Ghim ba thứ: `D` khớp `|Δ|` đã in, quy tắc dùng được, và nhóm task."""
    def luot(outcome, **kw):
        return {"outcome": outcome, "error": "", "cost_usd": 0.0, **kw}

    # C-1 `sec-2`: AISEF 0/3, trần 2/3 → báo cáo in Δ = −0,67; D phải bằng 0,67.
    sp = suc_phan_biet([FAIL] * 3, [PASS, PASS, FAIL])
    assert sp == {"cap": 9, "co_thong_tin": 6, "cung_pass": 0, "cung_fail": 3,
                  "D": 6 / 9}, sp
    # C-1 `sec-1` (Δ −0,33) và `state-3` (Δ +0,33) → D 0,33.
    assert suc_phan_biet([PASS, PASS, FAIL], [PASS] * 3)["D"] == 3 / 9
    assert suc_phan_biet([PASS] * 3, [PASS, FAIL, PASS])["D"] == 3 / 9
    # Chạm trần và sàn: không cặp nào có thông tin.
    assert suc_phan_biet([PASS] * 3, [PASS] * 3)["co_thong_tin"] == 0
    assert suc_phan_biet([FAIL] * 3, [FAIL] * 3)["co_thong_tin"] == 0
    # C-1b `sec-2`: 5/6 cả hai nhánh → Δ = 0 nhưng D > 0. Một hoà **còn biến
    # động** vẫn phân biệt được ở mức cặp; gộp nó vào "chạm trần" là mất tín hiệu.
    sp = suc_phan_biet([PASS] * 5 + [FAIL], [PASS] * 5 + [FAIL])
    assert sp["co_thong_tin"] == 10 and sp["cap"] == 36, sp

    # Dùng được: PASS sau phiên bị cắt giữ lại, FAIL vì hạ tầng thì không.
    assert dung_duoc(luot(PASS), "phien_cat") and dung_duoc(luot(PASS), "ha_tang")
    assert not dung_duoc(luot(FAIL), "phien_cat") and not dung_duoc(luot(FAIL), "ha_tang")
    assert dung_duoc(luot(FAIL), "tran_luot")          # trần lượt là ngân sách agent
    assert not dung_duoc(luot("INVALID"), "khong_cham_duoc")

    # Phân loại đọc `exit_status` của bằng chứng trước, rồi `error` của dòng kết quả.
    assert phan_loai_luot(luot(FAIL), {"exit_status": "timeout"}) == "ha_tang"
    assert phan_loai_luot(luot(FAIL, error="exceeded 1800s"), None) == "ha_tang"
    assert phan_loai_luot(luot(PASS, error="quá 1800s"), None) == "ha_tang"
    assert phan_loai_luot(luot(FAIL), {"exit_status": "max_turns"}) == "tran_luot"
    assert phan_loai_luot(luot(FAIL, error="max_turns"), None) == "tran_luot"
    assert phan_loai_luot(luot(PASS, error=f"x {CHU_KY_PHIEN_CAT} y"), None) == "phien_cat"
    assert phan_loai_luot(luot(PASS), None) == "ok"

    # Nhóm: "đã từng có nhánh thắng nhánh kia" thắng mọi cohort hoà sau đó.
    def c(delta, p1_a, p1_b, mo_phong=False):
        return {"delta": delta, "p1_a": p1_a, "p1_b": p1_b, "n_a": 3, "n_b": 3,
                "mo_phong": mo_phong}
    assert nhom_task([c(-0.67, 0.0, 0.67), c(0.0, 0.83, 0.83)]) == PHAN_BIET
    assert nhom_task([c(0.0, 1.0, 1.0)]) == TRAN
    assert nhom_task([c(0.0, 0.0, 0.0)]) == SAN
    assert nhom_task([c(0.0, 0.83, 0.83)]) == HOA_CO_BIEN_DONG
    assert nhom_task([]) == CHUA_DO
    # Cohort mô phỏng một mình không đủ để kết luận gì.
    assert nhom_task([c(0.5, 1.0, 0.5, mo_phong=True)]) == CHUA_DO


def main(argv: list[str]) -> int:
    if "--tu-kiem" in argv:
        tu_kiem()
        print("tự kiểm: ok")
        return 0
    args = [a for a in argv if not a.startswith("--")]
    so_list = [Path(a).expanduser() for a in args] or list(COHORT_MAC_DINH)
    tasks_dir = ROOT / "tests" / "bench" / "tasks"
    sach, ghi_chu = thu_thap(so_list, tasks_dir, loai_bo_ha_tang=True)
    tho, _ = thu_thap(so_list, tasks_dir, loai_bo_ha_tang=False)
    print(report(sach, tho, doc_task(tasks_dir), ghi_chu))
    return 0


if __name__ == "__main__":
    tu_kiem()
    raise SystemExit(main(sys.argv[1:]))
