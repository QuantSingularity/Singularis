from __future__ import annotations

from backend.evaluation.tasks import Task

TESTS_NOTE = " The tests in tests/ show how the code is used; run them with python -m unittest. Do not edit them."

# ---------------------------------------------------------------------------------------------------------------
_INVOICE = Task(
    id="invoice_cents",
    split="train",
    track="issues",
    prompt=(
        "Issue: invoice totals are sometimes off by a cent and negative amounts print wrongly (package billing/).\n\n"
        "Expected behavior:\n"
        "- to_cents parses prices as exact decimals (accepting str, int, float via str(), or Decimal) and rounds "
        "half away from zero to whole cents: to_cents('1.005') is 101, to_cents('2.675') is 268, "
        "to_cents('-1.005') is -101.\n"
        "- discount_amount(cents, pct) rounds half away from zero using exact decimal arithmetic on str(pct): "
        "discount_amount(1050, 10) is 105 and discount_amount(1005, 10) is 101.\n"
        "- tax_amount(cents, rate) does the same with str(rate): tax_amount(1005, 0.1) is 101, "
        "tax_amount(250, 0.01) is 3, tax_amount(50, 0.01) is 1.\n"
        "- build_invoice applies the discount once to the whole subtotal (not per line), then computes tax on the "
        "discounted amount: tax = tax_amount(subtotal - discount, tax_rate) and total = subtotal - discount + tax. "
        "Three lines of 0.05 with a 10% discount give a discount of 2 (not 0). It raises ValueError if any qty is "
        "not a non-negative int (bool and str are not accepted).\n"
        "- fmt_cents uses thousands separators and puts the sign first: fmt_cents(1234567) is '$12,345.67', "
        "fmt_cents(-123456) is '-$1,234.56', fmt_cents(-5) is '-$0.05'." + TESTS_NOTE
    ),
    files={
        "billing/__init__.py": "",
        "billing/money.py": "def to_cents(value):\n    return int(round(float(value) * 100))\n",
        "billing/discounts.py": "def discount_amount(cents, pct):\n    return int(cents * pct / 100)\n",
        "billing/tax.py": "def tax_amount(cents, rate):\n    return round(cents * rate)\n",
        "billing/format.py": 'def fmt_cents(cents):\n    return "$%d.%02d" % (cents // 100, cents % 100)\n',
        "billing/invoice.py": (
            "from .discounts import discount_amount\nfrom .money import to_cents\nfrom .tax import tax_amount\n\n\n"
            "def build_invoice(lines, discount_pct=0, tax_rate=0.0):\n"
            "    subtotal = 0\n    discount = 0\n    out = []\n"
            "    for line in lines:\n"
            "        unit = to_cents(line['unit_price'])\n"
            "        qty = line['qty']\n"
            "        line_cents = unit * qty\n"
            "        discount += discount_amount(line_cents, discount_pct)\n"
            "        subtotal += line_cents\n"
            "        out.append({'sku': line['sku'], 'qty': qty, 'unit_cents': unit, 'line_cents': line_cents})\n"
            "    tax = tax_amount(subtotal, tax_rate)\n"
            "    return {'subtotal': subtotal, 'discount': discount, 'tax': tax,\n"
            "            'total': subtotal - discount + tax, 'lines': out}\n"
        ),
        "tests/__init__.py": "",
        "tests/test_billing.py": (
            "import unittest\n\nfrom billing.format import fmt_cents\nfrom billing.invoice import build_invoice\n"
            "from billing.money import to_cents\n\n\nclass VisibleTests(unittest.TestCase):\n"
            "    def test_to_cents(self):\n        self.assertEqual(to_cents('2.50'), 250)\n\n"
            "    def test_plain_invoice(self):\n"
            "        inv = build_invoice([{'sku': 'A', 'unit_price': '2.50', 'qty': 2}])\n"
            "        self.assertEqual((inv['subtotal'], inv['total']), (500, 500))\n\n"
            "    def test_format(self):\n        self.assertEqual(fmt_cents(1234), '$12.34')\n"
        ),
    },
    hidden_tests=r"""
import unittest
from decimal import Decimal

from billing.discounts import discount_amount
from billing.format import fmt_cents
from billing.invoice import build_invoice
from billing.money import to_cents
from billing.tax import tax_amount


class MoneyTests(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(to_cents("2.50"), 250)

    def test_exact_decimal_rounding(self):
        self.assertEqual(to_cents("1.005"), 101)
        self.assertEqual(to_cents("2.675"), 268)
        self.assertEqual(to_cents("-1.005"), -101)

    def test_input_types(self):
        self.assertEqual(to_cents(2), 200)
        self.assertEqual(to_cents(2.5), 250)
        self.assertEqual(to_cents(Decimal("0.10")), 10)


class DiscountTaxTests(unittest.TestCase):
    def test_discount_rounds_half_up(self):
        self.assertEqual(discount_amount(1050, 10), 105)
        self.assertEqual(discount_amount(1005, 10), 101)
        self.assertEqual(discount_amount(1005, 7.5), 75)
        self.assertEqual(discount_amount(1000, 0), 0)

    def test_tax_rounds_half_up(self):
        self.assertEqual(tax_amount(1005, 0.1), 101)
        self.assertEqual(tax_amount(250, 0.01), 3)
        self.assertEqual(tax_amount(50, 0.01), 1)
        self.assertEqual(tax_amount(10000, 0.0825), 825)


class InvoiceTests(unittest.TestCase):
    def test_plain_invoice(self):
        inv = build_invoice([{"sku": "A", "unit_price": "2.50", "qty": 2}])
        self.assertEqual((inv["subtotal"], inv["discount"], inv["tax"], inv["total"]), (500, 0, 0, 500))

    def test_discount_is_applied_once_to_the_subtotal(self):
        lines = [{"sku": s, "unit_price": "0.05", "qty": 1} for s in "abc"]
        inv = build_invoice(lines, discount_pct=10)
        self.assertEqual((inv["subtotal"], inv["discount"], inv["total"]), (15, 2, 13))

    def test_tax_is_computed_on_the_discounted_amount(self):
        inv = build_invoice([{"sku": "X", "unit_price": "100.00", "qty": 1}], discount_pct=10, tax_rate=0.1)
        self.assertEqual(
            {k: inv[k] for k in ("subtotal", "discount", "tax", "total")},
            {"subtotal": 10000, "discount": 1000, "tax": 900, "total": 9900},
        )

    def test_mixed_example(self):
        lines = [{"sku": "A", "unit_price": "1.005", "qty": 3}, {"sku": "B", "unit_price": "2.50", "qty": 2}]
        inv = build_invoice(lines, discount_pct=10, tax_rate=0.0825)
        self.assertEqual((inv["subtotal"], inv["discount"], inv["tax"], inv["total"]), (803, 80, 60, 783))
        self.assertEqual(inv["lines"][0], {"sku": "A", "qty": 3, "unit_cents": 101, "line_cents": 303})

    def test_invalid_quantities(self):
        for qty in (-1, 1.5, "2", True):
            with self.assertRaises(ValueError):
                build_invoice([{"sku": "A", "unit_price": "1.00", "qty": qty}])

    def test_zero_quantity_is_allowed(self):
        self.assertEqual(build_invoice([{"sku": "A", "unit_price": "1.00", "qty": 0}])["total"], 0)


class FormatTests(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(fmt_cents(0), "$0.00")
        self.assertEqual(fmt_cents(5), "$0.05")
        self.assertEqual(fmt_cents(1234), "$12.34")
        self.assertEqual(fmt_cents(1234567), "$12,345.67")

    def test_negative_amounts(self):
        self.assertEqual(fmt_cents(-5), "-$0.05")
        self.assertEqual(fmt_cents(-123456), "-$1,234.56")
""",
    reference={
        "billing/money.py": r"""
from decimal import ROUND_HALF_UP, Decimal


def to_cents(value):
    amount = Decimal(str(value)) if not isinstance(value, Decimal) else value
    return int((amount * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
""",
        "billing/discounts.py": r"""
from decimal import ROUND_HALF_UP, Decimal


def discount_amount(cents, pct):
    return int((Decimal(cents) * Decimal(str(pct)) / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
""",
        "billing/tax.py": r"""
from decimal import ROUND_HALF_UP, Decimal


def tax_amount(cents, rate):
    return int((Decimal(cents) * Decimal(str(rate))).quantize(Decimal(1), rounding=ROUND_HALF_UP))
""",
        "billing/format.py": r"""
def fmt_cents(cents):
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return "%s$%s.%02d" % (sign, format(cents // 100, ","), cents % 100)
""",
        "billing/invoice.py": r"""
from .discounts import discount_amount
from .money import to_cents
from .tax import tax_amount


def build_invoice(lines, discount_pct=0, tax_rate=0.0):
    subtotal = 0
    out = []
    for line in lines:
        qty = line["qty"]
        if not isinstance(qty, int) or isinstance(qty, bool) or qty < 0:
            raise ValueError("qty must be a non-negative int")
        unit = to_cents(line["unit_price"])
        line_cents = unit * qty
        subtotal += line_cents
        out.append({"sku": line["sku"], "qty": qty, "unit_cents": unit, "line_cents": line_cents})
    discount = discount_amount(subtotal, discount_pct)
    tax = tax_amount(subtotal - discount, tax_rate)
    return {"subtotal": subtotal, "discount": discount, "tax": tax, "total": subtotal - discount + tax, "lines": out}
""",
    },
)

