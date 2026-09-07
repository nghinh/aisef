"""Bản đồ mã quanh phạm vi ghi — ngữ cảnh tĩnh cho phiên mới (ADR-005 V7).

Developer vào phiên mới không có bản đồ: trên e9 lượt đầu tốn 42–91 lượt,
phần lớn để dò "tệp này định nghĩa gì, ai gọi, test nào chạm"; reviewer
tốn 22–68 lượt cho cùng câu hỏi. Aider trả lời bằng repo map xếp hạng
PageRank trên đồ thị định danh; Agentless đo được **skeleton** (chữ ký,
thân → `…`) thắng tệp đầy đủ cả độ đúng lẫn giá (58 % @ $0,02 so với
54 % @ $0,15). Ở đây lấy hai ý ấy bằng stdlib, lân cận **một bước** quanh
phạm vi ghi:

  (a) skeleton tệp trong phạm vi — Python bằng `ast`, TS/JS bằng
      `_EXPORTS` + chữ ký trên dòng;
  (b) tệp ngoài phạm vi nhắc tên trong phạm vi (callers) và tệp phạm vi
      import — mỗi tệp ≤ 3 dòng;
  (c) tệp test nhắc tên trong phạm vi.

Đây là **gợi ý tĩnh**, không phải chân lý — cùng giới hạn với
`control/impact.py`: gọi động, phản chiếu, tiêm phụ thuộc đều không hiện.
Ngân sách ký tự là thiết kế, không phải nhượng bộ; Aider không công bố số
đo cho repo map, nên `context.max_repo_map_chars` mặc định 0 (tắt) cho tới
khi A/B T8 có số. Bản đầy đủ luôn tra được bằng `aisef ctx --story S`.

Nhà cung cấp ngoài (`context.map_provider`, tree-sitter/serena cắm sau)
nhận stdin JSON ``{project, seeds, budget}`` và trả văn bản; lỗi thì lùi
về bản dựng sẵn và nói ra ở dòng đầu — cùng kiểu `review.impact_provider`.

# ponytail: lân cận 1 bước; PageRank stdlib ~20 dòng khi kho > 500 tệp làm
# lân cận tràn ngân sách.
"""

from __future__ import annotations

import ast
import json
import math
import os
import re
import shlex
import subprocess
from collections import defaultdict
from pathlib import Path

from ..control.impact import _EXPORTS, SOURCE_EXT, _rel_files, is_test_path, refs, symbols, weights

#: Aider `to_tree` cắt 100 ký tự/dòng — đủ đọc chữ ký, không đủ chép thân.
MAX_LINE = 100
#: Dòng tối đa cho mỗi tệp lân cận.
PER_NEIGHBOUR = 3
#: Định danh trong story ngắn hơn chừng này là chữ thường, không phải tên mã.
MIN_IDENT = 5
_IDENT = re.compile(r"[A-Za-z][\w-]{%d,}" % (MIN_IDENT - 1), re.ASCII)
_IMPORT_JS = re.compile(r"""(?:from|require\()\s*['"](\.{1,2}/[^'"]+)['"]""")
_IMPORT_PY = re.compile(r"^\s*(?:from\s+([.\w]+)\s+import|import\s+([\w.]+))", re.M)

HEADING = "## Bản đồ mã quanh phạm vi — gợi ý tĩnh, không phải chân lý"


def seeds_for(story, project: Path | str, *, artifact_root: Path | str, config=None) -> list[str]:
    """Hạt giống của một story: phạm vi ghi có hiệu lực ∪ đường dẫn kiểm
    định ∪ định danh ≥ 5 ký tự trong story file (Aider `get_ident_mentions`)."""
    from ..control.normalize import effective_write_scope, verification_paths

    project = Path(project)
    seeds = list(effective_write_scope(story, project))
    seeds += [p for p in verification_paths(story, project, config) if p not in seeds]
    f = Path(artifact_root) / "stories" / story.epic_id / f"{story.id}.md"
    text = f.read_text(encoding="utf-8", errors="replace") if f.is_file() else (
        story.title + "\n" + "\n".join(story.acceptance_criteria)
    )
    seen = set(seeds)
    for tok in _IDENT.findall(text):
        if tok not in seen:
            seen.add(tok)
            seeds.append(tok)
    return seeds


def repo_map(project: Path | str, seeds: list[str], budget_chars: int = 0, *,
             command: str = "", story_id: str = "", timeout: int = 120) -> str:
    """Bản đồ quanh ``seeds`` (đường dẫn có thật = phạm vi; còn lại = định
    danh), cắt ở ``budget_chars`` (0 = không cắt). Có lệnh ngoài thì dùng;
    hỏng thì lùi về dựng sẵn và ghi rõ ở dòng đầu."""
    project = Path(project)
    note = ""
    if command.strip():
        got = _run_provider(project, seeds, budget_chars, command, timeout)
        if got is not None:
            return _cut(f"_Nguồn: {command.split()[0]}._\n\n{got}", budget_chars, story_id)
        note = f" · **thô** — `context.map_provider` chạy hỏng ({command.split()[0]}), đã lùi về bản dựng sẵn"
    text = f"_Nguồn: dựng sẵn (stdlib, lân cận 1 bước){note}._\n\n" + _builtin(project, seeds)
    return _cut(text, budget_chars, story_id)


