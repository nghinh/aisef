"""Sinh hiến pháp kỹ thuật cho dự án đích.

Một nguồn duy nhất (`kit/rules/*.md`) sinh ra file quy tắc cho từng
client: `CLAUDE.md` cho Claude Code, `AGENTS.md` cho OpenCode và các client
đọc quy ước đó. Viết một lần, phát nhiều nơi — không duy trì ba bản dễ lệch.

Phần theo stack được ghép thêm ở cuối: dự án Python nhắc `ruff`/`mypy`/
`pytest`, dự án React nhắc `tsc`/`eslint`/`vitest`. Nhắc đúng công cụ dự án
thật sự dùng thì agent mới chạy đúng lệnh.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .detect_stack import Stack

RULES_DIR = Path(__file__).parent / "rules"

#: Lệnh kiểm chất lượng theo công nghệ. Chỉ đưa vào khi dự án thật sự dùng.
QUALITY_COMMANDS: dict[str, list[str]] = {
    "python": ["ruff format --check .", "ruff check .", "mypy .", "pytest --cov"],
    "node": ["npm run lint", "npm run typecheck", "npm test"],
    "go": ["gofmt -l .", "go vet ./...", "go test ./..."],
    "rust": ["cargo fmt --check", "cargo clippy", "cargo test"],
    "java": ["./gradlew check"],
    "dotnet": ["dotnet format --verify-no-changes", "dotnet test"],
    "php": ["composer lint", "composer test"],
    "ruby": ["bundle exec rubocop", "bundle exec rspec"],
    "react": ["npm run lint", "npx tsc --noEmit", "npm test"],
    "vue": ["npm run lint", "npx vue-tsc --noEmit", "npm test"],
    "angular": ["npm run lint", "npm test"],
    "svelte": ["npm run lint", "npm run check", "npm test"],
    "flutter": ["dart format --set-exit-if-changed .", "flutter analyze", "flutter test"],
}

#: Client nào đọc file tên gì.
CLIENT_FILES: dict[str, str] = {
    "claude": "CLAUDE.md",
    "opencode": "AGENTS.md",
}


@dataclass
class Constitution:
    principles: str
    must_never: str

    @classmethod
    def load(cls, source_dir: Path = RULES_DIR) -> Constitution:
        return cls(
            principles=(source_dir / "principles.md").read_text(encoding="utf-8"),
            must_never=(source_dir / "must_never.md").read_text(encoding="utf-8"),
        )

    def render(self, project_name: str, stack: Stack) -> str:
        parts = [
            f"# Quy tắc kỹ thuật — {project_name}",
            "",
            "> Sinh bởi `aisdlc setup`. **Không sửa tay** — sửa ở",
            "> `aisdlc/kit/rules/` rồi chạy lại, nếu không lần cài sau sẽ đè mất.",
            "",
            self.principles.strip(),
            "",
            self.must_never.strip(),
            "",
            self._stack_section(stack),
        ]
        return "\n".join(p for p in parts if p is not None).rstrip() + "\n"

    def _stack_section(self, stack: Stack) -> str:
        lines = ["# Công nghệ của dự án này", ""]

        described = {
            k: v for k, v in stack.as_dict().items() if v and k != "undetermined"
        }
        if described:
            for category, values in described.items():
                lines.append(f"- **{category}**: {', '.join(values)}")
        else:
            lines.append("- chưa xác định được từ `docs/requirements.md`")

        if stack.undetermined:
            lines += [
                "",
                f"Chưa chốt: {', '.join(stack.undetermined)}. Pha kiến trúc quyết —",
                "**không tự chọn** trong lúc viết story.",
            ]

        commands: list[str] = []
        for values in described.values():
            for value in values:
                for cmd in QUALITY_COMMANDS.get(value, []):
                    if cmd not in commands:
                        commands.append(cmd)

        if commands:
            lines += [
                "",
                "## Cổng chất lượng",
                "",
                "Chạy đủ và phải xanh trước khi coi story là xong:",
                "",
                "```bash",
                *commands,
                "```",
            ]

        if stack.has_ui:
            lines += [
                "",
                "## Story có giao diện",
                "",
                "Story nào có `screen_id` phải đi qua hai nửa của bước map mockup:",
                "nạp lát cắt hợp đồng của đúng màn hình đó trước khi viết, và đối",
                "chiếu màn hình thật với hợp đồng sau khi viết. Thiếu component mà",
                "hợp đồng đã hứa thì story không đạt.",
            ]

        return "\n".join(lines)


def write_for_project(
    project: Path | str,
    project_name: str,
    stack: Stack,
    *,
    clients: list[str] | None = None,
    source_dir: Path = RULES_DIR,
) -> list[Path]:
    """Ghi file quy tắc cho từng client. Trả danh sách đường dẫn đã ghi."""
    constitution = Constitution.load(source_dir)
    text = constitution.render(project_name, stack)

    written = []
    for client in clients or list(CLIENT_FILES):
        filename = CLIENT_FILES.get(client)
        if not filename:
            continue
        path = Path(project) / filename
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return written
