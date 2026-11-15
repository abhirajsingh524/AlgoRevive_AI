"""Tests for WorkloadSpec validation and deterministic argument generators."""

import pytest
from pydantic import ValidationError

from app.engines.workload import (
    ArgSpec,
    EntrypointSpec,
    WorkloadSpec,
    generate_arg,
    generate_args_for_entrypoint,
)


def test_generator_determinism():
    """Identical seed and parameters must yield 100% deterministic output."""
    res1 = generate_arg("int_list", n=100, seed=42)
    res2 = generate_arg("int_list", n=100, seed=42)
    assert res1 == res2

    res3 = generate_arg("int_list", n=100, seed=99)
    assert res1 != res3


def test_generator_all_arg_kinds():
    """Verify all 6 supported argument kinds conform to structural requirements."""
    # 1. int_list
    ints = generate_arg("int_list", n=50, seed=123)
    assert isinstance(ints, list)
    assert len(ints) == 50
    assert all(isinstance(x, int) for x in ints)

    # 2. str_list
    strs = generate_arg("str_list", n=30, options={"str_len": 12}, seed=123)
    assert isinstance(strs, list)
    assert len(strs) == 30
    assert all(isinstance(s, str) and len(s) == 12 for s in strs)

    # 3. records: dicts with unique int id, name, and numeric value
    recs = generate_arg("records", n=40, seed=123)
    assert isinstance(recs, list)
    assert len(recs) == 40
    ids = [r["id"] for r in recs]
    assert len(set(ids)) == 40
    for r in recs:
        assert isinstance(r["id"], int)
        assert isinstance(r["name"], str)
        assert isinstance(r["value"], (int, float))

    # 4. int
    val_int = generate_arg("int", n=25, seed=123)
    assert isinstance(val_int, int)
    assert val_int == 25

    # 5. str
    val_str = generate_arg("str", n=15, seed=123)
    assert isinstance(val_str, str)
    assert len(val_str) == 15

    # 6. two_record_lists: orders/customers style with a shared key
    orders, customers = generate_arg("two_record_lists", n=20, seed=123)
    assert isinstance(orders, list) and len(orders) == 20
    assert isinstance(customers, list) and len(customers) == 20
    customer_ids = {c["id"] for c in customers}
    assert all(o["customer_id"] in customer_ids for o in orders)


def test_generate_args_for_entrypoint_expansion():
    """two_record_lists expands into two positional parameters."""
    ep_args = [{"kind": "two_record_lists", "size_factor": 1.0}]
    call_args = generate_args_for_entrypoint(ep_args, n=10, base_seed=42)
    assert len(call_args) == 2
    orders, customers = call_args
    assert isinstance(orders, list)
    assert isinstance(customers, list)


def test_workload_spec_valid():
    """Valid WorkloadSpec passes schema validation."""
    spec_data = {
        "sizes": [10, 50, 100],
        "entrypoints": [
            {
                "function": "demo.operations:slow_membership",
                "args": [{"kind": "int_list", "size_factor": 1.0}],
            }
        ],
        "operation_mix": {"lookup": 0.9, "insert": 0.05, "delete": 0.05},
        "memory_constraint": "low",
        "seed": 42,
    }
    spec = WorkloadSpec.model_validate(spec_data)
    assert spec.sizes == [10, 50, 100]
    assert len(spec.entrypoints) == 1
    assert spec.seed == 42


def test_workload_spec_validation_sizes_limits():
    """Sizes limits: at most 8 sizes, each n <= 2,000,000."""
    # More than 8 sizes fails
    with pytest.raises(ValidationError):
        WorkloadSpec(
            sizes=[1, 2, 3, 4, 5, 6, 7, 8, 9],
            entrypoints=[
                EntrypointSpec(
                    function="mod:f",
                    args=[ArgSpec(kind="int_list")],
                )
            ],
        )

    # Size > 2,000,000 fails
    with pytest.raises(ValidationError):
        WorkloadSpec(
            sizes=[2_000_001],
            entrypoints=[
                EntrypointSpec(
                    function="mod:f",
                    args=[ArgSpec(kind="int_list")],
                )
            ],
        )

    # Size <= 0 fails
    with pytest.raises(ValidationError):
        WorkloadSpec(
            sizes=[0],
            entrypoints=[
                EntrypointSpec(
                    function="mod:f",
                    args=[ArgSpec(kind="int_list")],
                )
            ],
        )


def test_workload_spec_validation_entrypoints_limits():
    """At most 10 entrypoints and valid function target format."""
    # More than 10 entrypoints fails
    eps = [
        EntrypointSpec(function=f"mod:f{i}", args=[ArgSpec(kind="int_list")])
        for i in range(11)
    ]
    with pytest.raises(ValidationError):
        WorkloadSpec(sizes=[10], entrypoints=eps)

    # Invalid function format (no colon)
    with pytest.raises(ValidationError):
        EntrypointSpec(function="invalid_function_target", args=[])
