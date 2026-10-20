"""More held-out and fresh tasks, so that the final comparisons rest on enough tasks to say anything.

Every task here is checked by `validate_tasks`: the starter files must fail the hidden tests and the
reference solution must pass them. Only held-out and fresh tasks live in this module; the search never
selects on them.
"""

from __future__ import annotations

from backend.evaluation.tasks import Task

_RLE = Task(
    id="rle_codec",
    split="heldout",
    prompt=(
        "Implement encode(s) and decode(s) in rle.py (run-length coding). encode('aaabcc') returns '3a1b2c': every "
        "run of a repeated character becomes its length followed by the character, including runs of length 1. "
        "encode('') returns ''. encode raises ValueError if s contains a digit. decode reverses encode, and counts "
        "can have several digits ('12a' decodes to twelve a's). decode('') returns ''. decode raises ValueError "
        "for malformed input: a character without a count, a count without a character, or a count of zero."
    ),
    files={
        "rle.py": "def encode(s):\n    raise NotImplementedError\n\n\ndef decode(s):\n    raise NotImplementedError\n"
    },
    hidden_tests=r"""
import unittest
from rle import decode, encode


class RleTests(unittest.TestCase):
    def test_encode_basic(self):
        self.assertEqual(encode("aaabcc"), "3a1b2c")
        self.assertEqual(encode("a"), "1a")
        self.assertEqual(encode(""), "")

    def test_encode_long_run(self):
        self.assertEqual(encode("a" * 12), "12a")
        self.assertEqual(encode("a" * 10 + "b"), "10a1b")

    def test_encode_rejects_digits(self):
        with self.assertRaises(ValueError):
            encode("ab1")

    def test_decode_basic(self):
        self.assertEqual(decode("3a1b2c"), "aaabcc")
        self.assertEqual(decode(""), "")

    def test_decode_multi_digit_count(self):
        self.assertEqual(decode("12a"), "a" * 12)
        self.assertEqual(decode("10a1b"), "a" * 10 + "b")

    def test_decode_rejects_malformed(self):
        for bad in ("a", "3", "3a2", "0a", "ab", "3a4"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    decode(bad)

    def test_round_trip(self):
        for text in ("", "x", "aabbbbcd", "zzzzzzzzzzzzzz", "ab ab  ab"):
            with self.subTest(text=text):
                self.assertEqual(decode(encode(text)), text)

    def test_adjacent_runs_stay_separate(self):
        self.assertEqual(encode("aabbaa"), "2a2b2a")
""",
    reference={
        "rle.py": """def encode(s):
    if any(ch.isdigit() for ch in s):
        raise ValueError("digits cannot be encoded")
    out = []
    i = 0
    while i < len(s):
        j = i
        while j < len(s) and s[j] == s[i]:
            j += 1
        out.append(f"{j - i}{s[i]}")
        i = j
    return "".join(out)


def decode(s):
    out = []
    i = 0
    while i < len(s):
        j = i
        while j < len(s) and s[j].isdigit():
            j += 1
        if j == i or j == len(s):
            raise ValueError("malformed input")
        count = int(s[i:j])
        if count == 0:
            raise ValueError("zero count")
        out.append(s[j] * count)
        i = j + 1
    return "".join(out)
"""
    },
)

