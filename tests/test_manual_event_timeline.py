"""Fictional-only regression tests for new manual data feeds."""
import importlib.util
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load(filename):
    spec = importlib.util.spec_from_file_location(filename.replace(".py", ""), SCRIPTS / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


exercise = load("19_sync_exercise_timeline.py")
fasting = load("20_sync_cronometer_fasts.py")


class ExerciseTimelineTests(unittest.TestCase):
    def test_hevy_normalization(self):
        workouts = [{"id": "fictional-1",
                     "start_time": "2026-10-27T12:00:00Z",
                     "end_time": "2026-10-27T13:00:00Z",
                     "title": "Test weights",
                     "exercises": [{"title": "Squat", "sets": [
                         {"weight_kg": 100, "reps": 5, "rpe": 8},
                         {"weight_kg": 60, "reps": 8, "type": "warmup"}]}]}]
        sessions, sets = exercise.hevy_rows(workouts)
        self.assertEqual(len(sessions), 1)
        self.assertEqual(len(sets), 2)
        self.assertEqual(sets[0][-1], 8.0)
        self.assertEqual(sets[1][5], "warmup")

    def test_naive_hevy_time_rejected(self):
        rows, _ = exercise.hevy_rows([{"id": "bad", "start_time": "2026-10-27T12:00:00",
                                      "end_time": "2026-10-27T13:00:00Z"}])
        self.assertEqual(rows, [])

    def test_google_exercise_is_deterministic(self):
        source = {"exercise": {"interval": {
            "startTime": "2026-10-30T09:00:00Z", "endTime": "2026-10-30T10:00:00Z"},
            "exerciseType": "WALKING", "displayName": "Walk",
            "metricsSummary": {"averageHeartRateBeatsPerMinute": 110}},
            "dataSource": {"platform": "HEALTH_CONNECT", "application": {"packageName": "example"}}}
        rows = exercise.google_exercise_rows([source])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0], exercise.google_exercise_rows([source])[0])
        self.assertEqual(rows[0][3], "WALKING")

    def test_ambiguous_daylight_saving_time_not_guessed(self):
        interval = {"civilStartTime": {"date": {"year": 2026, "month": 10, "day": 25},
                    "time": {"hours": 2, "minutes": 30}}}
        self.assertIsNone(exercise.google_interval(interval))

    def test_instant_used_before_civil_time(self):
        interval = {"startTime": "2026-10-31T07:00:00Z",
                    "civilStartTime": {"date": {"year": 2000, "month": 1, "day": 1}}}
        self.assertEqual(exercise.google_interval(interval),
                         datetime(2026, 10, 31, 7, tzinfo=timezone.utc))

    def test_reject_malformed_long_exercise(self):
        source = {"exercise": {"interval": {"startTime": "2026-10-20T00:00:00Z",
                             "endTime": "2026-10-26T00:00:00Z"}}}
        self.assertEqual(exercise.google_exercise_rows([source]), [])


class FastingImportTests(unittest.TestCase):
    def test_epoch_milliseconds(self):
        start = 1793000000000
        rows = fasting.extract_fasts({"data": {"fasts": [
            {"id": 42, "startTime": start, "endTime": start + 86400000, "name": "Fast"}]}})
        self.assertEqual(rows[0][0], "42")
        self.assertEqual((rows[0][2] - rows[0][1]).total_seconds(), 86400)

    def test_unknown_schema_fails_closed(self):
        with self.assertRaises(ValueError):
            fasting.extract_fasts({"something": "different"})

    def test_naive_timestamp_rejected(self):
        with self.assertRaises(ValueError):
            fasting.extract_fasts({"fasts": [
                {"id": 1, "startTime": "2026-10-25T10:00:00",
                 "endTime": "2026-10-26T10:00:00"}]})

    def test_active_fast(self):
        rows = fasting.extract_fasts({"fasts": [
            {"id": 1, "startTime": "2026-10-25T10:00:00+01:00", "endTime": None}]})
        self.assertIsNone(rows[0][2])

    def test_bad_end_rejected(self):
        with self.assertRaises(ValueError):
            fasting.extract_fasts({"fasts": [{"id": 1, "startTime": 1793000000,
                                             "endTime": "unknown"}]})

    def test_login_does_not_write_timezone(self):
        class Response:
            def raise_for_status(self): pass
            def json(self): return {"id": 1, "sessionKey": "fictional", "timezone": "Europe/Berlin"}
        class Session:
            def post(self, url, **kw):
                self.payload = kw["json"]
                return Response()
        s = Session()
        with patch.dict("os.environ", {"CRONOMETER_USERNAME": "test",
                                        "CRONOMETER_PASSWORD": "fictional-password"}):
            fasting.login(s)
        self.assertIsNone(s.payload["timezone"])


if __name__ == "__main__":
    unittest.main()
