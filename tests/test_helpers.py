"""Unit tests for the pure helpers in sheet.py and update_prices.py.

Run from the repo root:  .venv/bin/python -m unittest discover -s tests
No external test framework required (stdlib unittest).
"""
import unittest

from sheet import index_to_col, resolve_columns
from update_prices import _dividend_total, _round, _to_float, _yoy


class TestIndexToCol(unittest.TestCase):
    def test_single_letter(self):
        self.assertEqual(index_to_col(1), "A")
        self.assertEqual(index_to_col(12), "L")
        self.assertEqual(index_to_col(26), "Z")

    def test_double_letter(self):
        self.assertEqual(index_to_col(27), "AA")
        self.assertEqual(index_to_col(45), "AS")


class TestResolveColumns(unittest.TestCase):
    HEADER = ["銘柄名", "現在株価", "配当利回り", "配当金", "Ticker"]
    LABELS = {
        "name": "銘柄名",
        "current_price": "現在株価",
        "dividend_yield": "配当利回り",
        "dividend_amount": "配当金",
        "ticker": "Ticker",
    }

    def test_resolves_by_name_to_1based_index(self):
        out = resolve_columns(self.HEADER, self.LABELS)
        self.assertEqual(out["name"], 1)
        self.assertEqual(out["current_price"], 2)
        self.assertEqual(out["ticker"], 5)

    def test_column_moved_still_resolves(self):
        # Ticker moved to the front, current_price shifted right: name-based
        # resolution must track the label, not the position.
        header = ["Ticker", "銘柄名", "現在株価"]
        out = resolve_columns(header, {"ticker": "Ticker", "current_price": "現在株価"})
        self.assertEqual(out["ticker"], 1)
        self.assertEqual(out["current_price"], 3)

    def test_missing_optional_role_is_omitted(self):
        out = resolve_columns(["Ticker"], {"ticker": "Ticker", "current_price": "現在株価"})
        self.assertIn("ticker", out)
        self.assertNotIn("current_price", out)

    def test_missing_required_role_exits(self):
        with self.assertRaises(SystemExit):
            resolve_columns(["銘柄名"], {"ticker": "Ticker"}, required={"ticker"})

    def test_blank_and_whitespace_headers_ignored(self):
        header = ["", " 銘柄名 ", "Ticker"]
        out = resolve_columns(header, {"name": "銘柄名", "ticker": "Ticker"})
        self.assertEqual(out["name"], 2)
        self.assertEqual(out["ticker"], 3)

    def test_duplicate_label_first_wins(self):
        header = ["現在株価", "現在株価"]
        out = resolve_columns(header, {"current_price": "現在株価"})
        self.assertEqual(out["current_price"], 1)


class TestToFloat(unittest.TestCase):
    def test_plain_and_grouped(self):
        self.assertEqual(_to_float("1000"), 1000.0)
        self.assertEqual(_to_float("1,000"), 1000.0)
        self.assertEqual(_to_float(42), 42.0)

    def test_blank_and_garbage(self):
        self.assertIsNone(_to_float(""))
        self.assertIsNone(_to_float(None))
        self.assertIsNone(_to_float("abc"))


class TestRound(unittest.TestCase):
    def test_rounds(self):
        self.assertEqual(_round(9.789), 9.79)
        self.assertEqual(_round("1,234.567"), 1234.57)

    def test_none_and_garbage(self):
        self.assertEqual(_round(None), "N/A")
        self.assertEqual(_round("x"), "N/A")


class TestDividendTotal(unittest.TestCase):
    def test_rate_times_shares(self):
        self.assertEqual(_dividend_total(1.08, 100), 108.0)
        self.assertEqual(_dividend_total("50", "1,000"), 50000.0)

    def test_missing_shares_is_blank(self):
        # share count is a manual field and may be empty -> leave 配当金 blank
        self.assertEqual(_dividend_total(1.08, ""), "")
        self.assertEqual(_dividend_total(1.08, None), "")
        self.assertEqual(_dividend_total(1.08, 0), "")

    def test_missing_rate_is_na(self):
        self.assertEqual(_dividend_total(None, 100), "N/A")
        self.assertEqual(_dividend_total("", 100), "N/A")


class TestYoY(unittest.TestCase):
    def test_growth_and_decline(self):
        self.assertEqual(_yoy(110, 100), 10.0)
        self.assertEqual(_yoy(90, 100), -10.0)

    def test_uses_abs_of_old_base(self):
        # recovery from a negative prior year: (5 - (-10)) / 10 * 100 = 150.0
        self.assertEqual(_yoy(5, -10), 150.0)

    def test_missing_or_zero_base_is_na(self):
        self.assertEqual(_yoy(None, 100), "N/A")
        self.assertEqual(_yoy(100, None), "N/A")
        self.assertEqual(_yoy(100, 0), "N/A")


if __name__ == "__main__":
    unittest.main()
