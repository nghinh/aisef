"""Guard — code tất định chạy tại mốc vòng đời.

Đây là chỗ dành cho những điều agent **không được phép quên**, và cách duy
nhất bảo đảm là không trông vào việc nó nhớ. Mỗi guard là một hàm thuần:
nhận sự kiện, trả phán quyết. Không đọc trạng thái toàn cục, không ghi gì —
nhờ vậy kiểm được bằng test và chạy được ở mọi client.

Quy ước mã thoát theo Claude Code (đã kiểm chứng ở spike S2): **thoát 2 là
chặn**, và stderr được chuyển vào kết quả tool cho agent đọc. Vì thế lý do
chặn phải viết cho agent hiểu và sửa được, không phải viết cho log.

Phạm vi ghi của story truyền qua biến môi trường ``AISDLC_WRITE_SCOPE``.
Guard cố ý **không** tự tra `stories.index.json`: giữ nó thuần và nhanh,
việc tra cứu là của bộ chạy story.
"""

from __future__ import annotations

import os
import re
import shlex
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .observe import TOOL_RUN

ENV_WRITE_SCOPE = "AISDLC_WRITE_SCOPE"
ENV_STORY_ID = "AISDLC_STORY_ID"
ENV_BASE_REF = "AISDLC_BASE_REF"
#: Cây làm việc của story. Harness **biết** đường này — chính nó dựng
#: worktree — nên không việc gì phải hỏi client. Client báo sai (hoặc
#: model tự đặt `workdir` khác) thì guard vẫn soi đúng cây.
ENV_WORKDIR = "AISDLC_WORKDIR"
#: Tool vai này bị cấm, cách nhau bằng dấu phẩy. Claude Code có
#: `--disallowed-tools`; OpenCode khai "emulated qua permission config"
#: nhưng không có mã nào sinh config ấy — người rà soát trên OpenCode ghi
#: được code. Cấm ở guard thì mọi client đều cấm, và Claude có thêm một
#: lớp phòng khi cờ bị bỏ quên.
ENV_DISALLOWED_TOOLS = "AISDLC_DISALLOWED_TOOLS"
#: Gốc dự án — harness khai qua env. Hook biên dịch ghim `--project` tuyệt
#: đối; dự án bị chép/di chuyển thì guard vẫn chạy nhưng ghi bằng chứng vào
#: dự án cũ (đo A/B `par-A` 2026-09-05: 4 lượt trượt "guard có chạy" sai).
ENV_PROJECT = "AISDLC_PROJECT"

#: Phạm vi ghi khi **không** ở trong một story: các pha lập kế hoạch và
#: dựng mockup. Chúng có phạm vi cố định và biết trước, nên guard vẫn có
#: nghĩa — thay vì phải tắt đi ở nửa vòng đời.
PLANNING_SCOPE = ("_bmad-output", "docs")


@dataclass(frozen=True)
class Verdict:
    allowed: bool
    reason: str = ""

    @property
    def exit_code(self) -> int:
        return 0 if self.allowed else 2


ALLOW = Verdict(True)


# ------------------------------------------------------------ phạm vi ghi


def _norm(p: str) -> PurePosixPath:
    return PurePosixPath(str(p).strip().strip("/"))


def _within(path: str, scope: str) -> bool:
    """`path` có nằm trong `scope` không — so theo đoạn đường dẫn.

    So tiền tố chuỗi sẽ coi `src/apidocs/x.py` là nằm trong `src/api`, mà
    đó là hai vùng khác nhau.
    """
    p, s = _norm(path), _norm(scope)
    return p == s or s in p.parents


def check_write_scope(file_path: str, scope: list[str], *, project_root: str = "") -> Verdict:
    """Chặn ghi ra ngoài phạm vi story.

    Phạm vi rỗng nghĩa là **chưa khai**, và chưa khai thì không cho ghi —
    mặc định mở sẽ biến guard thành thứ trang trí ngay lần đầu ai đó quên
    truyền biến môi trường.
    """
    if not file_path:
        return ALLOW  # không phải thao tác lên file

    if not scope:
        return Verdict(
            False,
            f"story chưa khai write_scope nên không được ghi {file_path}. "
            f"Bổ sung write_scope vào story rồi chạy lại.",
        )

    rel = str(file_path)
    if project_root:
        try:
            rel = str(Path(file_path).resolve().relative_to(Path(project_root).resolve()))
        except ValueError:
            return Verdict(
                False,
                f"{file_path} nằm ngoài thư mục dự án. Story chỉ được ghi trong "
                f"write_scope của nó: {', '.join(scope)}",
            )

    if any(_within(rel, s) for s in scope):
        return ALLOW
    return Verdict(
        False,
        f"{rel} nằm ngoài write_scope của story ({', '.join(scope)}). "
        f"Nếu story thật sự cần chạm chỗ này thì dừng lại và báo — nhiều khả "
        f"năng phạm vi khai thiếu hoặc story bị chẻ sai.",
    )


