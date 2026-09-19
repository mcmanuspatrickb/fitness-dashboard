from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "fitness.duckdb"
LOOKBACK_DAYS = int(os.getenv("GRIP_LOOKBACK_DAYS", "730"))


def fetch_grip_measurements() -> pd.DataFrame:
    database_url = (
        os.getenv("GRIP_DATABASE_URL", "").strip()
        or os.getenv("WITHINGS_DATABASE_URL", "").strip()
    )
    if not database_url:
        raise RuntimeError("GRIP_DATABASE_URL or WITHINGS_DATABASE_URL is not configured.")

    try:
        import psycopg
        from psycopg.errors import UndefinedTable
    except ImportError as exc:
        raise RuntimeError("psycopg[binary] is required for grip sync.") from exc

    start = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    try:
        with psycopg.connect(database_url) as conn:
            rows = conn.execute(
                """
                SELECT
                    measurement_id, measured_at, dominant_hand,
                    left_1_kg, left_2_kg, left_3_kg,
                    right_1_kg, right_2_kg, right_3_kg,
                    notes
                FROM grip_measurements
                WHERE measured_at >= %s
                ORDER BY measured_at
                """,
                (start,),
            ).fetchall()
    except UndefinedTable:
        return pd.DataFrame()

    columns = [
        "measurement_id", "measured_at", "dominant_hand",
        "left_1_kg", "left_2_kg", "left_3_kg",
        "right_1_kg", "right_2_kg", "right_3_kg", "notes",
    ]
    frame = pd.DataFrame(rows, columns=columns)
    if frame.empty:
        return frame

    frame["measured_at"] = pd.to_datetime(frame["measured_at"], errors="coerce", utc=True)
    frame = frame.dropna(subset=["measured_at"])
    frame["date"] = frame["measured_at"].dt.tz_convert("Europe/Berlin").dt.date

    left_cols = ["left_1_kg", "left_2_kg", "left_3_kg"]
    right_cols = ["right_1_kg", "right_2_kg", "right_3_kg"]
    for column in left_cols + right_cols:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    frame["best_left_kg"] = frame[left_cols].max(axis=1, skipna=True)
    frame["best_right_kg"] = frame[right_cols].max(axis=1, skipna=True)
    frame["avg_left_kg"] = frame[left_cols].mean(axis=1, skipna=True)
    frame["avg_right_kg"] = frame[right_cols].mean(axis=1, skipna=True)
    frame["best_overall_kg"] = frame[["best_left_kg", "best_right_kg"]].max(axis=1, skipna=True)
    stronger = frame["best_overall_kg"]
    difference = (frame["best_left_kg"] - frame["best_right_kg"]).abs()
    frame["asymmetry_pct"] = (difference / stronger * 100.0).where(stronger > 0)
    frame["source"] = "health_dashboard_grip"
    return frame


def main() -> None:
    frame = fetch_grip_measurements()
    con = duckdb.connect(str(DB_PATH))
    try:
        con.execute("CREATE SCHEMA IF NOT EXISTS raw")
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS raw.grip_measurements (
                measurement_id BIGINT,
                measured_at TIMESTAMP,
                date DATE,
                dominant_hand VARCHAR,
                left_1_kg DOUBLE,
                left_2_kg DOUBLE,
                left_3_kg DOUBLE,
                right_1_kg DOUBLE,
                right_2_kg DOUBLE,
                right_3_kg DOUBLE,
                best_left_kg DOUBLE,
                best_right_kg DOUBLE,
                avg_left_kg DOUBLE,
                avg_right_kg DOUBLE,
                best_overall_kg DOUBLE,
                asymmetry_pct DOUBLE,
                notes VARCHAR,
                source VARCHAR
            )
            """
        )

        if not frame.empty:
            first_date = min(frame["date"])
            con.execute("DELETE FROM raw.grip_measurements WHERE date >= ?", [first_date])
            con.register("grip_recent", frame)
            con.execute(
                """
                INSERT INTO raw.grip_measurements
                SELECT
                    measurement_id,
                    measured_at,
                    date,
                    dominant_hand,
                    left_1_kg, left_2_kg, left_3_kg,
                    right_1_kg, right_2_kg, right_3_kg,
                    best_left_kg, best_right_kg,
                    avg_left_kg, avg_right_kg,
                    best_overall_kg, asymmetry_pct,
                    notes, source
                FROM grip_recent
                ORDER BY measured_at
                """
            )

        count = con.execute("SELECT COUNT(*) FROM raw.grip_measurements").fetchone()[0]
        latest = con.execute("SELECT MAX(date) FROM raw.grip_measurements").fetchone()[0]
    finally:
        con.close()

    if frame.empty:
        print("No grip measurements were available from the persistent database.")
    else:
        print(f"Synced {len(frame)} grip measurement(s).")
    print(f"Grip rows in DuckDB: {count}")
    print(f"Latest grip date: {latest}")


if __name__ == "__main__":
    main()
