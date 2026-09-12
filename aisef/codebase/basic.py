"""BasicProvider — fallback when Graphify is not available.

Uses grep + static import analysis.  Always available, no extra install needed.
Coarser than Graphify but sufficient for basic impact analysis.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from .provider import (
    BuildResult,
    CodebaseGraphProvider,
    GraphNode,
    ImpactResult,
    QueryResult,
)

_PY_IMPORT = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", re.MULTILINE)
_JS_IMPORT = re.compile(r"""(?:import\s+.*?from\s+['"]([^'"]+)['"]|require\s*\(\s*['"]([^'"]+)['"]\s*\))""")
_TEST_PAT = re.compile(r"test[_/]|_test\.|\.test\.|\.spec\.|tests/|__tests__/", re.IGNORECASE)


def _source_files(project: Path, limit: int = 5000) -> list[Path]:
    exts = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".rb", ".php"}
    found: list[Path] = []
    for root, dirs, files in os.walk(project):
        dirs[:] = [d for d in dirs if d not in {
            "node_modules", ".git", "__pycache__", ".venv", "venv",
            "dist", "build", ".next", ".nuxt", "target", "vendor",
            "graphify-out", "_bmad-output", ".aisef",
        }]
        for f in files:
            if Path(f).suffix in exts:
                found.append(Path(root) / f)
                if len(found) >= limit:
                    return found
    return found


def _imports_py(text: str) -> list[str]:
    return [m.group(1) or m.group(2) for m in _PY_IMPORT.finditer(text)]


def _imports_js(text: str) -> list[str]:
    return [m.group(1) or m.group(2) for m in _JS_IMPORT.finditer(text)]


def _parse_imports(path: Path, text: str) -> list[str]:
    if path.suffix == ".py":
        return _imports_py(text)
    if path.suffix in {".ts", ".tsx", ".js", ".jsx"}:
        return _imports_js(text)
    return []


class BasicProvider(CodebaseGraphProvider):
    name = "basic"

    @classmethod
    def available(cls) -> bool:
        return True

    def build(self, project: Path, *, incremental: bool = False) -> BuildResult:
        files = _source_files(project)
        import_graph: dict[str, list[str]] = {}
        for f in files:
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            rel = str(f.relative_to(project))
            import_graph[rel] = _parse_imports(f, text)
        return BuildResult(
            ok=True, nodes=len(files),
            edges=sum(len(v) for v in import_graph.values()),
        )

    def query(self, project: Path, question: str) -> QueryResult:
        return QueryResult(
            answer="(basic provider — dùng grep thay cho truy vấn đồ thị)",
        )

    def impact(self, project: Path, targets: list[str]) -> ImpactResult:
        files = _source_files(project)
        file_contents: dict[str, str] = {}
        for f in files:
            try:
                file_contents[str(f.relative_to(project))] = f.read_text(
                    encoding="utf-8", errors="replace")
            except OSError:
                continue

        affected_files: set[str] = set()
        affected_tests: set[str] = set()
        for target in targets:
            affected_files.add(target)
            if _TEST_PAT.search(target):
                affected_tests.add(target)

        # reverse imports: files importing the targets
        for target in targets:
            mod = target.replace("/", ".").replace(".py", "").replace(".ts", "")
            base = Path(target).stem
            for rel, text in file_contents.items():
                if rel in affected_files:
                    continue
                imports = _parse_imports(project / rel, text)
                if any(mod in imp or base == imp.rsplit(".", 1)[-1] for imp in imports):
                    affected_files.add(rel)
                    if _TEST_PAT.search(rel):
                        affected_tests.add(rel)

        return ImpactResult(
            targets=targets,
            affected=[GraphNode(id=f, file=f) for f in sorted(affected_files)],
            affected_files=sorted(affected_files),
            affected_tests=sorted(affected_tests),
            summary=f"{len(affected_files)} file bị ảnh hưởng (grep + import tĩnh)",
        )

    def path(self, project: Path, a: str, b: str) -> QueryResult:
        return QueryResult(answer="(basic provider không hỗ trợ path — cài graphify)")
