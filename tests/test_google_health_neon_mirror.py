"""Regression tests for source-labelled Google Health data."""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location(
    "google_health_ingest", ROOT / "scripts" / "18_ingest_google_health.py"
)
ingest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ingest)

from sync_google_health_to_neon import read_daily_rows


def nutrition_point(day, kcal, protein, source, package=""):
    return {
        "dataSource": {
            "platform": source, "application": {"packageName": package}
        },
        "nutritionLog": {
            "interval": {
                "civilStartTime": {
                    "date": {"year": day.year, "month": day.month, "day": day.day},
                    "time": {"hours": 12},
                }
            },
            "energy": {"kcal": kcal},
            "nutrients": [{"nutrient": "PROTEIN", "quantity": {"grams": protein}}],
            "totalCarbohydrate": {"grams": 5},
            "totalFat": {"grams": 2},
        },
    }


class GoogleHealthDailyTests(unittest.TestCase):
    def test_cronometer_only_does_not_sum_fitbit_or_other_sources(self):
        day = date(2026, 10, 27)
        points = [
            nutrition_point(day, 300, 30, "HEALTH_CONNECT", "com.cronometer.android.gold"),
            nutrition_point(day, 400, 40, "HEALTH_CONNECT", "com.cronometer.android.gold"),
            nutrition_point(day, 700, 70, "FITBIT_WEB_API"),
            nutrition_point(day, 100, 10, "OTHER"),
        ]
        with patch.object(ingest, "_list_all", return_value=points):
            frame = ingest.load_nutrition("test-token", day, day)
        self.assertEqual(len(frame), 1)
        self.assertEqual(frame.iloc[0]["calories"], 700)
        self.assertEqual(frame.iloc[0]["protein_g"], 70)

    def test_fitbit_summary_only_does_not_become_a_cronometer_day(self):
        day = date(2026, 10, 26)
        with patch.object(ingest, "_list_all", return_value=[
            nutrition_point(day, 800, 20, "FITBIT_WEB_API")
        ]):
            frame = ingest.load_nutrition("test-token", day, day)
        self.assertTrue(frame.empty)

    def test_energy_rollups_are_chunked_at_fourteen_days(self):
        calls = []
        def fake_request(_token, _method, _path, json_body=None):
            calls.append(json_body)
            d = json_body["range"]["start"]["date"]
            return {"rollupDataPoints": [{
                "civilStartTime": {"date": d},
                "totalCalories": {"kcalSum": 2719},
            }]}
        with patch.object(ingest, "_request", side_effect=fake_request):
            frame = ingest.load_total_calories_burned(
                "test", date(2026, 10, 1), date(2026, 10, 16)
            )
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(frame), 2)
        self.assertEqual(frame.iloc[0]["calories_burned"], 2719)

    def test_mirror_filters_unlabelled_and_null_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "mock.duckdb"
            with duckdb.connect(str(db)) as con:
                con.execute("CREATE SCHEMA raw")
                con.execute("""
                    CREATE TABLE raw.nutrition_daily(
                        date DATE, calories DOUBLE, protein_g DOUBLE,
                        carbs_g DOUBLE, fat_g DOUBLE, source VARCHAR
                    )
                """)
                con.execute("""
                    CREATE TABLE raw.fitbit_daily(
                        date DATE, steps DOUBLE, calories_burned DOUBLE,
                        resting_hr DOUBLE, hrv DOUBLE, sleep_hours DOUBLE,
                        deep_sleep_minutes DOUBLE, rem_sleep_minutes DOUBLE,
                        wake_minutes DOUBLE, source VARCHAR
                    )
                """)
                con.execute("""
                    INSERT INTO raw.nutrition_daily VALUES
                    ('2026-10-27', 1250, 110, 90, 40, 'google_health_cronometer'),
                    ('2026-10-27', 1250, 110, 90, 40, 'fitbit_summary'),
                    ('2026-10-28', 400, 10, 60, 10, 'fitbit_summary')
                """)
                con.execute("""
                    INSERT INTO raw.fitbit_daily VALUES
                    ('2026-10-27', 11000, 2900, 74, 14.3, 7.5, 65, 95, 25, 'google_health'),
                    ('2026-10-28', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'google_health')
                """)
            n, a = read_daily_rows(date(2026, 10, 27), date(2026, 10, 28), db)
            self.assertEqual(len(n), 1)
            self.assertEqual(n[0][1], 1250)
            self.assertEqual(len(a), 1)
            self.assertEqual(a[0][2], 2900)


if __name__ == "__main__":
    unittest.main()
