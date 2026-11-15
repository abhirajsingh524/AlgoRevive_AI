"""Bottleneck detection and ranking orchestrator."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.engines.bottleneck.scorer import calculate_impact
from app.engines.structure.dependencies import analyze_affected_functions
from app.models.bottleneck import Bottleneck
from app.models.file import File
from app.models.function import Function
from app.services.storage import StorageService

logger = get_logger("bottleneck_detector")


class BottleneckDetector:
    """Orchestrates bottleneck detection, scoring, and storage for an analysis run."""

    def __init__(self, db: Session, storage: StorageService):
        self.db = db
        self.storage = storage

    def detect_and_save(
        self,
        analysis_run_id: str,
        repository_id: str,
        workload_spec: Optional[Dict[str, Any]] = None,
    ) -> List[Bottleneck]:
        """Detect bottlenecks for the given analysis run and save them to the database.
        
        Enforces Contract G6:
        - Only functions with impact_score >= 0.10 are saved.
        - Idempotently replaces any existing bottlenecks for this analysis run.
        """
        # 1. Fetch functions and files for this repository
        functions = (
            self.db.query(Function)
            .filter(Function.repository_id == repository_id)
            .all()
        )
        files = (
            self.db.query(File)
            .filter(File.repository_id == repository_id)
            .all()
        )
        file_map: Dict[str, str] = {f.id: f.path for f in files}

        # Load call graph for affected function analysis
        call_graph_key = f"repos/{repository_id}/call_graph.json"
        call_graph_data: Optional[Dict[str, Any]] = None
        if self.storage.exists(call_graph_key):
            try:
                call_graph_data = json.loads(self.storage.get_file(call_graph_key).decode("utf-8"))
            except Exception as e:
                logger.warning(f"Could not load call graph from {call_graph_key}: {e}")

        # 2. Check if runtime profile exists
        profile_key = f"runs/{analysis_run_id}/profile.json"
        has_profile = self.storage.exists(profile_key)
        profile_data: Optional[Dict[str, Any]] = None

        if has_profile:
            try:
                raw_bytes = self.storage.get_file(profile_key)
                profile_data = json.loads(raw_bytes.decode("utf-8"))
            except Exception as e:
                logger.warning(f"Could not load profile from {profile_key}: {e}; falling back to static-only")
                has_profile = False

        # 3. Extract runtime metrics per function if profile exists
        # Map: function_id -> {runtime_pct, call_count, memory_peak_kb, ep_target, cumtime, total_ep_time}
        func_runtime_info: Dict[str, Dict[str, Any]] = {}

        if has_profile and profile_data and "entrypoints" in profile_data:
            entrypoints = profile_data.get("entrypoints", {})

            for ep_key, ep_val in entrypoints.items():
                if ep_val.get("status") != "success":
                    continue

                measurements = ep_val.get("measurements", [])
                if not measurements:
                    continue

                # Use the measurement with the largest size n (where algorithmic complexity manifests)
                largest_m = max(measurements, key=lambda m: m.get("n", 0))
                largest_n = largest_m.get("n", 0)
                ep_runtime_s = float(largest_m.get("runtime_s", 0.0))
                ep_peak_mem_kb = float(largest_m.get("peak_memory_kb", 0.0))
                top_functions = largest_m.get("top_functions", [])

                # Total entrypoint time
                max_top_cumtime = max((float(tf.get("cumulative_time", 0.0)) for tf in top_functions), default=0.0)
                total_ep_time = max(ep_runtime_s, max_top_cumtime, 1e-9)

                ep_mod = ep_key.split(":")[0] if ":" in ep_key else ""
                ep_func_name = ep_key.split(":")[-1] if ":" in ep_key else ep_key

                for fn in functions:
                    fn_path = file_map.get(fn.file_id, "").replace("\\", "/").lstrip("/")
                    matched_tf: Optional[Dict[str, Any]] = None

                    for tf in top_functions:
                        tf_file = tf.get("file", "").replace("\\", "/").lstrip("/")
                        tf_name = tf.get("function", "")

                        file_match = (
                            fn_path == tf_file
                            or fn_path.endswith(tf_file)
                            or tf_file.endswith(fn_path)
                            or (ep_mod and ep_mod.replace(".", "/") in fn_path)
                        )
                        name_match = (fn.name == tf_name)

                        if file_match and name_match:
                            matched_tf = tf
                            break

                    # Also check if fn is the entrypoint target itself
                    is_ep_func = (fn.name == ep_func_name and (
                        ep_mod.replace(".", "/") in fn_path or fn_path.endswith(ep_mod.replace(".", "/") + ".py")
                    ))

                    if matched_tf or is_ep_func:
                        cumtime = float(matched_tf.get("cumulative_time", ep_runtime_s)) if matched_tf else ep_runtime_s
                        calls = int(matched_tf.get("calls", 1)) if matched_tf else 1
                        runtime_pct = min(1.0, max(0.0, cumtime / total_ep_time))

                        current_best = func_runtime_info.get(fn.id)
                        if not current_best or runtime_pct > current_best["runtime_pct"]:
                            func_runtime_info[fn.id] = {
                                "runtime_pct": runtime_pct,
                                "call_count": calls,
                                "memory_peak_kb": ep_peak_mem_kb,
                                "profile_entrypoint": ep_key,
                                "cumulative_time": cumtime,
                                "total_entrypoint_time": total_ep_time,
                                "input_size": largest_n,
                            }

        # 4. Compute global maximums for normalization
        max_calls = max((info["call_count"] for info in func_runtime_info.values()), default=0)
        max_peak_mem_kb = max((info["memory_peak_kb"] for info in func_runtime_info.values()), default=0.0)

        # 5. Score every function
        scored_bottlenecks: List[Bottleneck] = []

        for fn in functions:
            r_info = func_runtime_info.get(fn.id, {})
            runtime_pct = r_info.get("runtime_pct", 0.0)
            call_count = r_info.get("call_count", 0)
            memory_peak_kb = r_info.get("memory_peak_kb", 0.0)

            scoring = calculate_impact(
                complexity_rank=fn.complexity_rank,
                runtime_pct=runtime_pct,
                call_count=call_count,
                max_calls=max_calls,
                memory_peak_kb=memory_peak_kb,
                max_peak_mem_kb=max_peak_mem_kb,
                has_profile=has_profile,
                profile_metadata=r_info if has_profile and r_info else None,
            )

            # Contract G6: Create one bottlenecks row per function whose impact_score >= 0.10
            if scoring.impact_score >= 0.10:
                evidence = dict(scoring.evidence)
                affected = analyze_affected_functions(
                    storage=self.storage,
                    repository_id=repository_id,
                    bottleneck_function_id=fn.id,
                    workload_spec=workload_spec,
                    call_graph_dict=call_graph_data,
                )
                evidence["affected_functions"] = affected

                bottleneck = Bottleneck(
                    id=str(uuid.uuid4()),
                    analysis_run_id=analysis_run_id,
                    function_id=fn.id,
                    static_score=scoring.static_score,
                    runtime_score=scoring.runtime_score,
                    call_count=scoring.call_count,
                    runtime_pct=scoring.runtime_pct,
                    memory_peak_kb=scoring.memory_peak_kb,
                    impact_score=scoring.impact_score,
                    severity=scoring.severity,
                    evidence=evidence,
                )
                scored_bottlenecks.append(bottleneck)

        # 6. Sort bottlenecks by impact_score descending
        scored_bottlenecks.sort(key=lambda b: b.impact_score, reverse=True)

        # 7. Idempotent database write: remove prior bottlenecks for this run
        self.db.query(Bottleneck).filter(
            Bottleneck.analysis_run_id == analysis_run_id
        ).delete(synchronize_session=False)

        if scored_bottlenecks:
            self.db.add_all(scored_bottlenecks)
        self.db.commit()

        logger.info(
            f"Saved {len(scored_bottlenecks)} bottlenecks (impact >= 0.10) for run {analysis_run_id}"
        )
        return scored_bottlenecks
