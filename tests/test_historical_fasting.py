"""Regression checks for non-destructive historical fasting and refeed analysis."""
from __future__ import annotations

import importlib.util
import os
import re
import runpy
import tempfile
import unittest
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "scripts" / "67_historical_fast_refeed_cycles.py"
spec = importlib.util.spec_from_file_location("fast_refeed", MODULE)
fast_refeed = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(fast_refeed)


class HistoricalFastingTests(unittest.TestCase):
    def test_refeed_intervals_and_overlapping_fast_guard(self) -> None:
        days = pd.date_range("2020-01-01", "2020-02-15")
        rows = []
        for offset, date in enumerate(days):
            d = date.date()
            is_early = d.day <= 3 and d.month == 1
            is_later = d.month == 1 and 7 <= d.day <= 14
            calories = 1800 if d == pd.Timestamp("2020-01-04").date() else (
                1600 if d == pd.Timestamp("2020-01-06").date() else (
                    1750 if d.month == 1 and d.day >= 15 else None
                )
            )
            rows.append({
                "date": date,
                "fasting_state": "EF" if is_early else (
                    "extended_fast" if is_later else "normal"
                ),
                "weight_kg": 110.0 - offset * 0.2,
                "calories": calories,
                "protein_g": 120.0 if calories is not None else None,
            })
        result = fast_refeed.analyze(pd.DataFrame(rows))
        self.assertEqual(len(result), 2)
        first, second = result.iloc[0], result.iloc[1]
        self.assertEqual(first["fast_category"], "3-day-or-shorter")
        self.assertEqual(first["non_fast_interval_days"], 3)
        self.assertEqual(first["logged_intake_days"], 2)
        self.assertEqual(first["avg_logged_calories"], 1700.0)
        self.assertTrue(pd.isna(first["weight_after_7d_kg"]))
        self.assertTrue(pd.isna(first["weight_after_28d_kg"]))
        self.assertEqual(second["fast_category"], "7+-day")
        self.assertFalse(pd.isna(second["weight_after_7d_kg"]))
        self.assertFalse(pd.isna(second["weight_after_28d_kg"]))

    def test_no_fasting_labels_is_missing_coverage_not_an_implied_fast(self) -> None:
        frame = pd.DataFrame({
            "date": ["2020-03-01", "2020-03-02"],
            "fasting_state": ["normal", None],
            "weight_kg": [110.0, 109.0],
            "calories": [1800.0, None],
            "protein_g": [110.0, None],
        })
        self.assertTrue(fast_refeed.analyze(frame).empty)

    def test_sheet_refresh_keeps_historical_source_rows(self) -> None:
        src = (ROOT / "scripts" / "10_ingest_interventions.py").read_text()
        match = re.search(
            r'con\.execute\("""\s*(DELETE FROM raw\.interventions_daily.*?)\s*"""\)',
            src, re.DOTALL,
        )
        self.assertIsNotNone(match)
        conn = duckdb.connect(":memory:")
        conn.execute("CREATE SCHEMA raw")
        conn.execute("CREATE TABLE raw.interventions_daily(date DATE, notes VARCHAR)")
        conn.execute("""
            INSERT INTO raw.interventions_daily VALUES
            ('2020-03-01', 'mfp_historical_fasting:EF'),
            ('2020-03-02', 'historical_fasting_import: EF'),
            ('2026-03-20', NULL)
        """)
        conn.execute(match.group(1))
        remaining = [x[0] for x in conn.execute(
            "SELECT CAST(date AS VARCHAR) FROM raw.interventions_daily ORDER BY date"
        ).fetchall()]
        self.assertEqual(remaining, ["2020-03-01", "2020-03-02"])
        conn.close()

    def test_clean_labels_and_daily_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "db").mkdir()
            db = root / "db" / "fitness.duckdb"
            conn = duckdb.connect(str(db))
            conn.execute("CREATE SCHEMA raw")
            conn.execute("CREATE SCHEMA clean")
            conn.execute("CREATE SCHEMA analytics")
            conn.execute("""
                CREATE TABLE raw.interventions_daily (
                    date DATE, fasting_state VARCHAR, fasting_hours DOUBLE,
                    mounjaro_mg DOUBLE, hunger_score INTEGER, notes VARCHAR)
            """)
            conn.execute("""
                INSERT INTO raw.interventions_daily VALUES
                ('2020-03-01', 'EF', 72, NULL, NULL, 'mfp_historical_fasting:EF'),
                ('2020-03-02', 'extended fasting', NULL, NULL, NULL, 'other'),
                ('2020-03-03', 'baseline', 0, NULL, NULL, 'historical_fasting_import: baseline')
            """)
            conn.close()
            previous = Path.cwd()
            try:
                os.chdir(root)
                runpy.run_path(str(ROOT / "scripts" / "20_build_clean_interventions.py"))
                conn = duckdb.connect(str(db))
                self.assertEqual(
                    conn.execute(
                        "SELECT fasting_state FROM clean.interventions_daily ORDER BY date"
                    ).fetchall(),
                    [("extended_fast",), ("extended_fast",), ("normal",)],
                )
                conn.execute("""
                    CREATE TABLE clean.body_composition (
                        date DATE, weight_kg DOUBLE, fat_mass_kg DOUBLE,
                        lean_mass_kg DOUBLE)
                """)
                conn.execute("""
                    INSERT INTO clean.body_composition VALUES
                        ('2020-03-01', 110, 38, 72)
                """)
                conn.execute("""CREATE TABLE clean.fitbit_daily (
                    date DATE, steps INTEGER, sleep_hours DOUBLE,
                    resting_hr DOUBLE, hrv DOUBLE)""")
                conn.execute("""CREATE TABLE clean.training_summary (
                    date DATE, workout_count INTEGER, total_volume DOUBLE)""")
                conn.execute("""CREATE TABLE clean.nutrition_daily (
                    date DATE, calories DOUBLE, protein_g DOUBLE,
                    carbs_g DOUBLE, fat_g DOUBLE, fiber_g DOUBLE,
                    alcohol_g DOUBLE, source VARCHAR)""")
                conn.execute("""
                    INSERT INTO clean.nutrition_daily VALUES
                    ('2020-03-01', 1500, 120, 30, 40, 10, 0, 'mfp_history')
                """)
                conn.execute("""CREATE TABLE analytics.daily_metrics (
                    date DATE, weight_kg DOUBLE, fat_mass_kg DOUBLE,
                    lean_mass_kg DOUBLE, steps INTEGER, sleep_hours DOUBLE,
                    resting_hr DOUBLE, hrv DOUBLE, calories DOUBLE,
                    protein_g DOUBLE, carbs_g DOUBLE, fat_g DOUBLE,
                    fiber_g DOUBLE, alcohol_g DOUBLE, nutrition_source VARCHAR,
                    workout_count INTEGER, training_volume DOUBLE,
                    fasting_state VARCHAR, fasting_hours DOUBLE,
                    mounjaro_mg DOUBLE, hunger_score INTEGER)""")
                conn.execute("""CREATE TABLE analytics.historical_daily_metrics (
                    date DATE, weight_kg DOUBLE, fat_mass_kg DOUBLE,
                    lean_mass_kg DOUBLE, steps INTEGER, sleep_hours DOUBLE,
                    resting_hr DOUBLE, hrv DOUBLE, calories DOUBLE,
                    protein_g DOUBLE, carbs_g DOUBLE, fat_g DOUBLE,
                    fiber_g DOUBLE, workout_count INTEGER, training_volume DOUBLE,
                    fasting_state VARCHAR, fasting_hours DOUBLE,
                    mounjaro_mg DOUBLE, nutrition_source VARCHAR)""")
                conn.close()
                runpy.run_path(str(ROOT / "scripts" / "30_build_daily_metrics.py"))
                runpy.run_path(str(ROOT / "scripts" / "41_build_historical_daily_metrics.py"))
                conn = duckdb.connect(str(db), read_only=True)
                row = conn.execute("""
                    SELECT fasting_state, fasting_hours, protein_g, carbs_g,
                           fat_g, fiber_g, nutrition_source
                    FROM analytics.historical_daily_metrics
                    WHERE date='2020-03-01'
                """).fetchone()
                self.assertEqual(
                    row, ("extended_fast", 72.0, 120.0, 30.0,
                          40.0, 10.0, "mfp_history")
                )
                conn.close()
            finally:
                os.chdir(previous)


if __name__ == "__main__":
    unittest.main()
