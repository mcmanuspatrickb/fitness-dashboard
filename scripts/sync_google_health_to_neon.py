"""Mirror normalized Google Health daily records into the private Health_Dashboard Neon DB.

The local DuckDB remains the coaching analytics source; this mirror makes
source-labelled daily values available for read-only ChatGPT comparisons.
Call only after a successful Google Health ingestion. Never write credentials
or health records to the repository, logs, or Actions artifacts.
"""
from __future__ import annotations

import math
import os
from datetime import date
from pathlib import Path

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "fitness.duckdb"


def _number(value):
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def read_daily_rows(start_date: date, end_date: date, db_path: Path = DB_PATH):
    """Read only current, explicitly labelled Google Health sources."""
    with duckdb.connect(str(db_path), read_only=True) as con:
        nutrition = con.execute(
            """
            SELECT date, calories, protein_g, carbs_g, fat_g
            FROM raw.nutrition_daily
            WHERE date BETWEEN ? AND ? AND source = 'google_health_cronometer'
            ORDER BY date
            """, [start_date, end_date]
        ).fetchall()
        activity = con.execute(
            """
            SELECT date, steps, calories_burned, resting_hr, hrv,
                   sleep_hours, deep_sleep_minutes, rem_sleep_minutes,
                   wake_minutes
            FROM raw.fitbit_daily
            WHERE date BETWEEN ? AND ? AND source = 'google_health'
            ORDER BY date
            """, [start_date, end_date]
        ).fetchall()

    nutrition_rows = [
        (day, *(_number(value) for value in values))
        for day, *values in nutrition
    ]
    activity_rows = [
        (day, int(steps) if _number(steps) is not None else None,
         *(_number(value) for value in values))
        for day, steps, *values in activity
        if any(_number(value) is not None for value in (steps, *values))
    ]
    return nutrition_rows, activity_rows


def mirror_daily_to_neon(start_date: date, end_date: date, db_path: Path = DB_PATH):
    """Idempotent upserts; absent Cronometer days stay absent, never zero-filled."""
    database_url = os.getenv("WITHINGS_DATABASE_URL", "").strip()
    if not database_url:
        print("Neon daily mirror skipped: WITHINGS_DATABASE_URL is not configured.")
        return {"status": "skipped", "nutrition": 0, "activity": 0}

    import psycopg

    nutrition_rows, activity_rows = read_daily_rows(start_date, end_date, db_path)

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            if nutrition_rows:
                cur.executemany(
                    """
                    INSERT INTO google_health_nutrition_daily
                        (day, calories_kcal, protein_g, carbohydrates_g, fat_g,
                         source, synced_at)
                    VALUES (%s,%s,%s,%s,%s,'cronometer_health_connect', now())
                    ON CONFLICT(day) DO UPDATE SET
                        calories_kcal=EXCLUDED.calories_kcal,
                        protein_g=EXCLUDED.protein_g,
                        carbohydrates_g=EXCLUDED.carbohydrates_g,
                        fat_g=EXCLUDED.fat_g,
                        source=EXCLUDED.source,
                        synced_at=now()
                    """,
                    nutrition_rows
                )
            if activity_rows:
                cur.executemany(
                    """
                    INSERT INTO google_health_activity_daily
                        (day, steps, energy_burned_kcal, resting_hr_bpm, hrv_ms,
                         sleep_hours, deep_sleep_minutes, rem_sleep_minutes,
                         wake_minutes, source, synced_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'google_health', now())
                    ON CONFLICT(day) DO UPDATE SET
                        steps=EXCLUDED.steps,
                        energy_burned_kcal=EXCLUDED.energy_burned_kcal,
                        resting_hr_bpm=EXCLUDED.resting_hr_bpm,
                        hrv_ms=EXCLUDED.hrv_ms,
                        sleep_hours=EXCLUDED.sleep_hours,
                        deep_sleep_minutes=EXCLUDED.deep_sleep_minutes,
                        rem_sleep_minutes=EXCLUDED.rem_sleep_minutes,
                        wake_minutes=EXCLUDED.wake_minutes,
                        source=EXCLUDED.source,
                        synced_at=now()
                    """,
                    activity_rows
                )

    print(
        "Neon daily mirror complete: "
        f"nutrition_days={len(nutrition_rows)}, activity_days={len(activity_rows)}; "
        f"window={start_date}..{end_date}."
    )
    return {"status": "success", "nutrition": len(nutrition_rows),
            "activity": len(activity_rows)}


if __name__ == "__main__":
    from datetime import timedelta
    days = min(90, max(7, int(os.getenv("GOOGLE_HEALTH_LOOKBACK_DAYS", "60"))))
    end = date.today() - timedelta(days=1)
    mirror_daily_to_neon(end - timedelta(days=days - 1), end)
