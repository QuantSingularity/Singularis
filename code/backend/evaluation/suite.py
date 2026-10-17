from __future__ import annotations

import dataclasses

from backend.evaluation.suite_finance import FINANCE_TASKS
from backend.evaluation.suite_issues import ISSUE_TASKS
from backend.evaluation.tasks import Task

_FIZZBUZZ = Task(
    id="fizzbuzz",
    split="train",
    prompt=(
        "Implement fizzbuzz(n) in solution.py. It returns a list of strings for the numbers 1..n: "
        "'FizzBuzz' for multiples of both 3 and 5, 'Fizz' for multiples of 3, 'Buzz' for multiples of 5, "
        "otherwise the number as a string. fizzbuzz(0) returns an empty list. A negative n raises ValueError."
    ),
    files={"solution.py": "def fizzbuzz(n):\n    raise NotImplementedError\n"},
    hidden_tests=r"""
import unittest
from solution import fizzbuzz


class FizzBuzzTests(unittest.TestCase):
    def test_small(self):
        self.assertEqual(fizzbuzz(5), ["1", "2", "Fizz", "4", "Buzz"])

    def test_fifteen(self):
        result = fizzbuzz(15)
        self.assertEqual(len(result), 15)
        self.assertEqual(result[14], "FizzBuzz")
        self.assertEqual(result[8], "Fizz")
        self.assertEqual(result[9], "Buzz")

    def test_zero(self):
        self.assertEqual(fizzbuzz(0), [])

    def test_negative(self):
        with self.assertRaises(ValueError):
            fizzbuzz(-1)

    def test_returns_strings(self):
        self.assertTrue(all(isinstance(x, str) for x in fizzbuzz(30)))
""",
    reference={
        "solution.py": r"""
def fizzbuzz(n):
    if n < 0:
        raise ValueError("n must be non-negative")
    out = []
    for i in range(1, n + 1):
        if i % 15 == 0:
            out.append("FizzBuzz")
        elif i % 3 == 0:
            out.append("Fizz")
        elif i % 5 == 0:
            out.append("Buzz")
        else:
            out.append(str(i))
    return out
"""
    },
)

_MEDIAN = Task(
    id="median_bug",
    split="train",
    prompt=(
        "stats.py has bugs. Fix median(values) so that it returns the middle value for odd-length input "
        "and the mean of the two middle values for even-length input, raises ValueError on empty input, "
        "and does not modify the list it is given. Also make mean(values) raise ValueError on empty input. "
        "Run test_stats.py to see the visible checks."
    ),
    files={
        "stats.py": (
            "def mean(values):\n    return sum(values) / len(values)\n\n\n"
            "def median(values):\n    ordered = values.sort()\n    return ordered[len(ordered) // 2]\n"
        ),
        "test_stats.py": (
            "import unittest\nfrom stats import mean, median\n\n\n"
            "class Visible(unittest.TestCase):\n"
            "    def test_median_odd(self):\n        self.assertEqual(median([3, 1, 2]), 2)\n\n"
            "    def test_mean(self):\n        self.assertEqual(mean([2, 4]), 3)\n\n\n"
            "if __name__ == '__main__':\n    unittest.main()\n"
        ),
    },
    hidden_tests=r"""
import unittest
from stats import mean, median


class StatsTests(unittest.TestCase):
    def test_median_odd(self):
        self.assertEqual(median([3, 1, 2]), 2)

    def test_median_even(self):
        self.assertEqual(median([4, 1, 3, 2]), 2.5)

    def test_median_single(self):
        self.assertEqual(median([7]), 7)

    def test_median_floats(self):
        self.assertEqual(median([1.5, 2.5]), 2.0)

    def test_median_empty(self):
        with self.assertRaises(ValueError):
            median([])

    def test_median_does_not_mutate(self):
        data = [3, 1, 2]
        median(data)
        self.assertEqual(data, [3, 1, 2])

    def test_mean(self):
        self.assertAlmostEqual(mean([1, 2, 3, 4]), 2.5)

    def test_mean_empty(self):
        with self.assertRaises(ValueError):
            mean([])
""",
    reference={
        "stats.py": r"""
def mean(values):
    if len(values) == 0:
        raise ValueError("mean of empty sequence")
    return sum(values) / len(values)


def median(values):
    if len(values) == 0:
        raise ValueError("median of empty sequence")
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2
"""
    },
)

