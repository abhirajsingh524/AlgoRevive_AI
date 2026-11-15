"""Hardened Docker Sandbox Executor enforcing Security Contract H1 and Protocol G8."""

from __future__ import annotations

from dataclasses import dataclass, field
import io
import json
import tarfile
import time
from typing import Any, Dict, List, Literal, Optional

import docker
from docker.errors import DockerException

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("sandbox_executor")

MAX_LOG_BYTES = 1024 * 1024  # 1 MB


@dataclass
class SandboxLimits:
    timeout_s: int = 60
    memory_mb: int = 512
    cpus: float = 1.0
    pids_limit: int = 128


@dataclass
class SandboxResult:
    status: Literal["OK", "TIMEOUT", "OOM", "ERROR"]
    result_json: Optional[Dict[str, Any]] = None
    stdout_tail: str = ""
    stderr_tail: str = ""
    duration_s: float = 0.0
    container_id: Optional[str] = None
    exit_code: Optional[int] = None
    extra: Dict[str, Any] = field(default_factory=dict)


def is_docker_available() -> bool:
    """Return True if Docker daemon is reachable and responding."""
    try:
        client = docker.from_env()
        return bool(client.ping())
    except Exception:
        return False


class SandboxExecutor:
    """Executes code securely inside isolated containers enforcing Contract H1."""

    def __init__(
        self,
        image: Optional[str] = None,
        docker_client: Optional[docker.DockerClient] = None,
    ):
        self.image = image or settings.SANDBOX_IMAGE
        self._client = docker_client

    def _get_client(self) -> docker.DockerClient:
        if self._client is not None:
            return self._client
        try:
            return docker.from_env()
        except DockerException as e:
            logger.error(f"Failed to connect to Docker daemon: {e}")
            raise

    def _build_archive(
        self,
        files: Dict[str, bytes | str],
        job_spec: Optional[Dict[str, Any] | str] = None,
    ) -> bytes:
        """Create a tar archive of repo files and job.json for put_archive."""
        bio = io.BytesIO()
        with tarfile.open(fileobj=bio, mode="w") as tar:
            if job_spec is not None:
                if isinstance(job_spec, str):
                    job_bytes = job_spec.encode("utf-8")
                elif hasattr(job_spec, "model_dump_json"):
                    job_bytes = job_spec.model_dump_json().encode("utf-8")
                else:
                    job_bytes = json.dumps(job_spec).encode("utf-8")

                ti = tarfile.TarInfo(name="job.json")
                ti.size = len(job_bytes)
                ti.mode = 0o644
                ti.uid = 10001
                ti.gid = 10001
                tar.addfile(ti, io.BytesIO(job_bytes))

            for rel_path, content in files.items():
                clean_path = rel_path.lstrip("/\\").replace("\\", "/")
                data = content.encode("utf-8") if isinstance(content, str) else bytes(content)

                ti = tarfile.TarInfo(name=f"repo/{clean_path}")
                ti.size = len(data)
                ti.mode = 0o644
                ti.uid = 10001
                ti.gid = 10001
                tar.addfile(ti, io.BytesIO(data))

        return bio.getvalue()

    def run(
        self,
        files: Optional[Dict[str, bytes | str]] = None,
        job_spec: Optional[Dict[str, Any] | str] = None,
        mode: str = "profile",
        limits: Optional[SandboxLimits] = None,
        command: Optional[List[str]] = None,
    ) -> SandboxResult:
        """Run execution inside an isolated Docker sandbox container.
        
        Enforces Contract H1:
        - Network disabled
        - Memory limit (default 512 MB)
        - CPU limit (default 1 CPU)
        - PIDs limit (128)
        - Read-only root filesystem with tmpfs /tmp and /work/out
        - All capabilities dropped
        - no-new-privileges
        - Non-root user (uid 10001)
        - Timeout enforcement
        - Container always destroyed in finally block
        """
        limits = limits or SandboxLimits(
            timeout_s=settings.SANDBOX_TIMEOUT_S,
            memory_mb=settings.SANDBOX_MEMORY_MB,
            cpus=settings.SANDBOX_CPUS,
        )
        files = files or {}
        cmd = command or ["python", "/runner/runner.py", "--mode", mode, "--spec", "/work/job.json"]

        client = self._get_client()
        container = None
        container_id = None
        start_time = time.perf_counter()
        status: Literal["OK", "TIMEOUT", "OOM", "ERROR"] = "ERROR"
        result_json: Optional[Dict[str, Any]] = None
        stdout_tail = ""
        stderr_tail = ""
        exit_code: Optional[int] = None

        try:
            # 1. Create container with strict security parameters
            container = client.containers.create(
                image=self.image,
                command=cmd,
                working_dir="/work",
                network_mode="none",
                mem_limit=f"{limits.memory_mb}m",
                nano_cpus=int(limits.cpus * 1_000_000_000),
                pids_limit=limits.pids_limit,
                read_only=True,
                tmpfs={
                    "/tmp": "rw,size=64m",
                    "/work/out": "rw,size=64m",
                },
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                user="10001:10001",
                detach=True,
            )
            container_id = container.id

            # 2. Copy code and job spec in using put_archive (Contract G8)
            tar_archive = self._build_archive(files, job_spec)
            container.put_archive(path="/work", data=tar_archive)

            # 3. Start container
            container.start()

            # 4. Wait for completion with timeout
            try:
                wait_res = container.wait(timeout=limits.timeout_s)
                exit_code = wait_res.get("StatusCode")
            except Exception as wait_exc:
                exc_msg = str(wait_exc).lower()
                if "timed out" in exc_msg or "timeout" in exc_msg or "readtimeout" in exc_msg:
                    status = "TIMEOUT"
                    try:
                        container.kill()
                    except Exception:
                        pass
                else:
                    logger.error(f"Unexpected error waiting on container {container_id}: {wait_exc}")
                    raise

            # 5. Extract logs (capped at 1 MB)
            try:
                raw_stdout = container.logs(stdout=True, stderr=False)
                if isinstance(raw_stdout, bytes):
                    stdout_tail = raw_stdout[-MAX_LOG_BYTES:].decode("utf-8", errors="replace")
                else:
                    stdout_tail = str(raw_stdout)[-MAX_LOG_BYTES:]
            except Exception as e:
                logger.debug(f"Could not read stdout from container: {e}")

            try:
                raw_stderr = container.logs(stdout=False, stderr=True)
                if isinstance(raw_stderr, bytes):
                    stderr_tail = raw_stderr[-MAX_LOG_BYTES:].decode("utf-8", errors="replace")
                else:
                    stderr_tail = str(raw_stderr)[-MAX_LOG_BYTES:]
            except Exception as e:
                logger.debug(f"Could not read stderr from container: {e}")

            # 6. Check OOM and exit state if not timed out
            if status != "TIMEOUT":
                try:
                    container.reload()
                    state = container.attrs.get("State", {})
                    oom_killed = bool(state.get("OOMKilled", False))
                except Exception:
                    oom_killed = False

                if oom_killed or exit_code == 137:
                    status = "OOM"
                elif exit_code == 0:
                    # 7. Extract /work/out/result.json using get_archive
                    try:
                        bits, _ = container.get_archive("/work/out/result.json")
                        tar_bio = io.BytesIO(b"".join(bits))
                        with tarfile.open(fileobj=tar_bio, mode="r") as tar:
                            member = tar.extractfile("result.json") or tar.extractfile(tar.getnames()[0])
                            if member:
                                result_json = json.loads(member.read().decode("utf-8"))
                                status = "OK"
                            else:
                                status = "ERROR"
                    except Exception as extract_err:
                        logger.warning(f"Failed to extract result.json: {extract_err}")
                        status = "ERROR"
                else:
                    status = "ERROR"

        except Exception as run_err:
            if status != "TIMEOUT":
                status = "ERROR"
                stderr_tail = f"{stderr_tail}\nSandbox execution error: {run_err}".strip()
                logger.exception(f"Sandbox container execution failed: {run_err}")

        finally:
            # 8. Ensure container is ALWAYS killed and removed
            if container is not None:
                try:
                    container.kill()
                except Exception:
                    pass
                try:
                    container.remove(force=True, v=True)
                except Exception as rem_err:
                    logger.debug(f"Error removing container {container_id}: {rem_err}")

        duration_s = round(time.perf_counter() - start_time, 4)
        return SandboxResult(
            status=status,
            result_json=result_json,
            stdout_tail=stdout_tail,
            stderr_tail=stderr_tail,
            duration_s=duration_s,
            container_id=container_id,
            exit_code=exit_code,
        )
