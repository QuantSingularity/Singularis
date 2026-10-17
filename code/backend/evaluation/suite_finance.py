from __future__ import annotations

from backend.evaluation.tasks import Task

_EWMA = Task(
    id="ewma_volatility",
    split="train",
    track="finance",
    prompt=(
        "Implement ewma_volatility(returns, lam=0.94) in ewma.py. It returns a list with one volatility per "
        "input return. Let s2[0] = returns[0]**2 and s2[t] = lam * s2[t-1] + (1 - lam) * returns[t]**2 for "
        "t >= 1. Element t of the result is sqrt(s2[t]). Raise ValueError if returns is empty or if lam is not "
        "strictly between 0 and 1."
    ),
    files={
        "ewma.py": "def ewma_volatility(returns, lam=0.94):\n    raise NotImplementedError\n"
    },
    hidden_tests=r"""
import math
import unittest
from ewma import ewma_volatility


class EwmaTests(unittest.TestCase):
    def test_known_values(self):
        out = ewma_volatility([0.01, -0.02, 0.015], lam=0.9)
        self.assertEqual(len(out), 3)
        self.assertAlmostEqual(out[0], 0.01)
        self.assertAlmostEqual(out[1], math.sqrt(1.3e-4))
        self.assertAlmostEqual(out[2], math.sqrt(1.395e-4))

    def test_default_lambda(self):
        out = ewma_volatility([0.02, 0.01])
        self.assertAlmostEqual(out[1], math.sqrt(0.94 * 0.02 ** 2 + 0.06 * 0.01 ** 2))

    def test_single_value(self):
        out = ewma_volatility([-0.03])
        self.assertEqual(len(out), 1)
        self.assertAlmostEqual(out[0], 0.03)

    def test_constant_returns_keep_constant_volatility(self):
        for v in ewma_volatility([0.01] * 6, lam=0.8):
            self.assertAlmostEqual(v, 0.01)

    def test_invalid_inputs(self):
        for args in (([],), ([0.01], 0.0), ([0.01], 1.0), ([0.01], 1.5), ([0.01], -0.1)):
            with self.assertRaises(ValueError):
                ewma_volatility(*args)
""",
    reference={
        "ewma.py": r"""
import math


def ewma_volatility(returns, lam=0.94):
    if len(returns) == 0:
        raise ValueError("returns must not be empty")
    if not 0 < lam < 1:
        raise ValueError("lam must be strictly between 0 and 1")
    s2 = returns[0] ** 2
    out = [math.sqrt(s2)]
    for r in returns[1:]:
        s2 = lam * s2 + (1 - lam) * r ** 2
        out.append(math.sqrt(s2))
    return out
"""
    },
)

_VAR = Task(
    id="historical_var",
    split="train",
    track="finance",
    prompt=(
        "Implement historical_var_cvar(returns, alpha=0.95) in var.py. Losses are the negated returns. Sort "
        "the losses ascending, let index = ceil(round(alpha * n, 9)) - 1 where n is the number of returns, "
        "VaR is losses[index], and CVaR is the mean of losses[index:]. Return the tuple (var, cvar). Raise "
        "ValueError if returns is empty or alpha is not strictly between 0 and 1. Do not modify the input."
    ),
    files={
        "var.py": "def historical_var_cvar(returns, alpha=0.95):\n    raise NotImplementedError\n"
    },
    hidden_tests=r"""
import unittest
from var import historical_var_cvar


class VarTests(unittest.TestCase):
    def test_known_values(self):
        returns = [-0.01 * i for i in range(1, 21)]
        var, cvar = historical_var_cvar(returns, 0.95)
        self.assertAlmostEqual(var, 0.19)
        self.assertAlmostEqual(cvar, 0.195)

    def test_unsorted_with_gains(self):
        var, cvar = historical_var_cvar([0.02, -0.05, 0.01, -0.01, 0.03], 0.8)
        self.assertAlmostEqual(var, 0.01)
        self.assertAlmostEqual(cvar, 0.03)

    def test_extreme_alpha_hits_worst_loss(self):
        returns = [-0.01 * i for i in range(1, 11)]
        var, cvar = historical_var_cvar(returns, 0.99)
        self.assertAlmostEqual(var, 0.10)
        self.assertAlmostEqual(cvar, 0.10)

    def test_returns_tuple(self):
        self.assertIsInstance(historical_var_cvar([-0.1, 0.1]), tuple)

    def test_no_mutation(self):
        data = [0.02, -0.05, 0.01]
        historical_var_cvar(data, 0.5)
        self.assertEqual(data, [0.02, -0.05, 0.01])

    def test_invalid_inputs(self):
        for args in (([],), ([0.1], 0.0), ([0.1], 1.0), ([0.1], 1.2), ([0.1], -0.1)):
            with self.assertRaises(ValueError):
                historical_var_cvar(*args)
""",
    reference={
        "var.py": r"""
import math


def historical_var_cvar(returns, alpha=0.95):
    if len(returns) == 0:
        raise ValueError("returns must not be empty")
    if not 0 < alpha < 1:
        raise ValueError("alpha must be strictly between 0 and 1")
    losses = sorted(-r for r in returns)
    index = math.ceil(round(alpha * len(losses), 9)) - 1
    tail = losses[index:]
    return losses[index], sum(tail) / len(tail)
"""
    },
)

