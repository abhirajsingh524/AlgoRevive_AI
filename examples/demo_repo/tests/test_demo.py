import unittest
import sys
import os

# Add parent demo directory to path so demo package is importable
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from demo.operations import (  # noqa: E402
    concat_report,
    drain_queue,
    efficient_total,
    fib,
    nested_match,
    repeated_sort,
    slow_membership,
)


class TestDemoFunctions(unittest.TestCase):
    def test_slow_membership(self):
        users = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}, {"id": 3, "name": "Charlie"}]
        ids = [2, 3, 5]
        res = slow_membership(users, ids)
        self.assertEqual(len(res), 2)
        self.assertEqual([u["id"] for u in res], [2, 3])

    def test_nested_match(self):
        orders = [{"order_id": 101, "customer_id": 1}, {"order_id": 102, "customer_id": 3}]
        customers = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
        res = nested_match(orders, customers)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["order"]["order_id"], 101)

    def test_repeated_sort(self):
        values = [5, 2, 8, 1, 9]
        queries = [10, 20]
        res = repeated_sort(values, queries)
        self.assertEqual(res, [(10, 1), (20, 1)])

    def test_concat_report(self):
        parts = ["Algo", "Revive", " ", "AI"]
        res = concat_report(parts)
        self.assertEqual(res, "AlgoRevive AI")

    def test_fib(self):
        self.assertEqual(fib(0), 0)
        self.assertEqual(fib(1), 1)
        self.assertEqual(fib(6), 8)

    def test_drain_queue(self):
        items = ["first", "second", "third"]
        res = drain_queue(items)
        self.assertEqual(res, ["first", "second", "third"])

    def test_efficient_total(self):
        values = [1, 2, 3, 4, 5]
        res = efficient_total(values)
        self.assertEqual(res, 15)


if __name__ == "__main__":
    unittest.main()