# ---------------------------------------------------------------------------------------------------------------
_LEDGER = Task(
    id="ledger_replay",
    split="train",
    track="issues",
    prompt=(
        "Issue: replaying an account from a snapshot gives wrong balances, and interest is off (package ledger/).\n\n"
        "Expected behavior:\n"
        "- Events are dicts with seq, ts, type ('deposit', 'withdraw' or 'fee') and amount (integer cents). replay "
        "applies them ordered by (ts, seq).\n"
        "- Events that share a seq are retries of the same event: only the first one in that order is applied.\n"
        "- With a snapshot {'balance': ..., 'seq': ...}, the snapshot already includes every event with "
        "seq <= snapshot['seq']; only events with a greater seq are applied.\n"
        "- replay returns {'balance': int, 'seq': highest seq applied, or the snapshot seq, or 0}.\n"
        "- A withdraw or fee that would make the balance negative raises InsufficientFunds (a ValueError subclass "
        "defined in ledger/events.py) and replay returns nothing. A balance of exactly zero is fine. Unknown event "
        "types raise ValueError. The input list must not be modified.\n"
        "- accrue(balance, annual_rate, days) returns simple interest in cents, balance * annual_rate * days / 365, "
        "rounded half away from zero using exact decimal arithmetic on str(annual_rate): accrue(100000, 0.05, 30) is "
        "411 and accrue(36500, 0.005, 1) is 1 (negative balances round away from zero too)."
        + TESTS_NOTE
    ),
    files={
        "ledger/__init__.py": "",
        "ledger/events.py": (
            "class InsufficientFunds(ValueError):\n    pass\n\n\n"
            "def apply_event(balance, event):\n"
            "    kind = event['type']\n"
            "    if kind == 'deposit':\n        return balance + event['amount']\n"
            "    if kind in ('withdraw', 'fee'):\n        return balance - event['amount']\n"
            "    raise ValueError('unknown event type: %r' % kind)\n"
        ),
        "ledger/replay.py": (
            "from .events import apply_event\n\n\n"
            "def replay(events, snapshot=None):\n"
            "    balance = snapshot['balance'] if snapshot else 0\n"
            "    last_seq = snapshot['seq'] if snapshot else 0\n"
            "    for event in sorted(events, key=lambda e: e['ts']):\n"
            "        if snapshot and event['seq'] < snapshot['seq']:\n            continue\n"
            "        balance = apply_event(balance, event)\n"
            "        last_seq = max(last_seq, event['seq'])\n"
            "    return {'balance': balance, 'seq': last_seq}\n"
        ),
        "ledger/interest.py": "def accrue(balance, annual_rate, days):\n    return int(balance * annual_rate * days / 360)\n",
        "tests/__init__.py": "",
        "tests/test_ledger.py": (
            "import unittest\n\nfrom ledger.replay import replay\n\n\n"
            "def ev(seq, ts, kind, amount):\n    return {'seq': seq, 'ts': ts, 'type': kind, 'amount': amount}\n\n\n"
            "class VisibleTests(unittest.TestCase):\n"
            "    def test_simple_replay(self):\n"
            "        out = replay([ev(1, 1, 'deposit', 1000), ev(2, 2, 'withdraw', 300)])\n"
            "        self.assertEqual(out, {'balance': 700, 'seq': 2})\n"
        ),
    },
    hidden_tests=r"""
import unittest

from ledger.events import InsufficientFunds
from ledger.interest import accrue
from ledger.replay import replay


def ev(seq, ts, kind, amount):
    return {"seq": seq, "ts": ts, "type": kind, "amount": amount}


class ReplayTests(unittest.TestCase):
    def test_simple(self):
        out = replay([ev(1, 1, "deposit", 1000), ev(2, 2, "withdraw", 300)])
        self.assertEqual(out, {"balance": 700, "seq": 2})

    def test_orders_by_timestamp_then_sequence(self):
        events = [ev(2, 10, "withdraw", 50), ev(1, 10, "deposit", 100)]
        self.assertEqual(replay(events), {"balance": 50, "seq": 2})
        later = [ev(3, 9, "withdraw", 40), ev(2, 5, "deposit", 100)]
        self.assertEqual(replay(later), {"balance": 60, "seq": 3})

    def test_snapshot_boundary_is_exclusive_of_included_events(self):
        events = [ev(1, 1, "deposit", 1000), ev(2, 2, "withdraw", 300), ev(3, 3, "deposit", 100)]
        out = replay(events, {"balance": 700, "seq": 2})
        self.assertEqual(out, {"balance": 800, "seq": 3})

    def test_snapshot_with_nothing_new(self):
        events = [ev(1, 1, "deposit", 1000)]
        self.assertEqual(replay(events, {"balance": 1000, "seq": 1}), {"balance": 1000, "seq": 1})

    def test_duplicate_sequence_numbers_apply_once(self):
        events = [ev(1, 1, "deposit", 100), ev(1, 2, "deposit", 100)]
        self.assertEqual(replay(events), {"balance": 100, "seq": 1})

    def test_overdraft_raises_for_withdrawals_and_fees(self):
        with self.assertRaises(InsufficientFunds):
            replay([ev(1, 1, "deposit", 100), ev(2, 2, "withdraw", 150)])
        with self.assertRaises(InsufficientFunds):
            replay([ev(1, 1, "deposit", 10), ev(2, 2, "fee", 11)])

    def test_exactly_zero_is_allowed(self):
        self.assertEqual(replay([ev(1, 1, "deposit", 100), ev(2, 2, "withdraw", 100)])["balance"], 0)

    def test_empty_inputs(self):
        self.assertEqual(replay([]), {"balance": 0, "seq": 0})
        self.assertEqual(replay([], {"balance": 5, "seq": 9}), {"balance": 5, "seq": 9})

    def test_unknown_type_and_input_not_modified(self):
        with self.assertRaises(ValueError):
            replay([ev(1, 1, "refund", 1)])
        events = [ev(2, 2, "deposit", 1), ev(1, 1, "deposit", 1)]
        replay(events)
        self.assertEqual([e["seq"] for e in events], [2, 1])


class InterestTests(unittest.TestCase):
    def test_day_count_is_365(self):
        self.assertEqual(accrue(100000, 0.05, 365), 5000)
        self.assertEqual(accrue(100000, 0.05, 30), 411)

    def test_rounds_half_away_from_zero(self):
        self.assertEqual(accrue(36500, 0.005, 1), 1)
        self.assertEqual(accrue(-36500, 0.005, 1), -1)

    def test_small_amounts(self):
        self.assertEqual(accrue(1, 0.5, 1), 0)
        self.assertEqual(accrue(0, 0.05, 30), 0)
""",
    reference={
        "ledger/events.py": r"""
class InsufficientFunds(ValueError):
    pass


def apply_event(balance, event):
    kind = event["type"]
    if kind == "deposit":
        return balance + event["amount"]
    if kind in ("withdraw", "fee"):
        result = balance - event["amount"]
        if result < 0:
            raise InsufficientFunds("balance would be negative")
        return result
    raise ValueError("unknown event type: %r" % kind)
""",
        "ledger/replay.py": r"""
from .events import apply_event


def replay(events, snapshot=None):
    balance = snapshot["balance"] if snapshot else 0
    base_seq = snapshot["seq"] if snapshot else 0
    last_seq = base_seq
    seen = set()
    for event in sorted(events, key=lambda e: (e["ts"], e["seq"])):
        if event["seq"] <= base_seq or event["seq"] in seen:
            continue
        seen.add(event["seq"])
        balance = apply_event(balance, event)
        last_seq = max(last_seq, event["seq"])
    return {"balance": balance, "seq": last_seq}
""",
        "ledger/interest.py": r"""
from decimal import ROUND_HALF_UP, Decimal


def accrue(balance, annual_rate, days):
    interest = Decimal(balance) * Decimal(str(annual_rate)) * Decimal(days) / Decimal(365)
    return int(interest.quantize(Decimal(1), rounding=ROUND_HALF_UP))
""",
    },
)

