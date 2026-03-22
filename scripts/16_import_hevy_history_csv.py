from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import hashlib

import duckdb
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = PROJECT_ROOT / "data_raw" / "hevy" / "workouts.csv"
DB_PATH = PROJECT_ROOT / "db" / "fitness.duckdb"


def make_set_key(row: pd.Series) -> str:
    parts = [
        str(row.get("title", "")),
        str(row.get("start_time", "")),
        str(row.get("end_time", "")),
        str(row.get("exercise_title", "")),
        str(row.get("superset_id", "")),
        str(row.get("exercise_notes", "")),
        str(row.get("set_index", "")),
        str(row.get("set_type", "")),
        str(row.get("weight_kg", "")),
        str(row.get("reps", "")),
        str(row.get("distance_km", "")),
        str(row.get("duration_seconds", "")),
        str(row.get("rpe", "")),
    ]
    raw = "||".join(parts)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def table_exists(con: duckdb.DuckDBPyConnection, full_table_name: str) -> bool:
    schema_name, table_name = full_table_name.split(".", 1)
    row = con.execute("""
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_schema = ? AND table_name = ?
    """, [schema_name, table_name]).fetchone()
    return bool(row and row[0] > 0)


def column_exists(con: duckdb.DuckDBPyConnection, full_table_name: str, column_name: str) -> bool:
    schema_name, table_name = full_table_name.split(".", 1)
    row = con.execute("""
        SELECT COUNT(*)
        FROM information_schema.columns
        WHERE table_schema = ?
          AND table_name = ?
          AND column_name = ?
    """, [schema_name, table_name, column_name]).fetchone()
    return bool(row and row[0] > 0)


def ensure_column(con: duckdb.DuckDBPyConnection, full_table_name: str, column_name: str, column_type: str) -> None:
    if not column_exists(con, full_table_name, column_name):
        con.execute(f"ALTER TABLE {full_table_name} ADD COLUMN {column_name} {column_type}")


