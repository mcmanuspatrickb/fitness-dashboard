"""Offline integration rehearsal: the real snapshot, email and packet code.

All data are deliberately fictional. The rehearsal uses an isolated temporary
DuckDB and report directory. It has NO Cronometer, Neon, or SMTP credentials.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import smtplib
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


canonical = module("integration_canonical", "79_canonical_coaching_engine.py")
email = module("integration_email", "111_build_coaching_summary.py")
packet = module("integration_packet", "81_build_weekly_coaching_packet.py")


class FictionalWeeklyIntegrationTests(unittest.TestCase):
    def _database(self, path: Path, end_date: date) -> None:
        with duckdb.connect(str(path)) as db:
            for schema in ("analytics", "clean", "raw"):
                db.execute(f"CREATE SCHEMA {schema}")
            db.execute("CREATE TABLE analytics.daily_metrics(date DATE)")
            db.execute("CREATE TABLE clean.body_composition(date DATE, weight_kg DOUBLE)")
            db.execute("CREATE TABLE clean.nutrition_daily(date DATE, calories DOUBLE)")
            db.execute("CREATE TABLE raw.hevy_workouts(workout_id VARCHAR, start_time TIMESTAMP)")
            db.execute("CREATE TABLE raw.hevy_sets(workout_id VARCHAR, exercise_title VARCHAR, set_type VARCHAR, weight_kg DOUBLE, reps INTEGER, rpe DOUBLE)")
            days = [end_date - timedelta(days=41 - n) for n in range(42)]
            db.executemany("INSERT INTO analytics.daily_metrics VALUES (?)", [(d,) for d in days])
            db.executemany(
                "INSERT INTO clean.body_composition VALUES (?,?)",
                [(d, 105.0 - 0.09 * i) for i, d in enumerate(days)],
            )
            db.executemany(
                "INSERT INTO clean.nutrition_daily VALUES (?,?)",
                [(d, 1750.0 + 25 * (i % 3)) for i, d in enumerate(days)],
            )
            sessions = [
                ("FAKE-SESSION-1", datetime.combine(end_date - timedelta(days=3), datetime.min.time())),
                ("FAKE-SESSION-2", datetime.combine(end_date - timedelta(days=1), datetime.min.time())),
            ]
            db.executemany("INSERT INTO raw.hevy_workouts VALUES (?,?)", sessions)
            exercises = [
                ("FAKE-SESSION-1", "Push Press", "normal", 45, 8, 8.0),
                ("FAKE-SESSION-1", "Dumbbell Step Up", "normal", 18, 8, 8.0),
                ("FAKE-SESSION-1", "Box Jump", "normal", 0, 4, 7.0),
                ("FAKE-SESSION-2", "Bench Press (Barbell)", "normal", 75, 6, 8.0),
                ("FAKE-SESSION-2", "Deadlift (Barbell)", "normal", 105, 6, 8.0),
                ("FAKE-SESSION-2", "Deadlift (Barbell)", "warmup", 45, 8, 4.0),
            ]
            db.executemany("INSERT INTO raw.hevy_sets VALUES (?,?,?,?,?,?)", exercises)

    def _context(self, end_date: date) -> dict:
        recent = [end_date - timedelta(days=6 - i) for i in range(7)]
        all_28 = [end_date - timedelta(days=27 - i) for i in range(28)]
        return {
            "analysis_end_date": end_date,
            "weekly": {
                "recent_weight": 101.5, "recent_lean": 73.0,
                "recent_calories": 1425, "recent_protein": 95,
                "recent_workouts": 2, "recent_sleep": 7.4,
                "recent_steps": 8000,
            },
            "trend_4w": {
                "fat_delta": -1.2, "lean_delta": -1.0, "weight_delta": -2.2,
            },
            "strength_4w": [
                {"direction": "down", "label": "Bench press", "current_best_e1rm": 85,
                 "prior_best_e1rm": 91},
                {"direction": "down", "label": "Squat", "current_best_e1rm": 120,
                 "prior_best_e1rm": 128},
            ],
            "current": pd.DataFrame({
                "date": recent, "protein_g": [85, 98, 110, 101, 95, 87, 92],
                "sleep_hours": [7.4] * 7, "steps": [8000] * 7,
            }),
            "trailing_28": pd.DataFrame({
                "date": all_28,
                "resting_hr": [74] * 21 + [77] * 7,
                "hrv": [14] * 21 + [11] * 7,
            }),
            "performance": {
                "grip_measurement_count": 4, "grip_trend_pct": 0.0,
                "latest_grip_overall_kg": 49.0, "latest_grip_date": "2026-10-01",
                "latest_waist_cm": 111.0, "latest_waist_date": "2026-09-25",
            },
            "coverage": {"confidence": "HIGH", "checks_passed": 6, "checks_total": 6},
        }

    def test_fictional_snapshot_to_unsent_email_and_packet(self):
        analysis_date = date(2026, 10, 25)
        start = datetime(2026, 10, 23, 20, tzinfo=timezone.utc)
        fast = [{
            "start_at": start,
            "end_at": start + timedelta(hours=35),
            "synced_at": datetime(2026, 10, 26, tzinfo=timezone.utc),
        }]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports = root / "reports"
            reports.mkdir()
            database = root / "fictional.duckdb"
            self._database(database, analysis_date)
            (reports / "current_phase.json").write_text(json.dumps({"current_phase": "cut"}))
            (reports / "cut_stress_guardrail.json").write_text(
                json.dumps({"status": "RECOVERY_CONCERN"})
            )
            (reports / "adaptive_calorie_recommendation.json").write_text(
                json.dumps({
                    "action": "INCREASE", "final_calorie_adjustment": 150,
                    "target_intake": 1500, "theoretical_model_intake": 2100,
                    "target_deficit": 250,
                })
            )
            (reports / "data_freshness.json").write_text(
                json.dumps({"overall_status": "fresh"})
            )
            (reports / "adaptive_calorie_recommendation.txt").write_text(
                "Adaptive Calorie Recommendation\n==============================\n"
                "Recommendation\n--------------\nAction: INCREASE\n"
                "Calorie adjustment: +150 kcal/day\n"
                "actionable target intake: 1500 kcal/day\n"
                "Why\n---\nSynthetic trend only\n"
            )
            (reports / "adaptive_coaching_feedback.txt").write_text(
                "Adaptive Coaching Feedback\n=========================\n"
                "Current Decision\n----------------\n"
                "actionable target intake: 1500 kcal/day\n"
            )

            context = self._context(analysis_date)
            # No live secret, DB writes, upstream syncs, or SMTP even if imported.
            with (
                patch.dict(os.environ, {"WITHINGS_DATABASE_URL": ""}),
                patch.object(canonical, "DB_PATH", database),
                patch.object(canonical, "OUT_JSON", reports / "canonical_coaching_snapshot.json"),
                patch.object(canonical, "OUT_TXT", reports / "canonical_coaching_snapshot.txt"),
                patch.object(canonical, "PHASE_JSON", reports / "current_phase.json"),
                patch.object(canonical, "GUARDRAIL_JSON", reports / "cut_stress_guardrail.json"),
                patch.object(canonical, "CALORIE_JSON", reports / "adaptive_calorie_recommendation.json"),
                patch.object(canonical, "PERSONAL_BLOCKS", reports / "personal_response_blocks.csv"),
                patch.object(canonical, "FEEDBACK_HISTORY", root / "adaptive_coaching_history.csv"),
                patch.object(canonical, "load_report_context", return_value=context),
                patch.object(canonical, "fetch_intervals", return_value=(fast, "AVAILABLE")),
                patch.object(canonical.psycopg, "connect", side_effect=AssertionError("Neon access forbidden")),
                patch.object(smtplib, "SMTP_SSL", side_effect=AssertionError("Email send forbidden")),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                canonical.main()

                snapshot = json.loads(
                    (reports / "canonical_coaching_snapshot.json").read_text()
                )
                self.assertEqual(snapshot["analysis_date"], analysis_date.isoformat())
                self.assertEqual(snapshot["states"]["fat_loss"], "PROGRESSING")
                self.assertEqual(snapshot["states"]["muscle_preservation"], "CONCERN")
                self.assertEqual(snapshot["states"]["recovery"], "RECOVERY_CONCERN")
                self.assertEqual(snapshot["states"]["training"], "ON_TARGET")
                self.assertEqual(snapshot["fasting"]["evidence_quality"], "FASTING_CONFOUNDED")
                self.assertEqual(snapshot["energy"]["confidence"], "LOW_FASTING_CONFOUNDED")
                self.assertEqual(snapshot["energy"]["stability"], "STABLE")
                self.assertEqual(snapshot["decision"]["target_intake"], 1500)
                self.assertTrue(snapshot["decision"]["review_required"])
                self.assertFalse(snapshot["decision"]["actionable"])
                self.assertTrue(snapshot["energy"]["overlapping_windows"])
                self.assertEqual(snapshot["training_dose"]["unmapped_working_sets_28d"], 0)
                self.assertGreater(
                    snapshot["training_dose"]["excluded_non_strength_sets_28d"], 0
                )
                groups = {row["muscle_group"] for row in snapshot["training_dose"]["groups"]}
                self.assertTrue({"Chest", "Quads", "Shoulders", "Posterior chain"} <= groups)

                with (
                    patch.object(email, "SNAPSHOT_JSON", reports / "canonical_coaching_snapshot.json"),
                    patch.object(email, "FRESHNESS_JSON", reports / "data_freshness.json"),
                    patch.object(email, "OUTPUT_TXT", reports / "weekly_coaching_summary.txt"),
                    patch.object(email, "OUTPUT_HTML", reports / "weekly_coaching_summary.html"),
                ):
                    email.main()

                with (
                    patch.object(packet, "CANONICAL_JSON", reports / "canonical_coaching_snapshot.json"),
                    patch.object(packet, "OUT_PATH", reports / "weekly_coaching_packet.txt"),
                    patch.object(packet, "SOURCE_FILES", {
                        name: reports / path.name
                        for name, path in packet.SOURCE_FILES.items()
                    }),
                    patch.object(packet, "load_report_context", return_value=context),
                ):
                    packet.main()

            plain = (reports / "weekly_coaching_summary.txt").read_text()
            html = (reports / "weekly_coaching_summary.html").read_text()
            attachment = (reports / "weekly_coaching_packet.txt").read_text()
            for body in (plain, html, attachment):
                self.assertIn("2026-10-25", body)
                self.assertIn("1500", body)
            self.assertIn("REVIEW REQUIRED", plain)
            self.assertIn("PROVISIONAL", html)
            self.assertIn("CALORIE MODEL REVIEW REQUIRED", attachment)
            self.assertIn("provisional model intake target", attachment)
            self.assertNotIn("actionable target intake:", attachment)


if __name__ == "__main__":
    unittest.main()
