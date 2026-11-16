"""Sample Python project demonstrating 6 algorithmic bottleneck patterns.

Upload or test this file in AlgoRevive AI to see:
1. Static analysis & Halstead metrics
2. Function call graph
3. Dynamic runtime profiling
4. Bottleneck impact scoring
5. Machine Learning recommendations (Random Forest)
6. Phase 6 candidate optimization generation with side-by-side diff
"""


def find_active_users(all_users: list, active_ids: list) -> list:
    """Pattern 1: LINEAR_MEMBERSHIP_IN_LOOP -> T1_SET_MEMBERSHIP"""
    active = []
    for user in all_users:
        if user in active_ids:
            active.append(user)
    return active


def match_orders_to_customers(orders: list, customers: list) -> list:
    """Pattern 2: NESTED_LOOP_LOOKUP -> T2_DICT_INDEX_JOIN"""
    matched = []
    for order in orders:
        for cust in customers:
            if cust["id"] == order["customer_id"]:
                matched.append((order, cust))
    return matched


def get_top_priority_item(items: list):
    """Pattern 3: REPEATED_SORT_FOR_EXTREME -> T3_MIN_MAX_HEAP"""
    if not items:
        return None
    return sorted(items)[0]


def generate_log_report(log_entries: list) -> str:
    """Pattern 4: STRING_CONCAT_IN_LOOP -> T4_JOIN_STRINGS"""
    report = ""
    for entry in log_entries:
        report += entry + "\n"
    return report


def calculate_fibonacci(n: int) -> int:
    """Pattern 5: NAIVE_RECURSION -> T5_LRU_CACHE"""
    if n <= 1:
        return n
    return calculate_fibonacci(n - 1) + calculate_fibonacci(n - 2)


def process_task_queue(initial_tasks: list) -> list:
    """Pattern 6: LIST_POP_FRONT -> T6_DEQUE_POPLEFT"""
    tasks = list(initial_tasks)
    processed = []
    while tasks:
        task = tasks.pop(0)
        processed.append(task)
    return processed
