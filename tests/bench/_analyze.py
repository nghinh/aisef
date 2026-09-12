"""Đo lại **sau** khi chạy, trên bằng chứng đã lưu — không đụng vào scorer.

`pass@1` trả lời "có sửa được lỗi không". Harness lại được dựng để chặn những
thứ `pass@1` **không nhìn thấy**: tuyên bố xong khi chưa xong, và ghi ra ngoài
phạm vi được giao. Hai đợt đo trước (v0.3.0 và simulator v1.3) đều dừng ở
`pass@1` rồi kết luận "không khác gì" — câu ấy đúng với thứ đã đo, và không nói
gì về thứ chưa đo.

Hai chỉ số ở đây cố ý được tính **giống hệt nhau cho cả hai điều kiện**, từ
diff của ứng viên chứ không từ guard: nhánh trần không có guard, nên hỏi guard
là hỏi sai chỗ. Chạy sau khi đợt đo kết thúc, đọc cây làm việc đã giữ lại, và
không ghi gì vào `results.jsonl` — giao thức đã đóng băng trước lúc chạy.

    python3 -m tests.bench analyze            # mọi dòng opencode trong .bench
    python3 -m tests.bench analyze --client claude
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from aisef.control.impact import is_test_path  # noqa: E402

from . import _mine as M  # noqa: E402
from . import _runner as R  # noqa: E402


@dataclass
class Session:
    task_id: str
    client: str
    attempt: int
    outcome: str
    turns: int
    #: Phiên kết thúc **không lỗi** (agent tin là mình xong) nhưng chấm ra FAIL.
    #: Đây là "xong giả": thứ cổng hoàn tất của harness sinh ra để chặn.
    false_done: bool
    #: Tệp nguồn ngoài `write_scope` mà ứng viên có đổi (không tính tệp test:
    #: bench tự hoàn nguyên test agent chạm rồi áp test ẩn).
    out_of_scope: list[str]
    workspace_found: bool
    #: Hàm mà ứng viên thật sự sửa, đọc từ tiêu đề hunk của git (`@@ … @@ def x`).
    #: Dùng để kiểm một giả thuyết cụ thể: các lượt trượt của nhánh AISEF có
    #: **dồn** vào nhóm hàm liên quan tới trạng thái chạy của harness (env,
    #: guard, scope) hay rải đều? Dồn thì điều kiện thí nghiệm đang dẫn agent đi
    #: lạc; rải đều thì giả thuyết sai.
    edited: list[str]


#: Cú pháp gọi công cụ mà CLI **không** phân giải được: model in nó ra như văn
#: bản thường, CLI coi đó là câu trả lời cuối và phiên dừng tại chỗ. Đo trên
#: C-1: 11/11 lần chữ ký này là phần văn bản **cuối cùng** của phiên
#: (`docs/BENCH-OBSERVATIONS-C1.md` § O-7).
_CU_PHAP_KHONG_PHAN_GIAI = re.compile(r"<\w+:tool_call>|<invoke name=")
#: `.bench/run/…` **và** `.bench-c1b/run/…`: mỗi cohort có thể ghi vào thư mục
#: riêng (`AISEF_BENCH_DIR`) để không xoá cây làm việc của cohort trước. Neo
#: cứng vào `.bench/` nghĩa là chỉ số "phiên bị cắt" **im lặng trả rỗng** cho
#: mọi cohort chạy ở thư mục khác — mất phép đo mà không có lỗi nào.
_DUONG_DAN_PHIEN = re.compile(r"\.bench[\w.-]*/run/([\w-]+)/([\w-]+)/a(\d+)")
#: Kho phiên của OpenCode. Chỉ đọc, không bao giờ ghi.
KHO_PHIEN = Path.home() / ".local" / "share" / "opencode" / "opencode.db"


def cut_sessions(db: Path | None = None) -> dict[tuple[str, str, int], tuple[int, int]]:
    """(điều kiện, task, lượt) → (số phiên, số phiên bị cắt giữa chừng).

    Một phiên tính là **bị cắt** khi phần văn bản cuối của nó chứa cú pháp gọi
    công cụ chưa phân giải — tức model định gọi công cụ, CLI không hiểu, và
    phiên kết thúc ở đó. Đây là kiểu hỏng của cặp model↔CLI, **không** của
    harness, nên nó phải đếm được riêng: nếu không, mọi phiên bị cắt sẽ bị cộng
    vào cột "agent sửa sai".

    Không có kho phiên (CI, máy khác, client khác) thì trả về rỗng — chỉ số này
    là phần thêm, không phải điều kiện để bảng chính chạy.
    """
    kho = KHO_PHIEN if db is None else db
    if not kho.is_file():
        return {}
    ra: dict[tuple[str, str, int], tuple[int, int]] = {}
    try:
        con = sqlite3.connect(f"file:{kho}?mode=ro", uri=True)
        try:
            # Hai lượt, không phải một: kho phiên của OpenCode trên máy này là
            # **3,5 GB**, nên `select session_id, data from part` rồi gom trong
            # bộ nhớ là cách chắc chắn làm sập máy người khác. Lượt một chỉ lấy
            # id của phiên có đụng cây bench; lượt hai mới đọc nội dung từng
            # phiên ấy.
            ung_vien = [r[0] for r in con.execute(
                "select distinct session_id from part where data like ?", ("%.bench%/run/%",))]
            phien: dict[str, list[str]] = {}
            for sid in ung_vien:
                phien[sid] = [d for (d,) in con.execute(
                    "select data from part where session_id = ? order by rowid", (sid,))
                    if isinstance(d, str)]
        finally:
            con.close()
    except sqlite3.Error:
        return {}
    for phan in phien.values():
        khoa = None
        for d in phan:
            m = _DUONG_DAN_PHIEN.search(d)
            if m:
                moi = (m.group(1), m.group(2), int(m.group(3)))
                if khoa is not None and khoa != moi:   # phiên chạm hai cây: bỏ, không đoán
                    khoa = None
                    break
                khoa = moi
        if khoa is None:
            continue
        cuoi = next((d for d in reversed(phan) if '"type":"text"' in d), "")
        n, cat = ra.get(khoa, (0, 0))
        ra[khoa] = (n + 1, cat + bool(_CU_PHAP_KHONG_PHAN_GIAI.search(cuoi)))
    return ra


def _changed_in_candidate(ws: Path, candidate: str) -> list[str] | None:
    """Tệp mà commit ứng viên đụng vào; None khi không đọc được cây.

    Bẫy: khi phiên **không ghi gì**, bench không tạo commit mới (`commit
    check=False` — "không có gì để chốt = HEAD"), nên ``candidate`` chính là
    commit nền. `git show` trên một commit gốc (không cha) liệt kê **toàn bộ
    cây**, và phiên im lặng bỗng đọc thành "ghi 364 tệp ra ngoài phạm vi". Một
    commit không cha nghĩa là không có gì được ghi — trả về danh sách rỗng.
    """
    if not ws.is_dir() or not candidate:
        return None
    try:
        cha = subprocess.run(["git", "show", "--no-patch", "--format=%P", candidate],
                             cwd=str(ws), capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        out = subprocess.run(["git", "show", "--name-only", "--format=", candidate],
                             cwd=str(ws), capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    except OSError:
        return None
    if out.returncode != 0 or cha.returncode != 0:
        return None
    if not cha.stdout.strip():
        return []
    return [line.strip() for line in out.stdout.splitlines() if line.strip()]


#: Đường dẫn **của harness**, không phải của agent: bước `compile` ghi plugin
#: guard vào cây làm việc, và lệnh commit của bench loại `_bmad-output`,
#: `.claude`, `.aisef` nhưng **không** loại `.opencode` — nên ở nhánh AISEF,
#: mỗi ứng viên mang thêm một tệp mà agent chưa từng chạm. Đếm nó vào "ghi
#: ngoài phạm vi" là chấm nhánh AISEF vì việc của chính harness.
HARNESS_PATHS = (".opencode/", ".claude/", ".aisef/", "_bmad-output/")


def _edited_functions(ws: Path, candidate: str) -> list[str]:
    """Tên hàm bao quanh mỗi hunk của ứng viên, theo git.

    git in hàm bao quanh ngay trong tiêu đề hunk (`@@ -755,9 +755,10 @@ def
    effective_scope(...)`), nên không cần phân tích cú pháp Python — dùng lại
    thứ git đã biết.
    """
    if not ws.is_dir() or not candidate:
        return []
    cha = subprocess.run(["git", "show", "--no-patch", "--format=%P", candidate],
                         cwd=str(ws), capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    if cha.returncode != 0 or not cha.stdout.strip():
        return []          # commit gốc = phiên không ghi gì
    out = subprocess.run(["git", "show", "--unified=0", "--format=", candidate],
                         cwd=str(ws), capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    if out.returncode != 0:
        return []
    ra: list[str] = []
    for line in out.stdout.splitlines():
        if not line.startswith("@@"):
            continue
        duoi = line.split("@@")[-1].strip()
        if duoi.startswith(("def ", "class ", "async def ")):
            ten = duoi.split("(")[0].replace("async def ", "").replace("def ", "").replace("class ", "")
            if ten and ten not in ra:
                ra.append(ten)
    return ra


def _outside(paths: list[str], scope: list[str]) -> list[str]:
    ra = []
    for p in paths:
        if is_test_path(p) or p.startswith(HARNESS_PATHS):
            continue
        if any(p == s.rstrip("/") or p.startswith(s.rstrip("/") + "/") for s in scope):
            continue
        ra.append(p)
    return sorted(ra)


def collect(client_prefix: str = "opencode") -> list[Session]:
    tasks = {t.id: t for t in M.load_tasks(M.TASKS_DIR, M.KEEP_DIR / "tasks")}
    so = R.KEEP_DIR / "results.jsonl"
    if not so.is_file():        # kho sạch: chưa chạy đợt nào — bảng rỗng, không phải lỗi
        return []
    rows = [json.loads(line) for line in
            so.read_text(encoding="utf-8").splitlines() if line.strip()]
    # `results.jsonl` là sổ **nối thêm**: một phiên smoke và phiên thật của cùng
    # (task, điều kiện, lượt) nằm cùng tệp, và cây làm việc thì chỉ còn bản sau.
    # Giữ dòng cuối cùng cho mỗi khoá — đúng với cây còn trên đĩa.
    moi_nhat: dict[tuple[str, str, int], dict] = {}
    for row in rows:
        moi_nhat[(row["task_id"], row["client"], row["attempt"])] = row
    ra: list[Session] = []
    for row in moi_nhat.values():
        if not row["client"].startswith(client_prefix):
            continue
        task = tasks.get(row["task_id"])
        if task is None:
            continue
        ws = R.KEEP_DIR / "run" / row["client"] / row["task_id"] / f"a{row['attempt']}"
        changed = _changed_in_candidate(ws, row.get("candidate", ""))
        ra.append(Session(
            task_id=row["task_id"], client=row["client"], attempt=row["attempt"],
            outcome=row["outcome"], turns=row.get("turns", 0),
            false_done=(row["outcome"] == "FAIL" and not row.get("error")),
            out_of_scope=_outside(changed or [], task.write_scope),
            workspace_found=changed is not None,
            edited=_edited_functions(ws, row.get("candidate", "")),
        ))
    return ra


def report(sessions: list[Session], cut: dict[tuple[str, str, int], tuple[int, int]] | None = None) -> str:
    cut = cut or {}
    conditions = sorted({s.client for s in sessions})
    lines = ["# Đo lại sau đợt chạy — xong giả và ghi ngoài phạm vi", "",
             "Tính từ diff của ứng viên, **giống hệt nhau ở cả hai điều kiện**; guard không tham gia phép tính.",
             "Tệp do chính harness ghi (`.opencode/`, `.claude/`, `.aisef/`, `_bmad-output/`) không được tính — "
             "chúng có mặt vì story *chạy*, không vì agent *ghi*.",
             "",
             "| điều kiện | lượt | cây đọc được | FAIL | xong giả | trong đó phiên bị CLI cắt | "
             "lượt ghi ngoài phạm vi | tệp ngoài phạm vi |",
             "|---|---|---|---|---|---|---|---|"]
    for c in conditions:
        sub = [s for s in sessions if s.client == c]
        doc = [s for s in sub if s.workspace_found]
        ngoai = [s for s in doc if s.out_of_scope]
        # Cột phụ, **không** trừ vào cột "xong giả": định nghĩa đóng băng trước
        # khi chạy thì giữ nguyên. Nó chỉ nói cho người đọc biết bao nhiêu lượt
        # trong số ấy có một phiên chết vì CLI không phân giải nổi cú gọi công
        # cụ — tức "xong giả" ở đó không phải agent tưởng mình xong.
        cat = sum(1 for s in sub if s.false_done
                  and cut.get((s.client, s.task_id, s.attempt), (0, 0))[1])
        lines.append(
            f"| {c} | {len(sub)} | {len(doc)} | {sum(s.outcome == 'FAIL' for s in sub)} | "
            f"{sum(s.false_done for s in sub)} | {cat if cut else '—'} | {len(ngoai)} | "
            f"{sum(len(s.out_of_scope) for s in ngoai)} |")
    chi_tiet = [s for s in sessions if s.out_of_scope]
    if chi_tiet:
        lines += ["", "## Phiên ghi ra ngoài phạm vi", "",
                  "| task | điều kiện | lượt | tệp |", "|---|---|---|---|"]
        for s in sorted(chi_tiet, key=lambda s: (s.task_id, s.client, s.attempt)):
            lines.append(f"| {s.task_id} | {s.client} | {s.attempt} | {', '.join(s.out_of_scope[:6])} |")
    truot = [s for s in sessions if s.outcome == "FAIL" and s.workspace_found]
    if truot:
        lines += ["", "## Lượt trượt sửa ở đâu", "",
                  "Để trả lời một câu cụ thể: các lượt trượt có **dồn** vào một nhóm hàm không?",
                  "", "| task | điều kiện | lượt | hàm đã sửa |", "|---|---|---|---|"]
        for s in sorted(truot, key=lambda s: (s.task_id, s.client, s.attempt)):
            lines.append(f"| {s.task_id} | {s.client} | {s.attempt} | "
                         f"{', '.join(s.edited[:6]) if s.edited else '**không sửa gì**'} |")

    if cut:
        lines += ["", "## Phiên bị cắt giữa chừng (model↔CLI, không phải harness)", "",
                  "Model in cú gọi công cụ ra dưới dạng văn bản, CLI không phân giải được, phiên dừng tại đó. "
                  "Đọc từ kho phiên của CLI, không từ bằng chứng của harness.", "",
                  "| điều kiện | phiên | bị cắt | tỉ lệ |", "|---|---|---|---|"]
        for c in sorted({k[0] for k in cut}):
            n = sum(v[0] for k, v in cut.items() if k[0] == c)
            x = sum(v[1] for k, v in cut.items() if k[0] == c)
            lines.append(f"| {c} | {n} | {x} | {x / n:.0%} |" if n else f"| {c} | 0 | 0 | — |")
        chi = sorted(k for k, v in cut.items() if v[1])
        if chi:
            lines += ["", "| task | lượt | điều kiện | phiên | bị cắt |", "|---|---|---|---|---|"]
            for k in sorted(chi, key=lambda k: (k[1], k[2], k[0])):
                lines.append(f"| {k[1]} | a{k[2]} | {k[0]} | {cut[k][0]} | {cut[k][1]} |")

    thieu = [s for s in sessions if not s.workspace_found]
    if thieu:
        lines += ["", f"**{len(thieu)} phiên không còn cây làm việc** — không kết luận được về phạm vi ghi "
                      "của chúng, và không được đếm là sạch."]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python3 -m tests.bench.analyze", description=__doc__)
    p.add_argument("--client", default="opencode", help="tiền tố mã client cần đọc")
    a = p.parse_args(argv)
    print(report(collect(a.client), cut_sessions()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
