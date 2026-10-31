"""Fictional-only regression tests for Cronometer serving-time import."""
import importlib.util
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "foodtimes", Path(__file__).resolve().parents[1] / "scripts" / "24_sync_cronometer_food_times.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class FoodTimesTests(unittest.TestCase):
    def test_normalizes_serving_rows_without_collapsing_duplicates(self):
        rows = [
            {"Day": "2026-10-27", "Time": "12:05", "Food Name": "Fictional meal",
             "Amount": "100 g", "Group": "Lunch", "Category": "Food"},
            {"Day": "2026-10-27", "Time": "12:05", "Food Name": "Fictional meal",
             "Amount": "100 g", "Group": "Lunch", "Category": "Food"},
        ]
        result = mod.normalize(rows, date(2026,10,22), date(2026,10,31))
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0][0], 0)
        self.assertEqual(result[1][0], 1)
        self.assertEqual(result[0][3], datetime(2026, 10, 27, 11, 5, tzinfo=timezone.utc))

    def test_parses_12hour_time(self):
        self.assertEqual(mod.parse_clock("1:15 PM").hour, 13)

    def test_missing_time_is_not_inferred(self):
        rows = [{"Day": "2026-10-27", "Time": "", "Food Name": "Fictional"}]
        result = mod.normalize(rows, date(2026,10,27), date(2026,10,27))
        self.assertIsNone(result[0][2])
        self.assertIsNone(result[0][3])

    def test_dst_ambiguous_kept_without_invented_utc_instant(self):
        rows = [{"Day":"2026-10-25","Time":"02:30","Food Name":"Fictional"}]
        result = mod.normalize(rows, date(2026,10,25), date(2026,10,25))
        self.assertIsNotNone(result[0][2])
        self.assertIsNone(result[0][3])

    def test_unknown_format_raises(self):
        with self.assertRaises(ValueError):
            mod.parse_clock("not a clock")

    def test_outside_window_raises(self):
        with self.assertRaises(ValueError):
            mod.normalize([{"Day":"2026-11-01","Time":"12:00"}],
                          date(2026,10,22),date(2026,10,31))


if __name__ == "__main__":
    unittest.main()