_BACKTEST = Task(
    id="sma_backtest",
    split="train",
    track="finance",
    prompt=(
        "Implement backtest_sma_crossover(prices, fast, slow, cost=0.0) in backtest.py. For each t >= slow - 1 "
        "the signal is 1 if the mean of the last `fast` prices (ending at t) is greater than the mean of the "
        "last `slow` prices, else 0; the signal is 0 before that. The position held during period t (t >= 1) is "
        "the signal at t - 1, so there is no lookahead. Start with equity[0] = 1.0. For t >= 1: "
        "equity[t] = equity[t-1] * (1 - cost if the position differs from the previous period's position, with "
        "the initial position 0, else 1) * (1 + pos * (prices[t] / prices[t-1] - 1)). Return "
        "{'equity': list of floats with one entry per price, 'trades': number of periods where the position "
        "changed}. Raise ValueError unless 1 <= fast < slow (integers), there are at least 2 prices, all prices "
        "are positive, and 0 <= cost < 1. If there are fewer than `slow` prices the strategy never trades."
    ),
    files={
        "backtest.py": "def backtest_sma_crossover(prices, fast, slow, cost=0.0):\n    raise NotImplementedError\n"
    },
    hidden_tests=r"""
import unittest
from backtest import backtest_sma_crossover

PRICES = [1, 2, 3, 2, 1, 2, 3]


class BacktestTests(unittest.TestCase):
    def test_no_cost(self):
        result = backtest_sma_crossover(PRICES, 1, 2)
        expected = [1.0, 1.0, 1.5, 1.0, 1.0, 1.0, 1.5]
        self.assertEqual(len(result["equity"]), 7)
        for got, want in zip(result["equity"], expected):
            self.assertAlmostEqual(got, want)
        self.assertEqual(result["trades"], 3)

    def test_with_cost(self):
        result = backtest_sma_crossover(PRICES, 1, 2, cost=0.01)
        expected = [1.0, 1.0, 1.485, 0.99, 0.9801, 0.9801, 1.4554485]
        for got, want in zip(result["equity"], expected):
            self.assertAlmostEqual(got, want)
        self.assertEqual(result["trades"], 3)

    def test_flat_prices_never_trade(self):
        result = backtest_sma_crossover([5.0] * 10, 2, 4)
        self.assertEqual(result["equity"], [1.0] * 10)
        self.assertEqual(result["trades"], 0)

    def test_short_history_never_trades(self):
        result = backtest_sma_crossover([1, 2, 3], 2, 5)
        self.assertEqual(result["equity"], [1.0, 1.0, 1.0])
        self.assertEqual(result["trades"], 0)

    def test_no_lookahead(self):
        a = backtest_sma_crossover([1, 2, 3, 4, 5, 6], 1, 2)["equity"]
        b = backtest_sma_crossover([1, 2, 3, 4, 5, 60], 1, 2)["equity"]
        self.assertEqual(a[:5], b[:5])

    def test_invalid_inputs(self):
        bad = [
            ([1, 2, 3], 3, 2), ([1, 2, 3], 0, 2), ([1, 2, 3], 2, 2), ([1], 1, 2),
            ([1, -2, 3], 1, 2), ([1, 2, 3], 1, 2, -0.1), ([1, 2, 3], 1, 2, 1.0), ([1, 2, 3], 1.5, 2),
        ]
        for args in bad:
            with self.assertRaises(ValueError):
                backtest_sma_crossover(*args)
""",
    reference={
        "backtest.py": r"""
def backtest_sma_crossover(prices, fast, slow, cost=0.0):
    if not (isinstance(fast, int) and isinstance(slow, int) and 1 <= fast < slow):
        raise ValueError("need integers with 1 <= fast < slow")
    if len(prices) < 2:
        raise ValueError("need at least 2 prices")
    if any(p <= 0 for p in prices):
        raise ValueError("prices must be positive")
    if not 0 <= cost < 1:
        raise ValueError("cost must be in [0, 1)")
    n = len(prices)
    signal = [0] * n
    for t in range(slow - 1, n):
        fast_mean = sum(prices[t - fast + 1:t + 1]) / fast
        slow_mean = sum(prices[t - slow + 1:t + 1]) / slow
        signal[t] = 1 if fast_mean > slow_mean else 0
    equity = [1.0]
    previous = 0
    trades = 0
    for t in range(1, n):
        position = signal[t - 1]
        value = equity[-1]
        if position != previous:
            value *= 1 - cost
            trades += 1
        value *= 1 + position * (prices[t] / prices[t - 1] - 1)
        equity.append(value)
        previous = position
    return {"equity": equity, "trades": trades}
"""
    },
)

