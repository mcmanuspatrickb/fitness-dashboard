"""Conservative, read-only interpretation of verified Cronometer fasting intervals.

No inference from missing food entries. A missing/stale manual sync is UNKNOWN,
not evidence that no fast occurred. Utilities are deterministic and use fictional
data in unit tests; production query is SELECT only.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Any
import os

LOCAL_ZONE = ZoneInfo("Europe/Berlin")
EXTENDED_HOURS = 24.0


def fetch_intervals(database_url: str | None = None) -> tuple[list[dict[str, Any]], str]:
    """Read already imported Neon intervals; never sync or modify Cronometer.

    None/UNKNOWN indicates that the dataset could not be verified. Empty/AVAILABLE
    is not proof that historical periods contained no fasts.
    """
    url = database_url if database_url is not None else os.getenv("WITHINGS_DATABASE_URL", "")
    if not url:
        return [], "UNAVAILABLE"
    try:
        import psycopg
        with psycopg.connect(url, connect_timeout=7) as con:
            with con.cursor() as cur:
                cur.execute(
                    "SELECT start_at, end_at, synced_at FROM "
                    "public.cronometer_fasting_intervals ORDER BY start_at"
                )
                rows = cur.fetchall()
        intervals = [
            {"start_at": start, "end_at": end, "synced_at": synced}
            for start, end, synced in rows
            if start is not None and start.tzinfo is not None
            and (end is None or (end.tzinfo is not None and end > start))
        ]
        return intervals, "AVAILABLE"
    except Exception:
        # Keep credentials and database error details out of email and reports.
        return [], "UNAVAILABLE"


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, LOCAL_ZONE)
    stop = datetime.combine(day + timedelta(days=1), time.min, LOCAL_ZONE)
    return start.astimezone(timezone.utc), stop.astimezone(timezone.utc)


def exposure_by_day(
    first: date, last: date, intervals: list[dict[str, Any]],
) -> dict[date, dict[str, Any]]:
    """Calculate true elapsed fasting hours, including DST transitions.

    An open-ended interval is clipped at the reporting window, and is treated
    as extended only after 24 observed hours; refeeding requires a known end.
    """
    result: dict[date, dict[str, Any]] = {}
    day = first
    while day <= last:
        left, right = _day_bounds(day)
        hours = 0.0
        extended = False
        refeed = False
        for row in intervals:
            begin, end = row["start_at"], row.get("end_at")
            if begin.tzinfo is None or (end is not None and end.tzinfo is None):
                continue
            # Always compare/subtract in UTC. Python arithmetic between
            # two datetimes with the SAME ZoneInfo can use wall-clock hours
            # across DST, which would misclassify a borderline 24-hour fast.
            begin = begin.astimezone(timezone.utc)
            end = end.astimezone(timezone.utc) if end is not None else None
            real_end = end if end is not None else right
            elapsed = (real_end - begin).total_seconds() / 3600.0
            overlap = max(0.0, (min(right, real_end) - max(left, begin)).total_seconds() / 3600.0)
            hours += overlap
            if overlap > 0 and elapsed >= EXTENDED_HOURS:
                extended = True
            if end is not None and elapsed >= EXTENDED_HOURS:
                if max(left, end) < min(right, end + timedelta(hours=24)):
                    refeed = True
        day_hours = (right - left).total_seconds() / 3600.0
        result[day] = {
            "fasting_hours": round(min(day_hours, hours), 2),
            "extended_fast": extended,
            "refeed": refeed,
            "intermittent_fast": hours >= 12.0 and not extended,
        }
        day += timedelta(days=1)
    return result


def assess_fasting(
    analysis_day: date,
    intervals: list[dict[str, Any]],
    source_status: str,
) -> dict[str, Any]:
    first = analysis_day - timedelta(days=41)
    days = exposure_by_day(first, analysis_day, intervals)
    last28 = {d: row for d, row in days.items() if d >= analysis_day - timedelta(days=27)}
    flagged28 = sum(1 for row in last28.values() if row["extended_fast"] or row["refeed"])
    flagged42 = sum(1 for row in days.values() if row["extended_fast"] or row["refeed"])
    latest_sync = max((i.get("synced_at") for i in intervals if i.get("synced_at")), default=None)
    source_stale = (
        latest_sync is None
        or (datetime.combine(analysis_day + timedelta(days=1), time.min, timezone.utc)
            - latest_sync.astimezone(timezone.utc)).total_seconds() > 7 * 86400
    )
    if source_status != "AVAILABLE" or source_stale:
        quality = "UNKNOWN"
    elif flagged28:
        quality = "FASTING_CONFOUNDED"
    else:
        quality = "LIMITED_HISTORY"
    return {
        "source_status": source_status,
        "manual_sync_stale": bool(source_stale),
        "interval_count": len(intervals),
        "last_synced_at": latest_sync.isoformat() if latest_sync else None,
        "extended_or_refeed_days_28": flagged28,
        "extended_or_refeed_days_42": flagged42,
        "intermittent_days_28": sum(bool(r["intermittent_fast"]) for r in last28.values()),
        "evidence_quality": quality,
        "review_required": quality in {"FASTING_CONFOUNDED", "UNKNOWN"},
        "note": (
            "Recent extended fasting/refeeding can distort scale/BIA slopes; agreement "
            "between overlapping TDEE windows does not establish accuracy."
            if flagged28 else
            "Fasting history is manually imported and incomplete; absent intervals "
            "cannot establish fasting-free historical blocks."
        ),
    }


def overlaps_extended_fast(
    start: date, end: date, intervals: list[dict[str, Any]],
) -> bool:
    if start > end:
        return False
    return any(
        row["extended_fast"] or row["refeed"]
        for row in exposure_by_day(start, end, intervals).values()
    )
