"""AlgoRevive Sandbox Runner.

Executes code inside the sandbox container for modes:
- profile
- validate
- benchmark
"""

from __future__ import annotations

import argparse
import copy
import cProfile
import importlib
import json
import math
import os
import pstats
import signal
import sys
import time
import traceback
import tracemalloc
from typing import Any, Dict, List, Optional

# Ensure runner directory is on sys.path to import generator
RUNNER_DIR = os.path.dirname(os.path.abspath(__file__))
if RUNNER_DIR not in sys.path:
    sys.path.insert(0, RUNNER_DIR)

try:
    from generator import generate_args_for_entrypoint
except ImportError:
    from app.engines.workload.generator import generate_args_for_entrypoint  # type: ignore


class ExecutionTimeout(Exception):
    pass


class TimeoutContext:
    """Context manager for enforcing per-call wall-clock timeouts on platforms with SIGALRM."""

    def __init__(self, seconds: float):
        self.seconds = seconds
        self._old_handler = None

    def __enter__(self):
        if hasattr(signal, "SIGALRM") and self.seconds > 0:
            def _handler(signum, frame):
                raise ExecutionTimeout(f"Execution timed out after {self.seconds}s")

            self._old_handler = signal.signal(signal.SIGALRM, _handler)
            signal.setitimer(signal.ITIMER_REAL, self.seconds)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if hasattr(signal, "SIGALRM") and self.seconds > 0:
            signal.setitimer(signal.ITIMER_REAL, 0)
            if self._old_handler is not None:
                signal.signal(signal.SIGALRM, self._old_handler)


def get_cpu_time() -> float:
    """Get process CPU time (user + system) with psutil if available, fallback to time.process_time."""
    try:
        import psutil
        p = psutil.Process()
        ct = p.cpu_times()
        return ct.user + ct.system
    except Exception:
        return time.process_time()


def compute_growth_exponent(sizes: List[int], runtimes: List[float]) -> float:
    """Compute empirical growth exponent from the log-log slope of runtime versus n.
    
    Model: ln(runtime) = alpha * ln(n) + beta.
    Alpha is the log-log slope.
    """
    valid_points = []
    for n, t in zip(sizes, runtimes):
        if n > 0 and t > 0:
            valid_points.append((math.log(n), math.log(max(t, 1e-9))))

    if len(valid_points) < 2:
        return 1.0

    sum_x = sum(p[0] for p in valid_points)
    sum_y = sum(p[1] for p in valid_points)
    n_pts = len(valid_points)
    mean_x = sum_x / n_pts
    mean_y = sum_y / n_pts

    numerator = sum((x - mean_x) * (y - mean_y) for x, y in valid_points)
    denominator = sum((x - mean_x) ** 2 for x, _ in valid_points)

    if denominator <= 1e-12:
        return 1.0

    slope = numerator / denominator
    # If slope is negative due to timing noise on tiny O(1) runs, clamp to 0.0
    return round(max(0.0, slope), 3)


