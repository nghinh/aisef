#!/usr/bin/env python3
"""Tính lại định mức người rà soát **sau lỗi 158** — OLD vs NEW, có ngày.

Vì sao phải tính lại: lỗi 158 đưa tỉ lệ phân giải dòng chặn thật từ **0/177**
lên **116/177**. Mọi con số O1 đã công bố đều được tính trong lúc `Finding.id`
**không** tính được trên đầu ra thật, nên không con nào được phép mặc định là
không đổi. Đây là việc đọc lại bằng chứng đã có trên đĩa — không một lượt gọi
model nào.

Ba luật, theo quyết định của chủ dự án (Adjustment 3):

1. **Không ghi đè báo cáo O1 lịch sử.** `docs/handoff/o1-reviewer-qualification.md`
   và mục O1 của ADR-009 giữ nguyên chữ; kết quả ở đây là *phụ lục có ngày*.
2. **Không tinh chỉnh parser để cải thiện con số.** Nếu số xấu đi thì ghi là xấu đi.
3. Quyết định miễn trừ G2.4b phải dùng số **mới**, không dùng 36,8 % cũ, trừ khi
   phép tính lại tự xác nhận lại đúng con ấy.

    python3 validation/recompute_reviewer_qual.py                 # bốn corpus todo*
    python3 validation/recompute_reviewer_qual.py --with-marks    # thêm marks-cli

Lưu ý về mẫu số: bảng O1 công bố tính trên **bốn** corpus `todo*`. Thêm
`marks-cli` đổi mẫu số, nên nó là một cột riêng, không gộp vào — so cái khác mẫu
số rồi gọi là "đã đổi" là tự tạo ra một thay đổi không có.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.control.findings import SOURCE_REVIEWER, Finding  # noqa: E402
from aisef.control.reviewer_qual import (  # noqa: E402
    classify,
    rates,
    read_judgements,
)

PROJECTS = Path.home() / "Downloads" / "projects"
TODO_CORPORA = ("todo-cli", "todo-e2e", "todo-oc", "todo")

#: Con số O1 **đã công bố**, trích từ `docs/ADR-009-…md` §O1 và
#: `docs/handoff/o1-reviewer-qualification.md`. Giữ nguyên văn ở đây để phép so
#: là so với cái đã in ra, không so với cái tôi nhớ.
PUBLISHED = {
    #: `rates()["total"]` là **số phiên đã ghi** (145), không phải số phiên
    #: *chấm được* (127). Bảng O1 in cả hai; ở đây so đúng khoá scorer trả về,
    #: vì một ô "—" trong bảng so sánh đọc thành "không kiểm được", còn sự thật
    #: là tôi đặt sai tên khoá.
    "total": 145,
    "undecided": 18,
    "blocks scored": 57,
    "false block": 6,
    "false block rate": 0.105,
    "passes scored": 70,
    "miss": 27,
    "miss rate": 0.386,
    "same-tree consecutive pairs": 20,
    "same-tree verdict reversals": 11,
    "block uncorroborated": 21,
}


def parse_rate(roots: dict[str, Path]) -> dict:
    """Bao nhiêu dòng chặn đã ghi phân giải được — số mà lỗi 158 đổi."""
    total = parsed = 0
    for root in roots.values():
        ev = root / "evidence"
        if not ev.is_dir():
            continue
        for f in ev.glob("*.jsonl"):
            for ln in f.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    e = json.loads(ln)
                except Exception:
                    continue
                if e.get("kind") == "tool_run" and e.get("name") == "review":
                    for item in (e.get("detail") or {}).get("findings") or []:
                        if isinstance(item, str):
                            total += 1
                            parsed += len(Finding.parse_lines(
                                [item], source=SOURCE_REVIEWER, trust="reviewer"))
    return {"blocking_lines": total, "parsed_as_canonical": parsed}


def score(roots: dict[str, Path]) -> dict:
    scored = []
    for name, root in roots.items():
        scored.extend(classify(read_judgements(root, project=name)))
    return rates(scored)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-marks", action="store_true",
                    help="thêm marks-cli (đổi mẫu số — in thành cột riêng)")
    ap.add_argument("--out", default="docs/O1-RECOMPUTE-AFTER-158.md")
    a = ap.parse_args()

    names = list(TODO_CORPORA) + (["marks-cli"] if a.with_marks else [])
    roots = {n: PROJECTS / n / "_bmad-output" for n in names
             if (PROJECTS / n / "_bmad-output").is_dir()}
    if not roots:
        print("không tìm thấy corpus nào — không kết luận gì", file=sys.stderr)
        return 2

    new = score(roots)
    pr = parse_rate(roots)

    rows = []
    for key, old in PUBLISHED.items():
        got = new.get(key)
        if got is None:
            rows.append((key, old, "—", "phép tính mới không trả khoá này"))
            continue
        if isinstance(old, float):
            moved = abs(float(got) - old) > 0.005
        else:
            moved = int(got) != int(old)
        rows.append((key, old, got, "**ĐỔI**" if moved else "không đổi"))

    lines = [
        "# O1 tính lại sau lỗi 158 — phụ lục có ngày",
        "",
        f"Tính ngày **{date.today().isoformat()}**, corpus: {', '.join(sorted(roots))}.",
        "Sinh lại bằng `python3 validation/recompute_reviewer_qual.py`"
        + (" --with-marks" if a.with_marks else "") + ". Không gọi model.",
        "",
        "> **Đây là phụ lục, không phải bản thay thế.** "
        "`docs/handoff/o1-reviewer-qualification.md` và mục O1 của ADR-009 giữ nguyên "
        "chữ — luật của kho này là bản ghi có ngày thì không sửa lại sau.",
        "",
        "## Vì sao phải tính lại",
        "",
        "Lỗi 158: `Finding._LINE_RE` chỉ nhận dạng canonical `[high] tệp:dòng thân`, "
        "còn prompt dặn người rà soát viết `[block] đường/dẫn:dòng — thân`. Trước khi "
        "sửa, **0** dòng chặn đã ghi phân giải được, nên `Finding.id` chưa từng được "
        "tính trên đầu ra thật.",
        "",
        f"Trên corpus này, sau khi sửa: **{pr['parsed_as_canonical']} / "
        f"{pr['blocking_lines']}** dòng chặn phân giải được.",
        "",
        "## OLD (đã công bố) vs NEW (parser đã sửa)",
        "",
        "| số | đã công bố | tính lại | |",
        "|---|---:|---:|---|",
    ]
    for key, old, got, verdict in rows:
        lines.append(f"| {key} | {old} | {got} | {verdict} |")

    moved_any = [r for r in rows if r[3].startswith("**")]
    lines += [
        "",
        "## Kết luận",
        "",
        (f"**{len(moved_any)} số đổi.** " if moved_any
         else "**Không số nào đổi.** ")
        + ("Quyết định miễn trừ G2.4b phải dùng cột *tính lại*, không dùng con số cũ."
           if moved_any else
           "Phép tính lại tự xác nhận lại các con số đã công bố: lỗi 158 đổi cách "
           "`Finding.id` được tính, nhưng các tỉ lệ O1 không đọc qua đường ấy — "
           "chúng đọc `note:review:verdict` và bảng cổng. Điều này đáng ghi ra, vì "
           "'không đổi' chỉ có nghĩa khi đã đi đo."),
        "",
        "Mỗi con số ở trên tính lại được bất cứ lúc nào; chúng không phụ thuộc một "
        "lượt gọi model nào.",
    ]
    out = ROOT / a.out
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {a.out}")
    print(f"  parse rate: {pr['parsed_as_canonical']}/{pr['blocking_lines']}")
    for key, old, got, verdict in rows:
        if verdict.startswith("**"):
            print(f"  MOVED {key}: {old} -> {got}")
    if not moved_any:
        print("  no published number moved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