_DURATION = Task(
    id="parse_duration",
    split="heldout",
    prompt=(
        "Implement parse_duration(text) in duration.py. It converts strings such as '1h30m15s' into a whole number of "
        "seconds. Units are d (86400), h (3600), m (60) and s (1), each written as a non-negative integer followed by "
        "the unit, in any order, with optional spaces between components. Each unit may appear at most once. Raise "
        "ValueError for an empty string, unknown units, a missing number or unit, a repeated unit, or a "
        "non-integer number such as '1.5h'."
    ),
    files={"duration.py": "def parse_duration(text):\n    raise NotImplementedError\n"},
    hidden_tests=r"""
import unittest
from duration import parse_duration


class DurationTests(unittest.TestCase):
    def test_combined(self):
        self.assertEqual(parse_duration("1h30m15s"), 5415)
        self.assertEqual(parse_duration("1d 2h 3m 4s"), 93784)

    def test_single_units(self):
        self.assertEqual(parse_duration("2d"), 172800)
        self.assertEqual(parse_duration("45s"), 45)
        self.assertEqual(parse_duration("90m"), 5400)
        self.assertEqual(parse_duration("0s"), 0)

    def test_any_order(self):
        self.assertEqual(parse_duration("30m1h"), 5400)

    def test_returns_an_int(self):
        self.assertIsInstance(parse_duration("5m"), int)

    def test_invalid(self):
        for bad in ("", "   ", "abc", "1x", "5", "h", "1h1h", "1.5h", "1h 30", "-5s", "1h-5m"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    parse_duration(bad)
""",
    reference={
        "duration.py": """import re

_UNITS = {"d": 86400, "h": 3600, "m": 60, "s": 1}
_PART = re.compile(r"(\\d+)([a-z])")


def parse_duration(text):
    stripped = text.replace(" ", "")
    if not stripped:
        raise ValueError("empty duration")
    pos, seen, total = 0, set(), 0
    while pos < len(stripped):
        match = _PART.match(stripped, pos)
        if not match:
            raise ValueError(f"bad duration: {text!r}")
        number, unit = match.groups()
        if unit not in _UNITS or unit in seen:
            raise ValueError(f"bad unit: {unit!r}")
        seen.add(unit)
        total += int(number) * _UNITS[unit]
        pos = match.end()
    return total
"""
    },
)

_BLACK_SCHOLES = Task(
    id="black_scholes_call",
    split="heldout",
    track="finance",
    prompt=(
        "Implement black_scholes_call(S, K, T, r, sigma) in bs.py: the Black-Scholes price of a European call on a "
        "non-dividend-paying asset. S is spot, K strike, T years to expiry, r the continuously compounded risk-free "
        "rate, sigma the annual volatility. Use math.erf for the normal CDF. If T <= 0 return the intrinsic value "
        "max(S - K, 0). If sigma <= 0 return the discounted intrinsic value max(S - K*exp(-r*T), 0). Raise "
        "ValueError if S <= 0 or K <= 0."
    ),
    files={
        "bs.py": "def black_scholes_call(S, K, T, r, sigma):\n    raise NotImplementedError\n"
    },
    hidden_tests=r"""
import math
import unittest
from bs import black_scholes_call


class BlackScholesTests(unittest.TestCase):
    def test_textbook_value(self):
        self.assertAlmostEqual(black_scholes_call(100, 100, 1, 0.05, 0.2), 10.4506, places=3)

    def test_expired_option_is_intrinsic(self):
        self.assertEqual(black_scholes_call(110, 100, 0, 0.05, 0.2), 10)
        self.assertEqual(black_scholes_call(90, 100, 0, 0.05, 0.2), 0)
        self.assertEqual(black_scholes_call(110, 100, -1, 0.05, 0.2), 10)

    def test_zero_volatility_is_discounted_intrinsic(self):
        expected = 100 - 90 * math.exp(-0.05)
        self.assertAlmostEqual(black_scholes_call(100, 90, 1, 0.05, 0), expected)
        self.assertEqual(black_scholes_call(50, 90, 1, 0.05, 0), 0)

    def test_increases_with_volatility(self):
        low = black_scholes_call(100, 100, 1, 0.02, 0.1)
        high = black_scholes_call(100, 100, 1, 0.02, 0.4)
        self.assertGreater(high, low)

    def test_bounds(self):
        price = black_scholes_call(100, 105, 0.5, 0.03, 0.25)
        self.assertGreaterEqual(price, max(100 - 105 * math.exp(-0.03 * 0.5), 0))
        self.assertLessEqual(price, 100)

    def test_deep_in_the_money_tracks_forward_intrinsic(self):
        price = black_scholes_call(200, 50, 1, 0.05, 0.2)
        self.assertAlmostEqual(price, 200 - 50 * math.exp(-0.05), places=4)

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            black_scholes_call(0, 100, 1, 0.05, 0.2)
        with self.assertRaises(ValueError):
            black_scholes_call(100, -1, 1, 0.05, 0.2)
""",
    reference={
        "bs.py": """import math


def _cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def black_scholes_call(S, K, T, r, sigma):
    if S <= 0 or K <= 0:
        raise ValueError("S and K must be positive")
    if T <= 0:
        return max(S - K, 0.0)
    if sigma <= 0:
        return max(S - K * math.exp(-r * T), 0.0)
    root = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / root
    d2 = d1 - root
    return S * _cdf(d1) - K * math.exp(-r * T) * _cdf(d2)
"""
    },
)