_ROMAN = Task(
    id="roman",
    split="train",
    prompt=(
        "Implement to_roman(n) and from_roman(s) in roman.py. to_roman converts an integer in 1..3999 to a "
        "canonical uppercase Roman numeral and raises ValueError for non-integers or values out of range. "
        "from_roman converts back and raises ValueError for anything that is not a canonical uppercase "
        "numeral in 1..3999 (for example 'IIII', 'IC', 'VX', lowercase, or the empty string)."
    ),
    files={
        "roman.py": (
            "def to_roman(n):\n    raise NotImplementedError\n\n\n"
            "def from_roman(s):\n    raise NotImplementedError\n"
        )
    },
    hidden_tests=r"""
import unittest
from roman import from_roman, to_roman


class RomanTests(unittest.TestCase):
    def test_known_values(self):
        self.assertEqual(to_roman(4), "IV")
        self.assertEqual(to_roman(9), "IX")
        self.assertEqual(to_roman(58), "LVIII")
        self.assertEqual(to_roman(1994), "MCMXCIV")
        self.assertEqual(to_roman(3999), "MMMCMXCIX")

    def test_out_of_range(self):
        for bad in (0, -1, 4000):
            with self.assertRaises(ValueError):
                to_roman(bad)

    def test_non_integer(self):
        for bad in (3.5, "4", None):
            with self.assertRaises(ValueError):
                to_roman(bad)

    def test_round_trip(self):
        for n in range(1, 4000):
            self.assertEqual(from_roman(to_roman(n)), n)

    def test_from_known(self):
        self.assertEqual(from_roman("XLII"), 42)
        self.assertEqual(from_roman("MCMXCIV"), 1994)

    def test_from_invalid(self):
        for bad in ("IIII", "IC", "VX", "iv", "", "MMMM", "ABC"):
            with self.assertRaises(ValueError):
                from_roman(bad)
""",
    reference={
        "roman.py": r"""
_VALUES = [
    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
    (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
]


def to_roman(n):
    if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= 3999:
        raise ValueError("n must be an integer in 1..3999")
    out = []
    for value, symbol in _VALUES:
        while n >= value:
            out.append(symbol)
            n -= value
    return "".join(out)


def from_roman(s):
    if not isinstance(s, str) or not s:
        raise ValueError("invalid numeral")
    total = 0
    i = 0
    for value, symbol in _VALUES:
        while s.startswith(symbol, i):
            total += value
            i += len(symbol)
    if i != len(s) or not 1 <= total <= 3999 or to_roman(total) != s:
        raise ValueError("invalid numeral")
    return total
"""
    },
)

_LRU = Task(
    id="lru_cache",
    split="train",
    prompt=(
        "Implement class LRUCache in lru.py. LRUCache(capacity) raises ValueError if capacity < 1. "
        "get(key, default=None) returns the value (or default) and marks the key most recently used. "
        "put(key, value) inserts or updates (updating also marks it most recently used) and evicts the "
        "least recently used entry when the size exceeds capacity. len(cache) is the number of entries. "
        "'key in cache' works and does not change recency."
    ),
    files={
        "lru.py": "class LRUCache:\n    def __init__(self, capacity):\n        raise NotImplementedError\n"
    },
    hidden_tests=r"""
import unittest
from lru import LRUCache


class LRUTests(unittest.TestCase):
    def test_basic_eviction(self):
        c = LRUCache(2)
        c.put("a", 1)
        c.put("b", 2)
        self.assertEqual(c.get("a"), 1)
        c.put("c", 3)
        self.assertIsNone(c.get("b"))
        self.assertEqual(c.get("a"), 1)
        self.assertEqual(c.get("c"), 3)

    def test_update_refreshes(self):
        c = LRUCache(2)
        c.put("a", 1)
        c.put("b", 2)
        c.put("a", 10)
        c.put("c", 3)
        self.assertEqual(c.get("a"), 10)
        self.assertIsNone(c.get("b"))

    def test_default(self):
        self.assertEqual(LRUCache(1).get("x", "d"), "d")

    def test_len_and_contains(self):
        c = LRUCache(2)
        c.put("a", 1)
        c.put("b", 2)
        self.assertEqual(len(c), 2)
        self.assertIn("a", c)
        c.put("c", 3)
        self.assertEqual(len(c), 2)
        self.assertNotIn("a", c)

    def test_contains_does_not_refresh(self):
        c = LRUCache(2)
        c.put("a", 1)
        c.put("b", 2)
        self.assertIn("a", c)
        c.put("c", 3)
        self.assertNotIn("a", c)
        self.assertIn("b", c)

    def test_invalid_capacity(self):
        for bad in (0, -1):
            with self.assertRaises(ValueError):
                LRUCache(bad)

    def test_capacity_one(self):
        c = LRUCache(1)
        c.put("a", 1)
        c.put("b", 2)
        self.assertIsNone(c.get("a"))
        self.assertEqual(c.get("b"), 2)
""",
    reference={
        "lru.py": r"""
from collections import OrderedDict


class LRUCache:
    def __init__(self, capacity):
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        self.capacity = capacity
        self._data = OrderedDict()

    def get(self, key, default=None):
        if key not in self._data:
            return default
        self._data.move_to_end(key)
        return self._data[key]

    def put(self, key, value):
        self._data[key] = value
        self._data.move_to_end(key)
        while len(self._data) > self.capacity:
            self._data.popitem(last=False)

    def __len__(self):
        return len(self._data)

    def __contains__(self, key):
        return key in self._data
"""
    },
)

