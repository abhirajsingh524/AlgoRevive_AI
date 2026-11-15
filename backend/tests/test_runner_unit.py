"""Runner unit tests using local temporary directories (no Docker requirement)."""

from pathlib import Path
import sys
import tempfile

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sandbox.runner import run_profile_mode  # noqa: E402


def test_runner_profile_mode_local_tempdir():
    """Unit test for runner profile mode collecting stats, timing, memory, and growth exponent."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_dir = Path(tmpdir) / "repo"
        out_dir = Path(tmpdir) / "out"
        repo_dir.mkdir(parents=True, exist_ok=True)
        out_dir.mkdir(parents=True, exist_ok=True)

        # Write dummy module
        sample_code = (
            "def linear_func(items):\n"
            "    total = 0\n"
            "    for x in items:\n"
            "        total += x\n"
            "    return total\n"
            "\n"
            "def quadratic_func(items):\n"
            "    count = 0\n"
            "    for x in items:\n"
            "        for y in items:\n"
            "            if x == y:\n"
            "                count += 1\n"
            "    return count\n"
        )
        (repo_dir / "sample.py").write_text(sample_code, encoding="utf-8")

        spec = {
            "sizes": [10, 30, 60],
            "entrypoints": [
                {
                    "function": "sample:linear_func",
                    "args": [{"kind": "int_list", "size_factor": 1.0}],
                },
                {
                    "function": "sample:quadratic_func",
                    "args": [{"kind": "int_list", "size_factor": 1.0}],
                },
            ],
            "seed": 42,
        }

        out_json = out_dir / "result.json"
        res = run_profile_mode(
            spec=spec,
            repo_path=str(repo_dir),
            out_path=str(out_json),
        )

        assert res["status"] == "completed"
        assert res["summary"]["total_entrypoints"] == 2
        assert res["summary"]["successful_entrypoints"] == 2
        assert out_json.is_file()

        # Check entrypoint details
        lin_ep = res["entrypoints"]["sample:linear_func"]
        assert lin_ep["status"] == "success"
        assert len(lin_ep["measurements"]) == 3
        assert lin_ep["measurements"][0]["n"] == 10
        assert lin_ep["measurements"][0]["runtime_s"] > 0
        assert lin_ep["measurements"][0]["peak_memory_kb"] >= 0
        assert len(lin_ep["measurements"][0]["top_functions"]) > 0

        quad_ep = res["entrypoints"]["sample:quadratic_func"]
        assert quad_ep["status"] == "success"
        # Quadratic function should have higher growth exponent than linear function
        assert quad_ep["growth_exponent"] >= lin_ep["growth_exponent"]


def test_runner_broken_user_code_captured_per_entrypoint():
    """Any exception inside user code is captured per entrypoint without crashing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_dir = Path(tmpdir) / "repo"
        out_dir = Path(tmpdir) / "out"
        repo_dir.mkdir(parents=True, exist_ok=True)
        out_dir.mkdir(parents=True, exist_ok=True)

        sample_code = (
            "def broken_func(items):\n"
            "    return 1 / 0\n"
            "\n"
            "def healthy_func(items):\n"
            "    return len(items)\n"
        )
        (repo_dir / "sample_err.py").write_text(sample_code, encoding="utf-8")

        spec = {
            "sizes": [10, 20],
            "entrypoints": [
                {
                    "function": "sample_err:broken_func",
                    "args": [{"kind": "int_list", "size_factor": 1.0}],
                },
                {
                    "function": "sample_err:healthy_func",
                    "args": [{"kind": "int_list", "size_factor": 1.0}],
                },
            ],
            "seed": 42,
        }

        out_json = out_dir / "result.json"
        res = run_profile_mode(
            spec=spec,
            repo_path=str(repo_dir),
            out_path=str(out_json),
        )

        assert res["status"] == "completed"
        # Broken func is captured as error, healthy func succeeds
        broken_ep = res["entrypoints"]["sample_err:broken_func"]
        assert broken_ep["status"] == "error"
        assert "division by zero" in broken_ep["error"]

        healthy_ep = res["entrypoints"]["sample_err:healthy_func"]
        assert healthy_ep["status"] == "success"
        assert len(healthy_ep["measurements"]) == 2


def test_runner_missing_module_handled_gracefully():
    """Non-existent module target records an error without aborting."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir) / "out"
        out_dir.mkdir(parents=True, exist_ok=True)

        spec = {
            "sizes": [10],
            "entrypoints": [
                {
                    "function": "non_existent_module:some_func",
                    "args": [{"kind": "int_list"}],
                }
            ],
            "seed": 42,
        }

        out_json = out_dir / "result.json"
        res = run_profile_mode(spec=spec, repo_path=tmpdir, out_path=str(out_json))

        assert res["status"] == "completed"
        ep = res["entrypoints"]["non_existent_module:some_func"]
        assert ep["status"] == "error"
        assert "Failed to import" in ep["error"]
