"""Fictional, offline regressions for isolated coaching development.

No Neon writes, Cronometer API requests, scheduled jobs, or email delivery.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def load_script(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


feedback = load_script("feedback_safeguards", "76_adaptive_coaching_feedback.py")
response = load_script("response_safeguards", "75_personal_response_analysis.py")
canonical = load_script("canonical_safeguards", "79_canonical_coaching_engine.py")
email = load_script("weekly_email_safeguards", "111_build_coaching_summary.py")


class CoachingSafeguardTests(unittest.TestCase):
    def _fake_history(self):
        row = {key: pd.NA for key in feedback.HISTORY_COLUMNS}
        row.update({
            "decision_date": "2026-09-01", "action": "HOLD",
            "calorie_adjustment": 0, "baseline_calories": 1800,
            "baseline_fat": 31, "baseline_lean": 70, "baseline_weight": 101,
            "baseline_sleep": 7.0, "baseline_rhr": 75, "baseline_hrv": 11,
            "baseline_steps": 7500, "target_protein_min": 130,
            "target_sleep_h": 7, "target_workouts": 2, "target_steps": 7000,
            "outcome7_status": "INSUFFICIENT_DATA",
            "outcome7_confounded": False,
        })
        return pd.DataFrame([row], columns=feedback.HISTORY_COLUMNS)

    def _fake_metrics(self):
        return {
            "body_days": 7, "sleep_days": 7, "weight": 100.7,
            "fat": 30.6, "lean": 70.0, "calories": 1810,
            "protein": 150, "sleep": 7.2, "rhr": 75,
            "hrv": 12, "steps": 7600, "workouts": 2,
            "grip": None, "waist": None,
        }

    def test_delayed_feedback_recovery_is_audited_and_idempotent(self):
        history = self._fake_history()
        with (
            patch.object(feedback.duckdb, "connect"),
            patch.object(feedback, "fetch_intervals", return_value=([], "AVAILABLE")),
            patch.object(feedback, "_window_metrics", return_value=self._fake_metrics()),
            patch.object(feedback, "_strength_summary_at", return_value=(1, 1, 0)),
        ):
            once = feedback._evaluate_history(history, date(2026, 9, 10))
            self.assertEqual(once.at[0, "outcome7_status"], "HELPFUL")
            self.assertEqual(len(once.attrs["revisions"]), 1)
            twice = feedback._evaluate_history(once, date(2026, 9, 10))
            self.assertEqual(twice.at[0, "outcome7_status"], "HELPFUL")
            self.assertEqual(twice.attrs["revisions"], [])

    def test_real_extended_fast_confounds_feedback(self):
        start = datetime(2026, 9, 2, tzinfo=timezone.utc)
        rows = [{"start_at": start, "end_at": start + timedelta(hours=31)}]
        with (
            patch.object(feedback.duckdb, "connect"),
            patch.object(feedback, "fetch_intervals", return_value=(rows, "AVAILABLE")),
            patch.object(feedback, "_window_metrics", return_value=self._fake_metrics()),
            patch.object(feedback, "_strength_summary_at", return_value=(1, 1, 0)),
        ):
            evaluated = feedback._evaluate_history(self._fake_history(), date(2026, 9, 10))
        self.assertEqual(evaluated.at[0, "outcome7_status"], "INCONCLUSIVE")
        self.assertTrue(evaluated.at[0, "outcome7_confounded"])

    def test_primary_dose_mapping_excludes_mobility_and_jumps(self):
        self.assertEqual(canonical._muscle_group("Push Press"), "Shoulders")
        self.assertEqual(canonical._muscle_group("Dumbbell Step Up"), "Quads")
        self.assertEqual(canonical._muscle_group("Pistol Squat"), "Quads")
        self.assertEqual(canonical._muscle_group("Chest Dip"), "Chest")
        self.assertEqual(canonical._muscle_group("Skullcrusher (Barbell)"), "Triceps")
        self.assertTrue(bool(canonical.NON_STRENGTH_EXERCISES.search("Box Jump")))
        self.assertTrue(bool(canonical.NON_STRENGTH_EXERCISES.search("Cat Cow Stretch")))
        self.assertFalse(bool(canonical.NON_STRENGTH_EXERCISES.search("Barbell Back Squat")))

    def test_14d_response_block_excludes_verified_fasting_refeed(self):
        days = pd.date_range("2026-10-01", periods=14)
        frame = pd.DataFrame({
            "date": days, "weight_kg": [100 - 0.05 * i for i in range(14)],
            "fat_mass_kg": [28 - 0.03 * i for i in range(14)],
            "lean_mass_kg": [72 - 0.02 * i for i in range(14)],
            "calories": [1900] * 14, "protein_g": [145] * 14,
            "steps": [7000] * 14, "sleep_hours": [7.5] * 14,
            "resting_hr": [74] * 14, "hrv": [12] * 14,
            "fasting_state": ["normal"] * 14,
            "verified_extended_or_refeed": [False] * 9 + [True] * 5,
            "fasting_source_status": ["AVAILABLE"] * 14,
            "workout_count": [1 if i in (1, 6, 9) else 0 for i in range(14)],
        })
        blocks = response.build_blocks(frame)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks.iloc[0]["fasting_days"], 5)
        self.assertEqual(blocks.iloc[0]["verified_fasting_or_refeed_days"], 5)

    def test_email_shared_decision_is_provisional_if_review_required(self):
        snapshot = {
            "analysis_date": "2026-10-24", "generated_at": "2026-10-26T08:00:00Z",
            "phase": "cut", "states": {},
            "energy": {"stability": "STABLE", "confidence": "LOW_FASTING_CONFOUNDED"},
            "fasting": {"evidence_quality": "FASTING_CONFOUNDED",
                        "extended_or_refeed_days_28": 4},
            "decision": {"action": "INCREASE", "calorie_adjustment": 150,
                         "target_intake": 1525, "theoretical_model_intake": 1800,
                         "review_required": True, "review_reason": "Fictional extended fast"},
        }
        text, html = email._build("fresh", snapshot)
        self.assertIn("REVIEW REQUIRED", text)
        self.assertIn("provisional, not actionable", text)
        self.assertIn("Fictional extended fast", text)
        self.assertIn("PROVISIONAL", html)
        self.assertIn("Low Fasting Confounded", html)


if __name__ == "__main__":
    unittest.main()
