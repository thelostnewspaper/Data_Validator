"""
Cycle detection for dependency graphs.

Reused by the Airflow pack (task dependencies) and the dbt pack
(ref/source resolution). Uses DFS-based cycle detection.
"""

from __future__ import annotations

from typing import Sequence


def build_dependency_graph(
    nodes: Sequence[str],
    edges: Sequence[tuple[str, str]],
) -> dict[str, list[str]]:
    """
    Build an adjacency-list representation of a directed graph.

    Args:
        nodes: List of node identifiers.
        edges: List of (from, to) directed edges.

    Returns:
        Dict mapping each node to its list of successors.
    """
    graph: dict[str, list[str]] = {node: [] for node in nodes}

    for src, dst in edges:
        if src not in graph:
            graph[src] = []
        graph[src].append(dst)
        # Ensure dst exists in the graph even if it has no outgoing edges
        if dst not in graph:
            graph[dst] = []

    return graph


def has_circular_dependencies(
    graph: dict[str, list[str]],
) -> list[list[str]]:
    """
    Detect all cycles in a directed graph using DFS.

    Args:
        graph: Adjacency-list graph (node -> list of successors).

    Returns:
        List of cycles found, where each cycle is a list of node IDs
        forming the cycle. Empty list if the graph is acyclic.
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {node: WHITE for node in graph}
    path: list[str] = []
    cycles: list[list[str]] = []

    def dfs(node: str) -> None:
        color[node] = GRAY
        path.append(node)

        for neighbor in graph.get(node, []):
            if color.get(neighbor, WHITE) == GRAY:
                # Found a cycle — extract it from the path
                cycle_start = path.index(neighbor)
                cycle = path[cycle_start:] + [neighbor]
                cycles.append(cycle)
            elif color.get(neighbor, WHITE) == WHITE:
                dfs(neighbor)

        path.pop()
        color[node] = BLACK

    for node in graph:
        if color[node] == WHITE:
            dfs(node)

    return cycles


def topological_sort(
    graph: dict[str, list[str]],
) -> list[str] | None:
    """
    Topologically sort a directed acyclic graph.

    Args:
        graph: Adjacency-list graph (node -> list of successors).

    Returns:
        Topologically sorted list of nodes, or None if the graph has cycles.
    """
    # Compute in-degrees
    in_degree: dict[str, int] = {node: 0 for node in graph}
    for node in graph:
        for neighbor in graph[node]:
            in_degree[neighbor] = in_degree.get(neighbor, 0) + 1

    # Start with nodes that have no incoming edges
    queue: list[str] = [node for node in graph if in_degree[node] == 0]
    result: list[str] = []

    while queue:
        node = queue.pop(0)
        result.append(node)
        for neighbor in graph[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(result) != len(graph):
        return None  # Graph has cycles

    return result
