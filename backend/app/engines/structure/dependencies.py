"""Transitive caller and affected dependency analysis for bottlenecks."""

from __future__ import annotations

from collections import deque
import json
from typing import Any, Dict, List, Optional, Set
import networkx as nx

from app.services.storage import StorageService


def analyze_affected_functions(
    storage: StorageService,
    repository_id: str,
    bottleneck_function_id: str,
    workload_spec: Optional[Dict[str, Any]] = None,
    call_graph_dict: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Find transitive callers of a bottleneck with depth using the saved call graph.
    
    Flags which callers are covered by entrypoints in the workload spec.
    Returns list of dicts sorted by depth ascending:
    [
        {
            "function_id": str,
            "name": str,
            "qualified_name": str,
            "file_path": str,
            "depth": int,
            "covered_by_workload": bool,
        },
        ...
    ]
    """
    if call_graph_dict is None:
        storage_key = f"repos/{repository_id}/call_graph.json"
        if not storage.exists(storage_key):
            return []
        try:
            raw_bytes = storage.get_file(storage_key)
            call_graph_dict = json.loads(raw_bytes.decode("utf-8"))
        except Exception:
            return []

    if not call_graph_dict:
        return []

    nodes: List[Dict[str, Any]] = call_graph_dict.get("nodes", [])
    edges: List[Dict[str, Any]] = call_graph_dict.get("edges", [])

    node_map: Dict[str, Dict[str, Any]] = {n["id"]: n for n in nodes if "id" in n}

    # Build DiGraph: source -> target
    g = nx.DiGraph()
    for n in nodes:
        g.add_node(n["id"], **n)
    for e in edges:
        g.add_edge(e["source"], e["target"])

    if bottleneck_function_id not in g:
        return []

    # Find entrypoint function targets from workload spec
    workload_entrypoints: Set[str] = set()
    if workload_spec and "entrypoints" in workload_spec:
        for ep in workload_spec["entrypoints"]:
            fn_target = ep.get("function", "")
            if fn_target:
                workload_entrypoints.add(fn_target)
                if ":" in fn_target:
                    workload_entrypoints.add(fn_target.split(":")[-1])

    # Transitive callers: reverse BFS from bottleneck_function_id
    # In g, an edge S -> T means S calls T. Predecessors of T are its callers.
    visited_depth: Dict[str, int] = {}
    queue = deque([(bottleneck_function_id, 0)])

    while queue:
        curr_id, depth = queue.popleft()
        for caller_id in g.predecessors(curr_id):
            if caller_id not in visited_depth and caller_id != bottleneck_function_id:
                visited_depth[caller_id] = depth + 1
                queue.append((caller_id, depth + 1))

    affected_list: List[Dict[str, Any]] = []
    for caller_id, depth in visited_depth.items():
        node_info = node_map.get(caller_id, {})
        fname = node_info.get("name", "")
        fqual = node_info.get("qualified_name", "")
        fpath = node_info.get("file_path", "")

        is_covered = (
            fqual in workload_entrypoints
            or fname in workload_entrypoints
            or any(
                ep.endswith(f":{fname}") or ep == fqual
                for ep in workload_entrypoints
            )
        )

        affected_list.append({
            "function_id": caller_id,
            "name": fname,
            "qualified_name": fqual,
            "file_path": fpath,
            "depth": depth,
            "covered_by_workload": is_covered,
        })

    # Sort by depth ascending, then name
    affected_list.sort(key=lambda x: (x["depth"], x["name"]))
    return affected_list
