"""Tự kiểm đường ống của đợt đo thật — **KHÔNG PHẢI MỘT KẾT QUẢ ĐO**.

Không một lượt gọi model nào xảy ra ở đây. `OpenCodeAdapter` được dựng với
``binary=`` trỏ thẳng vào một script giả trong thư mục tạm, nên `shutil.which`
không bao giờ tìm tới CLI thật — kể cả khi CLI thật có trên máy và đã đăng nhập.
Script giả phát một luồng JSON **đã ghi sẵn** đúng hình dạng mà `opencode run
--format json` phát ra (đo 2026-09-05, và số token lấy từ bằng chứng C-1b).

Nó chứng minh đúng phần đường ống mà một đợt đo thật phụ thuộc vào:

1. hai điều kiện gọi client với **cùng argv model** và **cùng đề bài từng byte**
   — bất cứ chênh lệch nào ở đây là một biến thứ hai, và bảng kết quả hết đọc
   được;
2. nhánh AISEF có `.claude/settings.json`, plugin guard trong `.opencode/`, và
   `AISEF_WRITE_SCOPE`/`AISEF_STORY_ID` **tới được tiến trình con**; nhánh trần
   không có cái nào trong ba thứ ấy;
3. token của `step_finish` đi từ luồng JSON vào `results.jsonl` — cột tiền của
   nhà cung cấp này là 0,00 nên token là đại lượng tài nguyên duy nhất còn lại;
4. phiên bị CLI cắt được xếp `infra` và **được chạy lại một lần**, không ăn mất
   một lượt của agent;
5. scorer (F2P/P2P trên test ẩn) vẫn chấm ra PASS cho bản sửa đúng và FAIL cho
   phiên không ghi gì — không sửa một dòng nào của scorer;
6. `MANIFEST.sha256` của bộ dữ liệu khớp từng byte.

Nó **không** chứng minh guard chặn được gì: script giả không chạy hook nào.
Bằng chứng cho việc ấy nằm ở `aisef/clients/opencode.py` (docstring, đo
2026-09-05) và ở bộ hợp quy — không ở đây.

    python3 -m tests.bench selfcheck
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from . import _mine as M
from . import _runner as R

#: Task rẻ nhất trong 12 task A-2 để tự kiểm: `tools.test` của nó là
#: `tests.test_runlog` (≈2 s), F2P=1, P2P=9. Đường ống giống hệt các task khác;
#: đắt hơn chỉ mua thêm thời gian chờ.
TASK_MAC_DINH = "bug-a2-multi-2"

#: Token của một phiên thật, đọc từ bằng chứng C-1b
#: (`.bench-c1b/run/opencode-bare/bug-a2-sec-1/a1`): vào 98 392 · ra 1 487 ·
#: cache đọc 581 444, trong khi `cost_usd` = 0,00. Dùng đúng số ấy để phép tự
#: kiểm chứng minh được điều cần chứng minh: 0,00 USD **không** phải miễn phí.
TOKEN = {"input": 98_392, "output": 1_487, "cache": {"read": 581_444, "write": 0}}

_FAKE = '''#!/usr/bin/env python3
"""`opencode` GIẢ — phát luồng JSON đã ghi sẵn. Không gọi model, không ra mạng.

