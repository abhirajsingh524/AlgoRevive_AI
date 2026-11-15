"""Call graph builder and analyzer using NetworkX.

Builds a directed graph of function calls across files, resolves calls by qualified
names and imports (best effort, unresolved calls are ignored), computes callers,
callees, fan-in, and fan-out, and formats for storage.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import networkx as nx

from app.services.storage import StorageService


@dataclass
class GraphNode:
    id: str
    name: str
    qualified_name: str
    file_id: str
    file_path: str
    lineno: int
    end_lineno: int
    severity: str
    complexity_class: str
    complexity_rank: int
    fan_in: int = 0
    fan_out: int = 0
    callers: List[str] = field(default_factory=list)
    callees: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class GraphEdge:
    source: str
    target: str
    call_count: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CallGraphResult:
    repository_id: str
    node_count: int
    edge_count: int
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "repository_id": self.repository_id,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "nodes": self.nodes,
            "edges": self.edges,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


class CallGraphBuilder:
    """Constructs and analyzes cross-file function call graphs."""

    def build_graph(
        self,
        repository_id: str,
        functions_data: List[Dict[str, Any]],
        file_imports: Dict[str, List[Dict[str, Any]]],
    ) -> CallGraphResult:
        """Build directed call graph from extracted functions and file imports.

        Args:
            repository_id: UUID of repository
            functions_data: List of function dictionaries with fields:
                id, name, qualified_name, file_id, file_path, lineno, end_lineno,
                severity, complexity_class, complexity_rank, calls
            file_imports: Mapping of file_path to list of ImportInfo dicts
                (module, name, alias)
        """
        g = nx.DiGraph()

        # Index functions for fast resolution
        # 1. By ID
        funcs_by_id: Dict[str, Dict[str, Any]] = {}
        # 2. By file_path -> name -> id
        funcs_by_file_and_name: Dict[str, Dict[str, str]] = {}
        # 3. By module_path -> name -> id
        funcs_by_module_and_name: Dict[str, Dict[str, str]] = {}
        # 4. Global by name -> list of ids
        funcs_by_name: Dict[str, List[str]] = {}

        for fn in functions_data:
            fn_id = str(fn["id"])
            funcs_by_id[fn_id] = fn

            fpath = fn.get("file_path", "")
            fname = fn.get("name", "")

            # File index
            if fpath not in funcs_by_file_and_name:
                funcs_by_file_and_name[fpath] = {}
            funcs_by_file_and_name[fpath][fname] = fn_id

            # Module path index (e.g. "demo/operations.py" -> "demo.operations")
            mod_path = fpath.replace("\\", "/")
            if mod_path.endswith(".py"):
                mod_path = mod_path[:-3]
            mod_dotted = mod_path.replace("/", ".")
            if mod_dotted not in funcs_by_module_and_name:
                funcs_by_module_and_name[mod_dotted] = {}
            funcs_by_module_and_name[mod_dotted][fname] = fn_id

            # Also index package root if __init__.py
            if mod_dotted.endswith(".__init__"):
                pkg_dotted = mod_dotted[:-9]
                if pkg_dotted not in funcs_by_module_and_name:
                    funcs_by_module_and_name[pkg_dotted] = {}
                funcs_by_module_and_name[pkg_dotted][fname] = fn_id

            # Global name index
            funcs_by_name.setdefault(fname, []).append(fn_id)

            # Add node to graph
            g.add_node(
                fn_id,
                name=fname,
                qualified_name=fn.get("qualified_name", fname),
                file_id=fn.get("file_id", ""),
                file_path=fpath,
                lineno=fn.get("lineno", 1),
                end_lineno=fn.get("end_lineno", 1),
                severity=fn.get("severity", "LOW"),
                complexity_class=fn.get("complexity_class", "O(1)"),
                complexity_rank=fn.get("complexity_rank", 0),
            )

        # Build edges by resolving calls
        edge_counts: Dict[Tuple[str, str], int] = {}

        for caller_id, fn in funcs_by_id.items():
            caller_file = fn.get("file_path", "")
            caller_name = fn.get("name", "")
            raw_calls: List[str] = fn.get("calls", []) or []
            imports = file_imports.get(caller_file, [])

            for call_str in raw_calls:
                target_id = self._resolve_call(
                    call_str=call_str,
                    caller_id=caller_id,
                    caller_file=caller_file,
                    caller_name=caller_name,
                    imports=imports,
                    funcs_by_file_and_name=funcs_by_file_and_name,
                    funcs_by_module_and_name=funcs_by_module_and_name,
                    funcs_by_name=funcs_by_name,
                )

                if target_id and target_id in funcs_by_id:
                    edge_key = (caller_id, target_id)
                    edge_counts[edge_key] = edge_counts.get(edge_key, 0) + 1

        for (src, tgt), count in edge_counts.items():
            g.add_edge(src, tgt, call_count=count)

        # Compute graph metrics (fan-in, fan-out, callers, callees)
        nodes_list: List[Dict[str, Any]] = []
        for node_id in g.nodes():
            node_data = g.nodes[node_id]
            fan_in = g.in_degree(node_id)
            fan_out = g.out_degree(node_id)
            callers = list(g.predecessors(node_id))
            callees = list(g.successors(node_id))

            graph_node = GraphNode(
                id=node_id,
                name=node_data["name"],
                qualified_name=node_data["qualified_name"],
                file_id=node_data["file_id"],
                file_path=node_data["file_path"],
                lineno=node_data["lineno"],
                end_lineno=node_data["end_lineno"],
                severity=node_data["severity"],
                complexity_class=node_data["complexity_class"],
                complexity_rank=node_data["complexity_rank"],
                fan_in=fan_in,
                fan_out=fan_out,
                callers=callers,
                callees=callees,
            )
            nodes_list.append(graph_node.to_dict())

        edges_list: List[Dict[str, Any]] = []
        for u, v, data in g.edges(data=True):
            edges_list.append(
                GraphEdge(
                    source=u,
                    target=v,
                    call_count=data.get("call_count", 1),
                ).to_dict()
            )

        return CallGraphResult(
            repository_id=repository_id,
            node_count=len(nodes_list),
            edge_count=len(edges_list),
            nodes=nodes_list,
            edges=edges_list,
        )

    def _resolve_call(
        self,
        call_str: str,
        caller_id: str,
        caller_file: str,
        caller_name: str,
        imports: List[Dict[str, Any]],
        funcs_by_file_and_name: Dict[str, Dict[str, str]],
        funcs_by_module_and_name: Dict[str, Dict[str, str]],
        funcs_by_name: Dict[str, List[str]],
    ) -> Optional[str]:
        """Resolve a function call to a target function id, or None if unresolved."""
        # 1. Direct self-call / recursion
        if call_str == caller_name:
            return caller_id

        # 2. Same-file resolution
        if caller_file in funcs_by_file_and_name:
            if call_str in funcs_by_file_and_name[caller_file]:
                return funcs_by_file_and_name[caller_file][call_str]

        # 3. Check imports from caller's file
        for imp in imports:
            imp_name = imp.get("name")
            alias = imp.get("alias") or imp_name
            module = imp.get("module") or ""

            # Case: from module import func
            if alias == call_str:
                # Target function name is imp_name
                # Check funcs_by_module_and_name
                if module in funcs_by_module_and_name:
                    if imp_name in funcs_by_module_and_name[module]:
                        return funcs_by_module_and_name[module][imp_name]

            # Case: import module as m; m.func()
            if "." in call_str:
                parts = call_str.split(".", 1)
                prefix, member = parts[0], parts[1]
                if alias == prefix:
                    target_mod = (f"{module}.{imp_name}" if module else imp_name) or ""
                    if target_mod in funcs_by_module_and_name:
                        if member in funcs_by_module_and_name[target_mod]:
                            return funcs_by_module_and_name[target_mod][member]

        # 4. Fallback: single unambiguous match across entire repo
        if "." not in call_str and call_str in funcs_by_name:
            candidates = funcs_by_name[call_str]
            if len(candidates) == 1:
                return candidates[0]

        return None


def save_call_graph(
    storage: StorageService,
    call_graph: CallGraphResult,
) -> str:
    """Save call graph JSON to repos/{repository_id}/call_graph.json."""
    storage_key = f"repos/{call_graph.repository_id}/call_graph.json"
    data = call_graph.to_json().encode("utf-8")
    storage.put_file(storage_key, data)
    return storage_key