def prompt_section(map_text: str) -> str:
    """Mục prompt cho cả ba vai; rỗng khi không có bản đồ (knob 0) để prompt
    không mang một tiêu đề trống."""
    if not map_text.strip():
        return ""
    return (
        f"{HEADING}\n\n"
        "Đây là **gợi ý**, không phải chân lý: phân tích tĩnh không thấy gọi động, "
        "phản chiếu hay tiêm phụ thuộc. Đừng dừng ở đây, và đừng bỏ qua chỗ nó "
        "không nhắc tới. Bản đầy đủ: `aisef ctx --story <mã>`.\n\n" + map_text
    )


# ------------------------------------------------------------------ dựng sẵn


def _builtin(project: Path, seeds: list[str]) -> str:
    scope, idents = _split_seeds(project, seeds)
    if not scope:
        return "_(phạm vi ghi chưa có tệp mã nào trên đĩa — story tạo mới từ đầu)_"
    files = list(_rel_files(project))
    syms = symbols(project, scope)
    names = sorted({n for s in syms.values() for n, _, _ in s})
    w = weights(project, names, files)
    # Aider: tệp có tên khớp định danh story được nhắc ×10.
    boost = lambda rel: 10.0 if any(i in Path(rel).stem.lower() for i in idents) else 1.0  # noqa: E731

    score: dict[str, float] = defaultdict(float)
    hit: dict[str, set[str]] = defaultdict(set)
    for name, per_file in refs(project, names, files).items():
        for rel, n in per_file.items():
            if rel in scope or w[name] <= 0:
                continue
            score[rel] += w[name] * math.sqrt(n)
            if w[name] >= 1:
                hit[rel].add(name)
    imported = {rel for f in scope for rel in _imports(project, f) if rel not in scope}
    for rel in imported:
        score[rel] += 1.0

    out = ["**Trong phạm vi (skeleton):**"]
    for rel in sorted(scope, key=lambda r: (-boost(r), r)):
        out.append(f"`{rel}`")
        out += [f"  {ln} {sig}" for ln, sig in _skeleton(project / rel, syms.get(rel, []))] or ["  (không có định nghĩa xuất khẩu)"]

    rank = lambda r: (-score[r] * boost(r), r)  # noqa: E731
    near = sorted((r for r in score if not is_test_path(r) and (score[r] >= 1 or r in imported)), key=rank)
    if near:
        out.append("\n**Lân cận 1 bước (gọi tên trong phạm vi / được phạm vi import):**")
        for rel in near:
            tag = ", ".join(sorted(hit[rel])[:4]) or "được import"
            out.append(f"`{rel}` · {tag}")
            out += [f"  {ln} {line}" for ln, line in _lines(project / rel, hit[rel], syms_of=rel in imported and not hit[rel])]
    tests = sorted((r for r in score if is_test_path(r) and score[r] >= 1), key=rank)
    if tests:
        out.append("\n**Test nhắc tên trong phạm vi:**")
        out += [f"- `{rel}` · {', '.join(sorted(hit[rel])[:4])}" for rel in tests]
    return "\n".join(out)


def _split_seeds(project: Path, seeds: list[str]) -> tuple[list[str], set[str]]:
    """Hạt giống là đường dẫn có thật (tệp, thư mục, glob) → phạm vi; còn lại
    → định danh (chữ thường, khớp với tên tệp để nhân 10)."""
    scope: list[str] = []
    idents: set[str] = set()
    for s in seeds:
        p = project / s
        if p.is_file():
            hits = [p]
        elif p.is_dir():
            hits = [f for f in sorted(p.rglob("*")) if f.is_file()]
        elif any(c in s for c in "*?["):
            # `src/**` chỉ khớp **thư mục** ở Python ≤ 3.12 (3.13 mới cho khớp
            # cả tệp) — phạm vi ghi viết kiểu ấy thì bản đồ rỗng trên đúng
            # những phiên bản gói này khai hỗ trợ (CI Linux 3.12, 2026-09-06).
            # Chuẩn hoá về `**/*`: cùng kết quả trên 3.11 → 3.14.
            pat = s + "/*" if s.endswith("**") else s
            hits = [f for f in sorted(project.glob(pat)) if f.is_file()]
        else:
            if len(s) >= MIN_IDENT:
                idents.add(s.lower())
            continue
        for f in hits:
            rel = f.relative_to(project).as_posix()
            if f.suffix in SOURCE_EXT and rel not in scope and not ({"node_modules", ".git"} & set(f.parts)):
                scope.append(rel)
    return scope, idents