_CLEAN = Task(
    id="clean_prices",
    split="train",
    track="finance",
    prompt=(
        "Implement clean_prices(csv_text) in prices.py. The text is a CSV with a header line (ignored) followed "
        "by 'date,close' rows; lines may end in \\n or \\r\\n. Strip whitespace around fields. Drop a row if it "
        "does not have exactly two comma separated fields, if the date is not exactly YYYY-MM-DD with a valid "
        "calendar date, or if the close is not a finite number greater than zero. If several valid rows share a "
        "date, keep the last one. Return a list of (date_string, float_close) tuples sorted by date ascending. "
        "Empty or header-only input returns []."
    ),
    files={"prices.py": "def clean_prices(csv_text):\n    raise NotImplementedError\n"},
    hidden_tests=r"""
import unittest
from prices import clean_prices


class CleanPricesTests(unittest.TestCase):
    def test_messy_input(self):
        lines = [
            "date,close", "2024-01-03, 101.5", "2024-01-02,100", "2024-01-02,100.5", "2024-01-04,",
            "2024-01-05,abc", "2024-01-06,-3", "2024-13-01,99", "20240108,99", "2024-1-9,98",
            "2024-01-10,0", "bad line without comma", "2024-01-12,1,000", "2024-01-11,102.25",
            "2024-01-13,nan", "2024-01-14,inf",
        ]
        self.assertEqual(
            clean_prices("\n".join(lines)),
            [("2024-01-02", 100.5), ("2024-01-03", 101.5), ("2024-01-11", 102.25)],
        )

    def test_invalid_duplicate_does_not_replace_valid(self):
        self.assertEqual(clean_prices("date,close\n2024-01-02,100\n2024-01-02,bad"), [("2024-01-02", 100.0)])

    def test_windows_line_endings_and_blank_lines(self):
        text = "date,close\r\n2024-02-01,10\r\n\r\n2024-01-31,9.5\r\n"
        self.assertEqual(clean_prices(text), [("2024-01-31", 9.5), ("2024-02-01", 10.0)])

    def test_empty_and_header_only(self):
        self.assertEqual(clean_prices(""), [])
        self.assertEqual(clean_prices("date,close\n"), [])

    def test_leap_day(self):
        self.assertEqual(clean_prices("h\n2024-02-29,1\n2023-02-29,2"), [("2024-02-29", 1.0)])

    def test_values_are_floats(self):
        self.assertIsInstance(clean_prices("h\n2024-01-01,5")[0][1], float)
""",
    reference={
        "prices.py": r"""
import datetime
import math
import re

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def clean_prices(csv_text):
    rows = {}
    for line in csv_text.splitlines()[1:]:
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 2:
            continue
        date, close = parts
        if not _DATE.match(date):
            continue
        try:
            datetime.date.fromisoformat(date)
            value = float(close)
        except ValueError:
            continue
        if not math.isfinite(value) or value <= 0:
            continue
        rows[date] = value
    return sorted(rows.items())
"""
    },
)

