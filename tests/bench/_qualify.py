"""Tuyển cặp model↔CLI trước khi cột 2 được phóng (G5.3) — **không chấm điểm gì**.

Đợt này trả lời đúng **một** câu hỏi, rẻ: *cặp model↔CLI này có mất quá nhiều
phiên vì CLI cắt giữa chừng, tới mức 72 lượt của cột 2 mua không được gì?*
C-1b đã trả giá cho câu hỏi ấy sau khi chạy: 36 lượt, 2,0 giờ phiên, 41,9 triệu
token, **0** cặp mang thông tin, và con số `+0,06` đã in là hiện vật của lỗi 86
([BENCH-TASK-DISCRIMINATION.md](../../docs/BENCH-TASK-DISCRIMINATION.md) §1).

Vì thế ở đây **không** có scorer, **không** có `pass@1`, **không** có nhánh
trần: một phiên bị cắt là chuyện của cặp model↔CLI, không của harness, nên thứ
duy nhất được đo là **trạng thái kết thúc của từng phiên**. Bỏ phần chấm cũng là
bỏ phần đắt nhất mà câu hỏi không cần.

Ngưỡng, số phiên, task, luật phán quyết: **đã đăng ký và ghim** ở
[docs/BENCH-PAIR-QUALIFICATION-PROTOCOL.md](../../docs/BENCH-PAIR-QUALIFICATION-PROTOCOL.md)
§2 (vùng `QUAL-FROZEN`, digest ở `docs/closure-gate.json` → G5.3 →
`protocol_sha256`). Hằng số dưới đây là **bản mã** của vùng ghim ấy và
`tests/test_meta.py::TestGiaoThucTuyenCapBiGhim` buộc hai bên khớp nhau: đổi một
con số ở đây mà không ghim lại văn bản thì phép kiểm đỏ. Đó là điều kiện để câu
"ngưỡng có trước dữ liệu" đọc được, chứ không phải để làm khó người sửa.

Ba chỗ cố ý **khác** đợt đo cohort, và mỗi chỗ có lý do:

1. **Không chạy lại phiên hỏng** (`INFRA_RETRIES` của cohort là 1). Đợt tuyển
   cần tỉ lệ cắt **thô** của từng phiên; chính sách chạy lại của cohort đi vào
   *số học* của ngưỡng (`p^2`), không đi vào phép đo.
2. **Sổ được ghi sau từng phiên**, không ghi một lần ở cuối như `_runner.run` —
   một đợt 2 giờ bị kill ở phiên 27 phải mất một phiên, không mất 27.
3. **Sổ nằm ở `.aisef-qual/`, không ở `.bench*/`.** Phiên tuyển **không phải**
   dữ liệu cohort; để chúng vào `.bench*/results.jsonl` là trộn đúng thứ mà
   G5.2 tồn tại để chặn (probe `probe_cut_session_separation` quét
   `.bench*/results.jsonl`).

Chạy (người vận hành, tốn phiên thật — cần `AISEF_BENCH=1`):

    python3 -m tests.bench qualify --client opencode --note "mycombo→<TÊN>" --du-toan
    python3 -m tests.bench qualify --client opencode --note "mycombo→<TÊN>"
    python3 -m tests.bench qualify --bao-cao          # dựng lại báo cáo từ sổ
    python3 -m tests.bench qualify --tu-kiem          # client GIẢ, 0 phiên thật
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from aisef.clients.stream import INFRA_STATUSES, exit_status_of

from . import _mine as M
from . import _runner as R

# --------------------------------------------------------------------------
# Hằng số đã đăng ký. Bản văn xuôi + số học đầy đủ ở
# docs/BENCH-PAIR-QUALIFICATION-PROTOCOL.md §2 (vùng ghim). Đừng đổi ở đây mà
# không ghim lại văn bản: test_meta so từng con số.
# --------------------------------------------------------------------------

#: Trần tỉ lệ phiên bị cắt để một cặp được dùng cho cột 2. Suy ra, không bốc:
#: thiết kế đã đăng ký là 36 lượt mỗi nhánh với 1 lần chạy lại, nên một lượt bị
#: *chấm* trên phiên cắt cần **cả hai** phiên cắt — xác suất `p²`. Ngân sách là
#: ≤ 1 lượt nhiễm mỗi nhánh (một phần ba của 3 lượt nhiễm đã sinh ra `+0,06`
#: của C-1b), tức `36 p² ≤ 1` → `p ≤ 1/6`.
NGUONG_TI_LE_CAT = 1 / 6

#: Trần **mọi** kiểu hỏng hạ tầng (cắt + timeout + rate_limit + infra) trên số
#: phiên hợp lệ. Không phải số của tôi: đây là điều kiện "không kết luận được"
#: số 1 đã đăng ký ở [BENCH-PREREGISTRATION-C2.md](../../docs/BENCH-PREREGISTRATION-C2.md)
#: §2, đọc trên phiên thay vì trên lượt.
NGUONG_HONG_HA_TANG = 1 / 3

#: Số phiên hợp lệ mỗi cặp — vừa là cỡ mẫu, vừa là sàn. Nhỏ nhất để luật
#: "tỉ lệ quan sát ≤ 1/6" có **cả hai** sai số ≤ 5 %: một cặp 30 % lọt qua
#: 4,7 % số lần, một cặp 5 % bị loại 1,2 % số lần (số học ở protocol §2.3).
SO_PHIEN_TUYEN = 28

#: Task để tuyển. `state-4` nằm trong 12 task đã đăng ký, `D = 0` ở C-1 (chưa
#: bao giờ tách hai nhánh → phiên tuyển không thể bị đọc thành thông tin), và
#: turn/giây mỗi phiên của nó nằm **trên** trung vị cohort (22,8 turn · 258 s so
#: với 19,8 · 248 s) — nên tỉ lệ cắt đo được không bị thiên xuống vì phiên ngắn.
TASK_TUYEN = "bug-a2-state-4"

#: Trần thời gian của cả đợt tuyển, phút. 180 = 1,5× dự phóng 2,0 giờ; không có
#: nó thì trần thật là 28 × `run.timeout_seconds` = 14 giờ.
TRAN_PHUT = 180.0

#: Đo trên C-1 (`bug-a2-state-4`, 6 phiên: 1546 s · 137 turn · 7 826 451 token).
#: Chỉ để **dự toán** in ra trước khi tiêu, không vào phán quyết.
GIAY_MOI_PHIEN = 1546 / 6
TOKEN_MOI_PHIEN = 7_826_451 / 6

#: Client mà "phiên bị cắt" có định nghĩa **đo được** trong mã
#: (`aisef/clients/opencode.py` — chữ ký cú pháp gọi công cụ không phân giải
#: được, đo trên C-1 § O-7). Client khác không có bộ phát hiện ấy, nên tỉ lệ cắt
#: của nó **không đo được** và phán quyết là `INCONCLUSIVE` — không bao giờ
#: `QUALIFIED`. Một tiêu chí không được thoả bằng sự vắng mặt của phép đo.
CLIENT_DO_DUOC = ("opencode",)

#: Chuỗi mà adapter OpenCode đặt vào `RunResult.error` cho đúng kiểu hỏng ấy.
#: Một phép kiểm chạy client giả ở chế độ `cut` buộc chuỗi này còn khớp.
DAU_HIEU_CAT = "could not parse the model's tool call"

#: Trạng thái thoát **loại khỏi mẫu**: không phải tính chất của cặp model↔CLI mà
#: là việc của người vận hành (khoá sai, quyền bị chặn). Đếm riêng, nêu tên, và
#: không vào mẫu số — để một khoá hết hạn không bị đọc thành "cặp này sạch".
LOAI_KHOI_MAU = ("auth", "permission")

#: Thư mục sổ + cây làm việc của đợt tuyển. **Không** khớp `.bench*` có chủ ý.
THU_MUC = R.ROOT / ".aisef-qual"
TEN_SO = "qualification.jsonl"

#: Bản sao sổ được commit. `.aisef-qual/` bị gitignore nên nó sống đúng tới lần
#: dọn máy kế tiếp; cột `evidence` của báo cáo phải trỏ vào thứ còn lại sau đó.
SO_TRONG_KHO = "closure-evidence/bench-pair-qualification.jsonl"

BANNER_GIA = ("KHÔNG PHẢI KẾT QUẢ ĐO — phiên do một binary GIẢ phát, "
              "không model nào được gọi.")

GIAO_THUC = "docs/BENCH-PAIR-QUALIFICATION-PROTOCOL.md"
MOC_DAU = r"<!--\s*QUAL-FROZEN:BEGIN\s*-->"
MOC_CUOI = r"<!--\s*QUAL-FROZEN:END\s*-->"
#: Giữ lại cho `tests/test_bench_qualification.py`, dựng từ hai mốc trên để hai
#: chỗ không thể lệch nhau.
VUNG_GHIM = rf"(?s){MOC_DAU}\n(.*?)\n{MOC_CUOI}"


# ------------------------------------------------------------------ số học


def _cdf(k: int, n: int, p: float) -> float:
    """P(X ≤ k) với X ~ Bin(n, p). `math.comb`, không phụ thuộc ngoài."""
    return sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k + 1))


def cp_tren(k: int, n: int, conf: float = 0.95) -> float:
    """Biên trên Clopper–Pearson một phía cho `k/n`.

    Báo cáo phải in **khoảng**, không chỉ một điểm: 0/28 và 4/28 cho hai câu
    khác nhau về cặp, và 0/28 vẫn **không** loại được một cặp 10 %.
    """
    if n <= 0 or k >= n:
        return 1.0
    lo, hi = k / n, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if _cdf(k, n, mid) > 1 - conf:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def phan_loai(exit_status: str, error: str) -> str:
    """Một phiên → một nhãn. Bốn nhãn, không có nhãn thứ năm."""
    if exit_status in LOAI_KHOI_MAU:
        return "loại"
    if exit_status in INFRA_STATUSES:
        return "cắt" if DAU_HIEU_CAT in (error or "") else "hạ tầng"
    return "xong"


def tong_hop(rows: list[dict]) -> list[dict]:
    """Sổ → một dòng mỗi cặp `(model đã khai, client)`.

    Gộp theo lời khai của người vận hành (`note`), không theo model quan sát
    được: `mycombo` là một alias, nên hai đợt trên hai mô hình nền trông y hệt
    nhau trong dữ liệu (xem `Result.note`).
    """
    theo_cap: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        theo_cap.setdefault((r.get("note") or r.get("model") or "?", r.get("client") or "?"), []).append(r)
    ra = []
    for (model, client), phien in sorted(theo_cap.items()):
        dem = {n: sum(1 for p in phien if p.get("nhan") == n) for n in ("cắt", "hạ tầng", "xong", "loại")}
        hop_le = dem["cắt"] + dem["hạ tầng"] + dem["xong"]
        ti_le = dem["cắt"] / hop_le if hop_le else 0.0
        ha_tang = (dem["cắt"] + dem["hạ tầng"]) / hop_le if hop_le else 0.0
        t = {
            "model": model, "client": client, "phien": len(phien), "hop_le": hop_le,
            "cat": dem["cắt"], "ha_tang": dem["hạ tầng"], "xong": dem["xong"],
            "loai": dem["loại"], "ti_le": ti_le, "ti_le_ha_tang": ha_tang,
            "cp95": cp_tren(dem["cắt"], hop_le), "gia": any(p.get("gia") for p in phien),
            "giay": sum(float(p.get("giay") or 0) for p in phien),
            "turn": sum(int(p.get("turn") or 0) for p in phien),
            "token": sum(int(p.get("token") or 0) for p in phien),
            "task": sorted({str(p.get("task") or "") for p in phien}),
        }
        t["phan_quyet"], t["vi_sao"] = phan_quyet(t)
        ra.append(t)
    return ra


def phan_quyet(t: dict) -> tuple[str, str]:
    """Ba kết cục, đúng ba, và lý do đọc ra được từ số của chính dòng ấy."""
    if t["client"] not in CLIENT_DO_DUOC:
        return "INCONCLUSIVE", (f"`{t['client']}` không có bộ phát hiện phiên bị cắt trong mã — "
                                "tỉ lệ cắt không đo được, không suy ra bằng 0")
    if t["hop_le"] < SO_PHIEN_TUYEN:
        return "INCONCLUSIVE", (f"{t['hop_le']}/{SO_PHIEN_TUYEN} phiên hợp lệ"
                                + (f" ({t['loai']} phiên bị loại: khoá/quyền)" if t["loai"] else ""))
    if t["ti_le"] > NGUONG_TI_LE_CAT:
        return "NOT_QUALIFIED", (f"tỉ lệ cắt {_p(t['ti_le'])} > ngưỡng {_p(NGUONG_TI_LE_CAT)} "
                                 f"({t['cat']}/{t['hop_le']} phiên)")
    if t["ti_le_ha_tang"] > NGUONG_HONG_HA_TANG:
        return "NOT_QUALIFIED", (f"hỏng hạ tầng {_p(t['ti_le_ha_tang'])} > ngưỡng đã đăng ký "
                                 f"{_p(NGUONG_HONG_HA_TANG)}")
    return "QUALIFIED", (f"{t['cat']}/{t['hop_le']} phiên bị cắt = {_p(t['ti_le'])} ≤ "
                         f"{_p(NGUONG_TI_LE_CAT)} (biên trên 95 %: {_p(t['cp95'])})")


def chon_cap(tom: list[dict]) -> dict | None:
    """Luật chọn khi nhiều cặp đạt — khai trước để không phải chọn sau khi thấy số:
    tỉ lệ cắt thấp nhất, rồi ít hỏng hạ tầng hơn, rồi thứ tự chữ."""
    dat = [t for t in tom if t["phan_quyet"] == "QUALIFIED"]
    if not dat:
        return None
    return min(dat, key=lambda t: (t["ti_le"], t["ti_le_ha_tang"], t["client"], t["model"]))


# ------------------------------------------------------------------ dự toán


def _p(x: float, n: int = 3) -> str:
    """Thập phân kiểu Việt (dấu phẩy) — bảng của bench in `0,00`, không `0.00`."""
    return f"{x:.{n}f}".replace(".", ",")


def _gio(giay: float) -> str:
    return f"{_p(giay / 3600, 1)} giờ"


def du_toan(client: str, model: str, task_id: str, phien: int, *, tran_phut: float = TRAN_PHUT,
            timeout: int = 1800) -> str:
    """Hoá đơn **trước** khi tiêu, bằng đơn vị nhà cung cấp này thật sự báo.

    Nhà cung cấp sau `mycombo` báo `cost_usd = 0` ở mọi bước của C-1 và C-1b, nên
    một cột `$` toàn số 0 đọc thành "miễn phí" — đó là **vắng mặt giá**, không
    phải vắng mặt tài nguyên. Vì thế dự toán tính bằng phiên, turn, token và giờ.
    """
    toi_da = min(phien * timeout, tran_phut * 60)
    nguong_cat = math.floor(phien * NGUONG_TI_LE_CAT)
    bo_som = math.ceil((nguong_cat + 1) / 0.30)
    return "\n".join([
        f"# Dự toán đợt tuyển cặp — {model or '(model mặc định)'} / {client}",
        "",
        "KHÔNG chạy gì. Bản in này là hoá đơn để chủ dự án xem trước khi cho phép.",
        "",
        "| khoản | số |",
        "|---|---|",
        f"| task | `{task_id}` |",
        f"| phiên sẽ chạy | **{phien}** (một phiên = một lần gọi client, không chạy lại) |",
        "| trần lượt mỗi phiên | 0 (chỉ đồng hồ chặn — đúng như cohort) |",
        f"| `run.timeout_seconds` | {timeout} |",
        f"| giờ phiên dự phóng | **{_gio(phien * GIAY_MOI_PHIEN)}** ({GIAY_MOI_PHIEN:.0f} s/phiên, đo trên C-1 `{TASK_TUYEN}`) |",
        f"| giờ phiên trần | {_gio(toi_da)} (trần đợt {tran_phut:.0f} phút cắt trước {phien} × {timeout} s = {_gio(phien * timeout)}) |",
        f"| turn dự phóng | ≈ {phien * 137 / 6:.0f} |",
        f"| token dự phóng | ≈ {_p(phien * TOKEN_MOI_PHIEN / 1e6, 1)} triệu |",
        "| tiền | **0,00 USD — và con số ấy không nói gì.** Nhà cung cấp này báo `cost_usd = 0` ở mọi bước của C-1 (88,9 M token) và C-1b (41,9 M token). Giá thì vắng mặt; tài nguyên thì không. |",
        "",
        f"**Luật quyết định, đã ghim trước khi có dữ liệu** ({GIAO_THUC} §2):",
        f"đạt khi ≤ {nguong_cat} phiên bị cắt trên {phien} phiên hợp lệ "
        f"(tỉ lệ ≤ {_p(NGUONG_TI_LE_CAT)}); "
        f"từ phiên cắt thứ {nguong_cat + 1} đợt **dừng ngay** vì không còn đạt được nữa "
        f"— một cặp 30 % vì thế thường tốn ≈ {bo_som} phiên ({_gio(bo_som * GIAY_MOI_PHIEN)}), không phải {phien}.",
        "",
        f"**So với thứ nó đứng trước:** cột 2 đã đăng ký là 12 task × 3 lượt × 2 nhánh "
        f"= 72 lượt ≈ 5,7 giờ phiên và 88,9 M token (đo trên C-1). Đợt tuyển này là "
        f"≈ {phien * GIAY_MOI_PHIEN / 20484 * 100:.0f} % giờ phiên và "
        f"≈ {phien * TOKEN_MOI_PHIEN / 88_930_672 * 100:.0f} % token của nó. "
        "Cái nó tránh là đúng thứ C-1b đã mua: 36 lượt, 2,0 giờ, 41,9 M token, 0 cặp mang thông tin.",
    ])


# -------------------------------------------------------------------- chạy


#: Tạo tác mà **không** đợt bench nào được để lại ở gốc kho khung. Kho khung
#: không phải một dự án AISEF; nó không có `_bmad-output`, và mọi phiên có
#: workspace riêng để ghi vào.
RANH_GIOI = ("_bmad-output",)


def ro_ri_ngoai_workspace(root: Path, truoc: bool) -> str:
    """Tên tạo tác mà đợt chạy để lại ở gốc kho khung — "" nếu sạch.

    Lỗi 166. Đo sau đợt tuyển G5.3: `_bmad-output/` xuất hiện ở gốc kho AISEF
    trong khi **mỗi phiên vẫn ghi đúng vào workspace của mình** — một tập khác,
    từ một lượt gọi mà `--project` rơi về mặc định `"."`.

    Vì sao phải nói to chứ không chỉ dọn: cây bẩn làm `closure.pin_target` từ
    chối, nên một đợt bench có thể chặn đúng bước chốt đích đóng dự án; và một
    thư mục lạ ở gốc kho dễ bị `git add -A` quét vào một commit.

    `truoc` là trạng thái **trước** đợt chạy: thư mục có sẵn từ trước không phải
    do đợt này tạo ra, và đổ lỗi cho nó là báo sai.
    """
    if truoc:
        return ""
    return ", ".join(t for t in RANH_GIOI if (root / t).exists())


def _phien(task, client, ws: Path, model: str):
    """Một phiên **đúng hình dạng nhánh AISEF của cohort**, không chấm điểm.

    Dựng qua đúng các hàm mà `_runner.run` dùng (`materialize`, `compile_for`,
    `_prompt`, `RunSpec`) chứ không dựng lại bằng tay: nếu cohort đổi đề bài hay
    đổi env thì đợt tuyển phải đổi theo, nếu không nó đo một thứ khác. Phép kiểm
    `test_bench_qualification.py` so argv + đề bài + env của hai đường đi.

    Nhánh AISEF chứ không phải nhánh trần là có chủ ý: C-1 đo tỉ lệ cắt của
    nhánh AISEF gấp ~2 lần nhánh trần (27 % so với 14 %), và một cổng hợp lệ
    không được tuyển cặp trên chân dễ hơn của nó.
    """
    base = R.head_sha(ws)
    R.write_compile_report(ws, [R.compile_for(client.id, ws, aisef_bin=str(R.ROOT / "bin" / "aisef"))])
    cfg = R.Config.load(ws)
    settings = ws / ".claude" / "settings.json"
    spec = R.RunSpec(
        prompt=R._prompt(task, ws, cfg), workdir=ws, max_turns=0,
        timeout_seconds=cfg["run.timeout_seconds"],
        settings_file=settings if settings.is_file() else None,
        model=model,
        env={R.ENV_WRITE_SCOPE: ",".join(task.write_scope), R.ENV_STORY_ID: task.id,
             R.ENV_BASE_REF: base, R.ENV_WORKDIR: str(ws), R.ENV_PROJECT: str(ws)},
    )
    return client.run(spec)


def chay(client, *, task_id: str = TASK_TUYEN, phien: int = SO_PHIEN_TUYEN, model: str = "",
         note: str = "", thu_muc: Path | None = None, tran_phut: float = TRAN_PHUT,
         gia: bool = False, out=sys.stderr) -> list[dict]:
    """Chạy tới `phien` phiên, ghi sổ **sau từng phiên**, trả về các dòng mới.

    Dừng sớm khi số phiên bị cắt đã vượt trần — lúc ấy không lượt nào còn cứu
    được phán quyết, nên mỗi phiên tiếp theo là tiền đổ vào một câu trả lời đã
    biết ("dừng sớm, chốt trước", đúng tinh thần luật đã đăng ký của cohort).
    """
    thu_muc = thu_muc or THU_MUC
    # Ranh giới workspace (lỗi 166): chụp trạng thái gốc kho **trước** khi chạy,
    # để cuối đợt nói được "đợt này để lại cái gì" thay vì "gốc kho có cái gì".
    ranh_gioi_truoc = {t: (R.ROOT / t).exists() for t in RANH_GIOI}
    tasks = {t.id: t for t in M.load_tasks(M.TASKS_DIR, M.KEEP_DIR / "tasks")}
    if task_id not in tasks:
        raise ValueError(f"không có task {task_id!r}")
    task = tasks[task_id]
    so = thu_muc / TEN_SO
    so.parent.mkdir(parents=True, exist_ok=True)
    tran_cat = math.floor(phien * NGUONG_TI_LE_CAT)
    moi: list[dict] = []
    cat = 0
    t0 = time.monotonic()
    for i in range(1, phien + 1):
        if (time.monotonic() - t0) / 60 >= tran_phut:
            print(f"TRẦN THỜI GIAN {tran_phut:.0f} phút — dừng ở phiên {i - 1}/{phien}", file=out)
            break
        ws = R.materialize(task, thu_muc / "run" / client.id / task.id / f"s{i}",
                           tests=task.tests_visible)
        t1 = time.monotonic()
        res = _phien(task, client, ws, model)
        trang_thai = exit_status_of(res)
        nhan = phan_loai(trang_thai, res.error)
        cat += nhan == "cắt"
        dong = {
            "luc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "client": client.id, "model": getattr(res, "model", "") or model, "note": note,
            "task": task.id, "phien": i, "exit_status": trang_thai, "nhan": nhan,
            "turn": res.num_turns, "giay": round(time.monotonic() - t1, 1),
            "token": (res.input_tokens + res.output_tokens + res.cache_read_tokens
                      + res.cache_creation_tokens),
            "usd": res.cost_usd, "loi": (res.error or "")[:200], "ws": str(ws), "gia": gia,
        }
        with so.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(dong, ensure_ascii=False) + "\n")
        moi.append(dong)
        print(f"  {i:2d}/{phien} {nhan:8s} {trang_thai:10s} {dong['turn']:3d} turn "
              f"{dong['giay']:6.0f} s  cắt {cat}/{tran_cat + 1}", file=out)
        if cat > tran_cat:
            print(f"DỪNG SỚM: {cat} phiên bị cắt > trần {tran_cat} — cặp này không còn đạt được "
                  f"dù {phien - i} phiên còn lại đều sạch", file=out)
            break
    ro = ", ".join(t for t, co_truoc in ranh_gioi_truoc.items()
                   if not co_truoc and (R.ROOT / t).exists())
    if ro:
        print(f"CẢNH BÁO ranh giới workspace: đợt này để lại `{ro}` ở gốc kho khung "
              f"({R.ROOT}). Mỗi phiên có workspace riêng; gốc kho không phải một dự "
              f"án AISEF. Cây bẩn làm `closure --pin-target` từ chối, và `git add -A` "
              f"dễ quét nhầm nó vào một commit (lỗi 166).", file=out)
    return moi


def doc_so(thu_muc: Path | None = None) -> list[dict]:
    """Sổ đã ghi → các dòng. Vắng mặt thì rỗng, không bịa."""
    so = (thu_muc or THU_MUC) / TEN_SO
    if not so.is_file():
        return []
    return [json.loads(l) for l in so.read_text(encoding="utf-8").splitlines() if l.strip()]


# ------------------------------------------------------------------ báo cáo


def _digest_giao_thuc(root: Path) -> str:
    """Digest vùng ghim của giao thức, tính lại lúc dựng báo cáo.

    In vào báo cáo để người đọc sau thấy dữ liệu này bị chấm bằng **văn bản
    nào**. Giá trị ghim thì sống ở `docs/closure-gate.json`, không ở đây và
    không ở trong chính tệp nó ghim.

    Công thức gọi sang `closure.frozen_region_digest` chứ không tự băm: bản đầu
    của hàm này là **bản thứ ba** của cùng một công thức (probe G5.1, test_meta,
    và đây), mà `BENCH-PREREGISTRATION-C2.md` §1.1 nói thẳng là không được có bản
    thứ hai. Ba bản thì hai trong ba có thể lệch mà không ai thấy, và cái lệch ấy
    đọc thành "digest không khớp" ở đúng chỗ nó phải khớp.
    """
    from aisef.control.closure import AmbiguousRegion, frozen_region_digest

    p = root / GIAO_THUC
    if not p.is_file():
        return ""
    try:
        return frozen_region_digest(p, {"begin": MOC_DAU, "end": MOC_CUOI})
    except AmbiguousRegion:
        return ""


#: Hằng số ↔ nhãn của nó trong bảng §2.10 của vùng ghim. Bản mã phải khớp từng
#: con số; đổi ở một chỗ mà không ghim lại chỗ kia là một bar hậu nghiệm.
_HANG_SO_GHIM = (
    ("NGUONG_TI_LE_CAT", lambda: "1/6"),
    ("SO_PHIEN_TUYEN", lambda: str(SO_PHIEN_TUYEN)),
    ("NGUONG_HONG_HA_TANG", lambda: "1/3"),
    ("TASK_TUYEN", lambda: TASK_TUYEN),
    ("TRAN_PHUT", lambda: f"{TRAN_PHUT:.0f}"),
    ("CLIENT_DO_DUOC", lambda: "opencode"),
)


def tien_kiem(root: Path | None = None, *, selfcheck: Path | None = None
              ) -> tuple[bool, list[str], dict]:
    """Bốn điều kiện, kiểm **trước** khi một phiên tuyển thật nào chạy.

    Ràng buộc 2 của chủ dự án: `PREREG_FROZEN` đúng, `protocol_digest` bằng bản
    ghim, selfcheck 19/19, ngưỡng cố định trước khi có dữ liệu — *"do not launch
    qualification if any of these is false."*

    Là một **cửa**, không phải một bản ghi: một bản ghi thì kiểm xong vẫn phóng
    được, nên cửa nằm ở đúng lệnh tiêu tiền. Thiếu bằng chứng đọc là *không biết*
    và không biết thì không phóng — một tiền kiểm vắng mặt không được đọc thành
    một tiền kiểm đạt.
    """
    import json as _json

    from aisef.control.closure import AmbiguousRegion, frozen_region_digest

    root = root or R.ROOT
    hong: list[str] = []
    rec: dict = {"prereg_frozen": False, "protocol_digest": "",
                 "selfcheck_passed": 0, "selfcheck_total": 0,
                 "thresholds_fixed_before_data": False}

    spec = _json.loads((root / "docs/closure-gate.json").read_text(encoding="utf-8"))
    crit = {c["id"]: c for g in spec["gates"] for c in g["criteria"]}

    def ghim(cid: str, khoa_pin: str, khoa_vung: str, nhan: str) -> str:
        c = crit.get(cid) or {}
        tep = root / str(c.get("protocol") or c.get("evidence") or "")
        pin = str(c.get(khoa_pin) or "")
        if not pin:
            hong.append(f"{nhan}: {cid} has no {khoa_pin} recorded")
            return ""
        if not tep.is_file():
            hong.append(f"{nhan}: missing {tep.name}")
            return ""
        try:
            now = frozen_region_digest(tep, c.get(khoa_vung) or {})
        except AmbiguousRegion as e:
            hong.append(f"{nhan}: {tep.name} has {e.n} frozen regions, expected 1")
            return ""
        if now != pin:
            hong.append(f"{nhan}: {tep.name} changed after pinning "
                        f"({pin[:12]} → {now[:12]})")
            return ""
        return now

    rec["prereg_frozen"] = bool(
        ghim("G5.1", "prereg_sha256", "prereg_frozen_region", "PREREG_FROZEN"))
    rec["protocol_digest"] = ghim(
        "G5.3", "protocol_sha256", "protocol_frozen_region", "protocol_digest")

    sc = selfcheck if selfcheck is not None else root / "closure-evidence/bench-selfcheck.json"
    if not sc.is_file():
        hong.append(f"selfcheck: no record at {sc} — run `python3 -m tests.bench selfcheck`"
                    " and record it; an absent selfcheck is not a passing one")
    else:
        d = _json.loads(sc.read_text(encoding="utf-8"))
        rec["selfcheck_passed"] = int(d.get("passed") or 0)
        rec["selfcheck_total"] = int(d.get("total") or 0)
        if rec["selfcheck_passed"] != rec["selfcheck_total"] or rec["selfcheck_total"] < 19:
            hong.append(f"selfcheck: {rec['selfcheck_passed']}/{rec['selfcheck_total']}, "
                        f"expected 19/19")

    # Ngưỡng cố định trước dữ liệu: bản mã phải khớp bảng hằng số **trong** vùng
    # ghim. Vùng ghim có trước một phiên nào chạy (digest ở trên), nên hai cái
    # khớp nhau là cách đọc được rằng bar này không được chọn sau khi thấy số.
    gt = root / GIAO_THUC
    vung = ""
    if gt.is_file():
        import re as _re
        khop = _re.findall(VUNG_GHIM, gt.read_text(encoding="utf-8").replace("\r\n", "\n"))
        vung = khop[0] if len(khop) == 1 else ""
    if not vung:
        hong.append(f"thresholds: cannot read the frozen region of {GIAO_THUC}")
    else:
        lech = [ten for ten, gia_tri in _HANG_SO_GHIM
                if f"| `{ten}` | {gia_tri()} |" not in vung]
        if lech:
            hong.append("thresholds: the code copy no longer matches the frozen table for "
                        + ", ".join(lech) + " — a constant changed without re-freezing the "
                        "text is a post-hoc bar wearing a pre-registered label")
        else:
            rec["thresholds_fixed_before_data"] = True

    return not hong, hong, rec


def bao_cao(rows: list[dict], *, root: Path | None = None) -> str:
    """Markdown đúng hình dạng mà `probe_pair_qualification` đọc (G5.3).

    Probe đòi một bảng có cột `qualifies` cùng `model`, `client`, `cut`, `rate`,
    `evidence` — nên tiêu đề cột mang cả tên Việt và từ khoá ASCII ấy. Giá trị
    của `qualifies` là `có` / `không` / `chưa kết luận`; probe chỉ đọc `có`
    (hoặc `yes`/`✅`) thành đạt, nên `chưa kết luận` **chặn** như nó phải chặn.
    """
    root = root or R.ROOT
    tom = tong_hop(rows)
    chon = chon_cap(tom)
    gia = any(t["gia"] for t in tom)
    nhan_qua = {"QUALIFIED": "có", "NOT_QUALIFIED": "không", "INCONCLUSIVE": "chưa kết luận"}
    d = _digest_giao_thuc(root)
    out = [
        "# Tuyển cặp model↔CLI cho cột 2 (G5.3)",
        "",
        f"Sinh bằng `python3 -m tests.bench qualify --bao-cao`, "
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}. "
        "Không sửa tay một con số nào ở đây: bảng là đầu ra của sổ phiên.",
        "",
    ]
    if gia:
        out += [f"> **{BANNER_GIA}** Bảng dưới đây là phép chứng minh đường ống, "
                "không phải bằng chứng tuyển cặp.", ""]
    out += [
        f"Giao thức đã ghim: [`{GIAO_THUC}`]({Path(GIAO_THUC).name}) §2 — "
        f"digest vùng ghim `{d[:16] or '?'}…`, giá trị đối chiếu ở "
        "`docs/closure-gate.json` → G5.3 → `protocol_sha256`. Ngưỡng "
        f"**{_p(NGUONG_TI_LE_CAT)}** và cỡ mẫu **{SO_PHIEN_TUYEN}** được ghim "
        "*trước* khi một phiên nào chạy; đó là thứ làm bảng này đọc được.",
        "",
        "## 1. Bảng tuyển",
        "",
        "| model | client | phiên tuyển | phiên hợp lệ | phiên bị cắt (cut) | "
        "tỉ lệ cắt (rate) | biên trên 95 % | hỏng hạ tầng (timeout/infra) | "
        "loại khỏi mẫu | phán quyết | qualifies | evidence |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|---|",
    ]
    for t in tom:
        out.append(
            f"| {t['model']} | {t['client']} | {t['phien']} | {t['hop_le']} | {t['cat']} | "
            f"{_p(t['ti_le'])} | {_p(t['cp95'])} | {t['ha_tang']} | {t['loai']} | "
            f"{t['phan_quyet']} | {nhan_qua[t['phan_quyet']]} | `{SO_TRONG_KHO}` |")
    out += ["", "## 2. Vì sao mỗi dòng ra kết cục ấy", ""]
    for t in tom:
        out.append(f"- **{t['model']} / {t['client']}** → `{t['phan_quyet']}`: {t['vi_sao']}.")
    out += [
        "",
        "## 3. Tài nguyên đã tiêu — giá thì vắng, tài nguyên thì không",
        "",
        "| model / client | phiên | turn | giờ phiên | token | USD |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for t in tom:
        out.append(f"| {t['model']} / {t['client']} | {t['phien']} | {t['turn']} | "
                   f"{_p(t['giay'] / 3600, 2)} | {R._so(t['token'])} | "
                   f"vắng mặt (nhà cung cấp báo 0,00) |")
    out += [
        "",
        "Cột USD của nhà cung cấp này là **vắng mặt giá**, không phải miễn phí — "
        "C-1 tiêu 88,9 triệu token và cũng báo 0,00.",
        "",
        "## 4. Kết luận cho cột 2",
        "",
    ]
    if chon:
        out.append(f"Cột 2 chạy trên **{chon['model']} / {chon['client']}** "
                   f"(luật chọn: tỉ lệ cắt thấp nhất, rồi ít hỏng hạ tầng hơn, rồi thứ tự chữ — "
                   f"{GIAO_THUC} §2).")
    else:
        out.append("**Không cặp nào đạt.** Theo phán quyết 3 của chủ dự án, G5.3 là "
                   "`WAIVER_PENDING`: đợt 72 lượt **không** chạy, và việc tiếp theo là quyết định "
                   "miễn trừ của chủ dự án, không phải một đợt đo.")
    out += ["", f"Sổ từng phiên: `{SO_TRONG_KHO}` (bản commit) và `{THU_MUC.name}/{TEN_SO}` "
                "cùng cây làm việc của từng phiên (bị gitignore).", ""]
    return "\n".join(out)


def viet_bao_cao(rows: list[dict], out_rel: str, *, root: Path | None = None,
                 thu_muc: Path | None = None) -> int:
    """Ghi báo cáo + bản sao sổ được commit. Trả 0 khi ghi, 2 khi từ chối.

    **Từ chối ghi bằng chứng đóng gate từ phiên giả.** `docs/BENCH-PAIR-QUALIFICATION.md`
    là thứ probe G5.3 đọc; một bảng sinh từ binary giả ghi vào đúng chỗ ấy là
    bằng chứng bịa, dù có banner. Ranh giới tin cậy, không phải tiện nghi.
    """
    root = root or R.ROOT
    if not rows:
        print("sổ rỗng — chưa có phiên tuyển nào", file=sys.stderr)
        return 2
    dich = root / out_rel
    if any(r.get("gia") for r in rows) and dich == root / "docs/BENCH-PAIR-QUALIFICATION.md":
        print(f"TỪ CHỐI: sổ có phiên giả, mà {out_rel} là bằng chứng của G5.3. "
              f"Dùng `--out` khác để xem thử.", file=sys.stderr)
        return 2
    dich.parent.mkdir(parents=True, exist_ok=True)
    dich.write_text(bao_cao(rows, root=root) + "\n", encoding="utf-8")
    if not any(r.get("gia") for r in rows):
        sao = root / SO_TRONG_KHO
        sao.parent.mkdir(parents=True, exist_ok=True)
        sao.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                       encoding="utf-8")
    print(f"đã ghi {out_rel}", file=sys.stderr)
    return 0


# ------------------------------------------------------------------ tự kiểm


def tu_kiem(out=sys.stdout) -> int:
    """Chứng minh đường ống bằng một binary GIẢ — **0 phiên thật, 0 đồng**.

    Dùng lại đúng script giả của `_selfcheck` (một bản giả trong kho, không hai).
    Hai cohort giả: một cohort 12 phiên cắt ở phiên 2 và 4 (tỉ lệ 2/12 — trộn,
    không dừng sớm), và một cohort 6 phiên cắt ở phiên 1 và 2 để chứng minh luật
    dừng sớm thật sự nổ. Rồi kiểm phán quyết trên số, và kiểm rằng báo cáo **từ
    chối** ghi vào đường dẫn bằng chứng của G5.3.
    """
    import json as _json
    import tempfile

    from aisef.clients.opencode import OpenCodeAdapter

    from . import _selfcheck as S

    kiem: list[tuple[bool, str]] = []

    def dat(ok, ten):
        kiem.append((bool(ok), ten))

    giu = R.KEEP_DIR
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        fake = tmp / "opencode"
        fake.write_text(S._FAKE.replace("TOKEN", _json.dumps(S.TOKEN)), encoding="utf-8")
        fake.chmod(0o755)
        cu = {k: os.environ.get(k) for k in ("AISEF_SELFCHECK_MODE", "AISEF_SELFCHECK_GOLD")}
        os.environ["AISEF_SELFCHECK_MODE"] = "cut:2,4"
        os.environ.pop("AISEF_SELFCHECK_GOLD", None)
        R.KEEP_DIR = tmp / "bench"
        try:
            client = OpenCodeAdapter(binary=str(fake))
            rows = chay(client, phien=12, note="tự-kiểm", thu_muc=tmp / "qual", gia=True, out=out)
            nhan = [r["nhan"] for r in rows]
            dat(len(rows) == 12, f"chạy đủ 12 phiên, không dừng sớm ở 2/12 ({len(rows)})")
            dat(nhan == ["xong", "cắt", "xong", "cắt"] + ["xong"] * 8,
                f"nhãn từng phiên đọc đúng chữ ký cắt: {nhan}")
            dat(all(r["exit_status"] == "infra" for r in rows if r["nhan"] == "cắt"),
                "phiên bị cắt vào `infra`, không lẫn vào cột agent")
            dat(len(doc_so(tmp / "qual")) == 12, "sổ ghi sau từng phiên, đọc lại được")
            [t] = tong_hop(rows)
            dat(abs(t["ti_le"] - 2 / 12) < 1e-9, f"tỉ lệ cắt = {t['ti_le']:.3f} (2/12)")
            dat(t["phan_quyet"] == "INCONCLUSIVE" and f"12/{SO_PHIEN_TUYEN}" in t["vi_sao"],
                f"12 phiên < {SO_PHIEN_TUYEN} → INCONCLUSIVE dù tỉ lệ ≤ ngưỡng ({t['vi_sao']})")
            os.environ["AISEF_SELFCHECK_MODE"] = "cut:1,2"
            som = chay(client, phien=6, note="tự-kiểm-dừng-sớm", thu_muc=tmp / "qual2",
                       gia=True, out=out)
            dat(len(som) == 2, f"dừng sớm khi cặp không còn đạt được nữa ({len(som)}/6 phiên)")
            bang = bao_cao(rows)
            dat(BANNER_GIA in bang, "báo cáo nói rõ đây là phiên giả")
            dat("| qualifies |" in bang and "chưa kết luận" in bang,
                "bảng có cột `qualifies` và không khai `có`")
            (tmp / "docs").mkdir()
            ma = viet_bao_cao(rows, "docs/BENCH-PAIR-QUALIFICATION.md", root=tmp)
            dat(ma == 2 and not (tmp / "docs/BENCH-PAIR-QUALIFICATION.md").exists(),
                "từ chối ghi bằng chứng G5.3 từ phiên giả")
            dat(viet_bao_cao(rows, "docs/thu.md", root=tmp) == 0,
                "vẫn ghi được ra đường dẫn khác để xem thử")
        finally:
            R.KEEP_DIR = giu
            for k, v in cu.items():
                os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)

    hong = [t for ok, t in kiem if not ok]
    print(f"\n# Tự kiểm đợt tuyển cặp\n\n{BANNER_GIA}\n", file=out)
    for ok, ten in kiem:
        print(f"{'✓' if ok else '✗'} {ten}", file=out)
    print(f"\n{len(kiem) - len(hong)}/{len(kiem)} đạt. {BANNER_GIA}", file=out)
    return 1 if hong else 0