def _skeleton(path: Path, syms: list[tuple[str, int, str]]) -> list[tuple[int, str]]:
    """Dòng định nghĩa + chữ ký, thân → `…` (Agentless `get_skeleton`)."""
    try:
        body = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    if path.suffix == ".py":
        got = _py_skeleton(body)
        if got:
            return got
    lines = body.splitlines()
    out = []
    for _, ln, _ in syms:
        # Chữ ký TS/JS hay xuống dòng (`export function X(\n  props: P\n) {`):
        # nối tới dòng có `{` hoặc `;`, tối đa 6 dòng, rồi cắt ở `{`.
        chunk = []
        for i, l in enumerate(lines[ln - 1: ln + 5]):
            chunk.append(l.strip())
            nxt = lines[ln + i] if ln + i < len(lines) else ""
            if "{" in l or ";" in l or not nxt.strip() or any(p.match(nxt) for p in _EXPORTS):
                break
        sig = " ".join(chunk)
        # Cắt ở `{` **cuối** — tham số huỷ cấu trúc (`({ onReload }: Props) {`)
        # cũng có `{`; rồi bỏ `=` / `=>` treo (`export type X =`, `() =>`).
        sig = sig.rsplit("{", 1)[0] if "{" in sig else sig
        sig = re.sub(r"\s*(?:=>|=)\s*$", "", sig.rstrip())
        out.append((ln, sig[:MAX_LINE] + " …"))
    return out


def _py_skeleton(body: str) -> list[tuple[int, str]]:
    try:
        tree = ast.parse(body)
    except SyntaxError:
        return []

    def sig(n) -> str:
        if isinstance(n, ast.ClassDef):
            bases = ", ".join(ast.unparse(b) for b in n.bases)
            return f"class {n.name}({bases}):" if bases else f"class {n.name}:"
        ret = f" -> {ast.unparse(n.returns)}" if n.returns else ""
        kw = "async def" if isinstance(n, ast.AsyncFunctionDef) else "def"
        return f"{kw} {n.name}({ast.unparse(n.args)}){ret}: …"

    out = []
    for n in tree.body:
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) or n.name.startswith("_"):
            continue
        out.append((n.lineno, sig(n)[:MAX_LINE]))
        if isinstance(n, ast.ClassDef):
            out += [(m.lineno, "    " + sig(m)[:MAX_LINE]) for m in n.body
                    if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and (not m.name.startswith("_") or m.name == "__init__")]
    return out


def _lines(path: Path, names: set[str], *, syms_of: bool) -> list[tuple[int, str]]:
    """≤ 3 dòng của tệp lân cận: dòng nhắc tên trong phạm vi; tệp chỉ được
    import thì lấy dòng định nghĩa xuất khẩu đầu tiên của nó."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    if syms_of:
        picks = [i + 1 for i, l in enumerate(lines) if any(pat.match(l) for pat in _EXPORTS)]
    else:
        pat = re.compile(r"\b(?:" + "|".join(re.escape(n) for n in sorted(names)) + r")\b") if names else None
        picks = [i + 1 for i, l in enumerate(lines) if pat and pat.search(l)]
    return [(ln, lines[ln - 1].strip()[:MAX_LINE]) for ln in picks[:PER_NEIGHBOUR]]


def _imports(project: Path, rel: str) -> list[str]:
    """Tệp mà ``rel`` import, chỉ lấy tệp có thật trong kho (import tương
    đối JS/TS; tương đối và tuyệt đối theo gói Python)."""
    f = project / rel
    root = project.resolve()
    try:
        body = f.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    out: list[str] = []
    cands: list[Path] = []
    if f.suffix == ".py":
        for m in _IMPORT_PY.finditer(body):
            mod = m.group(1) or m.group(2)
            dots = len(mod) - len(mod.lstrip("."))
            base = f.parents[dots - 1] if dots else project
            cands.append(base / Path(*mod.lstrip(".").split(".")) if mod.lstrip(".") else base)
    else:
        cands += [f.parent / m.group(1) for m in _IMPORT_JS.finditer(body)]
    for c in cands:
        for cand in (c, *(c.with_suffix(e) for e in SOURCE_EXT), *(c / f"index{e}" for e in SOURCE_EXT)):
            if cand.is_file() and cand.suffix in SOURCE_EXT and root in cand.resolve().parents:
                r = Path(os.path.normpath(cand)).relative_to(os.path.normpath(project)).as_posix()
                if r != rel and r not in out:
                    out.append(r)
                break
    return out


def _run_provider(project: Path, seeds: list[str], budget: int, command: str, timeout: int) -> str | None:
    try:
        proc = subprocess.run(
            shlex.split(command), cwd=project, capture_output=True, text=True, timeout=timeout,
            input=json.dumps({"project": str(project), "seeds": seeds, "budget": budget}),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    return proc.stdout.strip()


def _cut(text: str, budget: int, story_id: str) -> str:
    """Cắt ở ranh giới dòng, dòng cuối chỉ chỗ tra bản đầy đủ (R6). Kết quả
    luôn ≤ ``budget`` ký tự."""
    if budget <= 0 or len(text) <= budget:
        return text
    tail = f"\n_(đã cắt — `aisef ctx --story {story_id or '<mã>'}`)_"
    keep = text[: max(budget - len(tail), 0)]
    keep = keep[: keep.rfind("\n")] if "\n" in keep else keep
    return (keep.rstrip() + tail)[:budget]


__all__ = ["HEADING", "prompt_section", "repo_map", "seeds_for"]
