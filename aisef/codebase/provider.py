"""CodebaseGraphProvider — codebase knowledge graph abstraction.

The framework is not coupled to any specific tool: the provider is an
interface, Graphify and Basic are two implementations.  When the project has a
graph, queries go through it; otherwise fall back to grep + static imports —
still works, just coarser.
"""

from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GraphNode:
    """A node in the graph: function, class, module, file, DB table, etc."""
    id: str
    kind: str = ""
    file: str = ""
    line: int = 0
    label: str = ""


@dataclass
class GraphEdge:
    source: str
    target: str
    kind: str = ""
    confidence: str = "extracted"


@dataclass
class QueryResult:
    """Result of a natural-language or structured query."""
    answer: str = ""
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    raw: str = ""


@dataclass
class ImpactResult:
    """Impact scope when changing one or more targets."""
    targets: list[str] = field(default_factory=list)
    affected: list[GraphNode] = field(default_factory=list)
    affected_files: list[str] = field(default_factory=list)
    affected_tests: list[str] = field(default_factory=list)
    summary: str = ""


@dataclass
class BuildResult:
    ok: bool = True
    nodes: int = 0
    edges: int = 0
    error: str = ""
    report: str = ""


class CodebaseGraphProvider(ABC):
    """Codebase graph provider interface."""

    name: str = ""

    @abstractmethod
    def build(self, project: Path, *, incremental: bool = False) -> BuildResult:
        """Build (or incrementally update) the graph."""

    @abstractmethod
    def query(self, project: Path, question: str) -> QueryResult:
        """Query using natural language."""

    @abstractmethod
    def impact(self, project: Path, targets: list[str]) -> ImpactResult:
        """Impact scope: nodes/files/tests affected by changes to targets."""

    @abstractmethod
    def path(self, project: Path, a: str, b: str) -> QueryResult:
        """Shortest path between two entities."""

    @classmethod
    @abstractmethod
    def available(cls) -> bool:
        """Whether this provider is available on this machine."""

    def repo_map(self, project: Path, seeds: list[str], budget: int = 0) -> str:
        """Code map around seeds — defaults to query, subclasses override."""
        if not seeds:
            return ""
        r = self.query(project, f"code structure around: {', '.join(seeds[:10])}")
        text = r.answer or r.raw
        return text[:budget] if budget else text


def resolve(project: Path, *, preference: str = "auto") -> CodebaseGraphProvider:
    """Select provider: preference="graphify"|"basic"|"auto".

    auto: Graphify if CLI exists and graph is built; otherwise Basic.
    MCP not enabled by default — CLI/on-demand only.
    """
    from .basic import BasicProvider
    from .graphify import GraphifyProvider

    if preference == "graphify":
        if not GraphifyProvider.available():
            raise RuntimeError("graphify CLI không có trên PATH — cài: uv tool install graphifyy")
        return GraphifyProvider()
    if preference == "basic":
        return BasicProvider()

    if GraphifyProvider.available() and GraphifyProvider.has_graph(project):
        return GraphifyProvider()
    return BasicProvider()
