#!/usr/bin/env python3
"""Bản đồ danh tính tiêu chí ↔ phép thử của một corpus — trước/sau lỗi 159.

Vì sao cần một báo cáo riêng thay vì đọc cổng: cổng chấm **một** story ở **một**
lượt, và `aisef gate --replay` chấm lại bằng chính các tham số đã ghi lúc ấy
(ADR-005 V4) — nên một tiêu chí bị sửa **sau khi** story đã trộn là vô hình với
cả hai. Đó đúng là hình dạng lỗi 159 trên marks-cli. Câu hỏi duy nhất trả lời
được nó là câu hỏi **trạng thái hiện tại**: kế hoạch hôm nay so với tên phép thử
hôm nay.

    python3 validation/ac_identity_report.py ~/Downloads/projects/marks-cli
    python3 validation/ac_identity_report.py <corpus> --json

Bốn phép dò, tất cả từ `aisef.control.acceptance` — không dựng bản thứ hai:

* `missing`    — tiêu chí không có phép thử nào mang mã của nó
* `orphans`    — mã trong tên phép thử mà **không còn** tiêu chí nào mang
* `overloaded` — một phép thử mang **hai** mã của cùng một story
* `identities` — vân tay nội dung từng tiêu chí, để so hai thời điểm

Không gọi model, không sửa gì, chỉ đọc.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.control.acceptance import (  # noqa: E402
    identities,
    missing,
    orphans,
    overloaded,
)

#: Tên phép thử đọc từ **mã nguồn test**, không từ bằng chứng đã ghi: bằng chứng
#: mang tên lúc lượt ấy chạy, mà câu hỏi ở đây là hôm nay hai đầu có khớp không.
TEST_NAME = re.compile(r"""(?:test|it)\s*\(\s*["'`]([^"'`]+)["'`]""")
TEST_GLOBS = ("tests/**/*.test.js", "tests/**/*.test.ts", "tests/**/*.spec.js",
              "test/**/*.test.js", "tests/**/test_*.py", "tests/**/*_test.py")


def test_names(project: Path) -> list[str]:
    names: list[str] = []
    seen: set[Path] = set()
    for pat in TEST_GLOBS:
        for f in project.glob(pat):
            if f in seen or not f.is_file():
                continue
            seen.add(f)
            text = f.read_text(encoding="utf-8", errors="replace")
            names += TEST_NAME.findall(text)
            # pytest: tên hàm là tên phép thử
            names += [m for m in re.findall(r"(?m)^\s*def (test_\w+)", text)]
    return names


def scan(project: Path) -> dict:
    root = project / "_bmad-output"
    idx = json.loads((root / "stories.index.json").read_text(encoding="utf-8"))
    names = test_names(project)
    out = {"corpus": str(project), "test_names_read": len(names), "stories": {}}
    for s in idx.get("stories", []):
        sid = s["id"]
        crit = [str(c) for c in (s.get("acceptance_criteria") or [])]
        n = len(crit)
        out["stories"][sid] = {
            "criteria": n,
            "identities": identities(sid, crit),
            "missing": missing(sid, n, names),
            "orphans": orphans(sid, n, names),
            "overloaded": overloaded(sid, names),
        }
    return out


def clean(rep: dict) -> bool:
    return all(not (v["missing"] or v["orphans"] or v["overloaded"])
               for v in rep["stories"].values())


def render(rep: dict) -> str:
    lines = [f"# Bản đồ danh tính tiêu chí — {Path(rep['corpus']).name}", "",
             f"{rep['test_names_read']} tên phép thử đọc từ mã nguồn test.", "",
             "| story | tiêu chí | thiếu phép thử | mã mồ côi | phép thử mang 2 mã |",
             "|---|---:|---|---|---|"]
    for sid, v in rep["stories"].items():
        lines.append(
            f"| {sid} | {v['criteria']} | {v['missing'] or '—'} | "
            f"{v['orphans'] or '—'} | {list(v['overloaded']) or '—'} |")
    lines += ["", "**sạch**" if clean(rep) else "**CÒN SAI LỆCH**", ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--baseline", default="",
                    help="tệp JSON của một lần chạy trước — in phần **đổi**")
    a = ap.parse_args()
    rep = scan(Path(a.corpus).expanduser())
    if a.baseline:
        before = json.loads(Path(a.baseline).read_text(encoding="utf-8"))
        print("## Trước → sau\n")
        for sid, now in rep["stories"].items():
            was = (before.get("stories") or {}).get(sid)
            if was is None:
                print(f"- {sid}: **mới**")
                continue
            for k in ("missing", "orphans", "overloaded"):
                if was[k] != now[k]:
                    print(f"- {sid}.{k}: {was[k] or '—'} → {now[k] or '—'}")
            doi = sorted(k for k in was["identities"].keys() & now["identities"].keys()
                         if was["identities"][k] != now["identities"][k])
            if doi:
                print(f"- {sid}: danh tính đổi ở {', '.join(doi)} — "
                      f"phép thử mang mã ấy không còn chứng minh tiêu chí cũ")
        print()
    print(json.dumps(rep, indent=1, ensure_ascii=False) if a.json else render(rep))
    return 0 if clean(rep) else 1


if __name__ == "__main__":
    raise SystemExit(main())
