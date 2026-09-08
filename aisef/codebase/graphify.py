"""Graphify CLI adapter — preferred for brownfield projects.

Calls Graphify via CLI (no MCP by default).  First ``build()`` call constructs
the full graph; subsequent ``build(incremental=True)`` updates incrementally.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from .provider import (
    BuildResult,
    CodebaseGraphProvider,
    GraphNode,
    ImpactResult,
    QueryResult,
)

GRAPH_DIR = "graphify-out"
GRAPH_JSON = "graph.json"
GRAPH_REPORT = "GRAPH_REPORT.md"


def _run(args: list[str], cwd: Path, *, timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(
        args, cwd=cwd, capture_output=True, text=True, timeout=timeout,
    )


class GraphifyProvider(CodebaseGraphProvider):
    name = "graphify"

    @classmethod
    def available(cls) -> bool:
        return shutil.which("graphify") is not None

    @classmethod
    def has_graph(cls, project: Path) -> bool:
        return (project / GRAPH_DIR / GRAPH_JSON).is_file()

    def build(self, project: Path, *, incremental: bool = False) -> BuildResult:
        if not self.available():
            return BuildResult(ok=False, error="graphify CLI không có trên PATH")
        try:
            proc = _run(["graphify", "."], cwd=project, timeout=600)
        except subprocess.TimeoutExpired:
            return BuildResult(ok=False, error="graphify timeout (600s)")
        if proc.returncode != 0:
            return BuildResult(ok=False, error=proc.stderr.strip()[:500])

        report = ""
        report_path = project / GRAPH_DIR / GRAPH_REPORT
        if report_path.is_file():
            report = report_path.read_text(encoding="utf-8", errors="replace")

        nodes, edges = 0, 0
        graph_path = project / GRAPH_DIR / GRAPH_JSON
        if graph_path.is_file():
            try:
                g = json.loads(graph_path.read_text(encoding="utf-8"))
                nodes = len(g.get("nodes", []))
                edges = len(g.get("edges", []))
            except (json.JSONDecodeError, OSError):
                pass

        return BuildResult(ok=True, nodes=nodes, edges=edges, report=report)

    def query(self, project: Path, question: str) -> QueryResult:
        if not self.has_graph(project):
            return QueryResult(answer="(đồ thị chưa dựng — chạy `aisef baseline` trước)")
        try:
            proc = _run(["graphify", "query", question], cwd=project)
        except (subprocess.TimeoutExpired, OSError) as e:
            return QueryResult(answer=f"(lỗi: {e})")
        return QueryResult(answer=proc.stdout.strip(), raw=proc.stdout)

    def impact(self, project: Path, targets: list[str]) -> ImpactResult:
        if not self.has_graph(project):
            return ImpactResult(targets=targets, summary="(đồ thị chưa dựng)")
        affected: list[GraphNode] = []
        files: set[str] = set()
        tests: set[str] = set()
        for t in targets:
            try:
                proc = _run(["graphify", "affected", t], cwd=project)
            except (subprocess.TimeoutExpired, OSError):
                continue
            for line in proc.stdout.strip().splitlines():
                line = line.strip()
                if not line or line.startswith("─") or line.startswith("="):
                    continue
                node = GraphNode(id=line, label=line)
                affected.append(node)
                if "test" in line.lower() or line.startswith("test_"):
                    tests.add(line)
                if "/" in line or line.endswith(".py") or line.endswith(".ts"):
                    files.add(line)
        return ImpactResult(
            targets=targets, affected=affected,
            affected_files=sorted(files), affected_tests=sorted(tests),
            summary=f"{len(affected)} nút bị ảnh hưởng bởi {len(targets)} đích",
        )

    def path(self, project: Path, a: str, b: str) -> QueryResult:
        if not self.has_graph(project):
            return QueryResult(answer="(đồ thị chưa dựng)")
        try:
            proc = _run(["graphify", "path", a, b], cwd=project)
        except (subprocess.TimeoutExpired, OSError) as e:
            return QueryResult(answer=f"(lỗi: {e})")
        return QueryResult(answer=proc.stdout.strip(), raw=proc.stdout)

    def repo_map(self, project: Path, seeds: list[str], budget: int = 0) -> str:
        if not self.has_graph(project):
            return ""
        parts: list[str] = []
        for s in seeds[:10]:
            try:
                proc = _run(["graphify", "explain", s], cwd=project)
            except (subprocess.TimeoutExpired, OSError):
                continue
            if proc.stdout.strip():
                parts.append(proc.stdout.strip())
        text = "\n\n".join(parts)
        return text[:budget] if budget else text
