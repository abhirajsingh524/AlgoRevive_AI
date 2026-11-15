"""Tests for Docker sandbox isolation, resource limits, cleanup, and status mapping."""

import docker
import pytest

from app.engines.sandbox.executor import (
    SandboxExecutor,
    SandboxLimits,
    is_docker_available,
)

pytestmark = [
    pytest.mark.docker,
    pytest.mark.skipif(not is_docker_available(), reason="Docker daemon is not available"),
]


@pytest.fixture
def docker_client():
    return docker.from_env()


@pytest.fixture
def executor():
    return SandboxExecutor()


def test_normal_script_returns_ok_with_result_json(executor):
    """Normal script writing result.json to /work/out completes with status OK."""
    script = (
        "import json\n"
        "data = {'status': 'success', 'value': 42}\n"
        "with open('/work/out/result.json', 'w') as f:\n"
        "    json.dump(data, f)\n"
    )
    files = {"main.py": script}
    command = ["python", "/work/repo/main.py"]

    result = executor.run(files=files, command=command)

    assert result.status == "OK"
    assert result.result_json == {"status": "success", "value": 42}
    assert result.exit_code == 0
    assert result.duration_s > 0


def test_container_is_removed_after_execution(executor, docker_client):
    """Container is guaranteed to be killed and removed after execution."""
    script = (
        "import json\n"
        "with open('/work/out/result.json', 'w') as f:\n"
        "    json.dump({'ok': True}, f)\n"
    )
    result = executor.run(files={"test.py": script}, command=["python", "/work/repo/test.py"])

    assert result.status == "OK"
    assert result.container_id is not None

    # Verify container no longer exists in Docker daemon
    with pytest.raises(docker.errors.NotFound):
        docker_client.containers.get(result.container_id)


def test_network_access_is_blocked(executor):
    """Network requests from within sandbox must be blocked / fail immediately."""
    script = (
        "import urllib.request, json\n"
        "blocked = False\n"
        "try:\n"
        "    urllib.request.urlopen('http://1.1.1.1', timeout=2)\n"
        "except Exception as e:\n"
        "    blocked = True\n"
        "with open('/work/out/result.json', 'w') as f:\n"
        "    json.dump({'network_blocked': blocked}, f)\n"
    )
    result = executor.run(files={"net.py": script}, command=["python", "/work/repo/net.py"])

    assert result.status == "OK"
    assert result.result_json == {"network_blocked": True}


def test_writing_outside_tmp_and_work_out_fails(executor):
    """Filesystem is read-only outside /tmp and /work/out."""
    script = (
        "import json\n"
        "write_root_failed = False\n"
        "write_repo_failed = False\n"
        "write_tmp_ok = False\n"
        "write_out_ok = False\n"
        "\n"
        "try:\n"
        "    with open('/forbidden.txt', 'w') as f:\n"
        "        f.write('fail')\n"
        "except OSError:\n"
        "    write_root_failed = True\n"
        "\n"
        "try:\n"
        "    with open('/work/repo/forbidden.txt', 'w') as f:\n"
        "        f.write('fail')\n"
        "except OSError:\n"
        "    write_repo_failed = True\n"
        "\n"
        "try:\n"
        "    with open('/tmp/ok.txt', 'w') as f:\n"
        "        f.write('success')\n"
        "    write_tmp_ok = True\n"
        "except OSError:\n"
        "    write_tmp_ok = False\n"
        "\n"
        "try:\n"
        "    with open('/work/out/result.json', 'w') as f:\n"
        "        json.dump({\n"
        "            'write_root_failed': write_root_failed,\n"
        "            'write_repo_failed': write_repo_failed,\n"
        "            'write_tmp_ok': write_tmp_ok,\n"
        "        }, f)\n"
        "except OSError:\n"
        "    pass\n"
    )
    result = executor.run(files={"fs.py": script}, command=["python", "/work/repo/fs.py"])

    assert result.status == "OK"
    assert result.result_json == {
        "write_root_failed": True,
        "write_repo_failed": True,
        "write_tmp_ok": True,
    }


def test_infinite_loop_returns_timeout(executor):
    """Process exceeding timeout limit is killed and returns TIMEOUT status."""
    script = "while True: pass\n"
    limits = SandboxLimits(timeout_s=2)

    result = executor.run(
        files={"loop.py": script},
        command=["python", "/work/repo/loop.py"],
        limits=limits,
    )

    assert result.status == "TIMEOUT"


def test_memory_hog_killed_with_status_oom(executor):
    """Memory allocation exceeding limit triggers container OOM kill."""
    # Run with small 64 MB memory limit and allocate 128 MB
    script = (
        "data = []\n"
        "while True:\n"
        "    data.append(b'A' * (10 * 1024 * 1024))\n"
    )
    limits = SandboxLimits(memory_mb=64, timeout_s=15)

    result = executor.run(
        files={"oom.py": script},
        command=["python", "/work/repo/oom.py"],
        limits=limits,
    )

    assert result.status == "OOM"


def test_fork_bomb_contained_by_pids_limit(executor):
    """Fork bomb is prevented from exhausting system PIDs and contained by pids_limit."""
    script = (
        "import os, json\n"
        "fork_failed = False\n"
        "children = []\n"
        "try:\n"
        "    for _ in range(200):\n"
        "        pid = os.fork()\n"
        "        if pid == 0:\n"
        "            import time; time.sleep(1)\n"
        "            os._exit(0)\n"
        "        children.append(pid)\n"
        "except OSError:\n"
        "    fork_failed = True\n"
        "\n"
        "with open('/work/out/result.json', 'w') as f:\n"
        "    json.dump({'fork_contained': fork_failed}, f)\n"
    )
    limits = SandboxLimits(pids_limit=32, timeout_s=10)

    result = executor.run(
        files={"fork.py": script},
        command=["python", "/work/repo/fork.py"],
        limits=limits,
    )

    # Either completed with caught OSError (fork failed due to pids limit), or status ERROR/TIMEOUT
    assert result.status in ("OK", "ERROR")
    if result.status == "OK" and result.result_json:
        assert result.result_json.get("fork_contained") is True