def ensure_historical_table(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")

    con.execute("""
        CREATE TABLE IF NOT EXISTS raw.hevy_sets_historical (
            set_key VARCHAR,
            workout_id VARCHAR,
            title VARCHAR,
            start_time TIMESTAMP,
            end_time TIMESTAMP,
            description VARCHAR,
            exercise_title VARCHAR,
            superset_id DOUBLE,
            exercise_notes VARCHAR,
            set_index DOUBLE,
            set_type VARCHAR,
            weight_kg DOUBLE,
            reps DOUBLE,
            distance_km DOUBLE,
            duration_seconds DOUBLE,
            rpe DOUBLE,
            volume DOUBLE,
            source VARCHAR,
            ingested_at TIMESTAMP
        )
    """)

    # Migrate older schemas forward
    ensure_column(con, "raw.hevy_sets_historical", "set_key", "VARCHAR")
    ensure_column(con, "raw.hevy_sets_historical", "workout_id", "VARCHAR")
    ensure_column(con, "raw.hevy_sets_historical", "title", "VARCHAR")
    ensure_column(con, "raw.hevy_sets_historical", "start_time", "TIMESTAMP")
    ensure_column(con, "raw.hevy_sets_historical", "end_time", "TIMESTAMP")
    ensure_column(con, "raw.hevy_sets_historical", "description", "VARCHAR")
    ensure_column(con, "raw.hevy_sets_historical", "exercise_title", "VARCHAR")
    ensure_column(con, "raw.hevy_sets_historical", "superset_id", "DOUBLE")
    ensure_column(con, "raw.hevy_sets_historical", "exercise_notes", "VARCHAR")
    ensure_column(con, "raw.hevy_sets_historical", "set_index", "DOUBLE")
    ensure_column(con, "raw.hevy_sets_historical", "set_type", "VARCHAR")
    ensure_column(con, "raw.hevy_sets_historical", "weight_kg", "DOUBLE")
    ensure_column(con, "raw.hevy_sets_historical", "reps", "DOUBLE")
    ensure_column(con, "raw.hevy_sets_historical", "distance_km", "DOUBLE")
    ensure_column(con, "raw.hevy_sets_historical", "duration_seconds", "DOUBLE")
    ensure_column(con, "raw.hevy_sets_historical", "rpe", "DOUBLE")
    ensure_column(con, "raw.hevy_sets_historical", "volume", "DOUBLE")
    ensure_column(con, "raw.hevy_sets_historical", "source", "VARCHAR")
    ensure_column(con, "raw.hevy_sets_historical", "ingested_at", "TIMESTAMP")

    # Backfill set_key from older set_id if needed
    has_set_key = column_exists(con, "raw.hevy_sets_historical", "set_key")
    has_set_id = column_exists(con, "raw.hevy_sets_historical", "set_id")
    if has_set_key and has_set_id:
        con.execute("""
            UPDATE raw.hevy_sets_historical
            SET set_key = CAST(set_id AS VARCHAR)
            WHERE set_key IS NULL
              AND set_id IS NOT NULL
        """)


def main() -> None:
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"Hevy CSV not found: {CSV_PATH}")

    print(f"Loading Hevy CSV export: {CSV_PATH}")
    df = pd.read_csv(CSV_PATH)
    print(f"Loaded {len(df)} rows.")

    expected_columns = [
        "title",
        "start_time",
        "end_time",
        "description",
        "exercise_title",
        "superset_id",
        "exercise_notes",
        "set_index",
        "set_type",
        "weight_kg",
        "reps",
        "distance_km",
        "duration_seconds",
        "rpe",
    ]

    missing = [c for c in expected_columns if c not in df.columns]
    if missing:
        raise ValueError(f"Missing expected columns in Hevy CSV: {missing}")

    df["start_time"] = pd.to_datetime(
        df["start_time"],
        format="%d %b %Y, %H:%M",
        errors="coerce",
    )
    df["end_time"] = pd.to_datetime(
        df["end_time"],
        format="%d %b %Y, %H:%M",
        errors="coerce",
    )

    numeric_cols = [
        "superset_id",
        "set_index",
        "weight_kg",
        "reps",
        "distance_km",
        "duration_seconds",
        "rpe",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["workout_id"] = (
        df["title"].fillna("unknown_workout").astype(str)
        + "__"
        + df["start_time"].dt.strftime("%Y-%m-%d %H:%M:%S").fillna("no_start_time")
    )

    df["volume"] = df["weight_kg"] * df["reps"]
    df.loc[df["weight_kg"].isna() | df["reps"].isna(), "volume"] = pd.NA

    df["set_key"] = df.apply(make_set_key, axis=1)
    df["source"] = "hevy_csv_history"
    df["ingested_at"] = datetime.now(timezone.utc)

    df = df[
        [
            "set_key",
            "workout_id",
            "title",
            "start_time",
            "end_time",
            "description",
            "exercise_title",
            "superset_id",
            "exercise_notes",
            "set_index",
            "set_type",
            "weight_kg",
            "reps",
            "distance_km",
            "duration_seconds",
            "rpe",
            "volume",
            "source",
            "ingested_at",
        ]
    ]

    con = duckdb.connect(str(DB_PATH))
    try:
        ensure_historical_table(con)

        con.register("hevy_csv_df", df)

        con.execute("""
            DELETE FROM raw.hevy_sets_historical
            WHERE set_key IN (
                SELECT set_key
                FROM hevy_csv_df
            )
        """)

        con.execute("""
            INSERT INTO raw.hevy_sets_historical (
                set_key,
                workout_id,
                title,
                start_time,
                end_time,
                description,
                exercise_title,
                superset_id,
                exercise_notes,
                set_index,
                set_type,
                weight_kg,
                reps,
                distance_km,
                duration_seconds,
                rpe,
                volume,
                source,
                ingested_at
            )
            SELECT
                set_key,
                workout_id,
                title,
                start_time,
                end_time,
                description,
                exercise_title,
                superset_id,
                exercise_notes,
                set_index,
                set_type,
                weight_kg,
                reps,
                distance_km,
                duration_seconds,
                rpe,
                volume,
                source,
                ingested_at
            FROM hevy_csv_df
        """)

        total_sets = con.execute("""
            SELECT COUNT(*)
            FROM raw.hevy_sets_historical
        """).fetchone()[0]

        total_workouts = con.execute("""
            SELECT COUNT(DISTINCT workout_id)
            FROM raw.hevy_sets_historical
        """).fetchone()[0]

        preview = con.execute("""
            SELECT
                workout_id,
                title,
                start_time,
                exercise_title,
                set_index,
                weight_kg,
                reps,
                duration_seconds,
                volume
            FROM raw.hevy_sets_historical
            ORDER BY start_time DESC, workout_id, exercise_title, set_index
            LIMIT 20
        """).fetchdf()

        print(f"Imported historical Hevy sets: {total_sets}")
        print(f"Distinct historical workouts: {total_workouts}")
        print(preview.to_string(index=False))

    finally:
        con.close()


if __name__ == "__main__":
    main()