# ------------------------------------------------------------ bí mật

#: Mẫu bí mật. Nhắm vào những thứ có hình dạng đặc trưng, không đoán mò —
#: một chuỗi ngẫu nhiên dài chưa chắc là khoá, nhưng `sk-ant-...` thì chắc.
SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("khoá API Anthropic", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("khoá API OpenAI", re.compile(r"\bsk-[A-Za-z0-9]{32,}")),
    ("khoá truy cập AWS", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("token GitHub", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    ("khoá riêng tư", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("token Slack", re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}")),
    ("gán mật khẩu", re.compile(
        r"(?i)\b(password|passwd|pwd|pw|secret|api[_-]?key|access[_-]?token)\s*[=:]\s*"
        r"['\"][^'\"\s{}$]{8,}['\"]"
    )),
]

#: Giá trị giữ chỗ — có hình dạng bí mật nhưng rõ ràng là ví dụ.
PLACEHOLDER_MARKERS = (
    "example", "placeholder", "your-", "xxx", "changeme", "dummy",
    "<", "{{", "${", "os.environ", "process.env", "getenv",
)


def check_secrets(content: str) -> Verdict:
    """Chặn bí mật lọt vào mã nguồn.

    Bỏ qua dòng có dấu hiệu giữ chỗ hoặc đọc từ biến môi trường — chặn
    `API_KEY = os.environ["X"]` sẽ khiến người ta tắt guard đi, và một guard
    bị tắt còn tệ hơn không có.
    """
    if not content:
        return ALLOW

    for line_no, line in enumerate(content.splitlines(), 1):
        lowered = line.lower()
        if any(m in lowered for m in PLACEHOLDER_MARKERS):
            continue
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(line):
                return Verdict(
                    False,
                    f"dòng {line_no} có vẻ chứa {label}. Đọc từ biến môi trường "
                    f"hoặc kho bí mật, đừng viết thẳng vào mã nguồn.",
                )
    return ALLOW


# ------------------------------------------------------------ lệnh shell

#: Lệnh phá huỷ — chặn thẳng, kể cả khi agent nghĩ nó đang dọn dẹp.
DESTRUCTIVE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("git reset --hard", re.compile(r"\bgit\s+reset\s+(--\S+\s+)*--hard\b")),
    ("git checkout bỏ thay đổi", re.compile(r"\bgit\s+checkout\s+--\s")),
    ("git clean", re.compile(r"\bgit\s+clean\b.*-[a-z]*f")),
    ("git push --force", re.compile(r"\bgit\s+push\b.*(--force\b|-f\b)")),
    ("xoá đệ quy", re.compile(r"\brm\s+(-\w*\s+)*-\w*[rR]\w*f|\brm\s+-fr\b")),
    ("git stash bỏ việc", re.compile(r"\bgit\s+stash\s+(drop|clear)\b")),
]

_GIT_ADD_ALL = re.compile(r"\bgit\s+add\s+(.*\s)?(-A\b|--all\b|\.(\s|$))")


def check_git_stage(command: str) -> Verdict:
    """Chặn `git add -A` và `git add .`.

    Lệnh gộp nuốt cả file rác lẫn thay đổi của story khác đang chạy song
    song trong worktree bên cạnh.
    """
    if not command or not _GIT_ADD_ALL.search(command):
        return ALLOW
    return Verdict(
        False,
        "không dùng `git add -A` hay `git add .`. Chỉ stage đúng đường dẫn "
        "story này chạm, ví dụ: git add src/api/users.py tests/test_users.py",
    )


def check_destructive(command: str) -> Verdict:
    """Chặn lệnh phá huỷ công việc chưa lưu."""
    if not command:
        return ALLOW
    for label, pattern in DESTRUCTIVE_PATTERNS:
        if pattern.search(command):
            return Verdict(
                False,
                f"lệnh phá huỷ bị chặn ({label}). Nếu thật sự cần, dừng lại "
                f"và báo người — đừng tự chạy.",
            )
    return ALLOW


# ------------------------------------------------------------ tiêm mã

#: Mỗi rủi ro có **hai** mẫu, một cho mỗi họ ngôn ngữ framework gặp thật.
#: Guard chỉ biết mẫu Python thì trên dự án TypeScript nó có mặt mà không
#: bao giờ nổ — cùng loại sai với "chưa cấu hình bị đếm là đạt", và tệ hơn
#: vì báo cáo vẫn ghi "7 guard đã nối".
#:
#: Tách theo họ chứ không gộp một mẫu chung, vì dấu hiệu nội suy khác nhau
#: và gộp lại thì chúng bắt chéo nhau: `{` chỉ có nghĩa nội suy khi chuỗi
#: có tiền tố `f` của Python, còn trong JS nó là object tuỳ chọn — mẫu gộp
#: chặn oan `execFileSync('git', ['ls-files'], { cwd })`, đúng dạng **an
#: toàn** mà guard lẽ ra phải khuyến khích.
#:
#: Chỗ khó riêng của JS là `exec(`: `re.exec(s)` của RegExp phổ biến hơn
#: nhiều so với `child_process.exec`. Phân biệt bằng **đối số**: chỉ nổ khi
#: ngay sau ngoặc là chuỗi hoặc template. `re.exec(bien)` truyền biến nên
#: không dính; đổi lại bỏ sót `exec(chuoi_da_ghep_san)` — thà bỏ sót còn
#: hơn chặn oan mọi lần dùng biểu thức chính quy.
_SQL = r"\b(select|insert|update|delete)\b"
_SHELL_PY = r"os\.system|subprocess\.\w+|commands\.getoutput"
_SHELL_JS = (
    r"execSync|execFileSync|spawnSync|child_process\.\w+|\bexec|\bspawn"
)

INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("nối chuỗi vào câu SQL", re.compile(
        rf"""(?i)(execute|query|cursor\.execute|\braw|prepare)\s*\("""
        rf"""\s*f['"].*{_SQL}.*\{{"""
    )),
    ("nối chuỗi vào câu SQL", re.compile(
        rf"""(?i)(execute|query|\braw|prepare)\s*\(\s*['"`].*{_SQL}"""
        rf""".*(\$\{{|\+|%s\s*%)"""
    )),
    ("chèn HTML thô", re.compile(
        r"dangerouslySetInnerHTML|\.(inner|outer)HTML\s*=|"
        r"\.insertAdjacentHTML\s*\(|document\.write(ln)?\s*\("
    )),
    ("shell với chuỗi ghép", re.compile(
        rf"""(?i)({_SHELL_PY})\s*\(\s*(f['"].*\{{|['"].*\+)"""
    )),
    ("shell với chuỗi ghép", re.compile(
        rf"""(?i)({_SHELL_JS})\s*\(\s*['"`].*(\$\{{|\+)"""
    )),
    ("dựng mã từ chuỗi ghép", re.compile(
        r"""(?i)(\beval|new\s+Function)\s*\(\s*(f['"].*\{|['"`].*(\$\{|\+))"""
    )),
]


#: Luật 6 hiến pháp: không ghi số hiệu story/epic vào mã nguồn. Ngoại lệ có
#: chủ đích: tệp test (mã `AC-<story>-<i>` **phải** nằm trong tên test — G5),
#: tài liệu, artifact của harness.
_PROCESS_REF = re.compile(r"\b(?:STORY|EPIC)-\d+(?:-\d+)?\b")
_REF_ALLOWED_DIRS = ("docs/", "_bmad-output/", ".ai/", ".claude/", ".opencode/", ".aisdlc/", "bench/")
_REF_ALLOWED_SUFFIX = (".md", ".txt", ".json", ".yaml", ".yml", ".csv")


def check_process_refs(content: str, path: str, *, project_root: str = "") -> Verdict:
    """Luật 6: mã tham chiếu quy trình (`STORY-01-02`, `EPIC-01`) không được
    nằm trong mã nguồn. Test và tài liệu được phép — test còn bắt buộc mang
    mã tiêu chí. So thư mục trên đường dẫn **tương đối với gốc**: đường dẫn
    tuyệt đối của worktree chứa `.aisdlc/worktrees/` và khớp nhầm bảng cho
    phép (hợp quy C6 trên OpenCode, 2026-09-05)."""
    from ..control.impact import is_test_path

    rel = path.replace("\\", "/")
    if project_root:
        try:
            rel = str(Path(rel).resolve().relative_to(Path(project_root).resolve()))
        except ValueError:
            pass
    rel = rel.lstrip("./")
    if any(rel.startswith(seg) for seg in _REF_ALLOWED_DIRS) or rel.endswith(_REF_ALLOWED_SUFFIX) or is_test_path(rel):
        return ALLOW
    hit = _PROCESS_REF.search(content or "")
    if not hit:
        return ALLOW
    return Verdict(
        False,
        f"luật 6: mã quy trình `{hit.group(0)}` trong mã nguồn ({rel}). Comment giải thích "
        f"*vì sao*, không phải *việc này thuộc phiếu nào* — bỏ số hiệu ra khỏi nguồn.",
    )


def check_injection(content: str) -> Verdict:
    if not content:
        return ALLOW
    for label, pattern in INJECTION_PATTERNS:
        m = pattern.search(content)
        if m:
            line_no = content[: m.start()].count("\n") + 1
            return Verdict(
                False,
                f"dòng {line_no}: {label}. Dùng tham số hoá / API an toàn thay "
                f"vì ghép chuỗi.",
            )
    return ALLOW


# ------------------------------------------------------------ điều phối


# ------------------------------------------------------------ phạm vi diff


def check_diff_scope(changed: list[str], scope: list[str]) -> Verdict:
    """Chặn khi file **ngoài phạm vi** đã bị đổi.

    `write-scope` chặn từng thao tác ghi mà harness nhìn thấy. Guard này
    hỏi câu khác: sau tất cả những gì đã xảy ra, cây làm việc có đúng
    phạm vi không. Nó bắt được cả đường đi vòng — script tự sinh file, lệnh
    di chuyển file, hoặc client không gắn được hook tiền kiểm (OpenCode ở
    mức hậu kiểm) — vì nó đọc kết quả chứ không đọc ý định.
    """
    if not changed:
        return ALLOW
    if not scope:
        return Verdict(
            False,
            f"story chưa khai write_scope nhưng đã đổi {len(changed)} file: "
            f"{', '.join(changed[:5])}",
        )

    outside = [c for c in changed if not any(_within(c, s) for s in scope)]
    if not outside:
        return ALLOW
    return Verdict(
        False,
        f"{len(outside)} file bị đổi ngoài write_scope ({', '.join(scope)}): "
        f"{', '.join(outside[:5])}. Hoàn nguyên chúng, hoặc dừng lại và báo "
        f"rằng phạm vi story khai thiếu.",
    )


#: Đường dẫn do **harness** ghi trong lúc chạy, không phải agent: bằng
#: chứng, trạng thái đợt, bản ghi phê duyệt, worktree. Không loại chúng ra
#: thì chính việc harness ghi trạng thái lại bị tính là story ghi ra ngoài
#: phạm vi — guard tự tố cáo mình và mọi story đều trượt.
#:
#: Cố ý **không** loại cả `_bmad-output`: tài liệu kế hoạch (PRD, kiến
#: trúc, epic, hợp đồng thị giác, chỉ mục story) là thứ agent sửa trộm thì
#: phải lộ ra — sửa `stories.index.json` là sửa chính phạm vi ràng buộc nó.
#: Phụ thuộc cài đặt và tạo tác build. Chúng xuất hiện vì story **chạy**,
#: không phải vì story **viết** — tính vào phạm vi thì mọi story cài phụ
#: thuộc đều trượt, và cách duy nhất chạy tiếp là nới phạm vi đến mức guard
#: không còn nghĩa gì. Dự án có `.gitignore` đúng thì git đã loại sẵn;
#: danh sách này là lưới an toàn cho lúc `.gitignore` chưa kịp có.
VENDOR_PATHS = (
    "node_modules", ".venv", "venv", "vendor", "target", "dist", "build",
    "__pycache__", ".pytest_cache", ".ruff_cache", ".next", ".turbo",
    "coverage", ".gradle", "Pods",
    # Tạo tác của chính công cụ agent dùng để làm việc: ảnh chụp, trace,
    # báo cáo. Chúng ở gốc dự án nhưng không phải sản phẩm của story —
    # tính vào phạm vi thì mở trình duyệt một lần là trượt cổng.
    ".playwright-mcp", "playwright-report", "test-results", ".nyc_output",
)

HARNESS_OWNED = (
    "_bmad-output/evidence",
    "_bmad-output/journal",
    "_bmad-output/approvals",
    "_bmad-output/sprint-status.json",
    "_bmad-output/sprint-status.json.lock",
    "_bmad-output/compile-report.json",
    ".aisdlc",
    # Cấu hình client harness chép vào worktree (`WorktreeManager._carry_client_config`)
    # — dự án không gitignore `.claude/` thì nó hiện là tệp chưa theo dõi và guard
    # `diff-scope` chặn mọi lệnh vì "ngoài phạm vi ghi" (dogfood par 2026-09-05:
    # 3/3 story trượt "phạm vi ghi" vì đúng tệp này).
    ".claude/settings.json",
    ".opencode",
    *VENDOR_PATHS,
)


def _git_lines(project_root: str, args: list[str]) -> list[str]:
    """Chạy một lệnh git trả kết quả phân tách bằng NUL. Lỗi thì rỗng."""
    import subprocess

    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=project_root or ".",
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    return [e for e in proc.stdout.split("\0") if e]


def changed_files(
    project_root: str,
    *,
    ignore: tuple[str, ...] = HARNESS_OWNED,
    base_ref: str = "",
) -> list[str]:
    """Công việc story đã làm: file đổi so với **điểm rẽ nhánh**, kể cả
    file mới chưa theo dõi.

    Không có ``base_ref`` thì chỉ so với ``HEAD`` — và đó là chỗ sập.
    Agent được khuyến khích tự commit từng phần (merge chỉ thấy thứ đã
    commit), nên sau vài commit thì "so với HEAD" trả về gần như rỗng.
    Ba cổng cùng đọc danh sách này: phạm vi ghi thành đạt vô điều kiện,
    test-thật không còn gì để kiểm, và người rà soát nhận một diff rỗng
    rồi phải tự mò cả repo — vừa mù vừa tốn. So với điểm rẽ nhánh thì
    công việc đã commit vẫn nằm trong tầm nhìn.

    Bỏ qua phần harness tự ghi. Phần còn lại của ``_bmad-output`` **không**
    được bỏ qua: agent sửa PRD hay hợp đồng thị giác giữa lúc viết code là
    chuyện phải lộ ra.
    """
    paths: list[str] = []
    seen: set[str] = set()

    # `git status` cho cả file chưa theo dõi — thứ `git diff` không thấy.
    for entry in _git_lines(
        project_root, ["status", "--porcelain", "-z", "--untracked-files=all"]
    ):
        if len(entry) > 3:
            paths.append(entry[3:])

    # `git diff <base>` so **cây làm việc** với điểm rẽ nhánh, nên phủ cả
    # phần đã commit lẫn phần còn dở.
    if base_ref:
        paths += _git_lines(project_root, ["diff", "--name-only", "-z", base_ref])

    out: list[str] = []
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        if any(_within(path, skip) or skip in Path(path).parts for skip in ignore):
            continue
        out.append(path)
    return out


def fork_point(workdir: str, upstream: str) -> str:
    """Điểm nhánh story rẽ khỏi nhánh chính. Rỗng nếu không tính được.

    Dùng ``merge-base`` chứ không dùng thẳng đầu nhánh chính: trong một
    đợt, story trước có thể đã merge vào nhánh chính khi story sau đang
    chạy — so với đầu nhánh thì công việc của story trước bị tính sang
    story sau.
    """
    if not upstream:
        return ""
    got = _git_lines(workdir, ["merge-base", "HEAD", upstream])
    return got[0].strip() if got else ""


def head_sha(workdir: str | Path) -> str:
    """SHA của HEAD. Rỗng nếu không đọc được git.

    Rỗng phải là **không kiểm được**, không phải "khác bản": mất tầm nhìn
    git thì chặn cả story còn tệ hơn.
    """
    got = _git_lines(str(workdir), ["rev-parse", "HEAD"])
    return got[0].strip() if got else ""


# ------------------------------------------------------------ hoàn thành


def check_completion(evidence) -> Verdict:
    """Chặn agent kết thúc khi test chưa xanh cho **đoạn code hiện tại**.

    Ba câu hỏi, theo thứ tự nghiêm dần:

    1. Có lần chạy test nào chưa? Chưa chạy mà tuyên bố xong là tự khai.
    2. Lần gần nhất có xanh không?
    3. Có file nào sửa **sau** lần chạy đó không? Test xanh trước khi sửa
       không nói gì về đoạn vừa viết — đây là kiểu "xanh" hay gặp nhất khi
       agent vội kết thúc.
    """
    last = evidence.last(TOOL_RUN, "test")
    if last is None:
        # Nói đúng lệnh gõ được. Guard chặn bằng một chỉ dẫn không chạy được
        # thì agent kẹt: nó không dừng được, cũng không làm được điều được
        # bảo — và cứ thế đốt hết số lượt.
        from .tools import aisdlc_command

        return Verdict(
            False,
            f"chưa có lần chạy test nào cho story này. Chạy `{aisdlc_command()} "
            f"tool test` rồi mới kết thúc — bằng chứng nằm ở kết quả chạy, "
            f"không ở lời kể.",
        )
    if last.detail.get("unrunnable"):
        # Không chạy được ≠ đỏ: agent không sửa được môi trường/lệnh test
        # (ngoài phạm vi ghi), chặn Stop chỉ đốt lượt. Cổng story ghi
        # UNRUNNABLE và vẫn chặn — với lý do đúng.
        return ALLOW
    if last.detail.get("skipped"):
        # Chưa cấu hình ≠ đỏ. Chặn ở đây thì agent không sửa được gì (lệnh
        # test là việc của dự án) và chỉ đốt lượt — đo ở hợp quy: Stop bị
        # chặn hai lần liền trên dự án không khai lệnh test. Cổng story vẫn
        # ghi "unit chưa cấu hình", không tính là đạt.
        return ALLOW
    if not last.ok:
        tail = str(last.detail.get("tail") or "")[:400]
        return Verdict(
            False,
            "lần chạy test gần nhất còn đỏ, chưa được kết thúc story.\n" + tail,
        )

    stale = evidence.stale_since_last_test()
    if stale:
        from .tools import aisdlc_command

        return Verdict(
            False,
            f"{len(stale)} file đã sửa sau lần chạy test gần nhất "
            f"({', '.join(stale[:5])}). Chạy lại `{aisdlc_command()} tool test` "
            f"rồi mới kết thúc.",
        )
    return ALLOW


def project_root_from(env: dict[str, str] | None, fallback: str) -> str:
    """Gốc dự án cho guard: env của harness thắng, `--project` biên dịch là dự phòng."""
    goc = (env if env is not None else os.environ).get(ENV_PROJECT, "").strip()
    return goc or fallback


def scope_from_env(env: dict[str, str] | None = None) -> list[str]:
    raw = (env or os.environ).get(ENV_WRITE_SCOPE, "")
    return [p.strip() for p in raw.split(",") if p.strip()]


def story_from_env(env: dict[str, str] | None = None) -> str:
    return (env or os.environ).get(ENV_STORY_ID, "")


def disallowed_from_env(env: dict[str, str] | None = None) -> list[str]:
    raw = (env or os.environ).get(ENV_DISALLOWED_TOOLS, "")
    return [t.strip() for t in raw.split(",") if t.strip()]


def check_role_tool(tool_name: str, disallowed: list[str]) -> Verdict:
    """Vai này có được gọi tool này không. Khớp không phân biệt hoa thường:
    Claude gọi `Write`, OpenCode gọi `write`."""
    if not tool_name or not disallowed:
        return ALLOW
    cam = {t.lower() for t in disallowed}
    if tool_name.lower() not in cam:
        return ALLOW
    return Verdict(
        False,
        f"vai này không được dùng tool {tool_name} — nó rà soát, không sửa. "
        f"Báo cáo phát hiện thay vì tự chữa.",
    )


def workdir_from_env(env: dict[str, str] | None = None) -> str:
    """Cây làm việc do harness khai. Rỗng nghĩa là không chạy trong story."""
    return (env or os.environ).get(ENV_WORKDIR, "")


def base_from_env(env: dict[str, str] | None = None) -> str:
    return (env or os.environ).get(ENV_BASE_REF, "")


def effective_scope(env: dict[str, str] | None = None) -> list[str]:
    """Phạm vi ghi đang có hiệu lực.

    Trong một story: đúng phạm vi story khai, và **rỗng thì chặn** — quên
    truyền biến môi trường không được biến guard thành đồ trang trí.

    Ngoài story (pha lập kế hoạch, dựng mockup): phạm vi cố định của
    framework. Không có nhánh này thì guard chặn cả BMAD ghi PRD, và cách
    duy nhất để chạy tiếp là tắt guard ở nửa đầu vòng đời — nửa mà tài
    liệu quyết định mọi thứ phía sau.
    """
    scope = scope_from_env(env)
    if scope or story_from_env(env):
        return scope
    return list(PLANNING_SCOPE)


def _escaped_workdir(tool_input: dict, root: str) -> Verdict | None:
    """Lệnh có tự chỉ định thư mục nằm ngoài cây agent đang đứng không.

    Trả ``None`` khi không có gì để nói — không có `workdir`, không biết
    cây gốc, hoặc `workdir` nằm trong cây. Cách ly bằng worktree chỉ có
    giá trị khi không ai bước ra được khỏi nó.
    """
    wd = str(tool_input.get("workdir") or tool_input.get("cwd") or "")
    if not wd or not root:
        return None
    try:
        trong = Path(wd).resolve()
        cay = Path(root).resolve()
    except OSError:
        return None
    if trong == cay or cay in trong.parents:
        return None
    return Verdict(
        False,
        f"lệnh tự chỉ định thư mục {wd}, nằm ngoài cây đang làm việc ({root}). "
        f"Story chỉ được làm việc trong worktree của nó — công việc đặt ra "
        f"ngoài không qua cổng nào cả. Bỏ tham số thư mục đi và chạy lại.",
    )


def run_guard(kind: str, event: dict, *, env: dict[str, str] | None = None,
              project_root: str = "", artifact_root: str = "") -> Verdict:
    """Chạy một guard trên sự kiện hook của client.

    ``event`` theo hình dạng Claude Code gửi: ``tool_name`` và ``tool_input``.
    Hai guard cuối cần trạng thái ngoài (git, bằng chứng); phần **quyết
    định** của chúng vẫn là hàm thuần, chỗ này chỉ đi lấy dữ liệu.
    """
    tool_input = event.get("tool_input") or {}
    # Claude Code gửi `file_path`; OpenCode gửi `filePath` (đo hợp quy C6
    # 2026-09-05: guard thấy đường dẫn rỗng → write-scope cho qua như "không
    # phải thao tác lên file"). Tên khoá là chuyện của client, không phải của luật.
    file_path = str(tool_input.get("file_path") or tool_input.get("filePath") or tool_input.get("path") or "")
    content = str(tool_input.get("content") or tool_input.get("new_string") or tool_input.get("newString") or "")
    command = str(tool_input.get("command") or "")

    # Cây phải soi là cây agent đang đứng, không phải cây lúc biên dịch
    # hook. Story chạy trong worktree riêng, còn hook được ghi vào
    # `.claude/settings.json` một lần với `--project` là gốc dự án — dùng
    # nó thì guard đi đọc `git status` của cây khác, thấy toàn bộ tài liệu
    # kế hoạch chưa commit và chặn mọi thao tác. `--porcelain` luôn trả
    # đường dẫn tính từ gốc repo nên đứng ở thư mục con cũng đúng.
    # Thứ tự tin cậy: cây harness khai → cây client báo → cây lúc biên
    # dịch hook. Bản khai của harness đứng trước vì nó là **sự thật**:
    # client có thể báo gốc dự án thay vì worktree, và model của OpenCode
    # còn tự đặt `workdir` cho từng lệnh.
    root = workdir_from_env(env) or str(event.get("cwd") or "") or project_root

    # Tool `bash` của OpenCode nhận `workdir` riêng cho **từng lệnh**, và
    # model tự đặt nó — đã gặp thật: story chạy trong worktree nhưng lệnh
    # `git add … && git commit` mang `workdir` là gốc dự án, nên công việc
    # rơi thẳng lên `main` mà không cổng nào thấy (worktree vẫn trống,
    # diff rỗng, story trượt vì lý do sai).
    #
    # Kiểm ở đây, tại tầng điều phối, nên nó áp cho **mọi** guard và mọi
    # client: guard nào chạy trước cũng chặn được. Đi xuống thư mục con
    # thì vẫn cho — thoát ra khỏi cây mới là chuyện.
    if (thoat := _escaped_workdir(tool_input, root)):
        return thoat

    # Vai rà soát mà sửa được code thì nó thành lượt viết thứ hai, và không
    # còn ai rà soát nữa. Kiểm ở tầng điều phối để mọi guard, mọi client
    # đều chặn — không trông vào cờ dòng lệnh của từng client.
    vai = check_role_tool(str(event.get("tool_name") or ""), disallowed_from_env(env))
    if not vai.allowed:
        return vai

    if kind == "write-scope":
        return check_write_scope(
            file_path, effective_scope(env), project_root=root
        )
    if kind == "secret":
        return check_secrets(content)
    if kind == "injection":
        return check_injection(content)
    if kind == "process-ref":
        return check_process_refs(content, file_path, project_root=root)
    if kind == "git-stage":
        return check_git_stage(command)
    if kind == "destructive":
        return check_destructive(command)
    if kind == "diff-scope":
        return check_diff_scope(
            changed_files(root, base_ref=base_from_env(env)), scope_from_env(env)
        )
    if kind == "completion":
        story = story_from_env(env)
        if not story or not artifact_root:
            # Không biết đang làm story nào thì không kết luận được. Chặn ở
            # đây sẽ chặn cả những lượt chạy ngoài vòng đời story.
            return ALLOW
        from .observe import EvidenceStore

        return check_completion(EvidenceStore(artifact_root).read(story))
    raise ValueError(f"guard không tồn tại: {kind}")


def record_outcome(
    kind: str,
    event: dict,
    verdict: Verdict,
    *,
    env: dict[str, str] | None = None,
    artifact_root: str = "",
) -> None:
    """Guard tự ghi vào bằng chứng — nguồn duy nhất không phụ thuộc client.

    Hai lỗ hổng cùng một gốc: (1) `guard_blocked` chỉ trích từ luồng sự kiện
    của Claude Code, nên trên OpenCode nó luôn False dù guard chặn thật —
    đo trên `par`: 4 lần chặn, bằng chứng ghi False cả bốn; (2) sự kiện
    `FILE_CHANGE` có mô hình, có test, nhưng **không ai ghi**, nên luật
    "file sửa sau lần test cuối" của guard `completion` chưa từng chạy.

    Ghi ở đây, vì guard là điểm mà mọi client đều đi qua. Không có mã story
    (phiên rà soát cố ý không mang nó) thì không ghi — tránh làm bẩn hồ sơ.
    """
    story = story_from_env(env)
    if not story or not artifact_root:
        return
    from .observe import GUARD_BLOCK, GUARD_SEEN, TOOL_RUN, EvidenceStore, Event

    store = EvidenceStore(artifact_root)
    tool_input = event.get("tool_input") or {}
    tool = str(event.get("tool_name") or "")
    hien_co = store.read(story)

    # Nhịp tim: một lần mỗi story. Đo trên `par`: phiên chỉ dùng Bash để
    # ghi file thì không có Write/Edit nào đi qua `write-scope`, và không có
    # gì bị chặn — evidence trống dù hook chạy 17 lần. "Hook tới được" phải
    # là sự kiện riêng, không suy từ sự kiện khác.
    if not hien_co.of(GUARD_SEEN):
        store.record(story, Event(kind=GUARD_SEEN, name=kind, detail={"tool": tool}))

    if not verdict.allowed:
        store.record(story, Event(
            kind=GUARD_BLOCK, name=kind, ok=False,
            detail={"tool": tool, "reason": verdict.reason[:300]},
        ))
        return
    if kind == "write-scope":
        path = str(tool_input.get("file_path") or tool_input.get("path") or "")
        if path:
            store.file_change(story, path, detail={"tool": tool})
        return
    if kind == "diff-scope":
        # Guard duy nhất nhìn thấy file do **Bash** đổi. Chỉ ghi file có
        # mtime mới hơn lần `test` gần nhất: đó đúng là định nghĩa "sửa sau
        # lần test cuối" mà guard `completion` cần, và không ghi trùng file
        # đã đổi từ trước.
        last = hien_co.last(TOOL_RUN, "test")
        moc = last.at if last else 0.0
        root = workdir_from_env(env) or str(event.get("cwd") or "")
        da_ghi = {str(e.detail.get("path") or e.name) for e in hien_co.of("file_change")
                  if e.seq > (last.seq if last else 0)}
        for rel in changed_files(root, base_ref=base_from_env(env)) if root else []:
            try:
                mtime = (Path(root) / rel).stat().st_mtime
            except OSError:
                continue
            if mtime > moc and rel not in da_ghi:
                store.file_change(story, rel, detail={"tool": tool})


#: Guard nào gắn vào mốc nào, và khớp tool nào.
GUARD_MATCHERS: dict[str, tuple[str, str]] = {
    "write-scope": ("PreToolUse", "Write|Edit|NotebookEdit"),
    "secret": ("PreToolUse", "Write|Edit"),
    "injection": ("PreToolUse", "Write|Edit"),
    "process-ref": ("PreToolUse", "Write|Edit"),
    "git-stage": ("PreToolUse", "Bash"),
    "destructive": ("PreToolUse", "Bash"),
    "diff-scope": ("PostToolUse", "Write|Edit|NotebookEdit|Bash"),
    "completion": ("Stop", ""),
}


def parse_command(command: str) -> list[str]:
    """Tách lệnh shell an toàn; trả rỗng nếu không phân tích được."""
    try:
        return shlex.split(command)
    except ValueError:
        return []