_INTERVALS = Task(
    id="intervals",
    split="train",
    prompt=(
        "Implement merge_intervals(intervals) in intervals.py. The input is a list of (start, end) pairs "
        "(tuples or lists), in any order. Return a new sorted list of tuples where overlapping or touching "
        "intervals are merged, for example [(1, 4), (4, 5)] becomes [(1, 5)]. An empty input returns []. "
        "A pair with start > end raises ValueError. Do not modify the input."
    ),
    files={
        "intervals.py": "def merge_intervals(intervals):\n    raise NotImplementedError\n"
    },
    hidden_tests=r"""
import unittest
from intervals import merge_intervals


class IntervalTests(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(
            merge_intervals([(1, 3), (2, 6), (8, 10), (15, 18)]), [(1, 6), (8, 10), (15, 18)]
        )

    def test_touching(self):
        self.assertEqual(merge_intervals([(1, 4), (4, 5)]), [(1, 5)])

    def test_empty(self):
        self.assertEqual(merge_intervals([]), [])

    def test_unsorted(self):
        self.assertEqual(merge_intervals([(5, 6), (1, 2)]), [(1, 2), (5, 6)])

    def test_contained(self):
        self.assertEqual(merge_intervals([(1, 10), (2, 3)]), [(1, 10)])

    def test_lists_in_tuples_out(self):
        result = merge_intervals([[1, 3], [2, 4]])
        self.assertEqual(result, [(1, 4)])
        self.assertIsInstance(result[0], tuple)

    def test_invalid(self):
        with self.assertRaises(ValueError):
            merge_intervals([(3, 1)])

    def test_no_mutation(self):
        data = [(5, 6), (1, 2)]
        merge_intervals(data)
        self.assertEqual(data, [(5, 6), (1, 2)])

    def test_negatives(self):
        self.assertEqual(merge_intervals([(-5, -1), (-3, 2)]), [(-5, 2)])
""",
    reference={
        "intervals.py": r"""
def merge_intervals(intervals):
    pairs = [(a, b) for a, b in intervals]
    for a, b in pairs:
        if a > b:
            raise ValueError("start must not exceed end")
    pairs.sort()
    merged = []
    for a, b in pairs:
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged
"""
    },
)