_MINVAR = Task(
    id="min_variance",
    split="heldout",
    track="finance",
    prompt=(
        "Implement min_variance_weights(cov) in portfolio.py. cov is a covariance matrix given as a list of "
        "row lists. Return the weights of the global minimum variance portfolio (shorting allowed, weights sum "
        "to 1): w = inv(cov) * 1 / (1' * inv(cov) * 1). Use only the standard library. Raise ValueError if cov "
        "is empty, not square, or singular. Do not modify the input."
    ),
    files={
        "portfolio.py": "def min_variance_weights(cov):\n    raise NotImplementedError\n"
    },
    hidden_tests=r"""
import unittest
from portfolio import min_variance_weights


class MinVarianceTests(unittest.TestCase):
    def test_diagonal(self):
        w = min_variance_weights([[0.04, 0.0], [0.0, 0.01]])
        self.assertAlmostEqual(w[0], 0.2)
        self.assertAlmostEqual(w[1], 0.8)

    def test_correlated(self):
        w = min_variance_weights([[0.04, 0.006], [0.006, 0.01]])
        self.assertAlmostEqual(w[0], 0.004 / 0.038, places=6)
        self.assertAlmostEqual(w[1], 0.034 / 0.038, places=6)

    def test_identity_three_assets(self):
        for x in min_variance_weights([[1, 0, 0], [0, 1, 0], [0, 0, 1]]):
            self.assertAlmostEqual(x, 1 / 3)

    def test_weights_sum_to_one(self):
        cov = [[0.09, 0.02, 0.01], [0.02, 0.04, 0.005], [0.01, 0.005, 0.0225]]
        self.assertAlmostEqual(sum(min_variance_weights(cov)), 1.0)

    def test_single_asset(self):
        self.assertAlmostEqual(min_variance_weights([[0.04]])[0], 1.0)

    def test_invalid_inputs(self):
        for bad in ([], [[1, 2]], [[1, 1], [1, 1]], [[1, 2], [3]]):
            with self.assertRaises(ValueError):
                min_variance_weights(bad)

    def test_no_mutation(self):
        cov = [[0.04, 0.006], [0.006, 0.01]]
        min_variance_weights(cov)
        self.assertEqual(cov, [[0.04, 0.006], [0.006, 0.01]])
""",
    reference={
        "portfolio.py": r"""
def min_variance_weights(cov):
    n = len(cov)
    if n == 0 or any(len(row) != n for row in cov):
        raise ValueError("cov must be a non-empty square matrix")
    a = [[float(x) for x in row] + [1.0] for row in cov]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[pivot][col]) < 1e-12:
            raise ValueError("matrix is singular")
        a[col], a[pivot] = a[pivot], a[col]
        for r in range(n):
            if r != col:
                factor = a[r][col] / a[col][col]
                for k in range(col, n + 1):
                    a[r][k] -= factor * a[col][k]
    x = [a[i][n] / a[i][i] for i in range(n)]
    total = sum(x)
    if abs(total) < 1e-12:
        raise ValueError("weights cannot be normalized")
    return [v / total for v in x]
"""
    },
)

_ZSCORE = Task(
    id="rolling_zscore",
    split="fresh",
    track="finance",
    prompt=(
        "Implement rolling_zscore(values, window) in zscore.py. For index t >= window - 1 the result is "
        "(values[t] - mean(w)) / stdev(w) where w is the last `window` values ending at t and stdev is the "
        "sample standard deviation (n-1). If that standard deviation is 0 the result is 0.0. For t < window - 1 "
        "the result is None. The output has the same length as the input. Raise ValueError unless window is an "
        "integer >= 2."
    ),
    files={
        "zscore.py": "def rolling_zscore(values, window):\n    raise NotImplementedError\n"
    },
    hidden_tests=r"""
import math
import unittest
from zscore import rolling_zscore


class ZScoreTests(unittest.TestCase):
    def test_linear(self):
        self.assertEqual(rolling_zscore([1, 2, 3, 4, 5], 3), [None, None, 1.0, 1.0, 1.0])

    def test_mixed(self):
        out = rolling_zscore([1, 3, 2, 5], 2)
        self.assertIsNone(out[0])
        self.assertAlmostEqual(out[1], 1 / math.sqrt(2))
        self.assertAlmostEqual(out[2], -1 / math.sqrt(2))
        self.assertAlmostEqual(out[3], 1 / math.sqrt(2))

    def test_constant_window(self):
        self.assertEqual(rolling_zscore([5, 5, 5], 3), [None, None, 0.0])

    def test_window_longer_than_data(self):
        self.assertEqual(rolling_zscore([1, 2], 5), [None, None])

    def test_empty(self):
        self.assertEqual(rolling_zscore([], 3), [])

    def test_invalid_window(self):
        for bad in (1, 0, -2, 2.5, "3"):
            with self.assertRaises(ValueError):
                rolling_zscore([1, 2, 3], bad)
""",
    reference={
        "zscore.py": r"""
import statistics


def rolling_zscore(values, window):
    if not isinstance(window, int) or isinstance(window, bool) or window < 2:
        raise ValueError("window must be an integer >= 2")
    out = []
    for t in range(len(values)):
        if t < window - 1:
            out.append(None)
            continue
        w = values[t - window + 1:t + 1]
        sd = statistics.stdev(w)
        out.append(0.0 if sd == 0 else (values[t] - statistics.mean(w)) / sd)
    return out
"""
    },
)

