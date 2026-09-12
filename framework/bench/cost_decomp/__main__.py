"""Đọc `_bmad-output/evidence/*.jsonl` của một dự án, in bảng Markdown."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

#: `STORY-01-02#3` → lượt 3 của vai developer; hai vai còn lại có hậu tố riêng.
_DEV = re.compile(r"#(\d+)$")


def phan_vai(name: str) -> str:
    if name.endswith("-review"):
        return "reviewer"
    if name.endswith("-security"):
        return "security"
    if _DEV.search(name):
        return "developer"
    return "khác"


def doc(root: Path) -> list[dict]:
    """Mọi sự kiện, theo thứ tự trong từng tệp story."""
    ra = []
    for p in sorted((root / "_bmad-output" / "evidence").glob("*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                d["_story"] = p.stem
                ra.append(d)
    return ra


def _tok(d: dict) -> tuple[int, int, int]:
    t = d.get("tokens") or {}
    return (t.get("input", 0) or 0, t.get("output", 0) or 0, t.get("cache_read", 0) or 0)


def theo_vai(events: list[dict]) -> dict[str, dict]:
    ra: dict[str, dict] = defaultdict(lambda: {"phien": 0, "turn": 0, "in": 0, "out": 0, "cache": 0})
    for d in events:
        if d["kind"] != "agent_run":
            continue
        o = ra[phan_vai(d.get("name", ""))]
        i, out, cache = _tok(d)
        o["phien"] += 1
        o["turn"] += (d.get("detail") or {}).get("turns", 0)
        o["in"] += i
        o["out"] += out
        o["cache"] += cache
    return dict(ra)


def theo_ket_cuc(events: list[dict]) -> dict[str, dict]:
    """Token của mỗi phiên, chia theo **cổng phán gì về lượt chứa nó**.

    Một lượt bị cổng chặn là một lượt phải làm lại: token của nó không mua được
    hành vi nào đã nghiệm thu. Đây chính là phần "tiêu vào đâu" mà E4 hỏi.

    Gán theo **thứ tự sự kiện**, không theo số lượt: một story chạy lại nhiều
    lần thì "lượt 1" xuất hiện nhiều lần với phán quyết khác nhau, nên khoá theo
    số lượt sẽ dán nhãn của lần chạy sau lên phiên của lần chạy trước.
    """
    ra: dict[str, dict] = defaultdict(lambda: {"phien": 0, "in": 0, "out": 0, "cache": 0})

    def cong(khoa: str, cho: list[dict]) -> None:
        o = ra[khoa]
        for d in cho:
            i, out, cache = _tok(d)
            o["phien"] += 1
            o["in"] += i
            o["out"] += out
            o["cache"] += cache

    theo_story: dict[str, list[dict]] = defaultdict(list)
    for d in events:
        if d["kind"] == "agent_run":
            theo_story[d["_story"]].append(d)
        elif d["kind"] == "note" and d.get("name") == "gate:verdict":
            cong("lượt cổng cho qua" if d["ok"] else "lượt bị cổng chặn",
                 theo_story.pop(d["_story"], []))
    for con_lai in theo_story.values():
        cong("chưa tới cổng", con_lai)
    return dict(ra)


def ly_do_chan(events: list[dict]) -> Counter:
    c: Counter = Counter()
    for d in events:
        if d["kind"] == "note" and d.get("name") == "gate:verdict" and not d["ok"]:
            for f in (d.get("detail") or {}).get("failures", []) or ["(không ghi tên)"]:
                c[f] += 1
    return c


def _bang(ten: str, data: dict[str, dict], cot: str) -> list[str]:
    tong_in = sum(v["in"] for v in data.values()) or 1
    ra = [f"## {ten}", "", f"| {cot} | phiên | token vào | token ra | cache đọc | % token vào |",
          "|---|---|---|---|---|---|"]
    for k, v in sorted(data.items(), key=lambda kv: -kv[1]["in"]):
        ra.append(f"| {k} | {v['phien']} | {v['in']:,} | {v['out']:,} | {v['cache']:,} | "
                  f"{v['in'] / tong_in:.0%} |")
    return ra + [""]


def report(root: Path) -> str:
    events = doc(root)
    if not events:
        return f"Không có bằng chứng nào dưới `{root}/_bmad-output/evidence`."
    stories = {d["_story"] for d in events}
    chi_phi = sum(d.get("cost_usd") or 0 for d in events)
    lines = [f"# Phân rã chi phí — `{root.name}`", "",
             f"{len(events):,} sự kiện · {len(stories)} story · "
             f"nhà cung cấp báo chi phí **{chi_phi:.2f} USD** "
             f"({'có số' if chi_phi else 'không trả về chi phí — đếm token thay thế'}).", ""]
    lines += _bang("Theo vai", theo_vai(events), "vai")
    lines += _bang("Theo phán quyết của cổng cho lượt đó", theo_ket_cuc(events), "lượt")
    ly_do = ly_do_chan(events)
    if ly_do:
        lines += ["## Cổng chặn vì gì", "", "| mục kiểm | số lần chặn |", "|---|---|"]
        lines += [f"| {k} | {v} |" for k, v in ly_do.most_common()]
        lines += [""]
    tv = theo_vai(events)
    vao = sum(v["in"] for v in tv.values())
    tong_ra = sum(v["out"] for v in tv.values())
    lines += ["## Quy ra tiền", "",
              "Không có giá thật thì không in ra số tiền giả. Công thức, với `p` = giá 1 triệu "
              "token vào và `q` = giá 1 triệu token ra:", "",
              f"    chi phí ≈ {vao / 1e6:.2f} × p + {tong_ra / 1e6:.3f} × q     (toàn dự án)",
              f"    chi phí mỗi story ≈ {vao / 1e6 / len(stories):.2f} × p + "
              f"{tong_ra / 1e6 / len(stories):.3f} × q", "",
              "Token đọc từ cache tính riêng vì phần lớn bảng giá tính nó rẻ hơn nhiều; "
              f"dự án này đọc cache {sum(v['cache'] for v in tv.values()):,} token."]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python3 -m framework.bench.cost_decomp", description=__doc__)
    p.add_argument("root", type=Path, help="thư mục dự án (chứa `_bmad-output/`)")
    print(report(p.parse_args(argv).root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
