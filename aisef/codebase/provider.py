"""CodebaseGraphProvider — trừu tượng hoá đồ thị tri thức mã nguồn.

Framework không gắn cứng vào bất kỳ công cụ nào: nhà cung cấp là giao diện,
Graphify và Basic là hai bản cài. Khi dự án có đồ thị thì câu truy vấn đi
qua đó; không có thì lùi về grep + import tĩnh — vẫn hoạt động, chỉ thô hơn.
"""

from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GraphNode:
    """Một nút trong đồ thị: hàm, lớp, module, file, bảng DB…"""
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
    """Kết quả truy vấn tự nhiên hoặc có cấu trúc."""
    answer: str = ""
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    raw: str = ""


@dataclass
class ImpactResult:
    """Phạm vi ảnh hưởng khi thay đổi một hoặc nhiều đích."""
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
    """Giao diện nhà cung cấp đồ thị mã nguồn."""

    name: str = ""

    @abstractmethod
    def build(self, project: Path, *, incremental: bool = False) -> BuildResult:
        """Dựng (hoặc cập nhật tăng dần) đồ thị."""

    @abstractmethod
    def query(self, project: Path, question: str) -> QueryResult:
        """Hỏi bằng ngôn ngữ tự nhiên."""

    @abstractmethod
    def impact(self, project: Path, targets: list[str]) -> ImpactResult:
        """Phạm vi ảnh hưởng: nút/file/test bị ảnh hưởng bởi thay đổi ở targets."""

    @abstractmethod
    def path(self, project: Path, a: str, b: str) -> QueryResult:
        """Đường đi ngắn nhất giữa hai thực thể."""

    @classmethod
    @abstractmethod
    def available(cls) -> bool:
        """Nhà cung cấp có dùng được trên máy này không."""

    def repo_map(self, project: Path, seeds: list[str], budget: int = 0) -> str:
        """Bản đồ mã quanh seeds — mặc định dùng query, lớp con ghi đè."""
        if not seeds:
            return ""
        r = self.query(project, f"code structure around: {', '.join(seeds[:10])}")
        text = r.answer or r.raw
        return text[:budget] if budget else text


def resolve(project: Path, *, preference: str = "auto") -> CodebaseGraphProvider:
    """Chọn nhà cung cấp: preference="graphify"|"basic"|"auto".

    auto: Graphify nếu có CLI và đã dựng đồ thị; ngược lại Basic.
    Không bật MCP mặc định — chỉ CLI/on-demand.
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
