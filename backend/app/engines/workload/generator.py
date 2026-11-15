"""Deterministic seeded workload argument generator (dependency-free, stdlib only)."""

from __future__ import annotations

import random
from typing import Any, Dict, List


def generate_arg(
    kind: str,
    n: int,
    size_factor: float = 1.0,
    fixed: Any = None,
    options: Dict[str, Any] | None = None,
    seed: int = 42,
) -> Any:
    """Generate a single deterministic argument based on kind, size, and seed."""
    if fixed is not None:
        return fixed

    options = options or {}
    rng = random.Random(seed)
    effective_n = max(1, int(n * size_factor))

    if kind == "int_list":
        min_val = int(options.get("min", -1_000_000))
        max_val = int(options.get("max", 1_000_000))
        return [rng.randint(min_val, max_val) for _ in range(effective_n)]

    elif kind == "str_list":
        str_len = int(options.get("str_len", 8))
        alphabet = str(options.get("alphabet", "abcdefghijklmnopqrstuvwxyz"))
        return ["".join(rng.choices(alphabet, k=str_len)) for _ in range(effective_n)]

    elif kind == "records":
        # Dicts with unique int id, a name, and a numeric value
        records: List[Dict[str, Any]] = []
        for i in range(effective_n):
            records.append({
                "id": i,
                "name": f"item_{i}",
                "value": round(rng.uniform(1.0, 1000.0), 2),
            })
        return records

    elif kind == "int":
        val = effective_n
        if "max" in options:
            val = min(val, int(options["max"]))
        if "min" in options:
            val = max(val, int(options["min"]))
        return val

    elif kind == "str":
        alphabet = str(options.get("alphabet", "abcdefghijklmnopqrstuvwxyz"))
        return "".join(rng.choices(alphabet, k=effective_n))

    elif kind == "two_record_lists":
        # Orders / customers style with a shared key: customer['id'] == order['customer_id']
        num_customers = max(1, effective_n)
        orders_ratio = float(options.get("orders_ratio", 1.0))
        num_orders = max(1, int(effective_n * orders_ratio))

        customers = [
            {
                "id": cid,
                "name": f"customer_{cid}",
                "value": round(rng.uniform(10.0, 500.0), 2),
            }
            for cid in range(num_customers)
        ]

        orders = [
            {
                "id": oid,
                "customer_id": rng.randint(0, num_customers - 1),
                "amount": round(rng.uniform(1.0, 100.0), 2),
            }
            for oid in range(num_orders)
        ]
        return (orders, customers)

    else:
        raise ValueError(f"Unknown workload argument kind: '{kind}'")


def generate_args_for_entrypoint(
    entrypoint_args: List[Dict[str, Any]],
    n: int,
    base_seed: int = 42,
) -> List[Any]:
    """Generate the full positional arguments list for an entrypoint function call.
    
    If an argument kind is 'two_record_lists', it expands into two positional arguments
    (e.g. orders, customers) as expected by relational joins.
    """
    call_args: List[Any] = []
    for idx, arg_spec in enumerate(entrypoint_args):
        # Derive a deterministic subseed for each argument to prevent correlated streams
        arg_seed = (base_seed * 10007 + idx * 37) & 0xFFFFFFFF
        kind = arg_spec.get("kind", "int_list") if isinstance(arg_spec, dict) else arg_spec.kind
        size_factor = (
            arg_spec.get("size_factor", 1.0) if isinstance(arg_spec, dict) else arg_spec.size_factor
        )
        fixed = arg_spec.get("fixed", None) if isinstance(arg_spec, dict) else arg_spec.fixed
        options = (
            arg_spec.get("options", {}) if isinstance(arg_spec, dict) else arg_spec.options
        )

        generated = generate_arg(
            kind=kind,
            n=n,
            size_factor=size_factor,
            fixed=fixed,
            options=options,
            seed=arg_seed,
        )

        if kind == "two_record_lists" and isinstance(generated, tuple):
            call_args.extend(generated)
        else:
            call_args.append(generated)

    return call_args