_CALC = Task(
    id="calculator",
    split="heldout",
    prompt=(
        "Implement evaluate(expr) in calc.py: a parser and evaluator for arithmetic expressions without "
        "using eval, exec, or ast.literal_eval. Support decimal numbers, + - * /, ^ for exponentiation "
        "(right associative, binding tighter than * and /), parentheses, unary minus, and arbitrary "
        "whitespace. Return a float. Division by zero raises ZeroDivisionError. Any malformed input "
        "(empty string, unbalanced parentheses, trailing operator, unknown characters, two numbers in a "
        "row) raises ValueError."
    ),
    files={"calc.py": "def evaluate(expr):\n    raise NotImplementedError\n"},
    hidden_tests=r"""
import unittest
from calc import evaluate


class CalcTests(unittest.TestCase):
    def test_precedence(self):
        self.assertEqual(evaluate("2+3*4"), 14)
        self.assertEqual(evaluate("(2+3)*4"), 20)

    def test_power_right_associative(self):
        self.assertEqual(evaluate("2^3^2"), 512)

    def test_unary_minus(self):
        self.assertEqual(evaluate("-(2+3)"), -5)
        self.assertEqual(evaluate("2*-3"), -6)

    def test_decimals_and_whitespace(self):
        self.assertEqual(evaluate(" 1.5 + 2.5 "), 4.0)
        self.assertEqual(evaluate(".5*4"), 2.0)

    def test_division(self):
        self.assertEqual(evaluate("10/4"), 2.5)

    def test_nested(self):
        self.assertEqual(evaluate("2*(3+4)*5"), 70)
        self.assertEqual(evaluate("((2))"), 2)

    def test_returns_float(self):
        self.assertIsInstance(evaluate("1+1"), float)

    def test_zero_division(self):
        with self.assertRaises(ZeroDivisionError):
            evaluate("1/0")

    def test_malformed(self):
        for bad in ("", "2+", "(1+2", "abc", "1 2", "1+*2", ")"):
            with self.assertRaises(ValueError):
                evaluate(bad)
""",
    reference={
        "calc.py": r"""
import re

_TOKEN = re.compile(r"\s*(?:(\d+\.?\d*|\.\d+)|(\S))")


def _tokenize(expr):
    tokens = []
    pos = 0
    while True:
        m = _TOKEN.match(expr, pos)
        if m is None:
            break
        pos = m.end()
        if m.group(1) is not None:
            tokens.append(float(m.group(1)))
        elif m.group(2) in "+-*/^()":
            tokens.append(m.group(2))
        else:
            raise ValueError("unexpected character: " + m.group(2))
    return tokens


class _Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.i = 0

    def peek(self):
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def take(self):
        tok = self.peek()
        self.i += 1
        return tok

    def expression(self):
        value = self.term()
        while self.peek() in ("+", "-"):
            op = self.take()
            rhs = self.term()
            value = value + rhs if op == "+" else value - rhs
        return value

    def term(self):
        value = self.unary()
        while self.peek() in ("*", "/"):
            op = self.take()
            rhs = self.unary()
            value = value * rhs if op == "*" else value / rhs
        return value

    def unary(self):
        if self.peek() == "-":
            self.take()
            return -self.unary()
        return self.power()

    def power(self):
        base = self.atom()
        if self.peek() == "^":
            self.take()
            result = base ** self.unary()
            if isinstance(result, complex):
                raise ValueError("complex result")
            return result
        return base

    def atom(self):
        tok = self.take()
        if isinstance(tok, float):
            return tok
        if tok == "(":
            value = self.expression()
            if self.take() != ")":
                raise ValueError("expected )")
            return value
        raise ValueError("unexpected token")


def evaluate(expr):
    tokens = _tokenize(expr)
    if not tokens:
        raise ValueError("empty expression")
    parser = _Parser(tokens)
    value = parser.expression()
    if parser.peek() is not None:
        raise ValueError("trailing input")
    return value
"""
    },
)

_TOPO = Task(
    id="toposort",
    split="heldout",
    prompt=(
        "Implement topological_sort(graph) in topo.py. graph maps each node to the list of nodes it depends "
        "on. Return a list of all nodes (including nodes that appear only as dependencies) in which every "
        "node comes after its dependencies. When several nodes are available, always pick the "
        "alphabetically smallest, so the result is deterministic. A cycle (including a self-dependency) "
        "raises ValueError. An empty graph returns []. Do not modify the input."
    ),
    files={"topo.py": "def topological_sort(graph):\n    raise NotImplementedError\n"},
    hidden_tests=r"""
import unittest
from topo import topological_sort


class TopoTests(unittest.TestCase):
    def test_chain(self):
        self.assertEqual(topological_sort({"a": ["b", "c"], "b": ["c"], "c": []}), ["c", "b", "a"])

    def test_independent_sorted(self):
        self.assertEqual(topological_sort({"z": [], "x": [], "y": []}), ["x", "y", "z"])

    def test_tie_break(self):
        graph = {"d": ["a"], "c": ["a"], "b": [], "a": []}
        self.assertEqual(topological_sort(graph), ["a", "b", "c", "d"])

    def test_dependency_only_node(self):
        self.assertEqual(topological_sort({"a": ["b"]}), ["b", "a"])

    def test_duplicates(self):
        self.assertEqual(topological_sort({"a": ["b", "b"]}), ["b", "a"])

    def test_empty(self):
        self.assertEqual(topological_sort({}), [])

    def test_cycle(self):
        with self.assertRaises(ValueError):
            topological_sort({"a": ["b"], "b": ["a"]})

    def test_self_loop(self):
        with self.assertRaises(ValueError):
            topological_sort({"a": ["a"]})

    def test_no_mutation(self):
        graph = {"a": ["b"], "b": []}
        topological_sort(graph)
        self.assertEqual(graph, {"a": ["b"], "b": []})
""",
    reference={
        "topo.py": r"""
import heapq


def topological_sort(graph):
    deps = {}
    for node, requirements in graph.items():
        deps.setdefault(node, set()).update(requirements)
        for r in requirements:
            deps.setdefault(r, set())
    dependents = {n: [] for n in deps}
    remaining = {n: len(d) for n, d in deps.items()}
    for node, d in deps.items():
        for r in d:
            dependents[r].append(node)
    heap = [n for n, c in remaining.items() if c == 0]
    heapq.heapify(heap)
    order = []
    while heap:
        node = heapq.heappop(heap)
        order.append(node)
        for nxt in dependents[node]:
            remaining[nxt] -= 1
            if remaining[nxt] == 0:
                heapq.heappush(heap, nxt)
    if len(order) != len(deps):
        raise ValueError("cycle detected")
    return order
"""
    },
)

