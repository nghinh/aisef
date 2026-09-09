"""Mỏ task cho bench (ADR-005 V8) — hai mỏ sẵn có, không repo nào có.

**(a) Story e9 đã `done`.** ``base`` = `test:baseline.parent` (ADR-004 R9)
khi mốc ấy ghi **trước** lượt developer đầu; story chạy trước R9 (01-01…07)
thì lấy commit cuối trên `main` trước lúc lượt đầu bắt đầu (`at − duration`
của `agent_run`). Không lấy cha của ứng viên trong nhật ký: lượt xếp chồng,
cha của ứng viên là ứng viên trước — 01-07 đóng băng lần đầu ở lượt 3, cha
của nó bỏ mất commit đầu của story. ``candidate`` = ứng viên cuối trong nhật
ký `candidate.frozen`, không có thì đầu nhánh `story/<id>`; phải nằm trên
`main`. ``tests.patch`` = diff `base..candidate` trên đường dẫn
`impact.is_test_path`; ``gold.patch`` = phần còn lại, bỏ tạo tác harness và
tài liệu. Story không có tệp test theo đường dẫn là INVALID ngay lúc đào —
e9 để test **in-source** (`import.meta.vitest` trong `vite.config.ts`,
`src/**`), đường dẫn không tách được; nói ra, không đoán.

**(b) Lỗi thật của kho** (`docs/FAILURE-TAXONOMY.md`, STATUS §2.4). Commit sửa
tìm bằng `git log -S<tên test hồi quy>`; ``base`` = cha của commit;
``tests.patch`` = phần test của commit; ``gold.patch`` = phần nguồn (bỏ
docs/README/CHANGELOG); prompt = dòng triệu chứng, **không** dòng gốc/sửa;
test hồi quy **hiện** trong bản chép (`tests_visible`) — đó là đề bài, cách
sửa không nằm trong nó. Lỗi 1, 3 nằm trong commit gộp đợt 2+3 (39 tệp) —
không tách sạch; lỗi 22 không có mã — cả ba bỏ, nêu tên ở `SKIPPED_BUGS`.

**Lint rò** (`lint_prompt`): prompt không chứa SHA 7–40 hex, `STORY-RP-*`
(trừ mã của chính story), URL, tên commit sửa. Task vi phạm ghi `task.json`
mang lý do nhưng **không** ghi prompt.

Task lỗi kho commit vào `tests/bench/tasks/` (mã của kho). Task story sinh
lúc chạy từ e9 (`AISEF_BENCH_E9`, chỉ đọc) vào `.bench/tasks/` — nội dung
dự án thử không vào kho.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from aisef.config import Config  # noqa: E402
from aisef.control.impact import is_test_path  # noqa: E402
from aisef.control.journal import JournalStore  # noqa: E402
from aisef.harness.observe import AGENT_RUN, TOOL_RUN, EvidenceStore  # noqa: E402
from aisef.harness.tools import BASELINE_RUN  # noqa: E402

#: Task lỗi kho — mã của kho, commit được.
TASKS_DIR = Path(__file__).resolve().parent / "tasks"
#: Tạo tác bench (task story, bản chép, kết quả) — gitignore.
KEEP_DIR = Path(os.environ.get("AISEF_BENCH_DIR") or (ROOT / ".bench"))
#: Story tốn hơn mức này trong lịch sử thì vẫn ghi nhưng đánh dấu `too_big`:
#: 01-04 $184/17 lượt developer — 3 lượt × 2 client ≈ $1 000, không lặp được.
TOO_BIG_USD = 100.0

#: Đường dẫn không phải mã của task: tạo tác harness, cấu hình client, tài liệu.
#: Thư mục nguồn của framework, gồm tên trước 0.2.0 — xem `invalid_reason`.
SRC_PREFIXES = ("aisef/", "aisdlc/")
_NOT_CODE = ("docs/", "_bmad-output/", ".claude/", ".opencode/", ".ai/", ".aisef/", ".github/")
_NOT_CODE_NAMES = ("README.md", "CHANGELOG.md", ".gitignore")


@dataclass
class Task:
    id: str
    source: str                       # story | bug
    base: str = ""                    # SHA trong kho nguồn (e9 hoặc chính kho)
    candidate: str = ""               # SHA đã merge / commit sửa — chỉ để tra
    verify: str = ""                  # lệnh test (`tools.test`)
    write_scope: list[str] = field(default_factory=list)
    tests_visible: bool = False       # bug: test hồi quy là đề bài; story: test ẩn
    use_docker: bool = False
    f2p_ids: list[str] = field(default_factory=list)
    p2p_ids: list[str] = field(default_factory=list)
    flaky_ids: list[str] = field(default_factory=list)
    validated: dict = field(default_factory=lambda: {"base_fail": False, "gold_pass": False, "runs": 0})
    history: dict = field(default_factory=lambda: {"cost_usd": 0.0, "turns": 0})
    too_big: bool = False
    invalid_reason: str = ""
    fix_commit: str = ""              # bug: commit sửa — trong task.json, không bao giờ vào prompt
    dir: Path | None = field(default=None, compare=False)

    def save(self, dir: Path | str | None = None) -> Path:
        d = Path(dir or self.dir)
        self.dir = d
        d.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        data.pop("dir")
        (d / "task.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return d

    @classmethod
    def load(cls, dir: Path | str) -> "Task":
        d = Path(dir).resolve()   # patch được áp với cwd là bản chép — đường dẫn phải tuyệt đối
        return cls(dir=d, **json.loads((d / "task.json").read_text(encoding="utf-8")))

    def read(self, name: str) -> str:
        p = (self.dir or Path()) / name
        return p.read_text(encoding="utf-8") if p.is_file() else ""


def load_tasks(*dirs: Path | str) -> list[Task]:
    return [Task.load(p.parent) for d in dirs for p in sorted(Path(d).glob("*/task.json"))]


def _git(cwd: Path | str, *args: str, check: bool = True) -> str:
    p = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and p.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {p.stderr.strip()}")
    return p.stdout.strip()


def _diff(repo: Path, a: str, b: str, paths: list[str]) -> str:
    if not paths:
        return ""
    return subprocess.run(["git", "diff", "--binary", a, b, "--", *paths], cwd=repo,
                          capture_output=True, text=True, encoding="utf-8", errors="replace", check=True).stdout


def _is_ancestor(repo: Path, a: str, b: str) -> bool:
    return subprocess.run(["git", "merge-base", "--is-ancestor", a, b], cwd=repo,
                          capture_output=True).returncode == 0


def split_paths(paths: list[str]) -> tuple[list[str], list[str]]:
    """(test, nguồn) theo `impact.is_test_path`; bỏ tạo tác harness và tài liệu."""
    tests, src = [], []
    for p in paths:
        if p.startswith(_NOT_CODE) or p in _NOT_CODE_NAMES:
            continue
        (tests if is_test_path(p) else src).append(p)
    return tests, src


# ------------------------------------------------------------ lint rò

# ponytail: 7 chữ hex cũng bắt số thuần 7 chữ số — dương tính giả hiếm, và
# lỗi nêu đúng chuỗi để người sửa prompt; thà chặn nhầm còn hơn rò SHA ngắn.
_SHA = re.compile(r"\b[0-9a-f]{7,40}\b")
_RP = re.compile(r"\bSTORY-RP-\d+\b")
_URL = re.compile(r"https?://\S+")


def lint_prompt(text: str, *, allow: tuple[str, ...] = (), forbid: tuple[str, ...] = ()) -> list[str]:
    """Những gì làm prompt rò đáp án. Rỗng = sạch."""
    out = []
    if (m := _SHA.search(text)):
        out.append(f"SHA `{m.group(0)}`")
    for m in _RP.finditer(text):
        if m.group(0) not in allow:
            out.append(f"mã story sửa `{m.group(0)}`")
            break
    if (m := _URL.search(text)):
        out.append(f"URL `{m.group(0)}`")
    for f in forbid:
        if f and f in text:
            out.append(f"tên commit sửa `{f[:40]}`")
    return out


# ------------------------------------------------------------ (a) story e9

_DROP_HEAD = re.compile(r"^## .*(phản hồi|feedback|ứng viên|lượt trước)", re.I)


def story_prompt(md: str) -> str:
    """Story file bỏ phần feedback/ứng viên và dòng ký sinh tự động."""
    out, skip = [], False
    for line in md.splitlines():
        if line.startswith("## "):
            skip = bool(_DROP_HEAD.match(line))
        if skip or line.startswith("_Sinh tự động"):
            continue
        out.append(line)
    return "\n".join(out).rstrip().rstrip("-").rstrip() + "\n"


def story_scope(md: str) -> list[str]:
    scope, on = [], False
    for line in md.splitlines():
        if line.startswith("## "):
            on = line.startswith("## Phạm vi được ghi")
        elif on and (m := re.match(r"^- `([^`]+)`", line)):
            scope.append(m.group(1))
    return scope


def mine_stories(e9_root: Path | str, out_dir: Path | str | None = None) -> list[Task]:
    """Một task mỗi story `done`. Story không đào được vẫn trả về, mang `invalid_reason`."""
    e9 = Path(e9_root).resolve()
    root = e9 / "_bmad-output"
    out = Path(out_dir or KEEP_DIR / "tasks")
    status = json.loads((root / "sprint-status.json").read_text(encoding="utf-8"))["stories"]
    index = {s["id"]: s for s in json.loads((root / "stories.index.json").read_text(encoding="utf-8"))["stories"]}
    cfg = Config.load(e9)
    ev_store, j_store = EvidenceStore(root), JournalStore(root)
    tasks = []
    for sid, st in sorted(status.items()):
        if st.get("status") != "done":
            continue
        ev = ev_store.read(sid)
        dev = [e for e in ev.of(AGENT_RUN) if e.name.startswith(sid + "#")]
        task = Task(id=sid, source="story", verify=str(cfg["tools.test"]), use_docker=bool(cfg["sandbox.use_docker"]),
                    history={"cost_usd": round(ev.total_cost_usd, 2),
                             "turns": sum(int(e.detail.get("turns") or 0) for e in dev)})
        task.too_big = task.history["cost_usd"] > TOO_BIG_USD
        md = (root / index[sid]["file"]).read_text(encoding="utf-8") if sid in index else ""
        task.write_scope = story_scope(md)
        prompt = story_prompt(md)
        tests: list[str] = []
        src: list[str] = []
        if not md:
            task.invalid_reason = "không có story file trong stories.index.json"
        elif not task.verify:
            task.invalid_reason = "dự án chưa khai tools.test"
        elif not dev:
            task.invalid_reason = "không có lượt developer trong bằng chứng"
        else:
            base_ev = next((e for e in ev.of(TOOL_RUN, BASELINE_RUN) if e.detail.get("parent")), None)
            if base_ev and base_ev.seq < dev[0].seq:
                task.base = str(base_ev.detail["parent"])
            else:
                t0 = int(dev[0].at - dev[0].duration_ms / 1000)
                task.base = _git(e9, "rev-list", "-1", "--first-parent", f"--before={t0}", "main")
            frozen = [e for e in j_store.read(sid).entries if e.step == "candidate.frozen" and e.data.get("sha")]
            task.candidate = str(frozen[-1].data["sha"]) if frozen else _git(
                e9, "rev-parse", "--verify", "-q", f"story/{sid}", check=False)
            if not task.candidate:
                task.invalid_reason = f"không có ứng viên: nhật ký không có candidate.frozen, không có nhánh story/{sid}"
            elif not _is_ancestor(e9, task.candidate, "main"):
                task.invalid_reason = "ứng viên chưa lên main"
            elif not _is_ancestor(e9, task.base, task.candidate):
                task.invalid_reason = "base không phải tổ tiên của ứng viên"
            else:
                tests, src = split_paths(_git(e9, "diff", "--name-only", task.base, task.candidate).splitlines())
                if not tests:
                    task.invalid_reason = "không có tệp test theo đường dẫn giữa base..candidate (test in-source?)"
        loi = lint_prompt(prompt, allow=(sid,))
        if loi:
            task.invalid_reason = "; ".join(filter(None, [task.invalid_reason, "prompt rò: " + "; ".join(loi)]))
        _write(task, out / sid, "" if loi else prompt,
               _diff(e9, task.base, task.candidate, tests) if not task.invalid_reason else "",
               _diff(e9, task.base, task.candidate, src) if not task.invalid_reason else "")
        tasks.append(task)
    return tasks


def _write(task: Task, d: Path, prompt: str, tests_patch: str, gold_patch: str) -> None:
    task.save(d)
    for name, body in (("prompt.md", prompt), ("tests.patch", tests_patch), ("gold.patch", gold_patch)):
        p = d / name
        if body:
            p.write_text(body, encoding="utf-8")
        else:
            p.unlink(missing_ok=True)


# ------------------------------------------------------------ (b) lỗi kho


@dataclass(frozen=True)
class Bug:
    id: str          # số lỗi trong STATUS §2.4 / FAILURE-TAXONOMY; nhiều lỗi một commit nối bằng "-"
    key: str         # tên test hồi quy (`git log -S`) hoặc tệp test mới (`--diff-filter=A`)
    symptom: str     # triệu chứng đo được — không có dòng gốc, không có cách sửa


BUGS: tuple[Bug, ...] = (
    Bug("13", "test_stray_dir_is_not_a_worktree",
        "`WorktreeManager.create` coi thư mục có sẵn trong `.aisef/worktrees/` là worktree có sẵn: một tiến trình "
        "dev server sống sót sau khi gỡ worktree ghi lại `.vite/` vào đúng chỗ, lần chạy sau agent làm việc trong một "
        "thư mục thường nằm trong repo chính, guard diff-scope so với repo chính và chặn mọi Bash (16 lần, developer "
        "chạy 40 phút không làm được gì)."),
    Bug("15", "TestAppServerTrust",
        "`AppServer.start` nhận vơ bất kỳ thứ gì trả lời ở `app.base_url` là app của story (\"người dùng đang chạy sẵn "
        "— dùng luôn\"); `stop` chỉ giết `npm` chứ không giết cả nhóm tiến trình, `node vite` sống sót giữ cổng sau khi "
        "worktree đã gỡ — cổng map mockup mở vào app ma, thấy trang trống, chấm sai app."),
    Bug("11", "test_isolated_from_user_config",
        "Máy bật `permissions.defaultMode: \"auto\"` toàn cục: phiên con Claude Code mất Glob/Grep, được dặn ưu tiên Bash "
        "nên ghi tệp bằng heredoc né sạch guard `Write|Edit`; MCP và hook toàn cục của người dùng lọt vào phiên agent. "
        "Adapter chưa từng truyền chế độ quyền dù docstring nói có."),
    Bug("20", "TestDottedNamesAreNotFiles",
        "Preflight coi mọi token có dấu chấm trong tiêu chí (`tools.lint`, `Note.text`, `save.done`, `search.clear`) là "
        "tệp chưa tồn tại phải nằm trong write_scope → 6/21 story \"không chạy được\", cổng stories chặn cả kế hoạch thật."),
    Bug("17-18", "TestPlannedButNeverRun",
        "17: Cổng trước triển khai ghi \"mọi story xong ✅\" khi hai story trong kế hoạch chưa từng chạy — chỉ đếm bản "
        "ghi trạng thái, không đối chiếu `stories.index.json`. 18: Báo cáo nghiệm thu ghi Map mockup ✗ cho story đã qua "
        "cổng vì ô này đòi *mọi* lần đối chiếu trong lịch sử đều đạt."),
    Bug("23-24", "test_doi_ten_test_giu_tieu_de_la_khong_phai_mat",
        "23: Cổng \"bảo toàn\" hỏi test mang mã của story *sở hữu* FR, còn sổ hành vi xác minh FR *qua* story khác → "
        "UNRUNNABLE oan dù sổ nói VERIFIED. 24: Cổng \"không làm đỏ test có sẵn\" coi đổi tên test (developer chỉ thêm "
        "tiền tố mã tiêu chí) là mất 4 test."),
    Bug("r2r1", "TestUngVienChuaLanded",
        "Sổ hành vi ghi VERIFIED cho hành vi xanh ở ứng viên chưa landed (chưa merge) trong khi nhật ký story biết "
        "ứng viên nào đã vào nhánh chính — cùng lớp J: hai luật cho một sự thật."),
    Bug("26-27", "test_xanh_truoc_khi_dong_bang_khong_thanh_verified",
        "26: Sổ hành vi coi bằng chứng không mang candidate là landed; với story đã đóng băng thì đó là lần "
        "`aisef tool test` agent tự chạy giữa phiên — xanh ở đó làm 3 hành vi của story trượt, chưa merge thành "
        "VERIFIED. 27: `verified_touched` bỏ hành vi REOPENED → lượt 2 của chính story gây hồi quy không còn thấy hành "
        "vi nó vừa làm hỏng trong slot lẫn mục \"bảo toàn\" (mục ấy ✅ trong khi test story trước còn đỏ)."),
    Bug("25", "TestStorySuaKhongLamStaleCongStories",
        "Vòng cải tiến ghi story sửa vào `stories.index.json` → cổng người `stories`/`readiness` đã duyệt thành stale, "
        "lần gọi `aisef improve` kế bị chính vòng trước chặn (exit 2)."),
    Bug("16", "TestPersistVerdict",
        "Lời người rà soát không được lưu nguyên văn; mục `[chặn]`/`[bế tắc]` nhiều dòng chỉ giữ dòng đầu → lý do bế "
        "tắc trong sprint-status cụt ở \"— không.\", bằng chứng chặn story mà người đọc không kiểm lại được."),
    Bug("6", "TestHarnessKhaiGocDuAn",
        "Hook biên dịch ghim đường dẫn tuyệt đối của dự án: chép hay di chuyển dự án thì guard ghi bằng chứng vào "
        "dự án *khác*, cổng \"guard có chạy\" trượt."),
    Bug("2-7-8-9", "test_module_not_found_is_unrunnable",
        "2: Guard `completion` chặn Stop vô hạn khi dự án chưa khai lệnh test. 7: Cấu hình client harness chép vào "
        "worktree bị tính là tệp story đổi khi dự án không gitignore `.claude/` → guard `diff-scope` chặn mọi lệnh, cổng "
        "\"phạm vi ghi\" trượt 3/3. 8: Lệnh test không chạy được (MODULE_NOT_FOUND) bị coi là test đỏ → guard "
        "`completion` chặn Stop ~10 lần/lượt, 3 story đốt $17. 9: `run_suite` ghi `qa:<kind>` nhưng cổng story tìm tên "
        "trần → e2e/perf/accessibility xanh thật mà cổng báo \"chưa cấu hình\"."),
    Bug("10", "TestTenKhoaDuongDanTheoClient",
        "OpenCode gửi đường dẫn dưới khoá `filePath` và nội dung dưới `newString`, guard chỉ đọc `file_path`/`path` → "
        "mọi guard theo đường dẫn trên OpenCode thấy đường dẫn rỗng, `write-scope` cho qua như \"không phải thao tác "
        "lên file\". Luật 6 so đường dẫn tuyệt đối của worktree nên khớp nhầm bảng thư mục cho phép."),
    Bug("12", "TestWholePageContract",
        "Mockup do agent dựng bỏ quên `data-state`/`data-annotation` (quy ước của chính skill mockup) → hợp đồng thị "
        "giác ôm cả trang gồm nhiều trạng thái (32 component, 4 lần \"Thêm thẻ\", cả tiêu đề gallery), bước map mockup "
        "không thể khớp; cổng máy mockup không kiểm quy ước ấy dù checklist skill có ghi."),
    Bug("14", "TestSeedConvention",
        "Cổng map mockup mở route có tham số bằng giá trị mẫu `1` (`/note/:id` → `/note/1`) và coi \"dev phải có bản "
        "ghi `1`\" là quy ước — nhưng quy ước ấy không có trong ngữ cảnh story, agent chỉ có thể đoán."),
    Bug("19", "tests/test_prd_headings.py",
        "Parser PRD chỉ nhận tiêu đề khối tiêu chí `**Consequences (testable):**`; lượt plan thật thứ hai agent viết "
        "`**Hệ quả kiểm chứng được:**` → cổng PRD loại cả 14 FR \"không có tiêu chí\" dù có."),
    Bug("21", "tests/test_write_scope_verify.py",
        "Harness đòi kiểm định e2e/accessibility (hợp đồng story) nhưng phạm vi ghi có hiệu lực chỉ gồm `src/**` mà "
        "kế hoạch khai → guard chặn ghi `tests/`, người rà soát đánh dấu bế tắc kế hoạch; hai story liên tiếp trượt "
        "vì harness đòi test rồi cấm viết test."),
    Bug("4-5", "TestManHinhKhongPhaiTuKhoa",
        "4: Phiên con thừa hưởng `CLAUDE_*` của phiên cha → agent tự chuyển sang Bash thay vì Read/Write. 5: Router "
        "chọn 8/18 story — sai cả 8: năng lực suy từ chữ trong SKILL.md, \"màn hình + một chữ\" đếm là hai tín hiệu."),
)

#: Lỗi không thành task được — nêu tên, không im.
SKIPPED_BUGS = {
    "1": "sửa (`_carry_client_config`) nằm trong commit gộp đợt 2+3 (39 tệp) — không tách nguồn/test sạch",
    "3": "sửa (snapshot + hoàn nguyên cây người rà soát) cùng commit gộp đợt 2+3 — không tách sạch",
    "22": "không có mã: bằng chứng đúng, môi trường đo sai (lớp I) — không có gì để hoàn nguyên",
}

_BUG_PROMPT = """# Lỗi kho AISEF — #{id}

