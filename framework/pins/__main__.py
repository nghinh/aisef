"""So `references/PINS.md` với HEAD hiện tại trên GitHub.

    python3 -m framework.pins                 # dùng PINS.md trong kho
    python3 -m framework.pins --offline       # chỉ phân tích bảng, không gọi mạng

Thoát 1 khi có kho đã chạy tiếp — để job hằng tháng hiện đỏ, chứ không im.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

GOC = Path(__file__).resolve().parents[2]
PINS = GOC / "references" / "PINS.md"
#: Danh mục **được phát hành cùng gói**: nó quyết định máy người dùng clone cái
#: gì. Đây mới là nguồn skill thật; `PINS.md` chỉ là bản ghi clone để nghiên cứu.
CATALOG = GOC / "aisef" / "kit" / "catalog.json"
#: | tên | https://github.com/chu/kho | `sha` | ngày | nhánh |
_DONG = re.compile(
    r"^\|\s*(?P<ten>[^|]+?)\s*\|\s*(?P<url>https://github\.com/[^\s|]+?)\s*\|\s*`(?P<sha>[0-9a-f]{7,40})`"
    r"\s*\|[^|]*\|\s*(?P<nhanh>[\w./-]+)\s*\|")


def doc_pins(text: str) -> list[dict]:
    """Mỗi dòng bảng ghim → {ten, url, sha, nhanh}. Dòng khác bỏ qua."""
    ra = []
    for line in text.splitlines():
        m = _DONG.match(line.strip())
        if m:
            d = m.groupdict()
            d["ten"] = d["ten"].split(" (")[0]          # "playwright-monorepo (sparse: …)"
            d["kho"] = "/".join(d["url"].rstrip("/").split("/")[-2:])
            ra.append(d)
    return ra


def head_tren_github(kho: str, nhanh: str = "", *, token: str = "", timeout: float = 15.0) -> str:
    """SHA của HEAD nhánh, hoặc chuỗi rỗng khi không hỏi được.

    Nhánh rỗng nghĩa là "nhánh mặc định của kho" — danh mục phát hành ghim
    commit chứ không ghim nhánh.
    """
    duong = f"commits/{nhanh}" if nhanh else "commits?per_page=1"
    req = urllib.request.Request(
        f"https://api.github.com/repos/{kho}/{duong}",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "aisef-pins"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:      # noqa: S310 — URL cố định
            d = json.loads(r.read().decode("utf-8"))
        return str((d[0] if isinstance(d, list) else d).get("sha", "")) if d else ""
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return ""


def doc_catalog(text: str) -> list[dict]:
    """Nguồn skill trong danh mục phát hành → cùng dạng bản ghi như `doc_pins`.

    Danh sách này **không gõ tay**: gõ tay thì nó trôi khỏi danh mục thật, và
    một nguồn skill rơi khỏi danh sách là một nguồn không ai canh.
    """
    d = json.loads(text)
    ra = []
    for e in (d.get("sources") if isinstance(d, dict) else d) or []:
        url = str(e.get("repo", "")).rstrip("/")
        if not url.startswith("https://github.com/"):
            continue
        ra.append({"ten": str(e.get("id", "")) or url.split("/")[-1], "url": url,
                   "sha": str(e.get("commit", "")), "nhanh": "",
                   "kho": "/".join(url.split("/")[-2:]), "skill": True})
    return ra


def nguon(pins_text: str, catalog_text: str) -> list[dict]:
    """Danh mục phát hành trước, bản ghi nghiên cứu sau; khoá theo `owner/repo`.

    Một kho có mặt ở cả hai chỗ chỉ xuất hiện một lần, và luôn mang cờ `skill`
    của danh mục — vì đó là bản mà máy người dùng thật sự clone.
    """
    ra: dict[str, dict] = {}
    for m in doc_catalog(catalog_text):
        ra[m["kho"]] = m
    for m in doc_pins(pins_text):
        ra.setdefault(m["kho"], {**m, "skill": False})
    return list(ra.values())


def so_sanh(ghim: list[dict], hien_tai: dict[str, str]) -> list[dict]:
    """Gắn `head` và `trang_thai` vào từng mục đã ghim.

    Ba trạng thái, cố ý tách "không hỏi được" khỏi "đứng yên": một lần mạng hỏng
    mà báo "đứng yên" là đúng kiểu im lặng nguy hiểm nhất.
    """
    ra = []
    for m in ghim:
        head = hien_tai.get(m["kho"], "")
        if not head:
            tt = "không hỏi được"
        elif head.startswith(m["sha"]) or m["sha"].startswith(head):
            tt = "đứng yên"
        else:
            tt = "đã chạy tiếp"
        ra.append({**m, "head": head, "trang_thai": tt})
    return ra


def bao_cao(muc: list[dict]) -> str:
    chay = [m for m in muc if m["trang_thai"] == "đã chạy tiếp"]
    hong = [m for m in muc if m["trang_thai"] == "không hỏi được"]
    lines = ["# Kho tham chiếu đã ghim", "",
             f"{len(muc)} kho · **{len(chay)} đã chạy tiếp** · {len(hong)} không hỏi được", "",
             "| kho | nguồn skill | ghim | HEAD | |", "|---|---|---|---|---|"]
    for m in sorted(muc, key=lambda m: (m["trang_thai"] != "đã chạy tiếp",
                                        not m.get("skill"), m["ten"])):
        dau = {"đã chạy tiếp": "⚠", "đứng yên": "✅", "không hỏi được": "○"}[m["trang_thai"]]
        lines.append(f"| {m['ten']} | {'có' if m.get('skill') else '—'} | `{m['sha'][:12]}` | "
                     f"`{m['head'][:12] or '—'}` | {dau} {m['trang_thai']} |")
    if chay:
        lines += ["", "Kho đã chạy tiếp thì kết luận đọc từ bản cũ **vẫn đúng với bản cũ** — "
                      "nhưng phần mới chưa ai đọc."]
    skill_chay = [m["ten"] for m in chay if m.get("skill")]
    if skill_chay:
        lines += ["", f"**Nguồn skill đã chạy tiếp: {', '.join(skill_chay)}.** Phần văn bản mới "
                      "sẽ được đọc vào phiên agent mà chưa qua lớp quét tiêm prompt. Nâng "
                      "ghim trong `aisef/kit/catalog.json` **chỉ sau khi** chạy lại "
                      "`aisef skill --scan` (tốn tiền, cần khoá: việc của người)."]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python3 -m framework.pins", description=__doc__)
    p.add_argument("--pins", type=Path, default=PINS)
    p.add_argument("--catalog", type=Path, default=CATALOG)
    p.add_argument("--offline", action="store_true", help="không gọi mạng; chỉ in bảng đã ghim")
    a = p.parse_args(argv)
    pins_text = a.pins.read_text(encoding="utf-8") if a.pins.is_file() else ""
    ghim = nguon(pins_text, a.catalog.read_text(encoding="utf-8"))
    if not ghim:
        print(f"Không đọc được mục ghim nào trong {a.catalog} hay {a.pins}", file=sys.stderr)
        return 2
    token = os.environ.get("GITHUB_TOKEN", "")
    hien_tai = {} if a.offline else {
        m["kho"]: head_tren_github(m["kho"], m["nhanh"], token=token) for m in ghim}
    muc = so_sanh(ghim, hien_tai)
    print(bao_cao(muc))
    return 1 if any(m["trang_thai"] == "đã chạy tiếp" and m.get("skill") for m in muc) else 0


if __name__ == "__main__":
    raise SystemExit(main())
