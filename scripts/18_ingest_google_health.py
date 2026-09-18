from __future__ import annotations

import os
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import requests


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "fitness.duckdb"
BASE_URL = "https://health.googleapis.com/v4"
ALL_SOURCES = "users/me/dataSourceFamilies/all-sources"
WEARABLES = "users/me/dataSourceFamilies/google-wearables"
LOOKBACK_DAYS = min(90, max(7, int(os.getenv("GOOGLE_HEALTH_LOOKBACK_DAYS", "60"))))


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not configured.")
    return value


def _access_token() -> str:
    response = requests.post(
        "https://oauth2.googleapis.com/token",
        timeout=30,
        data={
            "client_id": _required_env("GOOGLE_HEALTH_CLIENT_ID"),
            "client_secret": _required_env("GOOGLE_HEALTH_CLIENT_SECRET"),
            "refresh_token": _required_env("GOOGLE_HEALTH_REFRESH_TOKEN"),
            "grant_type": "refresh_token",
        },
    )
    if not response.ok:
        raise RuntimeError(
            f"Google token refresh failed ({response.status_code}): {response.text}"
        )
    return response.json()["access_token"]


def _request(
    token: str,
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = requests.request(
        method,
        f"{BASE_URL}/{path.lstrip('/')}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
        params=params,
        json=json_body,
        timeout=60,
    )
    if not response.ok:
        raise RuntimeError(
            f"Google Health API error ({response.status_code}) for {path}: {response.text}"
        )
    return response.json() if response.content else {}


def _civil_midnight(value: date) -> dict[str, Any]:
    return {
        "date": {"year": value.year, "month": value.month, "day": value.day},
        "time": {},
    }


def _date_dict_to_timestamp(value: dict[str, Any] | None) -> pd.Timestamp | None:
    value = value or {}
    try:
        return pd.Timestamp(
            year=int(value["year"]),
            month=int(value["month"]),
            day=int(value["day"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _duration_seconds(value: str | None) -> float:
    if not value:
        return 0.0
    text = value[:-1] if value.endswith("s") else value
    try:
        return float(text)
    except ValueError:
        return 0.0


def _physical_to_local_timestamp(
    physical_time: str | None,
    utc_offset: str | None,
) -> pd.Timestamp | None:
    if not physical_time:
        return None
    try:
        return pd.Timestamp(physical_time) + pd.Timedelta(
            seconds=_duration_seconds(utc_offset)
        )
    except (TypeError, ValueError):
        return None


def _interval_timestamp(
    interval: dict[str, Any] | None,
    *,
    end: bool,
) -> pd.Timestamp | None:
    interval = interval or {}
    civil_key = "civilEndTime" if end else "civilStartTime"
    physical_key = "endTime" if end else "startTime"
    offset_key = "endUtcOffset" if end else "startUtcOffset"

    civil = interval.get(civil_key, {})
    civil_date = _date_dict_to_timestamp(civil.get("date"))
    if civil_date is not None:
        time_value = civil.get("time", {})
        return civil_date + pd.Timedelta(
            hours=int(time_value.get("hours", 0) or 0),
            minutes=int(time_value.get("minutes", 0) or 0),
            seconds=int(time_value.get("seconds", 0) or 0),
        )

    return _physical_to_local_timestamp(
        interval.get(physical_key),
        interval.get(offset_key),
    )


def _list_all(
    token: str,
    data_type: str,
    filter_expression: str,
    *,
    reconciled: bool = False,
    data_source_family: str | None = None,
    page_size: int = 1000,
) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    page_token: str | None = None

    while True:
        params: dict[str, Any] = {
            "page_size": page_size,
            "filter": filter_expression,
        }
        if data_source_family:
            params["dataSourceFamily"] = data_source_family
        if page_token:
            params["page_token"] = page_token

        suffix = ":reconcile" if reconciled else ""
        payload = _request(
            token,
            "GET",
            f"users/me/dataTypes/{data_type}/dataPoints{suffix}",
            params=params,
        )
        points.extend(payload.get("dataPoints", []))
        page_token = payload.get("nextPageToken") or None
        if not page_token:
            return points


def load_steps(token: str, start_date: date, end_date: date) -> pd.DataFrame:
    end_exclusive = end_date + timedelta(days=1)
    window_count = (end_exclusive - start_date).days
    payload = _request(
        token,
        "POST",
        "users/me/dataTypes/steps/dataPoints:dailyRollUp",
        json_body={
            "range": {
                "start": _civil_midnight(start_date),
                "end": _civil_midnight(end_exclusive),
            },
            "windowSizeDays": 1,
            "pageSize": max(1, min(window_count, 90)),
            "dataSourceFamily": WEARABLES,
        },
    )

    rows = []
    for point in payload.get("rollupDataPoints", []):
        day = _date_dict_to_timestamp(point.get("civilStartTime", {}).get("date"))
        if day is None:
            continue
        rows.append(
            {
                "date": day.date(),
                "steps": pd.to_numeric(
                    point.get("steps", {}).get("countSum", 0), errors="coerce"
                ),
            }
        )
    return pd.DataFrame(rows, columns=["date", "steps"])


def load_recovery(
    token: str,
    start_date: date,
    end_date_exclusive: date,
) -> pd.DataFrame:
    rhr_filter = (
        f'daily_resting_heart_rate.date >= "{start_date.isoformat()}" '
        f'AND daily_resting_heart_rate.date < "{end_date_exclusive.isoformat()}"'
    )
    hrv_filter = (
        f'daily_heart_rate_variability.date >= "{start_date.isoformat()}" '
        f'AND daily_heart_rate_variability.date < "{end_date_exclusive.isoformat()}"'
    )

    rhr_points = _list_all(
        token,
        "daily-resting-heart-rate",
        rhr_filter,
        reconciled=True,
        data_source_family=ALL_SOURCES,
    )
    hrv_points = _list_all(
        token,
        "daily-heart-rate-variability",
        hrv_filter,
        reconciled=True,
        data_source_family=ALL_SOURCES,
    )

    rows: dict[date, dict[str, Any]] = defaultdict(dict)
    for point in rhr_points:
        value = point.get("dailyRestingHeartRate", {})
        day = _date_dict_to_timestamp(value.get("date"))
        if day is not None:
            rows[day.date()]["resting_hr"] = pd.to_numeric(
                value.get("beatsPerMinute"), errors="coerce"
            )

    for point in hrv_points:
        value = point.get("dailyHeartRateVariability", {})
        day = _date_dict_to_timestamp(value.get("date"))
        if day is not None:
            rows[day.date()]["hrv"] = pd.to_numeric(
                value.get("averageHeartRateVariabilityMilliseconds"),
                errors="coerce",
            )

    return pd.DataFrame(
        [dict(date=day, **values) for day, values in rows.items()],
        columns=["date", "resting_hr", "hrv"],
    )


def load_sleep(
    token: str,
    start_date: date,
    end_date_exclusive: date,
) -> pd.DataFrame:
    filter_expression = (
        f'sleep.interval.civil_end_time >= "{start_date.isoformat()}" '
        f'AND sleep.interval.civil_end_time < "{end_date_exclusive.isoformat()}"'
    )
    points = _list_all(
        token,
        "sleep",
        filter_expression,
        reconciled=True,
        data_source_family=WEARABLES,
        page_size=25,
    )

    rows: list[dict[str, Any]] = []
    for point in points:
        value = point.get("sleep", {})
        wake_time = _interval_timestamp(value.get("interval"), end=True)
        if wake_time is None:
            continue
        metadata = value.get("metadata", {})
        summary = value.get("summary", {})
        stages = {
            stage.get("type", "UNKNOWN"): int(stage.get("minutes", 0) or 0)
            for stage in summary.get("stagesSummary", [])
        }
        rows.append(
            {
                "date": wake_time.date(),
                "wake_time": wake_time,
                "minutes_asleep": pd.to_numeric(
                    summary.get("minutesAsleep"), errors="coerce"
                ),
                "minutes_awake": pd.to_numeric(
                    summary.get("minutesAwake"), errors="coerce"
                ),
                "deep_sleep_minutes": stages.get("DEEP", 0),
                "rem_sleep_minutes": stages.get("REM", 0),
                "is_nap": bool(metadata.get("nap", False)),
            }
        )

    if not rows:
        return pd.DataFrame(
            columns=[
                "date",
                "sleep_hours",
                "deep_sleep_minutes",
                "rem_sleep_minutes",
                "wake_minutes",
            ]
        )

    frame = pd.DataFrame(rows)
    main = frame[~frame["is_nap"]].copy()
    if main.empty:
        return pd.DataFrame(
            columns=[
                "date",
                "sleep_hours",
                "deep_sleep_minutes",
                "rem_sleep_minutes",
                "wake_minutes",
            ]
        )

    main = (
        main.sort_values(["date", "minutes_asleep"])
        .groupby("date", as_index=False)
        .tail(1)
    )
    main["sleep_hours"] = pd.to_numeric(
        main["minutes_asleep"], errors="coerce"
    ) / 60.0
    main["wake_minutes"] = pd.to_numeric(
        main["minutes_awake"], errors="coerce"
    )
    return main[
        [
            "date",
            "sleep_hours",
            "deep_sleep_minutes",
            "rem_sleep_minutes",
            "wake_minutes",
        ]
    ]


def load_nutrition(token: str, start_date: date, end_date: date) -> pd.DataFrame:
    end_exclusive = end_date + timedelta(days=1)
    filter_expression = (
        f'nutrition_log.interval.civil_start_time >= "{start_date.isoformat()}" '
        f'AND nutrition_log.interval.civil_start_time < "{end_exclusive.isoformat()}"'
    )
    points = _list_all(
        token,
        "nutrition-log",
        filter_expression,
        reconciled=False,
        page_size=1000,
    )

    rows: list[dict[str, Any]] = []
    for point in points:
        value = point.get("nutritionLog", {})
        logged_at = _interval_timestamp(value.get("interval"), end=False)
        if logged_at is None:
            continue

        nutrients = {
            nutrient.get("nutrient"): float(
                nutrient.get("quantity", {}).get("grams", 0) or 0
            )
            for nutrient in value.get("nutrients", [])
        }
        source = point.get("dataSource", {})
        application = source.get("application", {})
        platform = source.get("platform", "")
        package_name = application.get("packageName", "")

        rows.append(
            {
                "date": logged_at.date(),
                "calories": float(value.get("energy", {}).get("kcal", 0) or 0),
                "protein_g": nutrients.get("PROTEIN", 0.0),
                "carbs_g": float(
                    value.get("totalCarbohydrate", {}).get("grams", 0) or 0
                ),
                "fat_g": float(value.get("totalFat", {}).get("grams", 0) or 0),
                "is_cronometer_health_connect": (
                    platform == "HEALTH_CONNECT"
                    and package_name == "com.cronometer.android.gold"
                ),
                "is_fitbit_web_summary": platform == "FITBIT_WEB_API",
            }
        )

    if not rows:
        return pd.DataFrame(
            columns=["date", "calories", "protein_g", "carbs_g", "fat_g"]
        )

    items = pd.DataFrame(rows)
    daily_rows = []
    for day, day_items in items.groupby("date", sort=True):
        cronometer_items = day_items[day_items["is_cronometer_health_connect"]]
        fitbit_summaries = day_items[day_items["is_fitbit_web_summary"]]
        kept = day_items
        if not cronometer_items.empty and not fitbit_summaries.empty:
            kept = day_items[~day_items["is_fitbit_web_summary"]]

        daily_rows.append(
            {
                "date": day,
                "calories": float(kept["calories"].sum()),
                "protein_g": float(kept["protein_g"].sum()),
                "carbs_g": float(kept["carbs_g"].sum()),
                "fat_g": float(kept["fat_g"].sum()),
            }
        )

    return pd.DataFrame(daily_rows)


def _ensure_raw_fitbit_columns(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS raw.fitbit_daily (
            date DATE,
            steps DOUBLE,
            calories_burned DOUBLE,
            resting_hr DOUBLE,
            hrv DOUBLE,
            sleep_hours DOUBLE,
            active_minutes DOUBLE,
            sleep_efficiency DOUBLE,
            deep_sleep_minutes DOUBLE,
            rem_sleep_minutes DOUBLE,
            wake_minutes DOUBLE,
            sleep_score DOUBLE,
            sleep_restlessness DOUBLE,
            source VARCHAR,
            created_at TIMESTAMP
        )
        """
    )
    existing = {
        row[0]
        for row in con.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema='raw' AND table_name='fitbit_daily'
            """
        ).fetchall()
    }
    wanted = {
        "sleep_efficiency": "DOUBLE",
        "deep_sleep_minutes": "DOUBLE",
        "rem_sleep_minutes": "DOUBLE",
        "wake_minutes": "DOUBLE",
        "sleep_score": "DOUBLE",
        "sleep_restlessness": "DOUBLE",
        "source": "VARCHAR",
        "created_at": "TIMESTAMP",
    }
    for column, dtype in wanted.items():
        if column not in existing:
            con.execute(f"ALTER TABLE raw.fitbit_daily ADD COLUMN {column} {dtype}")


def _ensure_raw_nutrition(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS raw.nutrition_daily (
            date DATE,
            calories DOUBLE,
            protein_g DOUBLE,
            carbs_g DOUBLE,
            fat_g DOUBLE,
            fiber_g DOUBLE,
            alcohol_g DOUBLE,
            source VARCHAR,
            created_at TIMESTAMP
        )
        """
    )


def main() -> None:
    end_date = datetime.now().date() - timedelta(days=1)
    start_date = end_date - timedelta(days=LOOKBACK_DAYS - 1)
    end_exclusive = end_date + timedelta(days=1)

    token = _access_token()
    print(f"Loading Google Health data for {start_date} through {end_date}...")

    steps = load_steps(token, start_date, end_date)
    recovery = load_recovery(token, start_date, end_exclusive)
    sleep = load_sleep(token, start_date, end_exclusive)
    nutrition = load_nutrition(token, start_date, end_date)

    daily = pd.DataFrame({
        "date": pd.date_range(start_date, end_date, freq="D").date
    })
    for frame in (steps, recovery, sleep):
        if not frame.empty:
            daily = daily.merge(frame, on="date", how="left")

    for column in (
        "steps",
        "resting_hr",
        "hrv",
        "sleep_hours",
        "deep_sleep_minutes",
        "rem_sleep_minutes",
        "wake_minutes",
    ):
        if column not in daily.columns:
            daily[column] = pd.NA

    daily["calories_burned"] = pd.NA
    daily["active_minutes"] = pd.NA
    daily["sleep_efficiency"] = pd.NA
    daily["sleep_score"] = pd.NA
    daily["sleep_restlessness"] = pd.NA
    daily["source"] = "google_health"
    daily["created_at"] = datetime.now(timezone.utc).replace(tzinfo=None)

    con = duckdb.connect(str(DB_PATH))
    try:
        _ensure_raw_fitbit_columns(con)
        _ensure_raw_nutrition(con)

        con.execute(
            "DELETE FROM raw.fitbit_daily WHERE date BETWEEN ? AND ?",
            [start_date, end_date],
        )
        con.register("google_health_daily_df", daily)
        con.execute(
            """
            INSERT INTO raw.fitbit_daily (
                date, steps, calories_burned, resting_hr, hrv, sleep_hours,
                active_minutes, sleep_efficiency, deep_sleep_minutes,
                rem_sleep_minutes, wake_minutes, sleep_score,
                sleep_restlessness, source, created_at
            )
            SELECT
                date, steps, calories_burned, resting_hr, hrv, sleep_hours,
                active_minutes, sleep_efficiency, deep_sleep_minutes,
                rem_sleep_minutes, wake_minutes, sleep_score,
                sleep_restlessness, source, created_at
            FROM google_health_daily_df
            ORDER BY date
            """
        )

        con.execute(
            "DELETE FROM raw.nutrition_daily WHERE date BETWEEN ? AND ?",
            [start_date, end_date],
        )
        if not nutrition.empty:
            nutrition = nutrition.copy()
            nutrition["fiber_g"] = pd.NA
            nutrition["alcohol_g"] = pd.NA
            nutrition["source"] = "google_health_cronometer"
            nutrition["created_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
            con.register("google_health_nutrition_df", nutrition)
            con.execute(
                """
                INSERT INTO raw.nutrition_daily (
                    date, calories, protein_g, carbs_g, fat_g,
                    fiber_g, alcohol_g, source, created_at
                )
                SELECT
                    date, calories, protein_g, carbs_g, fat_g,
                    fiber_g, alcohol_g, source, created_at
                FROM google_health_nutrition_df
                ORDER BY date
                """
            )

        latest_activity = con.execute(
            "SELECT MAX(date) FROM raw.fitbit_daily WHERE source='google_health'"
        ).fetchone()[0]
        latest_nutrition = con.execute(
            "SELECT MAX(date) FROM raw.nutrition_daily WHERE source='google_health_cronometer'"
        ).fetchone()[0]
    finally:
        con.close()

    print(f"Google Health daily rows loaded: {len(daily)}")
    print(f"Google Health nutrition days loaded: {len(nutrition)}")
    print(f"Latest activity/recovery date: {latest_activity}")
    print(f"Latest nutrition date: {latest_nutrition}")


if __name__ == "__main__":
    main()