Triệu chứng đo trên agent thật (không phải suy từ mã):

- {symptom}

Kiểm: `{verify}` — test hồi quy đang đỏ ở kho này. Sửa **nguồn** trong
`aisef/` cho test xanh; không sửa, không đổi tên, không xoá test. Chạy
`aisef tool test` để lần chạy vào bằng chứng.
"""


def _find_commit(repo: Path, key: str) -> str:
    args = ["--diff-filter=A", "--", key] if "/" in key else ["-S", key, "--", "tests"]
    got = _git(repo, "log", "--format=%H", "--reverse", *args, check=False)
    return got.splitlines()[0] if got else ""


def mine_bugs(repo_root: Path | str, out_dir: Path | str = TASKS_DIR, bugs: tuple[Bug, ...] = BUGS) -> list[Task]:
    """Một task mỗi commit sửa. Commit không tách được nguồn/test → task mang `invalid_reason`."""
    repo = Path(repo_root).resolve()
    out = Path(out_dir)
    tasks = []
    for bug in bugs:
        task = Task(id=f"bug-{bug.id}", source="bug", tests_visible=True, write_scope=["aisef"])
        tests: list[str] = []
        src: list[str] = []
        sha = _find_commit(repo, bug.key)
        if not sha:
            task.invalid_reason = f"không tìm thấy commit sửa theo `{bug.key}`"
        else:
            task.fix_commit = task.candidate = sha
            task.base = _git(repo, "rev-parse", sha + "^")
            tests, src = split_paths(_git(repo, "show", "--format=", "--name-only", sha).splitlines())
            mods = sorted(p[:-3].replace("/", ".") for p in tests if re.fullmatch(r"tests/test_\w+\.py", p))
            # Kho mang cả lịch sử **trước** lần đổi tên `aisdlc` → `aisef`
            # (0.2.0): commit cũ sửa `aisdlc/…`, commit mới sửa `aisef/…`.
            # Mỏ task đào cả hai thời kỳ nên phải nhận cả hai tiền tố.
            if not tests or not mods or not any(p.startswith(SRC_PREFIXES) for p in src):
                task.invalid_reason = ("commit không tách được nguồn/test "
                                       "(thiếu test unit hoặc thiếu nguồn aisef/)")
            task.verify = "python3 -m unittest -v " + " ".join(mods)
        prompt = _BUG_PROMPT.format(id=bug.id, symptom=bug.symptom, verify=task.verify)
        loi = lint_prompt(prompt, forbid=(_git(repo, "log", "-1", "--format=%s", sha) if sha else "",))
        if loi:
            task.invalid_reason = "prompt rò: " + "; ".join(loi)
        _write(task, out / task.id, "" if loi else prompt,
               _diff(repo, task.base, sha, tests) if not task.invalid_reason else "",
               _diff(repo, task.base, sha, src) if not task.invalid_reason else "")
        tasks.append(task)
    return tasks