# ---------------------------------------------------------------------------------------------------------------
_TTL = Task(
    id="ttl_cache",
    split="heldout",
    track="issues",
    prompt=(
        "Issue: the TTL cache returns stale data, evicts live entries, and the decorator misbehaves "
        "(package cachekit/).\n\n"
        "Expected behavior:\n"
        "- An entry written at time t is alive while now < t + ttl and expired once now >= t + ttl. get does not "
        "extend the lifetime; put resets it.\n"
        "- get(key, default=None): an expired entry is removed and counts as a miss (return default). A live entry "
        "counts as a hit and becomes the most recently used.\n"
        "- len(cache) and 'key in cache' only consider live entries. 'in' does not change recency or statistics.\n"
        "- put: first drop every expired entry, then, if the cache is still full, evict the least recently used "
        "live entry. Updating an existing key never evicts.\n"
        "- stats() returns {'hits': n, 'misses': m}. clear() removes all entries and keeps the statistics.\n"
        "- cached(ttl, maxsize=128, clock=None) decorates a function with a TTLCache: calls that differ only in "
        "the order of keyword arguments share one entry, results that are None are cached too, "
        "wrapper.cache_clear() clears the cache, and wrapper.cache is the cache."
        + TESTS_NOTE
    ),
    files={
        "cachekit/__init__.py": "",
        "cachekit/clock.py": "import time\n\n\nclass Clock:\n    def now(self):\n        return time.monotonic()\n",
        "cachekit/ttl.py": (
            "from collections import OrderedDict\n\nfrom .clock import Clock\n\n\nclass TTLCache:\n"
            "    def __init__(self, maxsize, ttl, clock=None):\n"
            "        if maxsize < 1 or ttl <= 0:\n            raise ValueError('maxsize must be >= 1 and ttl > 0')\n"
            "        self.maxsize = maxsize\n        self.ttl = ttl\n        self.clock = clock or Clock()\n"
            "        self._data = OrderedDict()\n        self._hits = 0\n        self._misses = 0\n\n"
            "    def put(self, key, value):\n"
            "        if key in self._data:\n            del self._data[key]\n"
            "        elif len(self._data) >= self.maxsize:\n            self._data.popitem(last=False)\n"
            "        self._data[key] = (value, self.clock.now() + self.ttl)\n\n"
            "    def get(self, key, default=None):\n"
            "        item = self._data.get(key)\n"
            "        if item is None:\n            self._misses += 1\n            return default\n"
            "        value, expires = item\n        self._hits += 1\n"
            "        if expires <= self.clock.now():\n            return default\n"
            "        self._data.move_to_end(key)\n        return value\n\n"
            "    def __len__(self):\n        return len(self._data)\n\n"
            "    def __contains__(self, key):\n        return key in self._data\n\n"
            "    def stats(self):\n        return {'hits': self._hits, 'misses': self._misses}\n"
        ),
        "cachekit/decorator.py": (
            "import functools\n\nfrom .ttl import TTLCache\n\n\n"
            "def cached(ttl, maxsize=128, clock=None):\n"
            "    def decorate(func):\n"
            "        cache = TTLCache(maxsize, ttl, clock)\n\n"
            "        @functools.wraps(func)\n"
            "        def wrapper(*args, **kwargs):\n"
            "            key = (args, tuple(kwargs.items()))\n"
            "            result = cache.get(key)\n"
            "            if result is None:\n"
            "                result = func(*args, **kwargs)\n                cache.put(key, result)\n"
            "            return result\n\n"
            "        wrapper.cache = cache\n        return wrapper\n\n"
            "    return decorate\n"
        ),
        "tests/__init__.py": "",
        "tests/test_cache.py": (
            "import unittest\n\nfrom cachekit.ttl import TTLCache\n\n\nclass FakeClock:\n"
            "    def __init__(self):\n        self.t = 0.0\n\n    def now(self):\n        return self.t\n\n\n"
            "class VisibleTests(unittest.TestCase):\n"
            "    def test_put_get(self):\n"
            "        cache = TTLCache(2, 10, FakeClock())\n        cache.put('a', 1)\n"
            "        self.assertEqual(cache.get('a'), 1)\n"
        ),
    },
    hidden_tests=r"""
import unittest

from cachekit.decorator import cached
from cachekit.ttl import TTLCache


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def now(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


class TTLTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()

    def test_basic_and_expiry_boundary(self):
        c = TTLCache(2, 10, self.clock)
        c.put("a", 1)
        self.clock.advance(9.9)
        self.assertEqual(c.get("a"), 1)
        self.clock.advance(0.1)
        self.assertIsNone(c.get("a"))

    def test_get_does_not_extend_life_but_put_resets_it(self):
        c = TTLCache(2, 10, self.clock)
        c.put("a", 1)
        self.clock.advance(6)
        c.get("a")
        self.clock.advance(5)
        self.assertIsNone(c.get("a"))
        c.put("b", 2)
        self.clock.advance(6)
        c.put("b", 3)
        self.clock.advance(6)
        self.assertEqual(c.get("b"), 3)

    def test_expired_get_removes_entry_and_counts_a_miss(self):
        c = TTLCache(2, 10, self.clock)
        c.put("a", 1)
        self.clock.advance(11)
        self.assertEqual(c.get("a", "gone"), "gone")
        self.assertEqual(len(c), 0)
        self.assertEqual(c.stats(), {"hits": 0, "misses": 1})

    def test_len_and_contains_only_see_live_entries(self):
        c = TTLCache(3, 10, self.clock)
        c.put("a", 1)
        self.clock.advance(11)
        c.put("b", 2)
        self.assertEqual(len(c), 1)
        self.assertNotIn("a", c)
        self.assertIn("b", c)

    def test_put_purges_expired_before_evicting_live_entries(self):
        c = TTLCache(2, 10, self.clock)
        c.put("a", 1)
        self.clock.advance(5)
        c.put("b", 2)
        self.clock.advance(1)
        c.get("a")
        self.clock.advance(5)
        c.put("c", 3)
        self.assertNotIn("a", c)
        self.assertIn("b", c)
        self.assertIn("c", c)

    def test_lru_eviction_when_all_entries_are_live(self):
        c = TTLCache(2, 10, self.clock)
        c.put("a", 1)
        c.put("b", 2)
        c.get("a")
        c.put("c", 3)
        self.assertNotIn("b", c)
        self.assertIn("a", c)

    def test_updating_an_existing_key_never_evicts(self):
        c = TTLCache(2, 10, self.clock)
        c.put("a", 1)
        c.put("b", 2)
        c.put("a", 9)
        self.assertEqual((len(c), c.get("a"), c.get("b")), (2, 9, 2))

    def test_contains_does_not_change_recency_or_stats(self):
        c = TTLCache(2, 10, self.clock)
        c.put("a", 1)
        c.put("b", 2)
        self.assertIn("a", c)
        c.put("c", 3)
        self.assertNotIn("a", c)
        self.assertEqual(c.stats(), {"hits": 0, "misses": 0})

    def test_stats_and_clear(self):
        c = TTLCache(2, 10, self.clock)
        c.put("a", 1)
        c.get("a")
        c.get("zzz")
        c.clear()
        self.assertEqual(len(c), 0)
        self.assertEqual(c.stats(), {"hits": 1, "misses": 1})

    def test_invalid_arguments(self):
        for args in ((0, 10), (1, 0), (1, -5)):
            with self.assertRaises(ValueError):
                TTLCache(*args)


class DecoratorTests(unittest.TestCase):
    def test_keyword_order_does_not_matter(self):
        calls = []

        @cached(ttl=10, clock=FakeClock())
        def f(a, b):
            calls.append((a, b))
            return a + b

        self.assertEqual(f(a=1, b=2), 3)
        self.assertEqual(f(b=2, a=1), 3)
        self.assertEqual(len(calls), 1)

    def test_none_results_are_cached(self):
        calls = []

        @cached(ttl=10, clock=FakeClock())
        def f(x):
            calls.append(x)

        f(1)
        f(1)
        self.assertEqual(len(calls), 1)

    def test_expiry_and_cache_clear(self):
        clock = FakeClock()
        calls = []

        @cached(ttl=10, clock=clock)
        def f(x):
            calls.append(x)
            return x * 2

        f(2)
        clock.advance(11)
        f(2)
        self.assertEqual(len(calls), 2)
        f.cache_clear()
        f(2)
        self.assertEqual(len(calls), 3)
        self.assertEqual(f.cache.stats()["misses"], 3)
""",
    reference={
        "cachekit/ttl.py": r"""
from collections import OrderedDict

from .clock import Clock


class TTLCache:
    def __init__(self, maxsize, ttl, clock=None):
        if maxsize < 1 or ttl <= 0:
            raise ValueError("maxsize must be >= 1 and ttl > 0")
        self.maxsize = maxsize
        self.ttl = ttl
        self.clock = clock or Clock()
        self._data = OrderedDict()
        self._hits = 0
        self._misses = 0

    def _purge(self):
        now = self.clock.now()
        for key in [k for k, (_, expires) in self._data.items() if expires <= now]:
            del self._data[key]

    def put(self, key, value):
        if key in self._data:
            del self._data[key]
        else:
            self._purge()
            while len(self._data) >= self.maxsize:
                self._data.popitem(last=False)
        self._data[key] = (value, self.clock.now() + self.ttl)

    def get(self, key, default=None):
        item = self._data.get(key)
        if item is not None and item[1] <= self.clock.now():
            del self._data[key]
            item = None
        if item is None:
            self._misses += 1
            return default
        self._hits += 1
        self._data.move_to_end(key)
        return item[0]

    def clear(self):
        self._data.clear()

    def __len__(self):
        self._purge()
        return len(self._data)

    def __contains__(self, key):
        item = self._data.get(key)
        return item is not None and item[1] > self.clock.now()

    def stats(self):
        return {"hits": self._hits, "misses": self._misses}
""",
        "cachekit/decorator.py": r"""
import functools

from .ttl import TTLCache

_MISSING = object()


def cached(ttl, maxsize=128, clock=None):
    def decorate(func):
        cache = TTLCache(maxsize, ttl, clock)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            key = (args, tuple(sorted(kwargs.items())))
            result = cache.get(key, _MISSING)
            if result is _MISSING:
                result = func(*args, **kwargs)
                cache.put(key, result)
            return result

        wrapper.cache = cache
        wrapper.cache_clear = cache.clear
        return wrapper

    return decorate
""",
    },
)

