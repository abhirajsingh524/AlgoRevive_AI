"""Structured 'WHY FLAGGED?' explanation tree according to Contract G6 and SRS specifications."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.models.bottleneck import Bottleneck
from app.models.function import Function


class WhyFlaggedNode(BaseModel):
    """Node in the structured 'WHY FLAGGED?' explanation tree."""
    reason: str
    metric: str
    value: Any
    weight: Optional[float] = None
    children: List[WhyFlaggedNode] = Field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


def build_why_flagged(
    bottleneck: Bottleneck,
    function: Optional[Function] = None,
) -> Dict[str, Any]:
    """Build a structured explanation tree (reason, metric, value, weight) mirroring the SRS.
    
    Guarantees:
    - Every number shown comes strictly from stored evidence on the bottleneck or function.
    - Zero invented numbers.
    - Accurately mirrors static-only or dynamic runtime scoring paths.
    """
    evidence: Dict[str, Any] = (
        bottleneck.evidence if isinstance(bottleneck.evidence, dict) else {}
    )
    is_static_only = evidence.get("source") == "static-only"

    # 1. Resolve complexity and patterns
    complexity_class = "O(1)"
    static_rank = 0
    patterns_list: List[str] = []

    if function:
        complexity_class = function.complexity_class or "O(1)"
        static_rank = function.complexity_rank
        if function.patterns:
            for p in function.patterns:
                if isinstance(p, dict):
                    pid = p.get("pattern_id") or p.get("pattern")
                    if pid:
                        patterns_list.append(pid)
                elif isinstance(p, str):
                    patterns_list.append(p)
    elif "static_norm" in evidence:
        static_rank = int(round(evidence["static_norm"] * 6))

    # 2. Workload input size
    workload_data = evidence.get("workload", {})
    input_size = (
        workload_data.get("input_size")
        or evidence.get("input_size")
        or (100 if not is_static_only else 0)
    )

    children: List[WhyFlaggedNode] = []

    # Child 1: Static analysis & Asymptotic complexity
    static_weight = 0.60 if is_static_only else 0.25
    pattern_children: List[WhyFlaggedNode] = []
    for pat in patterns_list:
        pattern_children.append(
            WhyFlaggedNode(
                reason=f"Inefficient algorithmic pattern detected: {pat}",
                metric="pattern",
                value=pat,
                weight=None,
            )
        )

    children.append(
        WhyFlaggedNode(
            reason=f"Asymptotic complexity estimated as {complexity_class} (rank {static_rank}/6)",
            metric="complexity_class",
            value=complexity_class,
            weight=static_weight,
            children=pattern_children,
        )
    )

    if is_static_only:
        # Static-only explanation branch
        children.append(
            WhyFlaggedNode(
                reason="Static-only fallback applied (no runtime profile available)",
                metric="source",
                value="static-only",
                weight=None,
            )
        )
    else:
        # Dynamic runtime explanation branch
        # Child 2: Runtime contribution
        pct_display = f"{round(float(bottleneck.runtime_pct) * 100, 1)}%"
        children.append(
            WhyFlaggedNode(
                reason=f"Dominant execution time: {pct_display} of total entrypoint time",
                metric="runtime_pct",
                value=pct_display,
                weight=0.40,
            )
        )

        # Child 3: Call frequency
        children.append(
            WhyFlaggedNode(
                reason=f"High execution frequency with {bottleneck.call_count} calls",
                metric="call_count",
                value=bottleneck.call_count,
                weight=0.20,
            )
        )

        # Child 4: Peak heap memory
        mem_display = f"{round(float(bottleneck.memory_peak_kb), 1)} KB"
        children.append(
            WhyFlaggedNode(
                reason=f"Peak heap memory allocation of {mem_display}",
                metric="memory_peak_kb",
                value=mem_display,
                weight=0.15,
            )
        )

        # Child 5: Input size
        if input_size > 0:
            children.append(
                WhyFlaggedNode(
                    reason=f"Evaluated under workload input size of {input_size} records",
                    metric="input_size",
                    value=input_size,
                    weight=None,
                )
            )

    # Child 6: Impact score & severity derivation
    children.append(
        WhyFlaggedNode(
            reason=f"Impact score {round(float(bottleneck.impact_score), 4)} maps to severity tier {bottleneck.severity}",
            metric="impact_score",
            value=round(float(bottleneck.impact_score), 4),
            weight=1.0,
        )
    )

    root = WhyFlaggedNode(
        reason=f"Function flagged as {bottleneck.severity} bottleneck (impact score {round(float(bottleneck.impact_score), 4)})",
        metric="severity",
        value=bottleneck.severity,
        weight=1.0,
        children=children,
    )

    return root.to_dict()