_DRAWDOWN_LEN = Task(
    id="longest_drawdown",
    split="heldout",
    track="finance",
    prompt=(
        "Implement longest_drawdown(prices) in dd.py. A drawdown period is a time index whose price is strictly below "
        "the highest price seen up to and including that index. Return the length of the longest run of consecutive "
        "drawdown periods (0 if there are none). Raise ValueError if prices is empty."
    ),
    files={"dd.py": "def longest_drawdown(prices):\n    raise NotImplementedError\n"},
    hidden_tests=r"""
import unittest
from dd import longest_drawdown


class LongestDrawdownTests(unittest.TestCase):
    def test_two_equal_runs(self):
        self.assertEqual(longest_drawdown([100, 90, 95, 100, 99, 98, 101]), 2)

    def test_recovery_to_the_peak_ends_the_run(self):
        self.assertEqual(longest_drawdown([100, 90, 100, 90]), 1)

    def test_run_that_never_recovers(self):
        self.assertEqual(longest_drawdown([100, 99, 98, 97, 96]), 4)

    def test_monotonic_rise_has_none(self):
        self.assertEqual(longest_drawdown([1, 2, 3, 4]), 0)
        self.assertEqual(longest_drawdown([5]), 0)
        self.assertEqual(longest_drawdown([5, 5, 5]), 0)

    def test_new_peak_resets_the_reference(self):
        self.assertEqual(longest_drawdown([10, 12, 11, 11.5, 11.9, 12.5, 12, 11]), 3)

    def test_longest_of_several(self):
        self.assertEqual(longest_drawdown([10, 9, 10, 9, 8, 7, 10, 9]), 3)

    def test_empty(self):
        with self.assertRaises(ValueError):
            longest_drawdown([])
""",
    reference={
        "dd.py": """def longest_drawdown(prices):
    if not prices:
        raise ValueError("prices is empty")
    peak, run, best = prices[0], 0, 0
    for price in prices:
        if price > peak:
            peak = price
        if price < peak:
            run += 1
            best = max(best, run)
        else:
            run = 0
    return best
"""
    },
)

_WRAP = Task(
    id="word_wrap",
    split="fresh",
    prompt=(
        "Implement wrap(text, width) in wrap.py. It splits text into words on any whitespace and packs them greedily "
        "into lines of at most width characters, joining words on a line with a single space. A word longer than "
        "width goes on its own line, unbroken. Return a list of lines; empty or all-whitespace text gives []. "
        "Raise ValueError if width < 1."
    ),
    files={"wrap.py": "def wrap(text, width):\n    raise NotImplementedError\n"},
    hidden_tests=r"""
import unittest
from wrap import wrap


class WrapTests(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(wrap("the quick brown fox", 10), ["the quick", "brown fox"])

    def test_exact_fit(self):
        self.assertEqual(wrap("abc def", 7), ["abc def"])

    def test_collapses_whitespace(self):
        self.assertEqual(wrap("a  b   c", 3), ["a b", "c"])
        self.assertEqual(wrap("a\nb\tc", 5), ["a b c"])

    def test_long_word_is_kept_whole(self):
        self.assertEqual(
            wrap("supercalifragilistic is long", 10), ["supercalifragilistic", "is long"]
        )

    def test_empty(self):
        self.assertEqual(wrap("", 5), [])
        self.assertEqual(wrap("   \n ", 5), [])

    def test_width_must_be_positive(self):
        with self.assertRaises(ValueError):
            wrap("abc", 0)

    def test_no_line_exceeds_width_unless_one_word(self):
        lines = wrap("one two three four five six seven eight nine ten", 12)
        self.assertTrue(all(len(line) <= 12 for line in lines))
        self.assertEqual(" ".join(lines), "one two three four five six seven eight nine ten")
""",
    reference={
        "wrap.py": """def wrap(text, width):
    if width < 1:
        raise ValueError("width must be at least 1")
    lines, current = [], ""
    for word in text.split():
        if not current:
            current = word
        elif len(current) + 1 + len(word) <= width:
            current += " " + word
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines
"""
    },
)