_DRAWDOWN = Task(
    id="drawdown_sharpe",
    split="heldout",
    prompt=(
        "Implement two functions in returns.py. max_drawdown(prices) takes a list of positive prices and "
        "returns the largest peak-to-trough decline as a fraction of the peak (0.0 if prices never fall). "
        "It raises ValueError for an empty list or any non-positive price. "
        "annualized_sharpe(returns, risk_free_per_period=0.0, periods_per_year=252) returns "
        "mean(excess) / sample_stdev(excess) * sqrt(periods_per_year), where excess is each return minus "
        "risk_free_per_period and sample_stdev uses n-1 in the denominator. It raises ValueError for fewer "
        "than 2 returns and returns 0.0 when the standard deviation is zero."
    ),
    files={
        "returns.py": (
            "def max_drawdown(prices):\n    raise NotImplementedError\n\n\n"
            "def annualized_sharpe(returns, risk_free_per_period=0.0, periods_per_year=252):\n"
            "    raise NotImplementedError\n"
        )
    },
    hidden_tests=r"""
import math
import statistics
import unittest
from returns import annualized_sharpe, max_drawdown


class DrawdownTests(unittest.TestCase):
    def test_known(self):
        self.assertAlmostEqual(max_drawdown([100, 120, 90, 110, 80, 130]), 1 / 3)

    def test_monotonic_up(self):
        self.assertEqual(max_drawdown([1, 2, 3]), 0.0)

    def test_monotonic_down(self):
        self.assertAlmostEqual(max_drawdown([3, 2, 1]), 2 / 3)

    def test_single(self):
        self.assertEqual(max_drawdown([5]), 0.0)

    def test_invalid(self):
        for bad in ([], [1, 0, 2], [1, -3]):
            with self.assertRaises(ValueError):
                max_drawdown(bad)


class SharpeTests(unittest.TestCase):
    def test_default(self):
        r = [0.01, 0.02, -0.01, 0.03]
        expected = statistics.mean(r) / statistics.stdev(r) * math.sqrt(252)
        self.assertAlmostEqual(annualized_sharpe(r), expected, places=9)

    def test_risk_free_and_periods(self):
        r = [0.01, 0.02, -0.01, 0.03]
        ex = [x - 0.001 for x in r]
        expected = statistics.mean(ex) / statistics.stdev(ex) * math.sqrt(12)
        self.assertAlmostEqual(annualized_sharpe(r, 0.001, 12), expected, places=9)

    def test_constant_returns(self):
        self.assertEqual(annualized_sharpe([0.01] * 5), 0.0)

    def test_too_few(self):
        for bad in ([], [0.01]):
            with self.assertRaises(ValueError):
                annualized_sharpe(bad)
""",
    reference={
        "returns.py": r"""
import math
import statistics


def max_drawdown(prices):
    if len(prices) == 0:
        raise ValueError("prices must not be empty")
    if any(p <= 0 for p in prices):
        raise ValueError("prices must be positive")
    peak = prices[0]
    worst = 0.0
    for p in prices:
        peak = max(peak, p)
        worst = max(worst, (peak - p) / peak)
    return worst


def annualized_sharpe(returns, risk_free_per_period=0.0, periods_per_year=252):
    if len(returns) < 2:
        raise ValueError("need at least two returns")
    excess = [r - risk_free_per_period for r in returns]
    sd = statistics.stdev(excess)
    if sd == 0:
        return 0.0
    return statistics.mean(excess) / sd * math.sqrt(periods_per_year)
"""
    },
)

BUILTIN_TASKS: list[Task] = [
    _FIZZBUZZ,
    _MEDIAN,
    _ROMAN,
    _LRU,
    _INTERVALS,
    _CALC,
    _TOPO,
    dataclasses.replace(_DRAWDOWN, track="finance"),
    *FINANCE_TASKS,
    *ISSUE_TASKS,
]