# ---------------------------------------------------------------------------------------------------------------
_LIMITER = Task(
    id="rate_limiter",
    split="fresh",
    track="issues",
    prompt=(
        "Issue: the rate limiter lets too few requests through, shares state between instances, and reports "
        "wrong retry times (package limiter/).\n\n"
        "Expected behavior:\n"
        "- TokenBucket(rate, burst, clock) starts full with burst tokens and refills continuously at rate tokens "
        "per second up to burst. Fractional progress must accumulate: with rate=1, burst=1, four calls spaced 0.25 "
        "seconds apart after emptying the bucket let the fourth one through.\n"
        "- allow(cost=1) consumes cost tokens and returns True if enough are available, otherwise returns False "
        "and consumes nothing.\n"
        "- retry_after(cost=1) is the number of seconds until cost tokens will be available: "
        "max(0, (cost - tokens) / rate), based on the current token count.\n"
        "- rate <= 0 or burst < 1 raises ValueError; so does a cost <= 0 or greater than burst, in both allow and "
        "retry_after.\n"
        "- Limiter(rate, burst, clock) keeps an independent bucket per key, created lazily and full. Two Limiter "
        "instances never share state." + TESTS_NOTE
    ),
    files={
        "limiter/__init__.py": "",
        "limiter/clock.py": "import time\n\n\nclass Clock:\n    def now(self):\n        return time.monotonic()\n",
        "limiter/bucket.py": (
            "from .clock import Clock\n\n\nclass TokenBucket:\n"
            "    def __init__(self, rate, burst, clock=None):\n"
            "        self.rate = rate\n        self.burst = burst\n        self.clock = clock or Clock()\n"
            "        self.tokens = burst\n        self.last = self.clock.now()\n\n"
            "    def _refill(self):\n"
            "        now = self.clock.now()\n"
            "        self.tokens = min(self.burst, self.tokens + int((now - self.last) * self.rate))\n"
            "        self.last = now\n\n"
            "    def allow(self, cost=1):\n"
            "        self._refill()\n"
            "        if self.tokens >= cost:\n            self.tokens -= cost\n            return True\n"
            "        return False\n\n"
            "    def retry_after(self, cost=1):\n        return cost / self.rate\n"
        ),
        "limiter/registry.py": (
            "from .bucket import TokenBucket\nfrom .clock import Clock\n\n\nclass Limiter:\n"
            "    def __init__(self, rate, burst, clock=None, buckets={}):\n"
            "        self.rate = rate\n        self.burst = burst\n        self.clock = clock or Clock()\n"
            "        self._buckets = buckets\n\n"
            "    def _bucket(self, key):\n"
            "        if key not in self._buckets:\n"
            "            self._buckets[key] = TokenBucket(self.rate, self.burst, self.clock)\n"
            "        return self._buckets[key]\n\n"
            "    def allow(self, key, cost=1):\n        return self._bucket(key).allow(cost)\n\n"
            "    def retry_after(self, key, cost=1):\n        return self._bucket(key).retry_after(cost)\n"
        ),
        "tests/__init__.py": "",
        "tests/test_limiter.py": (
            "import unittest\n\nfrom limiter.bucket import TokenBucket\n\n\nclass FakeClock:\n"
            "    def __init__(self):\n        self.t = 0.0\n\n    def now(self):\n        return self.t\n\n\n"
            "class VisibleTests(unittest.TestCase):\n"
            "    def test_burst(self):\n"
            "        bucket = TokenBucket(1, 2, FakeClock())\n"
            "        self.assertEqual([bucket.allow(), bucket.allow(), bucket.allow()], [True, True, False])\n"
        ),
    },
    hidden_tests=r"""
import unittest

from limiter.bucket import TokenBucket
from limiter.registry import Limiter


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def now(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


class BucketTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()

    def test_starts_full(self):
        b = TokenBucket(1, 3, self.clock)
        self.assertEqual([b.allow() for _ in range(4)], [True, True, True, False])

    def test_denial_consumes_nothing(self):
        b = TokenBucket(1, 2, self.clock)
        self.assertTrue(b.allow(2))
        self.assertFalse(b.allow(1))
        self.clock.advance(1)
        self.assertTrue(b.allow(1))

    def test_fractional_progress_accumulates(self):
        b = TokenBucket(1, 1, self.clock)
        self.assertTrue(b.allow())
        results = []
        for _ in range(4):
            self.clock.advance(0.25)
            results.append(b.allow())
        self.assertEqual(results, [False, False, False, True])

    def test_refill_is_capped_at_burst(self):
        b = TokenBucket(5, 2, self.clock)
        b.allow(2)
        self.clock.advance(100)
        self.assertEqual([b.allow(), b.allow(), b.allow()], [True, True, False])

    def test_retry_after(self):
        b = TokenBucket(2, 2, self.clock)
        b.allow(2)
        self.assertAlmostEqual(b.retry_after(1), 0.5)
        self.clock.advance(0.25)
        self.assertAlmostEqual(b.retry_after(1), 0.25)
        self.assertAlmostEqual(b.retry_after(2), 0.75)

    def test_retry_after_is_zero_when_tokens_are_available(self):
        b = TokenBucket(1, 3, self.clock)
        self.assertEqual(b.retry_after(2), 0)

    def test_invalid_costs_and_configuration(self):
        b = TokenBucket(1, 2, self.clock)
        for cost in (0, -1, 3):
            with self.assertRaises(ValueError):
                b.allow(cost)
            with self.assertRaises(ValueError):
                b.retry_after(cost)
        for args in ((0, 1), (-1, 1), (1, 0)):
            with self.assertRaises(ValueError):
                TokenBucket(*args)


class LimiterTests(unittest.TestCase):
    def test_keys_are_independent(self):
        limiter = Limiter(1, 1, FakeClock())
        self.assertTrue(limiter.allow("a"))
        self.assertTrue(limiter.allow("b"))
        self.assertFalse(limiter.allow("a"))

    def test_instances_do_not_share_state(self):
        clock = FakeClock()
        first, second = Limiter(1, 1, clock), Limiter(1, 1, clock)
        self.assertTrue(first.allow("k"))
        self.assertTrue(second.allow("k"))

    def test_retry_after_per_key(self):
        clock = FakeClock()
        limiter = Limiter(1, 2, clock)
        limiter.allow("a", 2)
        self.assertAlmostEqual(limiter.retry_after("a", 1), 1.0)
        self.assertEqual(limiter.retry_after("b", 1), 0)
""",
    reference={
        "limiter/bucket.py": r"""
from .clock import Clock


class TokenBucket:
    def __init__(self, rate, burst, clock=None):
        if rate <= 0 or burst < 1:
            raise ValueError("rate must be positive and burst at least 1")
        self.rate = rate
        self.burst = burst
        self.clock = clock or Clock()
        self.tokens = float(burst)
        self.last = self.clock.now()

    def _refill(self):
        now = self.clock.now()
        self.tokens = min(float(self.burst), self.tokens + (now - self.last) * self.rate)
        self.last = now

    def _check(self, cost):
        if cost <= 0 or cost > self.burst:
            raise ValueError("cost must be in (0, burst]")

    def allow(self, cost=1):
        self._check(cost)
        self._refill()
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False

    def retry_after(self, cost=1):
        self._check(cost)
        self._refill()
        return max(0.0, (cost - self.tokens) / self.rate)
""",
        "limiter/registry.py": r"""
from .bucket import TokenBucket
from .clock import Clock


class Limiter:
    def __init__(self, rate, burst, clock=None):
        self.rate = rate
        self.burst = burst
        self.clock = clock or Clock()
        self._buckets = {}

    def _bucket(self, key):
        if key not in self._buckets:
            self._buckets[key] = TokenBucket(self.rate, self.burst, self.clock)
        return self._buckets[key]

    def allow(self, key, cost=1):
        return self._bucket(key).allow(cost)

    def retry_after(self, key, cost=1):
        return self._bucket(key).retry_after(cost)
""",
    },
)

