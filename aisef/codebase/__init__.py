"""Codebase knowledge graph — abstraction, providers, brownfield detection."""

from .provider import (
    BuildResult,
    CodebaseGraphProvider,
    GraphEdge,
    GraphNode,
    ImpactResult,
    QueryResult,
    resolve,
)

__all__ = [
    "BuildResult",
    "CodebaseGraphProvider",
    "GraphEdge",
    "GraphNode",
    "ImpactResult",
    "QueryResult",
    "resolve",
]