`AISEF_SELFCHECK_MODE`: `fix` (áp gold) · `cut` (mọi phiên bị cắt) · `cut:2,4`
(chỉ phiên có số ấy bị cắt — số đọc từ tên cây làm việc `aN`/`sN`). Dạng thứ ba
để đợt tuyển cặp dựng được một cohort **trộn**: một tỉ lệ cắt 0 % hay 100 %
không kiểm được số học của tỉ lệ.
"""
import json, os, re, subprocess, sys

prompt = sys.stdin.read()
argv = sys.argv[1:]
ws = argv[argv.index("--dir") + 1]
log = os.environ.get("AISEF_SELFCHECK_LOG", "")
if log:
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"argv": argv, "dir": ws, "prompt": prompt,
                             "env": sorted(k for k in os.environ if k.startswith("AISEF_"))},
                            ensure_ascii=False) + "\\n")

def ev(o):
    o["sessionID"] = "selfcheck"
    print(json.dumps(o), flush=True)

ev({"type": "step_start", "part": {}})
che_do = os.environ.get("AISEF_SELFCHECK_MODE", "")
so_phien = re.sub(r"\\D", "", os.path.basename(ws.rstrip("/\\\\")))
if che_do == "cut" or (che_do.startswith("cut:") and so_phien in che_do[4:].split(",")):
    # Chữ ký phiên bị CLI cắt, đúng như đo trên C-1 § O-7: model in cú gọi công
    # cụ ra như văn bản thường, CLI không phân giải được, phiên dừng tại đó —
    # và CLI vẫn thoát 0.
    ev({"type": "text", "part": {"text": '<minimax:tool_call><invoke name="read">'}})
else:
    gold = os.environ.get("AISEF_SELFCHECK_GOLD", "")
    if gold:
        subprocess.run(["git", "apply", "--binary", gold], cwd=ws, check=False)
    ev({"type": "tool_use", "part": {"tool": "edit", "callID": "c1",
                                     "state": {"status": "completed", "input": {"filePath": "x"}}}})
    ev({"type": "text", "part": {"text": "đã sửa"}})
ev({"type": "step_finish", "part": {"tokens": TOKEN, "cost": 0}})
'''

BANNER = "KHÔNG PHẢI KẾT QUẢ ĐO — luồng phiên là fixture đã ghi sẵn, không model nào được gọi."


def _tien_ich_that() -> str:
    """Một dòng về CLI thật: có trên máy không, bản nào. `--version` không gọi
    model. Không tìm thấy thì đợt đo thật không chạy được, và biết trước thì
    đỡ hơn biết sau 6 giờ."""
    duong = shutil.which("opencode")
    if not duong:
        return "opencode KHÔNG có trên PATH — đợt đo thật sẽ không chạy được"
    try:
        ra = subprocess.run([duong, "--version"], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=30)
        return f"opencode thật: {duong} ({ra.stdout.strip() or ra.stderr.strip() or 'không nói bản'})"
    except (OSError, subprocess.SubprocessError) as e:
        return f"opencode thật: {duong} (không đọc được bản: {e})"


def run_selfcheck(task_id: str = TASK_MAC_DINH, model: str = "", out=sys.stdout) -> int:
    """Chạy đường ống thật với client giả; in bảng kiểm, trả 0 khi tất cả đạt."""
    from aisef.clients.opencode import OpenCodeAdapter

    tasks = {t.id: t for t in M.load_tasks(M.TASKS_DIR, M.KEEP_DIR / "tasks")}
    if task_id not in tasks:
        print(f"không có task {task_id!r}", file=sys.stderr)
        return 2
    task = tasks[task_id]
    kiem: list[tuple[bool, str]] = []

    def dat(ok: bool, ten: str) -> None:
        kiem.append((bool(ok), ten))

    dat(M.render_dataset_manifest(M.TASKS_DIR)
        == (M.TASKS_DIR / "MANIFEST.sha256").read_text(encoding="utf-8"),
        "MANIFEST.sha256 khớp từng byte — bộ dữ liệu không đổi")

    giu = R.KEEP_DIR
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        fake = tmp / "opencode"
        fake.write_text(_FAKE.replace("TOKEN", json.dumps(TOKEN)), encoding="utf-8")
        fake.chmod(0o755)
        log = tmp / "calls.jsonl"
        client = OpenCodeAdapter(binary=str(fake))
        R.KEEP_DIR = tmp / "bench"
        moi = {"AISEF_SELFCHECK_LOG": str(log),
               "AISEF_SELFCHECK_GOLD": str(task.dir / "gold.patch"),
               "AISEF_SELFCHECK_MODE": "fix"}
        cu = {k: os.environ.get(k) for k in moi}
        os.environ.update(moi)
        try:
            [a] = R.run(task, client, attempts=1, bare=False, model=model, note="selfcheck")
            [b] = R.run(task, client, attempts=1, bare=True, model=model, note="selfcheck")
            goi = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines()]
            ws_a = R.KEEP_DIR / "run" / "opencode" / task.id / "a1"
            ws_b = R.KEEP_DIR / "run" / "opencode-bare" / task.id / "a1"
            dat(len(goi) == 2, f"client được gọi đúng 2 lần ({len(goi)})")
            dat(goi[0]["argv"][:3] == ["run", "--format", "json"],
                f"argv của client: {' '.join(goi[0]['argv'][:3])}")
            dat(goi[0]["argv"][3:5] == ["--dir", str(ws_a)],
                "`--dir` trỏ vào cây làm việc của lượt, không vào kho ngoài")
            m_a = goi[0]["argv"][goi[0]["argv"].index("--model") + 1] if "--model" in goi[0]["argv"] else ""
            m_b = goi[1]["argv"][goi[1]["argv"].index("--model") + 1] if "--model" in goi[1]["argv"] else ""
            dat(m_a == m_b == model, f"cùng một model ở hai điều kiện ({m_a!r} vs {m_b!r})")
            dat(goi[0]["prompt"] == goi[1]["prompt"],
                f"đề bài giống nhau từng byte ({len(goi[0]['prompt'])} ký tự)")
            dat("AISEF_WRITE_SCOPE" in goi[0]["env"] and "AISEF_STORY_ID" in goi[0]["env"],
                "nhánh AISEF: AISEF_WRITE_SCOPE + AISEF_STORY_ID tới được tiến trình con")
            dat("AISEF_WRITE_SCOPE" not in goi[1]["env"] and "AISEF_STORY_ID" not in goi[1]["env"],
                "nhánh trần: không có biến AISEF_* nào của guard")
            # Với client `opencode`, `compile_for` ghi **một** tệp:
            # `.opencode/plugin/aisef-guard.ts` (`.claude/settings.json` là của
            # Claude Code, không phải của CLI này — đo trong chính lần tự kiểm
            # đầu tiên, và đây là chỗ duy nhất guard tới được agent).
            plugin = ws_a / ".opencode" / "plugin" / "aisef-guard.ts"
            dat(plugin.is_file() and "aisef" in plugin.read_text(encoding="utf-8"),
                "nhánh AISEF: plugin guard `.opencode/plugin/aisef-guard.ts` có trong cây")
            dat(not (ws_b / ".opencode").exists()
                and not (ws_b / "_bmad-output" / "compile-report.json").exists(),
                "nhánh trần: không plugin, không compile-report")
            dat(a.outcome == R.PASS and a.f2p_pass == a.f2p_total,
                f"scorer chấm bản sửa đúng thành PASS ({a.outcome} {a.f2p_pass}/{a.f2p_total})")
            dat(b.outcome == R.PASS, f"nhánh trần cùng bản sửa cũng PASS ({b.outcome})")
            tong = sum(TOKEN[k] for k in ("input", "output")) + sum(TOKEN["cache"].values())
            dat(a.tokens == b.tokens == tong and not a.cost_usd,
                f"token vào sổ: {a.tokens} mỗi lượt, trong khi $ = {a.cost_usd:.2f}")
            dat((a.exit_status, a.infra_retries) == ("ok", 0),
                f"phiên sạch ghi `ok`, 0 lần chạy lại ({a.exit_status}, {a.infra_retries})")

            os.environ["AISEF_SELFCHECK_MODE"] = "cut"
            log.write_text("", encoding="utf-8")
            [c] = R.run(task, client, attempts=1, bare=False, model=model, note="selfcheck")
            cat = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines()]
            dat(len(cat) == 2, f"phiên bị cắt được chạy lại đúng 1 lần ({len(cat)} phiên)")
            dat(c.exit_status == "infra" and c.infra_retries == 1,
                f"lượt ấy ghi `{c.exit_status}` + {c.infra_retries} lần chạy lại, "
                "không lẫn với lượt agent sửa sai")
            dat(c.outcome == R.FAIL, f"phiên không ghi gì vẫn FAIL ({c.outcome}) — scorer không nới")

            so = [json.loads(l) for l in
                  (R.KEEP_DIR / "results.jsonl").read_text(encoding="utf-8").splitlines()]
            dat(all("tokens_in" in r and "exit_status" in r for r in so),
                "results.jsonl mang token + trạng thái thoát (qua JSON, không chỉ trong bộ nhớ)")
            bao_cao = R.report([a, b, c], list(tasks.values()))
            dat("vắng mặt giá" in bao_cao,
                "báo cáo nói rõ 0,00 USD là vắng mặt giá, không phải miễn phí")
        finally:
            R.KEEP_DIR = giu
            for k, v in cu.items():
                os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)

    hong = [t for ok, t in kiem if not ok]
    print(f"# Tự kiểm đường ống bench — {task_id}\n\n{BANNER}\n", file=out)
    print(_tien_ich_that() + "\n", file=out)
    for ok, ten in kiem:
        print(f"{'✓' if ok else '✗'} {ten}", file=out)
    print(f"\n{len(kiem) - len(hong)}/{len(kiem)} đạt. {BANNER}", file=out)
    return 1 if hong else 0