# ---------------------------------------------------------------------------------------------------------------
_MIGRATE = Task(
    id="migrations",
    split="fresh",
    track="issues",
    prompt=(
        "Issue: the migration runner applies migrations in the wrong order and leaves the database half migrated "
        "after a failure (package migrate/).\n\n"
        "Expected behavior:\n"
        "- A migration is (version, sql). Versions are integers written as strings; anything else raises ValueError "
        "when the Migrator is created, and so do duplicate versions. Migrations may be passed in any order and "
        "are applied in ascending numeric order ('2' before '10').\n"
        "- migrate() applies the migrations that are not yet recorded in the schema_migrations table, returns the "
        "list of versions it applied in this call (strings), and is a no-op when run again.\n"
        "- Each migration is atomic. Its SQL may contain several statements, including semicolons inside string "
        "literals. If any statement fails, every change of that migration is rolled back, its version is not "
        "recorded, earlier migrations stay applied, and migrate() raises MigrationError (migrate/errors.py) with "
        "a version attribute holding the failing version, chained from the original exception.\n"
        "- current_version() returns the highest applied version as an int, or None if nothing was applied.\n"
        "- It must work with the default sqlite3 connection settings and with isolation_level=None."
        + TESTS_NOTE
    ),
    files={
        "migrate/__init__.py": "",
        "migrate/errors.py": (
            "class MigrationError(Exception):\n"
            "    def __init__(self, version, cause):\n"
            "        super().__init__('migration %s failed: %s' % (version, cause))\n"
            "        self.version = version\n"
        ),
        "migrate/runner.py": (
            "class Migrator:\n"
            "    def __init__(self, conn, migrations):\n"
            "        self.conn = conn\n        self.migrations = list(migrations)\n"
            "        conn.execute('CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY)')\n"
            "        conn.commit()\n\n"
            "    def applied(self):\n"
            "        return {row[0] for row in self.conn.execute('SELECT version FROM schema_migrations')}\n\n"
            "    def current_version(self):\n"
            "        rows = [row[0] for row in self.conn.execute('SELECT version FROM schema_migrations')]\n"
            "        return max(rows) if rows else None\n\n"
            "    def migrate(self):\n"
            "        done = []\n"
            "        for version, sql in sorted(self.migrations):\n"
            "            if version in self.applied():\n                continue\n"
            "            self.conn.execute('INSERT INTO schema_migrations (version) VALUES (?)', (version,))\n"
            "            self.conn.executescript(sql)\n"
            "            self.conn.commit()\n"
            "            done.append(version)\n"
            "        return done\n"
        ),
        "tests/__init__.py": "",
        "tests/test_runner.py": (
            "import sqlite3\nimport unittest\n\nfrom migrate.runner import Migrator\n\n\n"
            "class VisibleTests(unittest.TestCase):\n"
            "    def test_applies_in_order(self):\n"
            "        conn = sqlite3.connect(':memory:')\n"
            "        done = Migrator(conn, [('1', 'CREATE TABLE a (id INTEGER)'), ('2', 'CREATE TABLE b (id INTEGER)')]).migrate()\n"
            "        self.assertEqual(done, ['1', '2'])\n"
        ),
    },
    hidden_tests=r"""
import sqlite3
import unittest

from migrate.errors import MigrationError
from migrate.runner import Migrator


def tables(conn):
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def connections():
    default = sqlite3.connect(":memory:")
    autocommit = sqlite3.connect(":memory:")
    autocommit.isolation_level = None
    return [default, autocommit]


class MigratorTests(unittest.TestCase):
    def test_numeric_order_regardless_of_input_order(self):
        for conn in connections():
            migrations = [
                ("10", "INSERT INTO log VALUES ('10')"),
                ("2", "INSERT INTO log VALUES ('2')"),
                ("1", "CREATE TABLE log (v TEXT); INSERT INTO log VALUES ('1')"),
            ]
            self.assertEqual(Migrator(conn, migrations).migrate(), ["1", "2", "10"])
            self.assertEqual([r[0] for r in conn.execute("SELECT v FROM log ORDER BY rowid")], ["1", "2", "10"])

    def test_idempotent(self):
        for conn in connections():
            m = Migrator(conn, [("1", "CREATE TABLE a (id INTEGER)")])
            self.assertEqual(m.migrate(), ["1"])
            self.assertEqual(m.migrate(), [])
            self.assertEqual(Migrator(conn, [("1", "CREATE TABLE a (id INTEGER)")]).migrate(), [])

    def test_current_version_is_numeric(self):
        for conn in connections():
            m = Migrator(conn, [("9", "CREATE TABLE a (id INTEGER)"), ("10", "CREATE TABLE b (id INTEGER)")])
            self.assertIsNone(m.current_version())
            m.migrate()
            self.assertEqual(m.current_version(), 10)

    def test_failure_is_atomic_and_chained(self):
        for conn in connections():
            bad = [("1", "CREATE TABLE a (id INTEGER)"), ("2", "CREATE TABLE b (id INTEGER); INSERT INTO nope VALUES (1)")]
            m = Migrator(conn, bad)
            with self.assertRaises(MigrationError) as ctx:
                m.migrate()
            self.assertEqual(ctx.exception.version, "2")
            self.assertIsInstance(ctx.exception.__cause__, sqlite3.OperationalError)
            self.assertIn("a", tables(conn))
            self.assertNotIn("b", tables(conn))
            self.assertEqual(m.applied(), {"1"})
            self.assertEqual(m.current_version(), 1)

    def test_a_corrected_migration_can_be_applied_after_a_failure(self):
        conn = sqlite3.connect(":memory:")
        with self.assertRaises(MigrationError):
            Migrator(conn, [("1", "CREATE TABLE a (id INTEGER); BAD SQL")]).migrate()
        fixed = Migrator(conn, [("1", "CREATE TABLE a (id INTEGER)")])
        self.assertEqual(fixed.migrate(), ["1"])

    def test_multiple_statements_and_semicolons_in_strings(self):
        for conn in connections():
            script = "CREATE TABLE s (v TEXT); INSERT INTO s VALUES ('a;b'); INSERT INTO s VALUES ('c')"
            Migrator(conn, [("1", script)]).migrate()
            self.assertEqual([r[0] for r in conn.execute("SELECT v FROM s ORDER BY rowid")], ["a;b", "c"])

    def test_trailing_semicolon_and_whitespace(self):
        conn = sqlite3.connect(":memory:")
        Migrator(conn, [("1", "  CREATE TABLE a (id INTEGER);\n\n  ")]).migrate()
        self.assertIn("a", tables(conn))

    def test_invalid_versions_are_rejected(self):
        conn = sqlite3.connect(":memory:")
        for bad in ([("abc", "SELECT 1")], [("1.5", "SELECT 1")], [("", "SELECT 1")], [("1", "SELECT 1"), ("1", "SELECT 2")]):
            with self.assertRaises(ValueError):
                Migrator(conn, bad)
""",
    reference={
        "migrate/runner.py": r"""
import sqlite3

from .errors import MigrationError


def _statements(script):
    buffer = ""
    for chunk in script.split(";"):
        buffer += chunk + ";"
        if sqlite3.complete_statement(buffer):
            if buffer.strip() != ";":
                yield buffer
            buffer = ""
    if buffer.strip().strip(";").strip():
        yield buffer


class Migrator:
    def __init__(self, conn, migrations):
        parsed = []
        for version, sql in migrations:
            if not (isinstance(version, str) and version.isdigit()):
                raise ValueError("versions must be integers written as strings: %r" % (version,))
            parsed.append((int(version), version, sql))
        if len({number for number, _, _ in parsed}) != len(parsed):
            raise ValueError("duplicate migration versions")
        self.conn = conn
        self.migrations = sorted(parsed, key=lambda item: item[0])
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY)")
        conn.commit()

    def applied(self):
        return {row[0] for row in self.conn.execute("SELECT version FROM schema_migrations")}

    def current_version(self):
        rows = [int(row[0]) for row in self.conn.execute("SELECT version FROM schema_migrations")]
        return max(rows) if rows else None

    def migrate(self):
        done = []
        applied = self.applied()
        for _, version, sql in self.migrations:
            if version in applied:
                continue
            try:
                self.conn.execute("BEGIN")
                for statement in _statements(sql):
                    self.conn.execute(statement)
                self.conn.execute("INSERT INTO schema_migrations (version) VALUES (?)", (version,))
                self.conn.execute("COMMIT")
            except Exception as exc:
                if self.conn.in_transaction:
                    self.conn.execute("ROLLBACK")
                raise MigrationError(version, exc) from exc
            done.append(version)
        return done
""",
    },
)

ISSUE_TASKS: list[Task] = [_INVOICE, _LEDGER, _TTL, _LIMITER, _MIGRATE]
