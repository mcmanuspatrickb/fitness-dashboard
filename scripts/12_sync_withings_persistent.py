from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "fitness.duckdb"
LOOKBACK_DAYS = int(os.getenv("WITHINGS_LOOKBACK_DAYS", "400"))

# Keep this aligned with the production Health_Dashboard Withings scale mapping.
# Segmental measures have their own type IDs, so the whole-body types below can
# safely be loaded regardless of Withings' position_key value.
TYPE_TO_FIELD = {
    1: "weight_kg",
    5: "fat_free_mass_kg",
    6: "fat_percent",
    8: "fat_mass_kg",
    76: "muscle_mass_kg",
    77: "water_mass_kg",
    88: "bone_mass_kg",
    170: "visceral_fat",
}


def fetch_persistent_measurements() -> pd.DataFrame:
    database_url = os.getenv("WITHINGS_DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("WITHINGS_DATABASE_URL is not configured.")

    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError(
            "psycopg is required for persistent Withings sync. "
            "Install psycopg[binary]."
        ) from exc

    start = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)

    # Do not filter position_key here. The production dashboard reads all
    # persisted measurement rows, and recent Body Comp metrics can carry a
    # non--1 position_key even for scalar whole-body values. Filtering to -1
    # caused the weekly pipeline to receive current weight but lose current fat,
    # muscle, water and related body-composition values.
    with psycopg.connect(database_url) as conn:
        rows = conn.execute(
            """
            SELECT grpid, measured_at, type_id, scalar_value
            FROM withings_measurements
            WHERE measured_at >= %s
              AND scalar_value IS NOT NULL
              AND type_id = ANY(%s)
            ORDER BY measured_at, grpid, type_id
            """,
            (start, list(TYPE_TO_FIELD)),
        ).fetchall()

    if not rows:
        return pd.DataFrame()

    long_df = pd.DataFrame(
        rows,
        columns=["grpid", "measurement_time", "type_id", "scalar_value"],
    )
    long_df["measurement_time"] = pd.to_datetime(
        long_df["measurement_time"], utc=True, errors="coerce"
    )
    long_df = long_df.dropna(subset=["measurement_time"])
    long_df = long_df[long_df["type_id"].isin(TYPE_TO_FIELD)]
    if long_df.empty:
        return pd.DataFrame()

    long_df["field"] = long_df["type_id"].map(TYPE_TO_FIELD)
    wide = (
        long_df.pivot_table(
            index=["grpid", "measurement_time"],
            columns="field",
            values="scalar_value",
            aggfunc="last",
        )
        .reset_index()
        .rename_axis(None, axis=1)
    )

    for column in TYPE_TO_FIELD.values():
        if column not in wide.columns:
            wide[column] = pd.NA

    # Match the production dashboard's civil-date handling. Measurements are
    # stored as UTC in Postgres but the user's scale sessions are interpreted in
    # Europe/Berlin local time.
    wide["date"] = (
        wide["measurement_time"]
        .dt.tz_convert("Europe/Berlin")
        .dt.date
    )

    weight = pd.to_numeric(wide["weight_kg"], errors="coerce")
    muscle_mass = pd.to_numeric(wide["muscle_mass_kg"], errors="coerce")
    water_mass = pd.to_numeric(wide["water_mass_kg"], errors="coerce")

    wide["muscle_percent"] = (muscle_mass / weight * 100).where(weight > 0)
    wide["body_water_percent"] = (water_mass / weight * 100).where(weight > 0)
    wide["source"] = "withings_persistent_db"

    return wide[
        [
            "measurement_time",
            "date",
            "weight_kg",
            "fat_percent",
            "fat_mass_kg",
            "fat_free_mass_kg",
            "muscle_percent",
            "muscle_mass_kg",
            "body_water_percent",
            "visceral_fat",
            "bone_mass_kg",
            "source",
        ]
    ].sort_values("measurement_time")


def _ensure_column(con: duckdb.DuckDBPyConnection, column: str, dtype: str) -> None:
    exists = con.execute(
        """
        SELECT COUNT(*)
        FROM information_schema.columns
        WHERE table_schema='raw'
          AND table_name='withings_measurements'
          AND column_name=?
        """,
        [column],
    ).fetchone()[0]
    if not exists:
        con.execute(f"ALTER TABLE raw.withings_measurements ADD COLUMN {column} {dtype}")


def main() -> None:
    df = fetch_persistent_measurements()
    if df.empty:
        raise RuntimeError("Persistent Withings database returned no recent measurements.")

    con = duckdb.connect(str(DB_PATH))
    try:
        con.execute("CREATE SCHEMA IF NOT EXISTS raw")
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS raw.withings_measurements (
                measurement_time TIMESTAMP,
                date DATE,
                weight_kg DOUBLE,
                fat_percent DOUBLE,
                fat_mass_kg DOUBLE,
                fat_free_mass_kg DOUBLE,
                muscle_percent DOUBLE,
                muscle_mass_kg DOUBLE,
                body_water_percent DOUBLE,
                visceral_fat DOUBLE,
                bone_mass_kg DOUBLE,
                source VARCHAR,
                created_at TIMESTAMP DEFAULT now()
            )
            """
        )
        _ensure_column(con, "fat_free_mass_kg", "DOUBLE")

        first_date = min(df["date"])
        con.execute(
            "DELETE FROM raw.withings_measurements WHERE date >= ?",
            [first_date],
        )
        con.register("withings_recent_df", df)
        con.execute(
            """
            INSERT INTO raw.withings_measurements (
                measurement_time,
                date,
                weight_kg,
                fat_percent,
                fat_mass_kg,
                fat_free_mass_kg,
                muscle_percent,
                muscle_mass_kg,
                body_water_percent,
                visceral_fat,
                bone_mass_kg,
                source
            )
            SELECT
                measurement_time,
                date,
                weight_kg,
                fat_percent,
                fat_mass_kg,
                fat_free_mass_kg,
                muscle_percent,
                muscle_mass_kg,
                body_water_percent,
                visceral_fat,
                bone_mass_kg,
                source
            FROM withings_recent_df
            ORDER BY measurement_time
            """
        )

        latest = con.execute(
            "SELECT MAX(date) FROM raw.withings_measurements"
        ).fetchone()[0]
        latest_complete = con.execute(
            """
            SELECT MAX(date)
            FROM raw.withings_measurements
            WHERE weight_kg IS NOT NULL
              AND (fat_mass_kg IS NOT NULL OR fat_percent IS NOT NULL)
            """
        ).fetchone()[0]
    finally:
        con.close()

    print(f"Synced {len(df)} recent Withings measurement groups.")
    print(f"Latest Withings date in DuckDB: {latest}")
    print(f"Latest Withings body-composition date: {latest_complete}")


if __name__ == "__main__":
    main()
