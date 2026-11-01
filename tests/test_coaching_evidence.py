"""Fictional-only, offline tests for conservative coaching evidence."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import coaching_evidence as evidence


class FastingEvidenceTests(unittest.TestCase):
    def test_dst_and_refeed_are_elapsed_time_aware(self):
        berlin = ZoneInfo("Europe/Berlin")
        # Fictional fast through autumn clock change, 25-hour local day.
        start = datetime(2026, 10, 24, 22, 30, tzinfo=berlin)
        end = datetime(2026, 10, 26, 12, 15, tzinfo=berlin)
        rows = [{"start_at": start, "end_at": end, "synced_at": end}]
        daily = evidence.exposure_by_day(date(2026, 10, 24), date(2026, 10, 27), rows)
        self.assertAlmostEqual(daily[date(2026, 10, 25)]["fasting_hours"], 25.0)
        self.assertTrue(daily[date(2026, 10, 25)]["extended_fast"])
        self.assertTrue(daily[date(2026, 10, 26)]["refeed"])
        self.assertTrue(daily[date(2026, 10, 27)]["refeed"])
        self.assertFalse(daily[date(2026, 10, 24)]["refeed"])

    def test_regular_intermittent_fast_is_not_extended(self):
        start = datetime(2026, 10, 21, 20, tzinfo=timezone.utc)
        end = start + timedelta(hours=16)
        rows = [{"start_at": start, "end_at": end, "synced_at": end}]
        daily = evidence.exposure_by_day(date(2026, 10, 21), date(2026, 10, 22), rows)
        self.assertFalse(any(r["extended_fast"] or r["refeed"] for r in daily.values()))
        self.assertTrue(evidence.assess_fasting(date(2026, 10, 22), rows, "AVAILABLE")["evidence_quality"] == "LIMITED_HISTORY")

    def test_28_day_fasting_confounds_tdee_agreement(self):
        start = datetime(2026, 10, 25, 8, tzinfo=timezone.utc)
        end = start + timedelta(hours=30)
        synced = datetime(2026, 10, 30, tzinfo=timezone.utc)
        rows = [{"start_at": start, "end_at": end, "synced_at": synced}]
        state = evidence.assess_fasting(date(2026, 10, 30), rows, "AVAILABLE")
        self.assertEqual(state["evidence_quality"], "FASTING_CONFOUNDED")
        self.assertTrue(state["review_required"])
        self.assertTrue(evidence.overlaps_extended_fast(date(2026, 10, 24), date(2026, 10, 28), rows))
        self.assertFalse(evidence.overlaps_extended_fast(date(2026, 9, 1), date(2026, 9, 7), rows))

    def test_absent_sync_is_unknown_not_fasting_free(self):
        with patch.dict("os.environ", {"WITHINGS_DATABASE_URL": ""}):
            rows, status = evidence.fetch_intervals()
        self.assertEqual((rows, status), ([], "UNAVAILABLE"))
        state = evidence.assess_fasting(date(2026, 10, 30), rows, status)
        self.assertEqual(state["evidence_quality"], "UNKNOWN")
        self.assertTrue(state["review_required"])

    def test_open_fast_requires_24_observed_hours(self):
        start = datetime(2026, 10, 20, 20, tzinfo=timezone.utc)
        rows = [{"start_at": start, "end_at": None}]
        today = evidence.exposure_by_day(date(2026, 10, 20), date(2026, 10, 22), rows)
        self.assertFalse(today[date(2026, 10, 20)]["extended_fast"])
        self.assertTrue(today[date(2026, 10, 22)]["extended_fast"])


if __name__ == "__main__":
    unittest.main()
