"""Regression tests for persisted adaptive coaching feedback CSV dtypes."""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "adaptive_coaching_feedback", ROOT / "scripts" / "76_adaptive_coaching_feedback.py"
)
feedback = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(feedback)


class AdaptiveFeedbackHistoryTests(unittest.TestCase):
    def test_empty_csv_outcomes_accept_text_and_boolean_updates(self) -> None:
        # A real persisted history has all outcome columns, but unmatured
        # feedback windows leave them blank. read_csv infers float64 for them.
        with tempfile.TemporaryDirectory() as directory:
            history_path = Path(directory) / "adaptive_coaching_history.csv"
            row = {column: pd.NA for column in feedback.HISTORY_COLUMNS}
            row.update({
                "decision_id": "2026-09-01-hold-+0",
                "decision_date": "2026-09-01",
                "analysis_end_date": "2026-08-31",
                "phase": "cut",
                "action": "HOLD",
                "calorie_adjustment": 0,
                "baseline_calories": 1900,
                "target_protein_min": 138,
                "target_sleep_h": 7.0,
                "target_workouts": 2,
                "target_steps": 7000,
            })
            pd.DataFrame([row], columns=feedback.HISTORY_COLUMNS).to_csv(
                history_path, index=False
            )

            with patch.object(feedback, "HISTORY_PATH", history_path):
                history = feedback._load_history()

            for horizon in (7, 14, 28):
                self.assertEqual(history[f"outcome{horizon}_status"].dtype, object)
                self.assertEqual(history[f"outcome{horizon}_confounded"].dtype, object)

            metrics = {
                "body_days": 7,
                "sleep_days": 7,
                "weight": 100.0,
                "fat": 30.0,
                "lean": 70.0,
                "sleep": 7.2,
                "rhr": 73.0,
                "hrv": 14.0,
                "steps": 8000.0,
                "calories": 1900.0,
                "protein": 145.0,
                "workouts": 2.0,
                "grip": 48.0,
                "waist": 113.0,
            }
            with (
                patch.object(feedback.duckdb, "connect"),
                patch.object(feedback, "_window_metrics", return_value=metrics),
                patch.object(feedback, "_strength_summary_at", return_value=(0, 1, 0)),
            ):
                evaluated = feedback._evaluate_history(history, date(2026, 10, 12))

            for horizon in (7, 14, 28):
                self.assertEqual(evaluated.at[0, f"outcome{horizon}_status"], "NEUTRAL")
                self.assertIs(evaluated.at[0, f"outcome{horizon}_confounded"], False)

            # A second load from the saved CSV must preserve semantics too.
            evaluated.to_csv(history_path, index=False)
            with patch.object(feedback, "HISTORY_PATH", history_path):
                reloaded = feedback._load_history()
            self.assertEqual(feedback._feedback_evidence(reloaded, "HOLD")["eligible"], 1)


if __name__ == "__main__":
    unittest.main()
