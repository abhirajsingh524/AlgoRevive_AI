"""Runtime Profiler Engine executing sandbox profiling and validating outputs."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import platform
import tempfile
from typing import Any, Dict, Optional

from app.core.config import settings
from app.core.logging import get_logger
from app.engines.profiler.models import ProfileResult
from app.engines.sandbox.executor import (
    SandboxExecutor,
    SandboxLimits,
    is_docker_available,
)
from app.engines.workload.models import WorkloadSpec

logger = get_logger("profiler_engine")


def collect_environment_metadata(
    seed: int = 42,
    sandbox_image: Optional[str] = None,
) -> Dict[str, Any]:
    """Record environment metadata strictly as specified in Contract G10."""
    ram_mb = 0
    try:
        import psutil
        ram_mb = int(psutil.virtual_memory().total / (1024 * 1024))
    except Exception:
        pass

    return {
        "python_version": platform.python_version(),
        "os": f"{platform.system()} {platform.release()}",
        "cpu_count": os.cpu_count() or 1,
        "ram_mb": ram_mb,
        "sandbox_image_id": sandbox_image or settings.SANDBOX_IMAGE,
        "seed": seed,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


class ProfilerEngine:
    """Executes the runner under sandbox isolation and parses/validates ProfileResult."""

    def __init__(self, executor: Optional[SandboxExecutor] = None):
        self.executor = executor or SandboxExecutor()

    def profile(
        self,
        run_id: str,
        files: Dict[str, bytes | str],
        spec: Dict[str, Any] | WorkloadSpec,
        limits: Optional[SandboxLimits] = None,
    ) -> ProfileResult:
        """Run profiling for files and workload spec, returning validated ProfileResult."""
        if isinstance(spec, WorkloadSpec):
            spec_dict = spec.model_dump()
        else:
            # Validate through Pydantic
            validated_spec = WorkloadSpec.model_validate(spec)
            spec_dict = validated_spec.model_dump()

        job_spec = {"mode": "profile", "spec": spec_dict, "run_id": run_id}

        if is_docker_available():
            logger.info(f"Running profile for run {run_id} inside Docker sandbox")
            sandbox_res = self.executor.run(
                files=files,
                job_spec=job_spec,
                mode="profile",
                limits=limits,
            )

            if sandbox_res.status != "OK" or not sandbox_res.result_json:
                error_msg = (
                    f"Sandbox profiling returned status {sandbox_res.status}. "
                    f"Stderr: {sandbox_res.stderr_tail[:500]}"
                )
                logger.error(error_msg)
                raise RuntimeError(error_msg)

            return ProfileResult.model_validate(sandbox_res.result_json)

        else:
            # Fallback for environments without Docker daemon (e.g. non-containerized CI/tests)
            logger.warning(
                f"Docker unavailable; running profile for run {run_id} via local in-memory runner"
            )
            with tempfile.TemporaryDirectory() as tmpdir:
                repo_dir = Path(tmpdir) / "repo"
                out_dir = Path(tmpdir) / "out"
                repo_dir.mkdir(parents=True, exist_ok=True)
                out_dir.mkdir(parents=True, exist_ok=True)

                # Write files into temporary repo
                for rel_path, content in files.items():
                    clean_path = rel_path.lstrip("/\\")
                    dest = repo_dir / clean_path
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    if isinstance(content, str):
                        dest.write_text(content, encoding="utf-8")
                    else:
                        dest.write_bytes(content)

                out_json = out_dir / "result.json"

                # Ensure workspace root (containing sandbox) is in sys.path
                import sys
                project_root = str(Path(__file__).resolve().parent.parent.parent.parent)
                workspace_root = str(Path(__file__).resolve().parent.parent.parent.parent.parent)
                for p in (project_root, workspace_root):
                    if p not in sys.path:
                        sys.path.insert(0, p)

                # Import and run local runner mode
                from sandbox.runner import run_profile_mode

                res_dict = run_profile_mode(
                    spec=spec_dict,
                    repo_path=str(repo_dir),
                    out_path=str(out_json),
                )
                return ProfileResult.model_validate(res_dict)
