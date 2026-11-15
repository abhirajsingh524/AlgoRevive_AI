"""Impact scoring and severity evaluation according to Contract G6.

Formulas:
- static_norm = rank / 6.0
- call_freq_norm = log10(1 + calls) / log10(1 + max_calls) (0.0 if max_calls == 0)
- mem_norm = peak_mem / max_peak_mem (0.0 if max_peak_mem == 0.0)
- impact_score = 0.40 * runtime_pct + 0.25 * static_norm + 0.20 * call_freq_norm + 0.15 * mem_norm
- static-only fallback: impact_score = 0.6 * static_norm, evidence.source = "static-only"
- severity thresholds:
  >= 0.75: CRITICAL
  >= 0.50: HIGH
  >= 0.25: MEDIUM
  else: LOW
"""

from __future__ import annotations

import math
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class ScoringResult(BaseModel):
    static_score: float
    runtime_score: float
    call_count: int
    runtime_pct: float
    memory_peak_kb: float
    impact_score: float
    severity: str
    evidence: Dict[str, Any] = Field(default_factory=dict)


def compute_static_norm(complexity_rank: int) -> float:
    """Normalize complexity rank (0..6) to 0..1."""
    clamped_rank = max(0, min(6, complexity_rank))
    return round(clamped_rank / 6.0, 4)


def compute_call_freq_norm(call_count: int, max_calls: int) -> float:
    """Normalize call frequency logarithmically."""
    if max_calls <= 0 or call_count <= 0:
        return 0.0
    denom = math.log10(1.0 + max_calls)
    if denom <= 0.0:
        return 0.0
    return round(min(1.0, math.log10(1.0 + call_count) / denom), 4)


def compute_mem_norm(peak_mem_kb: float, max_peak_mem_kb: float) -> float:
    """Normalize peak memory usage to 0..1."""
    if max_peak_mem_kb <= 0.0 or peak_mem_kb <= 0.0:
        return 0.0
    return round(min(1.0, peak_mem_kb / max_peak_mem_kb), 4)


def get_severity(score: float) -> str:
    """Classify impact score into severity tier according to Contract G6."""
    if score >= 0.75:
        return "CRITICAL"
    elif score >= 0.50:
        return "HIGH"
    elif score >= 0.25:
        return "MEDIUM"
    else:
        return "LOW"


def calculate_impact(
    complexity_rank: int,
    runtime_pct: float = 0.0,
    call_count: int = 0,
    max_calls: int = 0,
    memory_peak_kb: float = 0.0,
    max_peak_mem_kb: float = 0.0,
    has_profile: bool = True,
    profile_metadata: Optional[Dict[str, Any]] = None,
) -> ScoringResult:
    """Calculate impact score, severity, and evidence according to Contract G6."""
    static_norm = compute_static_norm(complexity_rank)
    clamped_runtime_pct = round(max(0.0, min(1.0, runtime_pct)), 4)

    if not has_profile:
        # Static-only fallback
        impact_score = round(0.6 * static_norm, 4)
        severity = get_severity(impact_score)
        evidence: Dict[str, Any] = {
            "source": "static-only",
            "static_norm": static_norm,
            "runtime_pct": 0.0,
            "call_freq_norm": 0.0,
            "mem_norm": 0.0,
            "runtime_score": 0.0,
            "static_score": static_norm,
            "impact_score": impact_score,
            "severity": severity,
        }
        return ScoringResult(
            static_score=static_norm,
            runtime_score=0.0,
            call_count=0,
            runtime_pct=0.0,
            memory_peak_kb=0.0,
            impact_score=impact_score,
            severity=severity,
            evidence=evidence,
        )

    call_freq_norm = compute_call_freq_norm(call_count, max_calls)
    mem_norm = compute_mem_norm(memory_peak_kb, max_peak_mem_kb)

    # Contract G6 formula
    impact_score = round(
        0.40 * clamped_runtime_pct
        + 0.25 * static_norm
        + 0.20 * call_freq_norm
        + 0.15 * mem_norm,
        4,
    )
    severity = get_severity(impact_score)

    # Runtime component (composite runtime contribution)
    runtime_weighted = (
        0.40 * clamped_runtime_pct
        + 0.20 * call_freq_norm
        + 0.15 * mem_norm
    )
    runtime_score = round(runtime_weighted / 0.75, 4) if (max_calls > 0 or max_peak_mem_kb > 0 or clamped_runtime_pct > 0) else 0.0

    evidence = {
        "source": "runtime",
        "static_norm": static_norm,
        "runtime_pct": clamped_runtime_pct,
        "call_freq_norm": call_freq_norm,
        "mem_norm": mem_norm,
        "max_calls": max_calls,
        "max_peak_mem_kb": max_peak_mem_kb,
        "runtime_weighted": round(runtime_weighted, 4),
        "runtime_score": runtime_score,
        "static_score": static_norm,
        "impact_score": impact_score,
        "severity": severity,
    }
    if profile_metadata:
        evidence.update(profile_metadata)

    return ScoringResult(
        static_score=static_norm,
        runtime_score=runtime_score,
        call_count=call_count,
        runtime_pct=clamped_runtime_pct,
        memory_peak_kb=round(memory_peak_kb, 2),
        impact_score=impact_score,
        severity=severity,
        evidence=evidence,
    )
