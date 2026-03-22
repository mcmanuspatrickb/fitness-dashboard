from pathlib import Path
import json
import os

import duckdb
import pandas as pd
import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DB_PATH = PROJECT_ROOT / "db" / "fitness.duckdb"
HEVY_API_KEY = os.getenv("HEVY_API_KEY")
HEVY_BASE_URL = "https://api.hevyapp.com/v1"


def get_con() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(DB_PATH))


def hevy_get(path: str, params: dict | None = None) -> dict:
    response = requests.get(
        f"{HEVY_BASE_URL}{path}",
        headers={
            "api-key": HEVY_API_KEY,
            "accept": "application/json",
        },
        params=params or {},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def pick_workout_id(item: dict) -> str | None:
    if isinstance(item.get("workout"), dict):
        return item["workout"].get("id")
    return item.get("workout_id") or item.get("id")


def normalize_events(payload: dict) -> pd.DataFrame:
    items = payload.get("events") or payload.get("data") or []
    rows = []

    for item in items:
        workout = item.get("workout", {}) if isinstance(item.get("workout"), dict) else {}
        workout_id = pick_workout_id(item)

        event_time = (
            item.get("event_time")
            or item.get("updated_at")
            or item.get("created_at")
            or item.get("deleted_at")
            or workout.get("updated_at")
            or workout.get("created_at")
            or workout.get("start_time")
        )

        rows.append(
            {
                "event_id": item.get("id"),
                "event_type": item.get("type"),
                "workout_id": workout_id,
                "event_time": pd.to_datetime(event_time, errors="coerce", utc=True),
                "raw_json": json.dumps(item, ensure_ascii=False),
            }
        )

    return pd.DataFrame(rows)


def normalize_workouts_from_events(payload: dict) -> pd.DataFrame:
    items = payload.get("events") or payload.get("data") or []
    rows = []

    for item in items:
        workout = item.get("workout")
        if not isinstance(workout, dict):
            continue

        rows.append(
            {
                "workout_id": workout.get("id"),
                "title": workout.get("title"),
                "routine_id": workout.get("routine_id"),
                "description": workout.get("description"),
                "start_time": pd.to_datetime(workout.get("start_time"), errors="coerce", utc=True),
                "end_time": pd.to_datetime(workout.get("end_time"), errors="coerce", utc=True),
                "updated_at": pd.to_datetime(workout.get("updated_at"), errors="coerce", utc=True),
                "created_at": pd.to_datetime(workout.get("created_at"), errors="coerce", utc=True),
                "raw_json": json.dumps(workout, ensure_ascii=False),
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    return df.drop_duplicates(subset=["workout_id"], keep="last").reset_index(drop=True)


def normalize_sets_from_events(payload: dict) -> pd.DataFrame:
    items = payload.get("events") or payload.get("data") or []
    rows = []

    for item in items:
        workout = item.get("workout")
        if not isinstance(workout, dict):
            continue

        workout_id = workout.get("id")
        exercises = workout.get("exercises", []) or []

        for exercise_idx, exercise in enumerate(exercises):
            exercise_title = exercise.get("title")
            exercise_template_id = exercise.get("exercise_template_id")
            sets = exercise.get("sets", []) or []

            for set_idx, s in enumerate(sets):
                set_key = f"{workout_id}:{exercise_idx}:{set_idx}"
                weight_kg = s.get("weight_kg")
                reps = s.get("reps")
                duration_seconds = s.get("duration_seconds")

                volume = None
                if weight_kg is not None and reps is not None:
                    try:
                        volume = float(weight_kg) * float(reps)
                    except Exception:
                        volume = None

                rows.append(
                    {
                        "set_key": set_key,
                        "workout_id": workout_id,
                        "exercise_index": exercise_idx,
                        "exercise_title": exercise_title,
                        "exercise_template_id": exercise_template_id,
                        "set_index": set_idx,
                        "set_type": s.get("type"),
                        "weight_kg": weight_kg,
                        "reps": reps,
                        "duration_seconds": duration_seconds,
                        "rpe": s.get("rpe"),
                        "distance_meters": s.get("distance_meters"),
                        "volume": volume,
                        "raw_json": json.dumps(s, ensure_ascii=False),
                    }
                )

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    return df.drop_duplicates(subset=["set_key"], keep="last").reset_index(drop=True)


def table_exists(con: duckdb.DuckDBPyConnection, full_table_name: str) -> bool:
    schema_name, table_name = full_table_name.split(".", 1)
    row = con.execute("""
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_schema = ? AND table_name = ?
    """, [schema_name, table_name]).fetchone()
    return bool(row and row[0] > 0)


def ensure_column(con: duckdb.DuckDBPyConnection, table_name: str, column_name: str, column_type: str) -> None:
    schema_name, bare_table_name = table_name.split(".", 1)
    exists = con.execute("""
        SELECT COUNT(*)
        FROM information_schema.columns
        WHERE table_schema = ?
          AND table_name = ?
          AND column_name = ?
    """, [schema_name, bare_table_name, column_name]).fetchone()[0]

    if exists == 0:
        con.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")


def ensure_tables(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")

    con.execute("""
        CREATE TABLE IF NOT EXISTS raw.hevy_workout_events (
            event_id VARCHAR,
            event_type VARCHAR,
            workout_id VARCHAR,
            event_time TIMESTAMP,
            raw_json JSON
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS raw.hevy_workouts (
            workout_id VARCHAR,
            title VARCHAR,
            raw_json JSON
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS raw.hevy_sets (
            raw_json JSON
        )
    """)

    # Migrate raw.hevy_workout_events
    ensure_column(con, "raw.hevy_workout_events", "event_id", "VARCHAR")
    ensure_column(con, "raw.hevy_workout_events", "event_type", "VARCHAR")
    ensure_column(con, "raw.hevy_workout_events", "workout_id", "VARCHAR")
    ensure_column(con, "raw.hevy_workout_events", "event_time", "TIMESTAMP")
    ensure_column(con, "raw.hevy_workout_events", "raw_json", "JSON")

    # Migrate raw.hevy_workouts
    ensure_column(con, "raw.hevy_workouts", "workout_id", "VARCHAR")
    ensure_column(con, "raw.hevy_workouts", "title", "VARCHAR")
    ensure_column(con, "raw.hevy_workouts", "routine_id", "VARCHAR")
    ensure_column(con, "raw.hevy_workouts", "description", "VARCHAR")
    ensure_column(con, "raw.hevy_workouts", "start_time", "TIMESTAMP")
    ensure_column(con, "raw.hevy_workouts", "end_time", "TIMESTAMP")
    ensure_column(con, "raw.hevy_workouts", "updated_at", "TIMESTAMP")
    ensure_column(con, "raw.hevy_workouts", "created_at", "TIMESTAMP")
    ensure_column(con, "raw.hevy_workouts", "raw_json", "JSON")

    # Migrate raw.hevy_sets
    ensure_column(con, "raw.hevy_sets", "set_key", "VARCHAR")
    ensure_column(con, "raw.hevy_sets", "workout_id", "VARCHAR")
    ensure_column(con, "raw.hevy_sets", "exercise_index", "INTEGER")
    ensure_column(con, "raw.hevy_sets", "exercise_title", "VARCHAR")
    ensure_column(con, "raw.hevy_sets", "exercise_template_id", "VARCHAR")
    ensure_column(con, "raw.hevy_sets", "set_index", "INTEGER")
    ensure_column(con, "raw.hevy_sets", "set_type", "VARCHAR")
    ensure_column(con, "raw.hevy_sets", "weight_kg", "DOUBLE")
    ensure_column(con, "raw.hevy_sets", "reps", "DOUBLE")
    ensure_column(con, "raw.hevy_sets", "duration_seconds", "DOUBLE")
    ensure_column(con, "raw.hevy_sets", "rpe", "DOUBLE")
    ensure_column(con, "raw.hevy_sets", "distance_meters", "DOUBLE")
    ensure_column(con, "raw.hevy_sets", "volume", "DOUBLE")
    ensure_column(con, "raw.hevy_sets", "raw_json", "JSON")


def upsert_events(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> None:
    if df.empty:
        print("No event rows to upsert.")
        return

    con.register("events_df", df)

    con.execute("""
        DELETE FROM raw.hevy_workout_events
        WHERE workout_id IN (
            SELECT DISTINCT workout_id
            FROM events_df
            WHERE workout_id IS NOT NULL
        )
    """)

    con.execute("""
        INSERT INTO raw.hevy_workout_events (
            event_id,
            event_type,
            workout_id,
            event_time,
            raw_json
        )
        SELECT
            event_id,
            event_type,
            workout_id,
            event_time,
            raw_json::JSON
        FROM events_df
    """)


def upsert_workouts(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> None:
    if df.empty:
        print("No workout rows to upsert.")
        return

    con.register("workouts_df", df)

    con.execute("""
        DELETE FROM raw.hevy_workouts
        WHERE workout_id IN (
            SELECT DISTINCT workout_id
            FROM workouts_df
            WHERE workout_id IS NOT NULL
        )
    """)

    con.execute("""
        INSERT INTO raw.hevy_workouts (
            workout_id,
            title,
            routine_id,
            description,
            start_time,
            end_time,
            updated_at,
            created_at,
            raw_json
        )
        SELECT
            workout_id,
            title,
            routine_id,
            description,
            start_time,
            end_time,
            updated_at,
            created_at,
            raw_json::JSON
        FROM workouts_df
    """)


def upsert_sets(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> None:
    if df.empty:
        print("No set rows to upsert.")
        return

    con.register("sets_df", df)

    con.execute("""
        DELETE FROM raw.hevy_sets
        WHERE workout_id IN (
            SELECT DISTINCT workout_id
            FROM sets_df
            WHERE workout_id IS NOT NULL
        )
    """)

    con.execute("""
        INSERT INTO raw.hevy_sets (
            set_key,
            workout_id,
            exercise_index,
            exercise_title,
            exercise_template_id,
            set_index,
            set_type,
            weight_kg,
            reps,
            duration_seconds,
            rpe,
            distance_meters,
            volume,
            raw_json
        )
        SELECT
            set_key,
            workout_id,
            exercise_index,
            exercise_title,
            exercise_template_id,
            set_index,
            set_type,
            weight_kg,
            reps,
            duration_seconds,
            rpe,
            distance_meters,
            volume,
            raw_json::JSON
        FROM sets_df
    """)


def main() -> None:
    since = "2016-01-01T00:00:00Z"
    print(f"Syncing Hevy events since {since}...")

    payload = hevy_get("/workouts/events", params={"since": since})

    items = payload.get("events") or payload.get("data") or []
    if items:
        print("\nFirst raw event payload:")
        print(json.dumps(items[0], indent=2)[:5000])

    events_df = normalize_events(payload)
    workouts_df = normalize_workouts_from_events(payload)
    sets_df = normalize_sets_from_events(payload)

    print("\nNormalized events preview:")
    print(events_df.head().to_string(index=False))
    print(f"\nEvents with missing workout_id: {events_df['workout_id'].isna().sum()}")

    con = get_con()
    try:
        ensure_tables(con)
        upsert_events(con, events_df)
        upsert_workouts(con, workouts_df)
        upsert_sets(con, sets_df)

        print(f"\nUpserted {len(events_df)} Hevy events.")
        print(f"Upserted {len(workouts_df)} Hevy workouts.")
        print(f"Upserted {len(sets_df)} Hevy sets.")

        workout_preview = con.execute("""
            SELECT workout_id, title, routine_id, start_time, end_time, updated_at
            FROM raw.hevy_workouts
            ORDER BY start_time DESC NULLS LAST
            LIMIT 10
        """).fetchdf()

        print("\nWorkout preview:")
        print(workout_preview.to_string(index=False))

    finally:
        con.close()


if __name__ == "__main__":
    main()