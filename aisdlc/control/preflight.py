"""Kiểm story chạy được không, **trước khi** gọi model.

Một story không chạy được là story mà tiêu chí chấp nhận của nó đòi thứ
mà phạm vi ghi cấm, hoặc đòi một loại kiểm định chưa ai cấu hình. Không
có bước này thì cách duy nhất phát hiện là chạy thật rồi trượt cổng —
đo trên e9, hai story liên tiếp bí đúng vì thế, tám lượt không lượt nào
qua, $20.

Cả module là **hàm thuần trên dữ liệu đã có**. Không hỏi model câu nào:
"story này có đủ điều kiện chạy không" là câu tính được, và câu tính
được thì hỏi model chỉ thêm một nguồn sai. Đổi lại, mọi luật ở đây phải
bảo thủ — báo thiếu oan sẽ chặn một story chạy được, đắt ngang bỏ sót.

Mỗi năng lực suy ra mang theo **bằng chứng** đã kích nó, để người đọc
kiểm lại được kết luận thay vì phải tin.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..config import DEFAULTS, Config
from .normalize import (
    LOCKFILES,
    MANIFESTS,
    Story,
    effective_write_scope,
    is_lockfile,
)

#: Mã trả về khi story không chạy được. Chặn trước khi gọi model.
STORY_NOT_EXECUTABLE = "STORY_NOT_EXECUTABLE"


@dataclass(frozen=True)
class Need:
    """Một năng lực story cần, kèm chỗ trong story đã đòi nó."""

    capability: str
    #: Câu chữ trong story làm nảy sinh yêu cầu này. Không có nó thì kết
    #: luận không kiểm lại được, và người đọc chỉ còn cách tin.
    evidence: str
    #: Cách cấp năng lực, in ra khi thiếu.
    remedy: str = ""
    #: Ai phải sửa. ``"story"`` = chính story hỏng (tiêu chí đòi thứ phạm
    #: vi cấm) — sửa được ngay lúc chia story. ``"project"`` = dự án chưa
    #: cấu hình đủ — không phải lỗi của story, và sửa được **sau** khi
    #: story đã chốt. Phân biệt hai loại này vì cổng `stories` chạy trước
    #: cả pha dựng mockup: đòi hợp đồng thị giác ở đó là bài toán con gà
    #: quả trứng, còn đòi nó trước khi gọi model thì đúng.
    kind: str = "project"

    def line(self) -> str:
        out = f"{self.capability} — {self.evidence}"
        return f"{out}. {self.remedy}" if self.remedy else out


@dataclass
class Preflight:
    story_id: str
    needs: list[Need] = field(default_factory=list)
    missing: list[Need] = field(default_factory=list)

    @property
    def executable(self) -> bool:
        return not self.missing

    @property
    def story_defects(self) -> list[Need]:
        """Thiếu do **story** hỏng — chặn ngay từ cổng `stories`."""
        return [m for m in self.missing if m.kind == "story"]

    @property
    def provisioning_gaps(self) -> list[Need]:
        """Thiếu do **dự án** chưa cấu hình — còn sửa được sau khi chốt
        story, nên ở cổng `stories` chỉ cảnh báo; chặn ở `readiness` và
        ngay trước khi gọi model."""
        return [m for m in self.missing if m.kind != "story"]

    def summary(self) -> str:
        if self.executable:
            return f"{self.story_id}: chạy được ({len(self.needs)} năng lực)"
        lines = [f"{self.story_id}: {STORY_NOT_EXECUTABLE}"]
        lines += [f"  ✗ {m.line()}" for m in self.missing]
        return "\n".join(lines)


# ------------------------------------------------------------ dấu hiệu

#: Dấu hiệu kích một loại kiểm định. Cố ý hẹp: chỉ những cụm chỉ đích danh
#: loại kiểm, không phải cụm nào nhắc xa xôi tới nó. Rộng ra thì mọi story
#: đều "cần E2E" và cổng mất hết nghĩa.
_VERIFY_MARKERS: dict[str, tuple[str, ...]] = {
    "verify.e2e": ("e2e", "end-to-end", "đầu-cuối", "đầu cuối", "kịch bản người dùng"),
    "verify.sit": ("tích hợp", "integration test", "kiểm thử tích hợp"),
    "verify.api-contract": ("hợp đồng api", "api contract", "contract test", "openapi"),
    "verify.accessibility": ("trợ năng", "accessibility", "a11y", "wcag", "screen reader"),
    "verify.migration": ("migration", "di trú", "nâng cấp schema", "onupgradeneeded"),
    "verify.perf": ("hiệu năng", "performance", "p95", "p99", "độ trễ", "latency"),
}

#: Dấu hiệu story chạm mặt bảo mật. Rộng hơn nhóm trên có chủ đích: sót
#: một story bảo mật đắt hơn nhiều so với chạy thừa một lượt rà soát.
_SECURITY_MARKERS = (
    "bảo mật", "security", "xác thực", "phân quyền", "auth", "oauth", "jwt",
    "mã hoá", "mã hóa", "encrypt", "crypto", "băm mật khẩu", "hash",
    "bí mật", "secret", "credential", "injection", "xss", "csrf",
    # "token" trơn quá rộng: "token thị giác" của hệ thiết kế là biến CSS,
    # và nó xuất hiện ở gần như mọi story dựng giao diện.
    "token phiên", "token xác thực", "access token", "refresh token",
    "bearer", "api token", "session token",
    "sql", "sanitize", "khử trùng", "leo thang đặc quyền",
)

#: Dấu hiệu story cần mạng lúc chạy kiểm.
_NETWORK_MARKERS = (
    "gọi api ngoài", "dịch vụ ngoài", "third-party", "bên thứ ba",
    "tải về từ", "cdn", "webhook", "đồng bộ lên máy chủ",
)

#: Dấu hiệu story cần hiểu ảnh hưởng chéo module.
#: Cố ý **không** có "toàn kho": trong tiếng Việt "kho" vừa là kho mã vừa
#: là kho dữ liệu, và trên e9 nó xuất hiện ở câu *cấm* quét toàn kho
#: IndexedDB — báo oan ngay ở story đầu tiên có nó.
_IMPACT_MARKERS = (
    "mọi nơi dùng", "tất cả caller", "mọi lời gọi", "mọi nơi gọi",
    "cross-module", "liên module", "phiên bản api", "api version",
    "breaking change", "thay đổi phá vỡ", "mọi module",
)

#: Ngưỡng số module gốc mà phạm vi ghi chạm tới thì coi là thay đổi chéo.
IMPACT_MODULE_THRESHOLD = 3

_BACKTICK = re.compile(r"`([^`\n]{2,80})`")
#: Đường dẫn: có dấu `/`, hoặc có đuôi tệp quen thuộc.
_PATHISH = re.compile(r"^[\w.@/-]+$")
_EXT = re.compile(r"\.[a-z]{1,5}$")
#: Tên gói npm/pypi: chữ thường, có gạch nối hoặc tiền tố scope, không có `/`
#: (trừ scope), không có đuôi tệp.
_PACKAGEISH = re.compile(r"^(@[a-z0-9][\w.-]*/)?[a-z0-9][a-z0-9._-]*$")

#: Động từ cho thấy story phải **tạo hoặc sửa** thứ được nêu. Không có nó
#: thì đường dẫn trong tiêu chí là **ràng buộc**, không phải sản phẩm:
#: "tệp trong `src/search/` import React thì build hỏng" nói về một thư
#: mục story không sở hữu. Đo trên e9, luật thiếu vế này báo oan 2/18
#: story ngay lần chạy đầu.
_MUTATION = (
    "sinh ra", "tạo ", "tạo,", "ghi ", "ghi,", "cập nhật", "thêm vào",
    "sửa ", "xoá ", "xóa ", "commit", "lưu ", "dựng ", "xuất ra",
    "được tạo", "được ghi", "được sinh", "được lưu", "được commit",
)


def _text_of(story: Story) -> str:
    return " \n".join([story.title, *story.acceptance_criteria]).lower()


def _ticked(story: Story) -> list[str]:
    return _BACKTICK.findall(" \n".join([story.title, *story.acceptance_criteria]))


#: Khoảng cách tối đa giữa định danh và động từ tạo/sửa để coi là chúng
#: nói về nhau. Một tiêu chí chấp nhận dài thường có nhiều mệnh đề: quét
#: cả câu thì một động từ ở cuối kéo theo mọi đường dẫn ở đầu. Đo trên
#: e9: TCCN 2 của STORY-01-01 nêu `src/search/` như **ràng buộc** ở đầu
#: câu rồi nói "lệnh dựng thất bại" ở cuối — cách nhau 90 ký tự.
MUTATION_WINDOW = 60


def _ticked_in_mutations(story: Story) -> list[str]:
    """Định danh trong backtick **đứng gần** một động từ tạo/sửa.

    Nhắc tới một đường dẫn không đòi quyền ghi lên nó: tiêu chí hay nêu
    thư mục như ràng buộc ("tệp trong `src/search/` import React thì
    build hỏng") chứ không như sản phẩm story phải tạo.
    """
    out: list[str] = []
    for cau in [story.title, *story.acceptance_criteria]:
        low = cau.lower()
        moc = [low.find(v) for v in _MUTATION if v in low]
        if not moc:
            continue
        for m in _BACKTICK.finditer(cau):
            if any(abs(m.start() - i) <= MUTATION_WINDOW for i in moc):
                out.append(m.group(1))
    return out


def _within(path: str, scope: str) -> bool:
    p, s = path.strip("/").split("/"), scope.strip("/").split("/")
    return len(p) >= len(s) and p[: len(s)] == s


def _covered(tok: str, scope: list[str]) -> bool:
    """Đường dẫn này đã nằm trong phạm vi ghi chưa.

    Ngoài quan hệ tiền tố, còn nhận **đoạn giữa**: tiêu chí chấp nhận hay
    gọi tên tầng (`store/`) trong khi phạm vi khai đường đầy đủ
    (`src/store/db.ts`). Coi hai cái đó là khác nhau thì cổng báo thiếu
    oan, mà báo thiếu oan chặn một story chạy được — đắt ngang bỏ sót.
    """
    if any(_within(tok, s) for s in scope):
        return True
    want = [x for x in tok.strip("/").split("/") if x]
    for s in scope:
        have = [x for x in s.strip("/").split("/") if x]
        for i in range(len(have) - len(want) + 1):
            if have[i : i + len(want)] == want:
                return True
    return False


def _first_marker(text: str, markers: tuple[str, ...]) -> str:
    for m in markers:
        if m in text:
            return m
    return ""


# ------------------------------------------------------------ suy ra


def required_capabilities(story: Story, *, project: Path | None = None) -> list[Need]:
    """Năng lực story này cần, suy ra từ chính nội dung story.

    Nguồn suy ra, theo đúng thứ tự đáng tin: trường có cấu trúc trước
    (``screens``, ``write_scope``), rồi mới tới câu chữ tiêu chí chấp
    nhận. Câu chữ là nguồn yếu nhất nên chỉ dùng với dấu hiệu chỉ đích
    danh, không suy diễn.
    """
    text = _text_of(story)
    needs: list[Need] = []

    # 1. Story có giao diện: cần trình duyệt để dựng, và hợp đồng thị giác
    #    để đối chiếu. Đây là trường có cấu trúc, chắc chắn nhất.
    for screen in story.screens:
        needs.append(Need(
            "browser", f"story dựng màn hình `{screen}`",
            "cấu hình `app.dev_command` và `app.base_url`",
        ))
        needs.append(Need(
            "mockup-map", f"story dựng màn hình `{screen}`",
            "chạy `aisdlc mockup` để có hợp đồng thị giác cho màn này",
        ))

    # 2. Công cụ nền: mọi story đều bị chấm bằng test và lint. Không cấu
    #    hình thì guard `completion` chặn agent kết thúc bằng một chỉ dẫn
    #    nó không chạy được.
    needs.append(Need("tools.test", "mọi story đều bị chấm bằng test",
                      "cấu hình `tools.test`"))
    needs.append(Need("tools.lint", "mọi story đều bị chấm bằng lint",
                      "cấu hình `tools.lint`"))

    # 3. Loại kiểm định tiêu chí chấp nhận gọi tên.
    for cap, markers in _VERIFY_MARKERS.items():
        hit = _first_marker(text, markers)
        if hit:
            needs.append(Need(cap, f'tiêu chí chấp nhận nhắc "{hit}"',
                              f"cấu hình `{cap}`"))

    # 4. Bảo mật.
    hit = _first_marker(text, _SECURITY_MARKERS)
    if hit:
        needs.append(Need("verify.security", f'tiêu chí chấp nhận nhắc "{hit}"',
                          "cấu hình `verify.security`"))

    # 5. Mạng lúc chạy kiểm.
    hit = _first_marker(text, _NETWORK_MARKERS)
    if hit:
        needs.append(Need("network", f'tiêu chí chấp nhận nhắc "{hit}"',
                          "bật `sandbox.tools_network`"))

    # 6. Hiểu ảnh hưởng chéo module.
    hit = _first_marker(text, _IMPACT_MARKERS)
    # Chỉ đếm **thư mục** gốc: `vite.config.ts` hay `index.html` là tệp
    # cấu hình ở gốc dự án, không phải một module. Đếm chúng vào thì mọi
    # story dựng nền dự án đều bị coi là thay đổi chéo module.
    roots = {
        p.strip("/").split("/")[0]
        for p in story.write_scope
        if not is_lockfile(p) and ("/" in p.strip("/"))
    }
    roots -= set(MANIFESTS)
    if hit:
        needs.append(Need("code-intelligence", f'tiêu chí chấp nhận nhắc "{hit}"',
                          "cấu hình `review.impact_provider`"))
    elif len(roots) >= IMPACT_MODULE_THRESHOLD:
        needs.append(Need(
            "code-intelligence",
            f"phạm vi ghi chạm {len(roots)} module gốc: {', '.join(sorted(roots))}",
            "cấu hình `review.impact_provider`",
        ))

    # 7. Tệp và gói tiêu chí chấp nhận gọi tên.
    needs += _needs_from_names(story, project)
    return needs


def _needs_from_names(story: Story, project: Path | None) -> list[Need]:
    """Tệp/gói mà tiêu chí chấp nhận nêu đích danh nhưng story không được
    phép chạm.

    Phân biệt bằng **đĩa**, không đoán: một đường dẫn đã tồn tại trong dự
    án thì story có thể chỉ đọc nó; một đường dẫn chưa tồn tại thì story
    phải tạo ra, nên phải nằm trong phạm vi ghi. Cùng lối đó, một tên gói
    chưa có trong manifest nghĩa là story phải khai nó.
    """
    out: list[Need] = []
    # Đối chiếu với phạm vi **có hiệu lực**, không phải phạm vi khai thô:
    # harness tự thêm tệp khai phụ thuộc và lockfile, nên so với bản thô
    # thì cổng báo một vấn đề đã được vá.
    scope = (
        effective_write_scope(story, project)
        if project is not None
        else list(story.write_scope)
    )
    deps = _declared_deps(project) if project else None

    for tok in _ticked_in_mutations(story):
        if not _PATHISH.match(tok):
            continue
        la_duong_dan = "/" in tok or _EXT.search(tok)
        if la_duong_dan:
            if _covered(tok, scope):
                continue
            if project is not None and _exists_anywhere(project, tok):
                continue  # đã có sẵn — story chỉ đọc, không cần quyền ghi
            if project is None:
                continue  # không có đĩa để đối chiếu thì không kết luận
            out.append(Need(
                f"write:{tok}",
                f"tiêu chí chấp nhận đòi `{tok}`, tệp chưa tồn tại",
                "thêm nó vào `write_scope` của story hoặc sửa tiêu chí",
                kind="story",
            ))
        elif deps is not None and _PACKAGEISH.match(tok) and "-" in tok:
            # Chỉ tên có gạch nối: từ thường một tiếng (`store`, `rev`) hay
            # bị bọc backtick mà không phải tên gói.
            if tok in deps:
                continue
            if not any(m in scope for m in MANIFESTS):
                out.append(Need(
                    "manifest-write",
                    f"tiêu chí chấp nhận đòi gói `{tok}`, chưa khai trong manifest",
                    "thêm tệp manifest vào `write_scope` của story",
                    kind="story",
                ))
    # Một story chỉ cần báo thiếu manifest **một lần**.
    seen: set[str] = set()
    ket: list[Need] = []
    for n in out:
        if n.capability in seen:
            continue
        seen.add(n.capability)
        ket.append(n)
    return ket


def _exists_anywhere(project: Path, tok: str) -> bool:
    """Tệp này đã có trong dự án chưa — kể cả ở thư mục khác.

    `DESIGN.md` nằm trong `_bmad-output/`, không ở gốc; so đúng một chỗ
    thì cổng kết luận story phải tạo ra nó, mà nó đã có sẵn.
    """
    if (project / tok).exists():
        return True
    ten = tok.rstrip("/").rsplit("/", 1)[-1]
    if not ten:
        return False
    for goc in (project, project / "_bmad-output", project / "docs", project / "src"):
        if (goc / ten).exists():
            return True
    return False


def _declared_deps(project: Path) -> set[str] | None:
    """Tên gói dự án đã khai. ``None`` nếu không có manifest nào đọc được —
    không đọc được thì không kết luận, thay vì kết luận sai."""
    pkg = project / "package.json"
    if pkg.is_file():
        try:
            raw = json.loads(pkg.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        deps: set[str] = set()
        for key in ("dependencies", "devDependencies", "peerDependencies",
                    "optionalDependencies"):
            deps |= set((raw.get(key) or {}).keys())
        return deps
    for name in ("pyproject.toml", "requirements.txt", "requirements.in"):
        f = project / name
        if f.is_file():
            try:
                body = f.read_text(encoding="utf-8")
            except OSError:
                return None
            return set(re.findall(r"^\s*[\"']?([A-Za-z0-9][\w.-]*)", body, re.M))
    return None


# ------------------------------------------------------------ đối chiếu


def provisioned(
    project: Path,
    config: Config,
    *,
    contract_screens: set[str] | None = None,
) -> set[str]:
    """Năng lực dự án **đã** cấp. Đọc cấu hình và đĩa, không đoán."""
    have: set[str] = set()

    for key in DEFAULTS:
        if key.startswith(("verify.", "tools.")) and str(config.get(key, "")).strip():
            have.add(key)

    # Miễn có ghi lại là một quyết định của người, không phải chỗ trống.
    for waived in str(config.get("verify.waived", "")).split(","):
        w = waived.strip()
        if w:
            have.add(w if w.startswith("verify.") else f"verify.{w}")

    if str(config.get("app.dev_command", "")).strip() and str(
        config.get("app.base_url", "")
    ).strip():
        have.add("browser")

    if config.get("sandbox.tools_network"):
        have.add("network")

    if str(config.get("review.impact_provider", "")).strip():
        have.add("code-intelligence")

    if contract_screens is None:
        contract_screens = _contract_screens(project)
    if contract_screens:
        have.add("mockup-map")
        have |= {f"mockup-map:{s}" for s in contract_screens}

    return have


def _contract_screens(project: Path) -> set[str]:
    f = project / "_bmad-output" / "design-contract.json"
    if not f.is_file():
        return set()
    try:
        raw = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    screens = raw.get("screens") if isinstance(raw, dict) else raw
    if isinstance(screens, dict):
        return set(screens.keys())
    if isinstance(screens, list):
        # Hợp đồng thật dùng khoá `id`; nhận thêm `screen_id` cho bản cũ.
        # Đọc sai khoá thì cổng báo thiếu hợp đồng cho **mọi** màn — và
        # đó là chặn oan trên diện rộng, đắt hơn nhiều so với bỏ sót.
        out = set()
        for s in screens:
            if not isinstance(s, dict):
                continue
            sid = s.get("id") or s.get("screen_id") or ""
            if sid:
                out.add(sid)
        return out
    return set()


def check_story(
    story: Story,
    *,
    project: Path,
    config: Config | None = None,
    have: set[str] | None = None,
) -> Preflight:
    """Story này chạy được không. Không gọi model."""
    cfg = config or Config(dict(DEFAULTS))
    got = have if have is not None else provisioned(project, cfg)
    out = Preflight(story.id)
    out.needs = required_capabilities(story, project=project)

    for need in out.needs:
        cap = need.capability
        if cap == "mockup-map":
            screen = need.evidence.split("`")[-2] if "`" in need.evidence else ""
            if f"mockup-map:{screen}" in got or (not screen and "mockup-map" in got):
                continue
            out.missing.append(need)
            continue
        if cap.startswith("write:") or cap == "manifest-write":
            out.missing.append(need)  # suy ra đã là bằng chứng thiếu
            continue
        if cap not in got:
            out.missing.append(need)
    return out


def check_stories_executable(
    stories: list[Story],
    *,
    project: Path,
    config: Config | None = None,
) -> list[Preflight]:
    """Chấm cả tập story. Cấp năng lực đọc một lần, dùng cho mọi story."""
    cfg = config or Config(dict(DEFAULTS))
    got = provisioned(Path(project), cfg)
    return [
        check_story(s, project=Path(project), config=cfg, have=got) for s in stories
    ]


__all__ = [
    "IMPACT_MODULE_THRESHOLD",
    "LOCKFILES",
    "Need",
    "Preflight",
    "STORY_NOT_EXECUTABLE",
    "check_stories_executable",
    "check_story",
    "provisioned",
    "required_capabilities",
]