def run_profile_mode(
    spec: Dict[str, Any],
    repo_path: str = "/work/repo",
    out_path: str = "/work/out/result.json",
    per_call_timeout_s: float = 5.0,
) -> Dict[str, Any]:
    """Execute profiling for all entrypoints and sizes defined in spec."""
    # Ensure repo_path is on sys.path
    if repo_path not in sys.path:
        sys.path.insert(0, repo_path)

    sizes: List[int] = spec.get("sizes", [10, 50, 100])
    entrypoints: List[Dict[str, Any]] = spec.get("entrypoints", [])
    base_seed: int = int(spec.get("seed", 42))

    entrypoint_results: Dict[str, Any] = {}
    total_eps = len(entrypoints)
    successful_eps = 0
    failed_eps = 0

    for ep in entrypoints:
        func_target = ep.get("function", "")
        args_spec = ep.get("args", [])

        if ":" not in func_target:
            entrypoint_results[func_target] = {
                "function": func_target,
                "status": "error",
                "error": f"Invalid function target '{func_target}', expected 'module:function'",
                "measurements": [],
                "growth_exponent": 0.0,
            }
            failed_eps += 1
            continue

        mod_name, fn_name = func_target.split(":", 1)

        try:
            mod = importlib.import_module(mod_name)
            target_fn = getattr(mod, fn_name)
        except Exception as import_err:
            entrypoint_results[func_target] = {
                "function": func_target,
                "status": "error",
                "error": f"Failed to import {func_target}: {import_err}",
                "traceback": traceback.format_exc(),
                "measurements": [],
                "growth_exponent": 0.0,
            }
            failed_eps += 1
            continue

        measurements: List[Dict[str, Any]] = []
        measured_sizes: List[int] = []
        measured_runtimes: List[float] = []
        ep_error: Optional[str] = None
        ep_tb: Optional[str] = None

        for s_idx, n in enumerate(sizes):
            # Generate deterministic arguments
            try:
                call_args = generate_args_for_entrypoint(
                    args_spec,
                    n=n,
                    base_seed=base_seed + s_idx * 1000,
                )
            except Exception as arg_err:
                ep_error = f"Arg generation error for n={n}: {arg_err}"
                ep_tb = traceback.format_exc()
                break

            try:
                with TimeoutContext(per_call_timeout_s):
                    # 1. cProfile run: collect function call counts and cumulative/own times
                    prof = cProfile.Profile()
                    prof.enable()
                    args_prof = copy.deepcopy(call_args)
                    target_fn(*args_prof)
                    prof.disable()

                    stats = pstats.Stats(prof)
                    top_functions = []
                    # stats.stats key is (file, line, name)
                    for (file_name, lineno, func_name), (cc, nc, tottime, cumtime, _) in stats.stats.items():
                        # Normalize filename relative to repo_path
                        rel_file = file_name
                        if rel_file.startswith(repo_path):
                            rel_file = os.path.relpath(rel_file, repo_path).replace("\\", "/")
                        top_functions.append({
                            "file": rel_file,
                            "function": func_name,
                            "lineno": lineno,
                            "calls": nc,
                            "total_time": round(tottime, 6),
                            "cumulative_time": round(cumtime, 6),
                        })

                    # Sort top functions by cumulative time descending
                    top_functions.sort(key=lambda x: x["cumulative_time"], reverse=True)
                    top_functions = top_functions[:20]

                    # 2. Separate un-profiled timed run with time.perf_counter
                    args_time = copy.deepcopy(call_args)
                    t0 = time.perf_counter()
                    target_fn(*args_time)
                    t1 = time.perf_counter()
                    runtime_s = max(1e-8, t1 - t0)

                    # 3. Separate tracemalloc run for peak memory
                    tracemalloc.start()
                    tracemalloc.reset_peak()
                    args_mem = copy.deepcopy(call_args)
                    target_fn(*args_mem)
                    _, peak_bytes = tracemalloc.get_traced_memory()
                    tracemalloc.stop()
                    peak_memory_kb = round(peak_bytes / 1024, 2)

                    # 4. Separate CPU time measurement
                    args_cpu = copy.deepcopy(call_args)
                    cpu_t0 = get_cpu_time()
                    target_fn(*args_cpu)
                    cpu_t1 = get_cpu_time()
                    cpu_time_s = max(0.0, round(cpu_t1 - cpu_t0, 6))

                measurements.append({
                    "n": n,
                    "runtime_s": round(runtime_s, 6),
                    "cpu_time_s": cpu_time_s,
                    "peak_memory_kb": peak_memory_kb,
                    "top_functions": top_functions,
                })
                measured_sizes.append(n)
                measured_runtimes.append(runtime_s)

            except Exception as run_err:
                ep_error = str(run_err)
                ep_tb = traceback.format_exc()
                # Stop sizing for this entrypoint and continue to next entrypoint
                break

        # Compute empirical growth exponent from collected measurements
        growth_exponent = compute_growth_exponent(measured_sizes, measured_runtimes)

        status_str = "error" if ep_error and not measurements else "success"
        if status_str == "success":
            successful_eps += 1
        else:
            failed_eps += 1

        res_dict: Dict[str, Any] = {
            "function": func_target,
            "status": status_str,
            "growth_exponent": growth_exponent,
            "sizes": measured_sizes,
            "measurements": measurements,
        }
        if ep_error:
            res_dict["warning" if measurements else "error"] = ep_error
            if ep_tb:
                res_dict["traceback"] = ep_tb

        entrypoint_results[func_target] = res_dict

    result_payload: Dict[str, Any] = {
        "status": "completed",
        "entrypoints": entrypoint_results,
        "summary": {
            "total_entrypoints": total_eps,
            "successful_entrypoints": successful_eps,
            "failed_entrypoints": failed_eps,
        },
    }

    # Write output to result.json
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result_payload, f, indent=2)

    return result_payload


def parse_args():
    parser = argparse.ArgumentParser(description="AlgoRevive Sandbox Runner")
    parser.add_argument("--mode", choices=["profile", "validate", "benchmark"], required=True)
    parser.add_argument("--spec", default="/work/job.json", help="Path to job spec file")
    parser.add_argument("--repo", default="/work/repo", help="Path to repository root")
    parser.add_argument("--out", default="/work/out/result.json", help="Path to write output")
    return parser.parse_args()


def main():
    args = parse_args()

    # Load job spec
    if not os.path.isfile(args.spec):
        print(f"Error: Job spec not found at {args.spec}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(args.spec, "r", encoding="utf-8") as f:
            job_data = json.load(f)
    except Exception as e:
        print(f"Error parsing job spec JSON: {e}", file=sys.stderr)
        sys.exit(1)

    # Allow spec to be nested under "workload", "spec", or directly at root
    spec = job_data.get("workload") or job_data.get("spec") or job_data

    if args.mode == "profile":
        run_profile_mode(spec, repo_path=args.repo, out_path=args.out)
        sys.exit(0)
    else:
        # validate and benchmark modes will be implemented in later phases
        print(f"Mode {args.mode} not yet supported", file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