_BRACKETS = Task(
    id="bracket_error_index",
    split="fresh",
    prompt=(
        "Implement first_error(s) in brackets.py. The string may contain the bracket pairs (), [] and {} mixed with "
        "any other characters, which are ignored. Return -1 if the brackets are balanced and properly nested. "
        "Otherwise return the 0-based index of the first problem: a closing bracket that has no matching opener "
        "or closes the wrong kind, or, if the scan ends with openers still open, the index of the earliest "
        "opener that was never closed."
    ),
    files={"brackets.py": "def first_error(s):\n    raise NotImplementedError\n"},
    hidden_tests=r"""
import unittest
from brackets import first_error


class BracketTests(unittest.TestCase):
    def test_balanced(self):
        for ok in ("", "()", "{[()]}", "a(b)c", "([]{})", "no brackets at all"):
            with self.subTest(ok=ok):
                self.assertEqual(first_error(ok), -1)

    def test_wrong_kind(self):
        self.assertEqual(first_error("(]"), 1)
        self.assertEqual(first_error("([)]"), 2)

    def test_unmatched_closer(self):
        self.assertEqual(first_error(")"), 0)
        self.assertEqual(first_error("(()))"), 4)
        self.assertEqual(first_error("ab]"), 2)

    def test_unclosed_openers_report_the_earliest(self):
        self.assertEqual(first_error("("), 0)
        self.assertEqual(first_error("(()"), 0)
        self.assertEqual(first_error("a[b(c"), 1)
        self.assertEqual(first_error("(("), 0)

    def test_first_problem_wins(self):
        self.assertEqual(first_error("(]("), 1)
""",
    reference={
        "brackets.py": """PAIRS = {")": "(", "]": "[", "}": "{"}


def first_error(s):
    stack = []
    for i, ch in enumerate(s):
        if ch in "([{":
            stack.append((ch, i))
        elif ch in PAIRS:
            if not stack or stack[-1][0] != PAIRS[ch]:
                return i
            stack.pop()
    return stack[0][1] if stack else -1
"""
    },
)

_SUBARRAY = Task(
    id="max_subarray",
    split="fresh",
    prompt=(
        "Implement max_subarray(nums) in sub.py. It finds the contiguous, non-empty slice of nums with the largest "
        "sum and returns the tuple (total, start, end) with start and end inclusive 0-based indices. If several "
        "slices tie, return the one with the smallest start, and among those the smallest end. Raise ValueError "
        "if nums is empty."
    ),
    files={"sub.py": "def max_subarray(nums):\n    raise NotImplementedError\n"},
    hidden_tests=r"""
import unittest
from sub import max_subarray


class SubarrayTests(unittest.TestCase):
    def test_classic(self):
        self.assertEqual(max_subarray([1, -2, 3, 4, -1, 2, 1, -5, 4]), (9, 2, 6))

    def test_all_negative_picks_the_largest_element(self):
        self.assertEqual(max_subarray([-3, -1, -2]), (-1, 1, 1))

    def test_single(self):
        self.assertEqual(max_subarray([5]), (5, 0, 0))

    def test_ties_prefer_earliest_start_then_shortest(self):
        self.assertEqual(max_subarray([1, -1, 1]), (1, 0, 0))
        self.assertEqual(max_subarray([0, 0, 0]), (0, 0, 0))
        self.assertEqual(max_subarray([2, -2, 2]), (2, 0, 0))

    def test_whole_array(self):
        self.assertEqual(max_subarray([2, -1, 2]), (3, 0, 2))

    def test_negative_prefix_is_dropped(self):
        self.assertEqual(max_subarray([-5, 4, -1, 3]), (6, 1, 3))

    def test_empty(self):
        with self.assertRaises(ValueError):
            max_subarray([])
""",
    reference={
        "sub.py": """def max_subarray(nums):
    if not nums:
        raise ValueError("nums is empty")
    best = (nums[0], 0, 0)
    for start in range(len(nums)):
        total = 0
        for end in range(start, len(nums)):
            total += nums[end]
            if total > best[0]:
                best = (total, start, end)
    return best
"""
    },
)