_BS = Task(
    id="black_scholes",
    split="fresh",
    track="finance",
    prompt=(
        "Implement black_scholes_call(S, K, T, r, sigma) and black_scholes_put(S, K, T, r, sigma) in options.py "
        "using the Black-Scholes formula for a European option on a non-dividend-paying asset. Use math.erf for "
        "the normal CDF. Raise ValueError unless S, K, T and sigma are all strictly positive (r may be any real)."
    ),
    files={
        "options.py": (
            "def black_scholes_call(S, K, T, r, sigma):\n    raise NotImplementedError\n\n\n"
            "def black_scholes_put(S, K, T, r, sigma):\n    raise NotImplementedError\n"
        )
    },
    hidden_tests=r"""
import math
import unittest
from options import black_scholes_call, black_scholes_put


class BlackScholesTests(unittest.TestCase):
    def test_known_values(self):
        self.assertAlmostEqual(black_scholes_call(100, 100, 1, 0.05, 0.2), 10.4506, places=3)
        self.assertAlmostEqual(black_scholes_put(100, 100, 1, 0.05, 0.2), 5.5735, places=3)

    def test_put_call_parity(self):
        for S, K, T, r, sigma in [(100, 90, 0.5, 0.03, 0.25), (50, 60, 2.0, 0.0, 0.4), (80, 80, 1.0, -0.01, 0.15)]:
            lhs = black_scholes_call(S, K, T, r, sigma) - black_scholes_put(S, K, T, r, sigma)
            self.assertAlmostEqual(lhs, S - K * math.exp(-r * T), places=9)

    def test_lower_bound_and_monotonic_in_vol(self):
        S, K, T, r = 200, 100, 0.25, 0.03
        self.assertGreaterEqual(black_scholes_call(S, K, T, r, 0.2) + 1e-9, S - K * math.exp(-r * T))
        self.assertGreater(black_scholes_call(100, 100, 1, 0.05, 0.3), black_scholes_call(100, 100, 1, 0.05, 0.2))

    def test_invalid_inputs(self):
        for args in [(0, 100, 1, 0.05, 0.2), (100, 0, 1, 0.05, 0.2), (100, 100, 0, 0.05, 0.2), (100, 100, 1, 0.05, 0)]:
            with self.assertRaises(ValueError):
                black_scholes_call(*args)
            with self.assertRaises(ValueError):
                black_scholes_put(*args)
""",
    reference={
        "options.py": r"""
import math


def _cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _d1_d2(S, K, T, r, sigma):
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        raise ValueError("S, K, T and sigma must be positive")
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    return d1, d1 - sigma * math.sqrt(T)


def black_scholes_call(S, K, T, r, sigma):
    d1, d2 = _d1_d2(S, K, T, r, sigma)
    return S * _cdf(d1) - K * math.exp(-r * T) * _cdf(d2)


def black_scholes_put(S, K, T, r, sigma):
    d1, d2 = _d1_d2(S, K, T, r, sigma)
    return K * math.exp(-r * T) * _cdf(-d2) - S * _cdf(-d1)
"""
    },
)

FINANCE_TASKS: list[Task] = [_EWMA, _VAR, _BACKTEST, _CLEAN, _MINVAR, _ZSCORE, _BS]
