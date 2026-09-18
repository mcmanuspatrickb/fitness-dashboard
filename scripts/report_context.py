from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "fitness.duckdb"
REPORTS_DIR = PROJECT_ROOT / "reports"
STRENGTH_CSV = REPORTS_DIR / "strength_progress_weekly.csv"

LIFT_LABELS = {
    "bench_press": "Bench press",
    "deadlift": "Deadlift",
    "overhead_press": "Overhead press",
    "row": "Row",
    "squat": "Squat",
    "pull_up": "Pull-up",
}


def _mean(frame: pd.DataFrame, column: str) -> float | None:
    if frame.empty or column not in frame.columns:
        return None
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    return None if values.empty else float(values.mean())


def _sum(frame: pd.DataFrame, column: str) -> float | None:
    if frame.empty or column not in frame.columns:
        return None
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    return None if values.empty else float(values.sum())


def _latest(frame: pd.DataFrame, column: str) -> float | None:
    if frame.empty or column not in frame.columns:
        return None
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    return None if values.empty else float(values.iloc[-1])


def _delta(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    return a - b


def _count_complete(frame: pd.DataFrame, *columns: str) -> int:
    if frame.empty or any(column not in frame.columns for column in columns):
        return 0
    mask = pd.Series(True, index=frame.index)
    for column in columns:
        mask &= frame[column].notna()
    return int(mask.sum())


def _analysis_end_date(con: duckdb.DuckDBPyConnection) -> date | None:
    return con.execute(
        """
        WITH source_dates AS (
            SELECT
                (SELECT MAX(date)
                 FROM clean.body_composition
                 WHERE weight_kg IS NOT NULL) AS body_date,
                (SELECT MAX(date)
                 FROM clean.fitbit_daily
                 WHERE steps IS NOT NULL
                    OR sleep_hours IS NOT NULL
                    OR resting_hr IS NOT NULL
                    OR hrv IS NOT NULL) AS activity_date,
                (SELECT MAX(date)
                 FROM clean.nutrition_daily
                 WHERE calories IS NOT NULL
                    OR protein_g IS NOT NULL) AS nutrition_date
        )
        SELECT CASE
            WHEN body_date IS NULL
              OR activity_date IS NULL
              OR nutrition_date IS NULL
            THEN NULL
            ELSE LEAST(body_date, activity_date, nutrition_date)
        END
        FROM source_dates
        """
    ).fetchone()[0]


def _load_daily_frame(con: duckdb.DuckDBPyConnection, end_date: date) -> pd.DataFrame:
    frame = con.execute(
        """
        SELECT
            dm.date,
            b.weight_kg,
            b.fat_mass_kg,
            b.lean_mass_kg,
            n.calories,
            n.protein_g,
            n.carbs_g,
            n.fat_g,
            n.fiber_g,
            n.alcohol_g,
            f.steps,
            f.sleep_hours,
            f.resting_hr,
            f.hrv,
            t.workout_count,
            t.total_volume
        FROM analytics.daily_metrics dm
        LEFT JOIN clean.body_composition b
            ON dm.date = b.date
        LEFT JOIN clean.nutrition_daily n
            ON dm.date = n.date
        LEFT JOIN clean.fitbit_daily f
            ON dm.date = f.date
        LEFT JOIN clean.training_summary t
            ON dm.date = t.date
        WHERE dm.date BETWEEN (?::DATE - INTERVAL 27 DAY) AND ?::DATE
        ORDER BY dm.date
        """,
        [end_date, end_date],
    ).fetchdf()
    if not frame.empty:
        frame["date"] = pd.to_datetime(frame["date"]).dt.date
    return frame


def _strength_4w(end_date: date, path: Path = STRENGTH_CSV) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    try:
        frame = pd.read_csv(path)
    except Exception:
        return []

    required = {"week_start", "target_lift", "estimated_1rm"}
    if frame.empty or not required.issubset(frame.columns):
        return []

    frame = frame.copy()
    frame["week_start"] = pd.to_datetime(frame["week_start"], errors="coerce").dt.date
    frame["estimated_1rm"] = pd.to_numeric(frame["estimated_1rm"], errors="coerce")
    start_date = end_date - timedelta(days=27)
    frame = frame[
        frame["week_start"].notna()
        & frame["estimated_1rm"].notna()
        & (frame["week_start"] >= start_date)
        & (frame["week_start"] <= end_date)
    ]

    results: list[dict[str, Any]] = []
    for lift, sub in frame.groupby("target_lift"):
        sub = sub.sort_values("week_start")
        if len(sub) < 2:
            continue
        first = float(sub.iloc[0]["estimated_1rm"])
        latest = float(sub.iloc[-1]["estimated_1rm"])
        change = latest - first
        if change > 1.0:
            direction = "up"
        elif change < -1.0:
            direction = "down"
        else:
            direction = "flat"
        results.append(
            {
                "target_lift": str(lift),
                "label": LIFT_LABELS.get(str(lift), str(lift).replace("_", " ").title()),
                "first_e1rm": first,
                "latest_e1rm": latest,
                "change_e1rm": change,
                "direction": direction,
                "observations": int(len(sub)),
            }
        )

    order = {name: i for i, name in enumerate(LIFT_LABELS)}
    results.sort(key=lambda item: order.get(item["target_lift"], 999))
    return results


def load_report_context(db_path: Path = DB_PATH) -> dict[str, Any]:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        end_date = _analysis_end_date(con)
        if end_date is None:
            return {
                "analysis_end_date": None,
                "current": pd.DataFrame(),
                "previous": pd.DataFrame(),
                "trailing_28": pd.DataFrame(),
                "weekly": {},
                "coverage": {},
                "trend_4w": {},
                "strength_4w": [],
            }
        trailing_28 = _load_daily_frame(con, end_date)
    finally:
        con.close()

    current_start = end_date - timedelta(days=6)
    previous_start = end_date - timedelta(days=13)
    previous_end = end_date - timedelta(days=7)
    first_week_end = end_date - timedelta(days=21)

    current = trailing_28[trailing_28["date"].between(current_start, end_date)].copy()
    previous = trailing_28[trailing_28["date"].between(previous_start, previous_end)].copy()
    first_week = trailing_28[
        trailing_28["date"].between(end_date - timedelta(days=27), first_week_end)
    ].copy()

    recent_weight = _mean(current, "weight_kg")
    prior_weight = _mean(previous, "weight_kg")
    recent_fat = _mean(current, "fat_mass_kg")
    prior_fat = _mean(previous, "fat_mass_kg")
    recent_lean = _mean(current, "lean_mass_kg")
    prior_lean = _mean(previous, "lean_mass_kg")

    weekly = {
        "latest_weight": _latest(current, "weight_kg"),
        "recent_weight": recent_weight,
        "prior_weight": prior_weight,
        "weight_delta": _delta(recent_weight, prior_weight),
        "recent_fat": recent_fat,
        "prior_fat": prior_fat,
        "fat_delta": _delta(recent_fat, prior_fat),
        "recent_lean": recent_lean,
        "prior_lean": prior_lean,
        "lean_delta": _delta(recent_lean, prior_lean),
        "recent_calories": _mean(current, "calories"),
        "recent_protein": _mean(current, "protein_g"),
        "recent_carbs": _mean(current, "carbs_g"),
        "recent_fat_g": _mean(current, "fat_g"),
        "recent_fiber": _mean(current, "fiber_g"),
        "recent_alcohol": _mean(current, "alcohol_g"),
        "recent_steps": _mean(current, "steps"),
        "recent_sleep": _mean(current, "sleep_hours"),
        "recent_rhr": _mean(current, "resting_hr"),
        "recent_hrv": _mean(current, "hrv"),
        "prior_rhr": _mean(previous, "resting_hr"),
        "prior_hrv": _mean(previous, "hrv"),
        "prior_sleep": _mean(previous, "sleep_hours"),
        "rhr_delta": _delta(_mean(current, "resting_hr"), _mean(previous, "resting_hr")),
        "hrv_delta": _delta(_mean(current, "hrv"), _mean(previous, "hrv")),
        "sleep_delta": _delta(_mean(current, "sleep_hours"), _mean(previous, "sleep_hours")),
        "recent_workouts": _sum(current, "workout_count"),
        "recent_training_volume": _mean(current[current["total_volume"].notna()], "total_volume"),
    }

    coverage = {
        "body_composition_days": _count_complete(current, "weight_kg", "fat_mass_kg"),
        "nutrition_days": _count_complete(current, "calories", "protein_g"),
        "steps_days": _count_complete(current, "steps"),
        "sleep_days": _count_complete(current, "sleep_hours"),
        "recovery_days": _count_complete(current, "resting_hr", "hrv"),
        "workouts": int(round(weekly["recent_workouts"] or 0)),
    }

    checks = [
        coverage["body_composition_days"] >= 4,
        coverage["nutrition_days"] >= 6,
        coverage["steps_days"] >= 6,
        coverage["sleep_days"] >= 6,
        coverage["recovery_days"] >= 5,
    ]
    passed = sum(checks)
    if passed == len(checks):
        confidence = "HIGH"
    elif passed >= 3:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"
    coverage["confidence"] = confidence
    coverage["checks_passed"] = passed
    coverage["checks_total"] = len(checks)

    first_weight = _mean(first_week, "weight_kg")
    first_fat = _mean(first_week, "fat_mass_kg")
    first_lean = _mean(first_week, "lean_mass_kg")
    trend_4w = {
        "weight_delta": _delta(recent_weight, first_weight),
        "fat_delta": _delta(recent_fat, first_fat),
        "lean_delta": _delta(recent_lean, first_lean),
        "avg_calories": _mean(trailing_28, "calories"),
        "avg_protein": _mean(trailing_28, "protein_g"),
        "avg_steps": _mean(trailing_28, "steps"),
        "avg_sleep": _mean(trailing_28, "sleep_hours"),
        "workouts": _sum(trailing_28, "workout_count"),
        "nutrition_days": _count_complete(trailing_28, "calories", "protein_g"),
        "body_composition_days": _count_complete(trailing_28, "weight_kg", "fat_mass_kg"),
    }

    return {
        "analysis_end_date": end_date,
        "current": current,
        "previous": previous,
        "trailing_28": trailing_28,
        "weekly": weekly,
        "coverage": coverage,
        "trend_4w": trend_4w,
        "strength_4w": _strength_4w(end_date),
    }