_SORTINO = Task(
    id="sortino_ratio",
    split="fresh",
    track="finance",
    prompt=(
        "Implement sortino_ratio(returns, target=0.0, periods_per_year=252) in sortino.py. Downside deviation is "
        "sqrt(mean(min(r - target, 0)**2)) taken over ALL returns (not only the below-target ones). The ratio is "
        "(mean(returns) - target) / downside_deviation * sqrt(periods_per_year). If the downside deviation is 0, "
        "return math.inf when the mean exceeds target and 0.0 otherwise. Raise ValueError if returns is empty."
    ),
    files={
        "sortino.py": "def sortino_ratio(returns, target=0.0, periods_per_year=252):\n    raise NotImplementedError\n"
    },
    hidden_tests=r"""
import math
import unittest
from sortino import sortino_ratio

R = [0.01, -0.02, 0.03, -0.01]


class SortinoTests(unittest.TestCase):
    def test_known_value(self):
        # mean 0.0025, downside deviation sqrt(0.000125)
        self.assertAlmostEqual(
            sortino_ratio(R, periods_per_year=1), 0.0025 / math.sqrt(0.000125), places=6
        )

    def test_annualisation(self):
        one = sortino_ratio(R, periods_per_year=1)
        self.assertAlmostEqual(sortino_ratio(R), one * math.sqrt(252), places=6)

    def test_target_shifts_both_terms(self):
        # excess over 0.005: [0.005, -0.025, 0.025, -0.015]; mean -0.0025
        # downside: [0, -0.025, 0, -0.015] -> sqrt((0.000625 + 0.000225) / 4)
        expected = -0.0025 / math.sqrt(0.00085 / 4)
        self.assertAlmostEqual(sortino_ratio(R, target=0.005, periods_per_year=1), expected, places=6)

    def test_no_downside_is_infinite_when_positive(self):
        self.assertEqual(sortino_ratio([0.01, 0.02, 0.0]), math.inf)

    def test_no_downside_and_no_excess_is_zero(self):
        self.assertEqual(sortino_ratio([0.0, 0.0]), 0.0)
        self.assertEqual(sortino_ratio([0.01, 0.01], target=0.01), 0.0)

    def test_empty(self):
        with self.assertRaises(ValueError):
            sortino_ratio([])
""",
    reference={
        "sortino.py": """import math


def sortino_ratio(returns, target=0.0, periods_per_year=252):
    if not returns:
        raise ValueError("returns is empty")
    n = len(returns)
    mean_excess = sum(returns) / n - target
    downside = math.sqrt(sum(min(r - target, 0.0) ** 2 for r in returns) / n)
    if downside == 0:
        return math.inf if mean_excess > 0 else 0.0
    return mean_excess / downside * math.sqrt(periods_per_year)
"""
    },
)

EXTRA_TASKS = [
    _RLE,
    _DURATION,
    _BLACK_SCHOLES,
    _DRAWDOWN_LEN,
    _WRAP,
    _BRACKETS,
    _SUBARRAY,
    _SORTINO,
]
