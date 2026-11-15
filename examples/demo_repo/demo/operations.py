"""Demo module with performance patterns and control function."""

from typing import Any, Dict, List, Tuple


def slow_membership(users: List[Dict[str, Any]], ids: List[int]) -> List[Dict[str, Any]]:
    """Loops over users (list of dicts with id) and tests u['id'] in ids where ids is a list."""
    matched = []
    for u in users:
        if u["id"] in ids:
            matched.append(u)
    return matched


def nested_match(
    orders: List[Dict[str, Any]], customers: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Nested for loops joining on customer_id == id, building a result list."""
    result = []
    for order in orders:
        for customer in customers:
            if order["customer_id"] == customer["id"]:
                result.append({"order": order, "customer": customer})
    return result


def repeated_sort(values: List[int], queries: List[int]) -> List[Tuple[int, int]]:
    """For each query returns sorted(values)[0] inside the loop."""
    results = []
    for query in queries:
        smallest = sorted(values)[0]
        results.append((query, smallest))
    return results


def concat_report(parts: List[str]) -> str:
    """Builds a string with s += part in a loop."""
    s = ""
    for part in parts:
        s += part
    return s


def fib(n: int) -> int:
    """Naive recursion with two self-calls."""
    if n <= 1:
        return n
    return fib(n - 1) + fib(n - 2)


def drain_queue(items: List[Any]) -> List[Any]:
    """Builds a local list and repeatedly calls pop(0) in a while loop."""
    queue = list(items)
    drained = []
    while queue:
        drained.append(queue.pop(0))
    return drained


def efficient_total(values: List[int]) -> int:
    """A single sum loop (control function: must never be flagged HIGH or CRITICAL)."""
    total = 0
    for val in values:
        total += val
    return total
