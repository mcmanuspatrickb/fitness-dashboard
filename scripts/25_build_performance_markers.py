from __future__ import annotations

from pathlib import Path

import duckdb


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "fitness.duckdb"


def _table_exists(con: duckdb.DuckDBPyConnection, schema: str, table: str) -> bool:
    return bool(
        con.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema=? AND table_name=?
            """,
            [schema, table],
        ).fetchone()[0]
    )


def main() -> None:
    con = duckdb.connect(str(DB_PATH))
    try:
        con.execute("CREATE SCHEMA IF NOT EXISTS clean")
        con.execute(
            """
            CREATE OR REPLACE TABLE clean.performance_markers_daily (
                date DATE,
                waist_cm DOUBLE,
                grip_left_best_kg DOUBLE,
                grip_right_best_kg DOUBLE,
                grip_overall_best_kg DOUBLE,
                grip_asymmetry_pct DOUBLE,
                grip_measurement_count INTEGER
            )
            """
        )

        grip_exists = _table_exists(con, "raw", "grip_measurements")
        hevy_body_exists = _table_exists(con, "raw", "hevy_body_measurements")

        if not grip_exists and not hevy_body_exists:
            print("No grip or Hevy body-measurement raw tables exist yet.")
            return

        grip_cte = (
            """
            grip AS (
                SELECT
                    date,
                    arg_max(best_left_kg, measured_at) AS grip_left_best_kg,
                    arg_max(best_right_kg, measured_at) AS grip_right_best_kg,
                    arg_max(best_overall_kg, measured_at) AS grip_overall_best_kg,
                    arg_max(asymmetry_pct, measured_at) AS grip_asymmetry_pct,
                    COUNT(*)::INTEGER AS grip_measurement_count
                FROM raw.grip_measurements
                WHERE date IS NOT NULL
                GROUP BY date
            )
            """
            if grip_exists
            else """
            grip AS (
                SELECT
                    NULL::DATE AS date,
                    NULL::DOUBLE AS grip_left_best_kg,
                    NULL::DOUBLE AS grip_right_best_kg,
                    NULL::DOUBLE AS grip_overall_best_kg,
                    NULL::DOUBLE AS grip_asymmetry_pct,
                    NULL::INTEGER AS grip_measurement_count
                WHERE FALSE
            )
            """
        )
        waist_cte = (
            """
            waist AS (
                SELECT
                    date,
                    arg_max(waist_cm, measured_at) AS waist_cm
                FROM raw.hevy_body_measurements
                WHERE date IS NOT NULL AND waist_cm IS NOT NULL
                GROUP BY date
            )
            """
            if hevy_body_exists
            else """
            waist AS (
                SELECT NULL::DATE AS date, NULL::DOUBLE AS waist_cm
                WHERE FALSE
            )
            """
        )

        con.execute(
            f"""
            INSERT INTO clean.performance_markers_daily
            WITH
            {grip_cte},
            {waist_cte},
            dates AS (
                SELECT date FROM grip
                UNION
                SELECT date FROM waist
            )
            SELECT
                d.date,
                w.waist_cm,
                g.grip_left_best_kg,
                g.grip_right_best_kg,
                g.grip_overall_best_kg,
                g.grip_asymmetry_pct,
                g.grip_measurement_count
            FROM dates d
            LEFT JOIN grip g USING (date)
            LEFT JOIN waist w USING (date)
            WHERE d.date IS NOT NULL
            ORDER BY d.date
            """
        )

        count = con.execute("SELECT COUNT(*) FROM clean.performance_markers_daily").fetchone()[0]
        latest = con.execute(
            """
            SELECT MAX(date), MAX(date) FILTER (WHERE waist_cm IS NOT NULL),
                   MAX(date) FILTER (WHERE grip_overall_best_kg IS NOT NULL)
            FROM clean.performance_markers_daily
            """
        ).fetchone()
        preview = con.execute(
            "SELECT * FROM clean.performance_markers_daily ORDER BY date DESC LIMIT 10"
        ).fetchdf()
    finally:
        con.close()

    print(f"Built clean.performance_markers_daily with {count} row(s).")
    print(f"Latest marker date: {latest[0]} | waist: {latest[1]} | grip: {latest[2]}")
    if not preview.empty:
        print(preview.to_string(index=False))


if __name__ == "__main__":
    main()
