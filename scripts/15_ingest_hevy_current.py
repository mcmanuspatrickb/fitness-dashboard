from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import requests


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "fitness.duckdb"
HEVY_URL = "https://api.hevyapp.com/v1/workouts"


def _api_key() -> str:
    value = os.getenv("HEVY_API_KEY", "").strip()
    if not value:
        raise RuntimeError("HEVY_API_KEY is not configured.")
    return value


def _first(obj: dict[str, Any], keys: list[str], default=None):
    for key in keys:
        value = obj.get(key)
        if value not in (None, ""):
            return value
    return default


def fetch_workouts(page_size: int = 10, max_pages: int = 100) -> list[dict[str, Any]]:
    headers = {"accept": "application/json", "api-key": _api_key()}
    workouts: list[dict[str, Any]] = []

    for page in range(1, max_pages + 1):
        response = requests.get(
            HEVY_URL,
            headers=headers,
            params={"page": page, "pageSize": page_size},
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        batch = (
            payload.get("workouts")
            or payload.get("data")
            or payload.get("items")
            or []
        )
        if not batch:
            break

        workouts.extend(batch)

        page_count = (
            payload.get("page_count")
            or payload.get("pageCount")
            or payload.get("total_pages")
            or payload.get("totalPages")
        )
        if page_count is not None:
            try:
                if page >= int(page_count):
                    break
            except (TypeError, ValueError):
                pass

        has_next = payload.get("has_next")
        if has_next is None:
            has_next = payload.get("hasNext")
        if has_next is False or len(batch) < page_size:
            break

    return workouts


def normalize(workouts: list[dict[str, Any]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    workout_rows = []
    set_rows = []

    for workout in workouts:
        workout_id = _first(workout, ["id", "workout_id"])
        start_time = pd.to_datetime(
            _first(workout, ["start_time", "startTime", "started_at", "created_at"]),
            errors="coerce",
            utc=True,
        )
        end_time = pd.to_datetime(
            _first(workout, ["end_time", "endTime", "ended_at", "updated_at"]),
            errors="coerce",
            utc=True,
        )
        created_at = pd.to_datetime(
            _first(workout, ["created_at", "createdAt"]),
            errors="coerce",
            utc=True,
        )
        updated_at = pd.to_datetime(
            _first(workout, ["updated_at", "updatedAt"]),
            errors="coerce",
            utc=True,
        )

        workout_rows.append(
            {
                "workout_id": workout_id,
                "title": _first(workout, ["title", "name"], "Workout"),
                "routine_id": _first(workout, ["routine_id", "routineId"]),
                "description": _first(workout, ["description", "notes", "note"], ""),
                "start_time": start_time,
                "end_time": end_time,
                "updated_at": updated_at,
                "created_at": created_at,
                "raw_json": json.dumps(workout, ensure_ascii=False),
            }
        )

        exercises = (
            workout.get("exercises")
            or workout.get("exercise_templates")
            or workout.get("workout_exercises")
            or []
        )
        for exercise_position, exercise in enumerate(exercises):
            exercise_index = _first(
                exercise, ["index", "exercise_index"], exercise_position
            )
            exercise_title = _first(
                exercise,
                ["title", "name", "exercise_title", "exerciseName"],
                "Exercise",
            )
            exercise_template_id = _first(
                exercise,
                ["exercise_template_id", "exerciseTemplateId", "template_id"],
            )
            sets = (
                exercise.get("sets")
                or exercise.get("workout_sets")
                or exercise.get("exercise_sets")
                or []
            )

            for set_position, set_item in enumerate(sets):
                weight = pd.to_numeric(
                    _first(set_item, ["weight_kg", "weightKg", "weight"]),
                    errors="coerce",
                )
                reps = pd.to_numeric(
                    _first(set_item, ["reps", "repetitions"]),
                    errors="coerce",
                )
                volume = None
                if pd.notna(weight) and pd.notna(reps):
                    volume = float(weight) * float(reps)

                set_index = _first(
                    set_item, ["index", "set_index"], set_position
                )
                set_rows.append(
                    {
                        "set_key": f"{workout_id}:{exercise_index}:{set_index}",
                        "workout_id": workout_id,
                        "exercise_index": exercise_index,
                        "exercise_title": exercise_title,
                        "exercise_template_id": exercise_template_id,
                        "set_index": set_index,
                        "set_type": _first(set_item, ["type", "set_type"], "normal"),
                        "weight_kg": weight,
                        "reps": reps,
                        "duration_seconds": pd.to_numeric(
                            _first(set_item, ["duration_seconds", "durationSeconds"]),
                            errors="coerce",
                        ),
                        "rpe": pd.to_numeric(set_item.get("rpe"), errors="coerce"),
                        "distance_meters": pd.to_numeric(
                            _first(set_item, ["distance_meters", "distanceMeters"]),
                            errors="coerce",
                        ),
                        "volume": volume,
                        "raw_json": json.dumps(set_item, ensure_ascii=False),
                    }
                )

    workouts_df = pd.DataFrame(workout_rows)
    sets_df = pd.DataFrame(set_rows)
    if not workouts_df.empty:
        workouts_df = workouts_df.drop_duplicates("workout_id", keep="last")
    if not sets_df.empty:
        sets_df = sets_df.drop_duplicates("set_key", keep="last")
    return workouts_df, sets_df


def _ensure_column(con, table: str, column: str, dtype: str) -> None:
    schema, name = table.split(".", 1)
    exists = con.execute(
        """
        SELECT COUNT(*)
        FROM information_schema.columns
        WHERE table_schema=? AND table_name=? AND column_name=?
        """,
        [schema, name, column],
    ).fetchone()[0]
    if not exists:
        con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {dtype}")


def ensure_tables(con) -> None:
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS raw.hevy_workouts (
            workout_id VARCHAR,
            title VARCHAR,
            routine_id VARCHAR,
            description VARCHAR,
            start_time TIMESTAMP,
            end_time TIMESTAMP,
            updated_at TIMESTAMP,
            created_at TIMESTAMP,
            raw_json JSON
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS raw.hevy_sets (
            set_key VARCHAR,
            workout_id VARCHAR,
            exercise_index INTEGER,
            exercise_title VARCHAR,
            exercise_template_id VARCHAR,
            set_index INTEGER,
            set_type VARCHAR,
            weight_kg DOUBLE,
            reps DOUBLE,
            duration_seconds DOUBLE,
            rpe DOUBLE,
            distance_meters DOUBLE,
            volume DOUBLE,
            raw_json JSON
        )
        """
    )

    workout_columns = {
        "workout_id": "VARCHAR",
        "title": "VARCHAR",
        "routine_id": "VARCHAR",
        "description": "VARCHAR",
        "start_time": "TIMESTAMP",
        "end_time": "TIMESTAMP",
        "updated_at": "TIMESTAMP",
        "created_at": "TIMESTAMP",
        "raw_json": "JSON",
    }
    set_columns = {
        "set_key": "VARCHAR",
        "workout_id": "VARCHAR",
        "exercise_index": "INTEGER",
        "exercise_title": "VARCHAR",
        "exercise_template_id": "VARCHAR",
        "set_index": "INTEGER",
        "set_type": "VARCHAR",
        "weight_kg": "DOUBLE",
        "reps": "DOUBLE",
        "duration_seconds": "DOUBLE",
        "rpe": "DOUBLE",
        "distance_meters": "DOUBLE",
        "volume": "DOUBLE",
        "raw_json": "JSON",
    }
    for column, dtype in workout_columns.items():
        _ensure_column(con, "raw.hevy_workouts", column, dtype)
    for column, dtype in set_columns.items():
        _ensure_column(con, "raw.hevy_sets", column, dtype)


def main() -> None:
    workouts = fetch_workouts()
    if not workouts:
        raise RuntimeError("Hevy API returned no workouts.")

    workouts_df, sets_df = normalize(workouts)
    con = duckdb.connect(str(DB_PATH))
    try:
        ensure_tables(con)

        if not workouts_df.empty:
            con.register("hevy_workouts_current", workouts_df)
            con.execute(
                """
                DELETE FROM raw.hevy_workouts
                WHERE workout_id IN (SELECT workout_id FROM hevy_workouts_current)
                """
            )
            con.execute(
                """
                INSERT INTO raw.hevy_workouts (
                    workout_id, title, routine_id, description,
                    start_time, end_time, updated_at, created_at, raw_json
                )
                SELECT
                    workout_id, title, routine_id, description,
                    start_time, end_time, updated_at, created_at, raw_json::JSON
                FROM hevy_workouts_current
                """
            )

        if not sets_df.empty:
            con.register("hevy_sets_current", sets_df)
            con.execute(
                """
                DELETE FROM raw.hevy_sets
                WHERE workout_id IN (SELECT DISTINCT workout_id FROM hevy_sets_current)
                """
            )
            con.execute(
                """
                INSERT INTO raw.hevy_sets (
                    set_key, workout_id, exercise_index, exercise_title,
                    exercise_template_id, set_index, set_type, weight_kg,
                    reps, duration_seconds, rpe, distance_meters, volume, raw_json
                )
                SELECT
                    set_key, workout_id, exercise_index, exercise_title,
                    exercise_template_id, set_index, set_type, weight_kg,
                    reps, duration_seconds, rpe, distance_meters, volume, raw_json::JSON
                FROM hevy_sets_current
                """
            )

        latest = con.execute(
            "SELECT MAX(CAST(start_time AS DATE)) FROM raw.hevy_workouts"
        ).fetchone()[0]
    finally:
        con.close()

    print(f"Fetched {len(workouts_df)} Hevy workouts and {len(sets_df)} sets.")
    print(f"Latest Hevy workout date: {latest}")


if __name__ == "__main__":
    main()
